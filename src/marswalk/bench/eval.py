"""Benchmark B5 Evaluator: Retained Funnel Slope vs. Ground-Truth Rover Tilt.

Evaluates `MAE = mean(|retained_slope_deg - rover_tilt_deg|)` strictly on the requested
disjoint split (`tune_odd` for hyperparameter selection, `test_even` for final reporting),
comparing the multi-scale pruning funnel against fixed `4 m` and fixed `64 m` baselines.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from marswalk.bench.split import split_waypoints_odd_even
from marswalk.contracts.models import Waypoint
from marswalk.engine.carriers import (
    build_cell_carrier_triplets,
    compute_patch_roughness_fractal_texture,
)
from marswalk.engine.dtm_ingest import (
    IngestedDtmWindow,
    ingest_dtm_window_async,
    lat_to_eqc_y_m,
    lon_to_eqc_x_m,
    sample_point_multiscale_slopes,
    select_optimal_delta_window_2x2km,
)
from marswalk.engine.funnel import FunnelParams, run_cell_funnel
from marswalk.middleware.build_pack import (
    build_waypoints_collection,
    ensure_m20_datalake,
    spherical_distance_m,
)


@dataclass(frozen=True)
class WaypointTerrainObservation:
    """Pre-extracted DTM terrain observation at a single M20 waypoint."""

    waypoint_id: str
    sol: int
    lon: float
    lat: float
    measured_rover_tilt_deg: float
    slopes_by_scale: dict[int, float]
    roughness_rms_m: float
    fractal_d: float
    curvature_m_inv: float
    walkback_m: float
    nodata_fraction: float


def extract_window_observations(repo_root: Path) -> tuple[list[WaypointTerrainObservation], str]:
    """Load real DTM + M20 waypoints and extract local DTM patches for all window stops."""
    datalake_dir = repo_root / "datalake"
    wp_path, _ = ensure_m20_datalake(datalake_dir)
    raw_wp = json.loads(wp_path.read_text(encoding="utf-8"))
    wp_col = build_waypoints_collection(raw_wp)
    win = select_optimal_delta_window_2x2km(wp_col)
    dtm: IngestedDtmWindow = asyncio.run(ingest_dtm_window_async(datalake_dir, win))

    by_sol: dict[int, Waypoint] = {}
    for w in wp_col.features:
        if w.properties.sol not in by_sol:
            by_sol[w.properties.sol] = w
    origin_wp = by_sol.get(413, wp_col.features[0])
    origin_lon, origin_lat = origin_wp.properties.lon, origin_wp.properties.lat

    arr = dtm.elevation_m
    h, w_px = arr.shape
    observations: list[WaypointTerrainObservation] = []

    for wp in wp_col.features:
        lon = wp.properties.lon
        lat = wp.properties.lat
        x_m = lon_to_eqc_x_m(lon)
        y_m = lat_to_eqc_y_m(lat)
        if not (win.x_min_m <= x_m <= win.x_max_m and win.y_min_m <= y_m <= win.y_max_m):
            continue

        pt_slopes = sample_point_multiscale_slopes(dtm, lon, lat)
        col = max(64, min(w_px - 65, int(round((x_m - dtm.transform_x_min_m) - 0.5))))
        row = max(64, min(h - 65, int(round((dtm.transform_y_max_m - y_m) - 0.5))))
        patch = arr[row - 4 : row + 5, col - 4 : col + 5]
        rough_m, frac_d, curv = compute_patch_roughness_fractal_texture(patch, pixel_size_m=1.0)
        wb_m = min(1950.0, spherical_distance_m(origin_lon, origin_lat, lon, lat) * 0.75)

        observations.append(
            WaypointTerrainObservation(
                waypoint_id=wp.properties.waypoint_id,
                sol=wp.properties.sol,
                lon=lon,
                lat=lat,
                measured_rover_tilt_deg=float(wp.properties.rover_tilt_deg.value),
                slopes_by_scale={
                    1: pt_slopes["1"],
                    4: pt_slopes["4"],
                    16: pt_slopes["16"],
                    64: pt_slopes["64"],
                },
                roughness_rms_m=rough_m,
                fractal_d=frac_d,
                curvature_m_inv=curv,
                walkback_m=wb_m,
                nodata_fraction=dtm.nodata_fraction,
            )
        )

    manifest_path = repo_root / "public_packs" / "jezero" / "v1" / "manifest.json"
    if manifest_path.exists():
        sha_pack = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    else:
        sha_pack = hashlib.sha256(dtm.sha256.encode("utf-8")).hexdigest()

    return (observations, sha_pack)


def evaluate_observations_with_params(
    observations: list[WaypointTerrainObservation],
    params: FunnelParams,
    *,
    active_carriers: tuple[str, ...] | None = None,
) -> dict[str, float | int]:
    """Compute funnel MAE, fixed-baseline MAEs, and mean I* on a list of observations."""
    if not observations:
        raise ValueError("Cannot evaluate empty observation list.")

    err_funnel: list[float] = []
    err_1m: list[float] = []
    err_4m: list[float] = []
    err_16m: list[float] = []
    err_64m: list[float] = []
    i_stars: list[float] = []
    zero_i_count = 0

    for obs in observations:
        triplets = build_cell_carrier_triplets(
            slopes_by_scale=obs.slopes_by_scale,
            roughness_rms_m=obs.roughness_rms_m,
            fractal_d=obs.fractal_d,
            curvature_m_inv=obs.curvature_m_inv,
            walkback_m=obs.walkback_m,
            nodata_fraction=obs.nodata_fraction,
            source_id="SRC-USGS-HIRISE-DTM-1M",
            dtm_resolution_m=1.0,
            active_carriers=active_carriers,
        )
        f_out = run_cell_funnel(
            triplets,
            params=params,
            slopes_by_scale=obs.slopes_by_scale,
            walkback_m=obs.walkback_m,
        )
        tilt = obs.measured_rover_tilt_deg
        err_funnel.append(abs(f_out.retained_slope_deg - tilt))
        err_1m.append(abs(obs.slopes_by_scale[1] - tilt))
        err_4m.append(abs(obs.slopes_by_scale[4] - tilt))
        err_16m.append(abs(obs.slopes_by_scale[16] - tilt))
        err_64m.append(abs(obs.slopes_by_scale[64] - tilt))
        i_stars.append(f_out.i_star)
        if f_out.i_star <= 0.0 or not math.isfinite(f_out.i_star):
            zero_i_count += 1

    n = float(len(observations))
    return {
        "n_samples": len(observations),
        "mae_funnel": round(sum(err_funnel) / n, 4),
        "mae_fixed_1m": round(sum(err_1m) / n, 4),
        "mae_fixed_4m": round(sum(err_4m) / n, 4),
        "mae_fixed_16m": round(sum(err_16m) / n, 4),
        "mae_fixed_64m": round(sum(err_64m) / n, 4),
        "mean_i_star": round(sum(i_stars) / n, 4),
        "zero_i_star_count": zero_i_count,
    }


def load_funnel_params(repo_root: Path) -> FunnelParams:
    """Load `FunnelParams` from `profiles/funnel_v1.json`."""
    prof_path = repo_root / "profiles" / "funnel_v1.json"
    if not prof_path.exists():
        return FunnelParams()
    data = json.loads(prof_path.read_text(encoding="utf-8"))
    return FunnelParams(
        p=int(data["p"]),
        tau_max=float(data["tau_max"]),
        h_min=float(data["h_min"]),
        eps=float(data["eps"]),
    )


def load_retained_carriers(repo_root: Path) -> tuple[str, ...] | None:
    """Load `retained_carriers` from `profiles/funnel_v1.json` if present."""
    prof_path = repo_root / "profiles" / "funnel_v1.json"
    if not prof_path.exists():
        return None
    data = json.loads(prof_path.read_text(encoding="utf-8"))
    retained = data.get("retained_carriers")
    if isinstance(retained, list) and retained:
        return tuple(str(x) for x in retained)
    return None


def evaluate_window_b5(
    repo_root: Path,
    *,
    split: Literal["tune_odd", "test_even"] = "test_even",
    params: FunnelParams | None = None,
) -> dict[str, Any]:
    """Evaluate B5 strictly on `tune_odd` (odd sols) or `test_even` (even sols)."""
    datalake_dir = repo_root / "datalake"
    wp_path, _ = ensure_m20_datalake(datalake_dir)
    raw_wp = json.loads(wp_path.read_text(encoding="utf-8"))
    wp_col = build_waypoints_collection(raw_wp)
    tune_wps, test_wps = split_waypoints_odd_even(wp_col.features)
    allowed_ids = {
        w.properties.waypoint_id for w in (tune_wps if split == "tune_odd" else test_wps)
    }

    all_obs, sha_pack = extract_window_observations(repo_root)
    subset_obs = [o for o in all_obs if o.waypoint_id in allowed_ids]
    cfg = params if params is not None else load_funnel_params(repo_root)
    retained = load_retained_carriers(repo_root)
    metrics = evaluate_observations_with_params(subset_obs, cfg, active_carriers=retained)
    return {
        **metrics,
        "split": split,
        "params": {
            "p": cfg.p,
            "tau_max": cfg.tau_max,
            "h_min": cfg.h_min,
            "eps": cfg.eps,
        },
        "retained_carriers": list(retained) if retained is not None else None,
        "sha256_pack": sha_pack,
    }


def run_and_save_b5_eval(
    repo_root: Path,
    output_path: Path | None = None,
    params: FunnelParams | None = None,
) -> dict[str, Any]:
    """Run B5 on held-out EVEN sols (`test_even`) and write `bench/results/b5_eval.json`."""
    res = evaluate_window_b5(repo_root, split="test_even", params=params)
    fixed = {
        "1m": res["mae_fixed_1m"],
        "4m": res["mae_fixed_4m"],
        "16m": res["mae_fixed_16m"],
        "64m": res["mae_fixed_64m"],
    }
    best_name = min(fixed, key=fixed.get)
    beaten = sorted(k for k, v in fixed.items() if res["mae_funnel"] < v)
    comparison_note = (
        f"funnel point MAE below fixed baselines {beaten}; best fixed baseline is "
        f"{best_name} ({fixed[best_name]} deg). B5 verdict: "
        + ("PASS" if res["mae_funnel"] < fixed[best_name] else "FAIL")
        + " against the best fixed baseline. Significance: see bench/results/b5_bootstrap.json."
    )
    honest_16m_note = (
        "I propose (hypothesis, not tested): the rover chassis (~3 m wheelbase) plus stop "
        "localization error may average the ground over a footprint closer to the 16 m "
        "baseline, while the funnel keeps steeper 4 m slopes when hazards persist."
    )
    payload: dict[str, Any] = {
        "mae_funnel": res["mae_funnel"],
        "mae_fixed_1m": res["mae_fixed_1m"],
        "mae_fixed_4m": res["mae_fixed_4m"],
        "mae_fixed_16m": res["mae_fixed_16m"],
        "mae_fixed_64m": res["mae_fixed_64m"],
        "mean_i_star": res["mean_i_star"],
        "zero_i_star_count": res["zero_i_star_count"],
        "n_test": res["n_samples"],
        "split": "even_sols_only",
        "params": res["params"],
        "comparison_vs_fixed_baselines": comparison_note,
        "hypothesis_16m": honest_16m_note,
        "sha256_pack": res["sha256_pack"],
    }
    target = output_path or (repo_root / "bench" / "results" / "b5_eval.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
    return payload
