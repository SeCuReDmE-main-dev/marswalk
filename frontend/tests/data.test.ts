import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createDataSource } from "../src/data/source.ts";
import type { DataConfig } from "../src/data/types.ts";
const root = new URL("../../public_packs/jezero/v1/", import.meta.url);
const config: DataConfig = {
  mode: "static",
  siteId: "jezero",
  packUrl: "https://test.invalid/pack",
  apiBaseUrl: "https://api.invalid",
};
const map: Record<string, string> = {
  manifest: "manifest.json",
  waypoints: "waypoints.geojson",
  route: "route.geojson",
  hazards: "hazard_grid.json",
  constraints: "eva_constraints.json",
};
function fetchMock(
  options: {
    tamper?: boolean;
    api?: boolean;
    malformed?: boolean;
    wrongSite?: boolean;
    signal?: AbortSignal;
  } = {},
) {
  const requested: string[] = [];
  const fetcher = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    requested.push(url);
    if (options.signal) assert.equal(init?.signal, options.signal);
    const name = url.split("/").at(-1)!;
    let buffer = await readFile(new URL(options.api ? map[name] : name, root));
    if (options.malformed && name === "hazards") {
      const d = JSON.parse(buffer.toString());
      d.cells[0].confidence.t = 99;
      buffer = Buffer.from(JSON.stringify(d));
    }
    if (options.tamper && name === "hazard_grid.json")
      buffer = Buffer.from(buffer.toString() + " ");
    if (options.wrongSite && name.startsWith("manifest")) {
      const d = JSON.parse(buffer.toString());
      d.site_id = "wrong";
      buffer = Buffer.from(JSON.stringify(d));
    }
    return new Response(buffer, {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return { fetcher, requested };
}
test("static adapter loads the actual pack and verifies each consumed file hash", async () => {
  const { fetcher } = fetchMock();
  const data = await createDataSource(config, fetcher).load();
  assert.equal(data.integrity, "sha256-verified");
  assert.equal(data.hazards.cells.length, 384);
  assert.equal(data.waypoints.features.length, 708);
  assert.equal(data.mode, "static");
});
test("tampered static payload is rejected, even when still valid JSON", async () => {
  const { fetcher } = fetchMock({ tamper: true });
  await assert.rejects(
    () => createDataSource(config, fetcher).load(),
    /Integrity check failed/,
  );
});
test("API mode uses exactly the shared endpoint paths and preserves values", async () => {
  const controller = new AbortController();
  const { fetcher, requested } = fetchMock({
    api: true,
    signal: controller.signal,
  });
  const data = await createDataSource({ ...config, mode: "api" }, fetcher).load(
    controller.signal,
  );
  assert.equal(data.integrity, "schema-validated");
  assert.deepEqual(
    requested.sort(),
    Object.keys(map)
      .map((k) => `https://api.invalid/v1/sites/jezero/${k}`)
      .sort(),
  );
  assert.equal(
    data.hazards.cells[0].slope_deg_by_baseline["1"].note,
    "below 2x DTM resolution: pixel-scale noise, excluded from the funnel",
  );
});
test("malformed API confidence and wrong site are rejected at the boundary", async () => {
  await assert.rejects(
    () =>
      createDataSource(
        { ...config, mode: "api" },
        fetchMock({ api: true, malformed: true }).fetcher,
      ).load(),
    /Invalid hazards/,
  );
  await assert.rejects(
    () =>
      createDataSource(config, fetchMock({ wrongSite: true }).fetcher).load(),
    /another site/,
  );
});
test("HTTP errors produce actionable load errors instead of fake data", async () => {
  await assert.rejects(
    () =>
      createDataSource(
        config,
        (async () =>
          new Response("unavailable", { status: 503 })) as typeof fetch,
      ).load(),
    /HTTP 503/,
  );
});
