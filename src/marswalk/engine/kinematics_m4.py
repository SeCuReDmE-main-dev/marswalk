"""Phase 4 Kinematics, Grade-vs-Angle Conversions & Suited Metabolic Envelope (`M4`).

Enforces strict unit separation (`I5` & `C6`):
- `slope_deg` is terrain angle theta in degrees (`theta = degrees(atan(grade_frac))`).
- `grade_frac` is dimensionless tangent slope `i = tan(radians(theta))`
  (`-10% = -0.10 -> -5.7106 deg`, never `-10.0 deg`).
- Distinguishes Minetti et al. (2002, J. Appl. Physiol. 93:1039-1046) published experimental
  Table 1 means (`tag="MEASURED"`, `1.64 / 0.81 / 3.46 / 17.33 J/kg/m`) from the fitted quintic
  regression polynomial (`tag="DERIVED"`, `2.50 / 1.13 / 3.61 / 17.60 J/kg/m`).
- Preserves the repository canonical suit mass `SUIT_MASS_MKIII_KG = 121.0` (Norcross et al. 2010
  MKIII partial-gravity `0.32 g` anchor `375.2 W`) for all operational O2 and walkback budgets,
  while exposing both Pandolf CSRM (`all_g_scaled`) and Carr & Newman (2008, unscaled standing
  term) models strictly as `DERIVED` comparative diagnostics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from marswalk.engine.eva_human_rf import metabolic_rate_w

ASTRONAUT_BODY_MASS_KG: float = 70.0
SUIT_MASS_MKIII_KG: float = 121.0
SUIT_MASS_CSRM_REF_KG: float = 104.0
MARS_GRAVITY_RATIO: float = 0.3794

# Minetti et al. (2002, Table 1) published experimental walking net cost C_w (J / (kg * m))
_MINETTI_2002_TABLE_1: tuple[tuple[float, float], ...] = (
    (-0.45, 3.46),
    (-0.40, 2.97),
    (-0.35, 2.55),
    (-0.30, 2.09),
    (-0.25, 1.63),
    (-0.20, 1.22),
    (-0.15, 0.96),
    (-0.10, 0.81),
    (-0.05, 1.07),
    (0.00, 1.64),
    (0.05, 2.66),
    (0.10, 3.92),
    (0.15, 5.42),
    (0.20, 7.36),
    (0.25, 9.57),
    (0.30, 11.95),
    (0.35, 14.43),
    (0.40, 15.93),
    (0.45, 17.33),
)


@dataclass(frozen=True)
class SuitedMetabolicComparison:
    """Side-by-side comparison of suited Martian metabolic models (`I4`, `C6b`)."""

    grade_frac: float
    slope_deg: float
    speed_m_s: float
    body_mass_kg: float
    suit_mass_kg: float
    norcross_2010_measured_anchor_w: float
    norcross_tag: Literal["MEASURED"]
    pandolf_csrm_all_g_scaled_w: float
    pandolf_carr_newman_unscaled_postural_w: float
    pandolf_load_carriage_share: float
    pandolf_tag: Literal["DERIVED"]
    note: str


def slope_deg_to_grade_frac(slope_deg: float) -> float:
    """Convert terrain angle theta (degrees) to dimensionless grade fraction i = tan(theta)."""
    clamped_deg = max(-80.0, min(80.0, float(slope_deg)))
    return math.tan(math.radians(clamped_deg))


def grade_frac_to_slope_deg(grade_frac: float) -> float:
    """Convert dimensionless grade fraction i (rise/run) to terrain angle theta (degrees)."""
    return math.degrees(math.atan(float(grade_frac)))


def minetti_2002_table_j_per_kg_m(grade_frac: float) -> float:
    """Interpolate Minetti et al. (2002, Table 1) experimental walking cost C_w (J/kg/m).

    Exact published anchor values:
    - `i =  0.00` (`0%`)   -> `1.64 J/(kg*m)`
    - `i = -0.10` (`-10%`) -> `0.81 J/(kg*m)` (energetic optimum at `-5.7106 deg`)
    - `i = -0.45` (`-45%`) -> `3.46 J/(kg*m)`
    - `i = +0.45` (`+45%`) -> `17.33 J/(kg*m)`
    """
    g = max(-0.45, min(0.45, float(grade_frac)))
    for idx in range(len(_MINETTI_2002_TABLE_1) - 1):
        g0, c0 = _MINETTI_2002_TABLE_1[idx]
        g1, c1 = _MINETTI_2002_TABLE_1[idx + 1]
        if g <= g1 + 1e-12:
            if abs(g1 - g0) <= 1e-12:
                return c0
            t = (g - g0) / (g1 - g0)
            return round(c0 + t * (c1 - c0), 6)
    return _MINETTI_2002_TABLE_1[-1][1]


def minetti_2002_quintic_poly_j_per_kg_m(grade_frac: float) -> float:
    """Evaluate Minetti et al. (2002) fitted quintic regression polynomial C_w(i) (`DERIVED`).

    `C_w(i) = 280.5*i^5 - 58.7*i^4 - 76.8*i^3 + 51.9*i^2 + 19.6*i + 2.5`
    Evaluates to `2.50` (`0%`), `1.1325` (`-10%`), `3.606` (`-45%`), `17.601` (`+45%`).
    Kept distinct from `minetti_2002_table_j_per_kg_m` per CTO rule `C6c`.
    """
    i = max(-0.45, min(0.45, float(grade_frac)))
    val = 280.5 * (i**5) - 58.7 * (i**4) - 76.8 * (i**3) + 51.9 * (i**2) + 19.6 * i + 2.5
    return round(val, 6)


def compare_suited_metabolic_models(
    grade_frac: float = 0.0,
    speed_m_s: float = 2.0 / 3.6,
    body_mass_kg: float = ASTRONAUT_BODY_MASS_KG,
    suit_mass_kg: float = SUIT_MASS_MKIII_KG,
    payload_kg: float = 0.0,
    terrain_eta: float = 1.0,
    gravity_ratio: float = MARS_GRAVITY_RATIO,
) -> SuitedMetabolicComparison:
    """Compare Norcross (2010) suited anchor against both Pandolf Martian conventions (`I4`).

    - Operational O2 / walkback anchor: Norcross et al. (2010, NASA/TP-2010-216125, `0.32 g`
      MKIII suited table, `375.2 W` level at `70 kg` body + `121 kg` suit).
    - `pandolf_csrm_all_g_scaled_w`: scales all Pandolf (1977) terms including the `1.5*W`
      standing term by `gravity_ratio` (`343.65 W` for `W=75 kg, L=104 kg, v=0.625 m/s, eta=1.0`).
    - `pandolf_carr_newman_unscaled_postural_w`: keeps `1.5*W` unscaled per Carr & Newman (2008)
      (`413.47 W` on the same CSRM reference point).
    """
    w_kg = max(35.0, float(body_mass_kg))
    load_kg = max(0.0, float(suit_mass_kg) + float(payload_kg))
    v = max(0.0, float(speed_m_s))
    eta = max(0.8, float(terrain_eta))
    g_ratio = max(0.05, min(1.0, float(gravity_ratio)))
    g_frac = float(grade_frac)
    grade_pct = 100.0 * g_frac

    postural_earth_w = 1.5 * w_kg
    load_carriage_earth_w = 2.0 * (w_kg + load_kg) * ((load_kg / w_kg) ** 2)
    # Downhill relief follows Minetti table ratio relative to level walking
    if grade_pct >= 0.0:
        locomotion_earth_w = eta * (w_kg + load_kg) * (1.5 * (v**2) + 0.35 * v * grade_pct)
    else:
        c_ratio = minetti_2002_table_j_per_kg_m(g_frac) / minetti_2002_table_j_per_kg_m(0.0)
        locomotion_earth_w = eta * (w_kg + load_kg) * (1.5 * (v**2)) * c_ratio

    total_earth_w = postural_earth_w + load_carriage_earth_w + locomotion_earth_w
    csrm_all_g_w = g_ratio * total_earth_w
    carr_newman_w = postural_earth_w + g_ratio * (load_carriage_earth_w + locomotion_earth_w)
    load_share = load_carriage_earth_w / max(1e-6, total_earth_w)

    norcross_w = metabolic_rate_w(
        grade=g_frac,
        payload_kg=payload_kg,
        astronaut_mass_kg=w_kg,
        suit_mass_kg=float(suit_mass_kg),
    )

    return SuitedMetabolicComparison(
        grade_frac=round(g_frac, 6),
        slope_deg=round(grade_frac_to_slope_deg(g_frac), 4),
        speed_m_s=round(v, 4),
        body_mass_kg=round(w_kg, 2),
        suit_mass_kg=round(float(suit_mass_kg), 2),
        norcross_2010_measured_anchor_w=round(norcross_w, 2),
        norcross_tag="MEASURED",
        pandolf_csrm_all_g_scaled_w=round(csrm_all_g_w, 2),
        pandolf_carr_newman_unscaled_postural_w=round(carr_newman_w, 2),
        pandolf_load_carriage_share=round(load_share, 4),
        pandolf_tag="DERIVED",
        note=(
            "Norcross (2010) 0.32 g pressurized MKIII table is the operational anchor; "
            "Pandolf CSRM and Carr-Newman variants treat suit mass as backpack load (L/W)^2."
        ),
    )
