// Presentation only: never infer or change a verdict from these messages.
export function explainReason(text: string): string {
  if (/^SAFE_MODE:/.test(text))
    return "The operator has stopped live route planning.";
  if (/^FAIL_SAFE:/.test(text)) {
    if (/outside/.test(text))
      return "This location or route is outside the assessed area. The model blocks it.";
    if (/missing/.test(text))
      return "Required data is missing. The model blocks the assessment rather than assuming the route is safe.";
    return "The engine could not complete a reliable assessment. The model blocks the route; check the original message.";
  }
  const cell = text.match(
    /^\[.+\] Retained (4|16|64)m slope (\d+(?:\.\d+)?) deg; (.+)$/,
  );
  if (cell) {
    // The engine's retained slope can combine scales; the named scale is dominant.
    const base = `The model’s combined slope estimate is ${cell[2]}°. Its main comparison distance is ${cell[1]} m.`;
    const tail = cell[3];
    if (/^persistent hazard across neighbor scales \(.+\)$/.test(tail))
      return `${base} A warning remained across neighboring comparison distances. This is a model warning, not a confirmed obstacle.`;
    const pruned = tail.match(/^funnel pruned (\d+) outlier\(s\) \(.+\)$/);
    if (pruned)
      return `${base} The filtering rules set aside ${pruned[1]} unusual checks. That does not prove those checks were wrong or the ground is safe.`;
    if (tail === "coherent across 4m-64m scales")
      return `${base} The model reports agreement across its 4–64 m comparisons. Read this together with the verdict and uncertainty.`;
  }
  const rules: [RegExp, string][] = [
    [
      /^Solar Particle Event/,
      "A burst of particles from the Sun triggers the model’s stop rule. Terrain shelter does not cancel it.",
    ],
    [
      /^Route point .*out of bbox/,
      "Part of the proposed route is outside the assessed map area.",
    ],
    [
      /^Maximum retained funnel slope/,
      "The model’s slope estimate exceeds the spacesuit slope limit used for this assessment.",
    ],
    [
      /^Route segment crosses .*NO_GO/,
      "The route crosses terrain cells marked NO_GO.",
    ],
    [
      /^Route crosses moderate retained slope/,
      "The route has warnings involving slope, differences between scales, dust or walking effort. Review the readings and assumptions below.",
    ],
    [
      /^All traversed cells and walkback distance satisfy/,
      "The checked terrain cells and distance from the start meet the model’s limits. This does not certify a safe walk.",
    ],
    [
      /^Atmospheric dust optical depth/,
      "The assumed dust level exceeds the model’s limit.",
    ],
    [
      /^Walkback distance/,
      "Distance from the start or estimated return time exceeds the model’s return limit.",
    ],
    [
      /^Primary O2 reserve exhausted/,
      "The model estimates insufficient oxygen time after the return and other assumed use.",
    ],
    [
      /^UHF 414\.2 MHz diffraction loss/,
      "Terrain weakens the assumed radio link beyond its allowed signal loss.",
    ],
    [
      /^Estimated EVA duration/,
      "The estimated time outside exceeds the model’s duration limit.",
    ],
  ];
  return (
    rules.find(([pattern]) => pattern.test(text))?.[1] ??
    "This engine message needs technical interpretation. Open the original wording before relying on this assessment."
  );
}

export function explainNote(text: string): string {
  if (/below 2x DTM resolution/.test(text))
    return "Too close to the terrain model’s smallest detail for the decision rules; kept for inspection only.";
  if (/roughness.*proxy|orbital detection floor/.test(text))
    return "An indirect terrain estimate adds uncertainty; it is not a direct rock count.";
  if (/unavailable.*not present/.test(text))
    return "The required local data file is missing. This reading is unavailable.";
  if (/Curiosity RAD|MSL RAD/.test(text))
    return "Radiation context comes from Curiosity, at a different location on Mars.";
  return "This reading has a source or model qualification. Open the original note for details.";
}

export function geologyLabel(text?: string | null): string {
  if (!text) return "Terrain classification unavailable";
  const name = text.match(/^[A-Za-z0-9]+ \((.+), (?:USGS )?SIM 3464\)$/)?.[1];
  return name
    ? `Approximate terrain type: ${name}`
    : "Approximate terrain classification; see the original description below.";
}
