import { explainNote, explainReason } from "./explainEvidence";

export default function EvidenceText({
  text,
  kind = "reason",
  summary,
}: {
  text?: string | null;
  kind?: "reason" | "note";
  summary?: string;
}) {
  if (!text) return null;
  return (
    <div className="evidence-text">
      <p>
        {summary ??
          (kind === "reason" ? explainReason(text) : explainNote(text))}
      </p>
      <details>
        <summary>Original technical wording</summary>
        <p>{text}</p>
      </details>
    </div>
  );
}
