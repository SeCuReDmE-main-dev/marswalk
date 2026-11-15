"""Boolean Pre-Filter (Layer 1) before Neutrosophic / Plithogenic Determination.

Implements Section 2 of `PLAN_PASSE_2B_MOTEUR_BENCHMARKS_50_SOURCES_14_11_26.md`:
Binary conditions are decided immediately in crisp True/False and NEVER leak into
indeterminacy `I`:
1. Empty pixel (`nodata`) or `NaN`/`Inf` (`nodata_fraction >= max_nodata`) -> `CAUTION` / `NO_GO`.
2. Out of bounding box (`bbox`) -> `NO_GO`.
3. Baseline scale finer than `2 * dtm_resolution_m` (e.g. 1 m on 1 m/px DTM) -> scale rejected.
4. Unadmitted upstream `source_id` -> `NO_GO`.
5. Cliff (`slope_deg > 45.0` deg) -> direct `NO_GO` (`reason="cliff: ..."`).

CRITICAL INVARIANT (R2): `rover_tilt_deg` is never read here.
"""

from __future__ import annotations

import math
from typing import TypedDict

from marswalk.contracts.models import VerdictLiteral

ADMITTED_TERRAIN_SOURCES: frozenset[str] = frozenset(
    {
        "SRC-USGS-HIRISE-DTM-1M",
        "SRC-USGS-SIM3464",
        "SRC-TREK-HIRISE-25CM",
        "synthetic-v1",
    }
)

CLIFF_SLOPE_THRESHOLD_DEG: float = 45.0
DEFAULT_MAX_CELL_NODATA_FRACTION: float = 0.20


class ScalePrefilterResult(TypedDict):
    """Boolean prefilter outcome for a spatial baseline scale."""

    keep: bool
    reason: str


class CellPrefilterResult(TypedDict):
    """Boolean prefilter outcome for a terrain cell before T/I/F evaluation."""

    keep: bool
    reason: str
    verdict: VerdictLiteral | None


def prefilter_scale(baseline_m: float, dtm_resolution_m: float = 1.0) -> ScalePrefilterResult:
    """Reject spatial baselines finer than `2 * dtm_resolution_m` (Nyquist pixel-noise rule)."""
    if (
        not math.isfinite(baseline_m)
        or not math.isfinite(dtm_resolution_m)
        or dtm_resolution_m <= 0
    ):
        return {
            "keep": False,
            "reason": "invalid_scale_or_resolution: non-finite or non-positive resolution",
        }
    min_valid_baseline = 2.0 * dtm_resolution_m
    if baseline_m < min_valid_baseline:
        return {
            "keep": False,
            "reason": (
                f"baseline_below_2x_resolution: {baseline_m:.2f}m < 2 * {dtm_resolution_m:.2f}m"
            ),
        }
    return {"keep": True, "reason": "ok"}


def prefilter_cell(
    *,
    lon: float,
    lat: float,
    bbox: tuple[float, float, float, float],
    slope_deg: float,
    nodata_fraction: float,
    source_id: str,
    admitted_sources: frozenset[str] = ADMITTED_TERRAIN_SOURCES,
    max_nodata_fraction: float = DEFAULT_MAX_CELL_NODATA_FRACTION,
    cliff_slope_deg: float = CLIFF_SLOPE_THRESHOLD_DEG,
) -> CellPrefilterResult:
    """Apply crisp boolean pre-checks to a cell before any T/I/F or funnel computation."""
    if source_id not in admitted_sources:
        return {
            "keep": False,
            "reason": f"unadmitted_source: '{source_id}' is not in admitted sources",
            "verdict": "NO_GO",
        }

    if not (math.isfinite(lon) and math.isfinite(lat)):
        return {
            "keep": False,
            "reason": "nan_or_inf_coordinates",
            "verdict": "NO_GO",
        }

    min_lon, min_lat, max_lon, max_lat = bbox
    if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
        return {
            "keep": False,
            "reason": (
                f"out_of_bbox: ({lon:.6f}, {lat:.6f}) outside "
                f"[{min_lon:.6f}, {min_lat:.6f}, {max_lon:.6f}, {max_lat:.6f}]"
            ),
            "verdict": "NO_GO",
        }

    if not math.isfinite(slope_deg) or not math.isfinite(nodata_fraction):
        return {
            "keep": False,
            "reason": "nodata_or_nan: non-finite elevation/slope sample",
            "verdict": "CAUTION",
        }

    if nodata_fraction >= 1.0:
        return {
            "keep": False,
            "reason": "nodata_complete: 100% empty pixels in cell",
            "verdict": "NO_GO",
        }

    if nodata_fraction > max_nodata_fraction:
        return {
            "keep": False,
            "reason": (
                f"nodata_high: cell nodata fraction {nodata_fraction:.2%} exceeds "
                f"{max_nodata_fraction:.2%} boolean ceiling"
            ),
            "verdict": "CAUTION",
        }

    if slope_deg > cliff_slope_deg:
        return {
            "keep": False,
            "reason": (
                f"cliff: slope {slope_deg:.2f} deg > {cliff_slope_deg:.1f} deg vertical limit"
            ),
            "verdict": "NO_GO",
        }

    return {
        "keep": True,
        "reason": "ok",
        "verdict": None,
    }
