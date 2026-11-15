"""Block B3: 128-Combination Hyperparameter Sweep (E2B / 8-Shard Local Fallback) & B8 Timing.

Sweeps:
- `p in {2, 3}`
- `tau_max in {0.10, 0.20, 0.30, 0.40}`
- `h_min in {0.30, 0.50, 0.70, 1.00}`
- `eps in {0.005, 0.01, 0.02, 0.05}`
= 128 combinations partitioned across 8 isolated worker shards of 16 combinations each.

Strictly selects the sweet spot using ONLY odd-numbered sols (`tune_odd`), conditioned on
`B3` (persistent hazard detection = 100%) and `B9` (`zero_i_star_count == 0`).
Never reads `E2B_API_KEY` from anywhere except `os.environ.get("E2B_API_KEY")`.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from marswalk.bench.eval import (
    WaypointTerrainObservation,
    evaluate_observations_with_params,
    extract_window_observations,
    load_funnel_params,
)
from marswalk.bench.split import split_waypoints_odd_even
from marswalk.contracts.models import MARS_SPHERE_RADIUS_M
from marswalk.engine.carriers import (
    build_cell_carrier_triplets,
    compute_patch_roughness_fractal_texture,
)
from marswalk.engine.dtm_ingest import (
    compute_multiscale_grid_async,
    ingest_dtm_window_async,
    lat_to_eqc_y_m,
    lon_to_eqc_x_m,
    select_optimal_delta_window_2x2km,
)
from marswalk.engine.funnel import FunnelParams, run_cell_funnel
from marswalk.engine.prefilter import prefilter_cell
from marswalk.middleware.build_pack import (
    build_waypoints_collection,
    ensure_m20_datalake,
    spherical_distance_m,
)

P_GRID: tuple[int, ...] = (2, 3)
TAU_MAX_GRID: tuple[float, ...] = (0.10, 0.20, 0.30, 0.40)
H_MIN_GRID: tuple[float, ...] = (0.30, 0.50, 0.70, 1.00)
EPS_GRID: tuple[float, ...] = (0.005, 0.01, 0.02, 0.05)


def build_128_parameter_grid() -> list[FunnelParams]:
    """Build the deterministic 128-element Cartesian grid `p x tau_max x h_min x eps`."""
    return [
        FunnelParams(p=p_val, tau_max=tau_val, h_min=h_val, eps=eps_val)
        for p_val, tau_val, h_val, eps_val in itertools.product(
            P_GRID, TAU_MAX_GRID, H_MIN_GRID, EPS_GRID
        )
    ]


def check_b3_persistent_hazard_100pct(params: FunnelParams) -> bool:
    """Verify B3: 50 synthetic multi-scale scarps (25 2-scale 4m+16m, 25 3-scale) survive 100%."""
    for idx in range(50):
        scarp_deg = 21.0 + 0.35 * idx
        coarse_64 = (9.5 + 0.1 * (idx % 10)) if idx < 25 else (scarp_deg - 1.0)
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
        )
        out = run_cell_funnel(triplets, params=params, slopes_by_scale=slopes, walkback_m=450.0)
        if not out.persistent_hazard_detected or out.verdict not in ("NO_GO", "CAUTION"):
            return False
    return True


def _evaluate_single_combo(
    params: FunnelParams,
    tune_obs: list[WaypointTerrainObservation],
    shard_id: int,
) -> dict[str, Any]:
    """Evaluate one `(p, tau_max, h_min, eps)` candidate strictly on `tune_odd` sols."""
    t0 = time.perf_counter()
    metrics = evaluate_observations_with_params(tune_obs, params)
    b3_ok = check_b3_persistent_hazard_100pct(params)
    b9_ok = int(metrics["zero_i_star_count"]) == 0
    elapsed = round(time.perf_counter() - t0, 5)

    canonical_hash_payload = json.dumps(
        {
            "params": {
                "p": params.p,
                "tau_max": params.tau_max,
                "h_min": params.h_min,
                "eps": params.eps,
            },
            "mae_tune": metrics["mae_funnel"],
            "mean_i_star": metrics["mean_i_star"],
            "zero_i_star_count": metrics["zero_i_star_count"],
            "b3_pass": b3_ok,
            "b9_pass": b9_ok,
        },
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(canonical_hash_payload).hexdigest()

    return {
        "shard_id": shard_id,
        "params": {
            "p": params.p,
            "tau_max": params.tau_max,
            "h_min": params.h_min,
            "eps": params.eps,
        },
        "mae_tune": metrics["mae_funnel"],
        "mean_i_star": metrics["mean_i_star"],
        "zero_i_star_count": metrics["zero_i_star_count"],
        "b3_persistent_hazard_pass": b3_ok,
        "b9_entropy_floor_pass": b9_ok,
        "sha256": digest,
        "seconds": elapsed,
    }


def _run_shard_local(
    shard_id: int,
    shard_params: list[FunnelParams],
    tune_obs: list[WaypointTerrainObservation],
) -> list[dict[str, Any]]:
    """Execute one 16-combination worker shard locally."""
    return [_evaluate_single_combo(cfg, tune_obs, shard_id) for cfg in shard_params]


def _try_run_e2b_verification_probe(
    sweet_spot: dict[str, Any],
    api_key: str,
) -> tuple[str, str | None]:
    """If `E2B_API_KEY` is present in `os.environ`, verify deterministic SHA inside E2B microVM."""
    try:
        from e2b_code_interpreter import Sandbox  # type: ignore[import-untyped]

        payload_str = json.dumps(
            {
                "params": sweet_spot["params"],
                "mae_tune": sweet_spot["mae_tune"],
                "mean_i_star": sweet_spot["mean_i_star"],
                "zero_i_star_count": sweet_spot["zero_i_star_count"],
                "b3_pass": sweet_spot["b3_persistent_hazard_pass"],
                "b9_pass": sweet_spot["b9_entropy_floor_pass"],
            },
            sort_keys=True,
        )
        code = (
            "import hashlib\n"
            f"raw = {payload_str!r}.encode('utf-8')\n"
            "print(hashlib.sha256(raw).hexdigest())\n"
        )
        sbx = Sandbox.create(api_key=api_key, timeout=60)
        try:
            execution = sbx.run_code(code)
            out_lines = [ln.strip() for ln in execution.logs.stdout if ln.strip()]
            remote_sha = out_lines[-1] if out_lines else None
        finally:
            sbx.kill()
        return ("e2b_sandbox_verified", remote_sha)
    except Exception as exc:  # pragma: no cover - graceful quota/auth fallback
        return (f"local_8_shards_fallback (e2b_error: {type(exc).__name__})", None)


def run_sweet_spot_sweep_128(
    repo_root: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run the 128-combination sweep across 8 shards of 16 combinations on odd tune sols."""
    datalake_dir = repo_root / "datalake"
    wp_path, _ = ensure_m20_datalake(datalake_dir)
    raw_wp = json.loads(wp_path.read_text(encoding="utf-8"))
    wp_col = build_waypoints_collection(raw_wp)
    tune_wps, _test_wps = split_waypoints_odd_even(wp_col.features)
    odd_ids = {w.properties.waypoint_id for w in tune_wps}

    all_obs, _sha_pack = extract_window_observations(repo_root)
    tune_obs = [o for o in all_obs if o.waypoint_id in odd_ids]

    grid = build_128_parameter_grid()
    assert len(grid) == 128
    shards: list[list[FunnelParams]] = [grid[i * 16 : (i + 1) * 16] for i in range(8)]

    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(_run_shard_local, shard_idx, shard_cfg, tune_obs)
            for shard_idx, shard_cfg in enumerate(shards)
        ]
        shard_outputs = [fut.result() for fut in futures]
    total_seconds = round(time.perf_counter() - t_start, 4)

    records = [rec for shard_list in shard_outputs for rec in shard_list]
    admissible = [
        r for r in records if r["b3_persistent_hazard_pass"] and r["b9_entropy_floor_pass"]
    ]
    if not admissible:
        raise RuntimeError("No parameter combination satisfied both B3 and B9.")

    # Deterministic tie-break: min mae_tune, higher h_min, lower tau_max
    sweet_spot = min(
        admissible,
        key=lambda r: (
            r["mae_tune"],
            -r["params"]["h_min"],
            r["params"]["tau_max"],
            r["params"]["p"],
            r["params"]["eps"],
        ),
    )

    api_key = os.environ.get("E2B_API_KEY", "").strip()
    if api_key:
        backend, e2b_sha = _try_run_e2b_verification_probe(sweet_spot, api_key)
    else:
        backend = "local_8_shards_fallback (E2B_API_KEY not set in environment)"
        e2b_sha = None

    payload: dict[str, Any] = {
        "benchmark_id": "B3_SWEET_SPOT_SWEEP_128",
        "split": "odd_sols_only_tune",
        "n_tune_odd": len(tune_obs),
        "total_combinations": len(records),
        "shard_count": 8,
        "combinations_per_shard": 16,
        "execution_backend": backend,
        "e2b_remote_sha256": e2b_sha,
        "local_vs_e2b_sha_match": (e2b_sha == sweet_spot["sha256"]) if e2b_sha else None,
        "total_wall_seconds": total_seconds,
        "sweet_spot": sweet_spot,
        "records": records,
    }
    target = output_path or (repo_root / "bench" / "results" / "b3_sweep.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
    return payload


def measure_b8_window_timing(
    repo_root: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Benchmark B8: Measure wall-clock runtime across the 2x2 km HiRISE DTM window."""
    datalake_dir = repo_root / "datalake"
    wp_path, _ = ensure_m20_datalake(datalake_dir)
    raw_wp = json.loads(wp_path.read_text(encoding="utf-8"))
    wp_col = build_waypoints_collection(raw_wp)
    win = select_optimal_delta_window_2x2km(wp_col)
    params = load_funnel_params(repo_root)

    by_sol = {w.properties.sol: w for w in wp_col.features}
    origin_wp = by_sol.get(413, wp_col.features[0])
    origin_lon, origin_lat = origin_wp.properties.lon, origin_wp.properties.lat
    win_bbox = (win.min_lon, win.min_lat, win.max_lon, win.max_lat)

    t0 = time.perf_counter()
    dtm = asyncio.run(ingest_dtm_window_async(datalake_dir, win))
    samples = asyncio.run(
        compute_multiscale_grid_async(
            dtm,
            rows=16,
            cols=24,
            max_concurrency=8,
        )
    )

    arr = dtm.elevation_m
    h_px, w_px = arr.shape
    verdict_counts = {"GO": 0, "CAUTION": 0, "NO_GO": 0}

    for s in samples:
        wb_m = min(1950.0, spherical_distance_m(origin_lon, origin_lat, s.lon, s.lat) * 0.75)
        pf = prefilter_cell(
            lon=s.lon,
            lat=s.lat,
            bbox=win_bbox,
            slope_deg=max(s.slope_4m_deg, s.slope_16m_deg, s.slope_64m_deg),
            nodata_fraction=s.nodata_local,
            source_id="SRC-USGS-HIRISE-DTM-1M",
        )
        if not pf["keep"]:
            verdict_counts[pf["verdict"] or "NO_GO"] += 1
            continue

        x_m = lon_to_eqc_x_m(s.lon)
        y_m = lat_to_eqc_y_m(s.lat)
        col = max(64, min(w_px - 65, int(round((x_m - dtm.transform_x_min_m) - 0.5))))
        row = max(64, min(h_px - 65, int(round((dtm.transform_y_max_m - y_m) - 0.5))))
        patch = arr[row - 4 : row + 5, col - 4 : col + 5]
        rough_m, frac_d, curv = compute_patch_roughness_fractal_texture(patch, pixel_size_m=1.0)
        slopes_map = {
            1: s.slope_1m_deg,
            4: s.slope_4m_deg,
            16: s.slope_16m_deg,
            64: s.slope_64m_deg,
        }
        triplets = build_cell_carrier_triplets(
            slopes_by_scale=slopes_map,
            roughness_rms_m=rough_m,
            fractal_d=frac_d,
            curvature_m_inv=curv,
            walkback_m=wb_m,
            nodata_fraction=s.nodata_local,
            source_id="SRC-USGS-HIRISE-DTM-1M",
            dtm_resolution_m=1.0,
        )
        f_out = run_cell_funnel(
            triplets,
            params=params,
            slopes_by_scale=slopes_map,
            walkback_m=wb_m,
        )
        verdict_counts[f_out.verdict] += 1

    elapsed_s = round(time.perf_counter() - t0, 4)
    payload: dict[str, Any] = {
        "benchmark_id": "B8_WINDOW_2X2KM_TIMING",
        "window_size_km": "2x2",
        "dtm_shape_px": list(dtm.elevation_m.shape),
        "sphere_radius_m": MARS_SPHERE_RADIUS_M,
        "cell_count": len(samples),
        "seconds": elapsed_s,
        "verdict_counts": verdict_counts,
        "note": "Empirical wall-clock runtime measured locally on real 1 m/px USGS HiRISE window.",
    }
    target = output_path or (repo_root / "bench" / "results" / "b8_timing.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
    return payload
