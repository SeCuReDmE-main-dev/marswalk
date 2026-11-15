/* Generated from middleware Pydantic models via scripts/export-api-contracts.py. */

export type SiteId = string;
export type PointCount = number;
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
export type Verdict = "GO" | "CAUTION" | "NO_GO";
export type Reasons = string[];
export type TraversedCellIds = string[];
export type RfCommsVerdict = ("GO" | "CAUTION" | "NO_GO") | null;

/**
 * Response payload for `POST /v1/sites/{site_id}/evaluate-route`.
 */
export interface RouteEvaluationResult {
  site_id: SiteId;
  point_count: PointCount;
  total_distance_m: Quantity;
  walkback_distance_m: Quantity;
  walkback_within_limit: WalkbackWithinLimit;
  max_slope_1m_deg: Quantity;
  max_slope_64m_deg: Quantity;
  max_scale_divergence_deg: Quantity;
  estimated_duration_h: Quantity;
  estimated_radiation_msv: Quantity;
  verdict: Verdict;
  reasons: Reasons;
  traversed_cell_ids: TraversedCellIds;
  metabolic_rate_w?: Quantity | null;
  walkback_return_h?: Quantity | null;
  walkback_o2_margin_min?: Quantity | null;
  rf_diffraction_loss_db?: Quantity | null;
  rf_comms_verdict?: RfCommsVerdict;
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
