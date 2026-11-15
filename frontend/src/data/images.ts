import type { DataConfig, MarswalkData, SiteManifest } from "./types";
import { sha256 } from "./source";

export function bundledImagePath(data: MarswalkData, url?: string | null) {
  if (!url) return undefined;
  // Mirror only an exact canonical image match, never another frame from the same sol.
  const stop = data.route.features.find(
    (f) => f.properties.panorama_url === url && f.properties.sol != null,
  );
  if (!stop) return undefined;
  const path = `panoramas/sol_${String(stop.properties.sol).padStart(4, "0")}_ncam.jpg`;
  return data.manifest.files.some((f) => f.path === path) ? path : undefined;
}

export async function loadBundledImage(
  config: DataConfig,
  manifest: SiteManifest,
  path: string,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
) {
  const entry = manifest.files.find((f) => f.path === path);
  if (!entry || !/^panoramas\/sol_\d+_ncam\.jpg$/.test(path))
    throw new Error("Image is not listed in the pack manifest.");
  const base =
    config.mode === "api"
      ? `${config.apiBaseUrl.replace(/\/$/, "")}/v1/sites/${encodeURIComponent(config.siteId)}`
      : config.packUrl.replace(/\/$/, "");
  const response = await fetcher(`${base}/${path}`, { signal });
  if (!response.ok)
    throw new Error(`Bundled image unavailable (HTTP ${response.status}).`);
  const bytes = await response.arrayBuffer();
  if (
    bytes.byteLength !== entry.bytes ||
    (await sha256(bytes)) !== entry.sha256
  )
    throw new Error("Bundled image integrity check failed.");
  const header = new Uint8Array(bytes);
  if (header[0] !== 0xff || header[1] !== 0xd8 || header[2] !== 0xff)
    throw new Error("Bundled image is not a JPEG.");
  return new Blob([bytes], { type: "image/jpeg" });
}
