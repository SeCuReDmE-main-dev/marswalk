import type { ReactNode } from "react";
import type { HazardCell, Quantity } from "./data/types";
import { availableAngle, compareSlopes } from "./terrainComparison";

type RenderQuantity = (value?: Quantity | null, digits?: number) => ReactNode;

export function AngleReading({
  label,
  value,
  tone,
  q,
}: {
  label: string;
  value?: Quantity | null;
  tone: "orbit" | "detail";
  q: RenderQuantity;
}) {
  const angle = availableAngle(value);
  const radians = ((angle?.value ?? 0) * Math.PI) / 180;
  const end = {
    x: 18 + 102 * Math.cos(radians),
    y: 112 - 102 * Math.sin(radians),
  };
  return (
    <div className={`angle-reading ${tone}`}>
      <b>{label}</b>
      <svg viewBox="0 0 140 126" aria-hidden="true">
        <path d="M18 10 V112 H130" className="angle-axis" />
        {[1, 2, 3].map((i) => (
          <path key={i} d={`M18 ${112 - i * 28} H130`} className="angle-grid" />
        ))}
        {angle ? (
          <>
            <path
              d={`M18 112 L${end.x} ${end.y} L${end.x} 112 Z`}
              className="angle-fill"
            />
            <path d={`M18 112 L${end.x} ${end.y}`} className="angle-line" />
            <circle cx={end.x} cy={end.y} r="4" className="angle-tip" />
          </>
        ) : null}
      </svg>
      {q(angle, 2)}
    </div>
  );
}

export default function ScaleComparison({
  cell,
  baseline,
  onBaseline,
  q,
}: {
  cell: HazardCell;
  baseline: string;
  onBaseline: (baseline: string) => void;
  q: RenderQuantity;
}) {
  const comparison = compareSlopes(cell, baseline);
  return (
    <section className="scale-comparison" aria-label="Terrain scale comparison">
      <h3>What changes with scale?</h3>
      <p className="scale-intro">
        A broad map can smooth over a short, steep stretch.
      </p>
      <div
        className="scale-buttons"
        role="group"
        aria-label="Terrain analysis baseline"
      >
        {["64", "16", "4"].map((b) => (
          <button
            key={b}
            aria-pressed={baseline === b}
            onClick={() => onBaseline(b)}
          >
            {b} m
            <span>{b === "64" ? "Broad" : b === "16" ? "Closer" : "Fine"}</span>
          </button>
        ))}
      </div>
      <div className="angle-pair">
        <AngleReading
          label="64 m orbital slope"
          value={comparison.coarse}
          tone="orbit"
          q={q}
        />
        <AngleReading
          label={`${baseline} m orbital slope`}
          value={comparison.selected}
          tone="detail"
          q={q}
        />
      </div>
      <p className="scale-finding" role="status">
        {comparison.explanation}
      </p>
      <p className="scale-caption">
        Angle sketches, not a terrain cross-section. Changing scale keeps the
        supplied <b>{cell.verdict}</b> verdict.
      </p>
      <details>
        <summary>What does 64 m mean?</summary>
        <p>
          It is the distance used to calculate the slope. A 64 m reading
          compares heights farther apart than a 4 m reading. Short steep
          sections can be less visible in the longer reading. These buttons do
          not change map zoom.
        </p>
      </details>
      <details>
        <summary>Why not 1 m?</summary>
        <p>
          The 1 m baseline is diagnostic only and excluded from the decision
          logic. {cell.slope_deg_by_baseline["1"]?.note}
        </p>
      </details>
    </section>
  );
}
