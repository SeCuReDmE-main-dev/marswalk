"""Paired bootstrap of the B5 held-out errors: is the funnel really better, or is it noise?

A difference of a few tenths of a degree on 72 rover stops can be luck. This script
resamples the 72 held-out (even-sol) stops 5,000 times with replacement and reports,
for each fixed baseline, the mean of (funnel error - fixed error) with a 95 % interval.
If the interval excludes 0, the difference is unlikely to be chance.

Run:  python bench/bootstrap_b5.py   ->  bench/results/b5_bootstrap.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from marswalk.bench.eval import (
    extract_window_observations,
    load_funnel_params,
    load_retained_carriers,
)
from marswalk.engine.carriers import build_cell_carrier_triplets
from marswalk.engine.funnel import run_cell_funnel

N_RESAMPLES = 5000
SEED = 7
BASELINES = (1, 4, 16, 64)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    observations, sha_pack = extract_window_observations(root)
    params = load_funnel_params(root)
    carriers = load_retained_carriers(root)
    test = [o for o in observations if o.sol % 2 == 0]

    funnel_err: list[float] = []
    fixed_err: dict[int, list[float]] = {b: [] for b in BASELINES}
    for obs in test:
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
        out = run_cell_funnel(
            triplets, params=params, slopes_by_scale=obs.slopes_by_scale, walkback_m=obs.walkback_m
        )
        tilt = obs.measured_rover_tilt_deg
        funnel_err.append(abs(out.retained_slope_deg - tilt))
        for b in BASELINES:
            fixed_err[b].append(abs(obs.slopes_by_scale[b] - tilt))

    n = len(test)
    rng = random.Random(SEED)
    results = {}
    for b in BASELINES:
        diffs = [f - x for f, x in zip(funnel_err, fixed_err[b], strict=True)]
        boots = sorted(
            sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(N_RESAMPLES)
        )
        lo, hi = boots[int(0.025 * N_RESAMPLES)], boots[int(0.975 * N_RESAMPLES)]
        if hi < 0:
            reading = "funnel better (interval excludes 0)"
        elif lo > 0:
            reading = "funnel worse (interval excludes 0)"
        else:
            reading = "not distinguishable (interval contains 0)"
        results[f"vs_fixed_{b}m"] = {
            "mean_diff_deg": round(sum(diffs) / n, 4),
            "ci95_deg": [round(lo, 4), round(hi, 4)],
            "reading": reading,
        }

    payload = {
        "benchmark_id": "B5_PAIRED_BOOTSTRAP",
        "split": "even_sols_only",
        "n_test": n,
        "n_resamples": N_RESAMPLES,
        "seed": SEED,
        "sha256_pack": sha_pack,
        "results": results,
    }
    target = root / "bench" / "results" / "b5_bootstrap.json"
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
