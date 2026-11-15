import type { ReactNode } from "react";
import type {
  MarswalkData,
  EvaRouteFeature,
  HazardCell,
  Quantity,
} from "./data/types";
import { cellAt, routeParts, type LonLat } from "./domain";
import RoverImage from "./RoverImage";
import { AngleReading } from "./ScaleComparison";

export default function BenchmarkPanel({
  data,
  selected,
  onSelect,
  onInspect,
  q,
}: {
  data: MarswalkData;
  selected?: EvaRouteFeature;
  onSelect: (f?: EvaRouteFeature) => void;
  onInspect: (cell: HazardCell) => void;
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
      <h3>Orbit vs ground</h3>
      <p className="intro">
        One place, two kinds of evidence. These rover references are separate
        from the proposed walk and science stops.
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
          <div className="angle-pair">
            <AngleReading
              label="64 m orbital slope"
              value={cell?.slope_deg_by_baseline["64"]}
              tone="orbit"
              q={q}
            />
            <AngleReading
              label="Measured rover tilt"
              value={selected.properties.rover_tilt_deg}
              tone="detail"
              q={q}
            />
          </div>
          <p className="scale-caption">
            Orbital slope summarizes the containing terrain cell; rover tilt is
            a point observation. They cover different areas. Lines illustrate
            angles, not a terrain cross-section.
          </p>
          <RoverImage data={data} url={selected.properties.panorama_url} />
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
          {cell && (
            <>
              <div className="cell-assessment">
                <span>Containing cell · {cell.cell_id}</span>
                <span
                  className={`badge ${cell.verdict.toLowerCase().replace("_", "-")}`}
                >
                  {cell.verdict}
                </span>
              </div>
              <button
                className="scale-evidence-link"
                onClick={() => onInspect(cell)}
              >
                Compare this cell at 64 / 16 / 4 m →
              </button>
            </>
          )}
          <details>
            <summary>Benchmark explanation from the pack</summary>
            <p>
              The comparison above uses the containing cell. A point-sampled
              slope in these notes has different spatial support.
            </p>
            <p>{selected.properties.notes}</p>
          </details>
        </>
      )}
    </section>
  );
}
