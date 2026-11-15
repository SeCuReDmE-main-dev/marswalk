"""CLI entrypoint for Block B4: SALib Sobol sensitivity (B7) and carrier ablation (B6)."""

from __future__ import annotations

import json
from pathlib import Path

from marswalk.bench.sobol_ablation import run_b6_carrier_ablation, run_b7_sobol_sensitivity


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    b7 = run_b7_sobol_sensitivity(repo_root, n_base=64)
    b6 = run_b6_carrier_ablation(repo_root)
    print(
        json.dumps(
            {
                "b7_dominant_param": b7["dominant_parameter"],
                "b7_ST": b7["ST"],
                "b7_max_seed_drift": b7["max_st_drift_between_seeds"],
                "b6_retained_count": b6["retained_carrier_count"],
                "b6_retained_carriers": b6["retained_carriers"],
                "b6_removed_carriers": b6["removed_carriers"],
                "b6_mae_tune_all_10": b6["baseline_mae_tune_all_10"],
                "b6_mae_tune_after_reduction": b6["mae_tune_after_reduction"],
                "b6_decision": b6["decision_summary"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
