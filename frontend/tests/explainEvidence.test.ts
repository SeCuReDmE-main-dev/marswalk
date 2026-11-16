import test from "node:test";
import assert from "node:assert/strict";
import {
  explainReason,
  explainNote,
  geologyLabel,
} from "../src/explainEvidence";

test("filtering explanations do not equate discarded checks with safe ground", () => {
  const text = explainReason(
    "[Njf (Jezero floor unit, SIM 3464)] Retained 16m slope 1.1 deg; funnel pruned 2 outlier(s) (I_rough@4m, I_rough@16m)",
  );
  assert.match(text, /combined slope estimate is 1.1°/);
  assert.match(text, /main comparison distance is 16 m/);
  assert.match(text, /set aside 2 unusual checks/);
  assert.match(text, /does not prove/);
  assert.doesNotMatch(text, /I_rough|Njf|funnel/);
});
test("missing data and unfamiliar backend messages never become reassurance", () => {
  assert.match(
    explainReason("FAIL_SAFE: missing oxygen value"),
    /Required data is missing/,
  );
  assert.match(
    explainReason("FAIL_SAFE: outside assessed window"),
    /outside the assessed area/,
  );
  assert.match(
    explainReason("NEW_ENGINE_CODE: 123"),
    /technical interpretation/,
  );
  assert.match(
    explainReason("[x] Retained 16m slope 2.0 deg; new warning"),
    /technical interpretation/,
  );
  assert.match(explainNote("new source qualification"), /original note/);
});
test("geology stays approximate and unknown classifications are not guessed", () => {
  assert.equal(
    geologyLabel("Njf (Jezero floor unit, SIM 3464)"),
    "Approximate terrain type: Jezero floor unit",
  );
  assert.match(geologyLabel("unrecognized geology"), /original description/);
});
