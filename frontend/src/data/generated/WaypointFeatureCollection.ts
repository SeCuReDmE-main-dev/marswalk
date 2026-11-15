/* Generated from the frozen shared JSON Schema. Run npm run types:generate. */

export type Type = "FeatureCollection";
export type ContractVersion = "1.0.0";
export type SiteId = string;
/**
 * @minItems 1
 */
export type Features = [Waypoint, ...Waypoint[]];
export type Type1 = "Feature";
export type Type2 = "Point";
export type Coordinates = [unknown, unknown] | [unknown, unknown, unknown];
export type WaypointId = string;
/**
 * Mars 2020 mission sol.
 */
export type Sol = number;
export type Site = number;
export type Drive = number;
export type Lon = number;
export type Lat = number;
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
export type PanoramaUrl = string | null;

/**
 * GeoJSON FeatureCollection of all Perseverance waypoints in the site pack.
 */
export interface WaypointFeatureCollection {
  type?: Type;
  contract_version?: ContractVersion;
  site_id: SiteId;
  features: Features;
}
/**
 * GeoJSON Feature representing one Perseverance rover waypoint.
 */
export interface Waypoint {
  type?: Type1;
  geometry: GeoJsonPointGeometry;
  properties: WaypointProperties;
}
/**
 * GeoJSON Point geometry [lon, lat] or [lon, lat, elev_m].
 */
export interface GeoJsonPointGeometry {
  type?: Type2;
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
  lon: Lon;
  lat: Lat;
  elev_geoid_m: Quantity;
  rover_tilt_deg: Quantity;
  rover_pitch_deg: Quantity;
  rover_roll_deg: Quantity;
  dist_total_m: Quantity;
  panorama_url?: PanoramaUrl;
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
