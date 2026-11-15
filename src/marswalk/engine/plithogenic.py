"""Plithogenic Multi-Attribute Terrain Classifier with Lexicographic Safety Veto.

Implements the 6 pre-registered attributes (A1..A6), contradiction degrees c(v, v_dom),
plithogenic t-norm / t-conorm / conflict-amplified indeterminacy aggregation, and the
non-compensatory NASA xEVA safety veto.
"""

from __future__ import annotations

from dataclasses import dataclass

from marswalk.contracts.models import ConfidenceVector, VerdictLiteral


@dataclass(frozen=True)
class AttributeEvaluation:
    """Single-attribute Neutrosophic triplet (t, i, f) and contradiction degree c."""

    attr_id: str
    name: str
    t: float
    i: float
    f: float
    contradiction_c: float
    summary: str


@dataclass(frozen=True)
class CellPlithogenicResult:
    """Aggregated plithogenic evaluation and safety-veto verdict for a terrain cell."""

    confidence: ConfidenceVector
    verdict: VerdictLiteral
    veto_triggered: bool
    dominant_conflict_attr: str
    reason: str
    attributes: tuple[AttributeEvaluation, ...]


def plithogenic_and_t(t_a: float, t_b: float, c: float) -> float:
    """Plithogenic conjunction for Truth membership: (1-c)*(ta*tb) + c*(ta + tb - ta*tb)."""
    c_clamped = max(0.0, min(1.0, c))
    ta = max(0.0, min(1.0, t_a))
    tb = max(0.0, min(1.0, t_b))
    val = (1.0 - c_clamped) * (ta * tb) + c_clamped * (ta + tb - ta * tb)
    return max(0.0, min(1.0, val))


def plithogenic_or_f(f_a: float, f_b: float, c: float) -> float:
    """Plithogenic disjunction (dual of AND_p) for Falsehood membership."""
    c_clamped = max(0.0, min(1.0, c))
    fa = max(0.0, min(1.0, f_a))
    fb = max(0.0, min(1.0, f_b))
    val = (1.0 - c_clamped) * (fa + fb - fa * fb) + c_clamped * (fa * fb)
    return max(0.0, min(1.0, val))


def plithogenic_combine_triplet(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: float,
) -> tuple[float, float, float]:
    """Aggregate two Neutrosophic triplets (t, i, f) with contradiction degree c in [0, 1].

    Conflict between attributes (c * |t_a - t_b|) directly increases indeterminacy `i`.
    """
    c_clamped = max(0.0, min(1.0, c))
    t_a, i_a, f_a = a
    t_b, i_b, f_b = b
    t_out = plithogenic_and_t(t_a, t_b, c_clamped)
    f_out = plithogenic_or_f(f_a, f_b, c_clamped)
    i_out = min(1.0, max(0.0, 0.5 * (i_a + i_b) + c_clamped * abs(t_a - t_b)))
    return (t_out, i_out, f_out)


def _eval_a1_multiscale_slope(
    s1: float, s4: float, s16: float, s64: float, nodata_local: float
) -> AttributeEvaluation:
    eff_slope = max(s1, s4)
    if eff_slope <= 5.0:
        c = 0.02
        t, f = 0.94, 0.02
    elif eff_slope <= 10.0:
        c = 0.12
        t, f = 0.82, 0.08
    elif eff_slope <= 15.0:
        c = 0.28
        t, f = 0.66, 0.18
    elif eff_slope <= 20.0:
        c = 0.60
        t, f = 0.38, 0.42
    else:
        c = 0.95
        t, f = 0.04, 0.88
    i = min(0.85, max(0.04, nodata_local * 0.6 + abs(s1 - s64) / 35.0))
    return AttributeEvaluation(
        attr_id="A1",
        name="A1_multiscale_slope",
        t=t,
        i=i,
        f=f,
        contradiction_c=c,
        summary=f"1m={s1:.1f}deg, 4m={s4:.1f}deg, 64m={s64:.1f}deg",
    )


def _eval_a2_scale_divergence(divergence_deg: float, roughness_deg: float) -> AttributeEvaluation:
    combined = divergence_deg + 0.5 * roughness_deg
    if combined <= 2.0:
        c = 0.05
        t, i, f = 0.90, 0.06, 0.04
    elif combined <= 5.0:
        c = 0.30
        t, i, f = 0.68, 0.20, 0.12
    elif combined <= 8.0:
        c = 0.65
        t, i, f = 0.40, 0.38, 0.22
    else:
        c = 0.90
        t, i, f = 0.15, 0.55, 0.30
    return AttributeEvaluation(
        attr_id="A2",
        name="A2_scale_divergence",
        t=t,
        i=i,
        f=f,
        contradiction_c=c,
        summary=f"divergence={divergence_deg:.1f}deg, roughness={roughness_deg:.2f}deg",
    )


def _eval_a3_suit_margin(s1: float) -> AttributeEvaluation:
    margin = 20.0 - s1
    if margin >= 10.0:
        c = 0.02
        t, i, f = 0.93, 0.04, 0.03
    elif margin >= 5.0:
        c = 0.15
        t, i, f = 0.78, 0.10, 0.12
    elif margin >= 2.0:
        c = 0.55
        t, i, f = 0.45, 0.22, 0.33
    else:
        c = 0.92
        t, i, f = 0.08, 0.20, 0.72
    return AttributeEvaluation(
        attr_id="A3",
        name="A3_suit_slope_margin",
        t=t,
        i=i,
        f=f,
        contradiction_c=c,
        summary=f"suit_margin={margin:.1f}deg",
    )


def _eval_a4_walkback(walkback_m: float) -> AttributeEvaluation:
    if walkback_m <= 1000.0:
        c = 0.02
        t, i, f = 0.94, 0.04, 0.02
    elif walkback_m <= 1500.0:
        c = 0.18
        t, i, f = 0.80, 0.10, 0.10
    elif walkback_m <= 2000.0:
        c = 0.42
        t, i, f = 0.62, 0.18, 0.20
    else:
        c = 1.00
        t, i, f = 0.02, 0.08, 0.90
    return AttributeEvaluation(
        attr_id="A4",
        name="A4_walkback_distance",
        t=t,
        i=i,
        f=f,
        contradiction_c=c,
        summary=f"walkback={walkback_m:.0f}m",
    )


def _eval_a5_geologic_unit(unit_code: str) -> AttributeEvaluation:
    code_lower = unit_code.lower()
    if "delta" in code_lower or "d-" in code_lower or "apron" in code_lower:
        c = 0.05
        t, i, f = 0.90, 0.06, 0.04
    elif "margin" in code_lower or "contact" in code_lower:
        c = 0.25
        t, i, f = 0.76, 0.14, 0.10
    elif "cf-" in code_lower or "floor" in code_lower:
        c = 0.45
        t, i, f = 0.68, 0.18, 0.14
    else:
        c = 0.85
        t, i, f = 0.30, 0.35, 0.35
    return AttributeEvaluation(
        attr_id="A5",
        name="A5_geologic_unit",
        t=t,
        i=i,
        f=f,
        contradiction_c=c,
        summary=f"unit={unit_code}",
    )


def _eval_a6_science_proximity(dist_to_m20_stop_m: float) -> AttributeEvaluation:
    if dist_to_m20_stop_m <= 150.0:
        c = 0.04
        t, i, f = 0.92, 0.05, 0.03
    elif dist_to_m20_stop_m <= 350.0:
        c = 0.22
        t, i, f = 0.76, 0.14, 0.10
    elif dist_to_m20_stop_m <= 700.0:
        c = 0.50
        t, i, f = 0.55, 0.28, 0.17
    else:
        c = 0.78
        t, i, f = 0.35, 0.45, 0.20
    return AttributeEvaluation(
        attr_id="A6",
        name="A6_science_proximity",
        t=t,
        i=i,
        f=f,
        contradiction_c=c,
        summary=f"m20_dist={dist_to_m20_stop_m:.0f}m",
    )


def evaluate_cell_plithogenic(
    *,
    s1_deg: float,
    s4_deg: float,
    s16_deg: float,
    s64_deg: float,
    divergence_deg: float,
    roughness_deg: float,
    walkback_m: float,
    geologic_unit: str,
    dist_to_m20_stop_m: float,
    nodata_local: float = 0.0,
    suit_max_slope_deg: float = 20.0,
    walkback_max_m: float = 2000.0,
    rover_sand_slope_deg: float = 10.0,
) -> CellPlithogenicResult:
    """Evaluate a terrain cell across A1..A6 with Lexicographic Safety Veto first."""
    a1 = _eval_a1_multiscale_slope(s1_deg, s4_deg, s16_deg, s64_deg, nodata_local)
    a2 = _eval_a2_scale_divergence(divergence_deg, roughness_deg)
    a3 = _eval_a3_suit_margin(s1_deg)
    a4 = _eval_a4_walkback(walkback_m)
    a5 = _eval_a5_geologic_unit(geologic_unit)
    a6 = _eval_a6_science_proximity(dist_to_m20_stop_m)
    attrs = (a1, a2, a3, a4, a5, a6)

    # 1. LEXICOGRAPHIC NON-COMPENSATORY SAFETY VETO (Before Aggregation)
    # Neither high geologic value (A5) nor close M20 proximity (A6) can ever override
    # a 1m slope > 20.0 deg or walkback > 2,000 m.
    if s1_deg > suit_max_slope_deg or walkback_m > walkback_max_m:
        veto_attr = "A1_multiscale_slope" if s1_deg > suit_max_slope_deg else "A4_walkback_distance"
        f_veto = round(
            min(0.98, max(0.85, (s1_deg - 15.0) / 10.0 if s1_deg > suit_max_slope_deg else 0.92)), 4
        )
        i_veto = round(min(0.12, max(0.02, divergence_deg / 40.0)), 4)
        t_veto = round(max(0.01, 1.0 - f_veto - i_veto), 4)
        reason = (
            f"SAFETY VETO ({veto_attr}): 1m DTM slope "
            f"({s1_deg:.1f} deg vs {suit_max_slope_deg:.1f} deg limit) "
            f"or walkback ({walkback_m:.0f} m vs {walkback_max_m:.0f} m limit) breached; "
            f"64m orbital slope is {s64_deg:.1f} deg (divergence {divergence_deg:.1f} deg)."
        )
        return CellPlithogenicResult(
            confidence=ConfidenceVector(t=t_veto, i=i_veto, f=f_veto),
            verdict="NO_GO",
            veto_triggered=True,
            dominant_conflict_attr=veto_attr,
            reason=reason,
            attributes=attrs,
        )

    # 2. Plithogenic sequential aggregation across A1..A6
    cur_t, cur_i, cur_f = (a1.t, a1.i, a1.f)
    for nxt in attrs[1:]:
        c_pair = 0.5 * (a1.contradiction_c + nxt.contradiction_c)
        cur_t, cur_i, cur_f = plithogenic_combine_triplet(
            (cur_t, cur_i, cur_f),
            (nxt.t, nxt.i, nxt.f),
            c_pair,
        )

    cur_t = round(max(0.0, min(1.0, cur_t)), 4)
    cur_i = round(max(0.0, min(1.0, cur_i)), 4)
    cur_f = round(max(0.0, min(1.0, cur_f)), 4)

    dominant_attr = max(attrs, key=lambda a: a.contradiction_c * (1.0 - a.t))

    # 3. Verdict classification rule (GO if t >= 0.6 and f <= 0.2; NO_GO if f >= 0.5; else CAUTION)
    if cur_f >= 0.50:
        verdict: VerdictLiteral = "NO_GO"
    elif cur_t >= 0.60 and cur_f <= 0.20 and s1_deg < rover_sand_slope_deg and divergence_deg < 4.5:
        verdict = "GO"
    else:
        verdict = "CAUTION"

    reason = (
        f"Plithogenic {verdict} (T={cur_t:.2f}, I={cur_i:.2f}, F={cur_f:.2f}; dominant conflict "
        f"{dominant_attr.name}): 1m={s1_deg:.1f} deg, 4m={s4_deg:.1f} deg, "
        f"16m={s16_deg:.1f} deg, 64m={s64_deg:.1f} deg (divergence={divergence_deg:.1f} deg)."
    )
    return CellPlithogenicResult(
        confidence=ConfidenceVector(t=cur_t, i=cur_i, f=cur_f),
        verdict=verdict,
        veto_triggered=False,
        dominant_conflict_attr=dominant_attr.name,
        reason=reason,
        attributes=attrs,
    )
