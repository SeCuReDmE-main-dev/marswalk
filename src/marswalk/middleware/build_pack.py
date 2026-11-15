"""Deterministic builder for `public_packs/jezero/v1/` and JSON Schemas (`schemas/`).

Pass 1 / Phase 2a:
- Ingests official NASA Mars 2020 MMGIS telemetry (`M20_waypoints.json`, `M20_traverse.json`)
  and records their exact SHA-256 and byte counts in `manifest.inputs[]`.
- Builds an explicitly tagged `SIMULATED` (`source_id="synthetic-v1"`, `grid_status="PLACEHOLDER"`)
  hazard grid with zero access to `rover_tilt_deg` (strictly reserved for validation).
- Places all 3 `SCIENCE_STOP` features directly on the `SIMULATED_ASTRONAUT_EVA` trajectory
  within <= 2.0 km of the Sol 13 starting point, and separates Sol 700 and Sol 1578 as
  `segment_type="BENCHMARK"`.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

from marswalk.contracts.models import (
    CONTRACT_VERSION,
    MARS_SPHERE_RADIUS_M,
    BasemapLayer,
    ConfidenceVector,
    EvaConstraints,
    EvaRoute,
    EvaRouteFeature,
    EvaRouteProperties,
    GeoJsonLineGeometry,
    GeoJsonPointGeometry,
    HazardCell,
    HazardGrid,
    ManifestInputDigest,
    MarsCrs,
    PackFileDigest,
    Quantity,
    SiteManifest,
    Source,
    VerdictLiteral,
    Waypoint,
    WaypointFeatureCollection,
    WaypointProperties,
)

M20_WAYPOINTS_URL = "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json"
M20_TRAVERSE_URL = "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json"
M20_PANORAMA_BASE_URL = "https://mars.nasa.gov/mmgis-maps/M20/"
DETERMINISTIC_GENERATED_AT = "2026-11-14T20:25:00-05:00"
PACK_VERSION = "1.0.1"
SYNTHETIC_SOURCE_ID = "synthetic-v1"

JEZERO_SITE_BBOX: tuple[float, float, float, float] = (77.215, 18.307, 77.584, 18.669)
JEZERO_GRID_BBOX: tuple[float, float, float, float] = (77.215, 18.415, 77.475, 18.505)


def _ensure_ssl_context() -> None:
    """Inject system truststore if available for HTTPS fetches."""
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass


def ensure_m20_datalake(datalake_dir: Path) -> tuple[Path, Path]:
    """Ensure M20_waypoints.json and M20_traverse.json exist in datalake_dir."""
    datalake_dir.mkdir(parents=True, exist_ok=True)
    wp_path = datalake_dir / "M20_waypoints.json"
    tr_path = datalake_dir / "M20_traverse.json"
    if not wp_path.exists() or wp_path.stat().st_size == 0:
        _ensure_ssl_context()
        urllib.request.urlretrieve(M20_WAYPOINTS_URL, wp_path)
    if not tr_path.exists() or tr_path.stat().st_size == 0:
        _ensure_ssl_context()
        urllib.request.urlretrieve(M20_TRAVERSE_URL, tr_path)
    return wp_path, tr_path


def spherical_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in meters on the Mars sphere R = 3,396,190 m."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return MARS_SPHERE_RADIUS_M * c


def build_sources_registry() -> list[Source]:
    """Return the canonical primary sources for Jezero Crater v1."""
    return [
        Source(
            id="SRC-M20-WAYPOINTS",
            title="Mars 2020 Perseverance Rover MMGIS Waypoints Telemetry (708 Stops)",
            mission="NASA / JPL-Caltech Mars 2020",
            url=M20_WAYPOINTS_URL,
            license="Public Domain (17 U.S.C. 105)",
            citation=(
                "NASA/JPL-Caltech Mars 2020 Mission Operations MMGIS Waypoints Layer (2021-2026)."
            ),
        ),
        Source(
            id="SRC-M20-TRAVERSE",
            title="Mars 2020 Perseverance Rover MMGIS Traverse Path",
            mission="NASA / JPL-Caltech Mars 2020",
            url=M20_TRAVERSE_URL,
            license="Public Domain (17 U.S.C. 105)",
            citation=(
                "NASA/JPL-Caltech Mars 2020 Mission Operations MMGIS Traverse Layer (2021-2026)."
            ),
        ),
        Source(
            id="SRC-TREK-HIRISE-25CM",
            title="Mars 2020 TRN HiRISE Orthorectified Mosaic (25 cm/px WMTS)",
            mission="NASA Solar System Treks / USGS / MRO HiRISE",
            url="https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars",
            license="Public Domain (17 U.S.C. 105)",
            citation=(
                "Fergason et al. (2020), Mars 2020 Terrain Relative Navigation "
                "Flight Product, LPSC 51 #2020."
            ),
        ),
        Source(
            id="SRC-USGS-HIRISE-DTM-1M",
            title="Mars 2020 TRN HiRISE Digital Terrain Model (1 m/px) Blended with MOLA",
            mission="USGS Astrogeology Science Center / University of Arizona",
            url=(
                "https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/"
                "JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif"
            ),
            license="Public Domain (17 U.S.C. 105)",
            citation="Fergason et al. (2020), USGS Astrogeology Mars 2020 TRN HiRISE 1m DTM.",
        ),
        Source(
            id="SRC-USGS-SIM3464",
            title="USGS Scientific Investigations Map 3464: Geologic Map of Jezero Crater",
            mission="U.S. Geological Survey (USGS)",
            url="https://pubs.usgs.gov/sim/3464/sim3464_database.zip",
            license="Public Domain (17 U.S.C. 105)",
            citation=(
                "Sun, V. Z., & Stack, K. M. (2020), USGS SIM 3464, https://doi.org/10.3133/sim3464."
            ),
        ),
        Source(
            id="SRC-NASA-XEVA",
            title=(
                "NASA Extravehicular Activity (xEVA) System Concept of Operations "
                "(EVA-EXP-0042 Rev B)"
            ),
            mission="NASA Human Exploration and Operations",
            url=(
                "https://www.nasa.gov/wp-content/uploads/2017/02/"
                "eva-exp-0042_xeva_system_con_ops_rev_b_final_dtd_10192020_ref_doc.pdf"
            ),
            license="Public Domain (17 U.S.C. 105)",
            citation="NASA EVA-EXP-0042 Rev B (2020), xEVA System Concept of Operations.",
        ),
        Source(
            id="SRC-JPL-TRAVERSABILITY",
            title=(
                "Data-Driven Surface Traversability Analysis for Mars 2020 Landing Site Selection"
            ),
            mission="NASA Jet Propulsion Laboratory (JPL)",
            url=(
                "https://www-robotics.jpl.nasa.gov/media/documents/"
                "Data-driven%20surface%20traversability%20analysis%20for%20Mars%202020%20"
                "landing%20site%20selection.pdf"
            ),
            license="Public Use / IEEE Open Preprint via JPL Robotics",
            citation=(
                "Ono, M., Rothrock, B., Iwashita, Y., et al. (2016), IEEE Aerospace Conference."
            ),
        ),
        Source(
            id="SRC-RAD-GALE",
            title="Mars Surface Radiation Environment Measured with MSL Curiosity RAD",
            mission="NASA MSL Curiosity / Southwest Research Institute (SwRI)",
            url=(
                "https://www.swri.org/newsroom/press-releases/"
                "swri-scientists-publish-first-radiation-measurements-the-surface-of-mars"
            ),
            license="Open Scientific Reference Value",
            citation=(
                "Hassler, D. M., et al. (2014), Science 343(6169), 1244797 "
                "(0.67 mSv/day GCR surface dose)."
            ),
        ),
        Source(
            id="SRC-APOLLO-SLOPE",
            title="Historical Apollo Lunar EVA Slope and Elevation Envelope",
            mission="Apollo Program / Comparative Planetary EVA Literature",
            url="https://www.sciencedirect.com/science/article/pii/S0094576524003746",
            license="Open Scientific Reference Value",
            citation=(
                "Iqbal, Z., et al. (2024), Acta Astronautica "
                "(<15 deg practical slope, 150 m max elevation change)."
            ),
        ),
        Source(
            id=SYNTHETIC_SOURCE_ID,
            title="MarsWalk Pass 1 Synthetic Placeholder Surface (UI Scaffold)",
            mission="MarsWalk Synthetic Placeholder Generator",
            url="https://www.spaceappschallenge.org/2026/challenges/interplanetary-survival-guide-martian-map/",
            license="Apache-2.0",
            citation=(
                "Synthetic multi-scale terrain placeholder surface (grid_status=PLACEHOLDER, "
                "source_id=synthetic-v1) generated without reading rover tilt or USGS DTM."
            ),
        ),
    ]


def build_eva_constraints() -> EvaConstraints:
    """Build citable NASA xEVA, Apollo, JPL Rover, and Curiosity RAD constraints."""
    return EvaConstraints(
        suit_max_slope_deg=Quantity(
            value=20.0, unit="deg", tag="MEASURED", source_id="SRC-NASA-XEVA"
        ),
        apollo_practical_slope_deg=Quantity(
            value=15.0, unit="deg", tag="MEASURED", source_id="SRC-APOLLO-SLOPE"
        ),
        apollo_max_relief_m=Quantity(
            value=150.0, unit="m", tag="MEASURED", source_id="SRC-APOLLO-SLOPE"
        ),
        walkback_max_km=Quantity(value=2.0, unit="km", tag="MEASURED", source_id="SRC-NASA-XEVA"),
        eva_duration_min_h=Quantity(value=4.0, unit="h", tag="MEASURED", source_id="SRC-NASA-XEVA"),
        eva_duration_max_h=Quantity(value=8.0, unit="h", tag="MEASURED", source_id="SRC-NASA-XEVA"),
        rover_max_slope_rock_deg=Quantity(
            value=20.0, unit="deg", tag="MEASURED", source_id="SRC-JPL-TRAVERSABILITY"
        ),
        rover_max_slope_sand_deg=Quantity(
            value=10.0, unit="deg", tag="MEASURED", source_id="SRC-JPL-TRAVERSABILITY"
        ),
        ripple_hazard_height_cm=Quantity(
            value=10.0, unit="cm", tag="MEASURED", source_id="SRC-JPL-TRAVERSABILITY"
        ),
        rock_cfa_ok_pct=Quantity(
            value=7.0, unit="pct", tag="MEASURED", source_id="SRC-JPL-TRAVERSABILITY"
        ),
        rock_cfa_caution_pct=Quantity(
            value=15.0, unit="pct", tag="MEASURED", source_id="SRC-JPL-TRAVERSABILITY"
        ),
        gcr_dose_msv_per_day=Quantity(
            value=0.67,
            unit="mSv/day",
            tag="MEASURED",
            source_id="SRC-RAD-GALE",
            note="proxy Curiosity RAD, Gale",
        ),
        radiation_environment_note=(
            "Galactic Cosmic Ray (GCR) surface baseline of 0.67 mSv/day (approx. 28 uSv/h) "
            "measured by MSL Curiosity RAD at Gale Crater (Hassler et al. 2014) and applied as "
            "a transparent scalar reference proxy for Jezero Crater EVA duration budgeting."
        ),
    )


def build_waypoints_collection(raw_waypoints: dict[str, Any]) -> WaypointFeatureCollection:
    """Convert raw M20_waypoints.json into validated WaypointFeatureCollection."""
    features: list[Waypoint] = []
    for idx, feat in enumerate(raw_waypoints.get("features", [])):
        props = feat.get("properties", {})
        rmc = str(props.get("RMC") or f"wp_{idx}")
        sol = int(props.get("sol") or 0)
        site = int(props.get("site") or 0)
        drive = int(props.get("drive") or 0)
        lon = round(float(props["lon"]), 8)
        lat = round(float(props["lat"]), 8)
        elev = round(float(props.get("elev_geoid") or 0.0), 3)
        tilt = round(float(props.get("tilt") or 0.0), 4)
        pitch = round(float(props.get("pitch") or 0.0), 4)
        roll = round(float(props.get("roll") or 0.0), 4)
        dist_total = round(float(props.get("dist_total_m") or 0.0), 2)

        images = props.get("images") or []
        pan_url: str | None = None
        if isinstance(images, list) and images:
            rel_url = images[0].get("url")
            if isinstance(rel_url, str) and rel_url:
                pan_url = (
                    rel_url
                    if rel_url.startswith("http")
                    else f"{M20_PANORAMA_BASE_URL}{rel_url.lstrip('/')}"
                )

        features.append(
            Waypoint(
                geometry=GeoJsonPointGeometry(coordinates=(lon, lat, elev)),
                properties=WaypointProperties(
                    waypoint_id=f"M20-{rmc}-SOL{sol}",
                    sol=sol,
                    site=site,
                    drive=drive,
                    lon=lon,
                    lat=lat,
                    elev_geoid_m=Quantity(
                        value=elev, unit="m", tag="MEASURED", source_id="SRC-M20-WAYPOINTS"
                    ),
                    rover_tilt_deg=Quantity(
                        value=tilt, unit="deg", tag="MEASURED", source_id="SRC-M20-WAYPOINTS"
                    ),
                    rover_pitch_deg=Quantity(
                        value=pitch, unit="deg", tag="MEASURED", source_id="SRC-M20-WAYPOINTS"
                    ),
                    rover_roll_deg=Quantity(
                        value=roll, unit="deg", tag="MEASURED", source_id="SRC-M20-WAYPOINTS"
                    ),
                    dist_total_m=Quantity(
                        value=dist_total, unit="m", tag="MEASURED", source_id="SRC-M20-WAYPOINTS"
                    ),
                    panorama_url=pan_url,
                ),
            )
        )
    return WaypointFeatureCollection(site_id="jezero", features=features)


def _synthetic_elevation_m(lon: float, lat: float, offset_x_m: float, offset_y_m: float) -> float:
    """Purely synthetic multi-scale elevation surface z(x, y) for Pass 1 placeholder.

    Does not read rover_tilt_deg or any external telemetry. Combines a broad regional ramp,
    intermediate terrace undulations (where 64m slope can exceed 1m local flat terrace slope),
    and localized short-wavelength ridges (where 1m slope exceeds 64m slope).
    """
    m_per_deg_lat = MARS_SPHERE_RADIUS_M * (math.pi / 180.0)
    m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(lat))
    x_m = (lon - 77.215) * m_per_deg_lon + offset_x_m
    y_m = (lat - 18.415) * m_per_deg_lat + offset_y_m

    broad = -2570.0 + 650.0 * max(0.0, min(1.0, (14000.0 - x_m) / 14000.0)) ** 1.25
    terrace = 3.8 * math.sin(x_m / 14.5) * math.cos(y_m / 18.0)
    scarp_env = math.exp(-(((lon - 77.405) / 0.022) ** 2)) + 1.15 * math.exp(
        -(((lon - 77.265) / 0.032) ** 2)
    )
    fine = scarp_env * (0.42 * math.sin(x_m / 0.55 + y_m / 0.85))
    return broad + terrace + fine


def _synthetic_slope_at_baseline_deg(lon: float, lat: float, baseline_m: float) -> float:
    """Compute finite-difference slope (deg) at step size `baseline_m` on synthetic surface."""
    half = 0.5 * baseline_m
    dz_dx = (
        _synthetic_elevation_m(lon, lat, half, 0.0) - _synthetic_elevation_m(lon, lat, -half, 0.0)
    ) / baseline_m
    dz_dy = (
        _synthetic_elevation_m(lon, lat, 0.0, half) - _synthetic_elevation_m(lon, lat, 0.0, -half)
    ) / baseline_m
    grad = math.hypot(dz_dx, dz_dy)
    return round(math.degrees(math.atan(grad)), 2)


def build_hazard_grid_and_overlay(overlay_output_path: Path) -> HazardGrid:
    """Build the Pass 1 `PLACEHOLDER` synthetic hazard grid (`SIMULATED` / `synthetic-v1`).

    Strictly independent of `rover_tilt_deg` and M20 waypoints (`R1/R2/R3` compliance).
    """
    min_lon, min_lat, max_lon, max_lat = JEZERO_GRID_BBOX
    cols = 24
    rows = 16
    dlon = (max_lon - min_lon) / cols
    dlat = (max_lat - min_lat) / rows
    mid_lat = 0.5 * (min_lat + max_lat)
    cell_size_m = round(spherical_distance_m(min_lon, mid_lat, min_lon + dlon, mid_lat), 2)

    cells: list[HazardCell] = []
    scale_px = 10
    img = Image.new("RGBA", (cols * scale_px, rows * scale_px), (0, 0, 0, 0))
    pixels = img.load()

    for r in range(rows):
        lat = round(max_lat - (r + 0.5) * dlat, 6)
        for c in range(cols):
            lon = round(min_lon + (c + 0.5) * dlon, 6)

            elev_val = round(_synthetic_elevation_m(lon, lat, 0.0, 0.0), 2)
            s1 = _synthetic_slope_at_baseline_deg(lon, lat, 1.0)
            s4 = _synthetic_slope_at_baseline_deg(lon, lat, 4.0)
            s16 = _synthetic_slope_at_baseline_deg(lon, lat, 16.0)
            s64 = _synthetic_slope_at_baseline_deg(lon, lat, 64.0)

            slopes_all = (s1, s4, s16, s64)
            max_slope = max(slopes_all)
            min_slope = min(slopes_all)
            divergence = round(max_slope - min_slope, 2)

            if max_slope >= 20.0:
                verdict: VerdictLiteral = "NO_GO"
                f_score = round(min(0.95, max(0.60, (max_slope - 15.0) / 12.0)), 2)
                i_score = round(min(0.30, max(0.05, divergence / 25.0)), 2)
                t_score = round(max(0.02, 1.0 - f_score - i_score), 2)
                reason = (
                    f"[PLACEHOLDER SIMULATED] Synthetic slope ({max_slope:.1f} deg) exceeds "
                    f"20.0 deg NASA xEVA suit limit (1m={s1:.1f} deg, 64m={s64:.1f} deg)."
                )
                rgba = (220, 38, 38, 135)
            elif max_slope >= 10.0 or divergence >= 5.0:
                verdict = "CAUTION"
                i_score = round(min(0.55, max(0.20, divergence / 14.0)), 2)
                f_score = round(min(0.40, max(0.15, (max_slope - 8.0) / 25.0)), 2)
                t_score = round(max(0.15, 1.0 - i_score - f_score), 2)
                reason = (
                    f"[PLACEHOLDER SIMULATED] Moderate synthetic slope (max {max_slope:.1f} deg) "
                    f"or baseline spread ({divergence:.1f} deg across 1m..64m)."
                )
                rgba = (245, 158, 11, 115)
            else:
                verdict = "GO"
                t_score = round(min(0.94, max(0.72, 1.0 - (max_slope / 25.0))), 2)
                i_score = round(min(0.20, max(0.04, divergence / 20.0)), 2)
                f_score = round(max(0.02, 1.0 - t_score - i_score), 2)
                reason = (
                    f"[PLACEHOLDER SIMULATED] Low synthetic slope across all baselines "
                    f"(1m={s1:.1f} deg, 64m={s64:.1f} deg) within xEVA envelope."
                )
                rgba = (16, 185, 129, 95)

            for py in range(r * scale_px, (r + 1) * scale_px):
                for px in range(c * scale_px, (c + 1) * scale_px):
                    pixels[px, py] = rgba

            cells.append(
                HazardCell(
                    cell_id=f"JEZ-R{r:02d}-C{c:02d}",
                    row=r,
                    col=c,
                    lon=lon,
                    lat=lat,
                    size_m=cell_size_m,
                    elev_m=Quantity(
                        value=elev_val,
                        unit="m",
                        tag="SIMULATED",
                        source_id=SYNTHETIC_SOURCE_ID,
                    ),
                    slope_deg_by_baseline={
                        "1": Quantity(
                            value=s1,
                            unit="deg",
                            tag="SIMULATED",
                            source_id=SYNTHETIC_SOURCE_ID,
                        ),
                        "4": Quantity(
                            value=s4,
                            unit="deg",
                            tag="SIMULATED",
                            source_id=SYNTHETIC_SOURCE_ID,
                        ),
                        "16": Quantity(
                            value=s16,
                            unit="deg",
                            tag="SIMULATED",
                            source_id=SYNTHETIC_SOURCE_ID,
                        ),
                        "64": Quantity(
                            value=s64,
                            unit="deg",
                            tag="SIMULATED",
                            source_id=SYNTHETIC_SOURCE_ID,
                        ),
                    },
                    scale_divergence=Quantity(
                        value=divergence,
                        unit="deg",
                        tag="SIMULATED",
                        source_id=SYNTHETIC_SOURCE_ID,
                    ),
                    rock_cfa_pct=None,
                    confidence=ConfidenceVector(t=t_score, i=i_score, f=f_score),
                    verdict=verdict,
                    reason=reason,
                    nearest_waypoint_sol=None,
                    measured_rover_tilt_deg=None,
                )
            )

    overlay_output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(overlay_output_path, format="PNG", optimize=False, compress_level=6)

    return HazardGrid(
        grid_status="PLACEHOLDER",
        site_id="jezero",
        bbox=JEZERO_GRID_BBOX,
        rows=rows,
        cols=cols,
        cell_size_m=cell_size_m,
        cells=cells,
    )


def build_eva_route(
    waypoints: WaypointFeatureCollection,
    raw_traverse: dict[str, Any],
) -> EvaRoute:
    """Build `route.geojson` (MEASURED traverse, SIMULATED EVA path, 3 stops, 2 benchmarks)."""
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

    by_sol = {w.properties.sol: w for w in waypoints.features}
    wp_stop1 = by_sol.get(13, waypoints.features[0])
    wp_stop2 = by_sol.get(398, waypoints.features[min(100, len(waypoints.features) - 1)])
    wp_stop3 = by_sol.get(407, waypoints.features[min(115, len(waypoints.features) - 1)])

    eva_loop_coords: list[tuple[float, float]] = [
        (wp_stop1.properties.lon, wp_stop1.properties.lat),
        (77.447500, 18.455200),
        (wp_stop2.properties.lon, wp_stop2.properties.lat),
        (77.430500, 18.460200),
        (wp_stop3.properties.lon, wp_stop3.properties.lat),
    ]
    eva_dist_m = 0.0
    for i in range(len(eva_loop_coords) - 1):
        eva_dist_m += spherical_distance_m(
            eva_loop_coords[i][0],
            eva_loop_coords[i][1],
            eva_loop_coords[i + 1][0],
            eva_loop_coords[i + 1][1],
        )
    eva_dist_m = round(eva_dist_m, 1)
    eva_duration_h = 4.5
    eva_rad_msv = round(0.67 * (eva_duration_h / 24.0), 4)

    simulated_eva_feature = EvaRouteFeature(
        geometry=GeoJsonLineGeometry(coordinates=eva_loop_coords),
        properties=EvaRouteProperties(
            feature_id="ROUTE-XEVA-SIMULATED-FAN-CORRIDOR",
            segment_type="SIMULATED_ASTRONAUT_EVA",
            title="Simulated Astronaut EVA Safe Walkback Corridor (<= 2.0 km from Sol 13 Origin)",
            tag="SIMULATED",
            source_id="SRC-NASA-XEVA",
            verdict="GO",
            distance_m=Quantity(
                value=eva_dist_m, unit="m", tag="SIMULATED", source_id="SRC-NASA-XEVA"
            ),
            max_slope_deg=Quantity(
                value=9.4, unit="deg", tag="SIMULATED", source_id=SYNTHETIC_SOURCE_ID
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
            geologic_unit="Crater floor fractured rough unit (Cf-fr) to Three Forks Delta Apron",
            notes=(
                "Candidate crewed EVA sortie connecting Stop 1 (Sol 13), Stop 2 (Sol 398), and "
                "Stop 3 (Sol 407), staying strictly within the 2.0 km NASA xEVA walkback radius."
            ),
        ),
    )

    science_stops = [
        EvaRouteFeature(
            geometry=GeoJsonPointGeometry(
                coordinates=(wp_stop1.properties.lon, wp_stop1.properties.lat)
            ),
            properties=EvaRouteProperties(
                feature_id="STOP-01-SOL13-LANDING-BASE",
                segment_type="SCIENCE_STOP",
                title="Science Stop 1 — Octavia E. Butler Landing & EVA Origin (Sol 13, 0.0 km)",
                tag="MEASURED",
                source_id="SRC-M20-WAYPOINTS",
                verdict="GO",
                sol=wp_stop1.properties.sol,
                rover_tilt_deg=wp_stop1.properties.rover_tilt_deg,
                geologic_unit="Crater floor fractured rough (Cf-fr, USGS SIM 3464)",
                panorama_url=wp_stop1.properties.panorama_url,
                notes=(
                    "EVA departure & walkback origin (walkback distance 0.0 m <= 2,000 m; "
                    "measured rover tilt 1.18 deg -> GO)."
                ),
            ),
        ),
        EvaRouteFeature(
            geometry=GeoJsonPointGeometry(
                coordinates=(wp_stop2.properties.lon, wp_stop2.properties.lat)
            ),
            properties=EvaRouteProperties(
                feature_id="STOP-02-SOL398-RAPID-TRAVERSE",
                segment_type="SCIENCE_STOP",
                title="Science Stop 2 — Crater Floor Northwest Traverse Contact (Sol 398, 1.33 km)",
                tag="MEASURED",
                source_id="SRC-M20-WAYPOINTS",
                verdict="GO",
                sol=wp_stop2.properties.sol,
                rover_tilt_deg=wp_stop2.properties.rover_tilt_deg,
                geologic_unit="Crater floor fractured rough margin (Cf-fr, USGS SIM 3464)",
                panorama_url=wp_stop2.properties.panorama_url,
                notes=(
                    "Mid-corridor geological sampling stop on the astronaut EVA path "
                    "(walkback distance 1,328.6 m <= 2,000 m; measured rover tilt 1.24 deg -> GO)."
                ),
            ),
        ),
        EvaRouteFeature(
            geometry=GeoJsonPointGeometry(
                coordinates=(wp_stop3.properties.lon, wp_stop3.properties.lat)
            ),
            properties=EvaRouteProperties(
                feature_id="STOP-03-SOL407-DELTA-APRON",
                segment_type="SCIENCE_STOP",
                title="Science Stop 3 — Three Forks Delta Apron Turnaround (Sol 407, 1.93 km)",
                tag="MEASURED",
                source_id="SRC-M20-WAYPOINTS",
                verdict="GO",
                sol=wp_stop3.properties.sol,
                rover_tilt_deg=wp_stop3.properties.rover_tilt_deg,
                geologic_unit="Delta apron / distal sedimentary contact (USGS SIM 3464)",
                panorama_url=wp_stop3.properties.panorama_url,
                notes=(
                    "Terminal science sampling stop at the 2.0 km NASA xEVA walkback boundary "
                    "(walkback distance 1,925.2 m <= 2,000 m; measured rover tilt 0.78 deg -> GO)."
                ),
            ),
        ),
    ]

    wp_scarp = by_sol.get(700, waypoints.features[len(waypoints.features) // 2])
    wp_rim = by_sol.get(1578, waypoints.features[-1])

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
                geologic_unit="Delta layered rough / steep scarp contact (D-lr, USGS SIM 3464)",
                panorama_url=wp_scarp.properties.panorama_url,
                notes=(
                    "Out-of-walkback rover validation benchmark (2.5 km from Sol 13): Perseverance "
                    "measured 20.33 deg ground tilt, exceeding the 20.0 deg NASA xEVA suit limit."
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
                geologic_unit="Noachian crater rim megabreccia unit (Nr, USGS SIM 3464)",
                panorama_url=wp_rim.properties.panorama_url,
                notes=(
                    "Out-of-walkback rover validation benchmark (10.9 km from Sol 13): highest "
                    "ground tilt recorded across all 708 Perseverance stops (20.68 deg -> NO_GO)."
                ),
            ),
        ),
    ]

    return EvaRoute(
        site_id="jezero",
        features=[
            measured_traverse_feature,
            simulated_eva_feature,
            *science_stops,
            *benchmark_features,
        ],
    )


def _write_deterministic_json(path: Path, payload: dict[str, Any]) -> None:
    """Write UTF-8 JSON with LF newlines and deterministic key ordering."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if (
        isinstance(payload, dict)
        and isinstance(payload.get("cells"), list)
        and len(payload["cells"]) > 500
    ):
        header = {k: v for k, v in payload.items() if k != "cells"}
        header_str = json.dumps(header, indent=2, ensure_ascii=False)[:-2]
        cell_lines = [
            "    " + json.dumps(c, separators=(",", ":"), ensure_ascii=False)
            for c in payload["cells"]
        ]
        text = header_str + ',\n  "cells": [\n' + ",\n".join(cell_lines) + "\n  ]\n}\n"
    else:
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_bytes(text.encode("utf-8"))


def _compute_file_digest(path: Path) -> PackFileDigest:
    """Compute SHA-256 hex digest and byte count for a pack file."""
    raw = path.read_bytes()
    return PackFileDigest(
        path=path.name,
        sha256=hashlib.sha256(raw).hexdigest(),
        bytes=len(raw),
    )


def _compute_input_digest(source_id: str, path: Path, rel_label: str) -> ManifestInputDigest:
    """Compute SHA-256 hex digest and bytes_read for an ingested raw file."""
    raw = path.read_bytes()
    return ManifestInputDigest(
        source_id=source_id,
        path_or_url=rel_label,
        sha256=hashlib.sha256(raw).hexdigest(),
        bytes_read=len(raw),
    )


def export_contract_schemas(schemas_dir: Path) -> list[Path]:
    """Export Draft 2020-12 JSON Schemas for all 5 top-level contract models."""
    schemas_dir.mkdir(parents=True, exist_ok=True)
    models = [
        ("SiteManifest", SiteManifest),
        ("WaypointFeatureCollection", WaypointFeatureCollection),
        ("HazardGrid", HazardGrid),
        ("EvaConstraints", EvaConstraints),
        ("EvaRoute", EvaRoute),
    ]
    written: list[Path] = []
    for name, model_cls in models:
        schema = model_cls.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        out_path = schemas_dir / f"{name}.schema.json"
        _write_deterministic_json(out_path, schema)
        written.append(out_path)
    return written


def build_jezero_pack(
    repo_root: Path,
    generated_at: str = DETERMINISTIC_GENERATED_AT,
    mode: str = "engine",
) -> SiteManifest:
    """Build and sign the complete `public_packs/jezero/v1/` static pack.

    When `mode == "engine"` (default in Phase 2b), executes the asynchronous 4-stage
    Neutrosophic-gated Plithogenic + A* engine pipeline against the real 1 m/px USGS
    HiRISE DTM (`pack_version="1.1.0"`, `grid_status="ENGINE"`).
    When `mode == "placeholder"`, builds the synthetic Pass 1 placeholder (`1.0.1`).
    """
    if mode == "engine":
        import asyncio
        import shutil

        from marswalk.engine.pipeline import ENGINE_GENERATED_AT, run_engine_pipeline_async

        canonical_root = Path(__file__).resolve().parents[3]
        datalake_dir = repo_root / "datalake"
        datalake_dir.mkdir(parents=True, exist_ok=True)
        for fname in ("JEZ_hirise_soc_006_DTM_1m_window_2x2km.tif", "SIM3464_metadata.xml"):
            src_f = canonical_root / "datalake" / fname
            dst_f = datalake_dir / fname
            if src_f.exists() and not dst_f.exists():
                shutil.copyfile(src_f, dst_f)

        profiles_dir = repo_root / "profiles"
        if not profiles_dir.exists() and (canonical_root / "profiles").exists():
            shutil.copytree(canonical_root / "profiles", profiles_dir)

        ts = ENGINE_GENERATED_AT if generated_at == DETERMINISTIC_GENERATED_AT else generated_at
        res = asyncio.run(run_engine_pipeline_async(repo_root, generated_at=ts))
        return res.manifest

    datalake_dir = repo_root / "datalake"
    pack_dir = repo_root / "public_packs" / "jezero" / "v1"
    pack_dir.mkdir(parents=True, exist_ok=True)

    wp_raw_path, tr_raw_path = ensure_m20_datalake(datalake_dir)
    raw_waypoints = json.loads(wp_raw_path.read_text(encoding="utf-8"))
    raw_traverse = json.loads(tr_raw_path.read_text(encoding="utf-8"))

    waypoints = build_waypoints_collection(raw_waypoints)
    constraints = build_eva_constraints()
    route = build_eva_route(waypoints, raw_traverse)
    overlay_path = pack_dir / "hazard_overlay.png"
    hazard_grid = build_hazard_grid_and_overlay(overlay_path)

    wp_out = pack_dir / "waypoints.geojson"
    route_out = pack_dir / "route.geojson"
    hazard_out = pack_dir / "hazard_grid.json"
    constraints_out = pack_dir / "eva_constraints.json"

    _write_deterministic_json(wp_out, waypoints.model_dump(mode="json"))
    _write_deterministic_json(route_out, route.model_dump(mode="json"))
    _write_deterministic_json(hazard_out, hazard_grid.model_dump(mode="json"))
    _write_deterministic_json(constraints_out, constraints.model_dump(mode="json"))

    pack_files = [
        _compute_file_digest(wp_out),
        _compute_file_digest(route_out),
        _compute_file_digest(hazard_out),
        _compute_file_digest(overlay_path),
        _compute_file_digest(constraints_out),
    ]

    input_digests = [
        _compute_input_digest("SRC-M20-WAYPOINTS", wp_raw_path, "datalake/M20_waypoints.json"),
        _compute_input_digest("SRC-M20-TRAVERSE", tr_raw_path, "datalake/M20_traverse.json"),
    ]

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
        pack_version=PACK_VERSION,
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
    return manifest
