import EvidenceText from "./EvidenceText";
import { geologyLabel } from "./explainEvidence";
import ReadingHelp from "./ReadingHelp";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { MarswalkData, HazardCell, Quantity } from "./data/types";
import { createEngineClient, type CellLookupResult } from "./data/engine";
import { getConfig } from "./data/config";
import type { LonLat } from "./domain";
const explanations: Record<string, string> = {
  solar_shadow_fraction:
    "Estimated share in shadow: 0 means none, 1 means all.",
  hurst_exponent_h:
    "Describes how the pattern of terrain roughness changes with distance.",
  step_scale_slope_075m_deg:
    "A model estimate over a short walking-step distance, not a direct measurement of each step.",
  distance_to_contact_m:
    "Estimated distance to a boundary between rock units in the approximate geology model.",
  sky_view_factor:
    "How much sky is unobstructed by terrain: 0 means none, 1 means all.",
  local_gcr_dose_mgy_per_day:
    "Estimated radiation absorbed per day, based on a model and measurements from another Mars site.",
  meda_dust_tau_880nm:
    "How much dust blocks light. Higher values mean more dust, not a percentage.",
  metabolic_rate_w:
    "Estimated energy the body uses each second while walking; W means watts.",
  walkback_o2_margin_min:
    "Estimated oxygen time remaining after the modeled return and other assumed use.",
  rf_bullington_nu:
    "A technical score describing terrain obstruction along the assumed radio path.",
  rf_diffraction_loss_db:
    "How much terrain weakens the radio signal in the model; dB compares signal levels.",
  obstacle_mask_fraction:
    "Share of this cell marked as obstacles in the model: 0 means none, 1 means all.",
  partial_refuge_gcr_reduction_pct:
    "Estimated reduction of background space radiation from surrounding terrain. It is not solar-storm protection.",
  thermal_inertia_tiu:
    "How strongly the ground resists heating up or cooling down.",
  crism_olindex3:
    "A measurement from light reflected by the ground, used to look for the rock-forming mineral olivine.",
  crism_d2300:
    "A feature in reflected light used to study minerals, not a safety score.",
  crism_bd1900_2:
    "A feature in reflected light used to study water-related minerals, not a reading of available drinking water.",
};

export function TerrainExtras({
  data,
  cell,
  q,
}: {
  data: MarswalkData;
  cell: HazardCell;
  q: (v?: Quantity | null, digits?: number) => ReactNode;
}) {
  return (
    <details>
      <summary>Environment, effort & radio</summary>
      <ReadingHelp topics={["height", "effort", "oxygen", "radio", "dust"]} />
      <p className="footnote">
        Geology is an elevation/position approximation, not the boundaries on
        the published geology map. Rock abundance is a roughness proxy, not a
        rock count.
      </p>
      <p>{geologyLabel(cell.geologic_unit)}</p>
      <details>
        <summary>Original terrain classification</summary>
        <p>{cell.geologic_unit || "Unavailable"}</p>
      </details>
      <p>
        Terrain similar to the rover reference data:{" "}
        {cell.aoa_inside == null
          ? "Unavailable"
          : cell.aoa_inside
            ? "Similar to reference terrain"
            : "Different terrain · estimates are less supported"}
      </p>
      {(
        [
          ["solar_shadow_fraction", "Shadow fraction"],
          ["hurst_exponent_h", "Terrain texture"],
          ["step_scale_slope_075m_deg", "Step-scale slope"],
          ["distance_to_contact_m", "Distance to a rock-type boundary"],
          ["sky_view_factor", "Open sky fraction"],
          ["local_gcr_dose_mgy_per_day", "Local radiation estimate"],
          ["meda_dust_tau_880nm", "Dust level (optical depth)"],
          ["metabolic_rate_w", "Estimated body energy use"],
          ["walkback_o2_margin_min", "Estimated oxygen time left after return"],
          ["rf_bullington_nu", "Terrain obstruction score (nu)"],
          ["rf_diffraction_loss_db", "Radio signal loss from terrain"],
          ["obstacle_mask_fraction", "Obstacle coverage"],
          [
            "partial_refuge_gcr_reduction_pct",
            "Radiation reduction from terrain shelter",
          ],
          ["thermal_inertia_tiu", "Resistance to heating and cooling"],
          ["crism_olindex3", "Olivine index"],
          ["crism_d2300", "Reflected-light mineral indicator (2300)"],
          ["crism_bd1900_2", "Reflected-light water-related indicator (1900)"],
        ] as const
      ).map(([key, label]) => (
        <div className="readout" key={key}>
          <span>
            {label}
            <small className="reading-explanation">{explanations[key]}</small>
          </span>
          {q(cell[key], 3)}
        </div>
      ))}
      <div className="readout">
        <span>Radio assessment (separate from terrain)</span>
        <b>{cell.rf_comms_verdict || "Unavailable"}</b>
      </div>
      <p className="footnote">
        Direct UHF link to the rover parked at Science Stop 1 (Sol 413): 414.2
        MHz, suit antenna 1.8 m, rover mast 3.0 m. Terrain can block this link.
        This is a direct link to the rover, not a link through a satellite.
      </p>
      <p>
        Ground partly sheltered by surrounding terrain:{" "}
        {cell.partial_topographic_refuge == null
          ? "Unavailable"
          : cell.partial_topographic_refuge
            ? "Present"
            : "Absent"}
        . Terrain shelter never cancels a solar particle event.
      </p>
      <p>
        Possible clay-mineral warning:{" "}
        {cell.spectral_smectite_caution == null
          ? "Unavailable"
          : cell.spectral_smectite_caution
            ? "Yes"
            : "No"}
      </p>
      {cell.calibrated_opinion && (
        <details>
          <summary>Confidence adjusted using reference data</summary>
          <p>
            Verified agreement {cell.calibrated_opinion.t.toFixed(2)} ·
            scale/data uncertainty {cell.calibrated_opinion.i.toFixed(2)} ·
            hazard contradiction {cell.calibrated_opinion.f.toFixed(2)}.
            Separate values, not percentages that add to 100. Original
            confidence remains above.
          </p>
        </details>
      )}
      <details>
        <summary>Technical data availability</summary>
        {Object.entries(data.hazards.external_layers_status || {}).map(
          ([name, status]) => (
            <p key={name}>
              <b>{name}</b>:{" "}
              {Object.entries(status)
                .map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`)
                .join(" · ")}
            </p>
          ),
        )}
      </details>
    </details>
  );
}
export function CellEvidence({
  data,
  point,
  q,
}: {
  data: MarswalkData;
  point?: LonLat;
  q: (v?: Quantity | null, digits?: number) => ReactNode;
}) {
  const client = useMemo(
    () => createEngineClient(getConfig(), data.manifest),
    [data],
  );
  const [result, setResult] = useState<CellLookupResult>(),
    [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const request = useRef<AbortController | undefined>(undefined);
  const lon = point?.[0],
    lat = point?.[1];
  useEffect(() => {
    request.current?.abort();
    setResult(undefined);
    setError("");
    setBusy(false);
  }, [lon, lat]);
  useEffect(() => () => request.current?.abort(), []);
  async function load() {
    if (lon == null || lat == null) return;
    request.current?.abort();
    const c = new AbortController();
    request.current = c;
    setBusy(true);
    setError("");
    try {
      const r = await client.cell(lon, lat, c.signal);
      if (!c.signal.aborted) setResult(r);
    } catch (e) {
      if (!c.signal.aborted)
        setError(e instanceof Error ? e.message : "Lookup unavailable");
    } finally {
      if (!c.signal.aborted) setBusy(false);
    }
  }
  return (
    <details>
      <summary>Nearest rover stop · server lookup</summary>
      <button
        className="secondary-button"
        disabled={!point || busy}
        onClick={load}
      >
        Find nearest rover stop
      </button>
      {busy && <p role="status">Finding the nearest stop…</p>}
      {error && <p role="alert">{error}</p>}
      {result && (
        <>
          <p>
            <b>{result.cell.verdict}</b>
          </p>
          <EvidenceText text={result.cell.reason} />
          <p>
            Nearest rover observation: Sol{" "}
            {result.nearest_waypoint.properties.sol},{" "}
            {result.distance_to_waypoint_m.toFixed(0)} m from the query.
          </p>
          <div className="readout">
            <span>Nearest rover tilt</span>
            {q(result.nearest_waypoint.properties.rover_tilt_deg, 2)}
          </div>
          <p className="footnote">
            Nearest observation is context, not a measurement at the selected
            location. An edge cell returned outside coverage is context only.
          </p>
        </>
      )}
    </details>
  );
}
