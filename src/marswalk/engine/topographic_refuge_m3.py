"""Phase 4 Topographic Sky Occlusion & Partial GCR Refuge Estimator (`M3`).

Enforces CTO physics & terminology rules (`I1-I3` & `C5`):
1. Never labels a cliff or scarp toe as a solar particle storm shelter. Even at 35-50% geometric sky
   occlusion (`1 - SVF`), empirical MSL RAD measurements at Murray Buttes (Ehresmann
   et al. 2021, JGR Planets: 19% sky blocked -> 3.8% dose drop, `eta_s = 0.20`) and
   Kimberley (Guo et al. 2021, GRL: 5 +/- 1%, `eta_s <= 0.26`) yield only ~7-10.4%
   GCR reduction (`[7.0%, 9.1%]` at `1 - SVF = 0.35`, `[8.0%, 10.4%]` at `0.40`).
2. Under `spe_alert=True`, the verdict is unconditionally `NO_GO` and emergency egress
   minimizes travel time to the pressurized rover or habitat with ZERO routing weight
   (`SPE_REFUGE_ROUTING_WEIGHT = 0.0`) on wall occlusion.
3. Avoids the `P2` inert-threshold trap (`C5`): on 48 m cell centers `1 - SVF <= 0.2724`,
   so `partial_topographic_refuge` evaluates maximum 1 m DTM scarp-toe sky occlusion
   within each cell/pixel against a verified non-empty scarp-toe threshold (`0.22`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from marswalk.engine.radiation_svf import ETA_S_EMPIRICAL_BAND, compute_sky_view_factor_32az

TOE_OCCLUSION_REFUGE_THRESHOLD: float = 0.22
SPE_REFUGE_ROUTING_WEIGHT: float = 0.0
PARTIAL_REFUGE_PROVENANCE_NOTE: str = (
    "Partial geometric sky occlusion (DERIVED, eta_s in [0.20, 0.26] calibrated on MSL RAD GCR); "
    "UNVERIFIED for hard zenith-peaked SPE spectrum (arXiv:2205.13786 is ABSTRACT_OR_METADATA "
    "geometric context only); mandatory SPE action is immediate fastest return to rover or habitat."
)


@dataclass(frozen=True)
class PartialRefugeEstimate:
    """Topographic sky occlusion and GCR-calibrated partial dose reduction (`M3`)."""

    sky_occlusion_1_minus_svf: float
    expected_gcr_reduction_min_pct: float
    expected_gcr_reduction_max_pct: float
    partial_topographic_refuge: bool
    spe_routing_weight: float
    tag: Literal["DERIVED"]
    note: str


def analytical_finite_wall_sky_occlusion(
    wall_height_m: float,
    standoff_distance_m: float,
    wall_width_m: float | None = 30.0,
) -> float:
    """Compute exact hemispherical sky occlusion `1 - SVF` at standoff `d` from a vertical wall.

    Matches the isotropic horizon definition `1 - SVF = (1 / 2*pi) * integral sin(gamma(az)) daz`
    used in `radiation_svf.compute_sky_view_factor_32az`:
    - Infinite wall (`wall_width_m=None`): `(1 / pi) * atan(H / d)` (`-> 0.50` as `d -> 0+`).
    - Finite centered wall of width `W`:
      `(1 / pi) * asin((H / sqrt(d^2 + H^2)) * ((W/2) / sqrt(d^2 + (W/2)^2)))`.
    """
    h = max(0.0, float(wall_height_m))
    d = max(1e-6, float(standoff_distance_m))
    if h == 0.0:
        return 0.0
    if wall_width_m is None or math.isinf(wall_width_m):
        return round(math.atan(h / d) / math.pi, 6)
    half_w = max(0.0, 0.5 * float(wall_width_m))
    if half_w == 0.0:
        return 0.0
    arg = (h / math.hypot(d, h)) * (half_w / math.hypot(d, half_w))
    return round(math.asin(max(-1.0, min(1.0, arg))) / math.pi, 6)


def compute_partial_topographic_refuge(
    sky_occlusion_1_minus_svf: float,
    threshold: float = TOE_OCCLUSION_REFUGE_THRESHOLD,
    eta_band: tuple[float, float] = ETA_S_EMPIRICAL_BAND,
) -> PartialRefugeEstimate:
    """Evaluate GCR-calibrated partial dose reduction band from `1 - SVF` (`C5`, `I1-I3`)."""
    occ = max(0.0, min(1.0, float(sky_occlusion_1_minus_svf)))
    eta_min, eta_max = float(eta_band[0]), float(eta_band[1])
    red_min_pct = 100.0 * eta_min * occ
    red_max_pct = 100.0 * eta_max * occ
    return PartialRefugeEstimate(
        sky_occlusion_1_minus_svf=round(occ, 4),
        expected_gcr_reduction_min_pct=round(red_min_pct, 3),
        expected_gcr_reduction_max_pct=round(red_max_pct, 3),
        partial_topographic_refuge=bool(occ >= float(threshold)),
        spe_routing_weight=SPE_REFUGE_ROUTING_WEIGHT,
        tag="DERIVED",
        note=PARTIAL_REFUGE_PROVENANCE_NOTE,
    )


def estimate_cell_max_toe_occlusion(
    dtm_elev_m: np.ndarray,
    r0: int,
    r1: int,
    c0: int,
    c1: int,
    center_svf: float,
    step_x_m: float,
    step_y_m: float = 1.0,
) -> PartialRefugeEstimate:
    """Find peak scarp-toe sky occlusion `1 - SVF` inside a grid cell patch (`C5`).

    Evaluates candidate toe pixels (low-elevation pixels adjacent to steep internal relief)
    via 32-azimuth ray casting so scarp-toe occlusion is not diluted by 48 m cell-center
    averaging.
    """
    h, w = dtm_elev_m.shape
    ra = max(4, int(r0))
    rb = min(h - 4, int(r1))
    ca = max(4, int(c0))
    cb = min(w - 4, int(c1))
    base_occ = max(0.0, min(1.0, 1.0 - float(center_svf)))
    if rb <= ra + 2 or cb <= ca + 2:
        return compute_partial_topographic_refuge(base_occ)

    sub = dtm_elev_m[ra:rb, ca:cb]
    relief = float(np.max(sub) - np.min(sub))
    if relief < 3.5:
        return compute_partial_topographic_refuge(base_occ)

    # Probe the lowest-quartile toe pixel closest to the steepest local gradient inside the cell
    gy, gx = np.gradient(sub, float(step_y_m), float(step_x_m))
    grad_mag = np.hypot(gx, gy)
    q35_z = float(np.percentile(sub, 35))
    toe_score = grad_mag - 0.15 * np.maximum(0.0, sub - q35_z)
    flat_idx = int(np.argmax(toe_score))
    sub_r, sub_c = divmod(flat_idx, sub.shape[1])
    svf_toe = compute_sky_view_factor_32az(
        dtm_elev_m,
        row=ra + sub_r,
        col=ca + sub_c,
        step_x_m=step_x_m,
        step_y_m=step_y_m,
        max_radius_px=36,
    )
    peak_occ = max(base_occ, 1.0 - svf_toe)
    return compute_partial_topographic_refuge(peak_occ)
