/* Generated from middleware Pydantic models via scripts/export-api-contracts.py. */

/**
 * Ordered list of [lon, lat] waypoints on the Mars sphere.
 *
 * @minItems 2
 * @maxItems 500
 */
export type Points = [
  [unknown, unknown],
  [unknown, unknown],
  ...[unknown, unknown][],
];
export type WalkingSpeedKmH = number;
/**
 * Solar Particle Event (SPE) radiation emergency switch.
 */
export type SpeAlert = boolean;
/**
 * MEDA 880 nm atmospheric dust optical depth (nominal clear season = 0.45).
 */
export type DustTau880Nm = number;
/**
 * Additional carried sample / tool payload mass in kg.
 */
export type PayloadKg = number;
/**
 * UHF 414.2 MHz link margin (dB) between suit (1.8 m) and rover mast (3.0 m).
 */
export type RfLinkMarginDb = number;

/**
 * Request payload for `POST /v1/sites/{site_id}/evaluate-route`.
 */
export interface RouteEvaluationRequest {
  points: Points;
  walking_speed_km_h?: WalkingSpeedKmH;
  spe_alert?: SpeAlert;
  dust_tau_880nm?: DustTau880Nm;
  payload_kg?: PayloadKg;
  rf_link_margin_db?: RfLinkMarginDb;
}
