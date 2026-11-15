"""Multi-Scale Fractal Pruning Funnel (`funnel.py`) with Persistence Safety Guarantee.

Implements Section 4 of `MOTEUR_PLITHOGENIQUE_SWEET_SPOT_MARTIAN_MAP_14_11_26.md` and
Block B1 of `PROMPT_ANTIGRAVITY_PASSE2B_V2_FUNNEL_21H20.md`:
- Iteratively prunes isolated single-scale artifacts (`f* = argmax F`, `t* = argmin T`)
  across scales from coarsest (`64 m`) to finest (`4 m`), converging toward the midpoint
  of the upper truth quartile `[Q_0.75(T), max(T)]`.
- SAFETY PERSISTENCE RULE: Any elevated hazard (`F >= 0.5` or `T <= 0.5`) that persists
  across `>= p` neighboring scales is a structural terrain feature (e.g. a real scarp),
  NEVER an artifact: it is never pruned and immediately fixes a `NO_GO` or `CAUTION` exit.
- ENTROPY FLOOR (`H_min > 0`): Stops pruning before survivor Shannon entropy drops below
  `H_min`, guaranteeing `I* > 0` everywhere (never collapsing to a single overconfident scalar).
- GUARANTEED TERMINATION: Strictly bounded to `<= len(E) // 2` iterations.

CRITICAL INVARIANT (R2): Ground-truth rover tilt is NEVER read in this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from marswalk.contracts.models import ConfidenceVector, VerdictLiteral


@dataclass(frozen=True)
class CarrierScaleTriplet:
    """Single `(carrier, scale_m, t, i, f)` observation entering the cell funnel."""

    carrier: str
    scale_m: int
    t: float
    i: float
    f: float


@dataclass(frozen=True)
class FunnelParams:
    """Validated hyperparameters `(p, tau_max, h_min, eps)` for the pruning funnel."""

    p: int = 2
    tau_max: float = 0.25
    h_min: float = 0.50
    eps: float = 0.01

    def __post_init__(self) -> None:
        if int(self.p) < 2:
            raise ValueError(f"Funnel parameter p must be >= 2 (got {self.p}); p=1 erases cliffs.")
        if not (0.0 < float(self.tau_max) <= 0.40):
            raise ValueError(
                f"Funnel parameter tau_max must be in (0.0, 0.40] (got {self.tau_max})."
            )
        if float(self.h_min) <= 0.0 or not math.isfinite(self.h_min):
            raise ValueError(f"Funnel parameter h_min must be > 0.0 bits (got {self.h_min}).")
        if float(self.eps) < 1e-4 or not math.isfinite(self.eps):
            raise ValueError(f"Funnel parameter eps must be >= 1e-4 (got {self.eps}).")


@dataclass(frozen=True)
class FunnelOutput:
    """Output of `run_cell_funnel` for a single terrain cell."""

    t_star: float
    i_star: float
    f_star: float
    verdict: VerdictLiteral
    retained_slope_deg: float
    retained_scale_m: int
    iterations: int
    pruned_fraction: float
    entropy_bits: float
    persistent_hazard_detected: bool
    trace: tuple[dict[str, Any], ...]

    @property
    def confidence(self) -> ConfidenceVector:
        """Return contract-compatible `ConfidenceVector(t, i, f)`."""
        return ConfidenceVector(t=self.t_star, i=self.i_star, f=self.f_star)

    def to_dict(self) -> dict[str, Any]:
        """Deterministic dictionary representation for hashing and JSON export."""
        return {
            "t_star": self.t_star,
            "i_star": self.i_star,
            "f_star": self.f_star,
            "verdict": self.verdict,
            "retained_slope_deg": self.retained_slope_deg,
            "retained_scale_m": self.retained_scale_m,
            "iterations": self.iterations,
            "pruned_fraction": self.pruned_fraction,
            "entropy_bits": self.entropy_bits,
            "persistent_hazard_detected": self.persistent_hazard_detected,
            "trace": list(self.trace),
        }


def shannon_entropy_bits(values: list[float], n_bins: int = 8) -> float:
    """Compute discrete Shannon entropy (in bits) of `T` values across `n_bins` on `[0, 1]`."""
    n = len(values)
    if n < 2:
        return 0.0
    counts = [0] * n_bins
    for v in values:
        clamped = max(0.0, min(1.0, v))
        idx = min(n_bins - 1, int(clamped * n_bins))
        counts[idx] += 1
    ent = 0.0
    for c in counts:
        if c > 0:
            prob = c / float(n)
            ent -= prob * math.log2(prob)
    return round(ent, 6)


def _quantile_75(values: list[float]) -> float:
    """Deterministic linear-interpolated 0.75 quantile of a non-empty float list."""
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = 0.75 * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    frac = pos - lo
    return s[lo] * (1.0 - frac) + s[hi] * frac


def _persists_across_neighbor_scales(
    candidate: CarrierScaleTriplet,
    pool: list[CarrierScaleTriplet],
    ordered_scales: list[int],
    p_min: int,
    *,
    mode: str,
) -> bool:
    """Return True iff `candidate`'s carrier triggers on `>= p_min` contiguous neighbor scales."""
    flagged_scales: set[int] = set()
    for item in pool:
        if item.carrier != candidate.carrier:
            continue
        if mode == "high_f" and item.f >= 0.50:
            flagged_scales.add(item.scale_m)
        elif mode == "low_t" and item.t <= 0.50:
            flagged_scales.add(item.scale_m)

    if candidate.scale_m not in flagged_scales:
        return False

    # Measure length of the contiguous run of flagged scales containing `candidate.scale_m`
    idx = ordered_scales.index(candidate.scale_m)
    run_len = 1
    left = idx - 1
    while left >= 0 and ordered_scales[left] in flagged_scales:
        run_len += 1
        left -= 1
    right = idx + 1
    while right < len(ordered_scales) and ordered_scales[right] in flagged_scales:
        run_len += 1
        right += 1
    return run_len >= p_min


def _max_persistent_f(
    pool: list[CarrierScaleTriplet],
    ordered_scales: list[int],
    p_min: int,
) -> float:
    """Compute the highest `F` among carriers that persist across `>= p_min` neighbor scales."""
    by_carrier_scale: dict[str, dict[int, float]] = {}
    for item in pool:
        by_carrier_scale.setdefault(item.carrier, {})[item.scale_m] = item.f

    best_f = 0.0
    for _cname, scale_map in by_carrier_scale.items():
        # Sliding window of length `p_min` over neighboring scales
        if len(ordered_scales) >= p_min:
            for i in range(len(ordered_scales) - p_min + 1):
                win_scales = ordered_scales[i : i + p_min]
                if all(s in scale_map for s in win_scales):
                    # Persistent level across the `p_min` neighbors is the minimum F in that run
                    pers_level = min(scale_map[s] for s in win_scales)
                    if pers_level > best_f:
                        best_f = pers_level
    return round(best_f, 4)


def _compute_retained_slope_and_scale(
    survivors: list[CarrierScaleTriplet],
    slopes_by_scale: dict[int, float],
    ordered_scales: list[int],
    persistent_hazard: bool,
    hazard_scale_m: int | None,
) -> tuple[float, int]:
    """Compute the cell's retained slope (deg) and dominant scale from funnel survivors."""
    valid_slopes = {s: slopes_by_scale[s] for s in ordered_scales if s in slopes_by_scale}
    if not valid_slopes:
        return (0.0, ordered_scales[-1] if ordered_scales else 16)

    if persistent_hazard and hazard_scale_m in valid_slopes:
        # Never smooth away a persistent multi-scale slope scarp (I_slope with F >= 0.50)
        pers_slopes = [
            valid_slopes[s]
            for s in valid_slopes
            if any(tr.carrier == "I_slope" and tr.scale_m == s and tr.f >= 0.50 for tr in survivors)
        ]
        if pers_slopes:
            best_s = max(valid_slopes, key=lambda k: valid_slopes[k])
            return (round(max(pers_slopes), 3), best_s)

    # Weight each scale by survivor reliability: T * (1 - I), giving primary weight to
    # geometric terrain carriers (`I_slope`, `I_diverge`, `I_rough`, `I_scale`).
    # When no persistent multi-scale slope scarp is detected, favor the 16 m intermediate
    # rover-chassis scale over 4 m local facet jitter and 64 m coarse over-smoothing.
    geometric_carriers = {"I_slope", "I_diverge", "I_rough", "I_scale", "I_texture"}
    scale_prior = {4: 0.08, 16: 12.0, 64: 0.10}
    scale_weights: dict[int, float] = {s: 1e-6 for s in valid_slopes}
    for tr in survivors:
        if tr.scale_m in scale_weights:
            mult = 2.5 if tr.carrier in geometric_carriers else 1.0
            prior = scale_prior.get(tr.scale_m, 1.0)
            # Penalize scales with high local divergence or coarse smoothing uncertainty
            scale_weights[tr.scale_m] += prior * mult * tr.t * max(0.05, 1.0 - tr.i)

    total_w = sum(scale_weights.values())
    retained_slope = sum(valid_slopes[s] * scale_weights[s] for s in valid_slopes) / total_w
    dominant_scale = max(scale_weights, key=lambda k: scale_weights[k])
    return (round(retained_slope, 3), dominant_scale)


def run_cell_funnel(
    triplets: list[CarrierScaleTriplet],
    *,
    params: FunnelParams | None = None,
    slopes_by_scale: dict[int, float] | None = None,
    suit_max_slope_deg: float = 20.0,
    walkback_m: float = 0.0,
    walkback_max_m: float = 2000.0,
) -> FunnelOutput:
    """Execute the multi-scale fractal pruning funnel on a `(carrier, scale, T, I, F)` pool."""
    cfg = params if params is not None else FunnelParams()
    if len(triplets) < 2:
        raise ValueError("Funnel requires at least 2 triplets in E.")

    slopes_map = dict(slopes_by_scale or {})
    ordered_scales = sorted({tr.scale_m for tr in triplets}, reverse=True)
    pool = list(triplets)
    n0 = len(pool)
    max_iters = n0 // 2

    trace: list[dict[str, Any]] = []
    iterations = 0
    persistent_hazard = False
    hazard_scale_m: int | None = None
    f_persistent_exit = 0.0
    prev_t_c: float | None = None
    t_c = 0.5 * (_quantile_75([x.t for x in pool]) + max(x.t for x in pool))

    # Lexicographic non-compensatory walkback check
    if walkback_m > walkback_max_m:
        ent = shannon_entropy_bits([x.t for x in pool])
        dom_sc = ordered_scales[-1]
        s_ret = round(float(slopes_map.get(dom_sc, 0.0)), 3)
        return FunnelOutput(
            t_star=0.04,
            i_star=0.06,
            f_star=0.90,
            verdict="NO_GO",
            retained_slope_deg=s_ret,
            retained_scale_m=dom_sc,
            iterations=0,
            pruned_fraction=0.0,
            entropy_bits=round(ent, 4),
            persistent_hazard_detected=True,
            trace=({"carrier": "I_constraint", "scale_m": dom_sc, "reason": "walkback_veto"},),
        )

    # Outer funnel pass from coarsest scale to finest scale
    stop_all = False
    for current_scale in ordered_scales:
        if stop_all:
            break
        while iterations < max_iters:
            # 1. f* = argmax F in E
            f_idx = max(
                range(len(pool)),
                key=lambda idx: (
                    pool[idx].f,
                    -pool[idx].t,
                    1 if pool[idx].scale_m == current_scale else 0,
                    pool[idx].carrier,
                    -pool[idx].scale_m,
                ),
            )
            f_star_item = pool[f_idx]
            if f_star_item.f >= 0.50 and _persists_across_neighbor_scales(
                f_star_item, pool, ordered_scales, cfg.p, mode="high_f"
            ):
                persistent_hazard = True
                hazard_scale_m = f_star_item.scale_m
                f_persistent_exit = f_star_item.f
                trace.append(
                    {
                        "carrier": f_star_item.carrier,
                        "scale_m": f_star_item.scale_m,
                        "action": "PERSISTENT_HAZARD_EXIT",
                        "reason": (
                            f"persistent_high_F>={cfg.p}_scales "
                            f"(F={f_star_item.f:.3f} on {f_star_item.carrier})"
                        ),
                    }
                )
                stop_all = True
                break

            # 2. t* = argmin T in E (with same persistence test when T <= 0.50)
            t_idx = min(
                range(len(pool)),
                key=lambda idx: (
                    pool[idx].t,
                    -pool[idx].f,
                    0 if pool[idx].scale_m == current_scale else 1,
                    pool[idx].carrier,
                    pool[idx].scale_m,
                ),
            )
            t_star_item = pool[t_idx]
            if t_star_item.t <= 0.50 and _persists_across_neighbor_scales(
                t_star_item, pool, ordered_scales, cfg.p, mode="low_t"
            ):
                persistent_hazard = True
                hazard_scale_m = t_star_item.scale_m
                f_persistent_exit = max(f_star_item.f * 0.5, t_star_item.f, 0.50)
                trace.append(
                    {
                        "carrier": t_star_item.carrier,
                        "scale_m": t_star_item.scale_m,
                        "action": "PERSISTENT_LOW_T_EXIT",
                        "reason": (
                            f"persistent_low_T>={cfg.p}_scales "
                            f"(T={t_star_item.t:.3f} on {t_star_item.carrier})"
                        ),
                    }
                )
                stop_all = True
                break

            # 3. Candidate E' = E \ {f*, t*}
            remove_indices = {f_idx, t_idx}
            candidate_pool = [item for idx, item in enumerate(pool) if idx not in remove_indices]
            pruned_frac_next = (n0 - len(candidate_pool)) / float(n0)
            ent_next = shannon_entropy_bits([x.t for x in candidate_pool])

            if len(candidate_pool) < 2 or pruned_frac_next > cfg.tau_max or ent_next < cfg.h_min:
                stop_all = True
                break

            # Commit pruning step
            iterations += 1
            for r_idx in sorted(remove_indices):
                rem = pool[r_idx]
                role = "argmax_F_spike" if r_idx == f_idx else "argmin_T_outlier"
                trace.append(
                    {
                        "carrier": rem.carrier,
                        "scale_m": rem.scale_m,
                        "action": "PRUNED",
                        "reason": f"{role}_at_{rem.scale_m}m (T={rem.t:.3f}, F={rem.f:.3f})",
                    }
                )
            pool = candidate_pool

            new_t_c = 0.5 * (_quantile_75([x.t for x in pool]) + max(x.t for x in pool))
            if prev_t_c is not None and abs(new_t_c - prev_t_c) < cfg.eps:
                t_c = new_t_c
                prev_t_c = new_t_c
                break
            prev_t_c = new_t_c
            t_c = new_t_c

    pruned_frac = round((n0 - len(pool)) / float(n0), 4)
    surviving_t = [x.t for x in pool]
    mean_t = sum(surviving_t) / float(len(surviving_t))
    std_t = math.sqrt(sum((v - mean_t) ** 2 for v in surviving_t) / float(len(surviving_t)))
    mean_i_surv = sum(x.i for x in pool) / float(len(pool))
    ent_final = shannon_entropy_bits(surviving_t)

    # I* = survivor dispersion + pruned fraction + residual local indeterminacy (strictly > 0)
    i_star = round(
        min(0.98, max(0.01, std_t + 0.50 * pruned_frac + 0.25 * mean_i_surv)),
        4,
    )

    retained_slope, retained_scale = _compute_retained_slope_and_scale(
        pool, slopes_map, ordered_scales, persistent_hazard, hazard_scale_m
    )

    if persistent_hazard:
        f_star = round(min(0.99, max(0.50, f_persistent_exit)), 4)
        t_star = round(max(0.01, min(0.49, 1.0 - f_star)), 4)
        slope_allows_nogo = (not slopes_map) or (retained_slope >= 11.5)
        if retained_slope >= suit_max_slope_deg or (f_star >= 0.78 and slope_allows_nogo):
            verdict: VerdictLiteral = "NO_GO"
        else:
            verdict = "CAUTION"
    else:
        f_star = _max_persistent_f(pool, ordered_scales, cfg.p)
        t_star = round(max(0.01, min(0.99, t_c)), 4)
        slope_allows_nogo = (not slopes_map) or (retained_slope >= 11.5)
        if retained_slope >= suit_max_slope_deg or f_star >= 0.50:
            verdict = (
                "NO_GO"
                if retained_slope >= suit_max_slope_deg or (f_star >= 0.75 and slope_allows_nogo)
                else "CAUTION"
            )
        elif t_star >= 0.72 and f_star <= 0.22 and retained_slope < 10.0 and i_star < 0.35:
            verdict = "GO"
        else:
            verdict = "CAUTION"

    return FunnelOutput(
        t_star=t_star,
        i_star=i_star,
        f_star=f_star,
        verdict=verdict,
        retained_slope_deg=retained_slope,
        retained_scale_m=retained_scale,
        iterations=iterations,
        pruned_fraction=pruned_frac,
        entropy_bits=round(ent_final, 4),
        persistent_hazard_detected=persistent_hazard,
        trace=tuple(trace),
    )
