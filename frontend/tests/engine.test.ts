import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createEngineClient, validateEngine } from "../src/data/engine.ts";
const manifest = JSON.parse(
  readFileSync(
    new URL("../../public_packs/jezero/v1/manifest.json", import.meta.url),
    "utf8",
  ),
);
const config = {
  mode: "api" as const,
  siteId: "jezero",
  apiBaseUrl: "https://engine.invalid",
  packUrl: "",
};
test("route input validation rejects non-finite and out-of-planet coordinates before sending", () => {
  for (const p of [
    [NaN, 18],
    [Infinity, 18],
    [77, 91],
    [361, 18],
  ])
    assert.throws(() =>
      validateEngine("planRequest", { waypoints: [[77, 18], p] }),
    );
  assert.throws(() => validateEngine("planRequest", { waypoints: [[77, 18]] }));
  assert.throws(() =>
    validateEngine("planRequest", {
      waypoints: [
        [77, 18],
        [77.1, 18],
      ],
      payload_kg: 121,
    }),
  );
});
test("health rejects a different engine pack and malformed safe-mode flag", async () => {
  const fetcher = (async (url: RequestInfo | URL) =>
    new Response(
      JSON.stringify(
        String(url).endsWith("/health")
          ? { status: "ok", contract_version: "1.1.0", safe_mode: false }
          : { ...manifest, files: [] },
      ),
    )) as typeof fetch;
  await assert.rejects(
    () => createEngineClient(config, manifest, fetcher).health(),
    /pack differs/,
  );
  const malformed = (async () =>
    new Response(
      JSON.stringify({
        status: "ok",
        contract_version: "1.1.0",
        safe_mode: "false",
      }),
    )) as typeof fetch;
  await assert.rejects(
    () => createEngineClient(config, manifest, malformed).health(),
    /health response/,
  );
});
test("camera requests stay read-only and preserve pagination and azimuth filter", async () => {
  let requested = "";
  const fetcher = (async (url: RequestInfo | URL, init?: RequestInit) => {
    requested = String(url);
    assert.equal(init?.method, "GET");
    return new Response(
      JSON.stringify({
        site_id: "jezero",
        sol: 413,
        source_status: "offline_unavailable",
        cache_sha256: null,
        total_matching: 0,
        page: 2,
        page_size: 6,
        items: [],
      }),
    );
  }) as typeof fetch;
  await createEngineClient(config, manifest, fetcher).cameras(413, 2, 90);
  assert.match(requested, /allow_network=false/);
  assert.match(requested, /page=2/);
  assert.match(requested, /azimuth_deg=90/);
});
test("untrusted engine response cannot introduce a foreign site or obstacle source", () => {
  const obstacles = JSON.parse(
    readFileSync(
      new URL(
        "../../public_packs/jezero/v1/obstacles.geojson",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  validateEngine("obstacles", obstacles, manifest);
  obstacles.features[0].properties.source_id = "invented";
  assert.throws(
    () => validateEngine("obstacles", obstacles, manifest),
    /Unknown engine source/,
  );
  obstacles.site_id = "other";
  assert.throws(
    () => validateEngine("obstacles", obstacles, manifest),
    /another site/,
  );
});
test("engine HTTP failures reject instead of providing an assessment", async () => {
  const fetcher = (async () =>
    new Response("offline", { status: 503 })) as typeof fetch;
  await assert.rejects(
    () =>
      createEngineClient(config, manifest, fetcher).plan({
        waypoints: [
          [77, 18],
          [77.1, 18],
        ],
      }),
    /HTTP 503/,
  );
});
