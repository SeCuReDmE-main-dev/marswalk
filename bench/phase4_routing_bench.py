"""Reproducible Phase 4 Obstacle-Aware Routing Benchmark on Real Jezero HiRISE DTM (`H1`).

Runs deterministic traverses — including the worst-case SE-floor <-> NW-upper-fan
delta-scarp detour — on the real USGS 1.0 m/px HiRISE DTM (`200 x 190` 10 m grid and
`400 x 379` 5 m grid), recording expansion counts, wall-clock latencies, cost-guard
rejections, and host machine metadata into `bench/results/phase4_routing_bench.json`.
"""

from __future__ import annotations

import asyncio
import json
import platform
import statistics
import time
from pathlib import Path
from typing import Any

from marswalk.engine.dtm_ingest import ingest_dtm_window_async, select_optimal_delta_window_2x2km
from marswalk.engine.obstacles_m1 import build_planner_grid_10m_from_window
from marswalk.engine.planner_m2 import _grid_rc_to_lonlat, plan_obstacle_aware_route
from marswalk.middleware.pack_loader import load_and_verify_pack


def _first_unblocked_near_corner(
    blocked_mask: Any,
    rows: int,
    cols: int,
    corner: str,
) -> tuple[int, int]:
    for d in range(max(rows, cols)):
        for r_off in range(d + 1):
            c_off = d - r_off
            if corner == "SE":
                r, c = rows - 2 - r_off, cols - 2 - c_off
            elif corner == "NW":
                r, c = 1 + r_off, 1 + c_off
            elif corner == "SW":
                r, c = rows - 2 - r_off, 1 + c_off
            else:
                r, c = 1 + r_off, cols - 2 - c_off
            if 0 <= r < rows and 0 <= c < cols and not bool(blocked_mask[r, c]):
                return (r, c)
    return (rows // 2, cols // 2)


def run_phase4_routing_benchmark(repo_root: Path, repeats: int = 5) -> dict[str, Any]:
    """Execute reproducible Phase 4 routing benchmarks on real Jezero DTM grids (`H1`)."""
    pack = load_and_verify_pack(repo_root, site_id="jezero")
    win = select_optimal_delta_window_2x2km(pack.waypoints)
    dtm = asyncio.run(ingest_dtm_window_async(repo_root / "datalake", win))
    bbox = pack.hazards.bbox

    configs = (
        ("grid_10m_200x190", 200, 190),
        ("grid_5m_400x379", 400, 379),
    )
    results_by_grid: list[dict[str, Any]] = []

    for label, rows, cols in configs:
        t_build0 = time.perf_counter()
        grid, _ = build_planner_grid_10m_from_window(
            dtm.elevation_m,
            dtm.transform_x_min_m,
            dtm.transform_y_max_m,
            bbox,
            rows=rows,
            cols=cols,
        )
        build_ms = (time.perf_counter() - t_build0) * 1000.0

        se_rc = _first_unblocked_near_corner(grid.blocked_mask, rows, cols, "SE")
        nw_rc = _first_unblocked_near_corner(grid.blocked_mask, rows, cols, "NW")
        sw_rc = _first_unblocked_near_corner(grid.blocked_mask, rows, cols, "SW")
        ne_rc = _first_unblocked_near_corner(grid.blocked_mask, rows, cols, "NE")

        scenarios = (
            (
                "worst_case_se_to_nw_across_scarp",
                [_grid_rc_to_lonlat(grid, *se_rc), _grid_rc_to_lonlat(grid, *nw_rc)],
            ),
            (
                "cross_diagonal_sw_to_ne",
                [_grid_rc_to_lonlat(grid, *sw_rc), _grid_rc_to_lonlat(grid, *ne_rc)],
            ),
        )

        scen_records: list[dict[str, Any]] = []
        for scen_name, wpts in scenarios:
            timings_ms: list[float] = []
            last_res = None
            for _ in range(max(3, int(repeats))):
                t0 = time.perf_counter()
                last_res = plan_obstacle_aware_route(grid, wpts, heuristic_weight=1.0)
                timings_ms.append((time.perf_counter() - t0) * 1000.0)
            assert last_res is not None
            sorted_ms = sorted(timings_ms)
            p95_idx = min(len(sorted_ms) - 1, int(round(0.95 * (len(sorted_ms) - 1))))
            scen_records.append(
                {
                    "scenario": scen_name,
                    "reachable": last_res.reachable,
                    "cells_expanded": last_res.cells_expanded,
                    "total_cells": rows * cols,
                    "expansion_fraction": round(last_res.cells_expanded / float(rows * cols), 4),
                    "median_ms": round(statistics.median(sorted_ms), 2),
                    "p95_ms": round(sorted_ms[p95_idx], 2),
                    "total_distance_m": last_res.total_distance_m,
                    "raw_cost_s": last_res.string_pull_audit.raw_cost_s,
                    "smoothed_cost_s": last_res.string_pull_audit.smoothed_cost_s,
                    "rejected_by_obstacle_count": (
                        last_res.string_pull_audit.rejected_by_obstacle_count
                    ),
                    "rejected_by_cost_guard_count": (
                        last_res.string_pull_audit.rejected_by_cost_guard_count
                    ),
                    "optimality_guarantee": last_res.optimality_guarantee,
                }
            )

        results_by_grid.append(
            {
                "grid_id": label,
                "rows": rows,
                "cols": cols,
                "step_x_ground_m": grid.step_x_ground_m,
                "step_y_ground_m": grid.step_y_ground_m,
                "blocked_cells": int(grid.blocked_mask.sum()),
                "build_grid_ms": round(build_ms, 1),
                "scenarios": scen_records,
            }
        )

    payload: dict[str, Any] = {
        "benchmark": "phase4_obstacle_aware_routing",
        "tag": "DERIVED",
        "source_id": "SRC-USGS-HIRISE-DTM-1M",
        "dtm_sha256": dtm.sha256,
        "machine_info": {
            "system": platform.system(),
            "machine": platform.machine(),
            "processor": platform.processor() or "unknown",
            "python_version": platform.python_version(),
        },
        "grids": results_by_grid,
    }
    out_path = repo_root / "bench" / "results" / "phase4_routing_bench.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    report = run_phase4_routing_benchmark(root)
    print(json.dumps(report, indent=2))
