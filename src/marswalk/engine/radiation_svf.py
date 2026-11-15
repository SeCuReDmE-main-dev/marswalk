"""Phase 3 Radiation Horizon Sky View Factor (SVF) & Ehresmann (2021) Dose Factor (T07).

Implements:
- `ehresmann_dose_factor(svf, eta_s=0.20)` (`P2` / `C2`):
  Empirically calibrated topographic shielding factor from Curiosity RAD at Murray Buttes
  (Ehresmann et al. 2021, JGR Planets 126:e2021JE006851: 19% sky obstruction -> 3.8 +/- 0.4%
  dose rate reduction, eta_s = 0.20) and Kimberley (Guo et al. 2021, GRL 48:e2021GL093912:
  5 +/- 1% reduction, eta_s <= 0.26).
- Note on mathematical domain (`P2`):
  For SVF in [0, 1] and eta_s in [0.20, 0.26], `1 - eta_s*(1 - SVF) >= 0.74 > 0.19`.
  The 0.19 zenith-albedo ratio is retained in the formula for completeness, never claimed
  as an active threshold on Martian surface terrain. Furthermore, cell-level GCR differences
  are small over an 8 h EVA (~0.1 mGy vs 250 mGy 30-day limit); Solar Particle Event (SPE)
  acts as a global emergency abort switch (`spe_alert=True -> NO_GO`).
- `compute_sky_view_factor_32az(...)`:
  32-azimuth horizon ray-casting (Dozier & Frew 1990; Zaksek et al. 2011) over the 1 m
  HiRISE DTM with Mars curvature drop d^2 / (2 * R_Mars) and cos(phi) E-W ground scaling.
"""

from __future__ import annotations

import math

import numpy as np

from marswalk.contracts.models import MARS_SPHERE_RADIUS_M

ETA_S_DEFAULT: float = 0.20
ETA_S_EMPIRICAL_BAND: tuple[float, float] = (0.20, 0.26)
OPEN_SKY_GCR_DOSE_MGY_PER_DAY: float = 0.233
OPEN_SKY_GCR_DOSE_MSV_PER_DAY: float = 0.67


def ehresmann_dose_factor(svf: float, eta_s: float = ETA_S_DEFAULT) -> float:
    """Return local-to-open-sky GCR dose ratio calibrated on Ehresmann et al. (2021) (`C2`)."""
    svf_clamped = max(0.0, min(1.0, float(svf)))
    return max(0.19, 1.0 - float(eta_s) * (1.0 - svf_clamped))


def local_gcr_dose_mgy_per_day(
    svf: float,
    open_sky_mgy_per_day: float = OPEN_SKY_GCR_DOSE_MGY_PER_DAY,
    eta_s: float = ETA_S_DEFAULT,
) -> float:
    """Compute local GCR absorbed dose rate (mGy/day) from Sky View Factor."""
    return float(open_sky_mgy_per_day) * ehresmann_dose_factor(svf=svf, eta_s=eta_s)


def compute_sky_view_factor_32az(
    dtm_elev_m: np.ndarray,
    row: int,
    col: int,
    step_x_m: float = 0.9485,
    step_y_m: float = 1.0,
    max_radius_px: int = 48,
    observer_height_m: float = 1.2,
) -> float:
    """Compute 32-azimuth Sky View Factor SVF = 1 - mean(sin(gamma_i)) on 1m DTM."""
    h, w = dtm_elev_m.shape
    r0 = max(0, min(h - 1, int(row)))
    c0 = max(0, min(w - 1, int(col)))
    z0 = float(dtm_elev_m[r0, c0]) + float(observer_height_m)

    n_az = 32
    radii = np.arange(2, max(4, int(max_radius_px)) + 1, 2, dtype=np.float64)
    sin_sum = 0.0

    for k in range(n_az):
        az = (2.0 * math.pi * k) / float(n_az)
        dc = math.sin(az)
        dr = -math.cos(az)

        rr = np.clip(np.rint(r0 + radii * dr).astype(int), 0, h - 1)
        cc = np.clip(np.rint(c0 + radii * dc).astype(int), 0, w - 1)
        dist_m = np.hypot((cc - c0) * float(step_x_m), (rr - r0) * float(step_y_m))
        valid = dist_m >= 1.0
        if not np.any(valid):
            continue
        dist_v = dist_m[valid]
        z_v = dtm_elev_m[rr[valid], cc[valid]]
        curv_drop_m = (dist_v * dist_v) / (2.0 * MARS_SPHERE_RADIUS_M)
        tan_gamma = ((z_v - curv_drop_m) - z0) / dist_v
        max_tan = float(np.max(tan_gamma))
        if max_tan > 0.0:
            gamma = math.atan(max_tan)
            sin_sum += math.sin(gamma)

    svf = 1.0 - (sin_sum / float(n_az))
    return round(max(0.05, min(1.0, svf)), 4)
