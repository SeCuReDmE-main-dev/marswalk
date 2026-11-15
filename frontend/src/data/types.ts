export type { SiteManifest, Source } from "./generated/SiteManifest";
export type { HazardGrid, HazardCell, Quantity } from "./generated/HazardGrid";
export type { EvaRoute, EvaRouteFeature } from "./generated/EvaRoute";
export type {
  WaypointFeatureCollection,
  Waypoint,
} from "./generated/WaypointFeatureCollection";
export type { EvaConstraints } from "./generated/EvaConstraints";
import type { SiteManifest } from "./generated/SiteManifest";
import type { HazardGrid } from "./generated/HazardGrid";
import type { EvaRoute } from "./generated/EvaRoute";
import type { WaypointFeatureCollection } from "./generated/WaypointFeatureCollection";
import type { EvaConstraints } from "./generated/EvaConstraints";
import type { ObstacleFeatureCollection } from "./generated/ObstacleFeatureCollection";
export interface MarswalkData {
  manifest: SiteManifest;
  hazards: HazardGrid;
  route: EvaRoute;
  waypoints: WaypointFeatureCollection;
  constraints: EvaConstraints;
  obstacles?: ObstacleFeatureCollection;
  integrity: "sha256-verified" | "schema-validated";
  mode: "static" | "api";
}
export interface DataConfig {
  mode: "static" | "api";
  siteId: string;
  packUrl: string;
  apiBaseUrl: string;
}
export interface MarswalkDataSource {
  load(signal?: AbortSignal): Promise<MarswalkData>;
}
