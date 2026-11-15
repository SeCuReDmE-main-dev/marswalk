import type {
  HazardGrid,
  MarswalkData,
  EvaRouteFeature,
  HazardCell,
} from "./data/types";
export const MARS_RADIUS_M = 3396190;
export type LonLat = [number, number];
export type Bbox = [number, number, number, number];
export const numericBbox = (bbox: unknown[]) => bbox.map(Number) as Bbox;
export function distanceMeters(a: LonLat, b: LonLat) {
  const rad = Math.PI / 180,
    dlat = (b[1] - a[1]) * rad,
    dlon = (b[0] - a[0]) * rad;
  const h =
    Math.sin(dlat / 2) ** 2 +
    Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dlon / 2) ** 2;
  return 2 * MARS_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}
export function contains(bbox: Bbox, [lon, lat]: LonLat) {
  return lon >= bbox[0] && lon <= bbox[2] && lat >= bbox[1] && lat <= bbox[3];
}
export function cellBounds(grid: HazardGrid, cell: HazardCell): Bbox {
  const [w, s, e, n] = numericBbox(grid.bbox),
    dx = (e - w) / grid.cols,
    dy = (n - s) / grid.rows;
  return [
    w + cell.col * dx,
    n - (cell.row + 1) * dy,
    w + (cell.col + 1) * dx,
    n - cell.row * dy,
  ];
}
export function cellAt(grid: HazardGrid, point: LonLat) {
  if (!contains(numericBbox(grid.bbox), point)) return undefined;
  return grid.cells.find((c) => contains(cellBounds(grid, c), point));
}
export function routeParts(data: MarswalkData) {
  return {
    candidate: data.route.features.find(
      (f) => f.properties.segment_type === "SIMULATED_ASTRONAUT_EVA",
    ),
    traverse: data.route.features.filter(
      (f) => f.properties.segment_type === "MEASURED_ROVER_TRAVERSE",
    ),
    stops: data.route.features.filter(
      (f) => f.properties.segment_type === "SCIENCE_STOP",
    ),
  };
}
export const linePoints = (feature: EvaRouteFeature): LonLat[] =>
  feature.geometry.type === "LineString"
    ? feature.geometry.coordinates.map((p) => [Number(p[0]), Number(p[1])])
    : [];
export function maxWalkback(feature?: EvaRouteFeature) {
  const points = feature ? linePoints(feature) : [];
  return points.length
    ? Math.max(...points.map((p) => distanceMeters(points[0], p)))
    : null;
}
export const stopLabel = (title: string) =>
  title.replace(/^Science Stop \d+\s*[—–-]\s*/, "").replace(/\s*\(Sol.*$/, "");
export function safeUrl(value?: string | null) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:"
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}
export function exportSummary(data: MarswalkData) {
  const { candidate, stops } = routeParts(data);
  return {
    name: "Marswalk planning prototype",
    site: data.manifest.site_id,
    pack_version: data.manifest.pack_version,
    contract_version: data.manifest.contract_version,
    route: candidate,
    science_stops: stops,
    constraints: data.constraints,
    sources: data.manifest.sources,
    limitation:
      "Simulated astronaut route. Assessments are model outputs, not operational safety certification.",
  };
}
