import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  HelpCircle,
  LocateFixed,
  MapPinned,
  PanelRightClose,
  PanelRightOpen,
  RotateCcw,
  ShieldAlert,
  X,
} from "lucide-react";
import MapView, { type LayerState } from "./MapView";
import { createDataSource } from "./data/source";
import { getConfig } from "./data/config";
import type {
  MarswalkData,
  HazardCell,
  Quantity,
  EvaRouteFeature,
  Waypoint,
} from "./data/types";
import {
  exportSummary,
  maxWalkback,
  routeParts,
  safeUrl,
  stopLabel,
} from "./domain";

const steps = [
  "Review the walk",
  "Inspect the terrain",
  "Check the evidence",
  "Review the assessment",
];
const defaultLayers: LayerState = {
  imagery: true,
  hazards: true,
  rover: false,
  stops: true,
  opacity: 0.22,
};
function Badge({ value }: { value: string }) {
  return (
    <span className={`badge ${value.toLowerCase().replace("_", "-")}`}>
      {value === "NO_GO" ? <ShieldAlert size={13} /> : null}
      {value}
    </span>
  );
}
function Dialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="dialog-content">
        <header>
          <h2>{title}</h2>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </header>
        {children}
      </div>
    </dialog>
  );
}
function Panorama({ url }: { url?: string | null }) {
  const [failed, setFailed] = useState(false);
  const link = safeUrl(url);
  useEffect(() => setFailed(false), [url]);
  return (
    <div className="panorama">
      {link && !failed ? (
        <img
          src={link}
          alt="Perseverance panorama from the selected rover stop"
          loading="lazy"
          onError={() => setFailed(true)}
        />
      ) : (
        <div className="image-fallback">
          <MapPinned size={24} />
          <span>
            {link ? "Panorama could not be loaded" : "No panorama available"}
          </span>
        </div>
      )}
      {link && (
        <a href={link} target="_blank" rel="noreferrer">
          Open original panorama <ExternalLink size={12} />
        </a>
      )}
    </div>
  );
}
function Workspace({
  data,
  onRetry,
}: {
  data: MarswalkData;
  onRetry: () => void;
}) {
  const { candidate, stops } = routeParts(data);
  const [step, setStep] = useState(0),
    [expanded, setExpanded] = useState(true),
    [collapsed, setCollapsed] = useState(false),
    [tips, setTips] = useState(false);
  const [selectedStop, setSelectedStop] = useState<EvaRouteFeature | undefined>(
      stops[0],
    ),
    [cell, setCell] = useState<HazardCell>(),
    [waypoint, setWaypoint] = useState<Waypoint>(),
    [outside, setOutside] = useState(false),
    [baseline, setBaseline] = useState("16");
  const [layers, setLayers] = useState<LayerState>(defaultLayers),
    [fit, setFit] = useState<"route" | "coverage">("route"),
    [fitTick, setFitTick] = useState(0),
    [dialog, setDialog] = useState<"sources" | "help" | null>(null),
    [sourceId, setSourceId] = useState<string>(),
    [solSearch, setSolSearch] = useState("");

  const q = (value: Quantity | null | undefined, digits = 1) =>
    value ? (
      <span className="quantity">
        <strong>
          {value.value.toLocaleString("en-US", {
            maximumFractionDigits: digits,
          })}
          <span className="unit"> {value.unit}</span>
        </strong>
        <button
          className="provenance"
          title={`View source: ${value.source_id}`}
          onClick={() => {
            setSourceId(value.source_id);
            setDialog("sources");
          }}
        >
          {value.tag} <ExternalLink size={9} />
        </button>
        {value.note && <span className="quantity-note">{value.note}</span>}
      </span>
    ) : (
      <span className="unavailable">Unavailable</span>
    );
  function navigate(index: number) {
    setStep(index);
    setExpanded(true);
    if (index === 1 && !cell && !outside)
      setCell(
        data.hazards.cells.find((c) => c.verdict === "CAUTION") ||
          data.hazards.cells[0],
      );
    if (index === 2 && !waypoint) {
      const sol = selectedStop?.properties.sol;
      setWaypoint(
        data.waypoints.features.find((w) => w.properties.sol === sol) ||
          data.waypoints.features[0],
      );
    }
    if (index === 1) {
      setFit("coverage");
      setFitTick((t) => t + 1);
    }
  }
  function chooseStop(stop: EvaRouteFeature) {
    setSelectedStop(stop);
    setWaypoint(undefined);
    setStep(0);
    setExpanded(true);
    setLayers((l) => ({ ...l, stops: true }));
  }
  function chooseCell(value?: HazardCell) {
    setCell(value);
    setWaypoint(undefined);
    setOutside(!value);
    setSelectedStop(undefined);
    setStep(1);
    setExpanded(true);
  }
  function chooseWaypoint(value: Waypoint) {
    setWaypoint(value);
    setSelectedStop(undefined);
    setStep(2);
    setExpanded(true);
    setLayers((l) => ({ ...l, rover: true }));
  }
  function fitMap(mode: "route" | "coverage") {
    setFit(mode);
    setFitTick((t) => t + 1);
  }
  function reset() {
    setStep(0);
    setExpanded(true);
    setCollapsed(false);
    setSelectedStop(stops[0]);
    setCell(undefined);
    setWaypoint(undefined);
    setOutside(false);
    setLayers(defaultLayers);
    setBaseline("16");
    fitMap("route");
  }
  function download() {
    const blob = new Blob([JSON.stringify(exportSummary(data), null, 2)], {
        type: "application/json",
      }),
      url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = `marswalk-${data.manifest.site_id}-planning-summary.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const walkback = maxWalkback(candidate),
    filteredWaypoints = data.waypoints.features.filter(
      (w) => !solSearch || String(w.properties.sol).includes(solSearch),
    );
  const title =
    data.manifest.site_id.charAt(0).toUpperCase() +
    data.manifest.site_id.slice(1);
  useEffect(() => {
    if (dialog === "sources" && sourceId)
      document
        .getElementById(`source-${sourceId}`)
        ?.scrollIntoView({ block: "center" });
  }, [dialog, sourceId]);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#guide">
        Skip to mission guide
      </a>
      <header className="app-header">
        <div className="brand">
          <img
            src={`${import.meta.env.BASE_URL}brand/marswalk-logo-inverse.svg`}
            alt="Marswalk"
          />
          <span className="header-divider" />
          <span className="site-title">{title}</span>
        </div>
        <span className="prototype">Planning prototype</span>
        <nav aria-label="Application">
          <button
            aria-label={collapsed ? "Show mission guide" : "Hide mission guide"}
            aria-expanded={!collapsed}
            aria-controls="guide"
            onClick={() => setCollapsed((value) => !value)}
          >
            {collapsed ? (
              <PanelRightOpen size={17} />
            ) : (
              <PanelRightClose size={17} />
            )}
            <span>Guide</span>
          </button>
          <button
            aria-label="Sources"
            onClick={() => {
              setSourceId(undefined);
              setDialog("sources");
            }}
          >
            <BookOpen size={16} />
            <span>Sources</span>
          </button>
          <button aria-label="Help" onClick={() => setDialog("help")}>
            <HelpCircle size={17} />
            <span>Help</span>
          </button>
        </nav>
      </header>
      <main className={`workspace ${collapsed ? "guide-collapsed" : ""}`}>
        <div className="map-column">
          <div className="mission-strip">
            <div className="mission-label">
              <span className="eyebrow">CANDIDATE WALK</span>
              <b>{title} candidate EVA</b>
            </div>
            {candidate ? (
              <>
                <Badge value={candidate.properties.verdict} />
                <div className="strip-stat">
                  <small>Route length</small>
                  {q(candidate.properties.distance_m, 0)}
                </div>
                <div className="strip-stat">
                  <small>Estimated duration</small>
                  {q(candidate.properties.estimated_duration_h)}
                </div>
              </>
            ) : (
              <span>No candidate route in this pack</span>
            )}
          </div>
          <div className="map-container">
            <MapView
              data={data}
              cell={cell}
              stop={selectedStop}
              waypoint={waypoint}
              layers={layers}
              onLayers={setLayers}
              onCell={chooseCell}
              onStop={chooseStop}
              onWaypoint={chooseWaypoint}
              fit={fit}
              fitTick={fitTick}
            />
            <div className="fit-actions">
              <button className="map-button" onClick={() => fitMap("route")}>
                <LocateFixed size={15} /> Fit route
              </button>
              <button className="map-button" onClick={() => fitMap("coverage")}>
                Assessed area
              </button>
            </div>
          </div>
          <footer className="map-footer">
            <span
              className={`status-dot ${data.hazards.grid_status === "PLACEHOLDER" ? "preview" : ""}`}
            />
            <span>
              {data.hazards.grid_status === "PLACEHOLDER"
                ? "Preview grid · SIMULATED"
                : `Terrain model · ${data.hazards.cells.length} cells`}
            </span>
            <span className="footer-spacer" />
            <span>Pack {data.manifest.pack_version}</span>
            <button onClick={onRetry} aria-label="Reload data pack">
              <RotateCcw size={12} />
            </button>
          </footer>
        </div>
        <aside
          className="guide"
          id="guide"
          aria-label="Marswalk step-by-step guide"
        >
          {collapsed ? (
            <button
              className="reopen-guide"
              aria-label="Expand mission guide"
              onClick={() => setCollapsed(false)}
            >
              <PanelRightOpen size={22} />
              <span>Mission guide</span>
            </button>
          ) : (
            <>
              <div className="guide-heading">
                <div>
                  <span className="eyebrow">MISSION GUIDE</span>
                  <h1>Explore this Marswalk</h1>
                </div>
                <button
                  className="icon-button"
                  aria-label="Collapse mission guide"
                  onClick={() => setCollapsed(true)}
                >
                  <PanelRightClose size={19} />
                </button>
              </div>
              <div className="guide-tools">
                <span>
                  {step + 1} of {steps.length} steps
                </span>
                <label className="tip-toggle">
                  <input
                    type="checkbox"
                    checked={tips}
                    onChange={(e) => setTips(e.target.checked)}
                  />
                  <span>Show tips</span>
                </label>
              </div>
              <div className="guide-scroll">
                {steps.map((name, i) => (
                  <section
                    className={`step ${step === i ? "active" : ""}`}
                    key={name}
                  >
                    <button
                      className="step-header"
                      aria-expanded={step === i && expanded}
                      aria-controls={`step-${i}`}
                      onClick={() => {
                        if (step === i) setExpanded(!expanded);
                        else navigate(i);
                      }}
                    >
                      <span className="step-number">{i + 1}</span>
                      <span>{name}</span>
                      {step === i && expanded ? (
                        <ChevronDown size={17} />
                      ) : (
                        <ChevronRight size={17} />
                      )}
                    </button>
                    {step === i && expanded && (
                      <div className="step-content" id={`step-${i}`}>
                        {i === 0 && (
                          <>
                            <p className="intro">
                              A proposed walk across the western delta, with
                              science stops along the way.
                            </p>
                            {tips && (
                              <div className="context-tip">
                                <HelpCircle size={15} />
                                <span>
                                  Select a stop to locate it on the map. The
                                  astronaut walk is simulated; rover
                                  observations are measured.
                                </span>
                              </div>
                            )}
                            <div className="section-label">
                              SCIENCE STOPS <span>{stops.length}</span>
                            </div>
                            <div className="stop-list">
                              {stops.map((stop, index) => (
                                <button
                                  key={stop.properties.feature_id}
                                  className={`stop-row ${selectedStop?.properties.feature_id === stop.properties.feature_id ? "selected" : ""}`}
                                  onClick={() => chooseStop(stop)}
                                >
                                  <span className="stop-number">
                                    {String(index + 1).padStart(2, "0")}
                                  </span>
                                  <span>
                                    <b>{stopLabel(stop.properties.title)}</b>
                                    <small>
                                      {stop.properties.sol != null
                                        ? `Rover context · Sol ${stop.properties.sol}`
                                        : "Science target"}
                                    </small>
                                  </span>
                                  <ChevronRight size={15} />
                                </button>
                              ))}
                            </div>
                            {selectedStop && (
                              <div className="stop-detail">
                                <div className="detail-title">
                                  <span>Selected science stop</span>
                                  <Badge
                                    value={selectedStop.properties.verdict}
                                  />
                                </div>
                                <p className="geology">
                                  {selectedStop.properties.geologic_unit ||
                                    "Geology unavailable"}
                                </p>
                                <div className="readout">
                                  <span>Rover tilt at this stop</span>
                                  {q(selectedStop.properties.rover_tilt_deg, 2)}
                                </div>
                                <Panorama
                                  url={selectedStop.properties.panorama_url}
                                />
                                <details>
                                  <summary>Stop notes and source</summary>
                                  <p>{selectedStop.properties.notes}</p>
                                  <button
                                    className="text-button"
                                    onClick={() => {
                                      setSourceId(
                                        selectedStop.properties.source_id,
                                      );
                                      setDialog("sources");
                                    }}
                                  >
                                    View source <ExternalLink size={12} />
                                  </button>
                                </details>
                              </div>
                            )}
                            <p className="footnote">
                              Measured stop locations provide context. They are
                              not measurements of an astronaut visit.
                            </p>
                          </>
                        )}
                        {i === 1 && (
                          <>
                            <p className="intro">
                              Select a terrain cell to inspect its assessment.
                            </p>
                            <label className="field-label">
                              Terrain cell
                              <select
                                aria-label="Terrain cell"
                                value={cell?.cell_id || ""}
                                onChange={(e) =>
                                  chooseCell(
                                    data.hazards.cells.find(
                                      (c) => c.cell_id === e.target.value,
                                    ),
                                  )
                                }
                              >
                                <option value="">Choose a cell…</option>
                                {data.hazards.cells.map((c) => (
                                  <option key={c.cell_id} value={c.cell_id}>
                                    {c.cell_id} · {c.verdict}
                                  </option>
                                ))}
                              </select>
                            </label>
                            {outside ? (
                              <div className="notice">
                                <ShieldAlert size={19} />
                                <div>
                                  <b>Not assessed</b>
                                  <p>
                                    This location is outside the available
                                    cells. No terrain verdict is assigned here.
                                  </p>
                                </div>
                              </div>
                            ) : (
                              cell && (
                                <>
                                  <div className="cell-assessment">
                                    <div>
                                      <span className="eyebrow">
                                        SELECTED CELL
                                      </span>
                                      <small>{cell.cell_id}</small>
                                    </div>
                                    <Badge value={cell.verdict} />
                                  </div>
                                  <div className="reason-box">
                                    <b>Assessment reason</b>
                                    <p>
                                      {cell.reason.includes("persistent hazard")
                                        ? "The model identifies a persistent hazard across neighboring analysis scales."
                                        : cell.reason}
                                    </p>
                                    <details>
                                      <summary>Full engine explanation</summary>
                                      <p>{cell.reason}</p>
                                    </details>
                                  </div>
                                  <div className="section-label">
                                    SLOPE BY BASELINE <span>DERIVED</span>
                                  </div>
                                  <div
                                    className="baseline-buttons"
                                    role="group"
                                    aria-label="Terrain analysis baseline"
                                  >
                                    {["64", "16", "4"]
                                      .filter(
                                        (b) => cell.slope_deg_by_baseline[b],
                                      )
                                      .map((b) => (
                                        <button
                                          key={b}
                                          className={
                                            baseline === b ? "chosen" : ""
                                          }
                                          onClick={() => setBaseline(b)}
                                        >
                                          {b} m
                                        </button>
                                      ))}
                                  </div>
                                  {tips && (
                                    <div className="context-tip">
                                      <HelpCircle size={15} />
                                      <span>
                                        Baseline is the distance over which
                                        slope is computed. It changes the
                                        comparison, not map zoom or the cell
                                        verdict.
                                      </span>
                                    </div>
                                  )}
                                  <div className="slope-chart">
                                    {["64", "16", "4"].map((b) => {
                                      const value =
                                        cell.slope_deg_by_baseline[b];
                                      return (
                                        value && (
                                          <div
                                            key={b}
                                            className={
                                              baseline === b ? "focused" : ""
                                            }
                                          >
                                            <span>{b} m</span>
                                            <div className="bar-track">
                                              <i
                                                style={{
                                                  width: `${Math.min(100, (value.value / 45) * 100)}%`,
                                                }}
                                              />
                                            </div>
                                            <b>{value.value.toFixed(1)}°</b>
                                          </div>
                                        )
                                      );
                                    })}
                                  </div>
                                  <div className="selected-reading">
                                    {q(cell.slope_deg_by_baseline[baseline])}
                                  </div>
                                  <p className="footnote">
                                    1 m is diagnostic only and excluded from the
                                    current decision logic.
                                  </p>
                                  <details>
                                    <summary>Confidence and evidence</summary>
                                    <Confidence cell={cell} />
                                    <div className="readout">
                                      <span>Elevation</span>
                                      {q(cell.elev_m)}
                                    </div>
                                    <div className="readout">
                                      <span>Rock abundance</span>
                                      {q(cell.rock_cfa_pct)}
                                    </div>
                                    <div className="readout">
                                      <span>Matched rover tilt</span>
                                      {q(cell.measured_rover_tilt_deg)}
                                    </div>
                                    <p className="footnote">
                                      A nearby rover record is context, not an
                                      exact ground-truth match.
                                    </p>
                                  </details>
                                </>
                              )
                            )}
                          </>
                        )}
                        {i === 2 && (
                          <>
                            <p className="intro">
                              Browse Perseverance’s measured observations. A
                              rover stop may not coincide with an assessed cell.
                            </p>
                            <label className="field-label">
                              Find a sol
                              <input
                                aria-label="Find a sol"
                                type="search"
                                inputMode="numeric"
                                value={solSearch}
                                onChange={(e) => setSolSearch(e.target.value)}
                                placeholder="e.g. 609"
                              />
                            </label>
                            <label className="field-label">
                              Rover observation
                              <select
                                aria-label="Rover observation"
                                value={waypoint?.properties.waypoint_id || ""}
                                onChange={(e) => {
                                  const w = data.waypoints.features.find(
                                    (w) =>
                                      w.properties.waypoint_id ===
                                      e.target.value,
                                  );
                                  if (w) chooseWaypoint(w);
                                }}
                              >
                                <option value="">Select an observation…</option>
                                {(waypoint &&
                                !filteredWaypoints.includes(waypoint)
                                  ? [waypoint, ...filteredWaypoints]
                                  : filteredWaypoints
                                ).map((w) => (
                                  <option
                                    value={w.properties.waypoint_id}
                                    key={w.properties.waypoint_id}
                                  >
                                    Sol {w.properties.sol} · Site{" "}
                                    {w.properties.site} / Drive{" "}
                                    {w.properties.drive}
                                  </option>
                                ))}
                              </select>
                            </label>
                            {!filteredWaypoints.length && (
                              <p className="footnote">
                                No observations match that sol.
                              </p>
                            )}
                            {waypoint && (
                              <>
                                <div className="observation-title">
                                  <h2>Perseverance</h2>
                                  <span>Sol {waypoint.properties.sol}</span>
                                </div>
                                <div className="readout">
                                  <span>Measured rover tilt</span>
                                  {q(waypoint.properties.rover_tilt_deg, 2)}
                                </div>
                                <div className="readout">
                                  <span>Pitch</span>
                                  {q(waypoint.properties.rover_pitch_deg, 2)}
                                </div>
                                <div className="readout">
                                  <span>Roll</span>
                                  {q(waypoint.properties.rover_roll_deg, 2)}
                                </div>
                                <Panorama
                                  url={waypoint.properties.panorama_url}
                                />
                                <p className="footnote">
                                  {waypoint.properties.lat.toFixed(5)}° N,{" "}
                                  {waypoint.properties.lon.toFixed(5)}° E
                                </p>
                              </>
                            )}
                            <div className="notice quiet">
                              <BookOpen size={18} />
                              <div>
                                <b>Keep observation and model separate</b>
                                <p>
                                  {cell?.measured_rover_tilt_deg
                                    ? "A matched value is available for the selected cell."
                                    : "No matched rover observation is provided for the selected terrain cell."}
                                </p>
                              </div>
                            </div>
                          </>
                        )}
                        {i === 3 && (
                          <>
                            <p className="intro">
                              Review the supplied route assessment and the
                              limits behind it.
                            </p>
                            {candidate && (
                              <>
                                <div className="cell-assessment">
                                  <span>Candidate EVA</span>
                                  <Badge value={candidate.properties.verdict} />
                                </div>
                                <div className="readout">
                                  <span>Route length</span>
                                  {q(candidate.properties.distance_m, 0)}
                                </div>
                                <div className="readout">
                                  <span>Estimated duration</span>
                                  {q(
                                    candidate.properties.estimated_duration_h,
                                    2,
                                  )}
                                </div>
                                <div className="readout">
                                  <span>Maximum route slope</span>
                                  {q(candidate.properties.max_slope_deg, 2)}
                                </div>
                                <div className="readout">
                                  <span>Estimated radiation dose</span>
                                  {q(
                                    candidate.properties
                                      .estimated_radiation_msv,
                                    4,
                                  )}
                                </div>
                                <div className="readout">
                                  <span>Max distance from start</span>
                                  <span className="quantity">
                                    <strong>
                                      {walkback == null
                                        ? "Unavailable"
                                        : `${(walkback / 1000).toFixed(2)} km`}
                                    </strong>
                                    <span className="provenance">
                                      DERIVED · route geometry
                                    </span>
                                  </span>
                                </div>
                                <p className="footnote">
                                  Distance from start is calculated on the Mars
                                  sphere. It does not establish a traversable
                                  return path.
                                </p>
                                <details>
                                  <summary>Supplied route notes</summary>
                                  <p>{candidate.properties.notes}</p>
                                </details>
                              </>
                            )}
                            <details open>
                              <summary>Reference constraints</summary>
                              <div className="readout">
                                <span>Suit slope limit</span>
                                {q(data.constraints.suit_max_slope_deg)}
                              </div>
                              <div className="readout">
                                <span>Walkback limit</span>
                                {q(data.constraints.walkback_max_km)}
                              </div>
                              <div className="readout">
                                <span>Maximum EVA duration</span>
                                {q(data.constraints.eva_duration_max_h)}
                              </div>
                            </details>
                            <div className="notice">
                              <ShieldAlert size={19} />
                              <div>
                                <b>Planning prototype</b>
                                <p>
                                  GO means the model’s criteria are met. It is
                                  not operational safety certification. Missing
                                  data and unassessed terrain remain
                                  limitations.
                                </p>
                              </div>
                            </div>
                            <button
                              className="secondary-button full-width"
                              onClick={download}
                            >
                              <ArrowDownToLine size={15} /> Export planning
                              summary
                            </button>
                          </>
                        )}
                      </div>
                    )}
                  </section>
                ))}
              </div>
              <div className="guide-bottom">
                <button
                  className="secondary-button"
                  disabled={step === 0}
                  onClick={() => navigate(step - 1)}
                >
                  <ArrowLeft size={15} /> Previous
                </button>
                <div
                  className="step-progress"
                  aria-label={`Step ${step + 1} of 4`}
                >
                  {steps.map((s, i) => (
                    <i key={s} className={i <= step ? "done" : ""} />
                  ))}
                </div>
                {step < 3 ? (
                  <button
                    className="primary-button"
                    onClick={() => navigate(step + 1)}
                  >
                    Next <ArrowRight size={15} />
                  </button>
                ) : (
                  <button className="primary-button" onClick={reset}>
                    <RotateCcw size={15} /> Reset
                  </button>
                )}
              </div>
            </>
          )}
        </aside>
      </main>
      {dialog === "sources" && (
        <Dialog title="Sources & provenance" onClose={() => setDialog(null)}>
          <p className="dialog-lead">
            Every reading retains its source and provenance. Explore the records
            behind this pack.
          </p>
          <div className="integrity-strip">
            <Check size={16} />
            {data.integrity === "sha256-verified"
              ? "Static payload SHA-256 checks passed"
              : "API payloads validated against shared schemas"}
            <span>
              Contract {data.manifest.contract_version} · Pack{" "}
              {data.manifest.pack_version}
            </span>
          </div>
          {data.manifest.sources.map((source) => (
            <article
              id={`source-${source.id}`}
              className={`source-card ${source.id === sourceId ? "highlighted" : ""}`}
              key={source.id}
            >
              <small>{source.id}</small>
              <h3>{source.title}</h3>
              <p>{source.citation}</p>
              <div>
                <span>{source.license}</span>
                {safeUrl(source.url) && (
                  <a
                    href={safeUrl(source.url)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open source <ExternalLink size={12} />
                  </a>
                )}
              </div>
            </article>
          ))}
          <p className="footnote">
            Hashes check consistency against the supplied manifest, not
            authorship or scientific validity. API mode trusts the middleware to
            verify its stored pack.
          </p>
        </Dialog>
      )}
      {dialog === "help" && (
        <Dialog
          title="A walk through the evidence"
          onClose={() => setDialog(null)}
        >
          <p className="dialog-lead">
            Marswalk connects a proposed astronaut walk with terrain assessments
            and real rover observations.
          </p>
          <ol className="help-steps">
            {steps.map((s, i) => (
              <li key={s}>
                <b>{s}</b>
                <p>
                  {
                    [
                      "Choose a science stop and see where it sits along the candidate route.",
                      "Select a cell. Compare slopes at different spatial baselines without changing its supplied verdict.",
                      "Browse measured Perseverance observations and inspect their source panoramas.",
                      "Review the simulated walk’s estimates, constraints and limitations.",
                    ][i]
                  }
                </p>
              </li>
            ))}
          </ol>
          <div className="tag-explainer">
            <p>
              <Badge value="MEASURED" /> Direct observations or published
              specifications.
            </p>
            <p>
              <Badge value="DERIVED" /> Values computed from source data.
            </p>
            <p>
              <Badge value="SIMULATED" /> Proposed astronaut activity and its
              estimates.
            </p>
          </div>
          <p>
            Confidence has three independent components: verified agreement,
            scale/data uncertainty, and hazard contradiction. They are not
            percentages of one probability.
          </p>
          <button
            className="primary-button"
            onClick={() => {
              setTips(true);
              setCollapsed(false);
              navigate(0);
              setDialog(null);
            }}
          >
            Show me around <ArrowRight size={15} />
          </button>
        </Dialog>
      )}
    </div>
  );
}
function Confidence({ cell }: { cell: HazardCell }) {
  return (
    <div className="confidence">
      {(
        [
          ["t", "Verified agreement"],
          ["i", "Scale/data uncertainty"],
          ["f", "Hazard contradiction"],
        ] as const
      ).map(([key, label]) => (
        <div key={key}>
          <span>{label}</span>
          <div className={`confidence-track ${key}`}>
            <i style={{ width: `${cell.confidence[key] * 100}%` }} />
          </div>
          <b>{cell.confidence[key].toFixed(2)}</b>
        </div>
      ))}
      <p className="footnote">
        Independent evidence components, not a normalized probability.
      </p>
    </div>
  );
}
export default function App() {
  const [data, setData] = useState<MarswalkData>(),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(undefined);
    setError("");
    try {
      const source = createDataSource(getConfig());
      source
        .load(controller.signal)
        .then((value) => {
          if (!controller.signal.aborted) setData(value);
        })
        .catch((e) => {
          if (!controller.signal.aborted)
            setError(
              e instanceof Error ? e.message : "Unable to load the data pack.",
            );
        });
    } catch (e) {
      setError(String(e));
    }
    return () => controller.abort();
  }, [attempt]);
  if (!data)
    return (
      <div className="load-screen">
        <img
          src={`${import.meta.env.BASE_URL}brand/marswalk-mark.svg`}
          alt=""
        />
        <span className="eyebrow">MARSWALK / JEZERO</span>
        <h1>
          {error
            ? "The data pack could not be loaded"
            : "Preparing your Marswalk"}
        </h1>
        <p role={error ? "alert" : "status"}>
          {error ||
            "Loading the route, terrain assessments and rover evidence."}
        </p>
        {error ? (
          <button
            className="primary-button"
            onClick={() => setAttempt((n) => n + 1)}
          >
            <RotateCcw size={16} /> Try again
          </button>
        ) : (
          <div className="loading-line" />
        )}
        <small>Static pack or shared API · no account required</small>
      </div>
    );
  return <Workspace data={data} onRetry={() => setAttempt((n) => n + 1)} />;
}
