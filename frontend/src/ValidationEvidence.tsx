import { useEffect, useState, type ReactNode } from "react";
import { loadValidationReport, sampleForWaypoint } from "./data/validation";
import { getConfig } from "./data/config";
import type { MarswalkData, Quantity, Waypoint } from "./data/types";

export default function ValidationEvidence({
  data,
  waypoint,
  q,
}: {
  data: MarswalkData;
  waypoint: Waypoint;
  q: (v?: Quantity | null, digits?: number) => ReactNode;
}) {
  const [open, setOpen] = useState(false),
    [report, setReport] =
      useState<Awaited<ReturnType<typeof loadValidationReport>>>(),
    [error, setError] = useState("");
  const [baseline, setBaseline] = useState("16");
  useEffect(() => {
    if (!open || report) return;
    const controller = new AbortController();
    setError("");
    loadValidationReport(getConfig(), data.manifest, controller.signal)
      .then((r) => {
        if (!controller.signal.aborted) setReport(r);
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "Report unavailable.");
      });
    return () => controller.abort();
  }, [open, report, data]);
  const sample = report && sampleForWaypoint(report, waypoint);
  const metrics = report?.test_even_metrics_by_baseline?.[baseline];
  const slope = sample?.dtm_slope_deg_by_baseline[baseline];
  return (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Map comparison at this rover stop</summary>
      {error ? (
        <p role="status">{error} Rover measurements remain available.</p>
      ) : !report ? (
        <p role="status">
          {open ? "Loading the comparison…" : "Open to load the comparison."}
        </p>
      ) : (
        <>
          <p className="scale-caption">
            These slopes were sampled at the rover position, rather than at a
            terrain cell’s centre. They do not change the cell verdict.
          </p>
          <div
            className="scale-buttons"
            role="group"
            aria-label="Distance used for rover comparison"
          >
            {["64", "16", "4"].map((b) => (
              <button
                key={b}
                aria-pressed={baseline === b}
                onClick={() => setBaseline(b)}
              >
                {b} m
              </button>
            ))}
          </div>
          {sample &&
          slope != null &&
          Number.isFinite(slope) &&
          slope >= 0 &&
          slope <= 90 ? (
            <>
              <div className="readout">
                <span>Map slope at rover position</span>
                {q(
                  {
                    value: slope,
                    unit: "deg",
                    tag: "DERIVED",
                    source_id: report.dtm_source_id,
                  },
                  2,
                )}
              </div>
              <div className="readout">
                <span>Measured rover tilt</span>
                {q(waypoint.properties.rover_tilt_deg, 2)}
              </div>
            </>
          ) : (
            <p>
              No matching validation sample is available at this stop. No nearby
              sample is substituted.
            </p>
          )}
          <details>
            <summary>How well does this scale match?</summary>
            <p>
              The report compares {report.waypoint_count_in_window} stops inside
              the assessed window. It does not validate the rover’s entire
              traverse.
            </p>
            {metrics && metrics.sample_count > 0 ? (
              <p>
                At {baseline} m, the average difference from measured tilt is{" "}
                <b>{metrics.mae_deg.toFixed(2)}°</b> across{" "}
                {metrics.sample_count} even-sol test stops. Odd-sol stops were
                used to adjust the model. Nearby stops can have similar terrain,
                so this does not prove the model works in a new area.
              </p>
            ) : (
              <p>No test comparison is available at this scale.</p>
            )}
            <p className="scale-caption">
              A statistical comparison of different measurements, not a
              probability of safety. The 1 m reading is kept for inspection, not
              for deciding the verdict.
            </p>
          </details>
        </>
      )}
    </details>
  );
}
