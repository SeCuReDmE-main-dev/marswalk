/* Generated from the frozen shared JSON Schema. Run npm run types:generate. */

export type Type = "FeatureCollection";
export type ContractVersion = "1.0.0" | "1.1.0";
export type SiteId = string;
/**
 * @minItems 2
 */
export type Features = [EvaRouteFeature, EvaRouteFeature, ...EvaRouteFeature[]];
export type Type1 = "Feature";
export type Geometry = GeoJsonLineGeometry | GeoJsonPointGeometry;
export type Type2 = "LineString";
/**
 * @minItems 2
 */
export type Coordinates = [
  [unknown, unknown],
  [unknown, unknown],
  ...[unknown, unknown][],
];
export type Type3 = "Point";
export type Coordinates1 = [unknown, unknown] | [unknown, unknown, unknown];
export type FeatureId = string;
export type SegmentType =
  | "MEASURED_ROVER_TRAVERSE"
  | "SIMULATED_ASTRONAUT_EVA"
  | "SCIENCE_STOP"
  | "BENCHMARK";
export type Title = string;
export type Tag = "MEASURED" | "DERIVED" | "SIMULATED" | "UNAVAILABLE";
export type SourceId = string;
export type Verdict = "GO" | "CAUTION" | "NO_GO";
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
export type Tag1 = "MEASURED" | "DERIVED" | "SIMULATED" | "UNAVAILABLE";
/**
 * Identifier matching an entry in SiteManifest.sources.
 */
export type SourceId1 = string;
/**
 * Optional provenance or proxy clarification note.
 */
export type Note = string | null;
export type Sol = number | null;
export type GeologicUnit = string | null;
export type PanoramaUrl = string | null;
export type Notes = string;

/**
 * Complete `route.geojson` FeatureCollection combining measured traverse & simulated EVA.
 */
export interface EvaRoute {
  type?: Type;
  contract_version?: ContractVersion;
  site_id: SiteId;
  features: Features;
}
/**
 * Single GeoJSON Feature in `route.geojson`.
 */
export interface EvaRouteFeature {
  type?: Type1;
  geometry: Geometry;
  properties: EvaRouteProperties;
}
/**
 * GeoJSON LineString geometry [[lon, lat], ...].
 */
export interface GeoJsonLineGeometry {
  type?: Type2;
  coordinates: Coordinates;
}
/**
 * GeoJSON Point geometry [lon, lat] or [lon, lat, elev_m].
 */
export interface GeoJsonPointGeometry {
  type?: Type3;
  coordinates: Coordinates1;
}
/**
 * Properties for a feature in `route.geojson` (traverse, EVA path, stop, or benchmark).
 */
export interface EvaRouteProperties {
  feature_id: FeatureId;
  segment_type: SegmentType;
  title: Title;
  tag: Tag;
  source_id: SourceId;
  verdict: Verdict;
  distance_m?: Quantity | null;
  max_slope_deg?: Quantity | null;
  estimated_duration_h?: Quantity | null;
  estimated_radiation_msv?: Quantity | null;
  sol?: Sol;
  rover_tilt_deg?: Quantity | null;
  geologic_unit?: GeologicUnit;
  panorama_url?: PanoramaUrl;
  notes: Notes;
}
/**
 * Physical scalar quantity with mandatory unit, provenance tag, and source ID.
 */
export interface Quantity {
  value: Value;
  unit: Unit;
  tag: Tag1;
  source_id: SourceId1;
  note?: Note;
}
