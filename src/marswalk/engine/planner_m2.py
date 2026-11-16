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

import hashlib
import heapq
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from marswalk.contracts.models import VerdictLiteral
from marswalk.engine.eva_human_rf import tobler_xeva_kmh
from marswalk.engine.obstacles_m1 import EVA_SUIT_MAX_SLOPE_DEG, PlannerGrid10m

INTERNAL_CROSS_SLOPE_CAUTION_DEG: float = 15.0
# Exact global supremum of `tobler_xeva_kmh(grade, sand_penalty=1.0)` at `grade = -0.05` (`C4`)
V_MAX_XEVA_KMH: float = tobler_xeva_kmh(-0.05, sand_penalty=1.0)  # 2.4000 km/h
V_MAX_XEVA_M_S: float = V_MAX_XEVA_KMH / 3.6  # 0.6666666666666666 m/s
_TAN_MAX_SLOPE_20: float = math.tan(math.radians(EVA_SUIT_MAX_SLOPE_DEG))
_TAN_CROSS_CAUTION_15: float = math.tan(math.radians(INTERNAL_CROSS_SLOPE_CAUTION_DEG))

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
    if not (0 <= r0 < rows and 0 <= c0 < cols and 0 <= r1 < rows and 0 <= c1 < cols):
        return (False, [])
    has_blocked = blocked_flat is not None
    if has_blocked and (
        blocked_flat[r0 * cols + c0] or blocked_flat[r1 * cols + c1]  # type: ignore[index]
    ):
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

    last_r = r0
    last_c = c0
    append = visited.append
    max_iters = 2 * (abs(r1 - r0) + abs(c1 - c0)) + 4
    corner_eps = 1e-9

    for _ in range(max_iters):
        if r == r1 and c == c1:
            break
        if abs(t_max_c - t_max_r) <= corner_eps:
            # Corner crossing: include both orthogonal cells with explicit bounds check (`H3`)
            nc1 = c + step_c
            if not (0 <= r < rows and 0 <= nc1 < cols):
                return (False, visited)
            if has_blocked and blocked_flat[r * cols + nc1]:  # type: ignore[index]
                return (False, visited)
            if r != last_r or nc1 != last_c:
                append((r, nc1))
                last_r = r
                last_c = nc1

            nr2 = r + step_r
            if not (0 <= nr2 < rows and 0 <= c < cols):
                return (False, visited)
            if has_blocked and blocked_flat[nr2 * cols + c]:  # type: ignore[index]
                return (False, visited)
            if nr2 != last_r or c != last_c:
                append((nr2, c))
                last_r = nr2
                last_c = c

            c = nc1
            r = nr2
            t_max_c += t_delta_c
            t_max_r += t_delta_r
            if not (0 <= r < rows and 0 <= c < cols):
                return (False, visited)
            if has_blocked and blocked_flat[r * cols + c]:  # type: ignore[index]
                return (False, visited)
            if r != last_r or c != last_c:
                append((r, c))
                last_r = r
                last_c = c
        elif t_max_c < t_max_r:
            c += step_c
            t_max_c += t_delta_c
            if not (0 <= c < cols):
                return (False, visited)
            if has_blocked and blocked_flat[r * cols + c]:  # type: ignore[index]
                return (False, visited)
            append((r, c))
            last_r = r
            last_c = c
        else:
            r += step_r
            t_max_r += t_delta_r
            if not (0 <= r < rows):
                return (False, visited)
            if has_blocked and blocked_flat[r * cols + c]:  # type: ignore[index]
                return (False, visited)
            append((r, c))
            last_r = r
            last_c = c

    if last_r != r1 or last_c != c1:
        if not (0 <= r1 < rows and 0 <= c1 < cols):
            return (False, visited)
        if has_blocked and blocked_flat[r1 * cols + c1]:  # type: ignore[index]
            return (False, visited)
        append((r1, c1))
    return (True, visited)


def _supercover_flat_indices(
    rows: int,
    cols: int,
    r0: int,
    c0: int,
    r1: int,
    c1: int,
    blocked_flat: list[bool],
) -> tuple[bool, list[int]]:
    """Fast flat-index variant of `supercover_grid_cells` avoiding tuple allocation (`H3`)."""
    if not (0 <= r0 < rows and 0 <= c0 < cols and 0 <= r1 < rows and 0 <= c1 < cols):
        return (False, [])
    idx0 = r0 * cols + c0
    idx1 = r1 * cols + c1
    if blocked_flat[idx0] or blocked_flat[idx1]:
        return (False, [])

    visited: list[int] = [idx0]
    if idx0 == idx1:
        return (True, visited)

    du = float(c1 - c0)
    dv = float(r1 - r0)
    c = c0
    r = r0
    step_c = 1 if du > 0.0 else (-1 if du < 0.0 else 0)
    step_r = 1 if dv > 0.0 else (-1 if dv < 0.0 else 0)
    step_idx_r = step_r * cols

    t_delta_c = abs(1.0 / du) if step_c != 0 else float("inf")
    t_delta_r = abs(1.0 / dv) if step_r != 0 else float("inf")
    t_max_c = (0.5 * t_delta_c) if step_c != 0 else float("inf")
    t_max_r = (0.5 * t_delta_r) if step_r != 0 else float("inf")

    cur_idx = idx0
    last_idx = idx0
    append = visited.append
    max_iters = 2 * (abs(r1 - r0) + abs(c1 - c0)) + 4
    corner_eps = 1e-9

    for _ in range(max_iters):
        if cur_idx == idx1:
            break
        diff = t_max_c - t_max_r
        if diff < -corner_eps:
            c += step_c
            cur_idx += step_c
            t_max_c += t_delta_c
            if not (0 <= c < cols) or blocked_flat[cur_idx]:
                return (False, visited)
            append(cur_idx)
            last_idx = cur_idx
        elif diff > corner_eps:
            r += step_r
            cur_idx += step_idx_r
            t_max_r += t_delta_r
            if not (0 <= r < rows) or blocked_flat[cur_idx]:
                return (False, visited)
            append(cur_idx)
            last_idx = cur_idx
        else:
            nc1 = c + step_c
            idx_c1 = cur_idx + step_c
            if not (0 <= r < rows and 0 <= nc1 < cols) or blocked_flat[idx_c1]:
                return (False, visited)
            if idx_c1 != last_idx:
                append(idx_c1)
                last_idx = idx_c1

            nr2 = r + step_r
            idx_r2 = cur_idx + step_idx_r
            if not (0 <= nr2 < rows and 0 <= c < cols) or blocked_flat[idx_r2]:
                return (False, visited)
            if idx_r2 != last_idx:
                append(idx_r2)
                last_idx = idx_r2

            c = nc1
            r = nr2
            cur_idx = r * cols + c
            t_max_c += t_delta_c
            t_max_r += t_delta_r
            if not (0 <= r < rows and 0 <= c < cols) or blocked_flat[cur_idx]:
                return (False, visited)
            if cur_idx != last_idx:
                append(cur_idx)
                last_idx = cur_idx

    if last_idx != idx1:
        if not (0 <= r1 < rows and 0 <= c1 < cols) or blocked_flat[idx1]:
            return (False, visited)
        append(idx1)
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
        blocked_f, caution_f, gx_f, gy_f, risk_f = _get_flat_grid_lists(grid)

    ok_bounds, cell_indices = _supercover_flat_indices(grid.rows, cols, r0, c0, r1, c1, blocked_f)
    if not ok_bounds or not cell_indices:
        return (False, float("inf"), float("inf"), 90.0, 90.0, 0)

    dx_m = (c1 - c0) * grid.step_x_ground_m
    dy_north_m = -(r1 - r0) * grid.step_y_ground_m
    total_dist_m = math.hypot(dx_m, dy_north_m)
    if total_dist_m <= 1e-9:
        return (True, 0.0, 0.0, 0.0, 0.0, 0)

    ds_m = total_dist_m / float(len(cell_indices))
    ux = dx_m / total_dist_m
    uy = dy_north_m / total_dist_m
    total_weighted_s = 0.0
    total_dt_s = 0.0
    max_abs_par = 0.0
    max_g_cross = 0.0
    caution_cnt = 0

    _atan = math.atan
    _degrees = math.degrees
    _exp = math.exp
    _isfinite = math.isfinite
    max_slope_deg = EVA_SUIT_MAX_SLOPE_DEG
    cross_caution_deg = INTERNAL_CROSS_SLOPE_CAUTION_DEG
    vmax = V_MAX_XEVA_M_S
    tan20 = _TAN_MAX_SLOPE_20
    tan15 = _TAN_CROSS_CAUTION_15

    for idx in cell_indices:
        gx = gx_f[idx]
        gy = gy_f[idx]
        g_par = gx * ux + gy * uy
        abs_g_par = -g_par if g_par < 0.0 else g_par
        g_cross = gx * uy - gy * ux
        if g_cross < 0.0:
            g_cross = -g_cross
        g_max = abs_g_par if abs_g_par >= g_cross else g_cross
        if not (g_max <= tan20):
            if not (_isfinite(gx) and _isfinite(gy)):
                return (False, float("inf"), float("inf"), 90.0, 90.0, 0)
            theta_par_bad = _degrees(_atan(abs_g_par))
            theta_cross_bad = _degrees(_atan(g_cross))
            if max(theta_par_bad, theta_cross_bad) > max_slope_deg:
                return (False, float("inf"), float("inf"), theta_par_bad, theta_cross_bad, 0)

        if abs_g_par > max_abs_par:
            max_abs_par = abs_g_par
        if g_cross > max_g_cross:
            max_g_cross = g_cross
        is_caut = caution_f[idx]
        over_tan15 = g_cross > tan15
        if is_caut or over_tan15:
            caution_cnt += 1

        gp_shift = g_par + 0.05
        if gp_shift < 0.0:
            gp_shift = -gp_shift
        base_kmh = 2.4 * _exp(-3.5 * gp_shift)
        if base_kmh < 0.15:
            base_kmh = 0.15
        v_ms = (base_kmh / 3.6) / (1.0 + 0.60 * (g_cross * g_cross))
        if v_ms < 0.04:
            v_ms = 0.04
        elif v_ms > vmax:
            v_ms = vmax

        dt_s = ds_m / v_ms
        total_dt_s += dt_s
        if pure_time_only:
            total_weighted_s += dt_s
        else:
            theta_max = _degrees(_atan(g_max))
            norm_slope = theta_max / max_slope_deg
            risk_v = risk_f[idx]
            if over_tan15:
                theta_cross = theta_max if g_max == g_cross else _degrees(_atan(g_cross))
                cross_caution = (
                    0.45 * ((theta_cross - cross_caution_deg) / 5.0)
                    if theta_cross > cross_caution_deg
                    else 0.0
                )
            else:
                cross_caution = 0.0
            caution_pen = 0.20 if is_caut else 0.0
            mult = (
                1.0 + alpha_slope * norm_slope + gamma_risk * risk_v + cross_caution + caution_pen
            )
            total_weighted_s += dt_s * mult

    if not _isfinite(total_weighted_s):
        return (False, float("inf"), float("inf"), 90.0, 90.0, 0)
    max_par = _degrees(_atan(max_abs_par))
    max_cross = _degrees(_atan(max_g_cross))
    return (True, total_weighted_s, total_dt_s, max_par, max_cross, caution_cnt)


def _grid_content_digest(grid: PlannerGrid10m) -> bytes:
    """Compute a fast 16-byte BLAKE2b fingerprint of all grid arrays for edge-table caching."""
    h = hashlib.blake2b(digest_size=16)
    h.update(np.ascontiguousarray(grid.blocked_mask, dtype=np.uint8).tobytes())
    h.update(np.ascontiguousarray(grid.caution_mask, dtype=np.uint8).tobytes())
    h.update(np.ascontiguousarray(grid.grad_x, dtype=np.float64).tobytes())
    h.update(np.ascontiguousarray(grid.grad_y, dtype=np.float64).tobytes())
    h.update(np.ascontiguousarray(grid.risk_penalty_01, dtype=np.float64).tobytes())
    return h.digest()


# Maps a content digest to the most recent grid arrays without holding unbounded references
_GRID_ARRAYS_BY_DIGEST: dict[
    bytes, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]
] = {}


@lru_cache(maxsize=12)
def _cached_directional_edge_tables(
    rows: int,
    cols: int,
    step_x: float,
    step_y: float,
    alpha_slope: float,
    gamma_risk: float,
    pure_time_only: bool,
    digest: bytes,
) -> tuple[tuple[int, list[float]], ...]:
    """Vectorize exact 8-connected anisotropic edge costs (`inf` when blocked or > 20 deg)."""
    blocked, caution, grad_x, grad_y, risk_01 = _GRID_ARRAYS_BY_DIGEST[digest]
    inf = float("inf")
    tables: list[tuple[int, list[float]]] = []

    for dr, dc in _NEIGHBORS_8:
        dx_m = dc * step_x
        dy_m = -dr * step_y
        dist_m = math.hypot(dx_m, dy_m)
        ux = dx_m / dist_m
        uy = dy_m / dist_m
        is_diag = dr != 0 and dc != 0

        r0 = max(0, -dr)
        r1 = rows - max(0, dr)
        c0 = max(0, -dc)
        c1 = cols - max(0, dc)
        s_src = (slice(r0, r1), slice(c0, c1))
        s_dst = (slice(r0 + dr, r1 + dr), slice(c0 + dc, c1 + dc))

        edge_mat = np.full((rows, cols), inf, dtype=np.float64)
        valid = (~blocked[s_src]) & (~blocked[s_dst])
        if is_diag:
            s_orth1 = (slice(r0, r1), slice(c0 + dc, c1 + dc))
            s_orth2 = (slice(r0 + dr, r1 + dr), slice(c0, c1))
            valid &= (~blocked[s_orth1]) & (~blocked[s_orth2])

        gx = 0.5 * (grad_x[s_src] + grad_x[s_dst])
        gy = 0.5 * (grad_y[s_src] + grad_y[s_dst])
        risk_mid = 0.5 * (risk_01[s_src] + risk_01[s_dst])
        valid &= np.isfinite(gx) & np.isfinite(gy) & np.isfinite(risk_mid)

        g_par = gx * ux + gy * uy
        g_cross = np.abs(gx * uy - gy * ux)
        theta_par = np.degrees(np.arctan(np.abs(g_par)))
        theta_cross = np.degrees(np.arctan(g_cross))
        theta_max = np.maximum(theta_par, theta_cross)
        valid &= theta_max <= EVA_SUIT_MAX_SLOPE_DEG

        v_kmh = np.maximum(0.15, 2.4 * np.exp(-3.5 * np.abs(g_par + 0.05)))
        v_ms = np.clip((v_kmh / 3.6) / (1.0 + 0.60 * (g_cross * g_cross)), 0.04, V_MAX_XEVA_M_S)
        dt_s = dist_m / v_ms

        if pure_time_only:
            cost_sub = dt_s
        else:
            norm_slope = theta_max / EVA_SUIT_MAX_SLOPE_DEG
            cross_caution = np.where(
                theta_cross > INTERNAL_CROSS_SLOPE_CAUTION_DEG,
                0.45 * ((theta_cross - INTERNAL_CROSS_SLOPE_CAUTION_DEG) / 5.0),
                0.0,
            )
            caution_pen = np.where(caution[s_src] | caution[s_dst], 0.20, 0.0)
            cost_sub = dt_s * (
                1.0 + alpha_slope * norm_slope + gamma_risk * risk_mid + cross_caution + caution_pen
            )

        sub_out = edge_mat[s_src]
        sub_out[valid] = cost_sub[valid]
        tables.append((dr * cols + dc, edge_mat.ravel().tolist()))

    return tuple(tables)


def _register_grid_digest(grid: PlannerGrid10m) -> bytes:
    """Register `grid` arrays in the bounded ring buffer (`<= 12`) and return its digest."""
    digest = _grid_content_digest(grid)
    if digest not in _GRID_ARRAYS_BY_DIGEST:
        if len(_GRID_ARRAYS_BY_DIGEST) >= 12:
            _GRID_ARRAYS_BY_DIGEST.pop(next(iter(_GRID_ARRAYS_BY_DIGEST)))
        _GRID_ARRAYS_BY_DIGEST[digest] = (
            grid.blocked_mask,
            grid.caution_mask,
            grid.grad_x,
            grid.grad_y,
            grid.risk_penalty_01,
        )
    return digest


@lru_cache(maxsize=4096)
def _rel_supercover_geom(
    dr: int, dc: int, cols: int, step_x: float, step_y: float
) -> tuple[np.ndarray, float, float, float, float]:
    """Cache relative flat index offsets and unit vector geometry for `(dr, dc)`."""
    if dr == 0 and dc == 0:
        return (np.zeros(1, dtype=np.intp), 0.0, 0.0, 0.0, 0.0)
    du = float(dc)
    dv = float(dr)
    c = 0
    r = 0
    step_c = 1 if du > 0.0 else (-1 if du < 0.0 else 0)
    step_r = 1 if dv > 0.0 else (-1 if dv < 0.0 else 0)
    step_idx_r = step_r * cols
    t_delta_c = abs(1.0 / du) if step_c != 0 else float("inf")
    t_delta_r = abs(1.0 / dv) if step_r != 0 else float("inf")
    t_max_c = (0.5 * t_delta_c) if step_c != 0 else float("inf")
    t_max_r = (0.5 * t_delta_r) if step_r != 0 else float("inf")
    idx1 = dr * cols + dc
    cur_idx = 0
    last_idx = 0
    visited = [0]
    append = visited.append
    max_iters = 2 * (abs(dr) + abs(dc)) + 4
    corner_eps = 1e-9
    for _ in range(max_iters):
        if cur_idx == idx1:
            break
        diff = t_max_c - t_max_r
        if diff < -corner_eps:
            c += step_c
            cur_idx += step_c
            t_max_c += t_delta_c
            append(cur_idx)
            last_idx = cur_idx
        elif diff > corner_eps:
            r += step_r
            cur_idx += step_idx_r
            t_max_r += t_delta_r
            append(cur_idx)
            last_idx = cur_idx
        else:
            nc1 = c + step_c
            idx_c1 = cur_idx + step_c
            if idx_c1 != last_idx:
                append(idx_c1)
                last_idx = idx_c1
            nr2 = r + step_r
            idx_r2 = cur_idx + step_idx_r
            if idx_r2 != last_idx:
                append(idx_r2)
                last_idx = idx_r2
            c = nc1
            r = nr2
            cur_idx = r * cols + c
            t_max_c += t_delta_c
            t_max_r += t_delta_r
            if cur_idx != last_idx:
                append(cur_idx)
                last_idx = cur_idx
    if last_idx != idx1:
        append(idx1)
    dx_m = dc * step_x
    dy_north_m = -dr * step_y
    total_dist_m = math.hypot(dx_m, dy_north_m)
    ds_m = total_dist_m / float(len(visited))
    ux = dx_m / total_dist_m
    uy = dy_north_m / total_dist_m
    return (np.array(visited, dtype=np.intp), total_dist_m, ds_m, ux, uy)


@lru_cache(maxsize=12)
def _cached_flat_grid_np(
    digest: bytes,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Cache flat 1D contiguous NumPy views for vectorized string-pull shortcut evaluation."""
    blocked, caution, grad_x, grad_y, risk_01 = _GRID_ARRAYS_BY_DIGEST[digest]
    return (
        np.ascontiguousarray(blocked, dtype=np.uint8).ravel(),
        np.where(np.ascontiguousarray(caution, dtype=bool).ravel(), 0.20, 0.0),
        np.ascontiguousarray(grad_x, dtype=np.float64).ravel(),
        np.ascontiguousarray(grad_y, dtype=np.float64).ravel(),
        np.ascontiguousarray(risk_01, dtype=np.float64).ravel(),
    )


@lru_cache(maxsize=12)
def _cached_flat_grid_lists(
    digest: bytes,
) -> tuple[list[bool], list[bool], list[float], list[float], list[float]]:
    """Cache flat Python lists of `grid` arrays for fast scalar supercover / shortcut sweeps."""
    blocked, caution, grad_x, grad_y, risk_01 = _GRID_ARRAYS_BY_DIGEST[digest]
    return (
        blocked.ravel().tolist(),
        caution.ravel().tolist(),
        grad_x.ravel().tolist(),
        grad_y.ravel().tolist(),
        risk_01.ravel().tolist(),
    )


def _get_flat_grid_lists(
    grid: PlannerGrid10m,
    *,
    _digest: bytes | None = None,
) -> tuple[list[bool], list[bool], list[float], list[float], list[float]]:
    """Return cached flat Python lists for `grid` (bounded LRU <= 12)."""
    return _cached_flat_grid_lists(_digest if _digest is not None else _register_grid_digest(grid))


def _get_directional_edge_tables(
    grid: PlannerGrid10m,
    *,
    alpha_slope: float,
    gamma_risk: float,
    pure_time_only: bool,
    _digest: bytes | None = None,
) -> tuple[tuple[int, list[float]], ...]:
    """Return cached 8-directional edge-cost tables for `grid` (bounded ring buffer <= 12)."""
    digest = _digest if _digest is not None else _register_grid_digest(grid)
    return _cached_directional_edge_tables(
        grid.rows,
        grid.cols,
        float(grid.step_x_ground_m),
        float(grid.step_y_ground_m),
        float(alpha_slope),
        float(gamma_risk),
        bool(pure_time_only),
        digest,
    )


@lru_cache(maxsize=32)
def _cached_h_table(
    rows: int,
    cols: int,
    gr: int,
    gc: int,
    step_x: float,
    step_y: float,
    w_h: float,
) -> list[float]:
    """Cache Euclidean A* heuristic table `d / V_MAX_XEVA_M_S` for `(rows, cols, gr, gc)`."""
    if w_h == 0.0:
        return [0.0] * (rows * cols)
    scale_h = w_h / V_MAX_XEVA_M_S
    dy_vec = (gr - np.arange(rows, dtype=np.float64)) * step_y
    dx_vec = (gc - np.arange(cols, dtype=np.float64)) * step_x
    return (np.hypot(dy_vec[:, None], dx_vec[None, :]) * scale_h).ravel().tolist()


def _astar_single_leg(
    grid: PlannerGrid10m,
    start_rc: tuple[int, int],
    goal_rc: tuple[int, int],
    *,
    heuristic_weight: float = 1.0,
    alpha_slope: float = 1.2,
    gamma_risk: float = 1.4,
    pure_time_only: bool = False,
    _digest: bytes | None = None,
) -> tuple[bool, list[tuple[int, int]], list[float], int]:
    """Run 8-connected A* with strictly admissible Euclidean heuristic `d / V_MAX_XEVA_M_S`."""
    rows = grid.rows
    cols = grid.cols
    sr, sc = start_rc
    gr, gc = goal_rc
    if not (in_grid_bounds(sr, sc, rows, cols) and in_grid_bounds(gr, gc, rows, cols)):
        return (False, [], [], 0)

    if bool(grid.blocked_mask[sr, sc]) or bool(grid.blocked_mask[gr, gc]):
        return (False, [], [], 0)

    s_idx = sr * cols + sc
    g_idx = gr * cols + gc
    if s_idx == g_idx:
        return (True, [(sr, sc)], [0.0], 1)

    dir_tables = _get_directional_edge_tables(
        grid,
        alpha_slope=alpha_slope,
        gamma_risk=gamma_risk,
        pure_time_only=pure_time_only,
        _digest=_digest,
    )

    w_h = max(0.0, float(heuristic_weight))
    h_table = _cached_h_table(
        rows,
        cols,
        gr,
        gc,
        float(grid.step_x_ground_m),
        float(grid.step_y_ground_m),
        w_h,
    )

    inf = float("inf")
    n_total = rows * cols
    g_score = [inf] * n_total
    came_from = [-1] * n_total

    g_score[s_idx] = 0.0
    idx_shift = max(1, n_total.bit_length())
    idx_mask = (1 << idx_shift) - 1
    heap: list[tuple[float, int]] = [(h_table[s_idx], s_idx)]
    tie = 0
    expanded = 0
    heappop = heapq.heappop
    heappush = heapq.heappush

    (
        (d0, e0),
        (d1, e1),
        (d2, e2),
        (d3, e3),
        (d4, e4),
        (d5, e5),
        (d6, e6),
        (d7, e7),
    ) = dir_tables
    eps = 1e-12

    while heap:
        _, packed = heappop(heap)
        cur_idx = packed & idx_mask
        cur_g = g_score[cur_idx]
        if cur_g < 0.0:
            continue
        g_score[cur_idx] = -1.0 - cur_g
        expanded += 1

        if cur_idx == g_idx:
            rev_indices: list[int] = [g_idx]
            walk = g_idx
            while came_from[walk] != -1:
                walk = came_from[walk]
                rev_indices.append(walk)
            rev_indices.reverse()
            path = [(idx // cols, idx % cols) for idx in rev_indices]
            cum_g = [-1.0 - g_score[idx] for idx in rev_indices]
            return (True, path, cum_g, expanded)

        cg_eps = cur_g + eps

        es = e0[cur_idx]
        if es != inf:
            ni = cur_idx + d0
            if cg_eps + es < g_score[ni]:
                cg = cur_g + es
                g_score[ni] = cg
                came_from[ni] = cur_idx
                tie += 1
                heappush(heap, (cg + h_table[ni], (tie << idx_shift) | ni))
        es = e1[cur_idx]
        if es != inf:
            ni = cur_idx + d1
            if cg_eps + es < g_score[ni]:
                cg = cur_g + es
                g_score[ni] = cg
                came_from[ni] = cur_idx
                tie += 1
                heappush(heap, (cg + h_table[ni], (tie << idx_shift) | ni))
        es = e2[cur_idx]
        if es != inf:
            ni = cur_idx + d2
            if cg_eps + es < g_score[ni]:
                cg = cur_g + es
                g_score[ni] = cg
                came_from[ni] = cur_idx
                tie += 1
                heappush(heap, (cg + h_table[ni], (tie << idx_shift) | ni))
        es = e3[cur_idx]
        if es != inf:
            ni = cur_idx + d3
            if cg_eps + es < g_score[ni]:
                cg = cur_g + es
                g_score[ni] = cg
                came_from[ni] = cur_idx
                tie += 1
                heappush(heap, (cg + h_table[ni], (tie << idx_shift) | ni))
        es = e4[cur_idx]
        if es != inf:
            ni = cur_idx + d4
            if cg_eps + es < g_score[ni]:
                cg = cur_g + es
                g_score[ni] = cg
                came_from[ni] = cur_idx
                tie += 1
                heappush(heap, (cg + h_table[ni], (tie << idx_shift) | ni))
        es = e5[cur_idx]
        if es != inf:
            ni = cur_idx + d5
            if cg_eps + es < g_score[ni]:
                cg = cur_g + es
                g_score[ni] = cg
                came_from[ni] = cur_idx
                tie += 1
                heappush(heap, (cg + h_table[ni], (tie << idx_shift) | ni))
        es = e6[cur_idx]
        if es != inf:
            ni = cur_idx + d6
            if cg_eps + es < g_score[ni]:
                cg = cur_g + es
                g_score[ni] = cg
                came_from[ni] = cur_idx
                tie += 1
                heappush(heap, (cg + h_table[ni], (tie << idx_shift) | ni))
        es = e7[cur_idx]
        if es != inf:
            ni = cur_idx + d7
            if cg_eps + es < g_score[ni]:
                cg = cur_g + es
                g_score[ni] = cg
                came_from[ni] = cur_idx
                tie += 1
                heappush(heap, (cg + h_table[ni], (tie << idx_shift) | ni))

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
    _digest: bytes | None = None,
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

    digest = _digest if _digest is not None else _register_grid_digest(grid)
    blocked_arr, caut_pen_arr, gx_arr, gy_arr, risk_arr = _cached_flat_grid_np(digest)
    rows = grid.rows
    cols = grid.cols
    step_x = float(grid.step_x_ground_m)
    step_y = float(grid.step_y_ground_m)
    max_slope_deg = EVA_SUIT_MAX_SLOPE_DEG
    cross_caution_deg = INTERNAL_CROSS_SLOPE_CAUTION_DEG
    vmax = V_MAX_XEVA_M_S
    tan15 = _TAN_CROSS_CAUTION_15
    slope_scale = alpha_slope / max_slope_deg
    base_mult_arr = 1.0 + gamma_risk * risk_arr + caut_pen_arr if not pure_time_only else risk_arr

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
        chosen_seg_s = -1.0
        r0, c0 = raw_path[idx]
        idx0 = r0 * cols + c0

        upper_j = min(n - 1, idx + max(2, int(max_lookahead_steps)))
        base_g_s = cum_g_s[idx]
        cand_js = list(range(upper_j, idx + 1, -1))
        if cand_js:
            seg_arrays: list[np.ndarray] = []
            lengths: list[int] = []
            ux_segs: list[float] = []
            uy_segs: list[float] = []
            ds_segs: list[float] = []
            caps: list[float] = []
            oob_flags: list[bool] = []

            for cj in cand_js:
                r1, c1 = raw_path[cj]
                caps.append((cum_g_s[cj] - base_g_s) + cost_eps_s)
                if not (0 <= r0 < rows and 0 <= c0 < cols and 0 <= r1 < rows and 0 <= c1 < cols):
                    oob_flags.append(True)
                    seg_arrays.append(np.zeros(1, dtype=np.intp))
                    lengths.append(1)
                    ux_segs.append(0.0)
                    uy_segs.append(0.0)
                    ds_segs.append(0.0)
                    continue
                oob_flags.append(False)
                rel_arr, _, ds_m, ux, uy = _rel_supercover_geom(
                    r1 - r0, c1 - c0, cols, step_x, step_y
                )
                seg_arrays.append(idx0 + rel_arr)
                lengths.append(len(rel_arr))
                ux_segs.append(ux)
                uy_segs.append(uy)
                ds_segs.append(ds_m)

            c_idx_arr = np.concatenate(seg_arrays)
            len_arr = np.array(lengths, dtype=np.intp)
            off_arr = np.zeros(len(lengths), dtype=np.intp)
            if len(lengths) > 1:
                np.cumsum(len_arr[:-1], out=off_arr[1:])

            ux_a = np.repeat(np.array(ux_segs, dtype=np.float64), len_arr)
            uy_a = np.repeat(np.array(uy_segs, dtype=np.float64), len_arr)
            ds_a = np.repeat(np.array(ds_segs, dtype=np.float64), len_arr)

            gx = gx_arr[c_idx_arr]
            gy = gy_arr[c_idx_arr]
            g_par = gx * ux_a + gy * uy_a
            g_cross = np.abs(gx * uy_a - gy * ux_a)
            g_max = np.maximum(np.abs(g_par), g_cross)
            theta_max = np.degrees(np.arctan(g_max))
            cell_invalid = (
                (blocked_arr[c_idx_arr] != 0)
                | (~np.isfinite(gx))
                | (~np.isfinite(gy))
                | (theta_max > max_slope_deg)
            )
            v_kmh = np.maximum(0.15, 2.4 * np.exp(-3.5 * np.abs(g_par + 0.05)))
            v_ms = np.clip((v_kmh / 3.6) / (1.0 + 0.60 * (g_cross * g_cross)), 0.04, vmax)
            dt_s = ds_a / v_ms
            if pure_time_only:
                cell_cost = dt_s
            else:
                cell_invalid |= ~np.isfinite(risk_arr[c_idx_arr])
                mult = base_mult_arr[c_idx_arr] + slope_scale * theta_max
                if np.any(g_cross > tan15):
                    theta_cross = np.degrees(np.arctan(g_cross))
                    mult = mult + np.where(
                        theta_cross > cross_caution_deg,
                        0.45 * ((theta_cross - cross_caution_deg) / 5.0),
                        0.0,
                    )
                cell_cost = dt_s * mult

            seg_bad = np.maximum.reduceat(cell_invalid.view(np.uint8), off_arr) > 0
            seg_costs = np.add.reduceat(cell_cost, off_arr)
            seg_bad |= ~np.isfinite(seg_costs)

            for k, cj in enumerate(cand_js):
                candidates_tested += 1
                if oob_flags[k] or seg_bad[k]:
                    rej_obs += 1
                    continue
                sc = float(seg_costs[k])
                if sc <= caps[k]:
                    accepted_count += 1
                    chosen_j = cj
                    chosen_seg_s = sc
                    break
                rej_cost += 1

        if chosen_seg_s < 0.0:
            _, chosen_seg_s, _, _, _ = _cell_step_cost_s(
                grid,
                r0,
                c0,
                raw_path[idx + 1][0],
                raw_path[idx + 1][1],
                alpha_slope=alpha_slope,
                gamma_risk=gamma_risk,
                pure_time_only=pure_time_only,
            )
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

    digest = _register_grid_digest(grid)
    for leg_idx in range(len(rc_stops) - 1):
        ok_leg, leg_raw, leg_g, exp_n = _astar_single_leg(
            grid,
            rc_stops[leg_idx],
            rc_stops[leg_idx + 1],
            heuristic_weight=w_h,
            pure_time_only=pure_time,
            _digest=digest,
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
                grid, leg_raw, leg_g, pure_time_only=pure_time, _digest=digest
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
    flat_cache = _get_flat_grid_lists(grid, _digest=digest)

    for idx in range(len(full_smoothed) - 1):
        r0, c0 = full_smoothed[idx]
        r1, c1 = full_smoothed[idx + 1]
        dx_m = (c1 - c0) * grid.step_x_ground_m
        dy_m = -(r1 - r0) * grid.step_y_ground_m
        total_dist_m += math.hypot(dx_m, dy_m)
        _, _, seg_dt_s, seg_par, seg_cross, seg_caut = evaluate_shortcut_segment_cost_s(
            grid, r0, c0, r1, c1, pure_time_only=pure_time, _flat=flat_cache
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
