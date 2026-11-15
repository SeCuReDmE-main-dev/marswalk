# External Clean-Room NASA IV&V Hostile Audit Protocol for Philippe Pierre — Before 17:00

**Target Completion:** Before the **17:00** meeting.
**Objective:** Run **4 independent, clean-room NASA IV&V (`NPR 7150.2D` / `NASA-STD-8739.8B`) hostile audits** from your own machine and your own Antigravity instance (with zero exposure to my local conversation history and without my gitignored local `datalake/` directory) across **100% of the backend, engine, data pack, schemas, benchmarks, and tests** that you did not author, and push the 4 resulting reports into `shared/10_HANDOFFS/`.

---

## Step-by-Step Instructions (How to Run Before 17:00)

1. **Sync `origin/main` in a clean terminal on your machine:**
   ```bash
   git fetch origin
   git checkout main
   git pull --ff-only origin main
   ```
2. **Open 4 fresh Antigravity conversations (or run sequentially in 4 clean turns)** on your machine with the repository root checked out at `main`.
3. **Paste Prompt 1, Prompt 2, Prompt 3, and Prompt 4** (below) into your Antigravity.
   - Each prompt inspects a non-overlapping slice of `src/marswalk/**`, `public_packs/jezero/v1/**`, `schemas/**`, `bench/**`, `tests/**`, and `docs/**`.
   - None of them touch `frontend/**`.
   - Because your machine does not have the gitignored `datalake/` folder, your Antigravity will also catch any test that accidentally depends on `datalake/` instead of `public_packs/jezero/v1/`.
4. **Verify that all 4 audit reports are generated in `shared/10_HANDOFFS/`:**
   - `shared/10_HANDOFFS/NASA_AUDIT_01_GEODESY_DTM_OBSTACLES.md`
   - `shared/10_HANDOFFS/NASA_AUDIT_02_PLITHOGENIC_FUNNEL_ASTAR.md`
   - `shared/10_HANDOFFS/NASA_AUDIT_03_XEVA_HUMAN_RF_RADIATION.md`
   - `shared/10_HANDOFFS/NASA_AUDIT_04_PACK_MIDDLEWARE_API_DOCS.md`
5. **Acknowledge handoff `HO-002` and push `shared/` back to `origin/main` before 17:00:**
   ```bash
   python tools/spaceapps_bridge.py handoff-ack --id HO-002 --by philippe --note "Completed all 4 external NASA IV&V audits on clean machine"
   git add shared/
   git commit -m "I add external NASA IV&V hostile audit reports 01-04 from clean machine"
   git push origin main
   ```

---

## Prompt 1 / 4 — Planetocentric Geodesy, Multi-Scale HiRISE DEM (`1m/4m/16m/64m`), Obstacles (`M1`) & Calibration (`AoA`)

Copy-paste into Antigravity Session #1:

```markdown
ROLE & IMPERSONATION (ZERO MERCY / CLEAN-ROOM EXTERNAL AUDIT):
You are a Lead NASA Independent Verification & Validation (IV&V) Software & Planetary Geodesy Inspector (NASA IV&V Facility / JPL Mars 2020 Landing-Site Hazard & USGS Astrogeology Photogrammetry Assurance), auditing under NASA Procedural Requirements NPR 7150.2D (SWE-060, SWE-087, SWE-134) and NASA-STD-8739.8B.

You are running on an independent external machine with ZERO prior conversation context from the engine author. Do NOT trust docstrings, comments, or README claims. Trust ONLY:
1. The actual Python AST and mathematical formulas on disk on `origin/main`;
2. What actually executes when you run Python / pytest in this clean clone (where gitignored local caches like `datalake/` do not exist);
3. Cross-checks you compute yourself with one-liner Python scripts against `public_packs/jezero/v1/`.

IMPORTANT REPOSITORY RULE:
Use first-person singular ("I") in all commit messages and report prose (never "we"). Never modify `frontend/`.

SCOPE OF AUDIT (PART 1 OF 4 — GEODESY, MULTI-SCALE DEM, OBSTACLES M1 & AOA CALIBRATION):
Do NOT audit or modify `frontend/`. Inspect ONLY the following backend/engine files on `origin/main`:
- `src/marswalk/engine/dtm_ingest.py`
- `src/marswalk/engine/boulder_cfa.py`
- `src/marswalk/engine/obstacles_m1.py`
- `src/marswalk/engine/sim3464_ingest.py`
- `src/marswalk/engine/themis_ingest.py`
- `src/marswalk/engine/crism_ingest.py`
- `src/marswalk/engine/calibration_aoa.py`
- `src/marswalk/engine/validation.py`
- `tests/test_phase3_geodesy_and_aoa.py`
- `tests/test_engine_phase2b.py`

MANDATORY NASA IV&V INSPECTION CHECKLIST (EXECUTE & VERIFY EVERY ITEM):
1. Planetocentric Spherical Geodesy & Anisotropic Metric Scaling:
   - Verify whether Mars radius `R = 3,396,190.0 m` is consistently enforced and whether longitude/latitude degree-to-meter conversions apply `cos(lat)` scaling at Jezero (~18.46°N -> `cos(lat) ≈ 0.9485`). Flag any isotropic planar distortion where `dx_m` omits `cos(lat)`.
2. Multi-Scale Horn (1981) 3x3 Slope Kernel (`1 m`, `4 m`, `16 m`, `64 m` baselines):
   - Verify the exact finite-difference denominator (`8 * dx`, `8 * dy`), elevation pre-averaging / downsampling at `4 m`, `16 m`, `64 m`, and `NoData` / `NaN` propagation.
   - Check why `1 m` stereo pixel-scale noise is separated from `4 m` human-scale slope and verify the numbers in `public_packs/jezero/v1/validation_report.json` against `public_packs/jezero/v1/waypoints.geojson` (708 Perseverance stops).
3. Obstacle Extraction (`M1` — `obstacles_m1.py` & `boulder_cfa.py`):
   - Verify that `1 m / pixel` HiRISE DTM resolution is NEVER falsely claimed to detect individual meter-scale boulders (`CFA`), and that extracted polygons in `public_packs/jezero/v1/obstacles.geojson` represent only `>= 4 m` rock formations and steep scarps (`internal_relief_m`, `obstacle_type`).
   - Verify the physical clearance buffer (`0.85 m` radius -> `1.70 m` corridor check) and verify whether a `>= 2.0 m` corridor remains open.
4. External Layer Honesty (`THEMIS`, `CRISM`, `SIM3464`) & Area of Applicability (`calibration_aoa.py`):
   - Confirm that unavailable layers (`THEMIS`, `CRISM`) are never silently fabricated with synthetic random noise when files are absent, and instead emit `UNAVAILABLE` with indeterminacy `I = 1.0`.
   - Run `pytest -q tests/test_phase3_geodesy_and_aoa.py tests/test_engine_phase2b.py` from your clean machine and report any test that fails when `datalake/` is absent.

OUTPUT & GIT HANDOFF REQUIREMENT:
Write a rigorous, zero-complacency Markdown audit report to:
`shared/10_HANDOFFS/NASA_AUDIT_01_GEODESY_DTM_OBSTACLES.md`
containing:
- `EXECUTIVE VERDICT`: Count of `SEVERITY 1 (REJECTED / F)`, `SEVERITY 2 (HALF-DONE / I)`, and `VERIFIED (T)`.
- `TEST EXECUTION LOG`: Exact stdout/exit code of running `pytest` on this slice from your machine (without `datalake/`).
- `FINDINGS TABLE`: Every finding with `[File:Line]`, severity (`SEV-1`, `SEV-2`, `SEV-3`), mathematical/code proof, and exact surgical fix required.
- `INDEPENDENT NUMERICAL CROSS-CHECKS`: At least 5 numbers recomputed independently by you from `public_packs/jezero/v1/`.

Finally, register the handoff in the journal:
`python tools/spaceapps_bridge.py journal-append --author philippe-antigravity --text "I completed external NASA IV&V Audit Part 1 (Geodesy/DTM/Obstacles)"`
```

---

## Prompt 2 / 4 — Plithogenic Fusion `<T, I, F>`, 3-Stage Funnel, Neutrosophic Gates (`G0–G3`) & Anisotropic `A*` Planner (`M2`)

Copy-paste into Antigravity Session #2:

```markdown
ROLE & IMPERSONATION (ZERO MERCY / CLEAN-ROOM EXTERNAL AUDIT):
You are a Senior NASA IV&V Autonomous Surface Mobility & Safety-Critical Algorithm Inspector (JPL Surface Mobility Flight Software `autonav` / NASA IV&V Facility, auditing under NPR 7150.2D SWE-060, SWE-086, SWE-134 and NASA Software Safety Audit Checklist 8.17).

You are running on an independent external machine with ZERO prior context from the algorithm author. Do NOT trust comments, docstrings, or `docs/ENGINE_MATH.md` prose unless the actual Python code in `src/marswalk/engine/` and the numbers in `bench/results/*.json` match 100%.

IMPORTANT REPOSITORY RULE:
Use first-person singular ("I") in all commit messages and report prose (never "we"). Never modify `frontend/`.

SCOPE OF AUDIT (PART 2 OF 4 — PLITHOGENIC FUSION, 3-STAGE FUNNEL, GATES G0-G3, A* PLANNER M2 & BENCHMARKS):
Do NOT audit or modify `frontend/`. Inspect ONLY:
- `src/marswalk/engine/plithogenic.py`
- `src/marswalk/engine/carriers.py`
- `src/marswalk/engine/prefilter.py`
- `src/marswalk/engine/funnel.py`
- `src/marswalk/engine/gates.py`
- `src/marswalk/engine/search_astar.py`
- `src/marswalk/engine/planner_m2.py`
- `src/marswalk/engine/pipeline.py`
- `docs/ENGINE_MATH.md`
- `bench/` and `src/marswalk/bench/` (`bench/results/*.json`)
- `tests/test_b0_prefilter_and_g1.py`
- `tests/test_b1_funnel_and_attacks.py`
- `tests/test_b2_split_and_eval.py`
- `tests/test_b3_sweep_and_timing.py`
- `tests/test_b4_sobol_and_ablation.py`
- `tests/test_b5_pack_funnel_and_1m_note.py`
- `tests/test_phase3_route.py`

MANDATORY NASA IV&V INSPECTION CHECKLIST (EXECUTE & VERIFY EVERY ITEM):
1. Plithogenic Triplet Fusion `<T, I, F>` & Non-Compensatory Safety Veto (`plithogenic.py`, `carriers.py`, `funnel.py`):
   - Verify the algebraic formula for `plithogenic_combine_triplet(a, b, c)` at boundary values `c = 0.0`, `c = 0.5`, `c = 1.0`.
   - Verify whether prime geology or science proximity can EVER override a hard safety veto (`slope > 20.0°` or `walkback > 2,000 m`), or if the safety veto is strictly lexicographic and non-compensatory.
   - Check `docs/ENGINE_MATH.md` against `plithogenic.py` and `funnel.py`: flag any discrepancy between documented equations/tiers (`[PUBLISHED]`, `[ADAPTED]`, `[ NOVEL ]`) and the implemented code.
2. 8-Connected / 16-Connected Anisotropic A* Planner & String-Pulling (`planner_m2.py`, `search_astar.py`):
   - Verify `A*` heuristic admissibility: what is `V_MAX_XEVA_KMH` (`2.4 km/h` at `-5%` downhill grade in Tobler's hiking function)? Can the heuristic ever overestimate true step cost (violating Dijkstra optimality)?
   - Verify the Bresenham supercover line-of-sight (`supercover_grid_cells`) and string-pulling cost guard (`string_pull_with_cost_guard`): check for negative-index wrap-around bugs (`r < 0` or `c < 0`), diagonal corner-cutting across blocked cells, or shortcuts across high-risk cells.
   - Check whether `ROUTE-EVA-M2-OBSTACLE-AWARE` in `public_packs/jezero/v1/route.geojson` touches any obstacle polygon in `obstacles.geojson` and why (grid discretization vs smoothed polyline).
3. Neutrosophic Gates (`G0–G3` in `gates.py`) & Benchmark Integrity (`bench/results/*.json`):
   - Verify the `PASS / HOLD / BLOCK` state machine in `gates.py` and confirm that persistent `HOLD` escalates to `BLOCK`.
   - Inspect `bench/results/b3_sweep.json`, `b5_bootstrap.json`, `b6_ablation.json`, `b7_sobol.json`, `b8_timing.json` and run all `test_b*.py` and `test_phase3_route.py` tests on your machine.
4. Stale Prose or Hardcoded Strings in `pipeline.py`:
   - Inspect `src/marswalk/engine/pipeline.py` (especially around line 755) for any hardcoded slope numbers in route notes (e.g. `12.65 deg` vs the actual cell `JEZ-R27-C37` 64 m slope `11.19 deg` at Sol 700).

OUTPUT & GIT HANDOFF REQUIREMENT:
Write a rigorous Markdown audit report to:
`shared/10_HANDOFFS/NASA_AUDIT_02_PLITHOGENIC_FUNNEL_ASTAR.md`
containing:
- `EXECUTIVE VERDICT`: Count of `SEVERITY 1 (REJECTED / F)`, `SEVERITY 2 (HALF-DONE / I)`, and `VERIFIED (T)`.
- `TEST EXECUTION LOG`: Exact output of running `pytest` on all Part 2 test files from your machine.
- `FINDINGS TABLE`: Every finding with `[File:Line]`, severity (`SEV-1`, `SEV-2`, `SEV-3`), proof, and surgical fix.
- `ALGORITHM & BENCHMARK VERIFICATION`: Independent verification of A* admissibility, supercover corner safety, and Sobol/ablation benchmark reproducibility.

Finally, register the handoff in the journal:
`python tools/spaceapps_bridge.py journal-append --author philippe-antigravity --text "I completed external NASA IV&V Audit Part 2 (Plithogenic/Funnel/A*)"`
```

---

## Prompt 3 / 4 — Human xEVA Physiology (`M4`), Space Radiation (`RAD/SVF/M3`), UHF Diffraction (`414.2 MHz`), Rover Cameras (`M5`) & `MEDA`

Copy-paste into Antigravity Session #3:

```markdown
ROLE & IMPERSONATION (ZERO MERCY / CLEAN-ROOM EXTERNAL AUDIT):
You are a Lead NASA Johnson Space Center (JSC) xEVA Systems, Crew Physiology, Space Radiation (SRAG) & Surface RF Communications IV&V Inspector, auditing under NPR 7150.2D for Human-Rated Safety-Critical Software.

You are running on an independent external machine with ZERO prior context from the module author. Your job is to protect astronaut lives by hunting down every physical, physiological, radiological, or electromagnetic inaccuracy, unit mismatch, or unverified assumption.

IMPORTANT REPOSITORY RULE:
Use first-person singular ("I") in all commit messages and report prose (never "we"). Never modify `frontend/`.

SCOPE OF AUDIT (PART 3 OF 4 — XEVA PHYSIOLOGY, KINEMATICS M4, RADIATION SVF/M3, UHF DIFFRACTION, CAMERAS M5 & MEDA):
Do NOT audit or modify `frontend/`. Inspect ONLY:
- `src/marswalk/engine/eva_human_rf.py`
- `src/marswalk/engine/kinematics_m4.py`
- `src/marswalk/engine/radiation_svf.py`
- `src/marswalk/engine/topographic_refuge_m3.py`
- `src/marswalk/engine/m20_raw_images_m5.py`
- `src/marswalk/engine/meda_envelope.py`
- `tests/test_phase4_obstacles_and_routing.py`
- `tests/test_phase6_hardening.py`

MANDATORY NASA JSC / IV&V INSPECTION CHECKLIST (EXECUTE & VERIFY EVERY ITEM):
1. Suited Metabolic Power & Walkback O2 Contingency (`eva_human_rf.py`, `kinematics_m4.py`):
   - Verify the distinction between slope angle `theta` (degrees) and grade fraction `g = tan(theta)` in Minetti (2002) and Pandolf/CSRM equations.
   - Verify the canonical MkIII suit mass (`121.0 kg`), body mass (`75.0 kg` / `80.0 kg`), Martian gravity scaling (`0.3794 g`), Norcross (2010) regression (`MEASURED`) vs Pandolf CSRM (`DERIVED`), and the Artemis contingency walkback floor (`695.8 W` at `2.0 km/h`).
   - Check `walkback_o2_margin_min`: verify how `nominal_w` (3.0 h nominal traverse) and `walkback_w` are computed, and check whether `payload_kg` affects contingency walkback when `metabolic_rate_w < 695.8 W`.
2. Space Radiation Dose (`radiation_svf.py`) & Partial Topographic Refuge (`topographic_refuge_m3.py`):
   - Verify the Curiosity RAD baseline (`0.64 mSv/day` = `26.67 uSv/h` GCR surface dose rate from Hassler et al. 2014) and confirm that it is explicitly attributed as a Gale Crater proxy (`proxy Curiosity RAD, Gale`), never disguised as an in-situ Jezero dosimeter.
   - Verify the finite-wall Sky View Factor (`SVF`) occlusion geometry (`analytical_finite_wall_sky_occlusion`) and the `7.0%–9.1%` GCR reduction near scarp toes (`0.35` sky occlusion).
   - Confirm that scarp-toe occlusion is NEVER claimed to be a solar storm shelter (`SPE_REFUGE_ROUTING_WEIGHT == 0.0`, and under `spe_alert=True` the route verdict is immediately `NO_GO`).
3. UHF 414.2 MHz Knife-Edge Fresnel-Bullington Diffraction (`eva_human_rf.py`):
   - Verify the wavelength (`c / 414.2 MHz ≈ 0.7238 m`), first Fresnel zone radius `F1`, Mars spherical bulge `(d1 * d2) / (2 * R_mars)`, antenna heights (`3.0 m` Perseverance rover mast at Sol 413 origin to `1.8 m` suit antenna), `0.60 * F1` clearance threshold (`nu = -0.60 * sqrt(2) ≈ -0.8485 -> 0 dB`), and ITU-R P.526 diffraction loss.
   - Verify that this models direct suit-to-rover line-of-sight to Sol 413 (`84%` of the 40x40 grid cells occluded `NO_GO`), and is never misrepresented as an orbital relay link.
4. Rover POV Cameras (`m20_raw_images_m5.py`) & MEDA Envelope (`meda_envelope.py`):
   - Verify that the retired `api.nasa.gov/mars-photos` endpoint is completely absent, that `mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020` is used with strict offline fallback (`allow_network=false`), and that `panorama_url` in `waypoints.geojson` contains zero dead `mmgis-maps` URLs.

OUTPUT & GIT HANDOFF REQUIREMENT:
Write a rigorous Markdown audit report to:
`shared/10_HANDOFFS/NASA_AUDIT_03_XEVA_HUMAN_RF_RADIATION.md`
containing:
- `EXECUTIVE VERDICT`: Count of `SEVERITY 1 (REJECTED / F)`, `SEVERITY 2 (HALF-DONE / I)`, and `VERIFIED (T)`.
- `TEST EXECUTION LOG`: Exact output of running `pytest` on `tests/test_phase4_obstacles_and_routing.py` and `tests/test_phase6_hardening.py` on your machine.
- `FINDINGS TABLE`: Every finding with `[File:Line]`, severity (`SEV-1`, `SEV-2`, `SEV-3`), physical/mathematical proof, and surgical fix.
- `INDEPENDENT PHYSICS VERIFICATION`: Recompute by hand/script at least 5 physical outputs (Minetti grade vs angle, Pandolf watts, O2 margin, SVF GCR reduction, Fresnel `nu` parameter).

Finally, register the handoff in the journal:
`python tools/spaceapps_bridge.py journal-append --author philippe-antigravity --text "I completed external NASA IV&V Audit Part 3 (xEVA/RF/Radiation/Cameras)"`
```

---

## Prompt 4 / 4 — Frozen Contracts, SHA-256 Signed Pack (`public_packs/jezero/v1/`), FastAPI Middleware, SVG Map Card (`map_card.py`) & Docs

Copy-paste into Antigravity Session #4:

```markdown
ROLE & IMPERSONATION (ZERO MERCY / CLEAN-ROOM EXTERNAL AUDIT):
You are a Lead NASA Goddard / Ames Open-Science Data Assurance, Ground Data System API & Cryptographic Pack Integrity Inspector (auditing under NASA-STD-8739.8B, NPR 7150.2D Cybersecurity & Fault Containment Checklists 58–73, and NASA Planetary Data System PDS4 Provenance Standards).

You are running on an independent external machine with ZERO prior context from the backend author. You must treat every file in `public_packs/jezero/v1/`, every JSON schema in `schemas/`, every FastAPI endpoint in `src/marswalk/middleware/`, and every claim in `README.md` / `docs/` as untrusted until proven by execution on your machine.

IMPORTANT REPOSITORY RULE:
Use first-person singular ("I") in all commit messages and report prose (never "we"). Never modify `frontend/`.

SCOPE OF AUDIT (PART 4 OF 4 — FROZEN CONTRACTS, SIGNED PACK, FASTAPI MIDDLEWARE, SVG MAP CARD & DOCUMENTATION):
Do NOT audit or modify `frontend/`. Inspect ONLY:
- `src/marswalk/contracts/models.py`
- `src/marswalk/middleware/api.py`
- `src/marswalk/middleware/query_service.py`
- `src/marswalk/middleware/pack_loader.py`
- `src/marswalk/middleware/build_pack.py`
- `src/marswalk/middleware/cli.py`
- `src/marswalk/middleware/map_card.py`
- `public_packs/jezero/v1/**` (all 17 files) and `public_packs/HUMAN.md`
- `schemas/*.schema.json` and `schemas/HUMAN.md`
- `docs/assets/jezero_eva_survival_map.svg`, `docs/contracts/10_CONTRAT_DONNEES.md`, `docs/AI_USAGE.md`, `README.md`, `THIRD_PARTY_NOTICES.md`
- `tests/test_contracts_and_schemas.py`, `tests/test_pack_integrity.py`, `tests/test_api_and_load.py`, `tests/test_phase5_failsafe.py`, `tests/test_phase8_map_card.py`, `tests/test_repo_hygiene.py`

MANDATORY NASA DATA ASSURANCE & API IV&V CHECKLIST (EXECUTE & VERIFY EVERY ITEM):
1. Cryptographic Pack Integrity & Provenance Chain (`pack_loader.py`, `public_packs/jezero/v1/manifest.json`):
   - Run `python -m marswalk.middleware.cli verify-pack --site jezero` on your machine.
   - Verify that every single file in `public_packs/jezero/v1/` is listed in `manifest.json` with an exact byte count and SHA-256 hash, and that mutating 1 byte of any file raises `PackIntegrityError`.
   - Verify all 11 citation sources in `manifest.json` (`sources`): check DOIs, URLs, and verify that every `MEASURED`, `DERIVED`, and `SIMULATED` quantity in `waypoints.geojson`, `route.geojson`, `hazard_grid.json`, and `eva_constraints.json` references a valid `source_id`.
   - Check `build_pack.py` (especially around line 690) and `route.geojson` notes for any stale text discrepancy (e.g. `1,925.2 m` in prose note vs `1,925.7 m` spherical distance).
2. JSON Schema Drift & Contract Frozenness (`models.py`, `schemas/*.schema.json`):
   - Verify whether `python -m marswalk.middleware.cli export-schemas` produces byte-for-byte identical schemas to those committed in `schemas/*.schema.json`.
3. FastAPI Fault Containment, Path Traversal & Safe-Mode (`api.py`, `query_service.py`):
   - Test path traversal protection on `/v1/sites/{site_id}/panoramas/{filename}` and `site_id` validation (`../`, `%2e%2e`, unlisted files).
   - Verify `MARSWALK_SAFE_MODE=1` and internal exception `FAIL_SAFE` behavior on `/evaluate-route` and `/plan-route` (confirming that an unhandled internal error never returns silent `GO`, and always degrades to `NO_GO` with `FAIL_SAFE` reason).
   - Check cyclomatic complexity (`NPR 7150.2D SWE-134 <= 15`) and thread-safety under concurrent requests.
4. Standalone SVG Survival Map Card (`map_card.py`, `docs/assets/jezero_eva_survival_map.svg`):
   - Run `python -m marswalk.middleware.cli generate-map-card` into a temporary path and verify that it is byte-for-byte identical to `docs/assets/jezero_eva_survival_map.svg`.
   - Verify that every number displayed on the SVG card (walkback distances, slopes, obstacle polygon touches `2/82`, `UNAVAILABLE` layer keys `crism_mtrdr_18m, meda_pds4_env, themis_ti_100m`, Sol 700 `64 m` slope `11.19°` vs `20.33°` ground tilt) is dynamically computed from the pack and matches independent recalculation.
5. Full Test Suite Execution on a Clean External Machine (without `datalake/`):
   - Run `pytest -q --tb=short` across all Part 4 test files (and the full test suite) on your machine. Flag every test in `test_pack_integrity.py` or elsewhere that fails because `datalake/` is gitignored!

OUTPUT & GIT HANDOFF REQUIREMENT:
Write a rigorous Markdown audit report to:
`shared/10_HANDOFFS/NASA_AUDIT_04_PACK_MIDDLEWARE_API_DOCS.md`
containing:
- `EXECUTIVE VERDICT`: Count of `SEVERITY 1 (REJECTED / F)`, `SEVERITY 2 (HALF-DONE / I)`, and `VERIFIED (T)`.
- `TEST EXECUTION LOG`: Exact output of running `verify-pack`, `ruff check .`, and `pytest` on your clean machine.
- `FINDINGS TABLE`: Every finding with `[File:Line]`, severity (`SEV-1`, `SEV-2`, `SEV-3`), proof, and surgical fix.
- `README & SUBMISSION READINESS GAPS`: Any missing section required by NASA Space Apps 2026 (e.g. explicit `## References` heading, live demo link, etc.).

Finally, register the handoff in the journal and push `shared/`:
`python tools/spaceapps_bridge.py journal-append --author philippe-antigravity --text "I completed external NASA IV&V Audit Part 4 (Pack/Middleware/API/SVG)"`
`git add shared/ && git commit -m "I add external NASA IV&V hostile audit reports 01-04 from clean machine" && git push`
```
