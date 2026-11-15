/* Generated from the frozen shared JSON Schema. Run npm run types:generate. */

export type ContractVersion = "1.0.0";
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
export type Tag = "MEASURED" | "DERIVED" | "SIMULATED";
/**
 * Identifier matching an entry in SiteManifest.sources.
 */
export type SourceId = string;
/**
 * Optional provenance or proxy clarification note.
 */
export type Note = string | null;
export type RadiationEnvironmentNote = string;

/**
 * Citable NASA xEVA, Apollo, JPL Rover, and Curiosity RAD safety thresholds.
 */
export interface EvaConstraints {
  contract_version?: ContractVersion;
  suit_max_slope_deg: Quantity;
  apollo_practical_slope_deg: Quantity;
  apollo_max_relief_m: Quantity;
  walkback_max_km: Quantity;
  eva_duration_min_h: Quantity;
  eva_duration_max_h: Quantity;
  rover_max_slope_rock_deg: Quantity;
  rover_max_slope_sand_deg: Quantity;
  ripple_hazard_height_cm: Quantity;
  rock_cfa_ok_pct: Quantity;
  rock_cfa_caution_pct: Quantity;
  gcr_dose_msv_per_day: Quantity;
  radiation_environment_note: RadiationEnvironmentNote;
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
