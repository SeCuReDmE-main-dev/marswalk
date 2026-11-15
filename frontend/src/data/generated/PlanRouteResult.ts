/* Generated from middleware Pydantic models via scripts/export-api-contracts.py. */

export type SiteId = string;
export type Reachable = boolean;
export type Coordinates = [unknown, unknown][];
/**
 * Numeric scalar value (finite float).
 */
export type Value = number;
/**
 * Physical unit (e.g. 'm', 'deg', 'mSv/day').
 */
export type Unit = string;
/**
 * Data provenance: MEASURED, DERIVED, or SIMULATED.
 */
export type Tag = "MEASURED" | "DERIVED" | "SIMULATED" | "UNAVAILABLE";
/**
 * Identifier matching an entry in SiteManifest.sources.
 */
export type SourceId = string;
/**
 * Optional provenance or proxy clarification note.
 */
export type Note = string | null;
export type WalkbackWithinLimit = boolean;
export type CellsExpanded = number;
export type OptimalityGuarantee = string;
export type Verdict = "GO" | "CAUTION" | "NO_GO";
export type Reasons = string[];
export type CandidatesTested = number;
export type AcceptedCount = number;
export type RejectedByObstacleCount = number;
export type RejectedByCostGuardCount = number;
export type RawCostS = number;
export type SmoothedCostS = number;
export type RfCommsVerdict = "GO" | "CAUTION" | "NO_GO";

/**
 * Response payload for `POST /v1/sites/{site_id}/plan-route` (zero camera fields).
 */
export interface PlanRouteResult {
  site_id: SiteId;
  reachable: Reachable;
  coordinates: Coordinates;
  total_distance_m: Quantity;
  walkback_distance_m: Quantity;
  walkback_within_limit: WalkbackWithinLimit;
  pure_walking_time_s: Quantity;
  max_longitudinal_slope_deg: Quantity;
  max_cross_slope_deg: Quantity;
  cells_expanded: CellsExpanded;
  optimality_guarantee: OptimalityGuarantee;
  verdict: Verdict;
  reasons: Reasons;
  string_pull_audit: PlanRouteStringPullSummary;
  metabolic_rate_w: Quantity;
  walkback_o2_margin_min: Quantity;
  rf_bullington_nu: Quantity;
  rf_min_clearance_over_f1: Quantity;
  rf_diffraction_loss_db: Quantity;
  rf_comms_verdict: RfCommsVerdict;
}
/**
 * Physical scalar quantity with mandatory unit, provenance tag, and source ID.
 */
export interface Quantity {
  value: Value;
  unit: Unit;
  tag: Tag;
  source_id: SourceId;
  note?: Note;
}
/**
 * Measured string-pulling audit counters returned by `/plan-route` (`H2`).
 */
export interface PlanRouteStringPullSummary {
  candidates_tested: CandidatesTested;
  accepted_count: AcceptedCount;
  rejected_by_obstacle_count: RejectedByObstacleCount;
  rejected_by_cost_guard_count: RejectedByCostGuardCount;
  raw_cost_s: RawCostS;
  smoothed_cost_s: SmoothedCostS;
}
