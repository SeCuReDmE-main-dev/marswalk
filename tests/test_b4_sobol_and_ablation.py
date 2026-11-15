"""Block B4 Tests: SALib Sobol Sensitivity (B7) and 10-Carrier Leave-One-Out Ablation (B6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marswalk.bench.sobol_ablation import run_b6_carrier_ablation, run_b7_sobol_sensitivity
from marswalk.engine.carriers import REQUIRED_CARRIERS

REPO_ROOT = Path(__file__).resolve().parents[1]
HAS_LOCAL_DTM = (REPO_ROOT / "datalake" / "JEZ_hirise_soc_006_DTM_1m_window_2x2km.tif").exists()


@pytest.mark.skipif(
    not HAS_LOCAL_DTM,
    reason="Requires gitignored local datalake/JEZ_hirise_soc_006_DTM_1m_window_2x2km.tif",
)
def test_b7_sobol_sensitivity_two_seeds_stable(tmp_path: Path) -> None:
    """Verify SALib Sobol indices (S1, ST) over (p, tau_max, h_min, eps) are finite and stable."""
    out_json = tmp_path / "b7_sobol.json"
    res = run_b7_sobol_sensitivity(REPO_ROOT, n_base=32, output_path=out_json)

    assert out_json.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["parameter_names"] == ["p", "tau_max", "h_min", "eps"]
    assert len(payload["ST"]) == 4
    assert len(payload["S1"]) == 4
    assert all(v >= -0.05 for v in payload["ST"].values())
    assert payload["max_st_drift_between_seeds"] < 0.25
    assert res["dominant_parameter"] in ("p", "tau_max", "h_min", "eps")


@pytest.mark.skipif(
    not HAS_LOCAL_DTM,
    reason="Requires gitignored local datalake/JEZ_hirise_soc_006_DTM_1m_window_2x2km.tif",
)
def test_b6_leave_one_out_ablation_and_reduction_rule(tmp_path: Path) -> None:
    """Verify leave-one-out ablation across all 10 carriers applies the (<0.05 & <=0.1 deg) rule."""
    out_json = tmp_path / "b6_ablation.json"
    res = run_b6_carrier_ablation(REPO_ROOT, output_path=out_json)

    assert out_json.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["initial_carrier_count"] == len(REQUIRED_CARRIERS)
    assert len(payload["leave_one_out"]) == 10

    retained = payload["retained_carriers"]
    removed = payload["removed_carriers"]
    assert len(retained) + len(removed) == 10
    assert len(retained) >= 4
    assert "I_slope" in retained
    assert res["b3_pass_after_reduction"] is True
    assert res["b9_pass_after_reduction"] is True
