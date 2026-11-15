import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { MarswalkData, HazardCell, Quantity } from "./data/types";
import { createEngineClient, type CellLookupResult } from "./data/engine";
import { getConfig } from "./data/config";
import type { LonLat } from "./domain";

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
      <p className="footnote">
        Geology is an elevation/position approximation, not the published map
        polygons. Rock abundance is a roughness proxy, not a rock count.
      </p>
      <p>{cell.geologic_unit || "Geology unavailable"}</p>
      <p>
        Rover-data applicability:{" "}
        {cell.aoa_inside == null
          ? "Unavailable"
          : cell.aoa_inside
            ? "Inside reference domain"
            : "Outside reference domain · extrapolation"}
      </p>
      {(
        [
          ["solar_shadow_fraction", "Shadow fraction"],
          ["hurst_exponent_h", "Terrain texture"],
          ["step_scale_slope_075m_deg", "Step-scale slope"],
          ["distance_to_contact_m", "Distance to geological contact"],
          ["sky_view_factor", "Open sky fraction"],
          ["local_gcr_dose_mgy_per_day", "Local radiation estimate"],
          ["meda_dust_tau_880nm", "Dust optical depth"],
          ["metabolic_rate_w", "Metabolic effort"],
          ["walkback_o2_margin_min", "Oxygen return margin"],
          ["rf_bullington_nu", "Radio diffraction parameter"],
          ["rf_diffraction_loss_db", "Radio diffraction loss"],
          ["obstacle_mask_fraction", "Obstacle coverage"],
          [
            "partial_refuge_gcr_reduction_pct",
            "Partial refuge radiation reduction",
          ],
          ["thermal_inertia_tiu", "Thermal inertia"],
          ["crism_olindex3", "Olivine index"],
          ["crism_d2300", "Spectral absorption 2300"],
          ["crism_bd1900_2", "Spectral absorption 1900"],
        ] as const
      ).map(([key, label]) => (
        <div className="readout" key={key}>
          <span>{label}</span>
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
        This is not orbital-relay coverage.
      </p>
      <p>
        Partial topographic refuge:{" "}
        {cell.partial_topographic_refuge == null
          ? "Unavailable"
          : cell.partial_topographic_refuge
            ? "Present"
            : "Absent"}
        . Terrain shelter never cancels a solar particle event.
      </p>
      <p>
        Spectral smectite caution:{" "}
        {cell.spectral_smectite_caution == null
          ? "Unavailable"
          : cell.spectral_smectite_caution
            ? "Yes"
            : "No"}
      </p>
      {cell.calibrated_opinion && (
        <details>
          <summary>Calibrated confidence</summary>
          <p>
            Verified agreement {cell.calibrated_opinion.t.toFixed(2)} ·
            scale/data uncertainty {cell.calibrated_opinion.i.toFixed(2)} ·
            hazard contradiction {cell.calibrated_opinion.f.toFixed(2)}.
            Independent components, not a normalized probability. Original
            confidence remains above.
          </p>
        </details>
      )}
      <details>
        <summary>External data availability</summary>
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
      <summary>Nearby rover evidence · live lookup</summary>
      <button
        className="secondary-button"
        disabled={!point || busy}
        onClick={load}
      >
        Find nearby rover evidence
      </button>
      {busy && <p role="status">Looking up evidence…</p>}
      {error && <p role="alert">{error}</p>}
      {result && (
        <>
          <p>
            <b>{result.cell.verdict}</b> · {result.cell.reason}
          </p>
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
