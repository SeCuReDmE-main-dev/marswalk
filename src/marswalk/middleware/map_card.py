"""Deterministic standalone SVG EVA Survival Map Card generator (`generate-map-card`).

I read the cryptographically verified site pack (`public_packs/<site>/v1/`) via
`load_and_verify_pack` and emit a self-contained SVG survival map sheet into
`docs/assets/<site>_eva_survival_map.svg` (or an explicit `--output` path)
without modifying `public_packs/<site>/v1/manifest.json` or `frontend/`.
"""

from __future__ import annotations

import base64
import hashlib
import html
import math
from collections import Counter
from pathlib import Path
from statistics import median

from marswalk.contracts.models import (
    MARS_SPHERE_RADIUS_M,
    BaselineKey,
    EvaRouteFeature,
    GeoJsonLineGeometry,
    GeoJsonPointGeometry,
)
from marswalk.middleware.build_pack import spherical_distance_m
from marswalk.middleware.pack_loader import (
    LoadedSitePack,
    load_and_verify_pack,
    resolve_pack_relative_path,
)


def _esc(value: object) -> str:
    """Escape text or attribute values for strict XML/SVG compliance."""
    return html.escape(str(value), quote=True)


def _verdict_color(verdict: str) -> str:
    if verdict == "GO":
        return "#4fb87a"
    if verdict == "CAUTION":
        return "#edaa4d"
    return "#df6658"


def _tag_color(tag: str) -> str:
    if tag == "MEASURED":
        return "#4fb87a"
    if tag == "DERIVED":
        return "#4fd7eb"
    if tag == "SIMULATED":
        return "#edaa4d"
    return "#93a8b8"


def _find_route_feature(pack: LoadedSitePack, segment_type: str) -> EvaRouteFeature | None:
    for feat in pack.route.features:
        if feat.properties.segment_type == segment_type:
            return feat
    return None


def _render_badge(x: float, y: float, text: str, bg: str, fg: str = "#0b1822") -> str:
    width = max(56.0, round(len(text) * 6.4 + 14.0, 1))
    return (
        f'<g transform="translate({x:.1f},{y:.1f})">'
        f'<rect x="0" y="0" width="{width:.1f}" height="17" rx="4" fill="{_esc(bg)}" />'
        f'<text x="{width / 2.0:.1f}" y="12.2" text-anchor="middle" '
        f'font-size="9.5" font-weight="700" fill="{_esc(fg)}">{_esc(text)}</text>'
        "</g>"
    )


def generate_survival_map_svg(
    repo_root: Path,
    site_id: str = "jezero",
    output_path: Path | None = None,
) -> Path:
    """Generate a deterministic, self-contained SVG EVA Survival Map Card from a verified pack."""
    pack = load_and_verify_pack(repo_root, site_id=site_id)
    manifest_bytes = (pack.pack_dir / "manifest.json").read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

    overlay_path = resolve_pack_relative_path(pack.pack_dir, pack.hazards.overlay_file)
    overlay_b64 = base64.b64encode(overlay_path.read_bytes()).decode("ascii")

    min_lon, min_lat, max_lon, max_lat = pack.hazards.bbox
    mid_lat_rad = math.radians(0.5 * (min_lat + max_lat))
    cos_lat = math.cos(mid_lat_rad)
    dlon_deg = max_lon - min_lon
    dlat_deg = max_lat - min_lat
    ew_span_m = math.radians(dlon_deg) * MARS_SPHERE_RADIUS_M * cos_lat
    ns_span_m = math.radians(dlat_deg) * MARS_SPHERE_RADIUS_M

    map_x = 56.0
    map_y = 112.0
    map_h = 612.0
    map_w = round(map_h * (ew_span_m / ns_span_m), 2)

    def proj_x(lon: float) -> float:
        return map_x + ((lon - min_lon) / dlon_deg) * map_w

    def proj_y(lat: float) -> float:
        return map_y + ((max_lat - lat) / dlat_deg) * map_h

    def inside_bbox(lon: float, lat: float) -> bool:
        return (min_lon <= lon <= max_lon) and (min_lat <= lat <= max_lat)

    # Aggregate verified grid telemetry dynamically from pack.hazards.cells
    cells = pack.hazards.cells
    verdict_counts = Counter(c.verdict for c in cells)
    rf_counts = Counter(c.rf_comms_verdict for c in cells if c.rf_comms_verdict is not None)
    rf_total = sum(rf_counts.values()) or len(cells)
    rf_nogo = rf_counts.get("NO_GO", 0)
    rf_nogo_pct = round(100.0 * rf_nogo / rf_total)

    baseline_stats: dict[BaselineKey, tuple[float, float]] = {}
    for bl in ("64", "16", "4", "1"):
        vals = [c.slope_deg_by_baseline[bl].value for c in cells]
        baseline_stats[bl] = (float(median(vals)), float(max(vals)))

    obstacle_features = pack.obstacles.features if pack.obstacles is not None else []
    scarp_count = sum(1 for f in obstacle_features if f.properties.obstacle_type == "scarp")
    rock_count = sum(
        1 for f in obstacle_features if f.properties.obstacle_type == "large_rock_formation"
    )

    sim_route = _find_route_feature(pack, "SIMULATED_ASTRONAUT_EVA")
    obs_route = _find_route_feature(pack, "DERIVED_OBSTACLE_AWARE_EVA")
    rov_route = _find_route_feature(pack, "MEASURED_ROVER_TRAVERSE")
    stops = sorted(
        (f for f in pack.route.features if f.properties.segment_type == "SCIENCE_STOP"),
        key=lambda f: f.properties.sol or 0,
    )
    benchmarks = sorted(
        (f for f in pack.route.features if f.properties.segment_type == "BENCHMARK"),
        key=lambda f: f.properties.sol or 0,
    )

    suit_max_slope_deg = pack.constraints.suit_max_slope_deg.value
    walkback_max_m = pack.constraints.walkback_max_km.value * 1000.0
    total_waypoints = len(pack.waypoints.features)

    if stops and isinstance(stops[0].geometry, GeoJsonPointGeometry):
        origin_lon = float(stops[0].geometry.coordinates[0])
        origin_lat = float(stops[0].geometry.coordinates[1])
    elif sim_route is not None and isinstance(sim_route.geometry, GeoJsonLineGeometry):
        origin_lon = float(sim_route.geometry.coordinates[0][0])
        origin_lat = float(sim_route.geometry.coordinates[0][1])
    else:
        origin_lon, origin_lat = min_lon, min_lat

    def _max_walkback_from_origin(feat: EvaRouteFeature | None) -> float:
        if feat is None or not isinstance(feat.geometry, GeoJsonLineGeometry):
            return 0.0
        return max(
            spherical_distance_m(origin_lon, origin_lat, float(lon), float(lat))
            for lon, lat in feat.geometry.coordinates
        )

    def _nearest_cell_64m_slope_deg(lon: float, lat: float) -> float:
        nearest = min(
            cells,
            key=lambda cell: spherical_distance_m(lon, lat, cell.lon, cell.lat),
        )
        return nearest.slope_deg_by_baseline["64"].value

    unavailable_layers = sorted(
        name
        for name, meta in (pack.hazards.external_layers_status or {}).items()
        if meta.get("status") == "UNAVAILABLE"
    )
    unavailable_str = ", ".join(unavailable_layers) if unavailable_layers else "THEMIS, CRISM, MEDA"

    parts: list[str] = []
    a = parts.append

    a('<?xml version="1.0" encoding="UTF-8"?>')
    a(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 1200 820" width="1200" height="820" '
        'role="img" aria-labelledby="marswalk-map-title marswalk-map-desc" '
        "font-family=\"Bahnschrift, 'Segoe UI', Arial, sans-serif\">"
    )
    a(
        '<title id="marswalk-map-title">'
        "MarsWalk Jezero Western Delta EVA Survival Map Card (v1.1.0)"
        "</title>"
    )
    a(
        '<desc id="marswalk-map-desc">'
        "Georeferenced Mars EVA hazard and route card derived from HiRISE 1 m/px DTM, "
        "Mars 2020 Perseverance waypoints, NASA xEVA slope/walkback rules, and Curiosity RAD proxy."
        "</desc>"
    )
    a("<defs>")
    a(
        f'<clipPath id="jezero-map-clip">'
        f'<rect x="{map_x:.2f}" y="{map_y:.2f}" width="{map_w:.2f}" height="{map_h:.2f}" rx="4" />'
        "</clipPath>"
    )
    a("</defs>")

    # Root canvas
    a('<rect x="0" y="0" width="1200" height="820" fill="#102331" />')

    # Header bar
    a(
        '<rect x="20" y="16" width="1160" height="56" rx="8" '
        'fill="#162d3e" stroke="#2b4b63" stroke-width="1.2" />'
    )
    a(
        '<text x="36" y="39" font-size="16.5" font-weight="700" '
        'fill="#f2f7fb" letter-spacing="0.4">'
        "MARSWALK — JEZERO WESTERN DELTA EVA SURVIVAL MAP CARD"
        "</text>"
    )
    a(
        f'<text x="36" y="58" font-size="10.8" fill="#9fc0d6">'
        f"CRS: {_esc(pack.manifest.crs.name)} (R = {pack.manifest.crs.sphere_radius_m:,.0f} m) "
        f"| Window: {ew_span_m / 1000.0:.2f} km E-W x {ns_span_m / 1000.0:.2f} km N-S "
        f"| Contract v{_esc(pack.manifest.contract_version)}"
        f" · Pack v{_esc(pack.manifest.pack_version)}"
        "</text>"
    )
    a(_render_badge(898, 25, "MEASURED", "#4fb87a"))
    a(_render_badge(982, 25, "DERIVED", "#4fd7eb"))
    a(_render_badge(1062, 25, "SIMULATED", "#edaa4d"))
    a(
        '<text x="1164" y="60" text-anchor="end" font-size="9.5" fill="#9fc0d6">'
        "Prototype Assessment — Non-Flight"
        "</text>"
    )

    # Left Map Card Frame
    a(
        '<rect x="20" y="82" width="644" height="722" rx="8" '
        'fill="#162d3e" stroke="#2b4b63" stroke-width="1.2" />'
    )
    a(
        '<text x="36" y="102" font-size="12" font-weight="700" fill="#e8f2f8">'
        "GEOREFERENCED MULTI-SCALE HAZARD GRID (40x40 · 48.7 m) &amp; OBSTACLE-AWARE EVA CORRIDORS"
        "</text>"
    )

    # Clipped map viewport
    a('<g clip-path="url(#jezero-map-clip)">')
    a(
        f'<rect x="{map_x:.2f}" y="{map_y:.2f}" width="{map_w:.2f}" height="{map_h:.2f}" '
        'fill="#0b1822" />'
    )
    a(
        f'<image href="data:image/png;base64,{overlay_b64}" '
        f'x="{map_x:.2f}" y="{map_y:.2f}" width="{map_w:.2f}" height="{map_h:.2f}" '
        'preserveAspectRatio="none" opacity="0.82" />'
    )

    # Coordinate graticules
    lon_ticks = [77.38, 77.39, 77.40, 77.41]
    lat_ticks = [18.45, 18.46, 18.47, 18.48]
    a('<g stroke="#d8ecf8" stroke-opacity="0.18" stroke-width="0.8" stroke-dasharray="3 3">')
    for lon_t in lon_ticks:
        if min_lon <= lon_t <= max_lon:
            px = proj_x(lon_t)
            a(f'<line x1="{px:.2f}" y1="{map_y:.2f}" x2="{px:.2f}" y2="{map_y + map_h:.2f}" />')
    for lat_t in lat_ticks:
        if min_lat <= lat_t <= max_lat:
            py = proj_y(lat_t)
            a(f'<line x1="{map_x:.2f}" y1="{py:.2f}" x2="{map_x + map_w:.2f}" y2="{py:.2f}" />')
    a("</g>")

    # Obstacles polygons (82 features: scarp + large_rock_formation)
    a('<g id="obstacles-layer">')
    for obs_feat in obstacle_features:
        otype = obs_feat.properties.obstacle_type
        oid = obs_feat.properties.obstacle_id
        relief = obs_feat.properties.internal_relief_m
        fill_c = "#df6658" if otype == "scarp" else "#edaa4d"
        stroke_c = "#ff8577" if otype == "scarp" else "#ffd27d"
        ring = obs_feat.geometry.coordinates[0]
        pts = " ".join(f"{proj_x(lon):.2f},{proj_y(lat):.2f}" for lon, lat in ring)
        a(
            f'<polygon id="{_esc(oid)}" data-obstacle-type="{_esc(otype)}" '
            f'data-relief-m="{relief:.2f}" points="{pts}" '
            f'fill="{fill_c}" fill-opacity="0.34" stroke="{stroke_c}" stroke-width="0.9" />'
        )
    a("</g>")

    # Measured Perseverance traverse
    if rov_route is not None and isinstance(rov_route.geometry, GeoJsonLineGeometry):
        pts = " ".join(
            f"{proj_x(lon):.2f},{proj_y(lat):.2f}" for lon, lat in rov_route.geometry.coordinates
        )
        a(
            f'<g id="{_esc(rov_route.properties.feature_id)}">'
            f'<polyline points="{pts}" fill="none" stroke="#09131c" '
            'stroke-width="3.2" opacity="0.7" />'
            f'<polyline points="{pts}" fill="none" stroke="#dceaf5" stroke-width="1.6" '
            'stroke-dasharray="4 3" opacity="0.9" />'
            "</g>"
        )

    # Simulated 2-Agent A* EVA corridor
    if sim_route is not None and isinstance(sim_route.geometry, GeoJsonLineGeometry):
        pts = " ".join(
            f"{proj_x(lon):.2f},{proj_y(lat):.2f}" for lon, lat in sim_route.geometry.coordinates
        )
        a(
            f'<g id="{_esc(sim_route.properties.feature_id)}">'
            f'<polyline points="{pts}" fill="none" stroke="#08131c" stroke-width="5.2" '
            'stroke-linecap="round" stroke-linejoin="round" />'
            f'<polyline points="{pts}" fill="none" stroke="#4fd7eb" stroke-width="3.0" '
            'stroke-linecap="round" stroke-linejoin="round" />'
            "</g>"
        )

    # Derived 10 m Obstacle-Aware EVA corridor
    if obs_route is not None and isinstance(obs_route.geometry, GeoJsonLineGeometry):
        pts = " ".join(
            f"{proj_x(lon):.2f},{proj_y(lat):.2f}" for lon, lat in obs_route.geometry.coordinates
        )
        a(
            f'<g id="{_esc(obs_route.properties.feature_id)}">'
            f'<polyline points="{pts}" fill="none" stroke="#08131c" stroke-width="4.6" '
            'stroke-linecap="round" stroke-linejoin="round" />'
            f'<polyline points="{pts}" fill="none" stroke="#ff9e44" stroke-width="2.6" '
            'stroke-dasharray="7 4" stroke-linecap="round" stroke-linejoin="round" />'
            "</g>"
        )

    a("</g>")  # end clipped map layer

    # Outer map border & coordinate tick labels
    a(
        f'<rect x="{map_x:.2f}" y="{map_y:.2f}" width="{map_w:.2f}" height="{map_h:.2f}" '
        'rx="4" fill="none" stroke="#4c7391" stroke-width="1.4" />'
    )
    for lon_t in lon_ticks:
        if min_lon <= lon_t <= max_lon:
            px = proj_x(lon_t)
            a(
                f'<text x="{px:.2f}" y="{map_y + map_h + 13:.2f}" text-anchor="middle" '
                f'font-size="9" fill="#9fc0d6">{lon_t:.2f}°E</text>'
            )
    for lat_t in lat_ticks:
        if min_lat <= lat_t <= max_lat:
            py = proj_y(lat_t)
            a(
                f'<text x="{map_x - 5:.2f}" y="{py + 3:.2f}" text-anchor="end" '
                f'font-size="9" fill="#9fc0d6">{lat_t:.2f}°N</text>'
            )

    # Science stop markers & callouts
    a('<g id="science-stops-layer">')
    for idx, stop in enumerate(stops, start=1):
        if not isinstance(stop.geometry, GeoJsonPointGeometry):
            continue
        lon = float(stop.geometry.coordinates[0])
        lat = float(stop.geometry.coordinates[1])
        sol = stop.properties.sol or 0
        tilt = stop.properties.rover_tilt_deg.value if stop.properties.rover_tilt_deg else 0.0
        sx, sy = proj_x(lon), proj_y(lat)
        near_east_edge = sx > (map_x + 0.72 * map_w)
        label_x = sx - 11.0 if near_east_edge else sx + 11.0
        anchor = "end" if near_east_edge else "start"
        label_y = sy + (14.0 if sol == 413 else -8.0)
        label_txt = f"Stop {idx} · Sol {sol} ({tilt:.2f}° {stop.properties.verdict})"
        box_w = len(label_txt) * 5.6 + 10.0
        box_x = (label_x - box_w + 4.0) if near_east_edge else (label_x - 4.0)
        a(f'<g id="{_esc(stop.properties.feature_id)}">')
        a(
            f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="6.2" '
            'fill="#4fb87a" stroke="#ffffff" stroke-width="1.8" />'
        )
        a(f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="2.2" fill="#0b1822" />')
        a(
            f'<rect x="{box_x:.2f}" y="{label_y - 11.0:.2f}" width="{box_w:.2f}" height="15" '
            'rx="3" fill="#0b1822" fill-opacity="0.88" stroke="#4fb87a" stroke-width="0.9" />'
        )
        a(
            f'<text x="{label_x:.2f}" y="{label_y:.2f}" text-anchor="{anchor}" '
            f'font-size="9.5" font-weight="700" fill="#e9f9ef">{_esc(label_txt)}</text>'
        )
        a("</g>")
    a("</g>")

    # Benchmark markers (in-window Sol 700 + directional western rim callout for Sol 1578)
    a('<g id="benchmarks-layer">')
    for bm in benchmarks:
        if not isinstance(bm.geometry, GeoJsonPointGeometry):
            continue
        lon = float(bm.geometry.coordinates[0])
        lat = float(bm.geometry.coordinates[1])
        sol = bm.properties.sol or 0
        tilt = bm.properties.rover_tilt_deg.value if bm.properties.rover_tilt_deg else 0.0
        a(f'<g id="{_esc(bm.properties.feature_id)}">')
        if inside_bbox(lon, lat):
            bx, by = proj_x(lon), proj_y(lat)
            pts_d = (
                f"{bx:.2f},{by - 7.0:.2f} {bx + 7.0:.2f},{by:.2f} "
                f"{bx:.2f},{by + 7.0:.2f} {bx - 7.0:.2f},{by:.2f}"
            )
            a(f'<polygon points="{pts_d}" fill="#df6658" stroke="#ffffff" stroke-width="1.5" />')
            lbl = f"Benchmark · Sol {sol} ({tilt:.2f}° NO_GO)"
            bw = len(lbl) * 5.6 + 10.0
            lx = bx - 11.0
            a(
                f'<rect x="{lx - bw + 4.0:.2f}" y="{by - 19.0:.2f}" width="{bw:.2f}" height="15" '
                'rx="3" fill="#0b1822" fill-opacity="0.9" stroke="#df6658" stroke-width="0.9" />'
            )
            a(
                f'<text x="{lx:.2f}" y="{by - 8.0:.2f}" text-anchor="end" '
                f'font-size="9.5" font-weight="700" fill="#ffd7d2">{_esc(lbl)}</text>'
            )
        else:
            dist_w_km = math.radians(min_lon - lon) * MARS_SPHERE_RADIUS_M * cos_lat / 1000.0
            by = min(max(proj_y(lat), map_y + 28.0), map_y + map_h - 28.0)
            bx = map_x + 8.0
            lbl = (
                f"◄ Rim Benchmark · Sol {sol} "
                f"({lon:.3f}°E, ~{dist_w_km:.1f} km W · {tilt:.2f}° NO_GO)"
            )
            bw = len(lbl) * 5.35 + 12.0
            a(
                f'<rect x="{bx:.2f}" y="{by - 12.0:.2f}" width="{bw:.2f}" height="17" '
                'rx="3" fill="#0b1822" fill-opacity="0.92" stroke="#df6658" stroke-width="1.0" />'
            )
            a(
                f'<text x="{bx + 6.0:.2f}" y="{by:.2f}" font-size="9.3" font-weight="700" '
                f'fill="#ffd7d2">{_esc(lbl)}</text>'
            )
        a("</g>")
    a("</g>")

    # North arrow & 500 m ground scale bar inside map top-left + legend at bottom
    scale_500m_px = 500.0 / ns_span_m * map_h
    sb_x = map_x + 14.0
    sb_y = map_y + 26.0
    a(
        f'<rect x="{map_x + 8:.2f}" y="{map_y + 8:.2f}" width="{scale_500m_px + 54:.2f}" '
        'height="32" rx="4" fill="#0b1822" fill-opacity="0.84" '
        'stroke="#2b4b63" stroke-width="0.9" />'
    )
    a(
        f'<line x1="{sb_x:.2f}" y1="{sb_y:.2f}" x2="{sb_x + scale_500m_px:.2f}" y2="{sb_y:.2f}" '
        'stroke="#f2f7fb" stroke-width="2.2" />'
    )
    a(
        f'<line x1="{sb_x:.2f}" y1="{sb_y - 4:.2f}" x2="{sb_x:.2f}" y2="{sb_y + 4:.2f}" '
        'stroke="#f2f7fb" stroke-width="1.8" />'
    )
    a(
        f'<line x1="{sb_x + scale_500m_px:.2f}" y1="{sb_y - 4:.2f}" '
        f'x2="{sb_x + scale_500m_px:.2f}" y2="{sb_y + 4:.2f}" '
        'stroke="#f2f7fb" stroke-width="1.8" />'
    )
    a(
        f'<text x="{sb_x + scale_500m_px / 2.0:.2f}" y="{sb_y - 6:.2f}" text-anchor="middle" '
        'font-size="9.2" font-weight="700" fill="#f2f7fb">500 m</text>'
    )
    na_x = sb_x + scale_500m_px + 24.0
    a(
        f'<text x="{na_x:.2f}" y="{sb_y + 3:.2f}" text-anchor="middle" '
        'font-size="11" font-weight="700" fill="#4fd7eb">▲ N</text>'
    )

    # Bottom map legend (y = 746..796)
    a(
        '<g transform="translate(36,748)" font-size="9.4" fill="#d9e8f3">'
        '<line x1="0" y1="6" x2="22" y2="6" stroke="#4fd7eb" stroke-width="3" />'
        '<text x="27" y="9.5">Simulated EVA (A*)</text>'
        '<line x1="132" y1="6" x2="154" y2="6" stroke="#ff9e44" '
        'stroke-width="2.6" stroke-dasharray="6 3" />'
        '<text x="159" y="9.5">Derived 10 m Obstacle-Aware EVA</text>'
        '<line x1="336" y1="6" x2="358" y2="6" stroke="#dceaf5" '
        'stroke-width="1.8" stroke-dasharray="4 3" />'
        '<text x="363" y="9.5">Measured Rover Traverse</text>'
        '<rect x="0" y="20" width="12" height="10" fill="#df6658" '
        'fill-opacity="0.55" stroke="#ff8577" />'
        f'<text x="17" y="28.5">Scarps &gt;= 4 m ({scarp_count})</text>'
        '<rect x="132" y="20" width="12" height="10" fill="#edaa4d" '
        'fill-opacity="0.55" stroke="#ffd27d" />'
        f'<text x="149" y="28.5">Rock Formations &gt;= 4 m ({rock_count})</text>'
        '<circle cx="342" cy="25" r="5" fill="#4fb87a" stroke="#ffffff" stroke-width="1.2" />'
        '<text x="352" y="28.5">Science Stop (GO)</text>'
        '<polygon points="462,20 467,25 462,30 457,25" fill="#df6658" '
        'stroke="#ffffff" stroke-width="1.1" />'
        f'<text x="473" y="28.5">Benchmark (NO_GO &gt; {suit_max_slope_deg:.0f}°)</text>'
        "</g>"
    )

    # =========================================================================
    # Right Column — Telemetry, Stops/Benchmarks, Multi-Scale & Caveats
    # =========================================================================
    rx = 676.0
    rw = 504.0

    # Box 1: EVA Corridor Comparison
    a(
        f'<rect x="{rx:.1f}" y="82" width="{rw:.1f}" height="170" rx="8" '
        'fill="#162d3e" stroke="#2b4b63" stroke-width="1.2" />'
    )
    a(
        f'<text x="{rx + 16:.1f}" y="103" font-size="12" font-weight="700" fill="#e8f2f8">'
        "1. EVA CORRIDOR COMPARISON (STOP 1 SOL 413 -&gt; STOP 3 SOL 753)"
        "</text>"
    )
    if sim_route is not None:
        sp = sim_route.properties
        s_dist = sp.distance_m.value if sp.distance_m else 0.0
        s_slope = sp.max_slope_deg.value if sp.max_slope_deg else 0.0
        s_dur = sp.estimated_duration_h.value if sp.estimated_duration_h else 0.0
        s_rad = sp.estimated_radiation_msv.value if sp.estimated_radiation_msv else 0.0
        s_wb = _max_walkback_from_origin(sim_route)
        a(
            f'<rect x="{rx + 14:.1f}" y="112" width="{rw - 28:.1f}" height="62" rx="5" '
            'fill="#102331" stroke="#29526b" stroke-width="1" />'
        )
        a(_render_badge(rx + 22, 119, sp.tag, _tag_color(sp.tag)))
        a(
            f'<text x="{rx + 104:.1f}" y="131" font-size="10.5" font-weight="700" fill="#4fd7eb">'
            f"{_esc(sp.feature_id)} ({_esc(sp.verdict)})"
            "</text>"
        )
        a(
            f'<text x="{rx + 22:.1f}" y="149" font-size="10" fill="#e2eef6">'
            f"One-way: {s_dist:,.1f} m | "
            f"Max 1 m DTM slope: {s_slope:.2f}° (&lt;= {suit_max_slope_deg:.1f}°) | "
            f"Duration: {s_dur:.2f} h"
            "</text>"
        )
        a(
            f'<text x="{rx + 22:.1f}" y="165" font-size="9.5" fill="#9fc0d6">'
            f"Walkback tether: {s_wb:,.1f} m (&lt;= {walkback_max_m:,.0f} m) | "
            f"Dose: {s_rad:.4f} mSv (proxy Curiosity RAD, Gale)"
            "</text>"
        )

    if obs_route is not None:
        op = obs_route.properties
        o_dist = op.distance_m.value if op.distance_m else 0.0
        o_slope = op.max_slope_deg.value if op.max_slope_deg else 0.0
        o_dur = op.estimated_duration_h.value if op.estimated_duration_h else 0.0
        o_rad = op.estimated_radiation_msv.value if op.estimated_radiation_msv else 0.0
        o_wb = _max_walkback_from_origin(obs_route)
        a(
            f'<rect x="{rx + 14:.1f}" y="180" width="{rw - 28:.1f}" height="62" rx="5" '
            'fill="#102331" stroke="#5b452c" stroke-width="1" />'
        )
        a(_render_badge(rx + 22, 187, op.tag, _tag_color(op.tag)))
        a(
            f'<text x="{rx + 104:.1f}" y="199" font-size="10.5" font-weight="700" fill="#ff9e44">'
            f"{_esc(op.feature_id)} ({_esc(op.verdict)})"
            "</text>"
        )
        a(
            f'<text x="{rx + 22:.1f}" y="217" font-size="10" fill="#e2eef6">'
            f"One-way: {o_dist:,.1f} m | Max slope: {o_slope:.2f}° | "
            f"Duration: {o_dur:.2f} h (10 m HiRISE grid)"
            "</text>"
        )
        a(
            f'<text x="{rx + 22:.1f}" y="233" font-size="9.5" fill="#9fc0d6">'
            f"Walkback: {o_wb:,.1f} m | "
            f"Avoids {len(obstacle_features)} &gt;= 4 m scarps/formations | "
            f"Dose: {o_rad:.4f} mSv (proxy Curiosity RAD, Gale)"
            "</text>"
        )

    # Box 2: Science Stops & Rover Benchmarks
    a(
        f'<rect x="{rx:.1f}" y="262" width="{rw:.1f}" height="176" rx="8" '
        'fill="#162d3e" stroke="#2b4b63" stroke-width="1.2" />'
    )
    a(
        f'<text x="{rx + 16:.1f}" y="283" font-size="12" font-weight="700" fill="#e8f2f8">'
        "2. MEASURED SCIENCE STOPS (GO) &amp; SCALE-GAP BENCHMARKS (NO_GO)"
        "</text>"
    )
    row_y = 303.0
    for feat in (*stops, *benchmarks):
        fp = feat.properties
        sol = fp.sol or 0
        tilt = fp.rover_tilt_deg.value if fp.rover_tilt_deg else 0.0
        vc = _verdict_color(fp.verdict)
        kind_lbl = "STOP" if fp.segment_type == "SCIENCE_STOP" else "BENCHMARK"
        short_unit = (fp.geologic_unit or "").split("(")[0].strip()
        extra = ""
        if isinstance(feat.geometry, GeoJsonPointGeometry):
            pt_lon = float(feat.geometry.coordinates[0])
            pt_lat = float(feat.geometry.coordinates[1])
            if fp.segment_type == "SCIENCE_STOP":
                wb_stop_m = spherical_distance_m(origin_lon, origin_lat, pt_lon, pt_lat)
                if wb_stop_m < 1.0:
                    extra = f"Walkback {wb_stop_m:.1f} m · EVA Origin &amp; Rover 3.0 m UHF Mast"
                elif sol == 609:
                    extra = f"Walkback {wb_stop_m:,.1f} m · Sedimentary Bench"
                else:
                    extra = f"Walkback {wb_stop_m:,.1f} m · Upper Fan Turnaround"
            elif inside_bbox(pt_lon, pt_lat):
                cell_64m_deg = _nearest_cell_64m_slope_deg(pt_lon, pt_lat)
                extra = f"64 m orbital shows {cell_64m_deg:.2f}° vs {tilt:.2f}° ground!"
            else:
                extra = f"Max rover tilt across all {total_waypoints} mission stops"
        a(
            f'<rect x="{rx + 14:.1f}" y="{row_y - 12:.1f}" width="{rw - 28:.1f}" height="24" '
            'rx="4" fill="#102331" />'
        )
        a(
            f'<text x="{rx + 22:.1f}" y="{row_y + 4:.1f}" font-size="9.8" font-weight="700" '
            f'fill="{vc}">{kind_lbl} · Sol {sol}</text>'
        )
        a(
            f'<text x="{rx + 138:.1f}" y="{row_y + 4:.1f}" font-size="9.8" fill="#f2f7fb">'
            f"Tilt {tilt:5.2f}° [{_esc(fp.verdict)}]</text>"
        )
        a(
            f'<text x="{rx + 252:.1f}" y="{row_y + 4:.1f}" font-size="9.2" fill="#9fc0d6">'
            f"{extra or _esc(short_unit)}</text>"
        )
        row_y += 28.0

    # Box 3: Multi-Scale Slope Baselines & Grid Verdict Breakdown
    a(
        f'<rect x="{rx:.1f}" y="448" width="{rw:.1f}" height="150" rx="8" '
        'fill="#162d3e" stroke="#2b4b63" stroke-width="1.2" />'
    )
    a(
        f'<text x="{rx + 16:.1f}" y="469" font-size="12" font-weight="700" fill="#e8f2f8">'
        f"3. MULTI-SCALE HIRISE DTM SLOPE BASELINES "
        f"({len(cells):,} CELLS · {pack.hazards.cell_size_m:.1f} m)"
        "</text>"
    )
    bx_x = rx + 16.0
    for idx_b, (bl, role_lbl) in enumerate(
        (
            ("64", "Orbital Macro"),
            ("16", "Corridor Scale"),
            ("4", "Effective DTM"),
            ("1", "Diagnostic Only*"),
        )
    ):
        med_v, max_v = baseline_stats[bl]
        card_x = bx_x + idx_b * 119.0
        border_c = "#4c7391" if bl != "1" else "#6e5a3a"
        a(
            f'<rect x="{card_x:.1f}" y="479" width="112" height="58" rx="5" '
            f'fill="#102331" stroke="{border_c}" stroke-width="1" />'
        )
        a(
            f'<text x="{card_x + 8:.1f}" y="494" font-size="10" font-weight="700" fill="#4fd7eb">'
            f"{bl} m · {role_lbl}</text>"
        )
        a(
            f'<text x="{card_x + 8:.1f}" y="511" font-size="9.6" fill="#f2f7fb">'
            f"Median: {med_v:.2f}°</text>"
        )
        a(
            f'<text x="{card_x + 8:.1f}" y="527" font-size="9.6" fill="#9fc0d6">'
            f"Max: {max_v:.2f}°</text>"
        )

    a(
        f'<text x="{rx + 16:.1f}" y="555" font-size="9.6" fill="#e2eef6">'
        f"Grid Verdicts (4 m / 16 m / 64 m): GO = {verdict_counts.get('GO', 0)} | "
        f"CAUTION = {verdict_counts.get('CAUTION', 0):,} | "
        f"NO_GO = {verdict_counts.get('NO_GO', 0)}"
        "</text>"
    )
    a(
        f'<text x="{rx + 16:.1f}" y="573" font-size="9.1" fill="#edaa4d">'
        "*1 m baseline retained for telemetry only: excluded from GO/NO_GO gating due to sub-post"
        "</text>"
    )
    a(
        f'<text x="{rx + 16:.1f}" y="587" font-size="9.1" fill="#edaa4d">'
        "pixel-scale noise (~3-4 post effective horizontal resolution on 1 m/px HiRISE stereo DTM)."
        "</text>"
    )

    # Box 4: Safety Thresholds, Operational Caveats & Cryptographic Signature
    a(
        f'<rect x="{rx:.1f}" y="608" width="{rw:.1f}" height="196" rx="8" '
        'fill="#162d3e" stroke="#2b4b63" stroke-width="1.2" />'
    )
    a(
        f'<text x="{rx + 16:.1f}" y="629" font-size="12" font-weight="700" fill="#e8f2f8">'
        "4. SAFETY THRESHOLDS, COMMS/RADIATION CAVEATS &amp; PACK SIGNATURE"
        "</text>"
    )
    c = pack.constraints
    a(
        f'<text x="{rx + 16:.1f}" y="648" font-size="9.6" fill="#e2eef6">'
        f"• Limits [MEASURED]: Suit &lt;= {c.suit_max_slope_deg.value:.1f}° "
        f"(Apollo practical {c.apollo_practical_slope_deg.value:.1f}°) | "
        f"Walkback &lt;= {c.walkback_max_km.value:.1f} km | "
        f"EVA {c.eva_duration_min_h.value:.0f}-{c.eva_duration_max_h.value:.0f} h"
        "</text>"
    )
    gcr_note = c.gcr_dose_msv_per_day.note or "proxy Curiosity RAD, Gale"
    a(
        f'<text x="{rx + 16:.1f}" y="666" font-size="9.5" fill="#e2eef6">'
        f"• GCR Surface Baseline: {c.gcr_dose_msv_per_day.value:.2f} "
        f"{_esc(c.gcr_dose_msv_per_day.unit)} ({_esc(gcr_note)})."
        "</text>"
    )
    a(
        f'<text x="{rx + 16:.1f}" y="684" font-size="9.3" fill="#ffd7d2">'
        "• Solar Storm Caveat: Local terrain blocks only a few percent of galactic cosmic rays;"
        "</text>"
    )
    a(
        f'<text x="{rx + 24:.1f}" y="698" font-size="9.3" fill="#ffd7d2">'
        "it is not a shelter for a solar storm."
        "</text>"
    )
    a(
        f'<text x="{rx + 16:.1f}" y="716" font-size="9.3" fill="#edaa4d">'
        f"• Direct UHF Link (414.2 MHz, 1.8 m suit to 3.0 m Perseverance mast at Sol 413):"
        "</text>"
    )
    a(
        f'<text x="{rx + 24:.1f}" y="730" font-size="9.3" fill="#edaa4d">'
        f"NO_GO on {rf_nogo:,}/{rf_total:,} cells ({rf_nogo_pct}%) with no direct line of sight "
        "(direct rover LOS, not orbital relay)."
        "</text>"
    )
    a(
        f'<text x="{rx + 16:.1f}" y="748" font-size="9.3" fill="#9fc0d6">'
        f"• Unavailable Layers (indeterminacy I = 1.0, never fabricated): {_esc(unavailable_str)}."
        "</text>"
    )
    a(
        f'<line x1="{rx + 16:.1f}" y1="760" x2="{rx + rw - 16:.1f}" y2="760" '
        'stroke="#2b4b63" stroke-width="1" />'
    )
    a(
        f'<text x="{rx + 16:.1f}" y="776" font-size="9.0" fill="#9fc0d6" '
        'font-family="Consolas, monospace">'
        f"manifest.json sha256: {manifest_sha256[:32]}… ({len(pack.manifest.files)} signed files)"
        "</text>"
    )
    a(
        f'<text x="{rx + 16:.1f}" y="793" font-size="9.0" fill="#9fc0d6">'
        "Credits: NASA/JPL-Caltech/MSSS/ASU/USGS Astrogeology (Public Domain, 17 U.S.C. 105)."
        "</text>"
    )

    a("</svg>")
    svg_text = "\n".join(parts) + "\n"

    target = (
        output_path
        if output_path is not None
        else (repo_root / "docs" / "assets" / f"{pack.site_id}_eva_survival_map.svg")
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(svg_text)
    return target
