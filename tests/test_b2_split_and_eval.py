"""Block B2 Tests: Disjoint Odd/Even Sol Split and Honest B5 Funnel Evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marswalk.bench.eval import evaluate_window_b5, run_and_save_b5_eval
from marswalk.bench.split import assert_disjoint_sol_split, split_waypoints_odd_even
from marswalk.middleware.pack_loader import load_and_verify_pack

REPO_ROOT = Path(__file__).resolve().parents[1]
HAS_LOCAL_DTM = (REPO_ROOT / "datalake" / "JEZ_hirise_soc_006_DTM_1m_window_2x2km.tif").exists()


def test_split_is_disjoint() -> None:
    """Section 5 Attack: tuning and testing on overlapping sols must be impossible."""
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    tune_odd, test_even = split_waypoints_odd_even(pack.waypoints.features)

    assert len(tune_odd) > 0
    assert len(test_even) > 0
    assert len(tune_odd) + len(test_even) == len(pack.waypoints.features)

    odd_ids = {w.properties.waypoint_id for w in tune_odd}
    even_ids = {w.properties.waypoint_id for w in test_even}
    assert odd_ids.isdisjoint(even_ids)
    assert all(w.properties.sol % 2 == 1 for w in tune_odd)
    assert all(w.properties.sol % 2 == 0 for w in test_even)

    # Injecting an overlapping sol into assert_disjoint_sol_split must raise ValueError
    with pytest.raises(ValueError, match="overlap"):
        assert_disjoint_sol_split(tune_odd, [tune_odd[0], *test_even])


@pytest.mark.skipif(
    not HAS_LOCAL_DTM,
    reason="Requires gitignored local datalake/JEZ_hirise_soc_006_DTM_1m_window_2x2km.tif",
)
def test_b5_eval_writes_honest_even_sol_metrics(tmp_path: Path) -> None:
    """Verify B5 evaluates strictly on even TEST sols and records required JSON fields."""
    out_json = tmp_path / "b5_eval.json"
    result = run_and_save_b5_eval(REPO_ROOT, output_path=out_json)

    assert out_json.exists()
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    for req_key in ("mae_funnel", "mae_fixed_4m", "mae_fixed_64m", "n_test", "sha256_pack"):
        assert req_key in payload

    assert payload["n_test"] > 40
    assert len(payload["sha256_pack"]) == 64
    assert result["mae_funnel"] > 0.0

    # Verify direct call on tune vs test produces distinct sample counts
    tune_metrics = evaluate_window_b5(REPO_ROOT, split="tune_odd")
    test_metrics = evaluate_window_b5(REPO_ROOT, split="test_even")
    assert tune_metrics["n_samples"] != test_metrics["n_samples"] or (
        tune_metrics["mae_fixed_4m"] != test_metrics["mae_fixed_4m"]
    )
