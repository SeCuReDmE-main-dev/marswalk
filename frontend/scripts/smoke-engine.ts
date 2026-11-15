/** Run against the real server: node --import tsx scripts/smoke-engine.ts */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createEngineClient } from "../src/data/engine.ts";
import { createDataSource } from "../src/data/source.ts";
import type { DataConfig } from "../src/data/types.ts";

const config: DataConfig = {
  mode: "api",
  siteId: "jezero",
  packUrl: "",
  apiBaseUrl: process.env.MARSWALK_API_URL || "http://127.0.0.1:8000",
};
const data = await createDataSource(config).load();
console.log(
  `API adapter: ${data.hazards.cells.length} cells, ${data.obstacles?.features.length} obstacles; all response schemas and source references valid`,
);
const client = createEngineClient(config, data.manifest);
const health = await client.health();
assert.equal(health.safe_mode, process.env.EXPECT_SAFE_MODE === "1");
console.log(`Health and pack identity verified; safe_mode=${health.safe_mode}`);
const stops = data.route.features
  .filter((f) => f.properties.segment_type === "SCIENCE_STOP")
  .map((f) => f.geometry.coordinates as [number, number]);
const points: [[number, number], [number, number]] = [stops[0], stops[2]];
const route = await client.plan({ waypoints: points });
assert.ok(["GO", "CAUTION", "NO_GO"].includes(route.verdict));
if (health.safe_mode) {
  assert.equal(route.verdict, "NO_GO");
  assert.ok(route.reasons.some((r) => r.startsWith("SAFE_MODE:")));
} else {
  assert.equal(route.reachable, true);
  assert.ok(route.coordinates.length >= 2);
}
console.log(
  `Plan: ${route.verdict}, reachable=${route.reachable}, ${route.coordinates.length} vertices, ${route.total_distance_m.value.toFixed(1)} m`,
);
const evaluation = await client.evaluate({ points });
assert.ok(evaluation.reasons.length);
console.log(
  `Evaluate: ${evaluation.verdict}; ${evaluation.reasons.length} reasons`,
);
const storm = await client.plan({ waypoints: points, spe_alert: true });
assert.equal(storm.verdict, "NO_GO");
console.log("Solar particle event: NO_GO");
const outside = await client.cell(0, 0);
assert.equal(outside.cell.verdict, "NO_GO");
assert.match(outside.cell.reason, /^FAIL_SAFE:/);
console.log("Outside coverage: NO_GO / FAIL_SAFE, no invented safe terrain");
const cameras = await client.cameras(413, 1);
assert.ok(
  ["cached", "live", "offline_unavailable"].includes(cameras.source_status),
);
console.log(
  `Camera endpoint: ${cameras.source_status}, ${cameras.items.length} returned frames`,
);
// Compare served values with the checked-in pack, rather than only checking HTTP 200.
const grid = JSON.parse(
  await readFile(
    new URL("../../public_packs/jezero/v1/hazard_grid.json", import.meta.url),
    "utf8",
  ),
);
assert.equal(data.hazards.cells.length, grid.cells.length);
function checkPackFields(actual: unknown, expected: unknown, path: string) {
  if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual), path);
    assert.equal(actual.length, expected.length, path);
    expected.forEach((v, i) => checkPackFields(actual[i], v, `${path}[${i}]`));
  } else if (expected && typeof expected === "object") {
    assert.ok(actual && typeof actual === "object", path);
    for (const [key, value] of Object.entries(expected))
      checkPackFields(
        (actual as Record<string, unknown>)[key],
        value,
        `${path}.${key}`,
      );
  } else assert.deepEqual(actual, expected, path);
}
for (const [index, cell] of grid.cells.entries()) {
  checkPackFields(data.hazards.cells[index], cell, `cell ${index}`);
}
console.log(
  "PASS: all checked-in hazard cell fields preserved by the real API (extra optional defaults allowed)",
);
