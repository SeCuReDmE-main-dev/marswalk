import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  cellAt,
  cellBounds,
  distanceMeters,
  exportSummary,
  maxWalkback,
  numericBbox,
  routeParts,
  safeUrl,
} from "../src/domain.ts";
import type { MarswalkData } from "../src/data/types.ts";
const read = (name: string) =>
  JSON.parse(
    readFileSync(
      new URL(`../../public_packs/jezero/v1/${name}`, import.meta.url),
      "utf8",
    ),
  );
const data: MarswalkData = {
  manifest: read("manifest.json"),
  hazards: read("hazard_grid.json"),
  route: read("route.geojson"),
  constraints: read("eva_constraints.json"),
  waypoints: read("waypoints.geojson"),
  mode: "static",
  integrity: "sha256-verified",
};
test("cell lookup respects coverage and does not extrapolate a nearest-cell verdict", () => {
  const c = data.hazards.cells[0];
  assert.equal(cellAt(data.hazards, [c.lon, c.lat])?.cell_id, c.cell_id);
  const b = numericBbox(data.hazards.bbox);
  assert.equal(cellAt(data.hazards, [b[0] - 0.001, b[1]]), undefined);
  assert.equal(cellAt(data.hazards, [0, 0]), undefined);
  assert.equal(cellBounds(data.hazards, c).length, 4);
});
test("distance uses the Mars sphere, not Earth", () => {
  assert.ok(Math.abs(distanceMeters([0, 0], [1, 0]) - 59274.697) < 1);
  assert.equal(distanceMeters([77, 18], [77, 18]), 0);
});
test("candidate/stops exclude rover traverses and benchmark records", () => {
  const p = routeParts(data);
  assert.equal(p.candidate?.properties.tag, "DERIVED");
  assert.equal(
    p.candidate?.properties.segment_type,
    "DERIVED_OBSTACLE_AWARE_EVA",
  );
  assert.equal(p.stops.length, 3);
  assert.equal(p.traverse.length, 1);
  assert.ok(
    data.route.features.some((f) => f.properties.segment_type === "BENCHMARK"),
  );
  assert.ok(maxWalkback(p.candidate)! > 0);
});
test("summary preserves quantity provenance and labels the prototype limitations", () => {
  const x = exportSummary(data);
  assert.equal(x.route?.properties.distance_m?.tag, "DERIVED");
  assert.equal(x.science_stops[0].properties.rover_tilt_deg?.tag, "MEASURED");
  assert.equal(x.pack_version, data.manifest.pack_version);
  assert.match(x.limitation, /not operational/);
});
test("external links reject script URLs", () => {
  assert.equal(safeUrl("javascript:alert(1)"), undefined);
  assert.equal(safeUrl("https://nasa.gov/"), "https://nasa.gov/");
});
test("benchmarks remain separate from science stops and do not extrapolate terrain outside coverage", () => {
  const parts = routeParts(data);
  assert.equal(parts.benchmarks.length, 2);
  assert.ok(parts.benchmarks.every((b) => b.properties.tag === "MEASURED"));
  const scarp = parts.benchmarks.find((b) => b.properties.sol === 700)!;
  const rim = parts.benchmarks.find((b) => b.properties.sol === 1578)!;
  assert.ok(
    cellAt(
      data.hazards,
      scarp.geometry.coordinates.map(Number) as [number, number],
    ),
  );
  assert.equal(
    cellAt(
      data.hazards,
      rim.geometry.coordinates.map(Number) as [number, number],
    ),
    undefined,
  );
  const summary = exportSummary(data);
  assert.equal(summary.science_stops.length, 3);
  assert.equal(summary.validation_benchmarks.length, 2);
  assert.equal(summary.obstacle_aware_route?.properties.tag, "DERIVED");
  assert.equal(summary.simulated_route?.properties.tag, "SIMULATED");
});
test("legacy packs still use their simulated candidate when no computed route exists", () => {
  const legacy = {
    ...data,
    route: {
      ...data.route,
      features: data.route.features.filter(
        (f) => f.properties.segment_type !== "DERIVED_OBSTACLE_AWARE_EVA",
      ),
    },
  };
  assert.equal(routeParts(legacy).candidate?.properties.tag, "SIMULATED");
});
