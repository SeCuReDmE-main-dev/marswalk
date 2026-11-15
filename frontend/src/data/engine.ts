import Ajv2020 from "ajv/dist/2020";
import planRequest from "./api-schemas/PlanRouteRequest.json";
import planResult from "./api-schemas/PlanRouteResult.json";
import evaluateRequest from "./api-schemas/RouteEvaluationRequest.json";
import evaluateResult from "./api-schemas/RouteEvaluationResult.json";
import cameras from "./api-schemas/RoverCamerasResponse.json";
import lookup from "./api-schemas/CellLookupResult.json";
import obstacleSchema from "./api-schemas/ObstacleFeatureCollection.json";
import manifestSchema from "../../../schemas/SiteManifest.schema.json";
import type { DataConfig, SiteManifest } from "./types";
import type { PlanRouteRequest } from "./generated/PlanRouteRequest";
import type { PlanRouteResult } from "./generated/PlanRouteResult";
import type { RouteEvaluationRequest } from "./generated/RouteEvaluationRequest";
import type { RouteEvaluationResult } from "./generated/RouteEvaluationResult";
import type { RoverCamerasResponse } from "./generated/RoverCamerasResponse";
import type { CellLookupResult } from "./generated/CellLookupResult";
export type {
  PlanRouteRequest,
  PlanRouteResult,
  RouteEvaluationRequest,
  RouteEvaluationResult,
  RoverCamerasResponse,
  CellLookupResult,
};
export type { ObstacleFeatureCollection } from "./generated/ObstacleFeatureCollection";
const ajv = new Ajv2020({ strict: false, allErrors: true });
const manifestCheck = ajv.compile(manifestSchema);
const checks = Object.fromEntries(
  Object.entries({
    planRequest,
    planResult,
    evaluateRequest,
    evaluateResult,
    cameras,
    lookup,
    obstacles: obstacleSchema,
  }).map(([key, schema]) => [key, ajv.compile(schema)]),
);
export function validateEngine(
  name: keyof typeof checks,
  data: unknown,
  manifest?: SiteManifest,
) {
  if (!checks[name](data))
    throw new Error(`Invalid ${name}: ${ajv.errorsText(checks[name].errors)}`);
  if (name === "planRequest" || name === "evaluateRequest") {
    const request = data as Record<string, [number, number][]>;
    const points = request.waypoints || request.points;
    if (
      points.some(
        ([lon, lat]) =>
          !Number.isFinite(lon) ||
          !Number.isFinite(lat) ||
          lon < -180 ||
          lon > 360 ||
          lat < -90 ||
          lat > 90,
      )
    )
      throw new Error(
        "Route coordinates must be finite Mars longitude/latitude.",
      );
  }
  if (!manifest) return;
  const sources = new Set(manifest.sources.map((s) => s.id));
  function visit(value: unknown): void {
    if (!value || typeof value !== "object") return;
    const o = value as Record<string, unknown>;
    if ("site_id" in o && o.site_id !== manifest!.site_id)
      throw new Error("Engine response belongs to another site.");
    if ("source_id" in o && !sources.has(String(o.source_id)))
      throw new Error(`Unknown engine source: ${o.source_id}`);
    if (typeof o.value === "number" && !Number.isFinite(o.value))
      throw new Error("Non-finite engine quantity.");
    Object.values(o).forEach(visit);
  }
  visit(data);
}
export interface EngineHealth {
  status: "ok";
  contract_version: string;
  safe_mode: boolean;
}
export function createEngineClient(
  config: DataConfig,
  manifest: SiteManifest,
  fetcher: typeof fetch = fetch,
) {
  const origin = config.apiBaseUrl.replace(/\/$/, "");
  const base = `${origin}/v1/sites/${encodeURIComponent(config.siteId)}`;
  async function request(
    path: string,
    schema?: string,
    body?: unknown,
    signal?: AbortSignal,
  ) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
    const timeout = setTimeout(abort, 20000);
    try {
      const response = await fetcher(path, {
        method: body === undefined ? "GET" : "POST",
        headers:
          body === undefined
            ? { Accept: "application/json" }
            : {
                Accept: "application/json",
                "Content-Type": "application/json",
              },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok)
        throw new Error(
          `Engine request failed (HTTP ${response.status}). Check the service and inputs.`,
        );
      const data: unknown = await response.json();
      if (schema) validateEngine(schema, data, manifest);
      return data;
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", abort);
    }
  }
  return {
    async health(signal?: AbortSignal): Promise<EngineHealth> {
      const h = (await request(
        `${origin}/health`,
        undefined,
        undefined,
        signal,
      )) as EngineHealth;
      if (
        h.status !== "ok" ||
        typeof h.safe_mode !== "boolean" ||
        !["1.0.0", "1.1.0"].includes(h.contract_version)
      )
        throw new Error("Unsupported engine health response.");
      const remote = (await request(`${base}/manifest`)) as SiteManifest;
      if (
        !manifestCheck(remote) ||
        remote.site_id !== manifest.site_id ||
        remote.crs?.sphere_radius_m !== 3396190 ||
        remote.crs?.lat_type !== "planetocentric" ||
        manifest.files.some((f) => {
          const match = remote.files.find((r) => r.path === f.path);
          return !match || match.sha256 !== f.sha256 || match.bytes !== f.bytes;
        })
      )
        throw new Error(
          "Engine pack differs from the displayed pack. Reload with a matching pack before planning.",
        );
      return h;
    },
    async plan(body: PlanRouteRequest, signal?: AbortSignal) {
      validateEngine("planRequest", body);
      return (await request(
        `${base}/plan-route`,
        "planResult",
        body,
        signal,
      )) as PlanRouteResult;
    },
    async evaluate(body: RouteEvaluationRequest, signal?: AbortSignal) {
      validateEngine("evaluateRequest", body);
      return (await request(
        `${base}/evaluate-route`,
        "evaluateResult",
        body,
        signal,
      )) as RouteEvaluationResult;
    },
    async cell(lon: number, lat: number, signal?: AbortSignal) {
      return (await request(
        `${base}/cell?${new URLSearchParams({ lon: String(lon), lat: String(lat) })}`,
        "lookup",
        undefined,
        signal,
      )) as CellLookupResult;
    },
    async cameras(
      sol: number,
      page: number,
      azimuth?: number,
      signal?: AbortSignal,
    ) {
      const query = new URLSearchParams({
        page: String(page),
        page_size: "6",
        allow_network: "false",
      });
      if (azimuth !== undefined) query.set("azimuth_deg", String(azimuth));
      return (await request(
        `${base}/waypoints/${sol}/cameras?${query}`,
        "cameras",
        undefined,
        signal,
      )) as RoverCamerasResponse;
    },
  };
}
