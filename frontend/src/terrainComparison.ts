import type { HazardCell, Quantity } from "./data/types";

export function availableAngle(value?: Quantity | null) {
  return value &&
    value.tag !== "UNAVAILABLE" &&
    value.unit === "deg" &&
    Number.isFinite(value.value) &&
    value.value >= 0 &&
    value.value <= 90
    ? value
    : undefined;
}

export function compareSlopes(cell: HazardCell, baseline: string) {
  const coarse = availableAngle(cell.slope_deg_by_baseline["64"]);
  const selected = availableAngle(cell.slope_deg_by_baseline[baseline]);
  const difference =
    coarse && selected ? selected.value - coarse.value : undefined;
  let explanation = "Slope comparison unavailable for this baseline.";
  if (difference != null) {
    if (baseline === "64")
      explanation =
        "This is the broad 64 m view. Select 16 m or 4 m to compare a shorter analysis distance.";
    else if (Math.abs(difference) < 0.05)
      explanation = `The ${baseline} m and 64 m slopes are the same to one decimal place.`;
    else
      explanation = `The ${baseline} m slope is ${Math.abs(difference).toFixed(1)}° ${difference > 0 ? "steeper" : "gentler"} than the 64 m slope in this cell.`;
  }
  return { coarse, selected, difference, explanation };
}
