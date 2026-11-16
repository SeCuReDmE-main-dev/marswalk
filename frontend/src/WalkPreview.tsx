import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  Footprints,
  Pause,
  Play,
  RotateCcw,
  X,
} from "lucide-react";
import type { HazardCell, MarswalkData } from "./data/types";
import { linePoints, routeParts, type LonLat } from "./domain";
import { createRoutePreview, type PreviewPosition } from "./routePreview";

const colors = { GO: "#84c5af", CAUTION: "#f2b45f", NO_GO: "#f18d7e" };
const format = (n: number) => Math.round(n).toLocaleString("en-US");

export default function WalkPreview({
  data,
  onPosition,
  onInspect,
  onSource,
}: {
  data: MarswalkData;
  onPosition: (p?: PreviewPosition) => void;
  onInspect: (c: HazardCell) => void;
  onSource: (id: string) => void;
}) {
  const { candidate, stops } = routeParts(data);
  const preview = useMemo(
    () => candidate && createRoutePreview(linePoints(candidate), data.hazards),
    [candidate, data],
  );
  const [open, setOpen] = useState(false),
    [distance, setDistance] = useState(0),
    [playing, setPlaying] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const chart = useRef<SVGSVGElement>(null);
  const drag = useRef(false);
  const position = preview?.at(distance);
  useEffect(() => {
    onPosition(open && preview ? preview.at(distance) : undefined);
  }, [open, distance, preview, onPosition]);
  useEffect(() => () => onPosition(undefined), [onPosition]);
  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => {
      setReducedMotion(media.matches);
      setPlaying(false);
    };
    const visibility = () => {
      if (document.hidden) setPlaying(false);
    };
    media.addEventListener("change", change);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      media.removeEventListener("change", change);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);
  useEffect(() => {
    if (!playing || !open || !preview || reducedMotion) return;
    let frame = 0,
      last = 0;
    function tick(time: number) {
      if (last)
        setDistance((d) =>
          Math.min(
            preview!.total,
            d + (Math.min(100, time - last) / 45000) * preview!.total,
          ),
        );
      last = time;
      frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, open, preview, reducedMotion]);
  useEffect(() => {
    if (preview && distance >= preview.total) setPlaying(false);
  }, [distance, preview]);
  if (!preview || !candidate || !position) return null;
  const heights = preview.samples.flatMap((s) =>
    s.elevation ? [s.elevation.value] : [],
  );
  const min = heights.length ? Math.min(...heights) : 0;
  const max = heights.length ? Math.max(...heights) : 0;
  const x = (d: number) => 38 + (d / preview.total) * 918;
  const y = (h: number) => 14 + (1 - (h - min) / Math.max(1, max - min)) * 68;
  function seek(value: number) {
    setPlaying(false);
    setDistance(value);
  }
  function seekChart(clientX: number) {
    const rect = chart.current?.getBoundingClientRect();
    if (rect)
      seek(
        Math.max(
          0,
          Math.min(1, (((clientX - rect.left) / rect.width) * 1000 - 38) / 918),
        ) * preview!.total,
      );
  }
  return (
    <section
      className={`walk-preview ${open ? "is-open" : ""}`}
      aria-label="Walk preview"
    >
      <div className="preview-heading">
        <button
          className="preview-toggle"
          aria-expanded={open}
          aria-controls="walk-preview-content"
          onClick={() => {
            setOpen(!open);
            setPlaying(false);
          }}
        >
          <Footprints size={18} />
          <span>
            <b>Walk preview</b>
            <small>
              {open
                ? "Route playback · not live tracking"
                : "Play or scrub along the route"}
            </small>
          </span>
          {!open && <ChevronDown size={17} />}
        </button>
        {open && (
          <>
            <span
              className={`badge ${candidate.properties.verdict.toLowerCase().replace("_", "-")}`}
              title="Supplied route assessment"
            >
              {candidate.properties.verdict}
            </span>
            <button
              className="icon-button"
              aria-label="Close walk preview"
              onClick={() => {
                setOpen(false);
                setPlaying(false);
              }}
            >
              <X size={17} />
            </button>
          </>
        )}
      </div>
      {open && (
        <div id="walk-preview-content" className="preview-content">
          <div className="preview-readouts">
            <div>
              <small>Along the path · DERIVED</small>
              <strong>
                {format(position.distance)}{" "}
                <span>/ {format(preview.total)} m</span>
              </strong>
            </div>
            <div>
              <small>Cell elevation</small>
              <strong>
                {position.elevation
                  ? `${format(position.elevation.value)} m`
                  : "Unavailable"}
              </strong>
              {position.elevation && (
                <button
                  className="preview-source"
                  aria-label="View elevation source"
                  onClick={() => {
                    setPlaying(false);
                    onSource(position.elevation!.source_id);
                  }}
                >
                  {position.elevation.tag} · source ↗
                </button>
              )}
            </div>
            <div className="preview-cell">
              <small>Terrain at preview position</small>
              {position.cell ? (
                <>
                  <button
                    className="preview-inspect"
                    onClick={() => {
                      setPlaying(false);
                      onInspect(position.cell!);
                    }}
                  >
                    <i style={{ background: colors[position.cell.verdict] }} />
                    {position.cell.verdict} · Inspect cell ↗
                  </button>
                  <small>
                    Confidence {position.cell.confidence.t.toFixed(2)} agreement
                    · {position.cell.confidence.i.toFixed(2)} uncertainty ·{" "}
                    {position.cell.confidence.f.toFixed(2)} hazard
                  </small>
                </>
              ) : (
                <strong>Not assessed</strong>
              )}
            </div>
          </div>
          <svg
            className="preview-profile"
            ref={chart}
            viewBox="0 0 1000 90"
            preserveAspectRatio="none"
            role="img"
            aria-label="Coarse cell elevation along the supplied walk. Use the distance slider below to move the preview."
            onPointerDown={(e) => {
              drag.current = true;
              e.currentTarget.setPointerCapture(e.pointerId);
              seekChart(e.clientX);
            }}
            onPointerMove={(e) => {
              if (drag.current) seekChart(e.clientX);
            }}
            onPointerUp={() => {
              drag.current = false;
            }}
            onPointerCancel={() => {
              drag.current = false;
            }}
          >
            <defs>
              <linearGradient id="profile-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#4fd7eb" stopOpacity=".23" />
                <stop offset="100%" stopColor="#4fd7eb" stopOpacity="0" />
              </linearGradient>
            </defs>
            {[14, 48, 82].map((v) => (
              <line key={v} x1="38" x2="956" y1={v} y2={v} stroke="#a6c0cb22" />
            ))}
            {preview.samples.slice(1).map((s, i) => {
              const prev = preview.samples[i];
              if (!s.elevation || !prev.elevation) return null;
              const a = x(prev.distance),
                b = x(s.distance),
                c = y(prev.elevation.value),
                d = y(s.elevation.value);
              return (
                <g key={i}>
                  <path
                    d={`M${a},82 V${c} L${b},${d} V82 Z`}
                    fill="url(#profile-fill)"
                  />
                  <line
                    x1={a}
                    y1={c}
                    x2={b}
                    y2={d}
                    stroke={s.cell ? colors[s.cell.verdict] : "#a6c0cb"}
                    strokeWidth="2"
                    vectorEffect="non-scaling-stroke"
                  />
                </g>
              );
            })}
            <line
              x1={x(position.distance)}
              x2={x(position.distance)}
              y1="8"
              y2="86"
              stroke="#e9faff"
              strokeDasharray="3 3"
            />
            {position.elevation && (
              <circle
                cx={x(position.distance)}
                cy={y(position.elevation.value)}
                r="4"
                fill="#fff"
              />
            )}
          </svg>
          <div className="preview-axis">
            <span>Start · 0 m</span>
            <span>
              {heights.length
                ? `Cell elevation: ${format(min)} to ${format(max)} m`
                : "Elevation unavailable"}
            </span>
            <span>{format(preview.total)} m</span>
          </div>
          <label className="preview-slider">
            <span className="sr-only">Preview distance along route</span>
            <input
              type="range"
              min="0"
              max="1000"
              step="1"
              value={Math.round((distance / preview.total) * 1000)}
              aria-valuetext={`${format(position.distance)} metres along the supplied route`}
              onChange={(e) =>
                seek((Number(e.target.value) / 1000) * preview.total)
              }
            />
          </label>
          <div className="preview-controls">
            <button
              className="preview-play"
              disabled={reducedMotion}
              title={
                reducedMotion
                  ? "Reduced motion is on. Use the distance slider."
                  : "45-second visual preview; not walking speed"
              }
              onClick={() => {
                if (distance >= preview.total) setDistance(0);
                setPlaying(!playing);
              }}
            >
              {playing ? <Pause size={15} /> : <Play size={15} />}
              {playing
                ? "Pause"
                : distance >= preview.total
                  ? "Replay"
                  : "Play preview"}
            </button>
            <button
              className="preview-restart"
              aria-label="Restart walk preview"
              onClick={() => seek(0)}
            >
              <RotateCcw size={15} />
            </button>
            <div className="preview-stops" aria-label="Jump to science stop">
              {stops.map(
                (stop, i) =>
                  stop.geometry.type === "Point" && (
                    <button
                      key={stop.properties.feature_id}
                      title={stop.properties.title}
                      onClick={() =>
                        seek(
                          preview.nearestDistance(
                            stop.geometry.coordinates.map(Number) as LonLat,
                          ),
                        )
                      }
                    >
                      Stop {i + 1}
                    </button>
                  ),
              )}
            </div>
          </div>
          <p className="preview-note">
            {reducedMotion ? "Reduced motion: use the slider. " : ""}
            Elevations use {format(data.hazards.cell_size_m)} m cells; gaps are
            unassessed. Colors are model assessments, not safety certification.
            Route:{" "}
            <button
              aria-label="View preview route source"
              onClick={() => {
                setPlaying(false);
                onSource(candidate.properties.source_id);
              }}
            >
              {candidate.properties.tag} · source ↗
            </button>
          </p>
        </div>
      )}
    </section>
  );
}
