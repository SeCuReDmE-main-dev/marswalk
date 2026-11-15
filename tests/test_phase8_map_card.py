"""Phase 8 deterministic test suite for the standalone CLI Survival Map Card Generator."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

from marswalk.contracts.models import GeoJsonLineGeometry, GeoJsonPointGeometry
from marswalk.middleware.build_pack import spherical_distance_m
from marswalk.middleware.cli import main
from marswalk.middleware.pack_loader import load_and_verify_pack

REPO_ROOT = Path(__file__).resolve().parents[1]
SVG_NS = "{http://www.w3.org/2000/svg}"


def test_cli_generate_map_card_produces_deterministic_valid_svg(tmp_path: Path) -> None:
    """Verify `generate-map-card` emits well-formed deterministic SVG without touching pack."""
    manifest_path = REPO_ROOT / "public_packs" / "jezero" / "v1" / "manifest.json"
    manifest_sha_before = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    out_a = tmp_path / "card_a.svg"
    out_b = tmp_path / "card_b.svg"

    rc_a = main(["generate-map-card", "--site", "jezero", "--output", str(out_a)])
    rc_b = main(["generate-map-card", "--site", "jezero", "--output", str(out_b)])
    assert rc_a == 0
    assert rc_b == 0

    bytes_a = out_a.read_bytes()
    bytes_b = out_b.read_bytes()
    assert bytes_a == bytes_b, "SVG generation must be byte-for-byte deterministic"
    assert b"\r\n" not in bytes_a, "SVG output must use canonical LF newlines"

    root = ET.fromstring(bytes_a.decode("utf-8"))
    assert root.tag == f"{SVG_NS}svg"
    assert root.attrib.get("viewBox") == "0 0 1200 820"

    # Verify embedded base64 hazard_overlay.png and 82 obstacle polygons
    images = root.findall(f".//{SVG_NS}image")
    assert len(images) == 1
    href = images[0].attrib.get("href", "")
    assert href.startswith("data:image/png;base64,")
    assert len(href) > 1000

    obs_group = root.find(f".//{SVG_NS}g[@id='obstacles-layer']")
    assert obs_group is not None
    polygons = obs_group.findall(f"{SVG_NS}polygon")
    assert len(polygons) == 82
    obs_types = {p.attrib.get("data-obstacle-type") for p in polygons}
    assert obs_types == {"scarp", "large_rock_formation"}

    svg_text = bytes_a.decode("utf-8")
    for expected_token in (
        "ROUTE-M20-MEASURED-TRAVERSE",
        "ROUTE-XEVA-SIMULATED-FAN-CORRIDOR",
        "ROUTE-EVA-M2-OBSTACLE-AWARE",
        "STOP-01-SOL413-DELTA-BASE",
        "STOP-02-SOL609-DELTA-BENCH",
        "STOP-03-SOL753-UPPER-FAN",
        "BENCHMARK-01-SOL700-DELTA-SCARP",
        "BENCHMARK-02-SOL1578-CRATER-RIM",
        "Sol 413",
        "Sol 609",
        "Sol 700",
        "Sol 753",
        "Sol 1578",
        "MEASURED",
        "DERIVED",
        "SIMULATED",
        "proxy Curiosity RAD, Gale",
        "pixel-scale noise",
        "not a shelter for a solar storm",
        "414.2 MHz",
        "no direct line of sight",
        "not orbital relay",
        manifest_sha_before[:32],
    ):
        assert expected_token in svg_text, f"Missing expected token in SVG: {expected_token}"

    for forbidden_token in (
        "mmgis-maps/M20/Layers/mosaics",
        "SPE shelter",
        "los_clearance_m",
        "max_shelter_angle_deg",
        "api.nasa.gov/mars-photos",
        "Max cross-slope",
        "occluded behind scarp",
    ):
        assert forbidden_token not in svg_text, f"Forbidden token in SVG: {forbidden_token}"

    manifest_sha_after = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert manifest_sha_after == manifest_sha_before


def test_svg_telemetry_numbers_recomputed_from_pack_geometry_and_cells(tmp_path: Path) -> None:
    """Recompute walkback distances, constraints, and Sol 700 64 m cell slope and verify in SVG."""
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    out_svg = tmp_path / "recomputed.svg"
    assert main(["generate-map-card", "--site", "jezero", "--output", str(out_svg)]) == 0
    svg_text = out_svg.read_text(encoding="utf-8")

    stops = sorted(
        (f for f in pack.route.features if f.properties.segment_type == "SCIENCE_STOP"),
        key=lambda f: f.properties.sol or 0,
    )
    assert isinstance(stops[0].geometry, GeoJsonPointGeometry)
    orig_lon = float(stops[0].geometry.coordinates[0])
    orig_lat = float(stops[0].geometry.coordinates[1])

    # Check recomputed walkback for each science stop
    for st in stops:
        assert isinstance(st.geometry, GeoJsonPointGeometry)
        wb_m = spherical_distance_m(
            orig_lon,
            orig_lat,
            float(st.geometry.coordinates[0]),
            float(st.geometry.coordinates[1]),
        )
        assert f"Walkback {wb_m:,.1f} m" in svg_text

    # Check recomputed max walkback for both route corridors and thresholds from constraints
    suit_limit = pack.constraints.suit_max_slope_deg.value
    walkback_limit_m = pack.constraints.walkback_max_km.value * 1000.0
    sim_feat = next(
        f for f in pack.route.features if f.properties.segment_type == "SIMULATED_ASTRONAUT_EVA"
    )
    obs_feat = next(
        f for f in pack.route.features if f.properties.segment_type == "DERIVED_OBSTACLE_AWARE_EVA"
    )
    assert isinstance(sim_feat.geometry, GeoJsonLineGeometry)
    assert isinstance(obs_feat.geometry, GeoJsonLineGeometry)
    sim_wb = max(
        spherical_distance_m(orig_lon, orig_lat, float(lon), float(lat))
        for lon, lat in sim_feat.geometry.coordinates
    )
    obs_wb = max(
        spherical_distance_m(orig_lon, orig_lat, float(lon), float(lat))
        for lon, lat in obs_feat.geometry.coordinates
    )
    assert f"Walkback tether: {sim_wb:,.1f} m (&lt;= {walkback_limit_m:,.0f} m)" in svg_text
    assert f"(&lt;= {suit_limit:.1f}°)" in svg_text
    assert f"Walkback: {obs_wb:,.1f} m" in svg_text
    assert f"Max slope: {obs_feat.properties.max_slope_deg.value:.2f}°" in svg_text

    # Check Sol 700 nearest cell 64 m orbital slope from hazard_grid.json
    bm_700 = next(f for f in pack.route.features if f.properties.sol == 700)
    assert isinstance(bm_700.geometry, GeoJsonPointGeometry)
    lon_700 = float(bm_700.geometry.coordinates[0])
    lat_700 = float(bm_700.geometry.coordinates[1])
    nearest_cell = min(
        pack.hazards.cells,
        key=lambda c: spherical_distance_m(lon_700, lat_700, c.lon, c.lat),
    )
    cell_64m = nearest_cell.slope_deg_by_baseline["64"].value
    tilt_700 = bm_700.properties.rover_tilt_deg.value
    assert f"64 m orbital shows {cell_64m:.2f}° vs {tilt_700:.2f}° ground!" in svg_text


def _segments_cross(p1, p2, q1, q2) -> bool:
    def orient(a, b, c) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = orient(q1, q2, p1), orient(q1, q2, p2)
    d3, d4 = orient(p1, p2, q1), orient(p1, p2, q2)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def _inside(pt, ring) -> bool:
    x, y = pt
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=False):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def test_svg_makes_no_unverified_avoidance_or_layer_claims(tmp_path: Path) -> None:
    """Audit H2/H3: obstacle contacts and UNAVAILABLE layers come from the pack, not literals."""
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    out_svg = tmp_path / "claims.svg"
    assert main(["generate-map-card", "--site", "jezero", "--output", str(out_svg)]) == 0
    svg_text = out_svg.read_text(encoding="utf-8")

    # Independent oracle: exact segment/edge crossing or vertex containment.
    obs_feat = next(
        f for f in pack.route.features if f.properties.segment_type == "DERIVED_OBSTACLE_AWARE_EVA"
    )
    assert isinstance(obs_feat.geometry, GeoJsonLineGeometry)
    line = [tuple(map(float, c)) for c in obs_feat.geometry.coordinates]
    touched = 0
    for o in pack.obstacles.features:
        ring = [tuple(map(float, c)) for c in o.geometry.coordinates[0]]
        edges = list(zip(ring, ring[1:] + ring[:1], strict=False))
        if any(_inside(p, ring) for p in line) or any(
            _segments_cross(a, b, e1, e2)
            for a, b in zip(line, line[1:], strict=False)
            for e1, e2 in edges
        ):
            touched += 1
    n_obs = len(pack.obstacles.features)
    assert f"Touches {touched}/{n_obs} obstacle polygons (vector check)" in svg_text
    assert "Avoids" not in svg_text

    unavailable = sorted(
        k for k, v in pack.hazards.external_layers_status.items() if v.get("tag") == "UNAVAILABLE"
    )
    assert unavailable, "pack must declare its UNAVAILABLE layers"
    assert f"never fabricated): {', '.join(unavailable)}." in svg_text
    hz = pack.hazards
    assert f"({hz.rows}x{hz.cols} · {hz.cell_size_m:.1f} m)" in svg_text


def test_committed_jezero_survival_map_asset_matches_generator(tmp_path: Path) -> None:
    """Verify `docs/assets/jezero_eva_survival_map.svg` exists and matches fresh CLI output."""
    committed_svg = REPO_ROOT / "docs" / "assets" / "jezero_eva_survival_map.svg"
    assert committed_svg.is_file(), "Missing committed docs/assets/jezero_eva_survival_map.svg"

    fresh_svg = tmp_path / "fresh.svg"
    rc = main(["generate-map-card", "--site", "jezero", "--output", str(fresh_svg)])
    assert rc == 0
    assert committed_svg.read_bytes() == fresh_svg.read_bytes()
