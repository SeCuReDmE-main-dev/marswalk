/* Generated from the frozen shared JSON Schema. Run npm run types:generate. */

export type ContractVersion = "1.0.0" | "1.1.0";
/**
 * PLACEHOLDER in Pass 1 synthetic scaffold; ENGINE when built from HiRISE DTM.
 */
export type GridStatus = "PLACEHOLDER" | "ENGINE";
export type SiteId = string;
/**
 * @minItems 4
 * @maxItems 4
 */
export type Bbox = [unknown, unknown, unknown, unknown];
export type Rows = number;
export type Cols = number;
export type CellSizeM = number;
/**
 * @minItems 4
 * @maxItems 4
 */
export type BaselinesM = [unknown, unknown, unknown, unknown];
export type OverlayFile = string;
export type ExternalLayersStatus = {
  [k: string]: {
    [k: string]: string | number | boolean;
  };
} | null;
/**
 * @minItems 1
 */
export type Cells = [HazardCell, ...HazardCell[]];
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

/**
 * Complete multi-scale hazard grid (`hazard_grid.json`) for a site pack.
 */
export interface HazardGrid {
  contract_version?: ContractVersion;
  grid_status?: GridStatus;
  site_id: SiteId;
  bbox: Bbox;
  rows: Rows;
  cols: Cols;
  cell_size_m: CellSizeM;
  baselines_m?: BaselinesM;
  overlay_file?: OverlayFile;
  external_layers_status?: ExternalLayersStatus;
  cells: Cells;
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
