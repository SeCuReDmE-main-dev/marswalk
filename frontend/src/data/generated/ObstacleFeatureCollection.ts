/* Generated from middleware Pydantic models via scripts/export-api-contracts.py. */

export type Type = "FeatureCollection";
export type ContractVersion = "1.0.0" | "1.1.0";
export type SiteId = string;
export type OkPct = number;
export type CautionPct = number;
export type Golombek1P5MAt15Pct = number;
export type Type1 = "Feature";
export type Type2 = "Polygon";
/**
 * @minItems 1
 */
export type Coordinates = [[unknown, unknown][], ...[unknown, unknown][][]];
export type ObstacleId = string;
export type ObstacleType = "scarp" | "large_rock_formation";
export type Tag = "MEASURED" | "DERIVED" | "SIMULATED" | "UNAVAILABLE";
export type SourceId = string;
export type FootprintAreaM2 = number;
export type InternalReliefM = number;
export type PhysicalClearanceM = number;
export type ResolutionNote = string;
export type Features = ObstaclePolygonFeature[];

/**
 * GeoJSON FeatureCollection of DTM-derived scarps & >= 4 m formations (`obstacles.geojson`).
 */
export interface ObstacleFeatureCollection {
  type?: Type;
  contract_version?: ContractVersion;
  site_id: SiteId;
  ono_rover_cfa_reference_pct: OnoRoverCfaReference;
  features?: Features;
}
/**
 * Ono et al. (2016) rover CFA reference metadata stored alongside `obstacles.geojson`.
 */
export interface OnoRoverCfaReference {
  ok_pct: OkPct;
  caution_pct: CautionPct;
  golombek_1p5m_at_15pct: Golombek1P5MAt15Pct;
}
/**
 * Single GeoJSON Feature in `obstacles.geojson`.
 */
export interface ObstaclePolygonFeature {
  type?: Type1;
  geometry: GeoJsonPolygonGeometry;
  properties: ObstaclePolygonProperties;
}
/**
 * GeoJSON Polygon geometry for mapped obstacle clusters (`obstacles.geojson`).
 */
export interface GeoJsonPolygonGeometry {
  type?: Type2;
  coordinates: Coordinates;
}
/**
 * Metadata and DERIVED provenance for an obstacle polygon (`M1`).
 */
export interface ObstaclePolygonProperties {
  obstacle_id: ObstacleId;
  obstacle_type: ObstacleType;
  tag: Tag;
  source_id: SourceId;
  footprint_area_m2: FootprintAreaM2;
  internal_relief_m: InternalReliefM;
  physical_clearance_m: PhysicalClearanceM;
  resolution_note: ResolutionNote;
}
