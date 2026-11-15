import type { ReactNode } from "react";
import type { MarswalkData, EvaRouteFeature, Quantity } from "./data/types";
import { cellAt, routeParts, type LonLat } from "./domain";
import RoverImage from "./RoverImage";

export default function BenchmarkPanel({
  data,
  selected,
  onSelect,
  q,
}: {
  data: MarswalkData;
  selected?: EvaRouteFeature;
  onSelect: (f?: EvaRouteFeature) => void;
  q: (v?: Quantity | null, digits?: number) => ReactNode;
}) {
  const { benchmarks } = routeParts(data);
  if (!benchmarks.length) return null;
  const location =
    selected?.geometry.type === "Point"
      ? (selected.geometry.coordinates.map(Number) as LonLat)
      : undefined;
  const cell = location ? cellAt(data.hazards, location) : undefined;
  return (
    <section
      className="benchmark-panel"
      aria-label="Measured hazard benchmarks"
    >
      <div className="section-label">MEASURED HAZARD BENCHMARKS</div>
      <p className="intro">
        Compare orbital terrain with real rover tilt. These reference points are
        separate from the proposed walk and science stops.
      </p>
      <label className="field-label">
        Hazard benchmark
        <select
          value={selected?.properties.feature_id || ""}
          onChange={(e) =>
            onSelect(
              benchmarks.find(
                (b) => b.properties.feature_id === e.target.value,
              ),
            )
          }
        >
          <option value="">Choose a reference point…</option>
          {benchmarks.map((b) => (
            <option
              key={b.properties.feature_id}
              value={b.properties.feature_id}
            >
              Sol {b.properties.sol} ·{" "}
              {b.properties.title.replace(/^Benchmark \d+\s*[—–-]\s*/, "")}
            </option>
          ))}
        </select>
      </label>
      {selected && (
        <>
          <div className="cell-assessment">
            <span>Reference verdict</span>
            <span
              className={`badge ${selected.properties.verdict.toLowerCase().replace("_", "-")}`}
            >
              {selected.properties.verdict}
            </span>
          </div>
          <div className="readout">
            <span>Rover tilt at this reference point</span>
            {q(selected.properties.rover_tilt_deg, 2)}
          </div>
          <div className="readout">
            <span>Orbital slope · containing cell, 64 m baseline</span>
            {q(cell?.slope_deg_by_baseline["64"], 2)}
          </div>
          <div className="readout">
            <span>Suit slope reference limit</span>
            {q(data.constraints.suit_max_slope_deg, 1)}
          </div>
          {!cell && (
            <p className="notice quiet">
              Outside the assessed grid. No orbital cell assessment is assigned
              here; the measured reference remains available.
            </p>
          )}
          <p className="footnote">
            Rover tilt is a point observation; orbital slope summarizes terrain
            over a different area. They are different quantities. The 1 m
            baseline is diagnostic only.
          </p>
          <details>
            <summary>Benchmark explanation from the pack</summary>
            <p>{selected.properties.notes}</p>
          </details>
          <RoverImage data={data} url={selected.properties.panorama_url} />
        </>
      )}
    </section>
  );
}
