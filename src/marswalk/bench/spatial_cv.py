"""Spatial-Block Cross-Validation & AOA / Josang Calibration Benchmark (`H2.d`).

Partitions the 146 in-window Perseverance stops into spatially separated blocks of side
`>= h_r` (empirical semivariogram range), executes leave-one-spatial-block-out cross-validation
for both the multi-scale pruning funnel and the Meyer & Pebesma (2021) AOA + Josang Subjective
Logic model, and writes `bench/results/aoa_cv.json`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from marswalk.bench.eval import (
    extract_window_observations,
    load_funnel_params,
    load_retained_carriers,
)
from marswalk.engine.calibration_aoa import (
    compute_cell_aoa_di,
    estimate_variogram_range_m,
    evaluate_cell_aoa_and_opinion,
    fit_spatial_aoa_model,
)
from marswalk.engine.carriers import build_cell_carrier_triplets
from marswalk.engine.dtm_ingest import ground_step_x_m, lat_to_eqc_y_m, lon_to_eqc_x_m
from marswalk.engine.funnel import run_cell_funnel


def run_and_save_spatial_cv(repo_root: Path) -> dict[str, Any]:
    """Run spatial-block CV on the 146 Jezero Delta stops and save `bench/results/aoa_cv.json`."""
    observations, sha_pack = extract_window_observations(repo_root)
    params = load_funnel_params(repo_root)
    carriers = load_retained_carriers(repo_root)

    n = len(observations)
    coords_xy = np.asarray(
        [
            (
                lon_to_eqc_x_m(o.lon) * ground_step_x_m(o.lat, 1.0),
                lat_to_eqc_y_m(o.lat),
            )
            for o in observations
        ],
        dtype=np.float64,
    )
    feats = np.asarray(
        [
            (
                o.slopes_by_scale[4],
                o.slopes_by_scale[16],
                o.slopes_by_scale[64],
                abs(o.slopes_by_scale[4] - o.slopes_by_scale[64]),
            )
            for o in observations
        ],
        dtype=np.float64,
    )
    tilts = np.asarray([o.measured_rover_tilt_deg for o in observations], dtype=np.float64)
    gt_hazard_labels = (tilts >= 10.0).astype(np.float64)

    h_r = estimate_variogram_range_m(coords_xy, tilts)
    block_side = max(80.0, h_r)
    bx = np.floor((coords_xy[:, 0] - np.min(coords_xy[:, 0])) / block_side).astype(int)
    by = np.floor((coords_xy[:, 1] - np.min(coords_xy[:, 1])) / block_side).astype(int)
    block_ids = list(zip(bx.tolist(), by.tolist(), strict=False))
    unique_blocks = sorted(set(block_ids))

    err_funnel: list[float] = []
    err_1m: list[float] = []
    err_4m: list[float] = []
    err_16m: list[float] = []
    err_64m: list[float] = []
    heldout_di: list[float] = []
    heldout_inside_aoa: list[bool] = []
    heldout_josang_i: list[float] = []
    total_uncertainty: list[float] = []

    for blk in unique_blocks:
        train_idx = [i for i, b_id in enumerate(block_ids) if b_id != blk]
        test_idx = [i for i, b_id in enumerate(block_ids) if b_id == blk]
        if len(train_idx) < 4 or not test_idx:
            continue

        aoa_fold = fit_spatial_aoa_model(
            orbital_features=feats[train_idx],
            coords_xy_m=coords_xy[train_idx],
            variogram_response=tilts[train_idx],
            independent_hazard_labels=gt_hazard_labels[train_idx],
        )

        for idx in test_idx:
            obs = observations[idx]
            triplets = build_cell_carrier_triplets(
                slopes_by_scale=obs.slopes_by_scale,
                roughness_rms_m=obs.roughness_rms_m,
                fractal_d=obs.fractal_d,
                curvature_m_inv=obs.curvature_m_inv,
                walkback_m=obs.walkback_m,
                nodata_fraction=obs.nodata_fraction,
                source_id="SRC-USGS-HIRISE-DTM-1M",
                dtm_resolution_m=1.0,
                active_carriers=carriers,
            )
            f_out = run_cell_funnel(
                triplets,
                params=params,
                slopes_by_scale=obs.slopes_by_scale,
                walkback_m=obs.walkback_m,
            )
            f_vec = (
                obs.slopes_by_scale[4],
                obs.slopes_by_scale[16],
                obs.slopes_by_scale[64],
                abs(obs.slopes_by_scale[4] - obs.slopes_by_scale[64]),
            )
            di_val = compute_cell_aoa_di(aoa_fold, f_vec)
            in_aoa, op = evaluate_cell_aoa_and_opinion(aoa_fold, f_vec)

            tilt = obs.measured_rover_tilt_deg
            e_f = abs(f_out.retained_slope_deg - tilt)
            err_funnel.append(e_f)
            err_1m.append(abs(obs.slopes_by_scale[1] - tilt))
            err_4m.append(abs(obs.slopes_by_scale[4] - tilt))
            err_16m.append(abs(obs.slopes_by_scale[16] - tilt))
            err_64m.append(abs(obs.slopes_by_scale[64] - tilt))
            heldout_di.append(di_val)
            heldout_inside_aoa.append(in_aoa)
            heldout_josang_i.append(op.i)
            total_uncertainty.append(0.5 * f_out.i_star + 0.5 * op.i)

    n_eval = max(1, len(err_funnel))
    # Reliability curve across 3 uncertainty terciles (low I, mid I, high I)
    paired = sorted(zip(total_uncertainty, err_funnel, strict=False), key=lambda x: x[0])
    t1 = max(1, len(paired) // 3)
    t2 = max(t1 + 1, (2 * len(paired)) // 3)
    bins = [paired[:t1], paired[t1:t2], paired[t2:]]
    reliability_bins = [
        {
            "bin_index": idx_b + 1,
            "count": len(b_items),
            "mean_uncertainty_i": round(
                sum(x[0] for x in b_items) / float(max(1, len(b_items))), 4
            ),
            "mae_deg": round(sum(x[1] for x in b_items) / float(max(1, len(b_items))), 4),
        }
        for idx_b, b_items in enumerate(bins)
        if b_items
    ]

    payload: dict[str, Any] = {
        "benchmark_id": "PHASE3_SPATIAL_BLOCK_CV_AND_AOA",
        "split_method": "leave_one_spatial_block_out",
        "n_waypoints": n,
        "variogram_range_m": h_r,
        "block_side_m": block_side,
        "n_eff_spatial_blocks": len(unique_blocks),
        "spatial_cv_mae_deg": {
            "funnel": round(sum(err_funnel) / n_eval, 4),
            "fixed_1m": round(sum(err_1m) / n_eval, 4),
            "fixed_4m": round(sum(err_4m) / n_eval, 4),
            "fixed_16m": round(sum(err_16m) / n_eval, 4),
            "fixed_64m": round(sum(err_64m) / n_eval, 4),
        },
        "aoa_heldout_summary": {
            "inside_aoa_fraction": round(sum(1 for x in heldout_inside_aoa if x) / n_eval, 4),
            "mean_normalized_di": round(sum(heldout_di) / n_eval, 4),
            "max_normalized_di": round(max(heldout_di) if heldout_di else 0.0, 4),
            "distinct_josang_i_count": len({round(v, 4) for v in heldout_josang_i}),
            "min_josang_i": round(min(heldout_josang_i) if heldout_josang_i else 1.0, 4),
            "max_josang_i": round(max(heldout_josang_i) if heldout_josang_i else 1.0, 4),
        },
        "reliability_terciles": reliability_bins,
        "sha256_pack": sha_pack,
    }
    out_path = repo_root / "bench" / "results" / "aoa_cv.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
