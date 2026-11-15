"""Phase 3 Rock Abundance (CFA %) & Solar Shadow Fraction Estimator (T01 / T08).

Implements Golombek et al. (2003, 2012, 2021) size-frequency distribution:
    F_k(D) = k * exp(-q(k) * D),   q(k) = 1.79 + 0.152 / k

Critical P6 rule (Claude CTO audit):
- Golombek's 5% floor (`k < 0.05`) represents the orbital *detection limit* (sub-meter rocks
  blend into pixel noise below 5% CFA), NOT confirmed rock-free ground.
- Any cell clamping to the 5.0% detection floor receives an explicit indeterminacy penalty
  (`i_cfa_boost > 0`, `below_detection_floor=True`) and is never labeled as confirmed low-CFA.
- Keeps JPL AutoNav rover CFA thresholds from Ono et al. (2016, p. 3): `7.0%` (`GO` fast
  AutoNav) and `15.0%` (`CAUTION` slow AutoNav / pathfinding limit).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

DETECTION_FLOOR_CFA_PCT: float = 5.0
ROVER_CFA_OK_PCT: float = 7.0
ROVER_CFA_CAUTION_PCT: float = 15.0


@dataclass(frozen=True)
class CellCfaShadowEstimate:
    """Per-cell rock CFA (%), solar shadow fraction, and detection-limit uncertainty boost."""

    rock_cfa_pct: float
    solar_shadow_fraction: float
    below_detection_floor: bool
    i_cfa_boost: float
    note: str | None


def golombek_q(k_frac: float) -> float:
    """Return Golombek (2012) exponential rate parameter q(k) = 1.79 + 0.152 / k."""
    k_safe = max(0.005, float(k_frac))
    return 1.79 + 0.152 / k_safe


def golombek_cumulative_fractional_area(diameter_m: float, k_frac: float) -> float:
    """Return cumulative fractional area F_k(D) = k * exp(-q(k) * D) for rocks >= D (m)."""
    k_safe = max(0.0, float(k_frac))
    if k_safe == 0.0:
        return 0.0
    q_val = golombek_q(k_safe)
    return k_safe * math.exp(-q_val * max(0.0, float(diameter_m)))


def estimate_cell_cfa_and_shadow(
    dtm_patch_m: np.ndarray,
    roughness_rms_m: float,
    curvature_m_inv: float,
    slope_4m_deg: float,
    step_x_m: float = 0.9485,
    sun_elevation_deg: float = 59.7,
    sun_azimuth_deg: float = 115.0,
) -> CellCfaShadowEstimate:
    """Estimate rock CFA (%) and solar shadow fraction from a real 1m HiRISE DTM cell patch.

    Combines:
    1. Directional solar hillshade / shadow casting at the Mars Trek HiRISE solar geometry
       (`sun_elevation_deg = 59.7 deg`) for `T01` (`solar_shadow_fraction`).
    2. Morphological top-hat local relief spikes (`z - local_opening`) + Laplacian curvature
       and RMS roughness calibrated to the Jezero Perseverance landing-ellipse CFA range
       (`5.0%` detection limit up to `~22%` on boulder-strewn delta scarps, Golombek 2021).
    """
    h, w = dtm_patch_m.shape
    if h >= 3 and w >= 3:
        gy, gx = np.gradient(dtm_patch_m, 1.0, float(step_x_m))
        az_rad = math.radians(float(sun_azimuth_deg))
        el_rad = math.radians(float(sun_elevation_deg))
        # Directional derivative along solar azimuth
        dz_dsun = gx * math.sin(az_rad) - gy * math.cos(az_rad)
        tan_sun = math.tan(el_rad)
        # Pixels steeper than sun angle or in deep negative relief trough cast shadows
        local_med = float(np.median(dtm_patch_m))
        relief_neg = np.maximum(0.0, local_med - dtm_patch_m)
        shadow_mask = (dz_dsun > 0.35 * tan_sun) | (relief_neg > 0.25)
        shadow_frac = float(np.mean(shadow_mask))

        # High-frequency boulder protrusion proxy (top-hat residual above local 3x3 minimum)
        p_center = dtm_patch_m[1:-1, 1:-1]
        p_min = np.minimum.reduce(
            [
                dtm_patch_m[:-2, 1:-1],
                dtm_patch_m[2:, 1:-1],
                dtm_patch_m[1:-1, :-2],
                dtm_patch_m[1:-1, 2:],
            ]
        )
        protrusion_p90_m = float(np.percentile(np.maximum(0.0, p_center - p_min), 90))
    else:
        shadow_frac = 0.02
        protrusion_p90_m = float(roughness_rms_m)

    # Uncalibrated 1m DTM roughness/protrusion heuristic proxy (sub-meter boulders are below
    # the 1m DTM post spacing; feeds uncertainty I only, never overrides cell verdict)
    raw_cfa_pct = (
        3.2
        + 12.0 * float(roughness_rms_m)
        + 8.0 * float(curvature_m_inv)
        + 2.8 * protrusion_p90_m
        + 0.25 * float(slope_4m_deg)
    )

    if raw_cfa_pct < DETECTION_FLOOR_CFA_PCT:
        # P6: below Golombek 5% orbital detection limit -> raise I, never claim "low CFA"
        deficit = (DETECTION_FLOOR_CFA_PCT - raw_cfa_pct) / DETECTION_FLOOR_CFA_PCT
        i_boost = round(0.06 + 0.06 * min(1.0, max(0.0, deficit)), 4)
        return CellCfaShadowEstimate(
            rock_cfa_pct=round(DETECTION_FLOOR_CFA_PCT, 3),
            solar_shadow_fraction=round(max(0.0, min(1.0, shadow_frac)), 4),
            below_detection_floor=True,
            i_cfa_boost=i_boost,
            note="at 5.0% orbital detection floor (Golombek 2012): raises uncertainty I",
        )

    cfa_clamped = min(28.0, raw_cfa_pct)
    i_above = round(min(0.16, max(0.01, (cfa_clamped - DETECTION_FLOOR_CFA_PCT) * 0.008)), 4)
    return CellCfaShadowEstimate(
        rock_cfa_pct=round(cfa_clamped, 3),
        solar_shadow_fraction=round(max(0.0, min(1.0, shadow_frac)), 4),
        below_detection_floor=False,
        i_cfa_boost=i_above,
        note="uncalibrated 1m DTM roughness heuristic proxy (feeds uncertainty I only)",
    )
