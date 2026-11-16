/* Generated from middleware Pydantic models via scripts/export-api-contracts.py. */

export type ContractVersion = string;
export type PackVersion = string;
export type SiteId = string;
export type DtmSourceId = string;
export type RoverSourceId = string;
/**
 * @minItems 4
 * @maxItems 4
 */
export type WindowBbox = [unknown, unknown, unknown, unknown];
export type WaypointCountInWindow = number;
export type SteepThresholdDeg = number;
export type SteepWaypointCount = number;
export type BaselineM = number;
export type SampleCount = number;
/**
 * Mean Absolute Error |s_dtm - tilt_rover| (deg).
 */
export type MaeDeg = number;
/**
 * Root Mean Square Error (deg).
 */
export type RmseDeg = number;
/**
 * Mean signed error (s_dtm - tilt_rover) (deg).
 */
export type BiasDeg = number;
/**
 * Number of steep stops (rover_tilt_deg >= 8.0 deg).
 */
export type SteepSampleCount = number;
/**
 * MAE on steep scarp stops (>= 8.0 deg).
 */
export type SteepMaeDeg = number;
/**
 * Signed bias on steep scarp stops (negative = orbital underestimation).
 */
export type SteepBiasDeg = number;
export type SplitRule = string;
export type TuneOddWaypointCount = number;
export type TestEvenWaypointCount = number;
export type BestOverallBaselineM = number;
export type WorstSteepBaselineM = number;
export type OrbitalScaleGapSummary = string;
export type WaypointId = string;
export type Sol = number;
export type Lon = number;
export type Lat = number;
export type MeasuredRoverTiltDeg = number;
export type DtmElevM = number;
export type Samples = WaypointValidationSample[];

/**
 * Complete `validation_report.json` quantifying the orbital-to-ground scale gap.
 */
export interface ValidationReport {
  contract_version?: ContractVersion;
  pack_version?: PackVersion;
  site_id?: SiteId;
  dtm_source_id?: DtmSourceId;
  rover_source_id?: RoverSourceId;
  window_bbox: WindowBbox;
  waypoint_count_in_window: WaypointCountInWindow;
  steep_threshold_deg?: SteepThresholdDeg;
  steep_waypoint_count: SteepWaypointCount;
  metrics_by_baseline: MetricsByBaseline;
  split_rule?: SplitRule;
  tune_odd_waypoint_count?: TuneOddWaypointCount;
  test_even_waypoint_count?: TestEvenWaypointCount;
  tune_odd_metrics_by_baseline?: TuneOddMetricsByBaseline;
  test_even_metrics_by_baseline?: TestEvenMetricsByBaseline;
  best_overall_baseline_m: BestOverallBaselineM;
  worst_steep_baseline_m: WorstSteepBaselineM;
  orbital_scale_gap_summary: OrbitalScaleGapSummary;
  samples: Samples;
}
export interface MetricsByBaseline {
  [k: string]: BaselineValidationMetrics;
}
/**
 * Error metrics comparing a single DTM baseline against ground-truth rover tilt.
 */
export interface BaselineValidationMetrics {
  baseline_m: BaselineM;
  sample_count: SampleCount;
  mae_deg: MaeDeg;
  rmse_deg: RmseDeg;
  bias_deg: BiasDeg;
  steep_sample_count: SteepSampleCount;
  steep_mae_deg: SteepMaeDeg;
  steep_bias_deg: SteepBiasDeg;
}
export interface TuneOddMetricsByBaseline {
  [k: string]: BaselineValidationMetrics;
}
export interface TestEvenMetricsByBaseline {
  [k: string]: BaselineValidationMetrics;
}
/**
 * Per-waypoint comparison of measured Perseverance tilt vs. 1m..64m DTM slopes.
 */
export interface WaypointValidationSample {
  waypoint_id: WaypointId;
  sol: Sol;
  lon: Lon;
  lat: Lat;
  measured_rover_tilt_deg: MeasuredRoverTiltDeg;
  dtm_elev_m: DtmElevM;
  dtm_slope_deg_by_baseline: DtmSlopeDegByBaseline;
  signed_error_deg_by_baseline: SignedErrorDegByBaseline;
}
export interface DtmSlopeDegByBaseline {
  [k: string]: number;
}
export interface SignedErrorDegByBaseline {
  [k: string]: number;
}
