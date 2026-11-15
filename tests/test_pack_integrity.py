"""Tests for Jezero v1 static pack SHA-256 integrity, DERIVED provenance, and tilt independence."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from marswalk.contracts.models import Quantity
from marswalk.middleware.build_pack import (
    SYNTHETIC_SOURCE_ID,
    build_jezero_pack,
    spherical_distance_m,
)
from marswalk.middleware.pack_loader import (
    PackIntegrityError,
    _verify_quantities_sources,
    load_and_verify_pack,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_jezero_pack_loads_and_verifies_sha256() -> None:
    """Verify all files in public_packs/jezero/v1/ pass SHA-256, inputs[], and Pydantic checks."""
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    assert pack.site_id == "jezero"
    assert pack.manifest.contract_version == "1.0.0"
    assert pack.manifest.pack_version == "1.0.1"
    assert len(pack.manifest.files) == 5
    assert len(pack.manifest.inputs) == 2

    total_bytes = sum(f.bytes for f in pack.manifest.files)
    assert total_bytes < 5 * 1024 * 1024

    assert len(pack.waypoints.features) == 708
    min_lon, min_lat, max_lon, max_lat = pack.manifest.bbox
    sols: list[int] = []
    max_tilt = 0.0
    for wp in pack.waypoints.features:
        lon = wp.properties.lon
        lat = wp.properties.lat
        assert min_lon <= lon <= max_lon
        assert min_lat <= lat <= max_lat
        assert wp.properties.rover_tilt_deg.tag == "MEASURED"
        assert wp.properties.elev_geoid_m.tag == "MEASURED"
        sols.append(wp.properties.sol)
        if wp.properties.rover_tilt_deg.value > max_tilt:
            max_tilt = wp.properties.rover_tilt_deg.value

    assert min(sols) == 13
    assert max(sols) == 2022
    assert max_tilt > 20.0


def test_hazard_grid_is_simulated_placeholder_without_monotonic_lock() -> None:
    """Verify R1 and R3: placeholder grid uses SIMULATED + synthetic-v1 and rock_cfa_pct=None."""
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    assert pack.hazards.grid_status == "PLACEHOLDER"
    assert pack.hazards.rows == 16
    assert pack.hazards.cols == 24
    assert len(pack.hazards.cells) == 384

    non_monotonic_count = 0
    for cell in pack.hazards.cells:
        assert cell.elev_m.tag == "SIMULATED"
        assert cell.elev_m.source_id == SYNTHETIC_SOURCE_ID
        assert cell.scale_divergence.tag == "SIMULATED"
        assert cell.scale_divergence.source_id == SYNTHETIC_SOURCE_ID
        assert cell.rock_cfa_pct is None
        assert cell.measured_rover_tilt_deg is None
        for b_key in ("1", "4", "16", "64"):
            q = cell.slope_deg_by_baseline[b_key]
            assert q.tag == "SIMULATED"
            assert q.source_id == SYNTHETIC_SOURCE_ID

        s1 = cell.slope_deg_by_baseline["1"].value
        s4 = cell.slope_deg_by_baseline["4"].value
        s16 = cell.slope_deg_by_baseline["16"].value
        s64 = cell.slope_deg_by_baseline["64"].value
        if not (s1 >= s4 >= s16 >= s64):
            non_monotonic_count += 1

    # Prove R3: slopes are NOT artificially forced into s1 >= s4 >= s16 >= s64
    assert non_monotonic_count > 0


def test_science_stops_on_eva_route_within_2km_and_benchmarks_separated() -> None:
    """Verify H1 and H2: all 3 science stops lie on the EVA route <= 2 km."""
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    eva_features = [
        f for f in pack.route.features if f.properties.segment_type == "SIMULATED_ASTRONAUT_EVA"
    ]
    assert len(eva_features) == 1
    eva_feat = eva_features[0]
    assert eva_feat.properties.max_slope_deg is not None
    assert eva_feat.properties.max_slope_deg.tag == "SIMULATED"
    assert eva_feat.properties.max_slope_deg.source_id == SYNTHETIC_SOURCE_ID
    assert eva_feat.properties.estimated_radiation_msv is not None
    assert eva_feat.properties.estimated_radiation_msv.tag == "SIMULATED"
    assert eva_feat.properties.estimated_radiation_msv.note == "proxy Curiosity RAD, Gale"

    eva_coords = set(eva_feat.geometry.coordinates)  # type: ignore[arg-type]
    origin_lon, origin_lat = eva_feat.geometry.coordinates[0]  # type: ignore[index]

    science_stops = [f for f in pack.route.features if f.properties.segment_type == "SCIENCE_STOP"]
    assert len(science_stops) == 3
    for stop in science_stops:
        pt = (stop.geometry.coordinates[0], stop.geometry.coordinates[1])
        assert pt in eva_coords, f"Science stop {stop.properties.feature_id} is not on EVA polyline"
        dist_m = spherical_distance_m(origin_lon, origin_lat, pt[0], pt[1])
        assert dist_m <= 2000.0, f"Science stop {stop.properties.feature_id} exceeds 2 km: {dist_m}"
        assert stop.properties.verdict == "GO"

    benchmarks = [f for f in pack.route.features if f.properties.segment_type == "BENCHMARK"]
    assert {b.properties.sol for b in benchmarks} == {700, 1578}


def test_derived_quantity_without_manifest_input_is_rejected() -> None:
    """Blocking provenance test: any DERIVED quantity without a manifest.inputs[] entry fails."""
    fake_derived = Quantity(
        value=12.3,
        unit="deg",
        tag="DERIVED",
        source_id="SRC-USGS-HIRISE-DTM-1M",
    )
    with pytest.raises(PackIntegrityError, match="has no verified file entry in manifest.inputs"):
        _verify_quantities_sources(
            fake_derived,
            valid_source_ids={"SRC-USGS-HIRISE-DTM-1M"},
            verified_input_source_ids={"SRC-M20-WAYPOINTS"},
            context="test_derived",
        )


def test_hazard_grid_is_strictly_independent_of_rover_tilt_deg(tmp_path: Path) -> None:
    """Verify R2: mutating rover_tilt_deg in M20_waypoints.json keeps hazard_grid SHA-256."""
    tmp_datalake = tmp_path / "datalake"
    tmp_datalake.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "datalake" / "M20_traverse.json", tmp_datalake / "M20_traverse.json")

    raw_wp = json.loads((REPO_ROOT / "datalake" / "M20_waypoints.json").read_text(encoding="utf-8"))
    for feat in raw_wp["features"]:
        feat["properties"]["tilt"] = 88.8888
    (tmp_datalake / "M20_waypoints.json").write_text(json.dumps(raw_wp), encoding="utf-8")

    build_jezero_pack(tmp_path)

    committed_grid_sha = hashlib.sha256(
        (REPO_ROOT / "public_packs" / "jezero" / "v1" / "hazard_grid.json").read_bytes()
    ).hexdigest()
    mutated_grid_sha = hashlib.sha256(
        (tmp_path / "public_packs" / "jezero" / "v1" / "hazard_grid.json").read_bytes()
    ).hexdigest()
    assert committed_grid_sha == mutated_grid_sha
