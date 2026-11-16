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
