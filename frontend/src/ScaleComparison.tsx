import EvidenceText from "./EvidenceText";
import type { ReactNode } from "react";
import type { HazardCell, Quantity } from "./data/types";
import { availableAngle, compareSlopes } from "./terrainComparison";
import ReadingHelp from "./ReadingHelp";

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
      <p className="scale-caption">
        The map estimates ground slope using spacecraft images taken from orbit.
        The buttons choose the distance across the ground used for that
        calculation—not the height of a hill or the map zoom.
      </p>
      <div
        className="scale-buttons"
        role="group"
        aria-label="Distance used to calculate slope"
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
          label="Slope from space · 64 m"
          value={comparison.coarse}
          tone="orbit"
          q={q}
        />
        <AngleReading
          label={`Slope from space · ${baseline} m`}
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
      <details className="reading-help">
        <summary>Why compare 64 m, 16 m and 4 m?</summary>
        <p>
          Imagine a short, steep ramp on an otherwise gentle hillside. Comparing
          ground heights far apart can make the whole stretch look gentle.
          Comparing heights closer together can reveal the steeper part.
        </p>
        <dl>
          <div>
            <dt>64 m · the broader slope</dt>
            <dd>
              Uses heights farther apart. Useful for the general lie of the
              land, but short rises and dips can be less visible.
            </dd>
          </div>
          <div>
            <dt>16 m · a closer comparison</dt>
            <dd>
              Uses heights closer together. It shows how the reading changes
              between the broad 64 m calculation and the shorter 4 m one.
            </dd>
          </div>
          <div>
            <dt>4 m · shorter stretches</dt>
            <dd>
              Can reveal local steepness that the longer distances miss. It
              still cannot describe every rock or an astronaut’s individual
              footsteps.
            </dd>
          </div>
        </dl>
        <p>
          We care because an astronaut would have to cross the difficult parts,
          not just the average slope. A difference between readings tells us
          that the distance we use matters here. It is a reason to inspect the
          terrain, not proof of an obstacle. A shorter distance can give a
          gentler reading too, and errors in the height data can affect it more.
        </p>
        <p>
          These are three comparison distances used by this prototype, not three
          safety limits. The smallest distance is not automatically the most
          accurate. All three readings come from the same terrain model;
          comparing them does not replace observations on the ground.
        </p>
      </details>
      <details>
        <summary>Why not 1 m?</summary>
        <p>
          The 1 m reading is kept for inspection, but is not used to decide the
          verdict because it can include image-scale noise.{" "}
        </p>
        <EvidenceText
          text={cell.slope_deg_by_baseline["1"]?.note}
          kind="note"
        />
      </details>
      <ReadingHelp topics={["map", "cell", "height"]} />
    </section>
  );
}
