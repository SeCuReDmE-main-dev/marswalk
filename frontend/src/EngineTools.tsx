import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  createEngineClient,
  type EngineHealth,
  type PlanRouteResult,
  type RouteEvaluationResult,
  type RoverCamerasResponse,
} from "./data/engine";
import { getConfig } from "./data/config";
import type { MarswalkData, Quantity } from "./data/types";
import {
  linePoints,
  routeParts,
  safeUrl,
  stopLabel,
  type LonLat,
} from "./domain";

export interface EngineStatus {
  connected: boolean;
  safe: boolean;
  message: string;
}
export interface RouteOverlay {
  coordinates: LonLat[];
  verdict: string;
}
type Result = PlanRouteResult | RouteEvaluationResult;
export function EngineTools({
  data,
  open,
  points,
  setPoints,
  picking,
  setPicking,
  onRoute,
  onStatus,
  q,
}: {
  data: MarswalkData;
  open: boolean;
  points: LonLat[];
  setPoints: (p: LonLat[]) => void;
  picking: boolean;
  setPicking: (v: boolean) => void;
  onRoute: (r?: RouteOverlay) => void;
  onStatus: (s: EngineStatus) => void;
  q: (v?: Quantity | null, digits?: number) => ReactNode;
}) {
  const client = useMemo(
    () => createEngineClient(getConfig(), data.manifest),
    [data],
  );
  const [health, setHealth] = useState<EngineHealth>();
  const [connected, setConnected] = useState(getConfig().mode === "api");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>();
  const [scenario, setScenario] = useState({
    spe_alert: false,
    dust_tau_880nm: 0.45,
    payload_kg: 0,
    rf_link_margin_db: 6,
  });
  const [stopIndex, setStopIndex] = useState("0");
  const active = useRef<AbortController | undefined>(undefined);
  const revision = useRef(0);
  const { stops, candidate } = routeParts(data);
  // Never keep an old assessment after its route or scenario has changed.
  useEffect(() => {
    revision.current++;
    active.current?.abort();
    setBusy(false);
    setResult(undefined);
    onRoute(undefined);
  }, [points, scenario, onRoute]);
  useEffect(() => {
    if (!connected) return;
    let disposed = false;
    const controller = new AbortController();
    async function refresh() {
      try {
        const h = await client.health(controller.signal);
        if (disposed) return;
        setHealth(h);
        onStatus({
          connected: true,
          safe: h.safe_mode,
          message: h.safe_mode
            ? "Operator stop active · live planning disabled"
            : "Live engine connected",
        });
        if (h.safe_mode) {
          active.current?.abort();
          revision.current++;
          setBusy(false);
          setResult(undefined);
          onRoute(undefined);
        }
      } catch {
        if (disposed) return;
        setHealth(undefined);
        active.current?.abort();
        revision.current++;
        setBusy(false);
        setResult(undefined);
        onRoute(undefined);
        onStatus({
          connected: false,
          safe: false,
          message: "Live engine unavailable · pack remains browsable",
        });
      }
    }
    void refresh();
    const timer = setInterval(refresh, 10000);
    return () => {
      disposed = true;
      clearInterval(timer);
      controller.abort();
    };
  }, [client, connected, onRoute, onStatus]);
  useEffect(() => () => active.current?.abort(), []);
  async function run(mode: "plan" | "evaluate") {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    const ticket = ++revision.current;
    setBusy(true);
    setError("");
    setResult(undefined);
    onRoute(undefined);
    try {
      const h = await client.health(controller.signal);
      if (ticket !== revision.current) return;
      setHealth(h);
      onStatus({
        connected: true,
        safe: h.safe_mode,
        message: h.safe_mode
          ? "Operator stop active · live planning disabled"
          : "Live engine connected",
      });
      if (h.safe_mode)
        throw new Error("SAFE_MODE: route planning disabled by operator");
      const r =
        mode === "plan"
          ? await client.plan(
              {
                waypoints: points as [LonLat, LonLat, ...LonLat[]],
                ...scenario,
              },
              controller.signal,
            )
          : await client.evaluate(
              { points: points as [LonLat, LonLat, ...LonLat[]], ...scenario },
              controller.signal,
            );
      const after = await client.health(controller.signal);
      if (ticket !== revision.current) return;
      setHealth(after);
      onStatus({
        connected: true,
        safe: after.safe_mode,
        message: after.safe_mode
          ? "Operator stop active · live planning disabled"
          : "Live engine connected",
      });
      if (after.safe_mode)
        throw new Error("SAFE_MODE: route planning disabled by operator");
      setResult(r);
      const coordinates =
        "coordinates" in r
          ? r.coordinates.map((p) => [Number(p[0]), Number(p[1])] as LonLat)
          : points;
      if (!("reachable" in r) || r.reachable)
        onRoute({ coordinates, verdict: r.verdict });
    } catch (e) {
      if (ticket === revision.current && !controller.signal.aborted)
        setError(e instanceof Error ? e.message : "Engine unavailable");
    } finally {
      if (ticket === revision.current) setBusy(false);
    }
  }
  const available = !!health && !health.safe_mode;
  return (
    <section
      className="engine-tools"
      hidden={!open}
      aria-label="Live route planner"
    >
      <p className="intro">
        Choose stops or pick points on the map. The engine checks obstacles,
        slopes, effort, return margin and radio coverage.
      </p>
      <button
        className="secondary-button full-width"
        onClick={() => {
          setConnected(true);
          setError("");
        }}
        disabled={connected && !!health}
      >
        {health
          ? health.safe_mode
            ? "Operator stop active"
            : "Engine connected"
          : "Connect to planner"}
      </button>
      {!health && (
        <p className="footnote">
          New plans need the engine server. You can browse the included route
          without connecting.
        </p>
      )}
      <label className="field-label">
        Science stop
        <select
          value={stopIndex}
          onChange={(e) => setStopIndex(e.target.value)}
        >
          {stops.map((s, i) => (
            <option key={s.properties.feature_id} value={i}>
              {i + 1}. {stopLabel(s.properties.title)}
            </option>
          ))}
        </select>
      </label>
      <div className="engine-actions">
        <button
          className="secondary-button"
          disabled={points.length >= 32}
          onClick={() => {
            const s = stops[Number(stopIndex)];
            if (s?.geometry.type === "Point")
              setPoints([
                ...points,
                s.geometry.coordinates.map(Number) as LonLat,
              ]);
          }}
        >
          Add stop
        </button>
        <button
          className={picking ? "primary-button" : "secondary-button"}
          aria-pressed={picking}
          onClick={() => setPicking(!picking)}
        >
          {picking ? "Finish picking" : "Pick on map"}
        </button>
      </div>
      <ol className="planner-points">
        {points.map((p, i) => (
          <li key={i}>
            <span>
              {i + 1}. {p[0].toFixed(5)}° E, {p[1].toFixed(5)}° N
            </span>
            <button
              className="text-button"
              aria-label={`Remove point ${i + 1}`}
              onClick={() => setPoints(points.filter((_, j) => i !== j))}
            >
              Remove
            </button>
          </li>
        ))}
      </ol>
      <div className="engine-actions">
        <button
          className="text-button"
          onClick={() => setPoints([])}
          disabled={!points.length}
        >
          Clear points
        </button>
        <button
          className="text-button"
          onClick={() =>
            setPoints(candidate ? linePoints(candidate).slice(0, 500) : [])
          }
        >
          Use displayed route
        </button>
      </div>
      <details>
        <summary>Planning assumptions</summary>
        <p className="footnote">
          These are planning assumptions, not live telemetry.
        </p>
        <label className="field-label">
          Dust optical depth (880 nm)
          <input
            type="number"
            min="0"
            max="10"
            step="0.05"
            value={scenario.dust_tau_880nm}
            onChange={(e) =>
              setScenario((s) => ({
                ...s,
                dust_tau_880nm: e.target.valueAsNumber,
              }))
            }
          />
        </label>
        <label className="field-label">
          Additional payload (kg)
          <input
            type="number"
            min="0"
            max="120"
            value={scenario.payload_kg}
            onChange={(e) =>
              setScenario((s) => ({ ...s, payload_kg: e.target.valueAsNumber }))
            }
          />
        </label>
        <label className="field-label">
          Radio link margin (dB)
          <input
            type="number"
            min="0"
            max="40"
            value={scenario.rf_link_margin_db}
            onChange={(e) =>
              setScenario((s) => ({
                ...s,
                rf_link_margin_db: e.target.valueAsNumber,
              }))
            }
          />
        </label>
        <label className="scenario-check">
          <input
            type="checkbox"
            checked={scenario.spe_alert}
            onChange={(e) =>
              setScenario((s) => ({ ...s, spe_alert: e.target.checked }))
            }
          />{" "}
          Solar particle event · forces NO_GO
        </label>
      </details>
      <div className="engine-actions">
        <button
          className="primary-button"
          disabled={
            !available || busy || points.length < 2 || points.length > 32
          }
          onClick={() => run("plan")}
        >
          Plan around obstacles
        </button>
        <button
          className="secondary-button"
          disabled={
            !available || busy || points.length < 2 || points.length > 500
          }
          onClick={() => run("evaluate")}
        >
          Assess drawn path
        </button>
      </div>
      {busy && <p role="status">Checking the route…</p>}
      {error && (
        <p className="engine-error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="live-result" aria-live="polite">
          <div className="cell-assessment">
            <b>Live route assessment</b>
            <span
              className={`badge ${result.verdict.toLowerCase().replace("_", "-")}`}
            >
              {result.verdict}
            </span>
          </div>
          {"reachable" in result && !result.reachable && (
            <p>No traversable route returned.</p>
          )}
          <ul className="engine-reasons">
            {result.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
          {Object.entries(result)
            .filter(([, v]) => v && typeof v === "object" && "value" in v)
            .map(([key, v]) => (
              <div className="readout" key={key}>
                <span>
                  {(
                    {
                      total_distance_m: "Route length",
                      walkback_distance_m: "Walkback distance",
                      pure_walking_time_s: "Walking time",
                      max_longitudinal_slope_deg: "Along-path slope",
                      max_cross_slope_deg: "Cross slope",
                      metabolic_rate_w: "Metabolic effort",
                      walkback_o2_margin_min: "Oxygen return margin",
                      rf_diffraction_loss_db: "Radio diffraction loss",
                      rf_bullington_nu: "Radio diffraction parameter",
                      rf_min_clearance_over_f1: "Fresnel clearance ratio",
                      max_slope_1m_deg: "1 m diagnostic slope",
                      max_slope_64m_deg: "64 m slope",
                      max_scale_divergence_deg: "Scale divergence",
                      estimated_duration_h: "Estimated duration",
                      estimated_radiation_msv: "Estimated radiation dose",
                      walkback_return_h: "Return walking time",
                    } as Record<string, string>
                  )[key] || key.replaceAll("_", " ")}
                </span>
                {q(v as Quantity, 2)}
              </div>
            ))}
          <div className="readout">
            <span>Radio assessment</span>
            <b>{result.rf_comms_verdict ?? "Unavailable"}</b>
          </div>
          <p>
            Walkback distance within limit:{" "}
            {result.walkback_within_limit ? "Yes" : "No"}
          </p>
          {"string_pull_audit" in result && (
            <details>
              <summary>Planner details</summary>
              <p>{result.optimality_guarantee}</p>
              <p>
                {result.cells_expanded} cells explored;{" "}
                {result.string_pull_audit.accepted_count} smoothing shortcuts
                accepted.
              </p>
            </details>
          )}
          <button
            className="secondary-button full-width"
            onClick={() => {
              const url = URL.createObjectURL(
                new Blob(
                  [
                    JSON.stringify(
                      { scenario, points, assessment: result },
                      null,
                      2,
                    ),
                  ],
                  { type: "application/json" },
                ),
              );
              const a = document.createElement("a");
              a.href = url;
              a.download = "marswalk-live-assessment.json";
              a.click();
              setTimeout(() => URL.revokeObjectURL(url), 1000);
            }}
          >
            Export live assessment
          </button>
        </div>
      )}
      <p className="footnote">
        Derived planning results do not represent an astronaut visit. GO is a
        model verdict, not operational safety certification.
      </p>
    </section>
  );
}

export function CameraPanel({
  data,
  sol,
}: {
  data: MarswalkData;
  sol: number;
}) {
  const client = useMemo(
    () => createEngineClient(getConfig(), data.manifest),
    [data],
  );
  const [page, setPage] = useState(1),
    [azimuth, setAzimuth] = useState("");
  const [frames, setFrames] = useState<RoverCamerasResponse>();
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const request = useRef<AbortController | undefined>(undefined);
  useEffect(() => {
    request.current?.abort();
    setFrames(undefined);
    setError("");
    setBusy(false);
    setPage(1);
  }, [sol, azimuth]);
  useEffect(() => () => request.current?.abort(), []);
  async function load(p: number) {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError("");
    setFrames(undefined);
    try {
      const r = await client.cameras(
        sol,
        p,
        azimuth === "" ? undefined : Number(azimuth),
        controller.signal,
      );
      if (!controller.signal.aborted) {
        setFrames(r);
        setPage(p);
      }
    } catch (e) {
      if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : "Camera service unavailable");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  return (
    <details className="camera-panel">
      <summary>Rover camera frames</summary>
      <p className="footnote">
        Browse cached NASA photos for Sol {sol}. This does not request new
        downloads from NASA.
      </p>
      <label className="field-label">
        Mast azimuth (optional, 0–360°)
        <input
          type="number"
          min="0"
          max="360"
          value={azimuth}
          onChange={(e) => setAzimuth(e.target.value)}
        />
      </label>
      <button
        className="secondary-button"
        disabled={
          busy ||
          (azimuth !== "" &&
            (!Number.isFinite(Number(azimuth)) ||
              Number(azimuth) < 0 ||
              Number(azimuth) > 360))
        }
        onClick={() => load(1)}
      >
        Load camera frames
      </button>
      {busy && <p role="status">Loading camera frames…</p>}
      {error && <p role="alert">{error}</p>}
      {frames && (
        <>
          <p>
            {frames.source_status === "offline_unavailable"
              ? "No cached camera data is available for this sol."
              : `${frames.total_matching} matching frames · ${frames.source_status}`}
          </p>
          <div className="camera-grid">
            {frames.items.map((frame) => {
              const url = safeUrl(frame.image_url);
              return (
                <figure key={frame.image_id}>
                  {url && (
                    <a href={url} target="_blank" rel="noreferrer">
                      <img
                        src={url}
                        alt={`${frame.instrument}, Sol ${frame.sol}, frame ${frame.image_id}`}
                        loading="lazy"
                      />
                    </a>
                  )}
                  <figcaption>
                    {frame.instrument} · MEASURED
                    <br />
                    {frame.mast_azimuth_deg != null &&
                      `Mast azimuth ${frame.mast_azimuth_deg.toFixed(1)}°`}
                  </figcaption>
                  <details>
                    <summary>Camera metadata</summary>
                    <p>
                      {frame.camera_model_type || "Camera model unavailable"}
                    </p>
                    <p>
                      Attitude: {frame.attitude_quaternion || "Unavailable"}
                    </p>
                  </details>
                </figure>
              );
            })}
          </div>
          <div className="engine-actions">
            <button
              className="secondary-button"
              disabled={busy || page <= 1}
              onClick={() => load(page - 1)}
            >
              Previous frames
            </button>
            <button
              className="secondary-button"
              disabled={
                busy || page * frames.page_size >= frames.total_matching
              }
              onClick={() => load(page + 1)}
            >
              Next frames
            </button>
          </div>
        </>
      )}
    </details>
  );
}
