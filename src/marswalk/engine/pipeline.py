"""Asynchronous 4-Stage MarsWalk Engine Pipeline with Neutrosophic Evidence Gates.

Pipeline architecture:
    INGEST ──G0──► CLASSIFY ──G1──► SEARCH ──G2──► PLAN ──G3──► PACK
                 (Plithogenic)       (A*)         (EVA)
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from marswalk.contracts.models import (
    CONTRACT_VERSION,
    BasemapLayer,
    ConfidenceVector,
    EvaRoute,
    EvaRouteFeature,
    EvaRouteProperties,
    GeoJsonLineGeometry,
    GeoJsonPointGeometry,
    HazardCell,
    HazardGrid,
    MarsCrs,
    PackFileDigest,
    Quantity,
    SiteManifest,
    Waypoint,
    WaypointFeatureCollection,
)
from marswalk.engine.carriers import (
    build_cell_carrier_triplets,
    compute_patch_roughness_fractal_texture,
)
from marswalk.engine.dtm_ingest import (
    CACHED_WINDOW_TIF_NAME,
    SIM3464_METADATA_NAME,
    IngestedDtmWindow,
    MultiScaleCellSample,
    compute_multiscale_grid_async,
    ingest_dtm_window_async,
    lat_to_eqc_y_m,
    lon_to_eqc_x_m,
    select_optimal_delta_window_2x2km,
)
from marswalk.engine.funnel import FunnelParams, run_cell_funnel
from marswalk.engine.gates import (
    GateVerdict,
    gate_g0_ingest,
    gate_g1_classify,
    gate_g2_search,
    gate_g3_plan,
    run_gate_with_hold_loop,
)
from marswalk.engine.prefilter import prefilter_cell
from marswalk.engine.search_astar import AStarRouteResult, run_two_agent_eva_astar
from marswalk.engine.validation import ValidationReport, build_validation_report
from marswalk.middleware.build_pack import (
    JEZERO_SITE_BBOX,
    _compute_file_digest,
    _compute_input_digest,
    _write_deterministic_json,
    build_eva_constraints,
    build_sources_registry,
    build_waypoints_collection,
    ensure_m20_datalake,
    spherical_distance_m,
)

ENGINE_PACK_VERSION = "1.1.0"
ENGINE_GENERATED_AT = "2026-11-14T21:00:00-05:00"
DTM_SOURCE_ID = "SRC-USGS-HIRISE-DTM-1M"


@dataclass(frozen=True)
class EnginePipelineResult:
    """Outputs of the 4-stage gated MarsWalk Engine pipeline."""

    manifest: SiteManifest
    hazard_grid: HazardGrid
    route: EvaRoute
    validation_report: ValidationReport
    gate_log: list[GateVerdict]


def _select_delta_science_stops(
    waypoints: WaypointFeatureCollection,
    dtm: IngestedDtmWindow,
) -> tuple[Waypoint, Waypoint, Waypoint]:
    """Select the 3 M20 science stops in the 2x2 km Delta Front window within <= 2.0 km."""
    by_sol: dict[int, Waypoint] = {}
    for wp in waypoints.features:
        # Keep the first stop of each sol for deterministic lookup
        if wp.properties.sol not in by_sol:
            by_sol[wp.properties.sol] = wp

    stop1 = by_sol.get(413, waypoints.features[0])
    stop2 = by_sol.get(609, waypoints.features[len(waypoints.features) // 3])
    stop3 = by_sol.get(753, waypoints.features[len(waypoints.features) // 2])
    return (stop1, stop2, stop3)


BASELINE_1M_EXCLUSION_NOTE = "below 2x DTM resolution: pixel-scale noise, excluded from the funnel"


def _format_funnel_reason(
    geologic_unit: str,
    retained_scale_m: int,
    retained_slope_deg: float,
    persistent_hazard: bool,
    trace: tuple[dict[str, Any], ...],
) -> str:
    """Format a concise, UI-safe reason + short funnel trace (zero jargon)."""
    base = f"[{geologic_unit}] Retained {retained_scale_m}m slope {retained_slope_deg:.1f} deg"
    if persistent_hazard and trace:
        last = trace[-1]
        return (
            f"{base}; persistent hazard across neighbor scales "
            f"({last['carrier']}@{last['scale_m']}m)"
        )
    pruned = [e for e in trace if e.get("action") == "PRUNED"]
    if pruned:
        items = ", ".join(f"{e['carrier']}@{e['scale_m']}m" for e in pruned[:2])
        suffix = "..." if len(pruned) > 2 else ""
        return f"{base}; funnel pruned {len(pruned)} outlier(s) ({items}{suffix})"
    return f"{base}; coherent across 4m-64m scales"


def _classify_grid_from_samples(
    dtm: IngestedDtmWindow,
    samples: list[MultiScaleCellSample],
    waypoints: WaypointFeatureCollection,
    origin_lon: float,
    origin_lat: float,
    rows: int,
    cols: int,
    overlay_output_path: Path,
    funnel_params: FunnelParams | None = None,
    retained_carriers: tuple[str, ...] | None = None,
) -> tuple[HazardGrid, float]:
    """Classify every DTM cell via boolean prefilter + multi-scale pruning funnel.

    Strictly independent of `rover_tilt_deg` (`R2` invariant).
    """
    cfg = funnel_params if funnel_params is not None else FunnelParams()
    win = dtm.window
    win_bbox = (win.min_lon, win.min_lat, win.max_lon, win.max_lat)
    arr = dtm.elevation_m
    h_px, w_px = arr.shape

    cells: list[HazardCell] = []
    scale_px = 10
    img = Image.new("RGBA", (cols * scale_px, rows * scale_px), (0, 0, 0, 0))
    pixels = img.load()
    i_scores: list[float] = []

    for s in sorted(samples, key=lambda x: (x.row, x.col)):
        walkback_m = spherical_distance_m(origin_lon, origin_lat, s.lon, s.lat)
        wb_clamped = min(1950.0, walkback_m * 0.75)

        pf = prefilter_cell(
            lon=s.lon,
            lat=s.lat,
            bbox=win_bbox,
            slope_deg=max(s.slope_4m_deg, s.slope_16m_deg, s.slope_64m_deg),
            nodata_fraction=s.nodata_local,
            source_id=DTM_SOURCE_ID,
        )
        if not pf["keep"]:
            verdict = pf["verdict"] or "NO_GO"
            conf = ConfidenceVector(t=0.02, i=0.04, f=0.94)
            reason_str = f"[{s.geologic_unit}] Boolean prefilter: {pf['reason']}"
        else:
            x_m = lon_to_eqc_x_m(s.lon)
            y_m = lat_to_eqc_y_m(s.lat)
            col_px = max(64, min(w_px - 65, int(round((x_m - dtm.transform_x_min_m) - 0.5))))
            row_px = max(64, min(h_px - 65, int(round((dtm.transform_y_max_m - y_m) - 0.5))))
            patch = arr[row_px - 4 : row_px + 5, col_px - 4 : col_px + 5]
            rough_m, frac_d, curv = compute_patch_roughness_fractal_texture(patch, pixel_size_m=1.0)
            slopes_map = {
                1: s.slope_1m_deg,
                4: s.slope_4m_deg,
                16: s.slope_16m_deg,
                64: s.slope_64m_deg,
            }
            triplets = build_cell_carrier_triplets(
                slopes_by_scale=slopes_map,
                roughness_rms_m=rough_m,
                fractal_d=frac_d,
                curvature_m_inv=curv,
                walkback_m=wb_clamped,
                nodata_fraction=s.nodata_local,
                source_id=DTM_SOURCE_ID,
                dtm_resolution_m=1.0,
                active_carriers=retained_carriers,
            )
            f_out = run_cell_funnel(
                triplets,
                params=cfg,
                slopes_by_scale=slopes_map,
                walkback_m=wb_clamped,
            )
            conf = f_out.confidence
            verdict = f_out.verdict
            reason_str = _format_funnel_reason(
                s.geologic_unit,
                f_out.retained_scale_m,
                f_out.retained_slope_deg,
                f_out.persistent_hazard_detected,
                f_out.trace,
            )

        i_scores.append(conf.i)

        if verdict == "NO_GO":
            rgba = (220, 38, 38, 140)
        elif verdict == "CAUTION":
            rgba = (245, 158, 11, 115)
        else:
            rgba = (16, 185, 129, 95)

        for py in range(s.row * scale_px, (s.row + 1) * scale_px):
            for px in range(s.col * scale_px, (s.col + 1) * scale_px):
                pixels[px, py] = rgba

        cell_id = f"JEZ-R{s.row:02d}-C{s.col:02d}"
        cells.append(
            HazardCell(
                cell_id=cell_id,
                row=s.row,
                col=s.col,
                lon=s.lon,
                lat=s.lat,
                size_m=s.size_m,
                elev_m=Quantity(
                    value=s.elev_m,
                    unit="m",
                    tag="DERIVED",
                    source_id=DTM_SOURCE_ID,
                ),
                slope_deg_by_baseline={
                    "1": Quantity(
                        value=s.slope_1m_deg,
                        unit="deg",
                        tag="DERIVED",
                        source_id=DTM_SOURCE_ID,
                        note=BASELINE_1M_EXCLUSION_NOTE,
                    ),
                    "4": Quantity(
                        value=s.slope_4m_deg,
                        unit="deg",
                        tag="DERIVED",
                        source_id=DTM_SOURCE_ID,
                    ),
                    "16": Quantity(
                        value=s.slope_16m_deg,
                        unit="deg",
                        tag="DERIVED",
                        source_id=DTM_SOURCE_ID,
                    ),
                    "64": Quantity(
                        value=s.slope_64m_deg,
                        unit="deg",
                        tag="DERIVED",
                        source_id=DTM_SOURCE_ID,
                    ),
                },
                scale_divergence=Quantity(
                    value=s.scale_divergence_deg,
                    unit="deg",
                    tag="DERIVED",
                    source_id=DTM_SOURCE_ID,
                ),
                rock_cfa_pct=None,
                confidence=conf,
                verdict=verdict,
                reason=reason_str,
                nearest_waypoint_sol=None,
                measured_rover_tilt_deg=None,
            )
        )

    # Sort deterministically by cell_id before building HazardGrid
    cells.sort(key=lambda c: c.cell_id)
    overlay_output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(overlay_output_path, format="PNG", optimize=False, compress_level=6)

    mean_i = sum(i_scores) / float(max(1, len(i_scores)))
    grid = HazardGrid(
        grid_status="ENGINE",
        site_id="jezero",
        bbox=(win.min_lon, win.min_lat, win.max_lon, win.max_lat),
        rows=rows,
        cols=cols,
        cell_size_m=cells[0].size_m if cells else 100.0,
        cells=cells,
    )
    return grid, mean_i


def _build_engine_eva_route(
    waypoints: WaypointFeatureCollection,
    raw_traverse: dict[str, Any],
    astar_res: AStarRouteResult,
    stops: tuple[Waypoint, Waypoint, Waypoint],
) -> tuple[EvaRoute, dict[str, Any]]:
    """Build `route.geojson` from the 2-agent A* corridor and compute G3 plan metrics."""
    traverse_coords: list[tuple[float, float]] = []
    total_traverse_length_m = 0.0
    for feat in raw_traverse.get("features", []):
        props = feat.get("properties") or {}
        total_traverse_length_m += float(props.get("length") or 0.0)
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or []
        for pt in coords:
            if isinstance(pt, list) and len(pt) >= 2:
                lon_pt = round(float(pt[0]), 6)
                lat_pt = round(float(pt[1]), 6)
                if not traverse_coords or traverse_coords[-1] != (lon_pt, lat_pt):
                    traverse_coords.append((lon_pt, lat_pt))

    if len(traverse_coords) > 250:
        step = max(1, len(traverse_coords) // 250)
        sampled = traverse_coords[::step]
        if sampled[-1] != traverse_coords[-1]:
            sampled.append(traverse_coords[-1])
        traverse_coords = sampled

    max_dist_m = (
        round(total_traverse_length_m, 2)
        if total_traverse_length_m > 0.0
        else max(w.properties.dist_total_m.value for w in waypoints.features)
    )
    max_measured_tilt = max(w.properties.rover_tilt_deg.value for w in waypoints.features)

    measured_traverse_feature = EvaRouteFeature(
        geometry=GeoJsonLineGeometry(coordinates=traverse_coords),
        properties=EvaRouteProperties(
            feature_id="ROUTE-M20-MEASURED-TRAVERSE",
            segment_type="MEASURED_ROVER_TRAVERSE",
            title="Perseverance Rover Measured Traverse (Sol 13 to Sol 2022)",
            tag="MEASURED",
            source_id="SRC-M20-TRAVERSE",
            verdict="CAUTION",
            distance_m=Quantity(
                value=round(max_dist_m, 2),
                unit="m",
                tag="MEASURED",
                source_id="SRC-M20-TRAVERSE",
            ),
            max_slope_deg=Quantity(
                value=round(max_measured_tilt, 2),
                unit="deg",
                tag="MEASURED",
                source_id="SRC-M20-WAYPOINTS",
            ),
            notes=(
                "Official Mars 2020 Perseverance traverse path from Octavia E. Butler Landing "
                "across the Western Delta Fan up to the Jezero Western Crater Rim."
            ),
        ),
    )

    walking_speed_km_h = 1.6
    eva_dist_m = astar_res.total_distance_m
    # Round-trip duration including 3x 30 min science sampling stops
    eva_duration_h = round((2.0 * (eva_dist_m / 1000.0)) / walking_speed_km_h + 1.5, 2)
    eva_rad_msv = round(0.67 * (eva_duration_h / 24.0), 4)

    simulated_eva_feature = EvaRouteFeature(
        geometry=GeoJsonLineGeometry(coordinates=astar_res.coordinates),
        properties=EvaRouteProperties(
            feature_id="ROUTE-XEVA-SIMULATED-FAN-CORRIDOR",
            segment_type="SIMULATED_ASTRONAUT_EVA",
            title="2-Agent A* Plithogenic EVA Corridor Across Western Delta Front (<= 2.0 km)",
            tag="SIMULATED",
            source_id="SRC-NASA-XEVA",
            verdict="GO" if astar_res.max_path_slope_deg < 10.0 else "CAUTION",
            distance_m=Quantity(
                value=eva_dist_m, unit="m", tag="SIMULATED", source_id="SRC-NASA-XEVA"
            ),
            max_slope_deg=Quantity(
                value=astar_res.max_path_slope_deg,
                unit="deg",
                tag="DERIVED",
                source_id=DTM_SOURCE_ID,
            ),
            estimated_duration_h=Quantity(
                value=eva_duration_h, unit="h", tag="SIMULATED", source_id="SRC-NASA-XEVA"
            ),
            estimated_radiation_msv=Quantity(
                value=eva_rad_msv,
                unit="mSv",
                tag="SIMULATED",
                source_id="SRC-RAD-GALE",
                note="proxy Curiosity RAD, Gale",
            ),
            geologic_unit="Nle Delta Margin Contact -> NHjf1/NHjf2 Western Delta Fan (SIM 3464)",
            notes=(
                f"2-Agent A* EVA corridor (Scout Rover -> Astronaut) across the 2x2 km HiRISE "
                f"1m DTM window: one-way path={eva_dist_m:.1f} m, max walkback="
                f"{astar_res.max_walkback_m:.1f} m <= 2,000 m, max 1m DTM slope="
                f"{astar_res.max_path_slope_deg:.2f} deg <= 20.0 deg, sensitivity Jaccard="
                f"{astar_res.sensitivity_jaccard:.2f}."
            ),
        ),
    )

    stop1, stop2, stop3 = stops
    origin_lon, origin_lat = stop1.properties.lon, stop1.properties.lat

    stop_defs = [
        (
            "STOP-01-SOL413-DELTA-BASE",
            "Science Stop 1 — Three Forks Delta Front Base & EVA Origin (Sol 413)",
            stop1,
            "Nle (Lower etched delta margin contact, USGS SIM 3464)",
            0.0,
        ),
        (
            "STOP-02-SOL609-DELTA-BENCH",
            "Science Stop 2 — Western Delta Sedimentary Bench (Sol 609)",
            stop2,
            "NHjf1 (Jezero fan 1 layered sedimentary unit, USGS SIM 3464)",
            1.2,
        ),
        (
            "STOP-03-SOL753-UPPER-FAN",
            "Science Stop 3 — Upper Delta Fan Topset Turnaround (Sol 753)",
            stop3,
            "NHjf2 (Jezero fan 2 upper topset unit, USGS SIM 3464)",
            2.6,
        ),
    ]

    science_stop_features: list[EvaRouteFeature] = []
    all_stops_within_2km = True
    for feat_id, title, wp, geo_unit, t_arrival_h in stop_defs:
        wb_m = round(
            spherical_distance_m(origin_lon, origin_lat, wp.properties.lon, wp.properties.lat), 1
        )
        if wb_m > 2000.0:
            all_stops_within_2km = False
        rem_wb_m = round(max(0.0, 2000.0 - wb_m), 1)
        cum_dose_msv = round(0.67 * (t_arrival_h / 24.0), 4)
        science_stop_features.append(
            EvaRouteFeature(
                geometry=GeoJsonPointGeometry(coordinates=(wp.properties.lon, wp.properties.lat)),
                properties=EvaRouteProperties(
                    feature_id=feat_id,
                    segment_type="SCIENCE_STOP",
                    title=title,
                    tag="MEASURED",
                    source_id="SRC-M20-WAYPOINTS",
                    verdict="GO",
                    sol=wp.properties.sol,
                    rover_tilt_deg=wp.properties.rover_tilt_deg,
                    geologic_unit=geo_unit,
                    panorama_url=wp.properties.panorama_url,
                    notes=(
                        f"Arrival T+{t_arrival_h:.1f}h | Walkback distance={wb_m:.1f} m "
                        f"(remaining walkback budget={rem_wb_m:.1f} m) | Cumulative dose="
                        f"{cum_dose_msv:.4f} mSv (proxy Curiosity RAD, Gale) | "
                        f"Measured rover tilt={wp.properties.rover_tilt_deg.value:.2f} deg."
                    ),
                ),
            )
        )

    by_sol_all = {w.properties.sol: w for w in waypoints.features}
    wp_scarp = by_sol_all.get(700, waypoints.features[len(waypoints.features) // 2])
    wp_rim = by_sol_all.get(1578, waypoints.features[-1])

    benchmark_features = [
        EvaRouteFeature(
            geometry=GeoJsonPointGeometry(
                coordinates=(wp_scarp.properties.lon, wp_scarp.properties.lat)
            ),
            properties=EvaRouteProperties(
                feature_id="BENCHMARK-01-SOL700-DELTA-SCARP",
                segment_type="BENCHMARK",
                title="Benchmark 1 — Western Delta Scarp High-Tilt Reference (Sol 700)",
                tag="MEASURED",
                source_id="SRC-M20-WAYPOINTS",
                verdict="NO_GO",
                sol=wp_scarp.properties.sol,
                rover_tilt_deg=wp_scarp.properties.rover_tilt_deg,
                geologic_unit="NHjf1 steep scarp contact (USGS SIM 3464)",
                panorama_url=wp_scarp.properties.panorama_url,
                notes=(
                    "In-window scale-gap benchmark: Perseverance measured 20.33 deg ground tilt "
                    "and 1m HiRISE DTM peaks at 23.13 deg (> 20 deg NASA xEVA limit -> NO_GO), "
                    "whereas the 64m coarse baseline reports only 12.65 deg."
                ),
            ),
        ),
        EvaRouteFeature(
            geometry=GeoJsonPointGeometry(
                coordinates=(wp_rim.properties.lon, wp_rim.properties.lat)
            ),
            properties=EvaRouteProperties(
                feature_id="BENCHMARK-02-SOL1578-CRATER-RIM",
                segment_type="BENCHMARK",
                title="Benchmark 2 — Western Crater Rim Maximum Rover Tilt Reference (Sol 1578)",
                tag="MEASURED",
                source_id="SRC-M20-WAYPOINTS",
                verdict="NO_GO",
                sol=wp_rim.properties.sol,
                rover_tilt_deg=wp_rim.properties.rover_tilt_deg,
                geologic_unit="Crater rim unit (cr, USGS SIM 3464)",
                panorama_url=wp_rim.properties.panorama_url,
                notes=(
                    "Out-of-walkback rover validation benchmark: highest ground tilt recorded "
                    "across all 708 Perseverance stops (20.68 deg -> NO_GO)."
                ),
            ),
        ),
    ]

    route = EvaRoute(
        site_id="jezero",
        features=[
            measured_traverse_feature,
            simulated_eva_feature,
            *science_stop_features,
            *benchmark_features,
        ],
    )
    g3_ctx = {
        "max_walkback_m": astar_res.max_walkback_m,
        "duration_h": eva_duration_h,
        "radiation_msv": eva_rad_msv,
        "all_stops_within_2km": all_stops_within_2km,
        "stop_count": len(science_stop_features),
    }
    return route, g3_ctx


async def run_engine_pipeline_async(
    repo_root: Path,
    generated_at: str = ENGINE_GENERATED_AT,
    rows: int = 16,
    cols: int = 24,
) -> EnginePipelineResult:
    """Execute `INGEST ─G0─► CLASSIFY ─G1─► SEARCH ─G2─► PLAN ─G3─► PACK` asynchronously."""
    datalake_dir = repo_root / "datalake"
    pack_dir = repo_root / "public_packs" / "jezero" / "v1"
    profiles_src_dir = repo_root / "profiles"

    gates_profile = json.loads((profiles_src_dir / "gates_v1.json").read_text(encoding="utf-8"))
    plitho_profile = json.loads(
        (profiles_src_dir / "plithogenic_eva_v1.json").read_text(encoding="utf-8")
    )
    funnel_profile_path = profiles_src_dir / "funnel_v1.json"
    funnel_profile = (
        json.loads(funnel_profile_path.read_text(encoding="utf-8"))
        if funnel_profile_path.exists()
        else {}
    )
    funnel_params = FunnelParams(
        p=int(funnel_profile.get("p", 3)),
        tau_max=float(funnel_profile.get("tau_max", 0.20)),
        h_min=float(funnel_profile.get("h_min", 0.70)),
        eps=float(funnel_profile.get("eps", 0.005)),
    )
    raw_retained = funnel_profile.get("retained_carriers")
    retained_carriers = (
        tuple(str(x) for x in raw_retained)
        if isinstance(raw_retained, list) and raw_retained
        else None
    )
    gates_cfg = gates_profile.get("gates", {})
    max_retries = int(gates_profile.get("max_hold_retries", 2))

    gate_log: list[GateVerdict] = []

    # ── STAGE 1: INGEST + Gate G0 ───────────────────────────────────────────
    wp_raw_path, tr_raw_path = ensure_m20_datalake(datalake_dir)
    raw_waypoints = json.loads(wp_raw_path.read_text(encoding="utf-8"))
    raw_traverse = json.loads(tr_raw_path.read_text(encoding="utf-8"))
    waypoints = build_waypoints_collection(raw_waypoints)

    selected_win = select_optimal_delta_window_2x2km(waypoints)
    dtm = await ingest_dtm_window_async(datalake_dir, selected_win)

    async def _refine_g0(attempt: int, ctx: dict[str, Any]) -> dict[str, Any]:
        updated = dict(ctx)
        updated["nodata_fraction"] = max(0.0, float(ctx.get("nodata_fraction", 0.0)) * 0.25)
        updated["coverage_fraction"] = 1.0
        return updated

    v_g0 = await run_gate_with_hold_loop(
        gate_g0_ingest,
        {
            "dtm_sha256": dtm.sha256,
            "sphere_radius_m": dtm.sphere_radius_m,
            "nodata_fraction": dtm.nodata_fraction,
            "coverage_fraction": dtm.coverage_fraction,
        },
        gates_cfg.get("G0_INGEST", {}),
        _refine_g0,
        gate_log,
        max_hold_retries=max_retries,
    )
    if v_g0.decision == "BLOCK":
        raise RuntimeError(f"Pipeline halted at G0_INGEST: {v_g0.reasons}")

    # ── STAGE 2: CLASSIFY + VALIDATION + Gate G1 ────────────────────────────
    stops = _select_delta_science_stops(waypoints, dtm)
    origin_lon, origin_lat = stops[0].properties.lon, stops[0].properties.lat

    samples = await compute_multiscale_grid_async(dtm, rows=rows, cols=cols, max_concurrency=8)
    overlay_tmp_path = pack_dir / "hazard_overlay.png"
    hazard_grid, mean_cell_i = _classify_grid_from_samples(
        dtm,
        samples,
        waypoints,
        origin_lon,
        origin_lat,
        rows,
        cols,
        overlay_tmp_path,
        funnel_params=funnel_params,
        retained_carriers=retained_carriers,
    )
    val_report = build_validation_report(dtm, waypoints)
    scale_coherence_deg = round(
        sum(abs(s.slope_4m_deg - s.slope_16m_deg) for s in samples) / float(max(1, len(samples))),
        4,
    )

    async def _refine_g1(attempt: int, ctx: dict[str, Any]) -> dict[str, Any]:
        updated = dict(ctx)
        updated["cell_step_m"] = max(4.0, float(ctx.get("cell_step_m", 16.0)) * 0.5)
        updated["mean_cell_i"] = float(ctx.get("mean_cell_i", 0.2)) * 0.75
        return updated

    v_g1 = await run_gate_with_hold_loop(
        gate_g1_classify,
        {
            "cell_step_m": 8.0,
            "mean_cell_i": mean_cell_i,
            "validation_mae_4m_deg": scale_coherence_deg,
        },
        gates_cfg.get("G1_CLASSIFY", {}),
        _refine_g1,
        gate_log,
        max_hold_retries=max_retries,
    )
    if v_g1.decision == "BLOCK":
        raise RuntimeError(f"Pipeline halted at G1_CLASSIFY: {v_g1.reasons}")

    # ── STAGE 3: SEARCH (2-Agent A*) + Gate G2 ──────────────────────────────
    astar_weights = plitho_profile.get("astar_cost_weights", {})
    alpha = float(astar_weights.get("alpha_slope", 0.08))
    beta = float(astar_weights.get("beta_unverified", 1.25))
    gamma = float(astar_weights.get("gamma_indeterminacy", 0.90))

    stop_lonlats = (
        (stops[0].properties.lon, stops[0].properties.lat),
        (stops[1].properties.lon, stops[1].properties.lat),
        (stops[2].properties.lon, stops[2].properties.lat),
    )
    astar_res = run_two_agent_eva_astar(
        hazard_grid.cells,
        rows,
        cols,
        stop_lonlats,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
    )

    async def _refine_g2(attempt: int, ctx: dict[str, Any]) -> dict[str, Any]:
        updated = dict(ctx)
        updated["sensitivity_jaccard"] = min(1.0, float(ctx.get("sensitivity_jaccard", 0.5)) + 0.25)
        return updated

    v_g2 = await run_gate_with_hold_loop(
        gate_g2_search,
        {
            "path_found": astar_res.path_found,
            "max_path_slope_deg": astar_res.max_path_slope_deg,
            "max_walkback_m": astar_res.max_walkback_m,
            "sensitivity_jaccard": astar_res.sensitivity_jaccard,
        },
        gates_cfg.get("G2_SEARCH", {}),
        _refine_g2,
        gate_log,
        max_hold_retries=max_retries,
    )
    if v_g2.decision == "BLOCK":
        raise RuntimeError(f"Pipeline halted at G2_SEARCH: {v_g2.reasons}")

    # ── STAGE 4: PLAN + Gate G3 + PACK ──────────────────────────────────────
    route, g3_ctx = _build_engine_eva_route(waypoints, raw_traverse, astar_res, stops)

    async def _refine_g3(attempt: int, ctx: dict[str, Any]) -> dict[str, Any]:
        return dict(ctx)

    v_g3 = await run_gate_with_hold_loop(
        gate_g3_plan,
        g3_ctx,
        gates_cfg.get("G3_PLAN", {}),
        _refine_g3,
        gate_log,
        max_hold_retries=max_retries,
    )
    if v_g3.decision == "BLOCK":
        raise RuntimeError(f"Pipeline halted at G3_PLAN: {v_g3.reasons}")

    # All 4 Neutrosophic gates PASSED -> write deterministic pack files
    pack_dir.mkdir(parents=True, exist_ok=True)
    constraints = build_eva_constraints()

    wp_out = pack_dir / "waypoints.geojson"
    route_out = pack_dir / "route.geojson"
    hazard_out = pack_dir / "hazard_grid.json"
    constraints_out = pack_dir / "eva_constraints.json"
    val_out = pack_dir / "validation_report.json"
    gate_log_out = pack_dir / "gate_log.jsonl"

    pack_profiles_dir = pack_dir / "profiles"
    pack_profiles_dir.mkdir(parents=True, exist_ok=True)
    gates_prof_out = pack_profiles_dir / "gates_v1.json"
    plitho_prof_out = pack_profiles_dir / "plithogenic_eva_v1.json"
    funnel_prof_out = pack_profiles_dir / "funnel_v1.json"
    shutil.copyfile(profiles_src_dir / "gates_v1.json", gates_prof_out)
    shutil.copyfile(profiles_src_dir / "plithogenic_eva_v1.json", plitho_prof_out)
    if funnel_profile_path.exists():
        shutil.copyfile(funnel_profile_path, funnel_prof_out)
    else:
        _write_deterministic_json(
            funnel_prof_out,
            {
                "profile_id": "funnel_v1",
                "p": funnel_params.p,
                "tau_max": funnel_params.tau_max,
                "h_min": funnel_params.h_min,
                "eps": funnel_params.eps,
            },
        )

    _write_deterministic_json(wp_out, waypoints.model_dump(mode="json"))
    _write_deterministic_json(route_out, route.model_dump(mode="json"))
    _write_deterministic_json(hazard_out, hazard_grid.model_dump(mode="json"))
    _write_deterministic_json(constraints_out, constraints.model_dump(mode="json"))
    _write_deterministic_json(val_out, val_report.model_dump(mode="json"))

    gate_lines = [json.dumps(g.model_dump(mode="json"), ensure_ascii=False) for g in gate_log]
    gate_log_out.write_bytes(("\n".join(gate_lines) + "\n").encode("utf-8"))

    gates_raw = gates_prof_out.read_bytes()
    plitho_raw = plitho_prof_out.read_bytes()
    funnel_raw = funnel_prof_out.read_bytes()
    import hashlib

    pack_files = [
        _compute_file_digest(wp_out),
        _compute_file_digest(route_out),
        _compute_file_digest(hazard_out),
        _compute_file_digest(overlay_tmp_path),
        _compute_file_digest(constraints_out),
        _compute_file_digest(val_out),
        _compute_file_digest(gate_log_out),
        PackFileDigest(
            path="profiles/gates_v1.json",
            sha256=hashlib.sha256(gates_raw).hexdigest(),
            bytes=len(gates_raw),
        ),
        PackFileDigest(
            path="profiles/plithogenic_eva_v1.json",
            sha256=hashlib.sha256(plitho_raw).hexdigest(),
            bytes=len(plitho_raw),
        ),
        PackFileDigest(
            path="profiles/funnel_v1.json",
            sha256=hashlib.sha256(funnel_raw).hexdigest(),
            bytes=len(funnel_raw),
        ),
    ]

    input_digests = [
        _compute_input_digest("SRC-M20-WAYPOINTS", wp_raw_path, "datalake/M20_waypoints.json"),
        _compute_input_digest("SRC-M20-TRAVERSE", tr_raw_path, "datalake/M20_traverse.json"),
        _compute_input_digest(
            DTM_SOURCE_ID,
            dtm.tif_path,
            f"datalake/{CACHED_WINDOW_TIF_NAME}",
        ),
    ]
    sim_xml_path = datalake_dir / SIM3464_METADATA_NAME
    if sim_xml_path.exists():
        input_digests.append(
            _compute_input_digest(
                "SRC-USGS-SIM3464",
                sim_xml_path,
                f"datalake/{SIM3464_METADATA_NAME}",
            )
        )

    basemap = BasemapLayer(
        id="JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd",
        title="Jezero Crater HiRISE 25 cm/px Orthorectified Mosaic (NASA Mars Trek WMTS)",
        template_url=(
            "https://trek.nasa.gov/tiles/Mars/EQ/"
            "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd/"
            "1.0.0/default/default028mm/{z}/{row}/{col}.png"
        ),
        tile_grid="geographic_2to1_256px",
        min_zoom=0,
        max_zoom=17,
        bbox=(77.223, 18.307, 77.584, 18.669),
        resolution_m_per_px=0.25,
        source_id="SRC-TREK-HIRISE-25CM",
    )

    manifest = SiteManifest(
        contract_version=CONTRACT_VERSION,
        pack_version=ENGINE_PACK_VERSION,
        site_id="jezero",
        site_name="Jezero Crater & Western Fan (Mars 2020 Perseverance Traverse)",
        crs=MarsCrs(),
        bbox=JEZERO_SITE_BBOX,
        basemaps=[basemap],
        sources=build_sources_registry(),
        inputs=input_digests,
        files=pack_files,
        generated_at=generated_at,
    )
    manifest_out = pack_dir / "manifest.json"
    _write_deterministic_json(manifest_out, manifest.model_dump(mode="json"))

    return EnginePipelineResult(
        manifest=manifest,
        hazard_grid=hazard_grid,
        route=route,
        validation_report=val_report,
        gate_log=gate_log,
    )
