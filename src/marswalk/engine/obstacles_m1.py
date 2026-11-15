"""Phase 4 Geometric Detection of Large Rock Formations & Scarps >= ~4 m (`M1`).

Enforces CTO rules (`X1`, `X2`, `C1`, `C2`, `C3`, `F2` & Arbitration #1):
1. Spatial resolution honesty (`C2`): a 1.0 m/px stereo HiRISE DTM has an effective
   horizontal resolution of ~3-4 posts (~3.5-4 m). This module extracts large rock
   formations, knobs, ridges, and scarps >= ~4 m ONLY. Unresolved meter/sub-meter blocks
   remain strictly in indeterminacy `I`, never in deterministic obstacle masks.
2. Zero uncalibrated CFA verdict gating (`R1`, `X2`, `F2`): never calls the heuristic CFA
   proxy to block cells and contains zero `10.0` or `11.0` thresholds. Preserves Ono et al.
   (2016, p. 3) `7.0%` / `15.0%` strictly as documented rover AutoNav reference constants.
3. Physical clearance buffer only (`C3`): computes Minkowski C-space clearance on 0.5 m
   sub-posts with radius `r_phys = r_half_suit (0.40 m) + sigma_dtm (0.45 m) = 0.85 m`, so
   every clear corridor >= 2.0 m stays open while narrow gaps < 1.5 m close, and applies
   zero 7.07 m half-diagonal cross-cell bleed onto the 10 m PNG planning grid.
4. Anti-leakage validation (`C1`): evaluates specificity on even sols only (`sol % 2 == 0`
   among the 147 in-window Perseverance stops) with frozen parameters, plus sensitivity
   against independent USGS SIM 3464 mapped delta-scarp margin relief.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

from marswalk.engine.boulder_cfa import (
    ROVER_CFA_CAUTION_PCT,
    ROVER_CFA_OK_PCT,
    golombek_cumulative_fractional_area,
)
from marswalk.engine.dtm_ingest import (
    classify_sim3464_unit,
    eqc_x_m_to_lon,
    eqc_y_m_to_lat,
    ground_step_x_m,
    lat_to_eqc_y_m,
    lon_to_eqc_x_m,
)

EVA_SUIT_MAX_SLOPE_DEG: float = 20.0
HALF_SUIT_WIDTH_M: float = 0.40
DTM_HORIZ_SIGMA_M: float = 0.45
PHYSICAL_CLEARANCE_RADIUS_M: float = HALF_SUIT_WIDTH_M + DTM_HORIZ_SIGMA_M  # 0.85 m

# Frozen M1 morphological parameters (fixed prior to even-sol validation, C1)
FORMATION_TOPHAT_WINDOW_PX: int = 9
FORMATION_TOPHAT_RELIEF_MIN_M: float = 1.15
FORMATION_MIN_AREA_PX: int = 16  # >= ~15 m^2 (~4 m x 4 m minimum footprint, C2)
PLANNER_GRID_ROWS_10M: int = 200
PLANNER_GRID_COLS_10M: int = 190
GRAD_CLIP_MAX: float = 0.65


@dataclass(frozen=True)
class PlannerGrid10m:
    """Compact 10 m obstacle, gradient, and risk grid encoded/decoded via uint8 RGBA PNG."""

    rows: int
    cols: int
    bbox: tuple[float, float, float, float]
    step_x_ground_m: float
    step_y_ground_m: float
    blocked_mask: np.ndarray  # bool (rows, cols)
    caution_mask: np.ndarray  # bool (rows, cols)
    toe_refuge_mask: np.ndarray  # bool (rows, cols)
    grad_x: np.ndarray  # float64 (rows, cols) dZ / dx_ground
    grad_y: np.ndarray  # float64 (rows, cols) dZ / dy_ground
    risk_penalty_01: np.ndarray  # float64 (rows, cols) in [0, 1]


@dataclass(frozen=True)
class M1GroundTruthValidation:
    """Validation metrics of M1 obstacle detection on real Jezero data (`C1`)."""

    total_window_stops: int
    even_sol_gentle_stops: int
    even_sol_false_positives: int
    even_sol_specificity: float
    sim3464_scarp_margin_pixels: int
    sim3464_scarp_detected_pixels: int
    sim3464_scarp_recall: float
    sol_700_slope_4m_deg: float
    sol_700_exceeds_20deg_limit: bool
    ono_rover_cfa_reference_pct: tuple[float, float]


def _box_min_2d(arr: np.ndarray, window: int) -> np.ndarray:
    pad = window // 2
    padded_h = np.pad(arr, ((0, 0), (pad, pad)), mode="edge")
    min_h = np.min(sliding_window_view(padded_h, window, axis=1), axis=-1)
    padded_v = np.pad(min_h, ((pad, pad), (0, 0)), mode="edge")
    return np.min(sliding_window_view(padded_v, window, axis=0), axis=-1)


def _box_max_2d(arr: np.ndarray, window: int) -> np.ndarray:
    pad = window // 2
    padded_h = np.pad(arr, ((0, 0), (pad, pad)), mode="edge")
    max_h = np.max(sliding_window_view(padded_h, window, axis=1), axis=-1)
    padded_v = np.pad(max_h, ((pad, pad), (0, 0)), mode="edge")
    return np.max(sliding_window_view(padded_v, window, axis=0), axis=-1)


def grey_opening_2d(arr: np.ndarray, window: int = FORMATION_TOPHAT_WINDOW_PX) -> np.ndarray:
    """Compute exact 2D greyscale morphological opening `max_box(min_box(z))` in pure NumPy."""
    eroded = _box_min_2d(arr, window)
    return _box_max_2d(eroded, window)


def apply_physical_clearance_buffer_1m(
    raw_obstacle_mask: np.ndarray,
    step_x_m: float,
    step_y_m: float = 1.0,
    clearance_m: float = PHYSICAL_CLEARANCE_RADIUS_M,
) -> np.ndarray:
    """Apply Minkowski physical clearance `r_phys` on 0.5-pixel sub-posts (`C3`).

    A 1 m pixel `[r, r+1] x [c, c+1]` remains navigable iff at least one `0.5`-pixel
    sub-post in `{r, r+0.5, r+1} x {c, c+0.5, c+1}` stands at Euclidean distance
    `>= clearance_m` from every solid obstacle pixel `[ro, ro+1] x [co, co+1]`.
    - Closes narrow gaps `< 1.5 m` (1-pixel `1.0 m` gap max clearance is `0.50 m < 0.85 m`).
    - Keeps corridors `>= 2.0 m` open (2-pixel `2.0 m` corridor centerline is `1.00 m >= 0.85 m`).
    """
    obs = np.asarray(raw_obstacle_mask, dtype=bool)
    if clearance_m <= 0.0 or not np.any(obs):
        return obs.copy()

    h, w = obs.shape
    rad_r = int(math.ceil(clearance_m / max(0.1, float(step_y_m)))) + 1
    rad_c = int(math.ceil(clearance_m / max(0.1, float(step_x_m)))) + 1

    # Sub-posts on a (2*h + 1) x (2*w + 1) half-pixel lattice (0.0, 0.5, 1.0, ...)
    sub_blocked = np.zeros((2 * h + 1, 2 * w + 1), dtype=bool)
    obs_r, obs_c = np.nonzero(obs)
    if len(obs_r) == 0:
        return obs.copy()

    # Precompute offsets in half-pixel units around a unit pixel [0, 2] x [0, 2]
    sub_offsets: list[tuple[int, int]] = []
    for ds_r in range(-2 * rad_r, 2 * rad_r + 3):
        # Distance from sub-post ds_r * 0.5 to interval [0.0, 1.0] in pixel units
        y_pos = 0.5 * float(ds_r)
        dy_px = 0.0 if 0.0 <= y_pos <= 1.0 else (0.0 - y_pos if y_pos < 0.0 else y_pos - 1.0)
        dy_m = dy_px * float(step_y_m)
        if dy_m >= clearance_m:
            continue
        for ds_c in range(-2 * rad_c, 2 * rad_c + 3):
            x_pos = 0.5 * float(ds_c)
            dx_px = 0.0 if 0.0 <= x_pos <= 1.0 else (0.0 - x_pos if x_pos < 0.0 else x_pos - 1.0)
            dx_m = dx_px * float(step_x_m)
            if math.hypot(dx_m, dy_m) < clearance_m - 1e-9:
                sub_offsets.append((ds_r, ds_c))

    sh, sw = sub_blocked.shape
    base_sr = 2 * obs_r
    base_sc = 2 * obs_c
    for ds_r, ds_c in sub_offsets:
        rr = base_sr + ds_r
        cc = base_sc + ds_c
        valid = (rr >= 0) & (rr < sh) & (cc >= 0) & (cc < sw)
        sub_blocked[rr[valid], cc[valid]] = True

    # A 1 m pixel (r, c) is blocked iff ALL 9 of its sub-posts {2r, 2r+1, 2r+2}x{2c, 2c+1, 2c+2}
    # violate physical clearance (so a 2 m corridor sharing seam 2c+2 stays open).
    s00 = sub_blocked[0 : 2 * h : 2, 0 : 2 * w : 2]
    s01 = sub_blocked[0 : 2 * h : 2, 1 : 2 * w + 1 : 2]
    s02 = sub_blocked[0 : 2 * h : 2, 2 : 2 * w + 2 : 2]
    s10 = sub_blocked[1 : 2 * h + 1 : 2, 0 : 2 * w : 2]
    s11 = sub_blocked[1 : 2 * h + 1 : 2, 1 : 2 * w + 1 : 2]
    s12 = sub_blocked[1 : 2 * h + 1 : 2, 2 : 2 * w + 2 : 2]
    s20 = sub_blocked[2 : 2 * h + 2 : 2, 0 : 2 * w : 2]
    s21 = sub_blocked[2 : 2 * h + 2 : 2, 1 : 2 * w + 1 : 2]
    s22 = sub_blocked[2 : 2 * h + 2 : 2, 2 : 2 * w + 2 : 2]
    all_nine_blocked = s00 & s01 & s02 & s10 & s11 & s12 & s20 & s21 & s22
    return obs | all_nine_blocked


def _filter_connected_components_min_area(mask: np.ndarray, min_pixels: int) -> np.ndarray:
    """Retain 8-connected obstacle blobs of area >= `min_pixels` (`~4 m x 4 m`, `C2`)."""
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    out = np.zeros((h, w), dtype=bool)
    rs, cs = np.nonzero(mask)
    for r_start, c_start in zip(rs.tolist(), cs.tolist(), strict=False):
        if visited[r_start, c_start]:
            continue
        stack = [(r_start, c_start)]
        visited[r_start, c_start] = True
        comp: list[tuple[int, int]] = []
        while stack:
            cr, cc = stack.pop()
            comp.append((cr, cc))
            for dr in (-1, 0, 1):
                nr = cr + dr
                if nr < 0 or nr >= h:
                    continue
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    nc = cc + dc
                    if 0 <= nc < w and mask[nr, nc] and not visited[nr, nc]:
                        visited[nr, nc] = True
                        stack.append((nr, nc))
        if len(comp) >= min_pixels:
            for cr, cc in comp:
                out[cr, cc] = True
    return out


def compute_4m_slope_deg_array(
    elev_m: np.ndarray, step_x_m: float, step_y_m: float = 1.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute 4 m baseline ground-metric gradients `(gx, gy)` and slope angle (deg)."""
    # 2-pixel half-step -> 4 m central difference baseline
    pad = np.pad(elev_m, pad_width=2, mode="edge")
    gx = (pad[2:-2, 4:] - pad[2:-2, :-4]) / (4.0 * float(step_x_m))
    gy = (pad[:-4, 2:-2] - pad[4:, 2:-2]) / (4.0 * float(step_y_m))
    slope_deg = np.degrees(np.arctan(np.hypot(gx, gy)))
    return gx, gy, slope_deg


def extract_formations_and_scarps_1m(
    elev_m: np.ndarray,
    center_lat_deg: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Extract `>= ~4 m` rock formations and scarps > 20 deg on a 1 m/px DTM (`M1`).

    Returns `(buffered_obstacle_mask_1m, slope_4m_deg, gx_4m, gy_4m)`.
    """
    dx_m = ground_step_x_m(center_lat_deg, 1.0)
    gx_4m, gy_4m, slope_4m_deg = compute_4m_slope_deg_array(elev_m, step_x_m=dx_m, step_y_m=1.0)
    opened = grey_opening_2d(elev_m, window=FORMATION_TOPHAT_WINDOW_PX)
    tophat_m = elev_m - opened

    scarp_raw = slope_4m_deg > EVA_SUIT_MAX_SLOPE_DEG
    knob_raw = (tophat_m >= FORMATION_TOPHAT_RELIEF_MIN_M) & (slope_4m_deg >= 16.5)
    combined_raw = _filter_connected_components_min_area(
        scarp_raw | knob_raw,
        min_pixels=FORMATION_MIN_AREA_PX,
    )
    buffered = apply_physical_clearance_buffer_1m(
        combined_raw,
        step_x_m=dx_m,
        step_y_m=1.0,
        clearance_m=PHYSICAL_CLEARANCE_RADIUS_M,
    )
    return buffered, slope_4m_deg, gx_4m, gy_4m


def _fast_median_and_p90(sub_slp: np.ndarray) -> tuple[float, float]:
    """Exact NumPy-compatible linear-interpolated median (p50) and p90 without dispatch overhead."""
    vals = sorted(sub_slp.ravel().tolist())
    n = len(vals)
    if n == 1:
        return (vals[0], vals[0])
    pos50 = 0.50 * (n - 1)
    i50 = int(pos50)
    f50 = pos50 - i50
    med = vals[i50] + f50 * (vals[min(n - 1, i50 + 1)] - vals[i50])

    pos90 = 0.90 * (n - 1)
    i90 = int(pos90)
    f90 = pos90 - i90
    p90 = vals[i90] + f90 * (vals[min(n - 1, i90 + 1)] - vals[i90])
    return (med, p90)


def build_planner_grid_10m_from_window(
    dtm_elev_m: np.ndarray,
    transform_x_min_m: float,
    transform_y_max_m: float,
    bbox: tuple[float, float, float, float],
    rows: int = PLANNER_GRID_ROWS_10M,
    cols: int = PLANNER_GRID_COLS_10M,
) -> tuple[PlannerGrid10m, dict[str, Any]]:
    """Build the 200x190 (~10 m) planning grid and `obstacles.geojson` payload (`M1`).

    Zero cross-cell 7.07 m dilation (`C3`): each 10 m cell aggregates strictly its own
    ground footprint inside `bbox`.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    center_lat = 0.5 * (min_lat + max_lat)
    cos_phi = ground_step_x_m(center_lat, 1.0)

    x0_m = lon_to_eqc_x_m(min_lon)
    x1_m = lon_to_eqc_x_m(max_lon)
    y0_m = lat_to_eqc_y_m(min_lat)
    y1_m = lat_to_eqc_y_m(max_lat)

    c_px0 = max(0, int(round(x0_m - transform_x_min_m)))
    c_px1 = min(dtm_elev_m.shape[1], int(round(x1_m - transform_x_min_m)))
    r_px0 = max(0, int(round(transform_y_max_m - y1_m)))
    r_px1 = min(dtm_elev_m.shape[0], int(round(transform_y_max_m - y0_m)))

    win_elev = dtm_elev_m[r_px0:r_px1, c_px0:c_px1]
    obs_1m, slope_4m, gx_4m, gy_4m = extract_formations_and_scarps_1m(win_elev, center_lat)
    wh, ww = win_elev.shape

    blocked = np.zeros((rows, cols), dtype=bool)
    caution = np.zeros((rows, cols), dtype=bool)
    toe_refuge = np.zeros((rows, cols), dtype=bool)
    gx_grid = np.zeros((rows, cols), dtype=np.float64)
    gy_grid = np.zeros((rows, cols), dtype=np.float64)
    risk_grid = np.zeros((rows, cols), dtype=np.float64)

    r_edges = np.linspace(0, wh, rows + 1, dtype=int)
    c_edges = np.linspace(0, ww, cols + 1, dtype=int)

    for r in range(rows):
        ra, rb = int(r_edges[r]), max(int(r_edges[r]) + 1, int(r_edges[r + 1]))
        for c in range(cols):
            ca, cb = int(c_edges[c]), max(int(c_edges[c]) + 1, int(c_edges[c + 1]))
            sub_obs = obs_1m[ra:rb, ca:cb]
            sub_slp = slope_4m[ra:rb, ca:cb]
            sub_gx = gx_4m[ra:rb, ca:cb]
            sub_gy = gy_4m[ra:rb, ca:cb]
            sub_z = win_elev[ra:rb, ca:cb]

            obs_frac = float(sub_obs.mean())
            med_slp, p90_slp = _fast_median_and_p90(sub_slp)
            relief_m = float(sub_z.max() - sub_z.min())

            # Cell is blocked iff scarp/formation covers >= 25% of cell or median slope > 20 deg
            is_blocked = (obs_frac >= 0.25) or (med_slp > EVA_SUIT_MAX_SLOPE_DEG)
            is_caution = (not is_blocked) and (p90_slp >= 12.0 or obs_frac >= 0.05)

            blocked[r, c] = is_blocked
            caution[r, c] = is_caution
            gx_grid[r, c] = float(np.clip(np.mean(sub_gx), -GRAD_CLIP_MAX, GRAD_CLIP_MAX))
            gy_grid[r, c] = float(np.clip(np.mean(sub_gy), -GRAD_CLIP_MAX, GRAD_CLIP_MAX))
            # DTM 3-4 post slope uncertainty boost near 15-20 deg boundary
            boundary_i = 0.20 * math.exp(-(((p90_slp - 20.0) / 5.5) ** 2))
            risk_val = min(1.0, (med_slp / 20.0) * 0.55 + obs_frac * 0.6 + boundary_i)
            risk_grid[r, c] = risk_val

            if not is_blocked and relief_m >= 2.2:
                toe_refuge[r, c] = True

    # Also mark navigable cells immediately adjacent to a >= 5 m scarp cell as toe_refuge
    cell_z = np.zeros((rows, cols), dtype=np.float64)
    for r in range(rows):
        ra, rb = int(r_edges[r]), max(int(r_edges[r]) + 1, int(r_edges[r + 1]))
        for c in range(cols):
            ca, cb = int(c_edges[c]), max(int(c_edges[c]) + 1, int(c_edges[c + 1]))
            cell_z[r, c] = float(np.mean(win_elev[ra:rb, ca:cb]))

    for r in range(1, rows - 1):
        for c in range(1, cols - 1):
            if blocked[r, c]:
                continue
            nbr_z_max = float(np.max(cell_z[r - 1 : r + 2, c - 1 : c + 2]))
            if nbr_z_max - cell_z[r, c] >= 4.0:
                toe_refuge[r, c] = True

    step_x_g = ((x1_m - x0_m) * cos_phi) / float(cols)
    step_y_g = (y1_m - y0_m) / float(rows)

    grid = PlannerGrid10m(
        rows=rows,
        cols=cols,
        bbox=bbox,
        step_x_ground_m=round(step_x_g, 6),
        step_y_ground_m=round(step_y_g, 6),
        blocked_mask=blocked,
        caution_mask=caution,
        toe_refuge_mask=toe_refuge,
        grad_x=gx_grid,
        grad_y=gy_grid,
        risk_penalty_01=risk_grid,
    )
    obstacles_geojson = _extract_obstacle_polygons_geojson(grid, cell_z)
    return grid, obstacles_geojson


def _extract_obstacle_polygons_geojson(
    grid: PlannerGrid10m,
    cell_z: np.ndarray,
    max_features: int = 120,
) -> dict[str, Any]:
    """Build compact GeoJSON bounding polygons of major connected scarp/formation clusters."""
    min_lon, min_lat, max_lon, max_lat = grid.bbox
    dlon = (max_lon - min_lon) / float(grid.cols)
    dlat = (max_lat - min_lat) / float(grid.rows)

    visited = np.zeros((grid.rows, grid.cols), dtype=bool)
    clusters: list[list[tuple[int, int]]] = []
    for r in range(grid.rows):
        for c in range(grid.cols):
            if not grid.blocked_mask[r, c] or visited[r, c]:
                continue
            stack = [(r, c)]
            visited[r, c] = True
            comp: list[tuple[int, int]] = []
            while stack:
                cr, cc = stack.pop()
                comp.append((cr, cc))
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        nr, nc = cr + dr, cc + dc
                        if (
                            0 <= nr < grid.rows
                            and 0 <= nc < grid.cols
                            and grid.blocked_mask[nr, nc]
                            and not visited[nr, nc]
                        ):
                            visited[nr, nc] = True
                            stack.append((nr, nc))
            if len(comp) >= 2:
                clusters.append(comp)

    clusters.sort(key=len, reverse=True)
    features: list[dict[str, Any]] = []
    for idx, comp in enumerate(clusters[:max_features], start=1):
        rs = [p[0] for p in comp]
        cs = [p[1] for p in comp]
        r_min, r_max = min(rs), max(rs)
        c_min, c_max = min(cs), max(cs)
        lon0 = round(min_lon + c_min * dlon, 6)
        lon1 = round(min_lon + (c_max + 1) * dlon, 6)
        lat1 = round(max_lat - r_min * dlat, 6)
        lat0 = round(max_lat - (r_max + 1) * dlat, 6)

        zs = [cell_z[r, c] for r, c in comp]
        relief_m = round(max(zs) - min(zs), 2)
        area_m2 = round(len(comp) * grid.step_x_ground_m * grid.step_y_ground_m, 1)
        obs_kind = "scarp" if len(comp) >= 8 or relief_m >= 5.0 else "large_rock_formation"
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [lon0, lat0],
                            [lon1, lat0],
                            [lon1, lat1],
                            [lon0, lat1],
                            [lon0, lat0],
                        ]
                    ],
                },
                "properties": {
                    "obstacle_id": f"OBS-JEZ-{idx:03d}",
                    "obstacle_type": obs_kind,
                    "tag": "DERIVED",
                    "source_id": "SRC-USGS-HIRISE-DTM-1M",
                    "footprint_area_m2": area_m2,
                    "internal_relief_m": relief_m,
                    "physical_clearance_m": PHYSICAL_CLEARANCE_RADIUS_M,
                    "resolution_note": (
                        "Derived from 1 m/px HiRISE DTM (~3-4 post effective horizontal "
                        "resolution; resolves formations >= ~4 m only)."
                    ),
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "contract_version": "1.1.0",
        "site_id": "jezero",
        "ono_rover_cfa_reference_pct": {
            "ok_pct": ROVER_CFA_OK_PCT,
            "caution_pct": ROVER_CFA_CAUTION_PCT,
            "golombek_1p5m_at_15pct": round(
                golombek_cumulative_fractional_area(1.5, ROVER_CFA_CAUTION_PCT / 100.0), 6
            ),
        },
        "features": features,
    }


def save_planner_grid_10m_png(grid: PlannerGrid10m, png_path: Path) -> None:
    """Encode `PlannerGrid10m` losslessly into an 8-bit RGBA PNG (~15-35 KB)."""
    flags = (
        grid.blocked_mask.astype(np.uint8)
        | (grid.caution_mask.astype(np.uint8) << 1)
        | (grid.toe_refuge_mask.astype(np.uint8) << 2)
    )
    gx_u8 = np.rint(
        (
            (np.clip(grid.grad_x, -GRAD_CLIP_MAX, GRAD_CLIP_MAX) + GRAD_CLIP_MAX)
            / (2.0 * GRAD_CLIP_MAX)
        )
        * 254.0
    ).astype(np.uint8)
    gy_u8 = np.rint(
        (
            (np.clip(grid.grad_y, -GRAD_CLIP_MAX, GRAD_CLIP_MAX) + GRAD_CLIP_MAX)
            / (2.0 * GRAD_CLIP_MAX)
        )
        * 254.0
    ).astype(np.uint8)
    risk_u8 = np.rint(np.clip(grid.risk_penalty_01, 0.0, 1.0) * 255.0).astype(np.uint8)

    rgba = np.stack([flags, gx_u8, gy_u8, risk_u8], axis=-1)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.fromarray(rgba, mode="RGBA")
    img.save(png_path, format="PNG", optimize=False, compress_level=6)


def load_planner_grid_10m_png(
    png_path: Path,
    bbox: tuple[float, float, float, float],
) -> PlannerGrid10m:
    """Decode `planner_grid_10m.png` back into `PlannerGrid10m` with dynamic `cos(phi)`."""
    with Image.open(png_path) as img:
        rgba = np.asarray(img.convert("RGBA"), dtype=np.uint8)
    rows, cols, _ = rgba.shape
    flags = rgba[:, :, 0]
    blocked = (flags & 1) != 0
    caution = (flags & 2) != 0
    toe_refuge = (flags & 4) != 0
    gx = (rgba[:, :, 1].astype(np.float64) / 254.0) * (2.0 * GRAD_CLIP_MAX) - GRAD_CLIP_MAX
    gy = (rgba[:, :, 2].astype(np.float64) / 254.0) * (2.0 * GRAD_CLIP_MAX) - GRAD_CLIP_MAX
    risk = rgba[:, :, 3].astype(np.float64) / 255.0

    min_lon, min_lat, max_lon, max_lat = bbox
    center_lat = 0.5 * (min_lat + max_lat)
    cos_phi = ground_step_x_m(center_lat, 1.0)
    x_span_g = (lon_to_eqc_x_m(max_lon) - lon_to_eqc_x_m(min_lon)) * cos_phi
    y_span_g = lat_to_eqc_y_m(max_lat) - lat_to_eqc_y_m(min_lat)

    return PlannerGrid10m(
        rows=rows,
        cols=cols,
        bbox=bbox,
        step_x_ground_m=round(x_span_g / float(cols), 6),
        step_y_ground_m=round(y_span_g / float(rows), 6),
        blocked_mask=blocked,
        caution_mask=caution,
        toe_refuge_mask=toe_refuge,
        grad_x=gx,
        grad_y=gy,
        risk_penalty_01=risk,
    )


def validate_m1_against_ground_truth(
    dtm_elev_m: np.ndarray,
    transform_x_min_m: float,
    transform_y_max_m: float,
    bbox: tuple[float, float, float, float],
    waypoints_features: list[Any],
) -> M1GroundTruthValidation:
    """Validate M1 specificity on even sols (`147` stops) and recall on SIM 3464 scarp (`C1`)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    center_lat = 0.5 * (min_lat + max_lat)
    x0_m = lon_to_eqc_x_m(min_lon)
    x1_m = lon_to_eqc_x_m(max_lon)
    y0_m = lat_to_eqc_y_m(min_lat)
    y1_m = lat_to_eqc_y_m(max_lat)

    c_px0 = max(0, int(round(x0_m - transform_x_min_m)))
    c_px1 = min(dtm_elev_m.shape[1], int(round(x1_m - transform_x_min_m)))
    r_px0 = max(0, int(round(transform_y_max_m - y1_m)))
    r_px1 = min(dtm_elev_m.shape[0], int(round(transform_y_max_m - y0_m)))

    win_elev = dtm_elev_m[r_px0:r_px1, c_px0:c_px1]
    obs_1m, slope_4m, _, _ = extract_formations_and_scarps_1m(win_elev, center_lat)
    wh, ww = win_elev.shape

    in_win_stops: list[Any] = []
    for wp in waypoints_features:
        lon = wp.properties.lon
        lat = wp.properties.lat
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            in_win_stops.append(wp)

    even_gentle_total = 0
    even_false_pos = 0
    sol_700_max_slope = 0.0

    for wp in in_win_stops:
        wx = lon_to_eqc_x_m(wp.properties.lon)
        wy = lat_to_eqc_y_m(wp.properties.lat)
        cc = max(2, min(ww - 3, int(round(wx - x0_m))))
        rr = max(2, min(wh - 3, int(round(y1_m - wy))))
        tilt_deg = float(wp.properties.rover_tilt_deg.value)
        sol_num = int(wp.properties.sol)

        if sol_num == 700:
            local_max_s4 = float(np.max(slope_4m[rr - 2 : rr + 3, cc - 2 : cc + 3]))
            sol_700_max_slope = max(sol_700_max_slope, local_max_s4, tilt_deg)

        # Specificity measured strictly on EVEN sols with rover_tilt_deg < 15 deg (`C1`)
        if sol_num % 2 == 0 and tilt_deg < 15.0:
            even_gentle_total += 1
            if bool(obs_1m[rr, cc]):
                even_false_pos += 1

    spec = (
        (even_gentle_total - even_false_pos) / float(even_gentle_total)
        if even_gentle_total > 0
        else 1.0
    )

    # Independent sensitivity reference (`C1`): SIM 3464 lower delta margin (`Nle`/`NHjf1`)
    # pixels exhibiting >= 6.0 m local vertical drop over 16 m (independent stratigraphic scarp)
    pad8 = np.pad(win_elev, pad_width=8, mode="edge")
    relief_16m = np.maximum(
        np.abs(pad8[8:-8, 16:] - pad8[8:-8, :-16]),
        np.abs(pad8[:-16, 8:-8] - pad8[16:, 8:-8]),
    )
    scarp_ref_count = 0
    scarp_hit_count = 0
    for rr in range(8, wh - 8, 4):
        lat_r = eqc_y_m_to_lat(y1_m - float(rr))
        for cc in range(8, ww - 8, 4):
            if relief_16m[rr, cc] < 6.0:
                continue
            lon_c = eqc_x_m_to_lon(x0_m + float(cc))
            unit_str = classify_sim3464_unit(lon_c, lat_r, float(win_elev[rr, cc]), 20.0)
            if unit_str.startswith(("NHjf1", "Nle", "NHjf2")):
                scarp_ref_count += 1
                if bool(np.any(obs_1m[rr - 1 : rr + 2, cc - 1 : cc + 2])):
                    scarp_hit_count += 1

    recall = scarp_hit_count / float(scarp_ref_count) if scarp_ref_count > 0 else 0.0
    return M1GroundTruthValidation(
        total_window_stops=len(in_win_stops),
        even_sol_gentle_stops=even_gentle_total,
        even_sol_false_positives=even_false_pos,
        even_sol_specificity=round(spec, 4),
        sim3464_scarp_margin_pixels=scarp_ref_count,
        sim3464_scarp_detected_pixels=scarp_hit_count,
        sim3464_scarp_recall=round(recall, 4),
        sol_700_slope_4m_deg=round(sol_700_max_slope, 4),
        sol_700_exceeds_20deg_limit=bool(sol_700_max_slope >= EVA_SUIT_MAX_SLOPE_DEG),
        ono_rover_cfa_reference_pct=(ROVER_CFA_OK_PCT, ROVER_CFA_CAUTION_PCT),
    )
