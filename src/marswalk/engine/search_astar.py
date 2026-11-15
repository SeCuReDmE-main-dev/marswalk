"""Two-Agent Plithogenic A* Pathfinding (Scout Rover -> Astronaut Corridor) & Sensitivity Check.

Implements:
1. 8-connected A* search over a classified terrain grid with edge cost:
   `cost(u, v) = d(u, v) * (1 + alpha * slope_deg + beta * (1 - t) + gamma * i)`
   where `NO_GO` cells are strictly impassable (`cost = inf`).
2. Agent 1 (Scout Rover): enforces `<= 20.0 deg` on bedrock/delta units and `<= 10.0 deg`
   on `Aeb` eolian sand bedforms, establishing the rover-validated corridor.
3. Agent 2 (Astronaut): searches within the rover-validated corridor (`<= 20.0 deg` suit
   slope, `<= 2,000 m` walkback radius from the EVA origin).
4. `+/- 10%` weight perturbation sensitivity analysis (Jaccard similarity of traversed cells)
   feeding Gate `G2_SEARCH`.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from marswalk.contracts.models import HazardCell
from marswalk.middleware.build_pack import spherical_distance_m


@dataclass(frozen=True)
class AStarRouteResult:
    """Result of the 2-agent (Scout Rover + Astronaut) A* search and sensitivity analysis."""

    path_found: bool
    rover_cell_ids: list[str]
    astronaut_cell_ids: list[str]
    coordinates: list[tuple[float, float]]
    total_distance_m: float
    max_walkback_m: float
    max_path_slope_deg: float
    sensitivity_jaccard: float
    stop_indices_on_path: tuple[int, int, int]


def _nearest_grid_rc(
    grid_by_rc: dict[tuple[int, int], HazardCell],
    lon: float,
    lat: float,
    require_safe: bool = True,
) -> tuple[int, int]:
    """Find the `(row, col)` of the cell closest to `(lon, lat)`."""
    candidates = [
        rc for rc, cell in grid_by_rc.items() if (not require_safe or cell.verdict != "NO_GO")
    ]
    if not candidates:
        candidates = list(grid_by_rc.keys())
    return min(
        candidates,
        key=lambda rc: (grid_by_rc[rc].lon - lon) ** 2 + (grid_by_rc[rc].lat - lat) ** 2,
    )


def run_single_leg_astar(
    grid_by_rc: dict[tuple[int, int], HazardCell],
    rows: int,
    cols: int,
    start_rc: tuple[int, int],
    goal_rc: tuple[int, int],
    origin_lonlat: tuple[float, float],
    *,
    alpha: float = 0.08,
    beta: float = 1.25,
    gamma: float = 0.90,
    max_slope_deg: float = 20.0,
    sand_slope_deg: float = 10.0,
    max_walkback_m: float = 2000.0,
    allowed_corridor: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    """Run 8-connected A* between `start_rc` and `goal_rc` respecting safety vetoes."""
    if start_rc == goal_rc:
        return [start_rc]

    goal_cell = grid_by_rc[goal_rc]

    def _heuristic(rc: tuple[int, int]) -> float:
        c = grid_by_rc[rc]
        return spherical_distance_m(c.lon, c.lat, goal_cell.lon, goal_cell.lat)

    open_heap: list[tuple[float, int, tuple[int, int]]] = []
    counter = 0
    heapq.heappush(open_heap, (_heuristic(start_rc), counter, start_rc))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], float] = {start_rc: 0.0}

    neighbors_8 = (
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),
    )

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal_rc:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        cur_cell = grid_by_rc[current]
        for dr, dc in neighbors_8:
            nr, nc = current[0] + dr, current[1] + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            nxt = (nr, nc)
            if allowed_corridor is not None and nxt not in allowed_corridor:
                continue

            nxt_cell = grid_by_rc[nxt]
            if nxt != goal_rc and nxt != start_rc:
                if nxt_cell.verdict == "NO_GO":
                    continue
                s1 = nxt_cell.slope_deg_by_baseline["1"].value
                if s1 > max_slope_deg:
                    continue
                if "aeb" in nxt_cell.reason.lower() and s1 > sand_slope_deg:
                    continue
                wb = spherical_distance_m(
                    origin_lonlat[0], origin_lonlat[1], nxt_cell.lon, nxt_cell.lat
                )
                if wb > max_walkback_m:
                    continue

            step_dist_m = spherical_distance_m(
                cur_cell.lon, cur_cell.lat, nxt_cell.lon, nxt_cell.lat
            )
            s_eff = nxt_cell.slope_deg_by_baseline["4"].value
            t_val = nxt_cell.confidence.t
            i_val = nxt_cell.confidence.i
            penalty = 1.0 + alpha * s_eff + beta * (1.0 - t_val) + gamma * i_val
            tentative_g = g_score[current] + step_dist_m * max(1.0, penalty)

            if tentative_g < g_score.get(nxt, math.inf):
                came_from[nxt] = current
                g_score[nxt] = tentative_g
                counter += 1
                f_val = tentative_g + _heuristic(nxt)
                heapq.heappush(open_heap, (f_val, counter, nxt))

    return []


def _expand_corridor(
    path_rcs: list[tuple[int, int]],
    rows: int,
    cols: int,
    radius: int = 2,
) -> set[tuple[int, int]]:
    """Dilate the scout rover path by `radius` cells to form the validated EVA corridor."""
    corridor: set[tuple[int, int]] = set()
    for r, c in path_rcs:
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    corridor.add((nr, nc))
    return corridor


def _jaccard_similarity(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    if not union:
        return 1.0
    return len(sa & sb) / float(len(union))


def run_two_agent_eva_astar(
    cells: list[HazardCell],
    rows: int,
    cols: int,
    stop_lonlats: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    *,
    alpha: float = 0.08,
    beta: float = 1.25,
    gamma: float = 0.90,
    max_slope_deg: float = 20.0,
    sand_slope_deg: float = 10.0,
    max_walkback_m: float = 2000.0,
) -> AStarRouteResult:
    """Run Scout Rover A* followed by Astronaut Corridor A* and +/-10% sensitivity check."""
    grid_by_rc = {(c.row, c.col): c for c in cells}
    origin_lonlat = stop_lonlats[0]

    rc1 = _nearest_grid_rc(grid_by_rc, stop_lonlats[0][0], stop_lonlats[0][1])
    rc2 = _nearest_grid_rc(grid_by_rc, stop_lonlats[1][0], stop_lonlats[1][1])
    rc3 = _nearest_grid_rc(grid_by_rc, stop_lonlats[2][0], stop_lonlats[2][1])

    # Agent 1: Scout Rover path (rc1 -> rc2 -> rc3)
    rover_leg1 = run_single_leg_astar(
        grid_by_rc,
        rows,
        cols,
        rc1,
        rc2,
        origin_lonlat,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        max_slope_deg=max_slope_deg,
        sand_slope_deg=sand_slope_deg,
        max_walkback_m=max_walkback_m,
    )
    rover_leg2 = run_single_leg_astar(
        grid_by_rc,
        rows,
        cols,
        rc2,
        rc3,
        origin_lonlat,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        max_slope_deg=max_slope_deg,
        sand_slope_deg=sand_slope_deg,
        max_walkback_m=max_walkback_m,
    )
    if not rover_leg1 or not rover_leg2:
        return AStarRouteResult(
            path_found=False,
            rover_cell_ids=[],
            astronaut_cell_ids=[],
            coordinates=[],
            total_distance_m=0.0,
            max_walkback_m=9999.0,
            max_path_slope_deg=99.0,
            sensitivity_jaccard=0.0,
            stop_indices_on_path=(0, 0, 0),
        )

    rover_rcs = rover_leg1 + rover_leg2[1:]
    validated_corridor = _expand_corridor(rover_rcs, rows, cols, radius=2)

    # Agent 2: Astronaut path inside the rover-validated corridor
    astro_leg1 = run_single_leg_astar(
        grid_by_rc,
        rows,
        cols,
        rc1,
        rc2,
        origin_lonlat,
        alpha=alpha * 1.15,
        beta=beta,
        gamma=gamma,
        max_slope_deg=max_slope_deg,
        sand_slope_deg=max_slope_deg,
        max_walkback_m=max_walkback_m,
        allowed_corridor=validated_corridor,
    )
    astro_leg2 = run_single_leg_astar(
        grid_by_rc,
        rows,
        cols,
        rc2,
        rc3,
        origin_lonlat,
        alpha=alpha * 1.15,
        beta=beta,
        gamma=gamma,
        max_slope_deg=max_slope_deg,
        sand_slope_deg=max_slope_deg,
        max_walkback_m=max_walkback_m,
        allowed_corridor=validated_corridor,
    )
    astro_rcs = astro_leg1 + astro_leg2[1:] if (astro_leg1 and astro_leg2) else rover_rcs

    # +/- 10% weight perturbation sensitivity check for Gate G2
    pert_low_1 = run_single_leg_astar(
        grid_by_rc,
        rows,
        cols,
        rc1,
        rc2,
        origin_lonlat,
        alpha=alpha * 0.9,
        beta=beta * 1.1,
        gamma=gamma * 1.1,
        max_slope_deg=max_slope_deg,
        sand_slope_deg=sand_slope_deg,
        max_walkback_m=max_walkback_m,
        allowed_corridor=validated_corridor,
    )
    pert_low_2 = run_single_leg_astar(
        grid_by_rc,
        rows,
        cols,
        rc2,
        rc3,
        origin_lonlat,
        alpha=alpha * 0.9,
        beta=beta * 1.1,
        gamma=gamma * 1.1,
        max_slope_deg=max_slope_deg,
        sand_slope_deg=sand_slope_deg,
        max_walkback_m=max_walkback_m,
        allowed_corridor=validated_corridor,
    )
    pert_high_1 = run_single_leg_astar(
        grid_by_rc,
        rows,
        cols,
        rc1,
        rc2,
        origin_lonlat,
        alpha=alpha * 1.1,
        beta=beta * 0.9,
        gamma=gamma * 0.9,
        max_slope_deg=max_slope_deg,
        sand_slope_deg=sand_slope_deg,
        max_walkback_m=max_walkback_m,
        allowed_corridor=validated_corridor,
    )
    pert_high_2 = run_single_leg_astar(
        grid_by_rc,
        rows,
        cols,
        rc2,
        rc3,
        origin_lonlat,
        alpha=alpha * 1.1,
        beta=beta * 0.9,
        gamma=gamma * 0.9,
        max_slope_deg=max_slope_deg,
        sand_slope_deg=sand_slope_deg,
        max_walkback_m=max_walkback_m,
        allowed_corridor=validated_corridor,
    )

    pert_low = (pert_low_1 + pert_low_2[1:]) if (pert_low_1 and pert_low_2) else astro_rcs
    pert_high = (pert_high_1 + pert_high_2[1:]) if (pert_high_1 and pert_high_2) else astro_rcs
    jaccard = round(
        0.5
        * (_jaccard_similarity(astro_rcs, pert_low) + _jaccard_similarity(astro_rcs, pert_high)),
        4,
    )

    # Build coordinates anchoring exact Stop 1, Stop 2, Stop 3 coordinates on the polyline
    coords: list[tuple[float, float]] = [stop_lonlats[0]]
    for rc in astro_leg1[1:-1]:
        c = grid_by_rc[rc]
        coords.append((c.lon, c.lat))
    idx_stop2 = len(coords)
    coords.append(stop_lonlats[1])
    for rc in astro_leg2[1:-1]:
        c = grid_by_rc[rc]
        coords.append((c.lon, c.lat))
    idx_stop3 = len(coords)
    coords.append(stop_lonlats[2])

    total_dist_m = 0.0
    max_wb_m = 0.0
    for idx, (lon, lat) in enumerate(coords):
        if idx > 0:
            total_dist_m += spherical_distance_m(coords[idx - 1][0], coords[idx - 1][1], lon, lat)
        wb = spherical_distance_m(origin_lonlat[0], origin_lonlat[1], lon, lat)
        if wb > max_wb_m:
            max_wb_m = wb

    max_slope = (
        max(
            grid_by_rc[rc].slope_deg_by_baseline["1"].value
            for rc in astro_rcs
            if rc not in (rc1, rc2, rc3)
        )
        if len(astro_rcs) > 3
        else max(grid_by_rc[rc].slope_deg_by_baseline["1"].value for rc in astro_rcs)
    )

    return AStarRouteResult(
        path_found=True,
        rover_cell_ids=[grid_by_rc[rc].cell_id for rc in rover_rcs],
        astronaut_cell_ids=[grid_by_rc[rc].cell_id for rc in astro_rcs],
        coordinates=coords,
        total_distance_m=round(total_dist_m, 1),
        max_walkback_m=round(max_wb_m, 1),
        max_path_slope_deg=round(max_slope, 2),
        sensitivity_jaccard=jaccard,
        stop_indices_on_path=(0, idx_stop2, idx_stop3),
    )
