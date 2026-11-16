import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import {
  loadValidationReport,
  sampleForWaypoint,
} from "../src/data/validation.ts";
import type { DataConfig } from "../src/data/types.ts";
const read = (name: string) =>
  readFileSync(
    new URL(`../../public_packs/jezero/v1/${name}`, import.meta.url),
  );
const manifest = JSON.parse(read("manifest.json").toString());
const waypoints = JSON.parse(read("waypoints.geojson").toString());
const raw = read("validation_report.json").toString();
const config: DataConfig = {
  mode: "static",
  packUrl: "https://pack.invalid",
  apiBaseUrl: "https://api.invalid",
  siteId: "jezero",
};
const fetcher = (body: string) =>
  (async () => new Response(body)) as typeof fetch;
test("validation uses signed bytes in static and API modes and matches only the exact rover record", async () => {
  for (const mode of ["static", "api"] as const) {
    const report = await loadValidationReport(
      { ...config, mode },
      manifest,
      undefined,
      fetcher(raw),
    );
    const wp = waypoints.features.find(
      (w: { properties: { sol: number } }) => w.properties.sol === 700,
    );
    const sample = sampleForWaypoint(report, wp)!;
    assert.equal(sample.dtm_slope_deg_by_baseline["64"], 12.649);
    assert.equal(sample.dtm_slope_deg_by_baseline["4"], 18.108);
    const shifted = structuredClone(wp);
    shifted.properties.lon += 0.0001;
    assert.equal(sampleForWaypoint(report, shifted), undefined);
    const outside = waypoints.features.find(
      (w: { properties: { sol: number } }) => w.properties.sol === 1578,
    );
    assert.equal(sampleForWaypoint(report, outside), undefined);
    assert.equal(report.waypoint_count_in_window, report.samples.length);
  }
});
test("tampered, wrong-source and malformed validation reports are rejected", async () => {
  await assert.rejects(
    loadValidationReport(config, manifest, undefined, fetcher(raw + " ")),
    /does not match/,
  );
  for (const patch of [
    { dtm_source_id: "unknown" },
    { site_id: "other" },
    { samples: "bad" },
  ]) {
    const body = JSON.stringify({ ...JSON.parse(raw), ...patch });
    const m = structuredClone(manifest);
    const entry = m.files.find(
      (f: { path: string }) => f.path === "validation_report.json",
    );
    entry.bytes = Buffer.byteLength(body);
    entry.sha256 = createHash("sha256").update(body).digest("hex");
    await assert.rejects(
      loadValidationReport(config, m, undefined, fetcher(body)),
    );
  }
});
