import type { ReactNode } from "react";

export default function DecisionExplanation({
  slopeLimit,
}: {
  slopeLimit: ReactNode;
}) {
  return (
    <details className="reading-help">
      <summary>What makes it GO, CAUTION or NO_GO?</summary>
      <p>
        The question is whether the model supports walking here under its
        assumptions. A gentle-looking slope alone is not enough.
      </p>
      <dl>
        <div>
          <dt>GO · the model’s checks pass</dt>
          <dd>
            The terrain checks show enough agreement, limited uncertainty and
            limited evidence of danger. GO is not a guarantee of safety.
          </dd>
        </div>
        <div>
          <dt>CAUTION · concerns remain</dt>
          <dd>
            Warnings, uncertain data or mixed evidence keep the model from
            giving GO, without meeting its rules for NO_GO. CAUTION is not
            permission to proceed.
          </dd>
        </div>
        <div>
          <dt>NO_GO · the model blocks it</dt>
          <dd>
            A blocking limit or sufficiently strong hazard evidence is reached.
            A blocked result can also mean required data is missing or a live
            assessment could not be completed reliably—not that danger was
            measured.
          </dd>
        </div>
      </dl>
      <div className="readout">
        <span>Spacesuit slope reference limit</span>
        {slopeLimit}
      </div>
      <p>
        If the terrain model’s accepted slope estimate reaches this limit, its
        slope rule blocks the cell. Being below it does not automatically give
        GO: other terrain checks still matter. The prototype also uses its own
        evidence thresholds; this limit is not the entire decision rule.
      </p>
      <p>
        A whole walk has additional checks. Obstacles or blocked terrain, dust,
        oxygen time, radio signal loss, distance from the start and time outside
        can affect its result. A solar particle alert or operator stop blocks
        live planning. Read the reasons for the specific route.
      </p>
    </details>
  );
}
