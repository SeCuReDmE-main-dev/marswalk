/* Generated from the frozen shared JSON Schema. Run npm run types:generate. */

export type ContractVersion = "1.0.0" | "1.1.0";
export type PackVersion = string;
export type SiteId = string;
export type SiteName = string;
export type Name = string;
export type SphereRadiusM = number;
export type LonDomain = "east_positive_0_360";
export type LatType = "planetocentric";
/**
 * [min_lon, min_lat, max_lon, max_lat] in planetocentric East degrees.
 *
 * @minItems 4
 * @maxItems 4
 */
export type Bbox = [unknown, unknown, unknown, unknown];
/**
 * @minItems 1
 */
export type Basemaps = [BasemapLayer, ...BasemapLayer[]];
/**
 * Mars Trek layer identifier.
 */
export type Id = string;
/**
 * Human-readable layer title.
 */
export type Title = string;
/**
 * WMTS/XYZ tile URL template containing {z}, {row}, and {col}.
 */
export type TemplateUrl = string;
/**
 * Mars Trek 2:1 equirectangular geographic grid (EPSG:4326 style, 256x256 px).
 */
export type TileGrid = "geographic_2to1_256px";
export type MinZoom = number;
export type MaxZoom = number;
/**
 * Bounding box [min_lon, min_lat, max_lon, max_lat] in degrees East/North.
 *
 * @minItems 4
 * @maxItems 4
 */
export type Bbox1 = [unknown, unknown, unknown, unknown];
export type ResolutionMPerPx = number;
export type SourceId = string;
/**
 * @minItems 1
 */
export type Sources = [Source, ...Source[]];
/**
 * Unique source identifier (e.g. SRC-NASA-XEVA).
 */
export type Id1 = string;
/**
 * Document or dataset title.
 */
export type Title1 = string;
/**
 * Mission or institution name.
 */
export type Mission = string;
/**
 * Canonical HTTPS URL.
 */
export type Url = string;
/**
 * License or public domain designation.
 */
export type License = string;
/**
 * Full bibliographic citation.
 */
export type Citation = string;
/**
 * Source ID matching SiteManifest.sources.
 */
export type SourceId1 = string;
/**
 * Relative file path or canonical URL.
 */
export type PathOrUrl = string;
/**
 * Lowercase hex SHA-256.
 */
export type Sha256 = string;
/**
 * Exact number of bytes read from the raw input.
 */
export type BytesRead = number;
/**
 * Verified raw input files read during pack construction.
 */
export type Inputs = ManifestInputDigest[];
/**
 * @minItems 1
 */
export type Files = [PackFileDigest, ...PackFileDigest[]];
/**
 * Relative filename inside the site pack.
 */
export type Path = string;
/**
 * Lowercase hex SHA-256.
 */
export type Sha2561 = string;
/**
 * Exact file size in bytes.
 */
export type Bytes = number;
/**
 * ISO-8601 generation timestamp.
 */
export type GeneratedAt = string;

/**
 * Root manifest.json for a signed Martian site pack.
 */
export interface SiteManifest {
  contract_version?: ContractVersion;
  pack_version?: PackVersion;
  site_id: SiteId;
  site_name: SiteName;
  crs?: MarsCrs;
  bbox: Bbox;
  basemaps: Basemaps;
  sources: Sources;
  inputs?: Inputs;
  files: Files;
  generated_at: GeneratedAt;
}
/**
 * Coordinate Reference System definition for the Mars sphere R = 3,396,190 m.
 */
export interface MarsCrs {
  name?: Name;
  sphere_radius_m?: SphereRadiusM;
  lon_domain?: LonDomain;
  lat_type?: LatType;
}
/**
 * Tiled orbital basemap configuration compatible with NASA Mars Trek WMTS.
 */
export interface BasemapLayer {
  id: Id;
  title: Title;
  template_url: TemplateUrl;
  tile_grid?: TileGrid;
  min_zoom?: MinZoom;
  max_zoom?: MaxZoom;
  bbox: Bbox1;
  resolution_m_per_px?: ResolutionMPerPx;
  source_id: SourceId;
}
/**
 * Primary NASA, JPL, USGS, or synthetic scaffold reference source.
 */
export interface Source {
  id: Id1;
  title: Title1;
  mission: Mission;
  url: Url;
  license: License;
  citation: Citation;
}
/**
 * Cryptographic record of an upstream raw file actually read during pack generation.
 */
export interface ManifestInputDigest {
  source_id: SourceId1;
  path_or_url: PathOrUrl;
  sha256: Sha256;
  bytes_read: BytesRead;
}
/**
 * Integrity record for a file inside public_packs/<site>/v1/.
 */
export interface PackFileDigest {
  path: Path;
  sha256: Sha2561;
  bytes: Bytes;
}
