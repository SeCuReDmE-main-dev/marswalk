# Frontend polish and engine coverage

I shortened the four guide steps and help copy, added a visible purpose sentence and optional answers to specific beginner questions, and retained provenance and safety limits. Help dialogs now have accessible names and move keyboard focus to the guide. The general rover browser collapses while a benchmark is selected so different observations do not compete for attention.

I reviewed the engine interfaces. Health/safe mode, cell lookup, obstacles, planning/evaluation, scenarios, effort, oxygen, radio, camera cache, optional environmental fields and calibrated confidence were already connected. The useful unused output was `validation_report.json`.

**Map comparison at this rover stop** loads that report lazily, in both static and API modes, from the configured static pack URL. There is no validation-report API endpoint. It requires the active manifest's byte count/SHA-256, exported backend schema, matching pack identity and known sources. Stale or missing reports stay unavailable without blocking the map.

Point samples match waypoint ID, sol, coordinates and rounded measured tilt; no nearest observation is substituted. Users can inspect 64/16/4 m point slopes and even-sol test errors with sample counts. The current report has 147 in-window observations and 72 even-sol test observations. At Sol 700, the 64 m point value is 12.649°, separately from containing cell C38's 13.31°. Odd/even validation is not independent spatial validation or a safety probability. Internal gate logs, benchmark records and encoded planner rasters remain diagnostic resources rather than extra user controls.

## Verification

- 29 frontend tests and production build pass; new tests cover report tampering, schema/source/pack identity and exact-point matching.
- Real API smoke against Jean's `2369fea` hardening passes. Browser planning returned a real CAUTION route; changing payload invalidated the previous result.
- Desktop/mobile checks cover help, Escape and focus, tips-off guide collapse, 3D/preview, point validation and outside-window absence, source dialogs, image decoding and exported summary JSON (three science stops, two references). No JavaScript errors or horizontal overflow observed.
- Eleven source URLs and five canonical NASA photo URLs returned HEAD 200. Five served local JPEGs matched their sizes/hashes. Other mission-wide photo URLs were not exhaustively rechecked. Raw results remain in local `work/polish-link-results.json`.
- Ruff and 17-file pack verification pass. Full Python validation still stops on missing local `datalake/SIM3464_metadata.xml`; no full-repository green claim is made.
- Browser QA used an ephemeral build override for a fresh engine at port 8001. Committed configuration still defaults to port 8000. No backend/shared schema/pack was edited for this frontend change.

Screenshots: `screenshots/polished-help-desktop.png`, `screenshots/rover-validation-mobile.png`.

## Beginner reading pass

Each guide step now opens with its own purpose: identify the proposed walk,
inspect details a broad map can miss, compare with rover observations, then
read the route assessment and limits. The persistent introduction identifies
Jezero and Perseverance. Essential context stays visible even with tips off;
longer explanations expand beside the relevant reading.

The interface says “slope from space” instead of “orbital slope”, explains
analysis distances separately from map zoom, and distinguishes proposed science
stops from recorded rover stops. Sol, tilt, pitch and roll have plain-language
context where used. Technical geology descriptions remain in stop notes.
Optional definitions cover terrain cells, elevation, dust, effort, oxygen,
radio and camera direction. Intermediate radio calculations sit in technical
planner details. Values, sources, provenance and verdict logic are unchanged.

The production build and 29 frontend tests pass. Browser checks at desktop and
390 px mobile width confirm the context, scale explanation and verdict wording,
with no horizontal overflow or JavaScript errors observed. Steps collapse with
tips off. This is a copy/interaction review, not a comprehension study with new
users. Ruff and pack verification pass. A repeat full-Python run produced no
output and was interrupted; it supplies no new test result. The previously
observed missing local `SIM3464_metadata.xml` limitation remains unresolved.

Screenshots: `screenshots/beginner-context-desktop.png`,
`screenshots/plain-language-slopes-mobile.png`.

The scale comparison now explains the 64/16/4 m calculation distances beside
the buttons, with an expandable hillside/ramp example and a description of
each distance. It explains why scale differences matter for a walk, why shorter
is not automatically more accurate, and why these are not safety limits.
Help also explains the project goal and the role of Perseverance. Production
build and all 29 frontend tests pass; expanded theory was checked in the browser
with no JavaScript errors observed (`screenshots/scale-theory.png`).

## Pull and technical wording review

`git pull --ff-only origin main` returned `Already up to date.` Existing UI
coverage includes the current terrain layers, rover evidence, route planning
and evaluation, scenarios, radio/oxygen/effort, camera cache and validation
report. No additional engine feature was added for this review.

Cell reasons, route warnings, quantity qualifications and route/stop notes now
have readable context with the exact source text in an expandable original.
Known reason formats are translated conservatively; unfamiliar formats explicitly
request technical interpretation. A retained slope can combine scales, so its
named scale is described as the main comparison distance, not as a separate raw
slope measurement. Filtering checks is never described as proving safe terrain.
Geology remains approximate. External-layer names and several science labels
are expanded; original identifiers and data-status notes remain inspectable.

Build and 32 frontend tests pass. Browser checks used the reported example at
JEZ-R32-C34 and confirmed the 1.1° summary and unchanged original wording.
Mobile route readings showed no horizontal overflow; no JavaScript errors were
observed. Screenshot: `screenshots/readable-engine-reason.png`. The full Python
gate limitation documented above remains unresolved.
