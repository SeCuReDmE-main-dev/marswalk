"""Block B4: SALib Sobol Sensitivity (B7) and 10-Carrier Leave-One-Out Ablation (B6).

Implements:
1. `run_b7_sobol_sensitivity`: Global variance-based Sobol indices (`S1`, `ST`) via `SALib`
   over `(p, tau_max, h_min, eps)` evaluated strictly on odd-sol tuning stops (`tune_odd`)
   across two independent seeds (`42` and `137`) to verify stability.
2. `run_b6_carrier_ablation`: Leave-one-out ablation across all 10 carriers (`REQUIRED_CARRIERS`)
   plus per-carrier variance contribution index. Applies the exact reduction rule:
   any carrier with `variance_index < 0.05` AND `|delta_mae_deg| <= 0.10` (while keeping
   `B3` persistent hazard = 100% and `B9` `I* > 0` intact) is pruned; all others are retained.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from SALib.analyze import sobol as sobol_analyze  # type: ignore[import-untyped]
from SALib.sample import sobol as sobol_sample  # type: ignore[import-untyped]

from marswalk.bench.eval import (
    WaypointTerrainObservation,
    evaluate_observations_with_params,
    extract_window_observations,
    load_funnel_params,
)
from marswalk.bench.split import split_waypoints_odd_even
from marswalk.engine.carriers import REQUIRED_CARRIERS, build_cell_carrier_triplets
from marswalk.engine.funnel import CarrierScaleTriplet, FunnelParams, run_cell_funnel
from marswalk.middleware.build_pack import build_waypoints_collection, ensure_m20_datalake

SOBOL_PROBLEM: dict[str, Any] = {
    "num_vars": 4,
    "names": ["p", "tau_max", "h_min", "eps"],
    "bounds": [
        [2.0, 3.9999],
        [0.10, 0.40],
        [0.30, 1.00],
        [0.005, 0.050],
    ],
}


def _load_tune_odd_observations(repo_root: Path) -> list[WaypointTerrainObservation]:
    datalake_dir = repo_root / "datalake"
    wp_path, _ = ensure_m20_datalake(datalake_dir)
    raw_wp = json.loads(wp_path.read_text(encoding="utf-8"))
    wp_col = build_waypoints_collection(raw_wp)
    tune_wps, _ = split_waypoints_odd_even(wp_col.features)
    odd_ids = {w.properties.waypoint_id for w in tune_wps}
    all_obs, _ = extract_window_observations(repo_root)
    return [o for o in all_obs if o.waypoint_id in odd_ids]


def _prebuild_observation_pools(
    tune_obs: list[WaypointTerrainObservation],
) -> list[tuple[list[CarrierScaleTriplet], WaypointTerrainObservation]]:
    """Pre-extract 30-triplet pools for each odd-sol observation for fast Sobol evaluation."""
    pools: list[tuple[list[CarrierScaleTriplet], WaypointTerrainObservation]] = []
    for obs in tune_obs:
        triplets = build_cell_carrier_triplets(
            slopes_by_scale=obs.slopes_by_scale,
            roughness_rms_m=obs.roughness_rms_m,
            fractal_d=obs.fractal_d,
            curvature_m_inv=obs.curvature_m_inv,
            walkback_m=obs.walkback_m,
            nodata_fraction=obs.nodata_fraction,
            source_id="SRC-USGS-HIRISE-DTM-1M",
            dtm_resolution_m=1.0,
        )
        pools.append((triplets, obs))
    return pools


def _eval_prebuilt_mae(
    pools: list[tuple[list[CarrierScaleTriplet], WaypointTerrainObservation]],
    params: FunnelParams,
) -> float:
    errs: list[float] = []
    for triplets, obs in pools:
        out = run_cell_funnel(
            triplets,
            params=params,
            slopes_by_scale=obs.slopes_by_scale,
            walkback_m=obs.walkback_m,
        )
        errs.append(abs(out.retained_slope_deg - obs.measured_rover_tilt_deg))
    return sum(errs) / float(len(errs))


def run_b7_sobol_sensitivity(
    repo_root: Path,
    *,
    n_base: int = 64,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run SALib Saltelli-Sobol sensitivity analysis over `(p, tau_max, h_min, eps)`."""
    tune_obs = _load_tune_odd_observations(repo_root)
    pools = _prebuild_observation_pools(tune_obs)

    def _run_seed(seed_val: int) -> dict[str, Any]:
        param_matrix = sobol_sample.sample(
            SOBOL_PROBLEM, N=n_base, calc_second_order=False, seed=seed_val
        )
        y_vals = np.zeros(param_matrix.shape[0], dtype=float)
        for idx, row in enumerate(param_matrix):
            cfg = FunnelParams(
                p=int(math.floor(float(row[0]))),
                tau_max=round(float(row[1]), 5),
                h_min=round(float(row[2]), 5),
                eps=round(float(row[3]), 6),
            )
            y_vals[idx] = _eval_prebuilt_mae(pools, cfg)
        si = sobol_analyze.analyze(SOBOL_PROBLEM, y_vals, calc_second_order=False, seed=seed_val)
        names = SOBOL_PROBLEM["names"]
        return {
            "sample_count": int(param_matrix.shape[0]),
            "S1": {names[i]: round(float(si["S1"][i]), 4) for i in range(4)},
            "S1_conf": {names[i]: round(float(si["S1_conf"][i]), 4) for i in range(4)},
            "ST": {names[i]: round(float(si["ST"][i]), 4) for i in range(4)},
            "ST_conf": {names[i]: round(float(si["ST_conf"][i]), 4) for i in range(4)},
        }

    res_a = _run_seed(42)
    res_b = _run_seed(137)
    names = SOBOL_PROBLEM["names"]
    drifts = {nm: round(abs(res_a["ST"][nm] - res_b["ST"][nm]), 4) for nm in names}
    max_drift = max(drifts.values())
    dominant = max(names, key=lambda nm: res_a["ST"][nm])

    payload: dict[str, Any] = {
        "benchmark_id": "B7_SALIB_SOBOL_SENSITIVITY",
        "split": "odd_sols_only_tune",
        "n_tune_odd": len(tune_obs),
        "n_base": n_base,
        "evaluations_per_seed": res_a["sample_count"],
        "parameter_names": names,
        "S1": res_a["S1"],
        "S1_conf": res_a["S1_conf"],
        "ST": res_a["ST"],
        "ST_conf": res_a["ST_conf"],
        "seed_137_ST": res_b["ST"],
        "st_drift_by_param": drifts,
        "max_st_drift_between_seeds": max_drift,
        "dominant_parameter": dominant,
    }
    target = output_path or (repo_root / "bench" / "results" / "b7_sobol.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
    return payload


def _check_b3_for_carrier_subset(params: FunnelParams, active_carriers: tuple[str, ...]) -> bool:
    for idx in range(30):
        scarp_deg = 21.0 + 0.4 * idx
        coarse_64 = (9.5 + 0.1 * (idx % 10)) if idx < 15 else (scarp_deg - 1.0)
        slopes = {4: scarp_deg + 1.5, 16: scarp_deg, 64: coarse_64}
        triplets = build_cell_carrier_triplets(
            slopes_by_scale=slopes,
            roughness_rms_m=0.22,
            fractal_d=2.34,
            curvature_m_inv=0.06,
            walkback_m=450.0,
            nodata_fraction=0.0,
            source_id="SRC-USGS-HIRISE-DTM-1M",
            dtm_resolution_m=1.0,
            active_carriers=active_carriers,
        )
        out = run_cell_funnel(triplets, params=params, slopes_by_scale=slopes, walkback_m=450.0)
        if not out.persistent_hazard_detected or out.verdict not in ("NO_GO", "CAUTION"):
            return False
    return True


def _compute_carrier_variance_indices(
    tune_obs: list[WaypointTerrainObservation],
) -> dict[str, float]:
    """Compute normalized variance contribution of each carrier's T across odd-sol observations."""
    t_series: dict[str, list[float]] = {c: [] for c in REQUIRED_CARRIERS}
    for obs in tune_obs:
        triplets = build_cell_carrier_triplets(
            slopes_by_scale=obs.slopes_by_scale,
            roughness_rms_m=obs.roughness_rms_m,
            fractal_d=obs.fractal_d,
            curvature_m_inv=obs.curvature_m_inv,
            walkback_m=obs.walkback_m,
            nodata_fraction=obs.nodata_fraction,
            source_id="SRC-USGS-HIRISE-DTM-1M",
            dtm_resolution_m=1.0,
        )
        for tr in triplets:
            t_series[tr.carrier].append(tr.t)

    raw_vars: dict[str, float] = {}
    for c, vals in t_series.items():
        mean_v = sum(vals) / float(len(vals))
        raw_vars[c] = sum((v - mean_v) ** 2 for v in vals) / float(len(vals))

    total_var = sum(raw_vars.values()) or 1.0
    return {c: round(raw_vars[c] / total_var, 4) for c in REQUIRED_CARRIERS}


def run_b6_carrier_ablation(
    repo_root: Path,
    *,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run leave-one-out ablation across all 10 carriers on `tune_odd` sols."""
    tune_obs = _load_tune_odd_observations(repo_root)
    params = load_funnel_params(repo_root)
    baseline = evaluate_observations_with_params(tune_obs, params)
    base_mae = float(baseline["mae_funnel"])
    var_indices = _compute_carrier_variance_indices(tune_obs)

    leave_one_out: list[dict[str, Any]] = []
    candidate_removals: list[str] = []

    for c in REQUIRED_CARRIERS:
        subset = tuple(x for x in REQUIRED_CARRIERS if x != c)
        sub_metrics = evaluate_observations_with_params(tune_obs, params, active_carriers=subset)
        sub_mae = float(sub_metrics["mae_funnel"])
        delta_mae = round(sub_mae - base_mae, 4)
        v_idx = var_indices[c]
        b3_sub = _check_b3_for_carrier_subset(params, subset)
        b9_sub = int(sub_metrics["zero_i_star_count"]) == 0

        low_impact = (v_idx < 0.05) and (abs(delta_mae) <= 0.10)
        removable = low_impact and b3_sub and b9_sub
        if removable:
            candidate_removals.append(c)
            action = "REMOVE_CANDIDATE (index < 0.05 and |delta_mae| <= 0.10 deg)"
        elif low_impact and not (b3_sub and b9_sub):
            action = "KEEP (required for B3/B9 safety invariant)"
        else:
            action = "KEEP (variance_index >= 0.05 or |delta_mae| > 0.10 deg)"

        leave_one_out.append(
            {
                "carrier": c,
                "variance_index": v_idx,
                "mae_tune_without_carrier": sub_mae,
                "delta_mae_deg": delta_mae,
                "mean_i_star_without": sub_metrics["mean_i_star"],
                "b3_pass_without": b3_sub,
                "b9_pass_without": b9_sub,
                "decision": action,
            }
        )

    # Verify joint removal of `candidate_removals` preserves B3, B9, and |delta_mae| <= 0.10 deg;
    # otherwise greedily add back in order of lowest variance_index until B3 & B9 & MAE hold.
    retained_list = list(REQUIRED_CARRIERS)
    removed_list: list[str] = []
    ordered_candidates = sorted(candidate_removals, key=lambda name: var_indices[name])
    for cand in ordered_candidates:
        trial_retained = tuple(x for x in retained_list if x != cand)
        if len(trial_retained) < 4:
            break
        trial_metrics = evaluate_observations_with_params(
            tune_obs, params, active_carriers=trial_retained
        )
        trial_b3 = _check_b3_for_carrier_subset(params, trial_retained)
        trial_b9 = int(trial_metrics["zero_i_star_count"]) == 0
        trial_delta = abs(float(trial_metrics["mae_funnel"]) - base_mae)
        if trial_b3 and trial_b9 and trial_delta <= 0.10:
            retained_list.remove(cand)
            removed_list.append(cand)

    final_metrics = evaluate_observations_with_params(
        tune_obs, params, active_carriers=tuple(retained_list)
    )
    final_b3 = _check_b3_for_carrier_subset(params, tuple(retained_list))
    final_b9 = int(final_metrics["zero_i_star_count"]) == 0

    summary = (
        f"I keep {len(retained_list)} of 10 carriers ({', '.join(retained_list)}) and prune "
        f"{len(removed_list)} negligible carriers ({', '.join(removed_list) or 'none'}) whose "
        "variance index < 0.05 and whose joint removal changes odd-sol MAE by <= 0.10 deg "
        "while preserving B3 (100% persistent scarp survival) and B9 (I* > 0 everywhere)."
    )

    payload: dict[str, Any] = {
        "benchmark_id": "B6_CARRIER_ABLATION",
        "split": "odd_sols_only_tune",
        "n_tune_odd": len(tune_obs),
        "params_used": {
            "p": params.p,
            "tau_max": params.tau_max,
            "h_min": params.h_min,
            "eps": params.eps,
        },
        "initial_carrier_count": len(REQUIRED_CARRIERS),
        "baseline_mae_tune_all_10": base_mae,
        "leave_one_out": leave_one_out,
        "retained_carrier_count": len(retained_list),
        "retained_carriers": retained_list,
        "removed_carriers": removed_list,
        "mae_tune_after_reduction": final_metrics["mae_funnel"],
        "mean_i_star_after_reduction": final_metrics["mean_i_star"],
        "b3_pass_after_reduction": final_b3,
        "b9_pass_after_reduction": final_b9,
        "decision_summary": summary,
    }
    target = output_path or (repo_root / "bench" / "results" / "b6_ablation.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
    return payload
