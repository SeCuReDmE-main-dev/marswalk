import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  createTerrainGeometry,
  geographicTilePixel,
} from "../src/terrainGeometry.ts";
import { distanceMeters } from "../src/domain.ts";
const grid = JSON.parse(
  readFileSync(
    new URL("../../public_packs/jezero/v1/hazard_grid.json", import.meta.url),
    "utf8",
  ),
);
test("3D model preserves actual elevations and Mars-scale horizontal distances", () => {
  const model = createTerrainGeometry(grid);
  assert.equal(model.vertices.length, grid.cells.length);
  assert.equal(model.faces.length, (grid.rows - 1) * (grid.cols - 1) * 2);
  model.vertices.forEach((v, i) => {
    assert.ok(
      Math.abs(v.y / model.scale + model.min - grid.cells[i].elev_m.value) <
        1e-8,
    );
    assert.ok(Number.isFinite(v.x) && Number.isFinite(v.z));
  });
  const a = model.vertices.find((v) => v.cell.row === 20 && v.cell.col === 0)!;
  const b = model.vertices.find((v) => v.cell.row === 20 && v.cell.col === 39)!;
  const actual = distanceMeters(
    [a.cell.lon, a.cell.lat],
    [b.cell.lon, b.cell.lat],
  );
  assert.ok(
    Math.abs((b.x - a.x) / model.scale - actual) < 1,
    "local visual approximation stays within one metre across the window",
  );
  assert.equal(
    model.locate([0, 0]),
    undefined,
    "never project an outside route onto assessed terrain",
  );
});
test("geographic texture alignment uses the 2:1 matrix rather than Web Mercator", () => {
  assert.deepEqual(geographicTilePixel([-180, 90], 0), { x: 0, y: 0 });
  assert.deepEqual(geographicTilePixel([180, -90], 0), { x: 512, y: 256 });
  assert.deepEqual(geographicTilePixel([0, 0], 0), { x: 256, y: 128 });
  const top = geographicTilePixel([77.4, 18.48], 13),
    bottom = geographicTilePixel([77.4, 18.45], 13);
  assert.equal(top.x, bottom.x);
  assert.ok(top.y < bottom.y);
});
