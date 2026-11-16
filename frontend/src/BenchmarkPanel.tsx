import EvidenceText from "./EvidenceText";
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
import ValidationEvidence from "./ValidationEvidence";

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
  const observation =
    selected && location
      ? data.waypoints.features.find(
          (w) =>
            w.properties.sol === selected.properties.sol &&
            Math.abs(w.properties.lon - location[0]) < 1e-7 &&
            Math.abs(w.properties.lat - location[1]) < 1e-7,
        )
      : undefined;
  return (
    <section
      className="benchmark-panel"
      aria-label="Measured hazard benchmarks"
    >
      <h3>Map vs rover</h3>
      <p className="intro">
        Compare the map with Perseverance’s measurements. These reference points
        are separate from the proposed walk. A sol is a day on Mars.
      </p>
      <label className="field-label">
        Rover reference point
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
              label="Slope from space · 64 m"
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
            Rover tilt is how far the rover leaned at this location. The map
            estimates slope across an area, so the two readings can differ. The
            sketches compare angles, not ground shapes.
          </p>
          <RoverImage data={data} url={selected.properties.panorama_url} />
          {observation && (
            <ValidationEvidence data={data} waypoint={observation} q={q} />
          )}
          <div className="readout">
            <span>Spacesuit slope reference limit</span>
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
            <summary>Technical reference notes</summary>
            <p>
              The comparison above uses the map cell around the rover. A slope
              calculated at the rover’s exact position covers a different area
              and can have a different value.
            </p>
            <EvidenceText
              text={selected.properties.notes}
              kind="note"
              summary="The source notes compare recorded rover tilt with map estimates. Different comparison distances and locations can give different values; these observations do not certify an astronaut route."
            />
          </details>
        </>
      )}
    </section>
  );
}
