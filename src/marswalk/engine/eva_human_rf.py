"""Phase 3 Human xEVA Bioenergetics, Walkback Consumables & ITU-R P.526-16 UHF RF Engine (T10).

Implements:
- `fresnel_j_db(nu)` and `rf_verdict(nu_max, link_margin_db)` (`P1` / `C3`):
  ITU-R P.526-16 (11/2025) §4.1 eq. (31) single knife-edge / Bullington diffraction loss
  at 414.2 MHz (astronaut suit antenna 1.8 m -> Perseverance rover UHF mast 3.0 m) over
  spherical Mars radius R = 3,396,190 m. Verdict is decided by comparing diffraction loss
  J(nu_max) against link_margin_db (with fade margin), never by raw nu <= -0.78 alone.
- `metabolic_rate_w(grade, payload_kg)` (`P4` / `C4`):
  Piecewise linear interpolation on the Norcross et al. (NASA/TP-2010-216125) measured
  partial-gravity (0.32 g) pressurized MKIII suit VO2 table (70 kg crew, 121 kg suit,
  20.1 kJ/L O2 -> 375.2 W at 0% grade, 745.7 W at 30% grade), with Santee et al. (2003)
  relative shape only for downhill grades and monotone payload scaling.
- `walkback_return_h(distance_m, grade)` and `walkback_o2_margin_min(...)` (`P3` / `C5`):
  Tobler (1993) walking speed rescaled x0.4 to the NASA xEVA 2.0 km/h level baseline.
  The 1.0 h contingency walkback limit applies strictly to walking time; the 30 min
  perchlorate dust-removal airlock ingress is accounted for in the primary O2 mass budget.
"""

from __future__ import annotations

import math

import numpy as np

from marswalk.contracts.models import MARS_SPHERE_RADIUS_M, VerdictLiteral

UHF_FREQ_HZ: float = 414.2e6
SPEED_OF_LIGHT_M_S: float = 299_792_458.0
UHF_WAVELENGTH_M: float = SPEED_OF_LIGHT_M_S / UHF_FREQ_HZ
SUIT_ANTENNA_HEIGHT_M: float = 1.8
ROVER_MAST_HEIGHT_M: float = 3.0

# Norcross et al. (NASA/TP-2010-216125) measured 0.32 g suited VO2 (mL/kg/min) vs fractional grade
_NORCROSS_GRADE_TABLE: tuple[tuple[float, float], ...] = (
    (0.00, 16.0),
    (0.10, 18.3),
    (0.15, 20.8),
    (0.20, 23.8),
    (0.30, 31.8),
)
O2_ENERGY_J_PER_L: float = 20_100.0
O2_DENSITY_G_PER_L: float = 1.429
ARTEMIS_WALKBACK_W: float = 2_505_000.0 / 3600.0  # 695.833 W (2,505 kJ/h)


def fresnel_j_db(nu: float) -> float:
    """Compute ITU-R P.526-16 §4.1 eq. (31) knife-edge diffraction loss J(nu) in dB."""
    if nu <= -0.78:
        return 0.0
    val = math.sqrt((nu - 0.1) ** 2 + 1.0) + nu - 0.1
    if val <= 1e-12:
        return 0.0
    return 6.9 + 20.0 * math.log10(val)


def rf_verdict(
    nu_max: float,
    link_margin_db: float = 6.0,
    fade_margin_db: float = 1.0,
    beyond_horizon: bool = False,
) -> VerdictLiteral:
    """Return GO / CAUTION / NO_GO for UHF comms based on diffraction loss vs link margin (`P1`)."""
    if beyond_horizon:
        return "NO_GO"
    loss_db = fresnel_j_db(nu_max)
    if loss_db > link_margin_db:
        return "NO_GO"
    if loss_db <= max(0.0, link_margin_db - fade_margin_db):
        return "GO"
    return "CAUTION"


def bullington_nu_max_profile(
    elev_profile_m: np.ndarray | list[float],
    distance_m: float,
    h_tx_m: float = ROVER_MAST_HEIGHT_M,
    h_rx_m: float = SUIT_ANTENNA_HEIGHT_M,
    wavelength_m: float = UHF_WAVELENGTH_M,
    sphere_radius_m: float = MARS_SPHERE_RADIUS_M,
) -> float:
    """Compute maximum Fresnel-Kirchhoff parameter nu_max along a 1m DTM profile with Mars bulge.

    Convention: `elev_profile_m[0]` is the rover (UHF mast, 3.0 m) and `elev_profile_m[-1]`
    is the astronaut (suit antenna, 1.8 m). Both callers sample origin (rover) -> point.
    """
    n = len(elev_profile_m)
    if distance_m <= 1.0 or n < 2:
        return -2.0

    z0 = float(elev_profile_m[0]) + h_tx_m
    z1 = float(elev_profile_m[-1]) + h_rx_m
    best_nu = -1e9

    if n >= 3:
        for idx in range(1, n - 1):
            frac = idx / float(n - 1)
            d1 = distance_m * frac
            d2 = distance_m - d1
            if d1 <= 0.1 or d2 <= 0.1:
                continue
            bulge_m = (d1 * d2) / (2.0 * sphere_radius_m)
            los_z = z0 + (z1 - z0) * frac
            h_obs = (float(elev_profile_m[idx]) + bulge_m) - los_z
            nu = h_obs * math.sqrt((2.0 / wavelength_m) * (1.0 / d1 + 1.0 / d2))
            if nu > best_nu:
                best_nu = nu
    else:
        # Smooth spherical chord fallback when only endpoints are given
        for idx in range(1, 200):
            frac = idx / 200.0
            d1 = distance_m * frac
            d2 = distance_m - d1
            bulge_m = (d1 * d2) / (2.0 * sphere_radius_m)
            los_clear = h_tx_m + (h_rx_m - h_tx_m) * frac
            h_obs = bulge_m - los_clear
            nu = h_obs * math.sqrt((2.0 / wavelength_m) * (1.0 / d1 + 1.0 / d2))
            if nu > best_nu:
                best_nu = nu

    return float(best_nu)


def sample_dtm_los_profile(
    dtm_arr: object,
    r0: int,
    c0: int,
    r1: int,
    c1: int,
    distance_m: float,
    step_m: float = 8.0,
) -> list[float]:
    """Sample a 1 m/px DTM elevation profile along the straight line (r0, c0) -> (r1, c1).

    Guarantees >= 1 sample per `step_m` (<= 10 m) and >= 3 samples so
    `bullington_nu_max_profile` evaluates real terrain ridges and scarps (`R2`).
    """
    import numpy as np

    arr = np.asarray(dtm_arr, dtype=np.float64)
    h, w = arr.shape
    n_pts = max(3, int(math.ceil(max(1.0, float(distance_m)) / float(step_m))) + 1)
    rs = np.clip(np.rint(np.linspace(r0, r1, n_pts)).astype(int), 0, h - 1)
    cs = np.clip(np.rint(np.linspace(c0, c1, n_pts)).astype(int), 0, w - 1)
    return [float(v) for v in arr[rs, cs]]


def tobler_xeva_kmh(grade: float, sand_penalty: float = 1.0) -> float:
    """Compute Tobler (1993) walking speed (km/h) rescaled x0.4 to NASA xEVA 2.0 km/h on flat."""
    base_kmh = 0.4 * 6.0 * math.exp(-3.5 * abs(float(grade) + 0.05))
    return max(0.15, base_kmh * max(0.2, min(1.0, float(sand_penalty))))


def walkback_return_h(
    distance_m: float,
    grade: float = 0.0,
    sand_penalty: float = 1.0,
) -> float:
    """Compute contingency walkback walking duration (h) excluding airlock ingress (`P3`)."""
    if distance_m <= 0.0:
        return 0.0
    speed_kmh = tobler_xeva_kmh(grade=grade, sand_penalty=sand_penalty)
    return (float(distance_m) / 1000.0) / speed_kmh


def _norcross_vo2_ml_kg_min(grade: float) -> float:
    """Interpolate Norcross et al. (2010) 0.32 g pressurized suit VO2 (mL/kg/min)."""
    g = float(grade)
    if g < 0.0:
        # Downhill relative reduction bounded by Santee (2003) gentle-descent minimum (~0.88x)
        vo2_0 = _NORCROSS_GRADE_TABLE[0][1]
        opt_descent = -0.05
        if g >= opt_descent:
            factor = 1.0 - 0.10 * (abs(g) / abs(opt_descent))
        else:
            factor = 0.90 + 0.45 * min(0.40, abs(g - opt_descent))
        return vo2_0 * factor

    for idx in range(len(_NORCROSS_GRADE_TABLE) - 1):
        g0, v0 = _NORCROSS_GRADE_TABLE[idx]
        g1, v1 = _NORCROSS_GRADE_TABLE[idx + 1]
        if g <= g1:
            t = (g - g0) / max(1e-9, g1 - g0)
            return v0 + t * (v1 - v0)

    # Linear extrapolation above 30% fractional grade
    g_prev, v_prev = _NORCROSS_GRADE_TABLE[-2]
    g_last, v_last = _NORCROSS_GRADE_TABLE[-1]
    slope = (v_last - v_prev) / (g_last - g_prev)
    return v_last + slope * (g - g_last)


def metabolic_rate_w(
    grade: float,
    payload_kg: float = 0.0,
    astronaut_mass_kg: float = 70.0,
    suit_mass_kg: float = 121.0,
) -> float:
    """Compute suited Martian metabolic rate (W) anchored on Norcross (2010) (`P4` / `C4`)."""
    vo2 = _norcross_vo2_ml_kg_min(grade)
    base_w = (vo2 * float(astronaut_mass_kg) / 1000.0) * O2_ENERGY_J_PER_L / 60.0
    extra_kg = max(0.0, float(payload_kg))
    total_ref_kg = float(astronaut_mass_kg + suit_mass_kg)
    grade_pos = max(0.0, float(grade))
    payload_factor = 1.0 + (extra_kg / max(1.0, total_ref_kg)) * (1.0 + 2.0 * grade_pos)
    return float(base_w * payload_factor)


def o2_consumption_g_per_h(metabolic_w: float) -> float:
    """Convert metabolic power (W) to O2 mass flow (g/h) using 20.1 kJ/L and 1.429 g/L."""
    liters_per_min = (60.0 * max(0.0, float(metabolic_w))) / O2_ENERGY_J_PER_L
    return liters_per_min * 60.0 * O2_DENSITY_G_PER_L


def walkback_o2_margin_min(
    distance_m: float,
    grade: float = 0.0,
    payload_kg: float = 0.0,
    sand_penalty: float = 1.0,
    primary_o2_budget_g: float = 754.0,
    nominal_eva_elapsed_h: float = 3.0,
    dust_decontam_ingress_h: float = 0.5,
) -> float:
    """Compute remaining primary O2 margin (minutes) after EVA + walkback + 30 min ingress."""
    nominal_w = metabolic_rate_w(grade=0.02, payload_kg=payload_kg)
    walkback_w = max(
        ARTEMIS_WALKBACK_W, metabolic_rate_w(grade=max(0.0, grade), payload_kg=payload_kg)
    )
    ingress_w = metabolic_rate_w(grade=0.0, payload_kg=0.0)

    t_walk_h = walkback_return_h(distance_m=distance_m, grade=grade, sand_penalty=sand_penalty)
    used_g = (
        o2_consumption_g_per_h(nominal_w) * nominal_eva_elapsed_h
        + o2_consumption_g_per_h(walkback_w) * t_walk_h
        + o2_consumption_g_per_h(ingress_w) * dust_decontam_ingress_h
    )
    remaining_g = primary_o2_budget_g - used_g
    burn_rate_g_per_min = o2_consumption_g_per_h(walkback_w) / 60.0
    return remaining_g / max(1e-6, burn_rate_g_per_min)
