import Ajv2020 from "ajv/dist/2020";
import schema from "./api-schemas/ValidationReport.json";
import type { ValidationReport } from "./generated/ValidationReport";
import type { DataConfig, SiteManifest, Waypoint } from "./types";
import { sha256 } from "./source";
const validate = new Ajv2020({ strict: false }).compile<ValidationReport>(
  schema,
);
export async function loadValidationReport(
  config: DataConfig,
  manifest: SiteManifest,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
) {
  const entry = manifest.files.find((f) => f.path === "validation_report.json");
  if (!entry) throw new Error("No validation report is included in this pack.");
  // There is no validation-report API endpoint. Read the static pack copy in both
  // modes, requiring the active manifest's hash so stale API/static pairs fail closed.
  const response = await fetcher(
    `${config.packUrl.replace(/\/$/, "")}/validation_report.json`,
    { signal },
  );
  if (!response.ok)
    throw new Error("The validation report could not be loaded.");
  const bytes = await response.arrayBuffer();
  if (
    bytes.byteLength !== entry.bytes ||
    (await sha256(bytes)) !== entry.sha256
  )
    throw new Error("The validation report does not match this pack.");
  const raw: unknown = JSON.parse(new TextDecoder().decode(bytes));
  if (!validate(raw))
    throw new Error("The validation report has an unsupported format.");
  const report = raw;
  const sources = new Set(manifest.sources.map((s) => s.id));
  if (
    report.site_id !== manifest.site_id ||
    report.pack_version !== manifest.pack_version ||
    report.contract_version !== manifest.contract_version ||
    typeof report.dtm_source_id !== "string" ||
    typeof report.rover_source_id !== "string" ||
    !sources.has(report.dtm_source_id) ||
    !sources.has(report.rover_source_id)
  )
    throw new Error(
      "The validation report belongs to a different pack or source.",
    );
  return {
    ...report,
    dtm_source_id: report.dtm_source_id,
    rover_source_id: report.rover_source_id,
  };
}
export function sampleForWaypoint(
  report: ValidationReport,
  waypoint: Waypoint,
) {
  const p = waypoint.properties;
  return report.samples.find(
    (s) =>
      s.waypoint_id === p.waypoint_id &&
      s.sol === p.sol &&
      Math.abs(s.lon - p.lon) < 1e-7 &&
      Math.abs(s.lat - p.lat) < 1e-7 &&
      Math.abs(s.measured_rover_tilt_deg - p.rover_tilt_deg.value) <= 0.00051,
  );
}
