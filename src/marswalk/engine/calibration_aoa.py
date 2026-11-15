"""Phase 3 Spatial-Block Declustering, Meyer & Pebesma (2021) AOA Gate & Josang Opinion (T06).

Implements:
- `josang_opinion(r, s, n_eff, inside_aoa=True)` (`P7` / `C6`):
  Josang (2016; FUSION 2022) Subjective Logic binomial opinion `(t, f, i)` where:
  - Raw correlated counts `(r, s)` are capped to the number of spatially decorrelated blocks
    `n_eff` so the epistemic uncertainty floor `i >= W / (n_eff + W)` (`W = 2.0`) never
    collapses to zero from rover stop oversampling.
  - Outside the Area of Applicability (`inside_aoa=False`) or when variogram range exceeds
    half the window (`n_eff <= 0`), returns the vacuous opinion `(0.0, 0.0, 1.0)`.
- `fit_spatial_aoa_model(...)` & `evaluate_cell_aoa_and_opinion(...)`:
  Meyer & Pebesma (2021, Methods Ecol. Evol. 12:1620-1633) standardized Euclidean
  Dissimilarity Index `DI(x) = d_min(x) / mean_train_dist` (normalized by the mean
  cross-block nearest-neighbor distance in training space) and distance-weighted evidence
  aggregation `(r(x), s(x))` from independent spatial-block labels.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from marswalk.contracts.models import ConfidenceVector


@dataclass(frozen=True)
class SpatialAoaModel:
    """Calibrated Meyer & Pebesma (2021) Area of Applicability & spatial block parameters."""

    variogram_range_m: float
    window_span_m: float
    cv_feasible: bool
    n_eff_blocks: int
    mean_train_dist: float
    di_threshold: float
    feature_mean: tuple[float, ...]
    feature_std: tuple[float, ...]
    train_norm_features: np.ndarray
    block_norm_centers: np.ndarray
    block_hazard_labels: np.ndarray
    train_block_hazard_rate: float


def josang_opinion(
    r: float,
    s: float,
    n_eff: int | float,
    inside_aoa: bool = True,
    prior_weight: float = 2.0,
) -> tuple[float, float, float]:
    """Return Josang Subjective Logic `(t, f, i)` with declustered `n_eff` cap (`P7` / `C6`)."""
    if not inside_aoa or float(n_eff) <= 0.0:
        return (0.0, 0.0, 1.0)

    r_pos = max(0.0, float(r))
    s_pos = max(0.0, float(s))
    n_cap = max(0.0, float(n_eff))
    w = max(1e-6, float(prior_weight))

    raw_sum = r_pos + s_pos
    if raw_sum <= 0.0:
        return (0.0, 0.0, 1.0)

    if raw_sum > n_cap:
        scale = n_cap / raw_sum
        r_eff = r_pos * scale
        s_eff = s_pos * scale
    else:
        r_eff = r_pos
        s_eff = s_pos

    total = r_eff + s_eff + w
    t_val = s_eff / total
    f_val = r_eff / total
    i_val = w / total
    return (t_val, f_val, i_val)


def estimate_variogram_range_m(
    coords_xy_m: np.ndarray,
    values: np.ndarray,
    max_lag_m: float = 800.0,
    n_bins: int = 8,
) -> float:
    """Estimate empirical semivariogram range h_r (m) where semivariance reaches 90% of sill."""
    n = len(values)
    if n < 6:
        return 180.0

    diffs_d: list[float] = []
    diffs_g: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            d = float(
                math.hypot(
                    coords_xy_m[i, 0] - coords_xy_m[j, 0], coords_xy_m[i, 1] - coords_xy_m[j, 1]
                )
            )
            if 1.0 <= d <= max_lag_m:
                diffs_d.append(d)
                diffs_g.append(0.5 * float((values[i] - values[j]) ** 2))

    if len(diffs_d) < 10:
        return 180.0

    d_arr = np.asarray(diffs_d, dtype=np.float64)
    g_arr = np.asarray(diffs_g, dtype=np.float64)
    edges = np.linspace(0.0, max_lag_m, n_bins + 1)
    bin_centers: list[float] = []
    bin_gammas: list[float] = []
    for b in range(n_bins):
        mask = (d_arr >= edges[b]) & (d_arr < edges[b + 1])
        if int(np.count_nonzero(mask)) >= 3:
            bin_centers.append(0.5 * float(edges[b] + edges[b + 1]))
            bin_gammas.append(float(np.mean(g_arr[mask])))

    if len(bin_gammas) < 2:
        return 180.0

    sill = max(bin_gammas)
    target = 0.90 * sill
    for center, g_val in zip(bin_centers, bin_gammas, strict=False):
        if g_val >= target:
            return round(max(80.0, min(600.0, center)), 1)
    return round(max(120.0, min(450.0, bin_centers[-1])), 1)


def fit_spatial_aoa_model(
    orbital_features: np.ndarray,
    coords_xy_m: np.ndarray,
    variogram_response: np.ndarray,
    independent_hazard_labels: np.ndarray | None = None,
    window_span_m: float = 1897.0,
) -> SpatialAoaModel:
    """Fit Meyer & Pebesma (2021) AOA gate and declustered block centers on independent labels."""
    n = orbital_features.shape[0]
    d_dim = orbital_features.shape[1] if orbital_features.ndim == 2 else 4
    if n < 3:
        return SpatialAoaModel(
            variogram_range_m=200.0,
            window_span_m=window_span_m,
            cv_feasible=True,
            n_eff_blocks=1,
            mean_train_dist=1.0,
            di_threshold=2.5,
            feature_mean=tuple(0.0 for _ in range(d_dim)),
            feature_std=tuple(1.0 for _ in range(d_dim)),
            train_norm_features=np.zeros((1, d_dim), dtype=np.float64),
            block_norm_centers=np.zeros((1, d_dim), dtype=np.float64),
            block_hazard_labels=np.array([0.1], dtype=np.float64),
            train_block_hazard_rate=0.1,
        )

    h_r = estimate_variogram_range_m(coords_xy_m, variogram_response)
    cv_feasible = h_r <= 0.5 * float(window_span_m)

    block_side = max(80.0, h_r)
    bx = np.floor((coords_xy_m[:, 0] - np.min(coords_xy_m[:, 0])) / block_side).astype(int)
    by = np.floor((coords_xy_m[:, 1] - np.min(coords_xy_m[:, 1])) / block_side).astype(int)
    block_ids = list(zip(bx.tolist(), by.tolist(), strict=False))
    unique_blocks = sorted(set(block_ids))
    n_eff = len(unique_blocks) if cv_feasible else 0

    f_mean = np.mean(orbital_features, axis=0)
    f_std = np.maximum(1e-3, np.std(orbital_features, axis=0))
    norm_f = (orbital_features - f_mean) / f_std

    # Cross-block nearest-neighbor distances in standardized predictor space
    nn_dists: list[float] = []
    for i in range(n):
        dists = [
            float(np.linalg.norm(norm_f[i] - norm_f[j]))
            for j in range(n)
            if block_ids[j] != block_ids[i]
        ]
        if not dists:
            dists = [float(np.linalg.norm(norm_f[i] - norm_f[j])) for j in range(n) if j != i]
        if dists:
            nn_dists.append(min(dists))

    mean_train_d = max(1e-4, float(np.mean(nn_dists)) if nn_dists else 1.0)
    di_vals = [d / mean_train_d for d in nn_dists] if nn_dists else [1.0]
    q75 = float(np.percentile(di_vals, 75))
    q25 = float(np.percentile(di_vals, 25))
    di_thresh = max(1.35, q75 + 1.5 * max(0.25, q75 - q25))

    if independent_hazard_labels is not None and len(independent_hazard_labels) == n:
        raw_labels = np.clip(np.asarray(independent_hazard_labels, dtype=np.float64), 0.0, 1.0)
    else:
        # Independent spatial-sampling density / step-spacing proxy when no label array is passed
        raw_labels = np.zeros(n, dtype=np.float64)
        for i in range(n):
            other_d = [
                math.hypot(
                    coords_xy_m[i, 0] - coords_xy_m[j, 0], coords_xy_m[i, 1] - coords_xy_m[j, 1]
                )
                for j in range(n)
                if j != i
            ]
            nearest_step_m = min(other_d) if other_d else 25.0
            # Rover takes short < 12 m drives when navigating rough/complex outcrops
            raw_labels[i] = 1.0 if nearest_step_m < 12.0 else 0.15

    block_centers: list[np.ndarray] = []
    block_labels: list[float] = []
    for blk in unique_blocks:
        idxs = [i for i, b_id in enumerate(block_ids) if b_id == blk]
        block_centers.append(np.mean(norm_f[idxs], axis=0))
        block_labels.append(float(np.mean(raw_labels[idxs])))

    centers_arr = np.asarray(block_centers, dtype=np.float64)
    labels_arr = np.asarray(block_labels, dtype=np.float64)
    hazard_rate = float(np.mean(labels_arr)) if len(labels_arr) > 0 else 0.15

    return SpatialAoaModel(
        variogram_range_m=h_r,
        window_span_m=window_span_m,
        cv_feasible=cv_feasible,
        n_eff_blocks=n_eff,
        mean_train_dist=round(mean_train_d, 6),
        di_threshold=round(di_thresh, 4),
        feature_mean=tuple(float(x) for x in f_mean),
        feature_std=tuple(float(x) for x in f_std),
        train_norm_features=norm_f,
        block_norm_centers=centers_arr,
        block_hazard_labels=labels_arr,
        train_block_hazard_rate=round(hazard_rate, 4),
    )


def compute_cell_aoa_di(
    model: SpatialAoaModel,
    cell_feature_vec: tuple[float, ...] | list[float],
) -> float:
    """Compute normalized Dissimilarity Index DI(x) = d_min(x) / mean_train_dist (`H2.a`)."""
    mean_arr = np.asarray(model.feature_mean, dtype=np.float64)
    std_arr = np.asarray(model.feature_std, dtype=np.float64)
    vec_norm = (np.asarray(cell_feature_vec, dtype=np.float64) - mean_arr) / std_arr
    dists = np.linalg.norm(model.train_norm_features - vec_norm, axis=1)
    return float(np.min(dists)) / max(1e-6, float(model.mean_train_dist))


def evaluate_cell_aoa_and_opinion(
    model: SpatialAoaModel,
    cell_feature_vec: tuple[float, float, float, float],
    local_contradiction_f: float | None = None,
) -> tuple[bool, ConfidenceVector]:
    """Evaluate normalized AOA membership and distance-weighted Josang block opinion (`H2`).

    Uses kernel weights `w_b(x) = exp(-0.85 * d_b(x) / mean_train_dist)` across the
    `n_eff_blocks` spatially declustered blocks and their independent block hazard labels,
    so:
    1. DI(x) and `di_threshold` share identical normalized units (`d / mean_train_dist`).
    2. Evidence counts `(r(x), s(x))` come from independent training blocks (never circularly
       from the cell's own funnel `f`).
    3. Total effective sample support `r(x) + s(x) <= n_eff_blocks` varies continuously across
       feature space, producing continuous `calibrated_opinion.i` values in `[2/(n_eff+2), 1.0]`.
    """
    _ = local_contradiction_f  # Strictly unused to prevent circular self-calibration (`H2.c`)
    if not model.cv_feasible or model.n_eff_blocks <= 0:
        return (False, ConfidenceVector(t=0.0, i=1.0, f=0.0))

    di_val = compute_cell_aoa_di(model, cell_feature_vec)
    inside_aoa = bool(di_val <= model.di_threshold)
    if not inside_aoa:
        return (False, ConfidenceVector(t=0.0, i=1.0, f=0.0))

    mean_arr = np.asarray(model.feature_mean, dtype=np.float64)
    std_arr = np.asarray(model.feature_std, dtype=np.float64)
    vec_norm = (np.asarray(cell_feature_vec, dtype=np.float64) - mean_arr) / std_arr

    block_dists = np.linalg.norm(model.block_norm_centers - vec_norm, axis=1) / max(
        1e-6, float(model.mean_train_dist)
    )
    weights = np.exp(-0.85 * block_dists)
    r_count = float(np.sum(weights * model.block_hazard_labels))
    s_count = float(np.sum(weights * (1.0 - model.block_hazard_labels)))

    t_val, f_val, i_val = josang_opinion(
        r=r_count,
        s=s_count,
        n_eff=model.n_eff_blocks,
        inside_aoa=True,
    )
    return (
        True,
        ConfidenceVector(
            t=round(t_val, 4),
            i=round(i_val, 4),
            f=round(f_val, 4),
        ),
    )
