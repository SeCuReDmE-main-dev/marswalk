/* Generated from middleware Pydantic models via scripts/export-api-contracts.py. */

export type QueryLon = number;
export type QueryLat = number;
export type DistanceToCellCenterM = number;
export type CellId = string;
export type Row = number;
export type Col = number;
export type Lon = number;
export type Lat = number;
export type SizeM = number;
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
/**
 * Verified safety agreement score [0..1].
 */
export type T = number;
/**
 * Scale/coverage uncertainty score [0..1].
 */
export type I = number;
/**
 * Hazard contradiction score [0..1].
 */
export type F = number;
/**
 * Actionable EVA / rover traversability verdict: GO, CAUTION, or NO_GO.
 */
export type Verdict = "GO" | "CAUTION" | "NO_GO";
/**
 * Clear human-readable verdict explanation.
 */
export type Reason = string;
export type NearestWaypointSol = number | null;
export type SpectralSmectiteCaution = boolean | null;
export type GeologicUnit = string | null;
export type AoaInside = boolean | null;
export type RfCommsVerdict = ("GO" | "CAUTION" | "NO_GO") | null;
export type PartialTopographicRefuge = boolean | null;
export type Type = "Feature";
export type Type1 = "Point";
export type Coordinates = [unknown, unknown] | [unknown, unknown, unknown];
export type WaypointId = string;
/**
 * Mars 2020 mission sol.
 */
export type Sol = number;
export type Site = number;
export type Drive = number;
export type Lon1 = number;
export type Lat1 = number;
export type PanoramaUrl = string | null;
export type DistanceToWaypointM = number;

/**
 * Response payload for `GET /v1/sites/{site_id}/cell`.
 */
export interface CellLookupResult {
  query_lon: QueryLon;
  query_lat: QueryLat;
  distance_to_cell_center_m: DistanceToCellCenterM;
  cell: HazardCell;
  nearest_waypoint: Waypoint;
  distance_to_waypoint_m: DistanceToWaypointM;
}
/**
 * Multi-scale terrain & EVA hazard assessment for a single grid cell.
 */
export interface HazardCell {
  cell_id: CellId;
  row: Row;
  col: Col;
  lon: Lon;
  lat: Lat;
  size_m: SizeM;
  elev_m: Quantity;
  slope_deg_by_baseline: SlopeDegByBaseline;
  scale_divergence: Quantity1;
  /**
   * Estimated Cumulative Fractional Area of rocks (%), or None when unavailable.
   */
  rock_cfa_pct?: Quantity | null;
  confidence: ConfidenceVector;
  verdict: Verdict;
  reason: Reason;
  nearest_waypoint_sol?: NearestWaypointSol;
  measured_rover_tilt_deg?: Quantity | null;
  solar_shadow_fraction?: Quantity | null;
  hurst_exponent_h?: Quantity | null;
  step_scale_slope_075m_deg?: Quantity | null;
  thermal_inertia_tiu?: Quantity | null;
  crism_olindex3?: Quantity | null;
  crism_d2300?: Quantity | null;
  crism_bd1900_2?: Quantity | null;
  spectral_smectite_caution?: SpectralSmectiteCaution;
  geologic_unit?: GeologicUnit;
  distance_to_contact_m?: Quantity | null;
  aoa_inside?: AoaInside;
  calibrated_opinion?: ConfidenceVector | null;
  sky_view_factor?: Quantity | null;
  local_gcr_dose_mgy_per_day?: Quantity | null;
  meda_dust_tau_880nm?: Quantity | null;
  metabolic_rate_w?: Quantity | null;
  walkback_o2_margin_min?: Quantity | null;
  rf_bullington_nu?: Quantity | null;
  rf_diffraction_loss_db?: Quantity | null;
  rf_comms_verdict?: RfCommsVerdict;
  partial_topographic_refuge?: PartialTopographicRefuge;
  partial_refuge_gcr_reduction_pct?: Quantity | null;
  obstacle_mask_fraction?: Quantity | null;
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
 * Terrain slope in degrees at 1m, 4m, 16m, and 64m baselines.
 */
export interface SlopeDegByBaseline {
  [k: string]: Quantity;
}
/**
 * Physical scalar quantity with mandatory unit, provenance tag, and source ID.
 */
export interface Quantity1 {
  value: Value;
  unit: Unit;
  tag: Tag;
  source_id: SourceId;
  note?: Note;
}
/**
 * 3-component terrain confidence vector exposed to the UI as `confidence`.
 *
 * - `t`: Verified agreement between orbital baselines and ground-truth rover telemetry [0, 1].
 * - `i`: Scale-gap or coverage uncertainty across baselines [0, 1].
 * - `f`: Active hazard contradiction or safety limit exceedance [0, 1].
 */
export interface ConfidenceVector {
  t: T;
  i: I;
  f: F;
}
/**
 * GeoJSON Feature representing one Perseverance rover waypoint.
 */
export interface Waypoint {
  type?: Type;
  geometry: GeoJsonPointGeometry;
  properties: WaypointProperties;
}
/**
 * GeoJSON Point geometry [lon, lat] or [lon, lat, elev_m].
 */
export interface GeoJsonPointGeometry {
  type?: Type1;
  coordinates: Coordinates;
}
/**
 * Telemetry properties for a single Perseverance rover stop from M20_waypoints.json.
 */
export interface WaypointProperties {
  waypoint_id: WaypointId;
  sol: Sol;
  site: Site;
  drive: Drive;
  lon: Lon1;
  lat: Lat1;
  elev_geoid_m: Quantity;
  rover_tilt_deg: Quantity;
  rover_pitch_deg: Quantity;
  rover_roll_deg: Quantity;
  dist_total_m: Quantity;
  panorama_url?: PanoramaUrl;
}
