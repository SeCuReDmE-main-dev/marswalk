"""10-Carrier Terrain Vector (`I_terrain`) Modeled on `I_neutrino_vec`.

Implements Section 3 of `MOTEUR_PLITHOGENIQUE_SWEET_SPOT_MARTIAN_MAP_14_11_26.md`:
1. `I_source`      : Provenance trust (HiRISE 1m DTM vs coarse/synthetic) [MEASURED]
2. `I_scale`       : Spatial baseline index in {4, 16, 64} m (< 2x res rejected) [declared]
3. `I_slope`       : Baseline terrain slope in [0, 20] deg (NASA xEVA limit) [DERIVED]
4. `I_rough`       : Plane-detrended RMS roughness in [0, 0.10] m (10 cm ripple) [DERIVED]
5. `I_fractal`     : Variogram fractal dimension D = 3 - H in [2.0, 3.0] [DERIVED]
6. `I_diverge`     : Slope difference across neighboring scales in [0, 10] deg [DERIVED]
7. `I_texture`     : Laplacian curvature proxy for boulders/ripples in [0, 0.25] 1/m [DERIVED]
8. `I_constraint`  : Distance to NASA xEVA 2,000 m walkback boundary [0, 2000] m [rule]
9. `I_coverage`    : Empty / interpolated / seam pixel fraction in [0, 1] [MEASURED]
10. `I_uncertainty`: Traceability carrier summarizing scale + coverage ambiguity [traceability]

CRITICAL INVARIANT (R2):
Ground-truth IMU vehicle inclination is NEVER a carrier and is NEVER read in this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from marswalk.engine.funnel import CarrierScaleTriplet
from marswalk.engine.prefilter import prefilter_scale

REQUIRED_CARRIERS: tuple[str, ...] = (
    "I_source",
    "I_scale",
    "I_slope",
    "I_rough",
    "I_fractal",
    "I_diverge",
    "I_texture",
    "I_constraint",
    "I_coverage",
    "I_uncertainty",
)


@dataclass(frozen=True)
class CarrierSpec:
    """Declared normalization bounds `[x_min, x_max]` and provenance status for a carrier."""

    name: str
    x_min: float
    x_max: float
    status: str
    unit: str


CARRIER_SPECS: dict[str, CarrierSpec] = {
    "I_source": CarrierSpec("I_source", 0.0, 1.0, "MEASURED", "index"),
    "I_scale": CarrierSpec("I_scale", 0.0, 64.0, "DECLARED", "m"),
    "I_slope": CarrierSpec("I_slope", 0.0, 20.0, "DERIVED", "deg"),
    "I_rough": CarrierSpec("I_rough", 0.0, 0.10, "DERIVED", "m"),
    "I_fractal": CarrierSpec("I_fractal", 2.0, 3.0, "DERIVED", "dim"),
    "I_diverge": CarrierSpec("I_diverge", 0.0, 10.0, "DERIVED", "deg"),
    "I_texture": CarrierSpec("I_texture", 0.0, 0.25, "DERIVED_PROXY", "1/m"),
    "I_constraint": CarrierSpec("I_constraint", 0.0, 2000.0, "RULE", "m"),
    "I_coverage": CarrierSpec("I_coverage", 0.0, 1.0, "MEASURED", "ratio"),
    "I_uncertainty": CarrierSpec("I_uncertainty", 0.0, 1.0, "TRACEABILITY", "index"),
}


def clamp01(value: float) -> float:
    """Clamp a scalar float strictly into `[0.0, 1.0]`."""
    if not math.isfinite(value):
        return 1.0
    return max(0.0, min(1.0, value))


def normalize_x_hat(carrier_name: str, raw_value: float) -> float:
    """Normalize `raw_value` into `[0, 1]` using the carrier's declared `[x_min, x_max]`."""
    spec = CARRIER_SPECS[carrier_name]
    denom = spec.x_max - spec.x_min
    if denom <= 0.0:
        return 0.0
    return clamp01((raw_value - spec.x_min) / denom)


def validate_carrier_names(
    carrier_names: tuple[str, ...] | list[str],
    *,
    allow_ablation_subset: bool = False,
) -> tuple[str, ...]:
    """Validate the 10 required terrain carriers (rejects missing carriers unless ablating)."""
    names_tuple = tuple(carrier_names)
    unknown = [c for c in names_tuple if c not in CARRIER_SPECS]
    if unknown:
        raise ValueError(f"Unknown terrain carrier(s): {unknown}")
    if not allow_ablation_subset and set(names_tuple) != set(REQUIRED_CARRIERS):
        missing = sorted(set(REQUIRED_CARRIERS) - set(names_tuple))
        raise ValueError(f"Missing required terrain carrier(s): {missing}")
    if len(names_tuple) == 0:
        raise ValueError("At least one carrier is required.")
    return names_tuple


def compute_patch_roughness_fractal_texture(
    patch_elev_m: np.ndarray,
    pixel_size_m: float = 1.0,
) -> tuple[float, float, float]:
    """Derive `(roughness_rms_m, fractal_d, curvature_m_inv)` from a 2D DTM elevation patch.

    - `roughness_rms_m`: RMS residual (m) after subtracting a least-squares planar trend.
    - `fractal_d`: Surface fractal dimension `D = 3 - H` in `[2.0, 3.0]` estimated from
      the isotropic variogram `gamma(h) ~ h^(2H)` across lags `h in {1, 2, 4}` pixels
      (Taud & Parrot 2005; NASA PGDA Hurst method).
    - `curvature_m_inv`: Mean absolute discrete Laplacian `|d2z/dx2 + d2z/dy2|` (1/m).
    """
    h, w = patch_elev_m.shape
    if h < 5 or w < 5:
        return (0.015, 2.25, 0.02)

    yy, xx = np.mgrid[0:h, 0:w]
    a_mat = np.column_stack([xx.ravel() * pixel_size_m, yy.ravel() * pixel_size_m, np.ones(h * w)])
    z_vec = patch_elev_m.ravel()
    coeffs, _, _, _ = np.linalg.lstsq(a_mat, z_vec, rcond=None)
    plane = (coeffs[0] * xx * pixel_size_m) + (coeffs[1] * yy * pixel_size_m) + coeffs[2]
    resid = patch_elev_m - plane
    roughness_rms_m = float(np.sqrt(np.mean(resid * resid)))

    # Variogram gamma(lag) = 0.5 * E[(z(x + lag) - z(x))^2] on detrended or raw surface
    lags: list[float] = []
    gammas: list[float] = []
    max_lag = min(4, (min(h, w) - 1) // 2)
    for lag in (1, 2, 4):
        if lag > max_lag:
            continue
        dx_diff = patch_elev_m[:, lag:] - patch_elev_m[:, :-lag]
        dy_diff = patch_elev_m[lag:, :] - patch_elev_m[:-lag, :]
        g_val = 0.25 * (float(np.mean(dx_diff * dx_diff)) + float(np.mean(dy_diff * dy_diff)))
        if g_val > 1e-10:
            lags.append(math.log(lag * pixel_size_m))
            gammas.append(math.log(g_val))

    if len(lags) >= 2:
        slope_2h, _ = np.polyfit(lags, gammas, 1)
        hurst_h = max(0.02, min(0.98, 0.5 * float(slope_2h)))
        fractal_d = round(3.0 - hurst_h, 4)
    else:
        fractal_d = 2.25

    # Discrete Laplacian curvature proxy (1/m)
    lap_x = (patch_elev_m[1:-1, 2:] - 2.0 * patch_elev_m[1:-1, 1:-1] + patch_elev_m[1:-1, :-2]) / (
        pixel_size_m * pixel_size_m
    )
    lap_y = (patch_elev_m[2:, 1:-1] - 2.0 * patch_elev_m[1:-1, 1:-1] + patch_elev_m[:-2, 1:-1]) / (
        pixel_size_m * pixel_size_m
    )
    curvature_m_inv = float(np.mean(np.abs(lap_x + lap_y)))

    return (round(roughness_rms_m, 4), fractal_d, round(curvature_m_inv, 4))


def _source_distrust_index(source_id: str) -> float:
    if source_id == "SRC-USGS-HIRISE-DTM-1M":
        return 0.04
    if source_id in ("SRC-USGS-SIM3464", "SRC-TREK-HIRISE-25CM"):
        return 0.12
    return 0.55


def build_cell_carrier_triplets(
    *,
    slopes_by_scale: dict[int, float],
    roughness_rms_m: float,
    fractal_d: float,
    curvature_m_inv: float,
    walkback_m: float,
    nodata_fraction: float,
    source_id: str,
    dtm_resolution_m: float = 1.0,
    active_carriers: tuple[str, ...] | None = None,
) -> list[CarrierScaleTriplet]:
    """Construct the multi-scale `(carrier, scale_m, T, I, F)` triplets for a terrain cell.

    Scales failing `prefilter_scale` (`baseline_m < 2 * dtm_resolution_m`, such as `1 m`
    on a `1 m/px` DTM) are automatically excluded so pixel quantization noise never enters
    the funnel. Admitted scales are ordered coarsest-to-finest (`64 -> 16 -> 4`).
    """
    if active_carriers is None:
        carriers_to_use = validate_carrier_names(REQUIRED_CARRIERS, allow_ablation_subset=False)
    else:
        carriers_to_use = validate_carrier_names(active_carriers, allow_ablation_subset=True)

    admitted_scales = sorted(
        [int(s) for s in slopes_by_scale if prefilter_scale(float(s), dtm_resolution_m)["keep"]],
        reverse=True,
    )
    if not admitted_scales:
        raise ValueError("No spatial baseline passed prefilter_scale (>= 2x DTM resolution).")

    cov_hat = normalize_x_hat("I_coverage", nodata_fraction)
    src_hat = _source_distrust_index(source_id)
    wb_hat = normalize_x_hat("I_constraint", walkback_m)

    triplets: list[CarrierScaleTriplet] = []
    for idx_s, s_m in enumerate(admitted_scales):
        slope_s = float(slopes_by_scale[s_m])
        # Neighboring scale slope divergence
        neighbor_diffs: list[float] = []
        if idx_s > 0:
            neighbor_diffs.append(abs(slope_s - float(slopes_by_scale[admitted_scales[idx_s - 1]])))
        if idx_s + 1 < len(admitted_scales):
            neighbor_diffs.append(abs(slope_s - float(slopes_by_scale[admitted_scales[idx_s + 1]])))
        div_deg = max(neighbor_diffs) if neighbor_diffs else 0.0

        div_hat = normalize_x_hat("I_diverge", div_deg)
        i_local = round(max(0.02, min(0.95, max(cov_hat, div_hat))), 4)

        # Scale-modulated sub-metrics (finer scales resolve sharper roughness/curvature,
        # coarser scales suffer slight smoothing loss captured by I_scale)
        scale_atten = 4.0 / float(max(4, s_m))
        scale_hat = round(0.04 + 0.22 * (float(s_m) / 64.0), 4)
        slope_hat = normalize_x_hat("I_slope", slope_s)
        rough_hat = normalize_x_hat("I_rough", roughness_rms_m * (0.55 + 0.45 * scale_atten))
        frac_hat = normalize_x_hat("I_fractal", fractal_d)
        tex_hat = normalize_x_hat("I_texture", curvature_m_inv * (0.50 + 0.50 * scale_atten))
        unc_hat = clamp01(0.5 * (cov_hat + div_hat) + 0.08 * (float(s_m) / 64.0))

        x_hats: dict[str, float] = {
            "I_source": src_hat,
            "I_scale": scale_hat,
            "I_slope": slope_hat,
            "I_rough": rough_hat,
            "I_fractal": frac_hat,
            "I_diverge": div_hat,
            "I_texture": tex_hat,
            "I_constraint": wb_hat,
            "I_coverage": cov_hat,
            "I_uncertainty": unc_hat,
        }

        for c_name in carriers_to_use:
            xh = round(clamp01(x_hats[c_name]), 4)
            t_val = round(1.0 - xh, 4)
            f_val = xh
            triplets.append(
                CarrierScaleTriplet(
                    carrier=c_name,
                    scale_m=s_m,
                    t=t_val,
                    i=i_local,
                    f=f_val,
                )
            )

    return triplets
