"""Independent, offline Part 2 audit probes; no production/test files are modified."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import heapq
import json
import math
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

from marswalk.bench.e2b_sweep import build_128_parameter_grid
from marswalk.engine import gates, planner_m2, plithogenic
from marswalk.engine.carriers import build_cell_carrier_triplets
from marswalk.engine.funnel import CarrierScaleTriplet, FunnelParams, run_cell_funnel
from marswalk.engine.obstacles_m1 import PlannerGrid10m, load_planner_grid_10m_png
from marswalk.engine.search_astar import run_single_leg_astar
from marswalk.middleware.pack_loader import load_and_verify_pack

ROOT = Path(__file__).resolve().parents[4]


def emit(name: str, value: Any) -> None:
    print(name + "=" + json.dumps(value, sort_keys=True, allow_nan=True))


def grid(rows: int, cols: int, rng: np.random.Generator | None = None) -> PlannerGrid10m:
    shape = (rows, cols)
    return PlannerGrid10m(
        rows=rows,
        cols=cols,
        bbox=(77.0, 18.0, 77.01, 18.01),
        step_x_ground_m=9.485,
        step_y_ground_m=10.0,
        blocked_mask=np.zeros(shape, dtype=bool),
        caution_mask=np.zeros(shape, dtype=bool),
        toe_refuge_mask=np.zeros(shape, dtype=bool),
        grad_x=np.zeros(shape) if rng is None else rng.uniform(-0.3, 0.3, shape),
        grad_y=np.zeros(shape) if rng is None else rng.uniform(-0.3, 0.3, shape),
        risk_penalty_01=np.zeros(shape) if rng is None else rng.uniform(0, 1, shape),
    )


def interval_in_square(a: tuple[int, int], b: tuple[int, int], r: int, c: int):
    """Exact Liang-Barsky slab intersection; coordinates are doubled cell indices."""
    lo, hi = Fraction(0), Fraction(1)
    for start, end, lower, upper in (
        (2 * a[0] + 1, 2 * b[0] + 1, 2 * r, 2 * r + 2),
        (2 * a[1] + 1, 2 * b[1] + 1, 2 * c, 2 * c + 2),
    ):
        delta = end - start
        if delta == 0:
            if not lower <= start <= upper:
                return None
        else:
            limits = sorted((Fraction(lower - start, delta), Fraction(upper - start, delta)))
            lo, hi = max(lo, limits[0]), min(hi, limits[1])
            if lo > hi:
                return None
    return (lo, hi)


def true_flat_integral(g: PlannerGrid10m, path: list[tuple[int, int]]) -> float:
    """Independent piecewise-cell risk line integral on flat terrain (zero touch length)."""
    speed = 2.4 * math.exp(-3.5 * 0.05) / 3.6
    total = 0.0
    for a, b in zip(path, path[1:], strict=False):
        length = math.hypot((b[1] - a[1]) * g.step_x_ground_m, (b[0] - a[0]) * g.step_y_ground_m)
        for r in range(g.rows):
            for c in range(g.cols):
                interval = interval_in_square(a, b, r, c)
                if interval:
                    total += (
                        length
                        * float(interval[1] - interval[0])
                        / speed
                        * (1 + 1.4 * float(g.risk_penalty_01[r, c]))
                    )
    return total


def route_polygon_intervals(a, b, ring):
    """Independent parametric segment/polygon clipping, positive interior lengths only."""

    def inside(x, y):
        state = False
        for u, v in zip(ring, ring[1:], strict=False):
            if (u[1] > y) != (v[1] > y):
                crossing = u[0] + (y - u[1]) * (v[0] - u[0]) / (v[1] - u[1])
                if x < crossing:
                    state = not state
        return state

    params = [0.0, 1.0]
    dx, dy = b[0] - a[0], b[1] - a[1]
    for u, v in zip(ring, ring[1:], strict=False):
        ex, ey = v[0] - u[0], v[1] - u[1]
        denominator = dx * ey - dy * ex
        if abs(denominator) < 1e-24:
            continue
        qx, qy = u[0] - a[0], u[1] - a[1]
        t = (qx * ey - qy * ex) / denominator
        s = (qx * dy - qy * dx) / denominator
        if 0 <= t <= 1 and 0 <= s <= 1:
            params.append(t)
    params = sorted(set(params))
    return [
        (lo, hi)
        for lo, hi in zip(params, params[1:], strict=False)
        if hi - lo > 1e-12 and inside(a[0] + 0.5 * (lo + hi) * dx, a[1] + 0.5 * (lo + hi) * dy)
    ]


async def gate_probes() -> None:
    source = ast.parse((ROOT / "src/marswalk/engine/pipeline.py").read_text(encoding="utf-8"))
    nested = [
        n
        for n in ast.walk(source)
        if isinstance(n, ast.AsyncFunctionDef)
        and n.name in {"_refine_g0", "_refine_g1", "_refine_g2"}
    ]
    namespace: dict[str, Any] = {"Any": Any}
    exec(
        compile(ast.Module(body=nested, type_ignores=[]), "pipeline_refinements_from_ast", "exec"),
        namespace,
    )
    examples = [
        (
            "G0",
            gates.gate_g0_ingest,
            {
                "dtm_sha256": "a" * 64,
                "sphere_radius_m": 3396190.0,
                "nodata_fraction": 0.2,
                "coverage_fraction": 0.8,
            },
            namespace["_refine_g0"],
        ),
        (
            "G1",
            gates.gate_g1_classify,
            {"cell_step_m": 8.0, "mean_cell_i": 0.6, "validation_test_mae_deg": 1.0},
            namespace["_refine_g1"],
        ),
        (
            "G2",
            gates.gate_g2_search,
            {
                "path_found": True,
                "max_path_slope_deg": 5.0,
                "max_walkback_m": 400.0,
                "sensitivity_jaccard": 0.3,
            },
            namespace["_refine_g2"],
        ),
    ]
    for name, fn, ctx, refine in examples:
        logs = []
        result = await gates.run_gate_with_hold_loop(fn, ctx, {}, refine, logs)
        emit(
            "fabricated_refinement_" + name,
            {
                "original_evidence": ctx,
                "decisions": [v.decision for v in logs],
                "final": result.model_dump(),
            },
        )

    async def unchanged(_attempt, ctx):
        return ctx

    logs = []
    await gates.run_gate_with_hold_loop(gates.gate_g2_search, examples[2][2], {}, unchanged, logs)
    emit(
        "unchanged_HOLD_escalation", [{"attempt": v.attempt, "decision": v.decision} for v in logs]
    )
    for name, fn, ctx in [
        (
            "G0_zero_coverage_nonhex",
            gates.gate_g0_ingest,
            {
                "dtm_sha256": "z" * 64,
                "sphere_radius_m": 3396190,
                "nodata_fraction": 0,
                "coverage_fraction": 0,
            },
        ),
        ("G1_empty", gates.gate_g1_classify, {}),
        (
            "G1_nan",
            gates.gate_g1_classify,
            {
                "validation_test_mae_deg": float("nan"),
                "cell_step_m": float("nan"),
                "mean_cell_i": float("nan"),
            },
        ),
        (
            "G3_nan",
            gates.gate_g3_plan,
            {
                "max_walkback_m": float("nan"),
                "duration_h": float("nan"),
                "radiation_msv": float("nan"),
                "all_stops_within_2km": True,
                "stop_count": 3,
            },
        ),
    ]:
        emit(name, (await fn(ctx, {})).model_dump())


def main() -> None:
    assert Path(planner_m2.__file__).resolve().is_relative_to(ROOT)
    emit("source_import", Path(planner_m2.__file__).relative_to(ROOT).as_posix())
    emit(
        "raw_cache_files",
        sorted(
            p.relative_to(ROOT).as_posix() for p in (ROOT / "datalake").rglob("*") if p.is_file()
        ),
    )
    a, b = (0.8, 0.1, 0.2), (0.3, 0.4, 0.6)
    for c in (0, 0.5, 1):
        expected = ((1 - c) * 0.24 + c * 0.86, min(1.0, 0.25 + c * 0.5), (1 - c) * 0.68 + c * 0.12)
        actual = plithogenic.plithogenic_combine_triplet(a, b, c)
        assert np.allclose(expected, actual)
        emit("fusion_c_" + str(c), {"expected": expected, "actual": actual})
    for params in ({"s1_deg": 20.01, "walkback_m": 100}, {"s1_deg": 2, "walkback_m": 2000.01}):
        result = plithogenic.evaluate_cell_plithogenic(
            **params,
            s4_deg=2,
            s16_deg=2,
            s64_deg=2,
            divergence_deg=0,
            roughness_deg=0,
            geologic_unit="delta",
            dist_to_m20_stop_m=0,
        )
        emit(
            "legacy_fusion_hard_veto",
            {"inputs": params, "verdict": result.verdict, "veto": result.veto_triggered},
        )
    prof = json.loads((ROOT / "profiles/funnel_v1.json").read_text())
    cfg = FunnelParams(**{k: prof[k] for k in ("p", "tau_max", "h_min", "eps")})
    for slopes in (
        {4: 25.0, 16: 3.0, 64: 2.0},
        {4: 25.0, 16: 24.0, 64: 2.0},
        {4: 3.0, 16: 3.0, 64: 3.0},
    ):
        pool = build_cell_carrier_triplets(
            slopes_by_scale=slopes,
            roughness_rms_m=0.01,
            fractal_d=2.2,
            curvature_m_inv=0.02,
            walkback_m=100,
            nodata_fraction=0,
            source_id="SRC-USGS-HIRISE-DTM-1M",
            active_carriers=tuple(prof["retained_carriers"]),
        )
        emit(
            "production_funnel",
            {
                "slopes": slopes,
                "result": run_cell_funnel(
                    pool, params=cfg, slopes_by_scale=slopes, walkback_m=100
                ).to_dict(),
            },
        )
    uniform = [CarrierScaleTriplet("I_slope", s, 0.9, 0.1, 0.1) for s in (4, 16, 64)]
    emit(
        "initial_entropy_below_floor",
        run_cell_funnel(uniform, params=cfg, slopes_by_scale={4: 2.0, 16: 2.0, 64: 2.0}).to_dict(),
    )
    asyncio.run(gate_probes())

    pack = load_and_verify_pack(ROOT, site_id="jezero")
    template = pack.hazards.cells[0]
    cells = {}
    for r in range(2):
        for c in range(2):
            slope = template.slope_deg_by_baseline["4"].model_copy(update={"value": 2.0})
            cells[r, c] = template.model_copy(
                update={
                    "row": r,
                    "col": c,
                    "cell_id": f"TEST-{r}-{c}",
                    "lon": 77.0 + c * 0.0001,
                    "lat": 18.0 + r * 0.0001,
                    "verdict": "GO",
                    "slope_deg_by_baseline": {"4": slope},
                    "reason": "delta",
                }
            )
    no_go = cells[1, 1].model_copy(
        update={
            "verdict": "NO_GO",
            "slope_deg_by_baseline": {
                "4": cells[1, 1].slope_deg_by_baseline["4"].model_copy(update={"value": 30.0})
            },
        }
    )
    cells[1, 1] = no_go
    emit(
        "legacy_NO_GO_goal_slope30_walkback0_limit",
        run_single_leg_astar(cells, 2, 2, (0, 0), (1, 1), (77.0, 18.0), max_walkback_m=0),
    )
    cells[1, 1] = cells[0, 0].model_copy(
        update={"row": 1, "col": 1, "lon": 77.0001, "lat": 18.0001}
    )
    cells[0, 1] = cells[0, 1].model_copy(update={"verdict": "NO_GO"})
    cells[1, 0] = cells[1, 0].model_copy(update={"verdict": "NO_GO"})
    emit(
        "legacy_diagonal_between_two_blocked_cells",
        run_single_leg_astar(cells, 2, 2, (0, 0), (1, 1), (77.0, 18.0)),
    )
    emit(
        "legacy_same_blocked_cell", run_single_leg_astar(cells, 2, 2, (0, 1), (0, 1), (77.0, 18.0))
    )

    mismatch = []
    comparisons = 0
    for ar in range(5):
        for ac in range(5):
            for br in range(5):
                for bc in range(5):
                    ok, actual = planner_m2.supercover_grid_cells(5, 5, ar, ac, br, bc)
                    expected = {
                        (r, c)
                        for r in range(5)
                        for c in range(5)
                        if interval_in_square((ar, ac), (br, bc), r, c) is not None
                    }
                    comparisons += 1
                    if not ok or set(actual) != expected:
                        mismatch.append([ar, ac, br, bc, actual, sorted(expected)])
    emit("supercover_exact_square_oracle", {"comparisons": comparisons, "mismatches": mismatch})
    emit("supercover_negative_bounds", planner_m2.supercover_grid_cells(3, 3, -1, 0, 2, 2))
    blocked = [False] * 9
    blocked[1] = True
    emit(
        "supercover_blocked_corner",
        planner_m2.supercover_grid_cells(3, 3, 0, 0, 1, 1, blocked_flat=blocked),
    )
    emit("vmax", {"kmh": planner_m2.V_MAX_XEVA_KMH, "m_s": planner_m2.V_MAX_XEVA_M_S})
    rng = np.random.default_rng(20261115)
    errors, checked_edges = [], 0
    max_scalar_vector_error = 0.0
    for trial in range(30):
        g = grid(8, 9, rng)
        g.blocked_mask[:] = rng.uniform(0, 1, (8, 9)) < 0.1
        g.blocked_mask[0, 0] = g.blocked_mask[-1, -1] = False
        found, path, costs, _ = planner_m2._astar_single_leg(g, (0, 0), (7, 8))
        best = {(0, 0): 0.0}
        heap = [(0.0, (0, 0))]
        while heap:
            distance, current = heapq.heappop(heap)
            if distance != best[current]:
                continue
            for dr, dc in planner_m2._NEIGHBORS_8:
                nxt = (current[0] + dr, current[1] + dc)
                valid, cost, *_ = planner_m2._cell_step_cost_s(g, *current, *nxt)
                if valid and distance + cost < best.get(nxt, math.inf):
                    best[nxt] = distance + cost
                    heapq.heappush(heap, (distance + cost, nxt))
        actual = costs[-1] if found else math.inf
        expected = best.get((7, 8), math.inf)
        if not (actual == expected or math.isclose(actual, expected, abs_tol=1e-8)):
            errors.append({"trial": trial, "astar": actual, "dijkstra": expected})
        tables = planner_m2._get_directional_edge_tables(
            g, alpha_slope=1.2, gamma_risk=1.4, pure_time_only=False
        )
        for (dr, dc), (_, costs_table) in zip(planner_m2._NEIGHBORS_8, tables, strict=False):
            for r in range(8):
                for c in range(9):
                    valid, scalar, *_ = planner_m2._cell_step_cost_s(g, r, c, r + dr, c + dc)
                    vector = costs_table[r * 9 + c]
                    checked_edges += 1
                    if valid:
                        max_scalar_vector_error = max(max_scalar_vector_error, abs(scalar - vector))
                    elif not math.isinf(vector):
                        errors.append({"trial": trial, "bad_edge": [r, c, dr, dc]})
    emit(
        "M2_Astar_vs_independent_scalar_Dijkstra",
        {
            "trials": 30,
            "errors": errors,
            "edge_comparisons": checked_edges,
            "max_scalar_vector_error_s": max_scalar_vector_error,
        },
    )

    for trial in range(200):
        g = grid(6, 7)
        g.risk_penalty_01[:] = rng.uniform(0, 1, (6, 7))
        found, path, costs, _ = planner_m2._astar_single_leg(g, (0, 0), (5, 6))
        if not found:
            continue
        smoothed, audit = planner_m2.string_pull_with_cost_guard(g, path, costs)
        true_raw, true_smooth = true_flat_integral(g, path), true_flat_integral(g, smoothed)
        if true_smooth > true_raw + 1e-6:
            emit(
                "cost_guard_true_line_integral_counterexample",
                {
                    "trial": trial,
                    "raw": path,
                    "smoothed": smoothed,
                    "reported": audit.__dict__,
                    "true_raw_s": true_raw,
                    "true_smoothed_s": true_smooth,
                    "risk": g.risk_penalty_01.tolist(),
                },
            )
            break
    else:
        emit(
            "cost_guard_true_line_integral_counterexample",
            "none within 200 deterministic risk grids",
        )

    hazard = json.loads((ROOT / "public_packs/jezero/v1/hazard_grid.json").read_text())
    emit("hazard_top_keys", sorted(hazard))
    sol700 = next(c for c in hazard["cells"] if c["cell_id"] == "JEZ-R27-C37")
    emit("JEZ_R27_C37_slopes", sol700["slope_deg_by_baseline"])
    validation = json.loads((ROOT / "public_packs/jezero/v1/validation_report.json").read_text())
    sol700_records = []
    for value in validation.values():
        if isinstance(value, list):
            sol700_records.extend(
                item for item in value if isinstance(item, dict) and item.get("sol") == 700
            )
    emit("Sol700_exact_waypoint_validation", sol700_records)
    logs = [
        json.loads(line)
        for line in (ROOT / "public_packs/jezero/v1/gate_log.jsonl").read_text().splitlines()
    ]
    coherence = sum(
        abs(c["slope_deg_by_baseline"]["4"]["value"] - c["slope_deg_by_baseline"]["16"]["value"])
        for c in hazard["cells"]
    ) / len(hazard["cells"])
    emit(
        "G1_pack_record_and_independent_grid",
        {
            "record": next(v for v in logs if v["gate_id"] == "G1_CLASSIFY"),
            "actual_cell_size_m": hazard["cell_size_m"],
            "mean_abs_4m_minus_16m_deg": coherence,
        },
    )
    emit(
        "production_walkback_transform",
        {
            "physical_distance_m": 2500.0,
            "funnel_distance_m": min(1950.0, 2500.0 * 0.75),
            "maximum_funnel_distance_m": 1950.0,
            "funnel_veto_threshold_m": 2000.0,
        },
    )
    emit(
        "manifest_sha256",
        hashlib.sha256((ROOT / "public_packs/jezero/v1/manifest.json").read_bytes()).hexdigest(),
    )
    collection = json.loads((ROOT / "public_packs/jezero/v1/route.geojson").read_text())
    route = next(
        f
        for f in collection["features"]
        if f["properties"]["feature_id"] == "ROUTE-EVA-M2-OBSTACLE-AWARE"
    )
    coords = route["geometry"]["coordinates"]
    obstacles = json.loads((ROOT / "public_packs/jezero/v1/obstacles.geojson").read_text())[
        "features"
    ]
    touches = []
    for obstacle in obstacles:
        ring = obstacle["geometry"]["coordinates"][0]
        overlaps = []
        for k, (a, b) in enumerate(zip(coords, coords[1:], strict=False)):
            intervals = route_polygon_intervals(a, b, ring)
            if intervals:
                length = math.hypot(
                    (b[0] - a[0])
                    * math.pi
                    / 180
                    * 3396190
                    * math.cos(math.radians(0.5 * (a[1] + b[1]))),
                    (b[1] - a[1]) * math.pi / 180 * 3396190,
                )
                overlaps.append(
                    {
                        "segment": k,
                        "intervals": intervals,
                        "length_inside_m": length * sum(hi - lo for lo, hi in intervals),
                    }
                )
        if overlaps:
            touches.append({"properties": obstacle["properties"], "overlaps": overlaps})
    g_pack = load_planner_grid_10m_png(
        ROOT / "public_packs/jezero/v1/planner_grid_10m.png", tuple(hazard["bbox"])
    )
    blocked_crossings = []
    route_rcs = [planner_m2._lonlat_to_grid_rc(g_pack, *coordinate)[1:] for coordinate in coords]
    for k, (a, b) in enumerate(zip(route_rcs, route_rcs[1:], strict=False)):
        ok, visited = planner_m2.supercover_grid_cells(
            g_pack.rows, g_pack.cols, *a, *b, blocked_flat=g_pack.blocked_mask.ravel().tolist()
        )
        if not ok:
            blocked_crossings.append({"segment": k, "visited": visited})
    emit(
        "M2_pack_route_vs_polygons",
        {
            "route_points": len(coords),
            "obstacle_count": len(obstacles),
            "positive_interior_intersections": touches,
            "PNG_blocked_supercover_segments": blocked_crossings,
        },
    )
    bbox = hazard["bbox"]
    tune, test = [], []
    for waypoint in pack.waypoints.features:
        p = waypoint.properties
        if bbox[0] <= p.lon <= bbox[2] and bbox[1] <= p.lat <= bbox[3]:
            (tune if p.sol % 2 else test).append(p.waypoint_id)
    emit(
        "window_split",
        {
            "tune_odd": len(tune),
            "test_even": len(test),
            "overlap_ids": sorted(set(tune) & set(test)),
        },
    )
    for path in sorted((ROOT / "bench/results").glob("*.json")):
        value = json.loads(path.read_text())
        emit(
            "benchmark_" + path.name,
            {key: value[key] for key in value if key != "records" and key != "leave_one_out"},
        )
        if "records" in value:
            hash_errors = []
            for record in value["records"]:
                canonical = {
                    "params": record["params"],
                    "mae_tune": record["mae_tune"],
                    "mean_i_star": record["mean_i_star"],
                    "zero_i_star_count": record["zero_i_star_count"],
                    "b3_pass": record["b3_persistent_hazard_pass"],
                    "b9_pass": record["b9_entropy_floor_pass"],
                }
                digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
                if digest != record["sha256"]:
                    hash_errors.append(record["params"])
            eligible = [
                r
                for r in value["records"]
                if r["b3_persistent_hazard_pass"] and r["b9_entropy_floor_pass"]
            ]
            chosen = min(
                eligible,
                key=lambda r: (
                    r["mae_tune"],
                    -r["params"]["h_min"],
                    r["params"]["tau_max"],
                    r["params"]["p"],
                    r["params"]["eps"],
                ),
            )
            emit(
                "sweep_record_self_consistency",
                {
                    "count": len(value["records"]),
                    "hash_errors": hash_errors,
                    "selection_matches": chosen == value["sweet_spot"],
                },
            )
    emit("parameter_grid_count", len(build_128_parameter_grid()))
    emit("EXIT_CODE", 0)


if __name__ == "__main__":
    main()
