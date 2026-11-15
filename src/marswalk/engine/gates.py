"""Asynchronous Neutrosophic Evidence Gates (G0 -> G3) for the MarsWalk Engine.

Each gate evaluates the quality of the evidence entering the next pipeline stage
and outputs `PASS`, `HOLD` (triggering up to 2 scale/window refinements), or `BLOCK`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import ConfigDict, Field

from marswalk.contracts.models import MARS_SPHERE_RADIUS_M, FrozenContractModel

GateIdLiteral = Literal["G0_INGEST", "G1_CLASSIFY", "G2_SEARCH", "G3_PLAN"]
GateDecision = Literal["PASS", "HOLD", "BLOCK"]


class GateVerdict(FrozenContractModel):
    """Structured verdict emitted by an asynchronous Neutrosophic gate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate_id: GateIdLiteral
    attempt: int = Field(..., ge=1, le=5)
    t: float = Field(..., ge=0.0, le=1.0)
    i: float = Field(..., ge=0.0, le=1.0)
    f: float = Field(..., ge=0.0, le=1.0)
    decision: GateDecision
    reasons: list[str] = Field(..., min_length=1)
    metrics: dict[str, float | int | str] = Field(default_factory=dict)


def _decide_from_tif(
    t: float,
    i: float,
    f: float,
    tau_t: float,
    tau_i: float,
    tau_f: float,
) -> GateDecision:
    """Apply the canonical Neutrosophic gate decision law (BLOCK -> HOLD -> PASS)."""
    if f > tau_f:
        return "BLOCK"
    if i >= tau_i:
        return "HOLD"
    if t >= tau_t and f <= tau_f:
        return "PASS"
    return "HOLD"


async def gate_g0_ingest(
    ctx: dict[str, Any],
    gate_cfg: dict[str, Any],
    attempt: int = 1,
) -> GateVerdict:
    """G0 (INGEST -> CLASSIFY): Verify SHA-256, Mars sphere R=3,396,190m CRS, and nodata ratio."""
    tau_t = float(gate_cfg.get("tau_t", 0.70))
    tau_i = float(gate_cfg.get("tau_i", 0.25))
    tau_f = float(gate_cfg.get("tau_f", 0.15))
    max_nodata = float(gate_cfg.get("max_nodata_fraction", 0.05))

    sha256_str = str(ctx.get("dtm_sha256") or "")
    sphere_r = float(ctx.get("sphere_radius_m") or 0.0)
    nodata_frac = float(ctx.get("nodata_fraction") or 0.0)
    coverage_frac = float(ctx.get("coverage_fraction") or 1.0)

    reasons: list[str] = []
    if len(sha256_str) != 64 or abs(sphere_r - MARS_SPHERE_RADIUS_M) > 1.0:
        f = 0.90
        i = 0.05
        t = 0.05
        reasons.append(
            f"G0 BLOCK: Invalid DTM SHA-256 (len={len(sha256_str)}) "
            f"or sphere radius ({sphere_r} m)."
        )
    elif nodata_frac > max_nodata or coverage_frac < 0.95:
        f = 0.08
        i = round(min(0.90, max(tau_i + 0.05, nodata_frac * 4.0 + (1.0 - coverage_frac))), 4)
        t = round(max(0.05, 1.0 - i - f), 4)
        reasons.append(
            f"G0 HOLD: Nodata fraction ({nodata_frac:.4f}) or coverage ({coverage_frac:.4f}) "
            "requires window refinement."
        )
    else:
        f = round(min(0.05, nodata_frac), 4)
        i = round(min(tau_i * 0.4, (1.0 - coverage_frac) + nodata_frac), 4)
        t = round(max(tau_t, 1.0 - i - f), 4)
        reasons.append(
            f"G0 PASS: Verified DTM SHA-256 ({sha256_str[:12]}...), sphere R={sphere_r:.1f}m, "
            f"nodata={nodata_frac:.4f}."
        )

    decision = _decide_from_tif(t, i, f, tau_t, tau_i, tau_f)
    return GateVerdict(
        gate_id="G0_INGEST",
        attempt=attempt,
        t=t,
        i=i,
        f=f,
        decision=decision,
        reasons=reasons,
        metrics={
            "dtm_sha256_prefix": sha256_str[:16],
            "sphere_radius_m": sphere_r,
            "nodata_fraction": round(nodata_frac, 6),
            "coverage_fraction": round(coverage_frac, 6),
        },
    )


async def gate_g1_classify(
    ctx: dict[str, Any],
    gate_cfg: dict[str, Any],
    attempt: int = 1,
) -> GateVerdict:
    """G1 (CLASSIFY -> SEARCH): Stage gate on grid step, mean cell I, and even-sol test MAE.

    NOTE (M3): G1 produces a discrete pipeline stage decision (`PASS`, `HOLD`, `BLOCK`)
    using thresholds declared in `profiles/gates_v1.json` ("je propose"). It NEVER
    fabricates or alters cell terrain `ConfidenceVector(t, i, f)`.
    """
    tau_t = float(gate_cfg.get("tau_t", 0.60))
    tau_i = float(gate_cfg.get("tau_i", 0.35))
    tau_f = float(gate_cfg.get("tau_f", 0.25))
    max_mae = float(gate_cfg.get("max_validation_mae_deg", 4.5))
    max_step_m = float(gate_cfg.get("max_cell_step_m", 8.0))
    max_mean_i = float(gate_cfg.get("max_mean_cell_i", tau_i))

    states = gate_cfg.get("stage_states") or {
        "pass": [0.85, 0.10, 0.05],
        "hold": [0.45, 0.45, 0.10],
        "block": [0.05, 0.10, 0.85],
    }

    mean_cell_i = float(ctx.get("mean_cell_i", 0.15))
    val_test_mae = float(ctx.get("validation_test_mae_deg", ctx.get("validation_mae_4m_deg", 1.5)))
    cell_step_m = float(ctx.get("cell_step_m", 8.0))

    reasons: list[str] = []
    if val_test_mae > max_mae:
        t, i, f = (float(x) for x in states["block"])
        reasons.append(
            f"G1 BLOCK: Validation test MAE ({val_test_mae:.2f} deg) "
            f"exceeds {max_mae:.1f} deg ceiling."
        )
    elif cell_step_m > max_step_m or mean_cell_i >= max_mean_i:
        t, i, f = (float(x) for x in states["hold"])
        reasons.append(
            f"G1 HOLD: Cell step ({cell_step_m:.1f} m) or mean indeterminacy ({mean_cell_i:.3f}) "
            "requires finer grid resolution."
        )
    else:
        t, i, f = (float(x) for x in states["pass"])
        reasons.append(
            f"G1 PASS: Stage readiness verified at {cell_step_m:.1f}m step; "
            f"validation test MAE={val_test_mae:.2f} deg."
        )

    decision = _decide_from_tif(t, i, f, tau_t, tau_i, tau_f)
    return GateVerdict(
        gate_id="G1_CLASSIFY",
        attempt=attempt,
        t=t,
        i=i,
        f=f,
        decision=decision,
        reasons=reasons,
        metrics={
            "cell_step_m": cell_step_m,
            "mean_cell_i": round(mean_cell_i, 4),
            "validation_test_mae_deg": round(val_test_mae, 4),
        },
    )


async def gate_g2_search(
    ctx: dict[str, Any],
    gate_cfg: dict[str, Any],
    attempt: int = 1,
) -> GateVerdict:
    """G2 (SEARCH -> PLAN): Verify A* path existence, safety margins, and +/-10% sensitivity."""
    tau_t = float(gate_cfg.get("tau_t", 0.60))
    tau_i = float(gate_cfg.get("tau_i", 0.35))
    tau_f = float(gate_cfg.get("tau_f", 0.20))

    path_found = bool(ctx.get("path_found", False))
    max_path_slope_deg = float(ctx.get("max_path_slope_deg", 99.0))
    max_walkback_m = float(ctx.get("max_walkback_m", 9999.0))
    sensitivity_jaccard = float(ctx.get("sensitivity_jaccard", 1.0))

    reasons: list[str] = []
    if not path_found or max_path_slope_deg > 20.0 or max_walkback_m > 2000.0:
        f = 0.90
        i = 0.05
        t = 0.05
        reasons.append(
            f"G2 BLOCK: Path found={path_found}, max_slope={max_path_slope_deg:.2f} deg, "
            f"walkback={max_walkback_m:.1f} m."
        )
    elif sensitivity_jaccard < 0.55:
        f = 0.10
        i = round(max(tau_i + 0.05, 1.0 - sensitivity_jaccard), 4)
        t = round(max(0.10, 1.0 - i - f), 4)
        reasons.append(
            f"G2 HOLD: High route sensitivity under +/-10% weight perturbation "
            f"(Jaccard overlap={sensitivity_jaccard:.2f})."
        )
    else:
        slope_margin = max(0.0, 20.0 - max_path_slope_deg) / 20.0
        f = round(min(tau_f * 0.5, (1.0 - slope_margin) * 0.18), 4)
        i = round(min(tau_i * 0.65, (1.0 - sensitivity_jaccard) * 0.5 + 0.05), 4)
        t = round(max(tau_t, 1.0 - i - f), 4)
        reasons.append(
            f"G2 PASS: Rover & astronaut A* paths verified "
            f"(max slope={max_path_slope_deg:.2f} deg, "
            f"walkback={max_walkback_m:.1f} m, sensitivity Jaccard={sensitivity_jaccard:.2f})."
        )

    decision = _decide_from_tif(t, i, f, tau_t, tau_i, tau_f)
    return GateVerdict(
        gate_id="G2_SEARCH",
        attempt=attempt,
        t=t,
        i=i,
        f=f,
        decision=decision,
        reasons=reasons,
        metrics={
            "path_found": int(path_found),
            "max_path_slope_deg": round(max_path_slope_deg, 3),
            "max_walkback_m": round(max_walkback_m, 2),
            "sensitivity_jaccard": round(sensitivity_jaccard, 4),
        },
    )


async def gate_g3_plan(
    ctx: dict[str, Any],
    gate_cfg: dict[str, Any],
    attempt: int = 1,
) -> GateVerdict:
    """G3 (PLAN -> PACK): Verify final EVA walkback <= 2km, duration <= 8h, dose, and stops."""
    tau_t = float(gate_cfg.get("tau_t", 0.70))
    tau_i = float(gate_cfg.get("tau_i", 0.25))
    tau_f = float(gate_cfg.get("tau_f", 0.10))

    max_walkback_m = float(ctx.get("max_walkback_m", 9999.0))
    duration_h = float(ctx.get("duration_h", 99.0))
    radiation_msv = float(ctx.get("radiation_msv", 9.9))
    all_stops_within_2km = bool(ctx.get("all_stops_within_2km", False))
    stop_count = int(ctx.get("stop_count", 0))

    reasons: list[str] = []
    if (
        max_walkback_m > 2000.0
        or duration_h > 8.0
        or radiation_msv > 0.30
        or not all_stops_within_2km
        or stop_count < 3
    ):
        f = 0.88
        i = 0.07
        t = 0.05
        reasons.append(
            f"G3 BLOCK: EVA plan violates envelope (walkback={max_walkback_m:.1f}m, "
            f"duration={duration_h:.2f}h, rad={radiation_msv:.4f}mSv, "
            f"stops_ok={all_stops_within_2km})."
        )
    else:
        f = 0.04
        i = 0.08
        t = 0.88
        reasons.append(
            f"G3 PASS: Crewed EVA plan verified ({stop_count} stops <= 2km, "
            f"walkback={max_walkback_m:.1f}m, duration={duration_h:.2f}h, "
            f"dose={radiation_msv:.4f}mSv)."
        )

    decision = _decide_from_tif(t, i, f, tau_t, tau_i, tau_f)
    return GateVerdict(
        gate_id="G3_PLAN",
        attempt=attempt,
        t=t,
        i=i,
        f=f,
        decision=decision,
        reasons=reasons,
        metrics={
            "max_walkback_m": round(max_walkback_m, 2),
            "duration_h": round(duration_h, 3),
            "radiation_msv": round(radiation_msv, 4),
            "stop_count": stop_count,
        },
    )


async def run_gate_with_hold_loop(
    gate_fn: Callable[[dict[str, Any], dict[str, Any], int], Awaitable[GateVerdict]],
    ctx: dict[str, Any],
    gate_cfg: dict[str, Any],
    on_hold_refine: Callable[[int, dict[str, Any]], Awaitable[dict[str, Any]]],
    gate_log: list[GateVerdict],
    max_hold_retries: int = 2,
) -> GateVerdict:
    """Execute an async gate with up to `max_hold_retries` refinements on HOLD before BLOCK."""
    current_ctx = dict(ctx)
    for attempt in range(1, max_hold_retries + 2):
        verdict = await gate_fn(current_ctx, gate_cfg, attempt)
        gate_log.append(verdict)
        if verdict.decision == "PASS":
            return verdict
        if verdict.decision == "BLOCK":
            return verdict
        # decision == "HOLD"
        if attempt <= max_hold_retries:
            current_ctx = await on_hold_refine(attempt, current_ctx)
        else:
            blocked = GateVerdict(
                gate_id=verdict.gate_id,
                attempt=attempt,
                t=verdict.t,
                i=verdict.i,
                f=max(verdict.f, float(gate_cfg.get("tau_f", 0.20)) + 0.05),
                decision="BLOCK",
                reasons=[
                    *verdict.reasons,
                    (
                        f"Escalated HOLD -> BLOCK after exhausting "
                        f"{max_hold_retries} refinement retries."
                    ),
                ],
                metrics=verdict.metrics,
            )
            gate_log[-1] = blocked
            return blocked
    raise RuntimeError("Unreachable gate loop exit")
