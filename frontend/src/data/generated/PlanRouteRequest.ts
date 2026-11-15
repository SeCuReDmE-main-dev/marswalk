/* Generated from middleware Pydantic models via scripts/export-api-contracts.py. */

/**
 * Ordered [lon, lat] stops on the Mars sphere to connect avoiding scarps.
 *
 * @minItems 2
 * @maxItems 32
 */
export type Waypoints = [
  [unknown, unknown],
  [unknown, unknown],
  ...[unknown, unknown][],
];
/**
 * A* heuristic weight (1.0 = strictly optimal, >1.0 = bounded-suboptimal).
 */
export type HeuristicWeight = number;
/**
 * Solar Particle Event (SPE) switch: forces NO_GO + fastest pure-time egress.
 */
export type SpeAlert = boolean;
export type DustTau880Nm = number;
export type PayloadKg = number;
export type RfLinkMarginDb = number;

/**
 * Request payload for `POST /v1/sites/{site_id}/plan-route` (`M2`).
 */
export interface PlanRouteRequest {
  waypoints: Waypoints;
  heuristic_weight?: HeuristicWeight;
  spe_alert?: SpeAlert;
  dust_tau_880nm?: DustTau880Nm;
  payload_kg?: PayloadKg;
  rf_link_margin_db?: RfLinkMarginDb;
}
