"""Block B3 Tests: 128-Parameter Sweet-Spot Sweep, CRS Round-Trip Guard, and B8 Timing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marswalk.bench.e2b_sweep import measure_b8_window_timing, run_sweet_spot_sweep_128
from marswalk.contracts.models import MARS_SPHERE_RADIUS_M
from marswalk.engine.dtm_ingest import (
    eqc_x_m_to_lon,
    eqc_y_m_to_lat,
    lat_to_eqc_y_m,
    lon_to_eqc_x_m,
    verify_mars_crs_roundtrip,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_crs_roundtrip_and_mixed_sphere_attack() -> None:
    """Section 5 Attack: mixing local M20 meters or Earth sphere radius must be rejected."""
    # Valid Mars IAU 2015 sphere R = 3,396,190 m passes round-trip (< 1 mm error)
    err_m = verify_mars_crs_roundtrip(77.4051, 18.4589, sphere_radius_m=MARS_SPHERE_RADIUS_M)
    assert err_m < 1e-4

    # Attack 1: Mixing Earth WGS84 radius (6,378,137 m) shifts coordinates by hundreds of km
    with pytest.raises(ValueError, match="3396190"):
        verify_mars_crs_roundtrip(77.4051, 18.4589, sphere_radius_m=6_378_137.0)

    # Attack 2: Passing local M20 rover meters (~4580000 wrong origin / 0 sphere)
    with pytest.raises(ValueError, match="3396190"):
        verify_mars_crs_roundtrip(77.4051, 18.4589, sphere_radius_m=0.0)

    # Direct EQC round-trip across Jezero bounding box
    for lon, lat in ((77.3767, 18.4478), (77.4104, 18.4815), (77.4509, 18.4446)):
        x_m = lon_to_eqc_x_m(lon)
        y_m = lat_to_eqc_y_m(lat)
        assert abs(eqc_x_m_to_lon(x_m) - lon) < 1e-12
        assert abs(eqc_y_m_to_lat(y_m) - lat) < 1e-12


def test_b3_128_combo_sweep_selects_valid_odd_sol_sweet_spot(tmp_path: Path) -> None:
    """Verify 128-combination sweep across 8 shards selects odd-sol sweet spot with B3/B9 PASS."""
    out_json = tmp_path / "b3_sweep.json"
    res1 = run_sweet_spot_sweep_128(REPO_ROOT, output_path=out_json)
    res2 = run_sweet_spot_sweep_128(REPO_ROOT, output_path=tmp_path / "b3_sweep_run2.json")

    assert out_json.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["total_combinations"] == 128
    assert payload["shard_count"] == 8
    assert len(payload["records"]) == 128

    winner = payload["sweet_spot"]
    assert winner["b3_persistent_hazard_pass"] is True
    assert winner["b9_entropy_floor_pass"] is True
    assert winner["zero_i_star_count"] == 0
    assert winner["mae_tune"] > 0.0

    # B2 determinism: identical SHA-256 across independent sweep runs
    assert res1["sweet_spot"]["sha256"] == res2["sweet_spot"]["sha256"]


def test_b8_2x2km_window_timing_recorded_without_big_o(tmp_path: Path) -> None:
    """Verify B8 records empirical wall-clock runtime on the 2x2 km window with zero Big-O claim."""
    out_json = tmp_path / "b8_timing.json"
    timing = measure_b8_window_timing(REPO_ROOT, output_path=out_json)
    assert out_json.exists()
    raw = out_json.read_text(encoding="utf-8")
    assert ("O(" + "1)") not in raw
    assert timing["window_size_km"] == "2x2"
    assert timing["cell_count"] >= 384
    assert timing["seconds"] > 0.0
    assert timing["seconds"] < 30.0


def test_colab_sweet_spot_notebook_exists_and_is_valid_ipynb() -> None:
    """Verify `notebooks/explore_sweet_spot.ipynb` is valid nbformat v4 JSON."""
    nb_path = REPO_ROOT / "notebooks" / "explore_sweet_spot.ipynb"
    assert nb_path.exists()
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4
    assert len(nb["cells"]) >= 4
