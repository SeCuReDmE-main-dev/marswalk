import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { availableAngle, compareSlopes } from "../src/terrainComparison.ts";
import { cellAt, type LonLat } from "../src/domain.ts";
import type { HazardGrid, EvaRoute } from "../src/data/types";
const pack = (name: string) =>
  JSON.parse(
    readFileSync(
      new URL(`../../public_packs/jezero/v1/${name}`, import.meta.url),
      "utf8",
    ),
  );
const grid: HazardGrid = pack("hazard_grid.json");
const route: EvaRoute = pack("route.geojson");

test("scale comparison preserves supplied quantities and verdicts for every grid cell", () => {
  const original = JSON.stringify(grid);
  for (const cell of grid.cells)
    for (const baseline of ["64", "16", "4"]) {
      const result = compareSlopes(cell, baseline);
      assert.equal(result.coarse, cell.slope_deg_by_baseline["64"]);
      assert.equal(result.selected, cell.slope_deg_by_baseline[baseline]);
      assert.equal(
        result.difference,
        result.selected!.value - result.coarse!.value,
      );
      if (baseline === "64")
        assert.match(result.explanation, /Select 16 m or 4 m/);
      else if (result.difference! >= 0.05)
        assert.match(result.explanation, /steeper/);
      else if (result.difference! <= -0.05)
        assert.match(result.explanation, /gentler/);
    }
  assert.equal(JSON.stringify(grid), original);
});
test("missing or invalid angles stay unavailable, including outside-grid rover references", () => {
  const cell = structuredClone(grid.cells[0]);
  delete cell.slope_deg_by_baseline["4"];
  assert.equal(compareSlopes(cell, "4").difference, undefined);
  assert.match(compareSlopes(cell, "4").explanation, /unavailable/);
  const value = grid.cells[0].slope_deg_by_baseline["64"];
  for (const n of [NaN, Infinity, -1, 91])
    assert.equal(availableAngle({ ...value, value: n }), undefined);
  assert.equal(availableAngle({ ...value, tag: "UNAVAILABLE" }), undefined);
  assert.equal(availableAngle({ ...value, unit: "m" }), undefined);
  const outside = route.features.find(
    (f) =>
      f.properties.segment_type === "BENCHMARK" && f.properties.sol === 1578,
  )!;
  assert.equal(
    cellAt(grid, outside.geometry.coordinates.map(Number) as LonLat),
    undefined,
  );
  assert.ok(availableAngle(outside.properties.rover_tilt_deg));
});
