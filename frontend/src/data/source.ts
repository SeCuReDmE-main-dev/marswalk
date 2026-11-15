import Ajv2020 from "ajv/dist/2020";
import { validateEngine } from "./engine";
import manifestSchema from "../../../schemas/SiteManifest.schema.json";
import hazardSchema from "../../../schemas/HazardGrid.schema.json";
import routeSchema from "../../../schemas/EvaRoute.schema.json";
import waypointSchema from "../../../schemas/WaypointFeatureCollection.schema.json";
import constraintSchema from "../../../schemas/EvaConstraints.schema.json";
import type {
  DataConfig,
  MarswalkData,
  MarswalkDataSource,
  SiteManifest,
} from "./types";

const ajv = new Ajv2020({ strict: false, allErrors: true });
const validators = {
  manifest: ajv.compile(manifestSchema),
  hazards: ajv.compile(hazardSchema),
  route: ajv.compile(routeSchema),
  waypoints: ajv.compile(waypointSchema),
  constraints: ajv.compile(constraintSchema),
};
export function validatePart(name: keyof typeof validators, data: unknown) {
  if (!validators[name](data))
    throw new Error(
      `Invalid ${name} data: ${ajv.errorsText(validators[name].errors, { separator: "; " })}`,
    );
}
const files = {
  hazards: "hazard_grid.json",
  route: "route.geojson",
  waypoints: "waypoints.geojson",
  constraints: "eva_constraints.json",
} as const;
export async function sha256(bytes: ArrayBuffer) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map((n) => n.toString(16).padStart(2, "0"))
    .join("");
}
export function createDataSource(
  config: DataConfig,
  fetcher: typeof fetch = fetch,
): MarswalkDataSource {
  const base =
    config.mode === "api"
      ? `${config.apiBaseUrl.replace(/\/$/, "")}/v1/sites/${encodeURIComponent(config.siteId)}`
      : config.packUrl.replace(/\/$/, "");
  async function get(path: string, signal?: AbortSignal) {
    const response = await fetcher(`${base}/${path}`, {
      signal,
      headers: { Accept: "application/json" },
    });
    if (!response.ok)
      throw new Error(
        `Could not load ${path} (HTTP ${response.status}). Check the data URL and retry.`,
      );
    const bytes = await response.arrayBuffer();
    let data: unknown;
    try {
      data = JSON.parse(new TextDecoder().decode(bytes));
    } catch {
      throw new Error(
        `${path} did not return JSON. Check the static path or API configuration.`,
      );
    }
    return { bytes, data };
  }
  return {
    async load(signal) {
      const first = await get(
        config.mode === "api" ? "manifest" : "manifest.json",
        signal,
      );
      validatePart("manifest", first.data);
      const manifest = first.data as SiteManifest;
      if (manifest.site_id !== config.siteId)
        throw new Error(
          "The manifest belongs to another site. Check VITE_SITE_ID.",
        );
      if (
        manifest.crs?.sphere_radius_m !== 3396190 ||
        manifest.crs.lat_type !== "planetocentric"
      )
        throw new Error(
          "Unsupported coordinate reference. Marswalk requires the shared Mars sphere.",
        );
      const loaded: Record<string, unknown> = { manifest };
      await Promise.all(
        Object.entries({
          ...files,
          ...(manifest.files.some((f) => f.path === "obstacles.geojson")
            ? { obstacles: "obstacles.geojson" }
            : {}),
        }).map(async ([key, filename]) => {
          const result = await get(
            config.mode === "api" ? key : filename,
            signal,
          );
          if (config.mode === "static") {
            const digest = manifest.files.find(
              (file) => file.path === filename,
            );
            if (
              !digest ||
              digest.bytes !== result.bytes.byteLength ||
              (await sha256(result.bytes)) !== digest.sha256
            )
              throw new Error(
                `Integrity check failed for ${filename}. Ask the pack owner for a consistent pack.`,
              );
          }
          if (key === "obstacles")
            validateEngine("obstacles", result.data, manifest);
          else validatePart(key as keyof typeof validators, result.data);
          if (
            (result.data as { site_id?: string }).site_id &&
            (result.data as { site_id?: string }).site_id !== config.siteId
          )
            throw new Error(`${filename} belongs to another site.`);
          loaded[key] = result.data;
        }),
      );
      // Quantity provenance must resolve to the manifest, including nested fields.
      const sources = new Set(manifest.sources.map((source) => source.id));
      function check(value: unknown): void {
        if (!value || typeof value !== "object") return;
        const record = value as Record<string, unknown>;
        if (
          "value" in record &&
          "unit" in record &&
          !sources.has(String(record.source_id))
        )
          throw new Error(`Unknown quantity source: ${record.source_id}`);
        Object.values(record).forEach(check);
      }
      check(loaded);
      return {
        ...loaded,
        integrity:
          config.mode === "static" ? "sha256-verified" : "schema-validated",
        mode: config.mode,
      } as MarswalkData;
    },
  };
}
