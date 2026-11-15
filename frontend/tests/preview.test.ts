import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRoutePreview } from "../src/routePreview.ts";
import { distanceMeters, linePoints, type LonLat } from "../src/domain.ts";
const pack = (name: string) =>
  JSON.parse(
    readFileSync(
      new URL(`../../public_packs/jezero/v1/${name}`, import.meta.url),
      "utf8",
    ),
  );
const grid = pack("hazard_grid.json");
const route = pack("route.geojson").features.find(
  (f: { properties: { segment_type: string } }) =>
    f.properties.segment_type === "DERIVED_OBSTACLE_AWARE_EVA",
);

test("walk preview follows the entire supplied path using Mars distances and exact endpoints", () => {
  const points = linePoints(route);
  const preview = createRoutePreview(points, grid)!;
  const total = points
    .slice(1)
    .reduce((sum, p, i) => sum + distanceMeters(points[i], p), 0);
  assert.equal(preview.total, total);
  assert.deepEqual(preview.at(0).point, points[0]);
  assert.deepEqual(preview.at(total).point, points.at(-1));
  assert.deepEqual(preview.at(-10).point, points[0]);
  assert.equal(preview.at(total + 10).distance, total);
  assert.ok(preview.samples.length <= 241);
  preview.samples.forEach((s) => {
    if (s.elevation) {
      assert.ok(s.cell);
      assert.equal(
        s.elevation,
        s.cell.elev_m,
        "cell quantity and provenance preserved without interpolation",
      );
    }
  });
});
test("preview gaps never borrow an elevation or terrain verdict from the nearest cell", () => {
  const a = grid.cells[0];
  const preview = createRoutePreview(
    [
      [a.lon, a.lat],
      [0, 0],
    ],
    grid,
  )!;
  assert.ok(preview.at(0).cell);
  assert.equal(preview.at(preview.total).cell, undefined);
  assert.equal(preview.at(preview.total).elevation, undefined);
  const unavailable = structuredClone(grid);
  unavailable.cells.forEach((c: { elev_m: { tag: string } }) => {
    c.elev_m.tag = "UNAVAILABLE";
  });
  const missing = createRoutePreview(
    [
      [a.lon, a.lat],
      [a.lon + 0.001, a.lat],
    ],
    unavailable,
  )!;
  assert.equal(missing.at(0).elevation, undefined);
});
test("preview stop jumps project onto a segment and handle repeated and empty vertices", () => {
  const points: LonLat[] = [
    [77.39, 18.46],
    [77.39, 18.46],
    [77.4, 18.46],
  ];
  const preview = createRoutePreview(points, grid)!;
  const halfway = preview.nearestDistance([77.395, 18.46]);
  assert.ok(Math.abs(halfway / preview.total - 0.5) < 1e-6);
  assert.ok(preview.at(0).point.every(Number.isFinite));
  assert.equal(createRoutePreview([], grid), undefined);
  assert.equal(createRoutePreview([points[0], points[0]], grid), undefined);
  assert.equal(createRoutePreview([[NaN, 0], points[0]], grid), undefined);
});
