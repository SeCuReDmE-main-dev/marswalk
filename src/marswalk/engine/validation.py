"""Ground-Truth Rover Tilt vs. Multi-Scale USGS HiRISE DTM Validation Engine.

Compares Perseverance's IMU ground-truth `rover_tilt_deg` (`MEASURED` from `M20_waypoints.json`)
against the real `1.0 m/px` USGS HiRISE DTM slope computed at `1 m`, `4 m`, `16 m`, and `64 m`
baselines across all 146 stops inside the `2 x 2 km` Western Delta Front window.

CRITICAL INVARIANT (R2):
`rover_tilt_deg` is NEVER used as an input to `hazard_grid.json` or `CLASSIFY`. It is
used exclusively here in `VALIDATION` to quantify at which spatial scale orbital maps
underestimate ground-level slope hazards.
"""

from __future__ import annotations

import math

from pydantic import ConfigDict, Field

from marswalk.contracts.models import (
    CONTRACT_VERSION,
    BaselineKey,
    FrozenContractModel,
    WaypointFeatureCollection,
)
from marswalk.engine.dtm_ingest import (
    IngestedDtmWindow,
    lat_to_eqc_y_m,
    lon_to_eqc_x_m,
    sample_point_multiscale_slopes,
)


class BaselineValidationMetrics(FrozenContractModel):
    """Error metrics comparing a single DTM baseline against ground-truth rover tilt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_m: int
    sample_count: int
    mae_deg: float = Field(..., description="Mean Absolute Error |s_dtm - tilt_rover| (deg).")
    rmse_deg: float = Field(..., description="Root Mean Square Error (deg).")
    bias_deg: float = Field(..., description="Mean signed error (s_dtm - tilt_rover) (deg).")
    steep_sample_count: int = Field(
        ..., description="Number of steep stops (rover_tilt_deg >= 8.0 deg)."
    )
    steep_mae_deg: float = Field(..., description="MAE on steep scarp stops (>= 8.0 deg).")
    steep_bias_deg: float = Field(
        ..., description="Signed bias on steep scarp stops (negative = orbital underestimation)."
    )


class WaypointValidationSample(FrozenContractModel):
    """Per-waypoint comparison of measured Perseverance tilt vs. 1m..64m DTM slopes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    waypoint_id: str
    sol: int
    lon: float
    lat: float
    measured_rover_tilt_deg: float
    dtm_elev_m: float
    dtm_slope_deg_by_baseline: dict[BaselineKey, float]
    signed_error_deg_by_baseline: dict[BaselineKey, float]


class ValidationReport(FrozenContractModel):
    """Complete `validation_report.json` quantifying the orbital-to-ground scale gap."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: str = Field(default=CONTRACT_VERSION)
    pack_version: str = Field(default="1.1.0")
    site_id: str = Field(default="jezero")
    dtm_source_id: str = Field(default="SRC-USGS-HIRISE-DTM-1M")
    rover_source_id: str = Field(default="SRC-M20-WAYPOINTS")
    window_bbox: tuple[float, float, float, float]
    waypoint_count_in_window: int
    steep_threshold_deg: float = Field(default=8.0)
    steep_waypoint_count: int
    metrics_by_baseline: dict[BaselineKey, BaselineValidationMetrics]
    split_rule: str = Field(default="odd_sols_tune_even_sols_test")
    tune_odd_waypoint_count: int = Field(default=0)
    test_even_waypoint_count: int = Field(default=0)
    tune_odd_metrics_by_baseline: dict[BaselineKey, BaselineValidationMetrics] = Field(
        default_factory=dict
    )
    test_even_metrics_by_baseline: dict[BaselineKey, BaselineValidationMetrics] = Field(
        default_factory=dict
    )
    best_overall_baseline_m: int
    worst_steep_baseline_m: int
    orbital_scale_gap_summary: str
    samples: list[WaypointValidationSample]


def _compute_subset_metrics(
    subset: list[WaypointValidationSample],
    steep_threshold_deg: float,
) -> dict[BaselineKey, BaselineValidationMetrics]:
    """Compute per-baseline MAE/RMSE/bias on a disjoint waypoint subset."""
    steep_sub = [s for s in subset if s.measured_rover_tilt_deg >= steep_threshold_deg]
    n_sub = max(1, len(subset))
    n_steep = max(1, len(steep_sub))
    out: dict[BaselineKey, BaselineValidationMetrics] = {}
    for b_key, b_int in (("1", 1), ("4", 4), ("16", 16), ("64", 64)):
        signed_all = [s.signed_error_deg_by_baseline[b_key] for s in subset]
        abs_all = [abs(e) for e in signed_all]
        sq_all = [e * e for e in signed_all]
        signed_steep = [s.signed_error_deg_by_baseline[b_key] for s in steep_sub]
        abs_steep = [abs(e) for e in signed_steep]
        out[b_key] = BaselineValidationMetrics(
            baseline_m=b_int,
            sample_count=len(subset),
            mae_deg=round(sum(abs_all) / n_sub, 3),
            rmse_deg=round(math.sqrt(sum(sq_all) / n_sub), 3),
            bias_deg=round(sum(signed_all) / n_sub, 3),
            steep_sample_count=len(steep_sub),
            steep_mae_deg=round(sum(abs_steep) / n_steep, 3),
            steep_bias_deg=round(sum(signed_steep) / n_steep, 3),
        )
    return out


def build_validation_report(
    dtm: IngestedDtmWindow,
    waypoints: WaypointFeatureCollection,
    steep_threshold_deg: float = 8.0,
) -> ValidationReport:
    """Compare real DTM multi-scale slopes against Perseverance `rover_tilt_deg` in window."""
    win = dtm.window
    samples: list[WaypointValidationSample] = []

    for wp in waypoints.features:
        lon = wp.properties.lon
        lat = wp.properties.lat
        x_m = lon_to_eqc_x_m(lon)
        y_m = lat_to_eqc_y_m(lat)
        if not (win.x_min_m <= x_m <= win.x_max_m and win.y_min_m <= y_m <= win.y_max_m):
            continue

        tilt = float(wp.properties.rover_tilt_deg.value)
        pt_slopes = sample_point_multiscale_slopes(dtm, lon, lat)

        slopes_dict: dict[BaselineKey, float] = {
            "1": round(pt_slopes["1"], 3),
            "4": round(pt_slopes["4"], 3),
            "16": round(pt_slopes["16"], 3),
            "64": round(pt_slopes["64"], 3),
        }
        err_dict: dict[BaselineKey, float] = {
            "1": round(slopes_dict["1"] - tilt, 3),
            "4": round(slopes_dict["4"] - tilt, 3),
            "16": round(slopes_dict["16"] - tilt, 3),
            "64": round(slopes_dict["64"] - tilt, 3),
        }
        samples.append(
            WaypointValidationSample(
                waypoint_id=wp.properties.waypoint_id,
                sol=wp.properties.sol,
                lon=lon,
                lat=lat,
                measured_rover_tilt_deg=round(tilt, 3),
                dtm_elev_m=round(pt_slopes["elev_m"], 2),
                dtm_slope_deg_by_baseline=slopes_dict,
                signed_error_deg_by_baseline=err_dict,
            )
        )

    metrics_by_baseline = _compute_subset_metrics(samples, steep_threshold_deg)
    tune_odd_samples = [s for s in samples if s.sol % 2 == 1]
    test_even_samples = [s for s in samples if s.sol % 2 == 0]
    tune_odd_metrics = _compute_subset_metrics(tune_odd_samples, steep_threshold_deg)
    test_even_metrics = _compute_subset_metrics(test_even_samples, steep_threshold_deg)
    steep_samples = [s for s in samples if s.measured_rover_tilt_deg >= steep_threshold_deg]

    best_b = min(
        test_even_metrics.values(),
        key=lambda m: m.mae_deg,
    ).baseline_m
    worst_steep_b = max(
        test_even_metrics.values(),
        key=lambda m: m.steep_mae_deg,
    ).baseline_m

    m4 = test_even_metrics["4"]
    m16 = test_even_metrics["16"]
    m64 = test_even_metrics["64"]
    summary = (
        f"Disjoint split across {len(samples)} Perseverance stops in the 2x2 km Western "
        f"Delta Front window ({len(tune_odd_samples)} odd-sol tune stops, "
        f"{len(test_even_samples)} even-sol test stops). "
        f"On held-out even test sols: 4m MAE={m4.mae_deg:.2f} deg, "
        f"16m MAE={m16.mae_deg:.2f} deg, 64m MAE={m64.mae_deg:.2f} deg "
        f"(64m steep bias={m64.steep_bias_deg:+.2f} deg, "
        f"steep MAE={m64.steep_mae_deg:.2f} deg)."
    )

    return ValidationReport(
        window_bbox=(win.min_lon, win.min_lat, win.max_lon, win.max_lat),
        waypoint_count_in_window=len(samples),
        steep_threshold_deg=steep_threshold_deg,
        steep_waypoint_count=len(steep_samples),
        metrics_by_baseline=metrics_by_baseline,
        split_rule="odd_sols_tune_even_sols_test",
        tune_odd_waypoint_count=len(tune_odd_samples),
        test_even_waypoint_count=len(test_even_samples),
        tune_odd_metrics_by_baseline=tune_odd_metrics,
        test_even_metrics_by_baseline=test_even_metrics,
        best_overall_baseline_m=best_b,
        worst_steep_baseline_m=worst_steep_b,
        orbital_scale_gap_summary=summary,
        samples=samples,
    )
