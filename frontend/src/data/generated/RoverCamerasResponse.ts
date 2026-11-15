/* Generated from middleware Pydantic models via scripts/export-api-contracts.py. */

export type SiteId = string;
export type Sol = number;
export type SourceStatus = "cached" | "live" | "offline_unavailable";
export type CacheSha256 = string | null;
export type TotalMatching = number;
export type Page = number;
export type PageSize = number;
export type ImageId = string;
export type Sol1 = number;
export type Site = number | null;
export type Drive = number | null;
export type Instrument = string;
export type ImageUrl = string;
export type MastAzimuthDeg = number | null;
export type MastElevationDeg = number | null;
export type AttitudeQuaternion = string | null;
export type CameraModelType = string | null;
export type AzimuthDeltaDeg = number | null;
export type Items = RoverCameraItem[];

/**
 * Paginated response for `GET /v1/sites/{site_id}/waypoints/{sol}/cameras` (`M5`).
 */
export interface RoverCamerasResponse {
  site_id: SiteId;
  sol: Sol;
  source_status: SourceStatus;
  cache_sha256?: CacheSha256;
  total_matching: TotalMatching;
  page: Page;
  page_size: PageSize;
  items: Items;
}
/**
 * Single Mars 2020 raw camera frame returned by `GET .../waypoints/{sol}/cameras` (`M5`).
 */
export interface RoverCameraItem {
  image_id: ImageId;
  sol: Sol1;
  site?: Site;
  drive?: Drive;
  instrument: Instrument;
  image_url: ImageUrl;
  mast_azimuth_deg?: MastAzimuthDeg;
  mast_elevation_deg?: MastElevationDeg;
  attitude_quaternion?: AttitudeQuaternion;
  camera_model_type?: CameraModelType;
  azimuth_delta_deg?: AzimuthDeltaDeg;
}
