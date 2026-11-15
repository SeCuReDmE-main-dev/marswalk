"""Phase 4 Obstacle-Aware Anisotropic 8-Connected A*, Supercover & Cost-Guarded String-Pull (`M2`).

Enforces CTO rules (`F1`, `H1`, `H2`, `H3`, `C4`, `C5`, `C6a` & Missing Angles):
1. Dynamic `cos(phi_c)` ground-metric scaling (`C6a`): East-West step is computed from
   `manifest.bbox` center latitude (`cos(18.46335 deg) = 0.948526`), decomposing terrain
   gradient `(gx, gy)` along segment unit ground heading `u_hat = (ux, uy)` into:
   - Longitudinal slope `theta_parallel = atan(|gx*ux + gy*uy|)`
   - Cross-slope `theta_perp = atan(|gx*uy - gy*ux|)`
2. Official `EVA-EXP-0042 Rev B` (p. 38) limit (`F1`): `20.0 deg` covers walking up, down,
   AND across slopes (`max(theta_parallel, theta_perp) > 20.0 deg -> blocked`). The `15.0 deg`
   cross-slope comfort threshold (`CAUTION`) is documented as an internal `DERIVED` margin.
3. Exact mathematical admissibility (`C4`, `H3`): `tobler_xeva_kmh(grade)` attains its global
   supremum `V_MAX_XEVA_KMH = 2.4 km/h` (`0.666667 m/s`) at `-5%` downhill (`grade = -0.05`),
   NOT `2.0 km/h` on flat ground. Using `V_MAX_XEVA_M_S = 2.4 / 3.6` makes the Euclidean
   heuristic `h(n) = dist_ground_m / V_MAX_XEVA_M_S` strictly admissible and consistent for
   `heuristic_weight = 1.0`.
4. Bounds-safe Amanatides-Woo supercover (`H3`): checks `0 <= r < rows and 0 <= c < cols`
   before every lookup (including corner touches), preventing `-1` negative index wraparound.
5. Measured string-pulling cost guard (`H2`): accepts line-of-sight shortcut `p_i -> p_j` iff
   supercover is unblocked AND measured segment integral cost `C_seg <= g(p_j) - g(p_i) + 1e-6`.
6. Emergency SPE rule (`C5`): under `spe_alert=True`, sets all risk/refuge biases to `0.0` so
   egress minimizes pure physical walking time back to the rover/habitat.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from marswalk.contracts.models import VerdictLiteral
from marswalk.engine.eva_human_rf import tobler_xeva_kmh
from marswalk.engine.obstacles_m1 import EVA_SUIT_MAX_SLOPE_DEG, PlannerGrid10m

INTERNAL_CROSS_SLOPE_CAUTION_DEG: float = 15.0
# Exact global supremum of `tobler_xeva_kmh(grade, sand_penalty=1.0)` at `grade = -0.05` (`C4`)
V_MAX_XEVA_KMH: float = tobler_xeva_kmh(-0.05, sand_penalty=1.0)  # 2.4000 km/h
V_MAX_XEVA_M_S: float = V_MAX_XEVA_KMH / 3.6  # 0.6666666666666666 m/s

_NEIGHBORS_8: tuple[tuple[int, int], ...] = (
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
    (-1, -1),
    (-1, 1),
    (1, -1),
    (1, 1),
)


@dataclass(frozen=True)
class StringPullAudit:
    """Measured audit counters for post-A* cost-guarded string-pulling (`H2`)."""

    candidates_tested: int
    accepted_count: int
    rejected_by_obstacle_count: int
    rejected_by_cost_guard_count: int
    raw_cost_s: float
    smoothed_cost_s: float


@dataclass(frozen=True)
class PlannedSegmentPlanResult:
    """Result of planning an obstacle-avoiding route across `PlannerGrid10m`."""

    reachable: bool
    coordinates: list[tuple[float, float]]
    raw_grid_path: list[tuple[int, int]]
    smoothed_grid_path: list[tuple[int, int]]
    total_distance_m: float
    pure_walking_time_s: float
    risk_weighted_cost_s: float
    max_longitudinal_slope_deg: float
    max_cross_slope_deg: float
    caution_cells_touched: int
    cells_expanded: int
    optimality_guarantee: str
    verdict: VerdictLiteral
    reasons: list[str]
    string_pull_audit: StringPullAudit


def decompose_anisotropic_slopes(
    gx: float,
    gy: float,
    ux_ground: float,
    uy_ground: float,
) -> tuple[float, float, float, float]:
    """Decompose metric terrain gradient `(gx, gy)` along unit ground heading `(ux, uy)`.

    Returns `(grade_parallel_signed, grade_cross_abs, slope_parallel_deg, slope_cross_deg)`.
    Note: `ux_ground` is positive East, `uy_ground` is positive North (`dr < 0 -> uy > 0`).
    """
    norm = math.hypot(ux_ground, uy_ground)
    if norm <= 1e-12:
        mag = math.hypot(gx, gy)
        ang = math.degrees(math.atan(mag))
        return (0.0, mag, 0.0, ang)
    ux = ux_ground / norm
    uy = uy_ground / norm
    grade_par = gx * ux + gy * uy
    grade_cross = abs(gx * uy - gy * ux)
    theta_par = math.degrees(math.atan(abs(grade_par)))
    theta_cross = math.degrees(math.atan(grade_cross))
    return (grade_par, grade_cross, theta_par, theta_cross)


def anisotropic_walking_speed_m_s(
    grade_parallel: float,
    grade_cross: float,
    sand_penalty: float = 1.0,
) -> float:
    """Compute suited walking speed (m/s), strictly bounded above by `V_MAX_XEVA_M_S` (`C4`)."""
    v_kmh = tobler_xeva_kmh(grade_parallel, sand_penalty=sand_penalty)
    cross_factor = 1.0 / (1.0 + 0.60 * (grade_cross * grade_cross))
    v_ms = (v_kmh / 3.6) * cross_factor
    return max(0.04, min(V_MAX_XEVA_M_S, v_ms))


def in_grid_bounds(r: int, c: int, rows: int, cols: int) -> bool:
    """Explicit non-negative bounds check preventing Python/NumPy `-1` index wraparound (`H3`)."""
    return 0 <= r < rows and 0 <= c < cols


def supercover_grid_cells(
    rows: int,
    cols: int,
    r0: int,
    c0: int,
    r1: int,
    c1: int,
    *,
    blocked_flat: list[bool] | None = None,
) -> tuple[bool, list[tuple[int, int]]]:
    """Traverse all grid cells touched by center-to-center segment `(r0, c0) -> (r1, c1)` (`H3`).

    Returns `(all_in_bounds, cells)`. If either endpoint or any corner touch falls outside
    `[0, rows) x [0, cols)` (or hits `blocked_flat`), returns `(False, ...)` immediately.
    """
    if not (in_grid_bounds(r0, c0, rows, cols) and in_grid_bounds(r1, c1, rows, cols)):
        return (False, [])
    if blocked_flat is not None and (blocked_flat[r0 * cols + c0] or blocked_flat[r1 * cols + c1]):
        return (False, [])

    visited: list[tuple[int, int]] = [(r0, c0)]
    if r0 == r1 and c0 == c1:
        return (True, visited)

    u0, v0 = float(c0) + 0.5, float(r0) + 0.5
    u1, v1 = float(c1) + 0.5, float(r1) + 0.5
    du = u1 - u0
    dv = v1 - v0

    c = c0
    r = r0
    step_c = 1 if du > 0.0 else (-1 if du < 0.0 else 0)
    step_r = 1 if dv > 0.0 else (-1 if dv < 0.0 else 0)

    t_delta_c = abs(1.0 / du) if abs(du) > 1e-12 else float("inf")
    t_delta_r = abs(1.0 / dv) if abs(dv) > 1e-12 else float("inf")
    t_max_c = (0.5 / abs(du)) if step_c != 0 else float("inf")
    t_max_r = (0.5 / abs(dv)) if step_r != 0 else float("inf")

    def _append_checked(rr: int, cc: int) -> bool:
        if not in_grid_bounds(rr, cc, rows, cols):
            return False
        if blocked_flat is not None and blocked_flat[rr * cols + cc]:
            return False
        if visited[-1] != (rr, cc):
            visited.append((rr, cc))
        return True

    max_iters = 2 * (abs(r1 - r0) + abs(c1 - c0)) + 4
    corner_eps = 1e-9
    for _ in range(max_iters):
        if r == r1 and c == c1:
            break
        if abs(t_max_c - t_max_r) <= corner_eps:
            # Corner crossing: include both orthogonal cells with explicit bounds check (`H3`)
            if not _append_checked(r, c + step_c):
                return (False, visited)
            if not _append_checked(r + step_r, c):
                return (False, visited)
            c += step_c
            r += step_r
            t_max_c += t_delta_c
            t_max_r += t_delta_r
            if not _append_checked(r, c):
                return (False, visited)
        elif t_max_c < t_max_r:
            c += step_c
            t_max_c += t_delta_c
            if not _append_checked(r, c):
                return (False, visited)
        else:
            r += step_r
            t_max_r += t_delta_r
            if not _append_checked(r, c):
                return (False, visited)

    if visited[-1] != (r1, c1):
        if not _append_checked(r1, c1):
            return (False, visited)
    return (True, visited)


def _cell_step_cost_s(
    grid: PlannerGrid10m,
    r_a: int,
    c_a: int,
    r_b: int,
    c_b: int,
    *,
    alpha_slope: float = 1.2,
    gamma_risk: float = 1.4,
    pure_time_only: bool = False,
) -> tuple[bool, float, float, float, float]:
    """Compute dimensionally homogeneous edge cost (s) between two grid cells (`H3`, `C4`).

    Returns `(valid, weighted_cost_s, pure_dt_s, theta_par_deg, theta_cross_deg)`.
    """
    if not (
        in_grid_bounds(r_a, c_a, grid.rows, grid.cols)
        and in_grid_bounds(r_b, c_b, grid.rows, grid.cols)
    ):
        return (False, float("inf"), float("inf"), 90.0, 90.0)
    if grid.blocked_mask[r_a, c_a] or grid.blocked_mask[r_b, c_b]:
        return (False, float("inf"), float("inf"), 90.0, 90.0)

    # Diagonal step corner-clipping guard (supercover consistency on 1-step diagonal moves)
    if r_a != r_b and c_a != c_b:
        if grid.blocked_mask[r_a, c_b] or grid.blocked_mask[r_b, c_a]:
            return (False, float("inf"), float("inf"), 90.0, 90.0)

    dx_m = (c_b - c_a) * grid.step_x_ground_m
    dy_north_m = -(r_b - r_a) * grid.step_y_ground_m
    dist_m = math.hypot(dx_m, dy_north_m)
    if dist_m <= 1e-9:
        return (True, 0.0, 0.0, 0.0, 0.0)

    gx = 0.5 * float(grid.grad_x[r_a, c_a] + grid.grad_x[r_b, c_b])
    gy = 0.5 * float(grid.grad_y[r_a, c_a] + grid.grad_y[r_b, c_b])
    g_par, g_cross, theta_par, theta_cross = decompose_anisotropic_slopes(gx, gy, dx_m, dy_north_m)

    # Official NASA EVA-EXP-0042 Rev B p. 38 limit: 20 deg up, down, AND across (`F1`)
    if max(theta_par, theta_cross) > EVA_SUIT_MAX_SLOPE_DEG:
        return (False, float("inf"), float("inf"), theta_par, theta_cross)

    v_ms = anisotropic_walking_speed_m_s(g_par, g_cross)
    dt_s = dist_m / v_ms

    if pure_time_only:
        return (True, dt_s, dt_s, theta_par, theta_cross)

    norm_slope = max(theta_par, theta_cross) / EVA_SUIT_MAX_SLOPE_DEG
    risk_mid = 0.5 * float(grid.risk_penalty_01[r_a, c_a] + grid.risk_penalty_01[r_b, c_b])
    cross_caution = (
        0.45 * ((theta_cross - INTERNAL_CROSS_SLOPE_CAUTION_DEG) / 5.0)
        if theta_cross > INTERNAL_CROSS_SLOPE_CAUTION_DEG
        else 0.0
    )
    caution_pen = 0.20 if (grid.caution_mask[r_a, c_a] or grid.caution_mask[r_b, c_b]) else 0.0
    multiplier = (
        1.0 + alpha_slope * norm_slope + gamma_risk * risk_mid + cross_caution + caution_pen
    )
    return (True, dt_s * multiplier, dt_s, theta_par, theta_cross)


def evaluate_shortcut_segment_cost_s(
    grid: PlannerGrid10m,
    r0: int,
    c0: int,
    r1: int,
    c1: int,
    *,
    alpha_slope: float = 1.2,
    gamma_risk: float = 1.4,
    pure_time_only: bool = False,
    _flat: tuple[list[bool], list[bool], list[float], list[float], list[float]] | None = None,
) -> tuple[bool, float, float, float, float, int]:
    """Evaluate exact line-integral cost along supercover of shortcut `(r0,c0)->(r1,c1)` (`H2`)."""
    cols = grid.cols
    if _flat is not None:
        blocked_f, caution_f, gx_f, gy_f, risk_f = _flat
    else:
        blocked_f = grid.blocked_mask.ravel().tolist()
        caution_f = grid.caution_mask.ravel().tolist()
        gx_f = grid.grad_x.ravel().tolist()
        gy_f = grid.grad_y.ravel().tolist()
        risk_f = grid.risk_penalty_01.ravel().tolist()

    ok_bounds, cells = supercover_grid_cells(
        grid.rows, cols, r0, c0, r1, c1, blocked_flat=blocked_f
    )
    if not ok_bounds or not cells:
        return (False, float("inf"), float("inf"), 90.0, 90.0, 0)

    dx_m = (c1 - c0) * grid.step_x_ground_m
    dy_north_m = -(r1 - r0) * grid.step_y_ground_m
    total_dist_m = math.hypot(dx_m, dy_north_m)
    if total_dist_m <= 1e-9:
        return (True, 0.0, 0.0, 0.0, 0.0, 0)

    ds_m = total_dist_m / float(len(cells))
    ux = dx_m / total_dist_m
    uy = dy_north_m / total_dist_m
    total_weighted_s = 0.0
    total_dt_s = 0.0
    max_par = 0.0
    max_cross = 0.0
    caution_cnt = 0

    for rr, cc in cells:
        idx = rr * cols + cc
        gx = gx_f[idx]
        gy = gy_f[idx]
        g_par = gx * ux + gy * uy
        g_cross = abs(gx * uy - gy * ux)
        theta_par = math.degrees(math.atan(abs(g_par)))
        theta_cross = math.degrees(math.atan(g_cross))
        theta_max = theta_par if theta_par >= theta_cross else theta_cross
        if theta_max > EVA_SUIT_MAX_SLOPE_DEG:
            return (False, float("inf"), float("inf"), theta_par, theta_cross, 0)

        if theta_par > max_par:
            max_par = theta_par
        if theta_cross > max_cross:
            max_cross = theta_cross
        is_caut = caution_f[idx]
        if is_caut or theta_cross > INTERNAL_CROSS_SLOPE_CAUTION_DEG:
            caution_cnt += 1

        v_ms = anisotropic_walking_speed_m_s(g_par, g_cross)
        dt_s = ds_m / v_ms
        total_dt_s += dt_s
        if pure_time_only:
            total_weighted_s += dt_s
        else:
            norm_slope = theta_max / EVA_SUIT_MAX_SLOPE_DEG
            risk_v = risk_f[idx]
            cross_caution = (
                0.45 * ((theta_cross - INTERNAL_CROSS_SLOPE_CAUTION_DEG) / 5.0)
                if theta_cross > INTERNAL_CROSS_SLOPE_CAUTION_DEG
                else 0.0
            )
            caution_pen = 0.20 if is_caut else 0.0
            mult = (
                1.0 + alpha_slope * norm_slope + gamma_risk * risk_v + cross_caution + caution_pen
            )
            total_weighted_s += dt_s * mult

    return (True, total_weighted_s, total_dt_s, max_par, max_cross, caution_cnt)


def _astar_single_leg(
    grid: PlannerGrid10m,
    start_rc: tuple[int, int],
    goal_rc: tuple[int, int],
    *,
    heuristic_weight: float = 1.0,
    alpha_slope: float = 1.2,
    gamma_risk: float = 1.4,
    pure_time_only: bool = False,
) -> tuple[bool, list[tuple[int, int]], list[float], int]:
    """Run 8-connected A* with strictly admissible Euclidean heuristic `d / V_MAX_XEVA_M_S`."""
    rows = grid.rows
    cols = grid.cols
    sr, sc = start_rc
    gr, gc = goal_rc
    if not (in_grid_bounds(sr, sc, rows, cols) and in_grid_bounds(gr, gc, rows, cols)):
        return (False, [], [], 0)

    blocked_f: list[bool] = grid.blocked_mask.ravel().tolist()
    s_idx = sr * cols + sc
    g_idx = gr * cols + gc
    if blocked_f[s_idx] or blocked_f[g_idx]:
        return (False, [], [], 0)

    caution_f: list[bool] = grid.caution_mask.ravel().tolist()
    gx_f: list[float] = grid.grad_x.ravel().tolist()
    gy_f: list[float] = grid.grad_y.ravel().tolist()
    risk_f: list[float] = grid.risk_penalty_01.ravel().tolist()

    step_x = grid.step_x_ground_m
    step_y = grid.step_y_ground_m
    w_h = max(0.0, float(heuristic_weight))
    inv_vmax = 1.0 / V_MAX_XEVA_M_S

    # Precompute heading vectors and step lengths for the 8 neighbors
    neighbor_specs: list[tuple[int, int, float, float, float, bool]] = []
    for dr, dc in _NEIGHBORS_8:
        dx_m = dc * step_x
        dy_m = -dr * step_y
        dist_m = math.hypot(dx_m, dy_m)
        neighbor_specs.append((dr, dc, dist_m, dx_m / dist_m, dy_m / dist_m, dr != 0 and dc != 0))

    inf = float("inf")
    n_total = rows * cols
    g_score = [inf] * n_total
    came_from = [-1] * n_total
    closed = [False] * n_total

    g_score[s_idx] = 0.0
    h0 = w_h * math.hypot((gc - sc) * step_x, (gr - sr) * step_y) * inv_vmax
    heap: list[tuple[float, int, int]] = [(h0, 0, s_idx)]
    tie = 0
    expanded = 0

    while heap:
        _, _, cur_idx = heapq.heappop(heap)
        if closed[cur_idx]:
            continue
        closed[cur_idx] = True
        expanded += 1

        if cur_idx == g_idx:
            rev_indices: list[int] = [g_idx]
            walk = g_idx
            while came_from[walk] != -1:
                walk = came_from[walk]
                rev_indices.append(walk)
            rev_indices.reverse()
            path = [(idx // cols, idx % cols) for idx in rev_indices]
            cum_g = [g_score[idx] for idx in rev_indices]
            return (True, path, cum_g, expanded)

        cr = cur_idx // cols
        cc = cur_idx % cols
        cur_g = g_score[cur_idx]
        gx_a = gx_f[cur_idx]
        gy_a = gy_f[cur_idx]
        risk_a = risk_f[cur_idx]
        caut_a = caution_f[cur_idx]

        for dr, dc, dist_m, ux, uy, is_diag in neighbor_specs:
            nr = cr + dr
            nc = cc + dc
            if nr < 0 or nr >= rows or nc < 0 or nc >= cols:
                continue
            n_idx = nr * cols + nc
            if closed[n_idx] or blocked_f[n_idx]:
                continue
            if is_diag and (blocked_f[cr * cols + nc] or blocked_f[nr * cols + cc]):
                continue

            gx = 0.5 * (gx_a + gx_f[n_idx])
            gy = 0.5 * (gy_a + gy_f[n_idx])
            g_par = gx * ux + gy * uy
            g_cross = abs(gx * uy - gy * ux)
            theta_par = math.degrees(math.atan(abs(g_par)))
            theta_cross = math.degrees(math.atan(g_cross))
            theta_max = theta_par if theta_par >= theta_cross else theta_cross
            if theta_max > EVA_SUIT_MAX_SLOPE_DEG:
                continue

            v_ms = anisotropic_walking_speed_m_s(g_par, g_cross)
            dt_s = dist_m / v_ms
            if pure_time_only:
                edge_s = dt_s
            else:
                norm_slope = theta_max / EVA_SUIT_MAX_SLOPE_DEG
                risk_mid = 0.5 * (risk_a + risk_f[n_idx])
                cross_caution = (
                    0.45 * ((theta_cross - INTERNAL_CROSS_SLOPE_CAUTION_DEG) / 5.0)
                    if theta_cross > INTERNAL_CROSS_SLOPE_CAUTION_DEG
                    else 0.0
                )
                caution_pen = 0.20 if (caut_a or caution_f[n_idx]) else 0.0
                edge_s = dt_s * (
                    1.0
                    + alpha_slope * norm_slope
                    + gamma_risk * risk_mid
                    + cross_caution
                    + caution_pen
                )

            cand_g = cur_g + edge_s
            if cand_g < g_score[n_idx] - 1e-12:
                g_score[n_idx] = cand_g
                came_from[n_idx] = cur_idx
                tie += 1
                h_n = w_h * math.hypot((gc - nc) * step_x, (gr - nr) * step_y) * inv_vmax
                heapq.heappush(heap, (cand_g + h_n, tie, n_idx))

    return (False, [], [], expanded)


def string_pull_with_cost_guard(
    grid: PlannerGrid10m,
    raw_path: list[tuple[int, int]],
    cum_g_s: list[float],
    *,
    alpha_slope: float = 1.2,
    gamma_risk: float = 1.4,
    pure_time_only: bool = False,
    cost_eps_s: float = 1e-6,
    max_lookahead_steps: int = 48,
) -> tuple[list[tuple[int, int]], StringPullAudit]:
    """Smooth an 8-connected A* path only if supercover is clear AND cost never rises (`H2`)."""
    if len(raw_path) <= 2:
        raw_total = cum_g_s[-1] if cum_g_s else 0.0
        return (
            list(raw_path),
            StringPullAudit(
                candidates_tested=0,
                accepted_count=0,
                rejected_by_obstacle_count=0,
                rejected_by_cost_guard_count=0,
                raw_cost_s=round(raw_total, 6),
                smoothed_cost_s=round(raw_total, 6),
            ),
        )

    flat_cache = (
        grid.blocked_mask.ravel().tolist(),
        grid.caution_mask.ravel().tolist(),
        grid.grad_x.ravel().tolist(),
        grid.grad_y.ravel().tolist(),
        grid.risk_penalty_01.ravel().tolist(),
    )

    smoothed: list[tuple[int, int]] = [raw_path[0]]
    candidates_tested = 0
    accepted_count = 0
    rej_obs = 0
    rej_cost = 0
    smoothed_total_s = 0.0

    idx = 0
    n = len(raw_path)
    while idx < n - 1:
        chosen_j = idx + 1
        _, chosen_seg_s, _, _, _ = _cell_step_cost_s(
            grid,
            raw_path[idx][0],
            raw_path[idx][1],
            raw_path[idx + 1][0],
            raw_path[idx + 1][1],
            alpha_slope=alpha_slope,
            gamma_risk=gamma_risk,
            pure_time_only=pure_time_only,
        )

        upper_j = min(n - 1, idx + max(2, int(max_lookahead_steps)))
        for cand_j in range(upper_j, idx + 1, -1):
            candidates_tested += 1
            r0, c0 = raw_path[idx]
            r1, c1 = raw_path[cand_j]
            ok_seg, seg_cost_s, _, _, _, _ = evaluate_shortcut_segment_cost_s(
                grid,
                r0,
                c0,
                r1,
                c1,
                alpha_slope=alpha_slope,
                gamma_risk=gamma_risk,
                pure_time_only=pure_time_only,
                _flat=flat_cache,
            )
            if not ok_seg:
                rej_obs += 1
                continue

            subpath_budget_s = cum_g_s[cand_j] - cum_g_s[idx]
            if seg_cost_s <= subpath_budget_s + cost_eps_s:
                accepted_count += 1
                chosen_j = cand_j
                chosen_seg_s = seg_cost_s
                break
            rej_cost += 1

        smoothed.append(raw_path[chosen_j])
        smoothed_total_s += chosen_seg_s
        idx = chosen_j

    raw_total = cum_g_s[-1]
    return (
        smoothed,
        StringPullAudit(
            candidates_tested=candidates_tested,
            accepted_count=accepted_count,
            rejected_by_obstacle_count=rej_obs,
            rejected_by_cost_guard_count=rej_cost,
            raw_cost_s=round(raw_total, 6),
            smoothed_cost_s=round(smoothed_total_s, 6),
        ),
    )


def _lonlat_to_grid_rc(grid: PlannerGrid10m, lon: float, lat: float) -> tuple[bool, int, int]:
    min_lon, min_lat, max_lon, max_lat = grid.bbox
    eps = 1e-6
    if not (min_lon - eps <= lon <= max_lon + eps and min_lat - eps <= lat <= max_lat + eps):
        return (False, -1, -1)
    u = (lon - min_lon) / max(1e-12, max_lon - min_lon) * float(grid.cols)
    v = (max_lat - lat) / max(1e-12, max_lat - min_lat) * float(grid.rows)
    c = max(0, min(grid.cols - 1, int(math.floor(u))))
    r = max(0, min(grid.rows - 1, int(math.floor(v))))
    return (True, r, c)


def _grid_rc_to_lonlat(grid: PlannerGrid10m, r: int, c: int) -> tuple[float, float]:
    min_lon, min_lat, max_lon, max_lat = grid.bbox
    lon = min_lon + ((float(c) + 0.5) / float(grid.cols)) * (max_lon - min_lon)
    lat = max_lat - ((float(r) + 0.5) / float(grid.rows)) * (max_lat - min_lat)
    return (round(lon, 6), round(lat, 6))


def _snap_to_nearest_unblocked(
    grid: PlannerGrid10m,
    r0: int,
    c0: int,
    max_radius_cells: int = 3,
) -> tuple[int, int] | None:
    if not grid.blocked_mask[r0, c0]:
        return (r0, c0)
    best: tuple[float, int, int] | None = None
    for dr in range(-max_radius_cells, max_radius_cells + 1):
        for dc in range(-max_radius_cells, max_radius_cells + 1):
            nr, nc = r0 + dr, c0 + dc
            if in_grid_bounds(nr, nc, grid.rows, grid.cols) and not grid.blocked_mask[nr, nc]:
                d2 = float(dr * dr + dc * dc)
                if best is None or d2 < best[0]:
                    best = (d2, nr, nc)
    return (best[1], best[2]) if best is not None else None


def plan_obstacle_aware_route(
    grid: PlannerGrid10m,
    waypoints_lonlat: list[tuple[float, float]],
    *,
    heuristic_weight: float = 1.0,
    spe_alert: bool = False,
    enable_string_pull: bool = True,
) -> PlannedSegmentPlanResult:
    """Plan a multi-waypoint obstacle-avoiding EVA route on `PlannerGrid10m` (`M2`)."""
    w_h = max(0.0, float(heuristic_weight))
    if abs(w_h - 1.0) <= 1e-9 or w_h < 1.0:
        opt_label = "exact_admissible"
    else:
        subopt_pct = (w_h - 1.0) * 100.0
        opt_label = f"bounded_suboptimal_{subopt_pct:.1f}pct"

    if len(waypoints_lonlat) < 2:
        return PlannedSegmentPlanResult(
            reachable=False,
            coordinates=[],
            raw_grid_path=[],
            smoothed_grid_path=[],
            total_distance_m=0.0,
            pure_walking_time_s=0.0,
            risk_weighted_cost_s=0.0,
            max_longitudinal_slope_deg=0.0,
            max_cross_slope_deg=0.0,
            caution_cells_touched=0,
            cells_expanded=0,
            optimality_guarantee=opt_label,
            verdict="NO_GO",
            reasons=["At least 2 waypoints are required for route planning."],
            string_pull_audit=StringPullAudit(0, 0, 0, 0, 0.0, 0.0),
        )

    rc_stops: list[tuple[int, int]] = []
    for lon, lat in waypoints_lonlat:
        ok_b, r, c = _lonlat_to_grid_rc(grid, lon, lat)
        if not ok_b:
            return PlannedSegmentPlanResult(
                reachable=False,
                coordinates=[],
                raw_grid_path=[],
                smoothed_grid_path=[],
                total_distance_m=0.0,
                pure_walking_time_s=0.0,
                risk_weighted_cost_s=0.0,
                max_longitudinal_slope_deg=0.0,
                max_cross_slope_deg=0.0,
                caution_cells_touched=0,
                cells_expanded=0,
                optimality_guarantee=opt_label,
                verdict="NO_GO",
                reasons=[f"Waypoint ({lon:.6f}, {lat:.6f}) is out of bbox {list(grid.bbox)}."],
                string_pull_audit=StringPullAudit(0, 0, 0, 0, 0.0, 0.0),
            )
        snapped = _snap_to_nearest_unblocked(grid, r, c, max_radius_cells=0)
        if snapped is None:
            return PlannedSegmentPlanResult(
                reachable=False,
                coordinates=[],
                raw_grid_path=[],
                smoothed_grid_path=[],
                total_distance_m=0.0,
                pure_walking_time_s=0.0,
                risk_weighted_cost_s=0.0,
                max_longitudinal_slope_deg=0.0,
                max_cross_slope_deg=0.0,
                caution_cells_touched=0,
                cells_expanded=0,
                optimality_guarantee=opt_label,
                verdict="NO_GO",
                reasons=[
                    f"Waypoint ({lon:.6f}, {lat:.6f}) lies inside a blocked obstacle/scarp cell."
                ],
                string_pull_audit=StringPullAudit(0, 0, 0, 0, 0.0, 0.0),
            )
        rc_stops.append(snapped)

    # Under `spe_alert=True`, plan fastest return to origin (`rc_stops[0]`) from current position
    # (`rc_stops[-1]`) with ZERO refuge/risk bias (`pure_time_only=True`, `C5`).
    pure_time = bool(spe_alert)
    if spe_alert:
        rc_stops = [rc_stops[-1], rc_stops[0]]

    full_raw: list[tuple[int, int]] = []
    full_smoothed: list[tuple[int, int]] = []
    total_expanded = 0
    cand_tested = 0
    acc_cnt = 0
    rej_obs = 0
    rej_cost = 0
    raw_cost_sum = 0.0
    smooth_cost_sum = 0.0

    for leg_idx in range(len(rc_stops) - 1):
        ok_leg, leg_raw, leg_g, exp_n = _astar_single_leg(
            grid,
            rc_stops[leg_idx],
            rc_stops[leg_idx + 1],
            heuristic_weight=w_h,
            pure_time_only=pure_time,
        )
        total_expanded += exp_n
        if not ok_leg:
            return PlannedSegmentPlanResult(
                reachable=False,
                coordinates=[],
                raw_grid_path=[],
                smoothed_grid_path=[],
                total_distance_m=0.0,
                pure_walking_time_s=0.0,
                risk_weighted_cost_s=0.0,
                max_longitudinal_slope_deg=0.0,
                max_cross_slope_deg=0.0,
                caution_cells_touched=0,
                cells_expanded=total_expanded,
                optimality_guarantee=opt_label,
                verdict="NO_GO",
                reasons=["No obstacle-free path <= 20.0 deg exists between requested waypoints."],
                string_pull_audit=StringPullAudit(0, 0, 0, 0, 0.0, 0.0),
            )

        if enable_string_pull:
            leg_sm, audit = string_pull_with_cost_guard(
                grid, leg_raw, leg_g, pure_time_only=pure_time
            )
        else:
            leg_sm = list(leg_raw)
            audit = StringPullAudit(0, 0, 0, 0, leg_g[-1], leg_g[-1])

        cand_tested += audit.candidates_tested
        acc_cnt += audit.accepted_count
        rej_obs += audit.rejected_by_obstacle_count
        rej_cost += audit.rejected_by_cost_guard_count
        raw_cost_sum += audit.raw_cost_s
        smooth_cost_sum += audit.smoothed_cost_s

        if not full_raw:
            full_raw.extend(leg_raw)
        else:
            full_raw.extend(leg_raw[1:])
        if not full_smoothed:
            full_smoothed.extend(leg_sm)
        else:
            full_smoothed.extend(leg_sm[1:])

    # Measure final smoothed polyline physical telemetry
    total_dist_m = 0.0
    total_dt_s = 0.0
    max_par_deg = 0.0
    max_cross_deg = 0.0
    caution_cells = 0

    for idx in range(len(full_smoothed) - 1):
        r0, c0 = full_smoothed[idx]
        r1, c1 = full_smoothed[idx + 1]
        dx_m = (c1 - c0) * grid.step_x_ground_m
        dy_m = -(r1 - r0) * grid.step_y_ground_m
        total_dist_m += math.hypot(dx_m, dy_m)
        _, _, seg_dt_s, seg_par, seg_cross, seg_caut = evaluate_shortcut_segment_cost_s(
            grid, r0, c0, r1, c1, pure_time_only=pure_time
        )
        total_dt_s += seg_dt_s
        max_par_deg = max(max_par_deg, seg_par)
        max_cross_deg = max(max_cross_deg, seg_cross)
        caution_cells += seg_caut

    coords = [_grid_rc_to_lonlat(grid, r, c) for r, c in full_smoothed]
    reasons: list[str] = []
    if spe_alert:
        verdict: VerdictLiteral = "NO_GO"
        reasons.append(
            "Solar Particle Event (SPE) alert active: NO_GO abort; returning fastest safe "
            "egress path to rover/habitat with zero topographic refuge detour."
        )
    elif (
        caution_cells > 0 or max_cross_deg > INTERNAL_CROSS_SLOPE_CAUTION_DEG or max_par_deg >= 10.0
    ):
        verdict = "CAUTION"
        reasons.append(
            f"Obstacle-free path planned with moderate slope/caution margin "
            f"(max longitudinal {max_par_deg:.1f} deg, max cross-slope {max_cross_deg:.1f} deg)."
        )
    else:
        verdict = "GO"
        reasons.append(
            "Obstacle-free path avoids all >= 4 m formations and scarps within NASA xEVA limits."
        )

    return PlannedSegmentPlanResult(
        reachable=True,
        coordinates=coords,
        raw_grid_path=full_raw,
        smoothed_grid_path=full_smoothed,
        total_distance_m=round(total_dist_m, 2),
        pure_walking_time_s=round(total_dt_s, 2),
        risk_weighted_cost_s=round(smooth_cost_sum, 4),
        max_longitudinal_slope_deg=round(max_par_deg, 2),
        max_cross_slope_deg=round(max_cross_deg, 2),
        caution_cells_touched=caution_cells,
        cells_expanded=total_expanded,
        optimality_guarantee=opt_label,
        verdict=verdict,
        reasons=reasons,
        string_pull_audit=StringPullAudit(
            candidates_tested=cand_tested,
            accepted_count=acc_cnt,
            rejected_by_obstacle_count=rej_obs,
            rejected_by_cost_guard_count=rej_cost,
            raw_cost_s=round(raw_cost_sum, 6),
            smoothed_cost_s=round(smooth_cost_sum, 6),
        ),
    )
