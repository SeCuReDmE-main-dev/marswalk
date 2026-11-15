import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { bundledImagePath, loadBundledImage } from "../src/data/images.ts";
import type { DataConfig, MarswalkData } from "../src/data/types.ts";
const root = new URL("../../public_packs/jezero/v1/", import.meta.url);
const manifest = JSON.parse(
  await readFile(new URL("manifest.json", root), "utf8"),
);
const route = JSON.parse(
  await readFile(new URL("route.geojson", root), "utf8"),
);
const data = { manifest, route } as MarswalkData;
const config: DataConfig = {
  mode: "static",
  siteId: "jezero",
  packUrl: "https://static.invalid/pack",
  apiBaseUrl: "https://api.invalid",
};
test("all three stops have verified pack JPEGs in static and API modes", async () => {
  for (const stop of route.features.filter(
    (f: { properties: { segment_type: string } }) =>
      f.properties.segment_type === "SCIENCE_STOP",
  )) {
    const path = bundledImagePath(data, stop.properties.panorama_url);
    assert.ok(path);
    for (const mode of ["static", "api"] as const) {
      const fetcher = (async (url: RequestInfo | URL) => {
        assert.equal(
          String(url),
          mode === "static"
            ? `${config.packUrl}/${path}`
            : `${config.apiBaseUrl}/v1/sites/jezero/${path}`,
        );
        return new Response(await readFile(new URL(path, root)));
      }) as typeof fetch;
      const blob = await loadBundledImage(
        { ...config, mode },
        manifest,
        path,
        undefined,
        fetcher,
      );
      assert.equal(blob.type, "image/jpeg");
      assert.ok(blob.size > 40000);
    }
  }
});
test("an unknown frame cannot borrow a bundled photo just because the sol matches", () => {
  assert.equal(
    bundledImagePath(data, "https://example.org/another-sol-753-frame.jpg"),
    undefined,
  );
});
test("tampered pack image is rejected before display", async () => {
  const path = "panoramas/sol_0753_ncam.jpg";
  const bytes = await readFile(new URL(path, root));
  bytes[100] ^= 1;
  const fetcher = (async () => new Response(bytes)) as typeof fetch;
  await assert.rejects(
    () => loadBundledImage(config, manifest, path, undefined, fetcher),
    /integrity check failed/,
  );
  await assert.rejects(
    () =>
      loadBundledImage(config, manifest, "../secret.jpg", undefined, fetcher),
    /not listed/,
  );
});
