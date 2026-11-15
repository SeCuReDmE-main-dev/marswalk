import { cellAt, distanceMeters, type LonLat } from "./domain";
import type { HazardGrid } from "./data/types";

// Display geometry only. Never evaluate a route or interpolate a safety verdict.
export function createRoutePreview(points: LonLat[], grid: HazardGrid) {
  if (
    points.length < 2 ||
    points.some((p) => p.some((v) => !Number.isFinite(v)))
  )
    return undefined;
  const distances = [0];
  for (let i = 1; i < points.length; i++)
    distances.push(distances[i - 1] + distanceMeters(points[i - 1], points[i]));
  const total = distances.at(-1)!;
  if (!(total > 0)) return undefined;
  function at(distance: number) {
    const d = Math.min(
      total,
      Math.max(0, Number.isFinite(distance) ? distance : 0),
    );
    let end = 1;
    while (end < distances.length - 1 && distances[end] <= d) end++;
    const start = end - 1;
    const span = distances[end] - distances[start];
    const t = span > 0 ? (d - distances[start]) / span : 0;
    const point: LonLat = [
      points[start][0] + (points[end][0] - points[start][0]) * t,
      points[start][1] + (points[end][1] - points[start][1]) * t,
    ];
    const cell = cellAt(grid, point);
    const elevation = cell?.elev_m;
    return {
      distance: d,
      point,
      cell,
      elevation:
        elevation &&
        elevation.tag !== "UNAVAILABLE" &&
        Number.isFinite(elevation.value)
          ? elevation
          : undefined,
    };
  }
  // At most 241 chart samples; repeated values are cell elevations, not new measurements.
  const count = Math.min(240, Math.max(2, Math.ceil(total / 15)));
  const samples = Array.from({ length: count + 1 }, (_, i) =>
    at((i / count) * total),
  );
  function nearestDistance(point: LonLat) {
    let best = Infinity,
      result = 0;
    const cos = Math.cos((point[1] * Math.PI) / 180);
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1],
        b = points[i];
      const dx = (b[0] - a[0]) * cos,
        dy = b[1] - a[1];
      const denom = dx * dx + dy * dy;
      const t = denom
        ? Math.max(
            0,
            Math.min(
              1,
              ((point[0] - a[0]) * cos * dx + (point[1] - a[1]) * dy) / denom,
            ),
          )
        : 0;
      const projected: LonLat = [
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
      ];
      const gap = distanceMeters(point, projected);
      if (gap < best) {
        best = gap;
        result = distances[i - 1] + t * (distances[i] - distances[i - 1]);
      }
    }
    return result;
  }
  return { total, samples, at, nearestDistance };
}

export type PreviewPosition = NonNullable<
  ReturnType<typeof createRoutePreview>
>["samples"][number];
