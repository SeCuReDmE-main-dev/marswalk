# Audit 04 — Pack, contracts, middleware, map card and documentation

## EXECUTIVE VERDICT

**I reject closure of the Part 4 assurance checklist at main `e38ceba70e9c6273cf35233d3255cd912a7a4809`.** I record **2 SEV-1 findings (REJECTED / F), 5 SEV-2 findings (HALF-DONE / I), and 8 verified controls (T)**. These are seven distinct findings and eight bounded successful controls, not a percentage of source coverage. I found no test failures in the completed offline runs, but I found nine skipped tests and independently reproduced integrity and fault-containment gaps that the passing tests do not cover.

I am **OpenAI Codex**, an AI audit assistant, not Philippe Pierre, Antigravity, a NASA employee, or an accredited NASA IV&V organization. I retain the requested `NASA_AUDIT_04_...` filename as a handoff identifier. I use NASA guidance as an inspection reference; I do not certify compliance, human rating, flight readiness, or astronaut safety.

I inspected a separate checkout pinned to the stated main commit, with a fresh delegated review context. I used the same host and an existing shared Python virtual environment; this is **not an independent external machine or a newly provisioned environment**. I had no author conversation transcript, but I received a coordinator's preliminary probe summary. I independently read the critical implementation, reran its isolated mutation/API probe, reran the full offline suite, reran CLI/static checks, and wrote a separate numerical/segment-intersection implementation. I distinguish inherited execution evidence from my reruns below. I did not modify frontend, engine, middleware, contract, schema, pack, tests, or git state.

## Scope, method and evidence

I inspected all seven requested middleware modules, `contracts/models.py`, the five schemas, all 17 manifest-listed payloads and the manifest, the specified documentation and six Part 4 test files. I verified binary payloads by hash/size and generated output; I did not claim a scientific reconstruction of images or the original DEM. Raw ignored `datalake/` data was absent; only tracked cache documentation/placeholders were preserved. The offline pytest harness permits localhost for TestClient/Windows socket pairs and denies remote socket connections and name resolution. It does not fabricate data or change test assertions.

I retain reproduction artifacts under `audit_evidence/part04/`:

- `probe_pack_api.py` and `probe-results.json`: coordinator-prepared probe, inspected and independently rerun by me, exit 0; all mutations occur in temporary pack copies.
- `independent_numbers.py` and `independent-numbers.json`: my separate spherical-distance and inclusive line/polygon intersection calculations, exit 0; no imports of engine/card geometry functions.
- `independent-cli-checks.log`: my exact CLI stdout and per-command exit codes.
- `independent-full-tests.log`: my full offline rerun, 111 collected, 102 passed, 9 skipped, 0 failed, 0 xfailed, exit 0.
- `slice-tests.log`: coordinator's Part 4 slice execution, 29 passed, 2 skipped, exit 0. I reviewed the test files and corroborated their execution in my full rerun.
- `source-head-results.json` and `check_sources.py`: coordinator's 11 URL HEAD checks, HTTP 200 including redirects; timestamp `2026-11-16T00:13:04Z` (November 15 locally).

Published pytest logs explicitly redact local home/checkout prefixes. Exact unredacted captured output is retained locally outside the report tree under `work/ivv-raw-logs/`; I do not present redacted logs as byte-identical raw captures. Python 3.12.10 and the actual dependency versions appear in the logs. I used the source import from this checkout, not a global installed copy.

## FINDINGS TABLE

| ID / verdict | File:line evidence | Executed/code proof and consequence | Surgical correction required |
|---|---|---|---|
| **04-F1 — SEV-1 / F: consumed payload need not have a digest entry** | `src/marswalk/middleware/pack_loader.py:123`, `:140`; `src/marswalk/contracts/models.py:161` | The loader iterates only `manifest.files`, then unconditionally reads four required documents. In an isolated copy I removed only the waypoint digest entry and changed a rover tilt to `88.0`; loading succeeded and exposed that value. The current committed inventory is complete, but completeness is not enforced. The manifest itself is an unsigned local trust input: changing it is an explicit precondition of this reproduction. I did not demonstrate remote write access. | Require unique entries for every required payload before reading it; reject missing/duplicate required entries and unverified consumed files. Keep optional legacy payload rules version-aware. Add a regression for omitted entries plus changed payload, without weakening existing oracle tests. |
| **04-F2 — SEV-1 / F: service initialization escapes route fail-safe** | `src/marswalk/middleware/api.py:72`, `:174`, `:180`; `src/marswalk/middleware/query_service.py:618`, `:966` | Service lookup/loading occurs before either query-service `try` block. Injecting `RuntimeError` at `get_query_service` yielded HTTP **500** for both route endpoints. The inner engine error envelope works, but the AGENTS invariant requires an internal error to return HTTP 200, `NO_GO`, and `FAIL_SAFE:`. A pack integrity error is mapped to 404 rather than that envelope. No silent `GO` occurred in this probe; the defect is the broken response guarantee. | Put service acquisition and route evaluation inside an endpoint-level containment boundary with a pack-independent, valid fail-safe response builder. Preserve deliberate request-validation/unknown-site semantics; add separate initialization/parsing failure regressions for both endpoints. |
| **04-I1 — SEV-2 / I: verified binary can change before it is served** | `src/marswalk/middleware/api.py:66`, `:209`, `:224`; analogous `:152`, `:203` | After the first JPEG GET loads/caches the verified service, I changed one byte in that temporary JPEG. The next GET returned **200**, changed bytes, and a SHA-256 different from the manifest. Path membership and containment are checked again; content integrity is not. This requires local post-load disk mutation and is not evidence of a client traversal exploit. | Serve the verified immutable byte snapshot, or verify and serve bytes from one read operation under an immutable/versioned pack publication policy. Rehashing a path before `FileResponse` alone leaves a check/use race. Cover JPEG and both raster routes. |
| **04-I2 — SEV-2 / I: clean-clone closure is unproved** | `tests/test_pack_integrity.py:144`, `:181`; `AGENTS.md:75` (verification gate); full log | Two Part 4 tests skip without raw cache: tilt independence under rebuild and committed-pack/fresh-rebuild parity. The full suite has **9 skips**. Thus cached pack loading works offline, but reproducible scientific construction and all benchmark paths were not re-executed. Exit 0 is not the required zero-skip gate. | Make a reviewed, small deterministic input fixture available for rebuild/independence checks, or document and provision the separately pinned raw input prerequisite for a complete verification run. Execute the missing checks before closure; do not delete skips, weaken assertions, or call these tests passed. |
| **04-I3 — SEV-2 / I: stale numerical prose and overstated cryptographic terminology** | `README.md:45`, `:47`, `:62`, `:180`; `src/marswalk/middleware/build_pack.py:690`; `public_packs/HUMAN.md:8`; `docs/contracts/10_CONTRAT_DONNEES.md:39`, `:47`; `src/marswalk/middleware/map_card.py:574` | README M2 distance `1,669.9 m` and walkback `1,430 m` disagree with committed M2 geometry (`2,290.584 m`, `1,927.662 m` from science origin). README Sol 700 `4 m=22.1°` / tilt `20.5°` do not match the waypoint validation sample `18.108°` / measured `20.3345°`. Builder prose still contains `1,925.2 m` / `0.78°` for a stop now `1,925.712 m` / `7.49°`; pipeline can replace that prose in the current engine build. Contract prose still shows health `1.0.0`, six files, and an EVA loop. The card reads stored M2 distance `2290.43`, not independently recomputed `2290.584`; the 0.154 m difference is small but disproves a blanket every-number-recomputed claim. SHA-256 records in a mutable manifest are checksums, not a digital signature or proof that a cited paper supports a value. | Generate narrative values from the same explicitly named spatial support and current pack; document the route-distance metric/rounding; refresh contract examples/endpoints. Call this a checksum-verified pack. If origin authentication is required, verify a detached signature or externally pinned trusted digest with a documented trust root; no additive data-field break is needed for this terminology correction. |
| **04-I4 — SEV-2 / I: requested complexity assurance fails the additional check** | `src/marswalk/middleware/map_card.py:103`; `src/marswalk/middleware/query_service.py:390`, `:634`; `pyproject.toml:62` | Default Ruff passes; C901 is not selected by the project. My explicit threshold-15 check reports map generator **36**, supercover **23**, route evaluator **21**, exit 1. This is distinct from a default Ruff failure. I found no classification/waiver evidence in this slice. | Split cohesive rendering/traversal/evaluation responsibilities while preserving behavior, then rerun behavioral checks. For components formally identified as safety-critical, record the safety classification and any justified approval-authority waiver. Do not assign human-rating status from a metric alone. |
| **04-I5 — SEV-2 / I: submission completion lacks reviewable evidence** | `README.md:178`, `:195`; `docs/AI_USAGE.md:3`, `:13`; submission evidence absent in reviewed files | References and AI disclosure exist. I found no confirmed public project submission, accessible final presentation/video, or live deployment evidence in this scope. README's blanket assertion that all equations/thresholds were verified is stronger than these clean-clone results. The older AI table labels Codex an optional frontend helper; it does not describe this backend audit. I do not infer that a mandatory live website or a literal `## References` heading is missing. | Link and privately-window-check the actual public demo/presentation and English project page; confirm submission in the competition system; update AI disclosure to the actual assistance and outstanding validation limitations. Keep these as evidence requirements rather than inventing website requirements. |

I treat F1 as a high-priority integrity-contract failure and F2 as a high-priority safety-interface failure. I do not claim an authenticated adversary can remotely edit the pack, nor that either probe demonstrated an unsafe `GO` result.

## VERIFIED CONTROLS AND COMPLETE CHECKLIST DISPOSITION

| Control | Status | Evidence / precise limit |
|---|---|---|
| T1: committed payload inventory, byte sizes and hashes | **T** | All **17** payloads listed, **4,663,360 bytes** total; no unlisted payload excluding `manifest.json`. All **17/17** same-length one-byte mutations rejected with `PackIntegrityError`. This excludes trust-root authentication and manifest omission (F1). |
| T2: provenance referential integrity and citation reachability | **T** | **22,767 Quantity** objects across the four required documents; **0 unknown source IDs**, **11 sources**. All 11 citation URLs answered HEAD 200. I verified the single DOI is syntactically the manifest citation and redirects; HEAD does not prove full paper contents, license, raw-input digest, or scientific support. |
| T3: schema regeneration drift | **T** | Five schema files exported into a temporary directory are byte-for-byte equal to committed schemas. I called the same exporter as CLI; I did not overwrite committed schemas. |
| T4: current contract acceptance | **T** | `models.py:30` accepts `1.0.0` and `1.1.0`; contract/schema tests passed. I verified the pinned snapshot, not every historical change against a separately supplied frozen v1.0 release. |
| T5: path/site protection | **T** | Resolver rejects traversal/backslashes/absolute paths; site regex precedes LRU lookup. Probe variants `%2e%2e%2fmanifest.json`, `..%5cmanifest.json`, unlisted JPEG and extra trailing path all returned 404. Existing invalid-site/cache-poisoning tests passed in full suite. |
| T6: operator stop and inner engine containment | **T** | Live safe-mode health flag true and both route verdicts `NO_GO`. The engine-error regression in `test_phase5_failsafe.py:84` passed; service acquisition is separately rejected by F2. |
| T7: reproducible card and checked pack-driven numbers | **T** | Regenerated SVG equals committed SVG; SHA-256 `fe2889a1970fe002654817f8143fb0e977d3e511b1e993f63d91b0995dc10ca0`. Independent distances, two M2 polygon hits, layer names, nearest-center slope and tilt match displayed values. Stored route summaries and hardcoded labels are not new physical measurements (I3). |
| T8: bounded concurrent API load | **T** | Full rerun passed `test_api_and_load.py:94`: 500 requests, 20 workers, `/cell` and `/evaluate-route`, all 200 and required p95 below 500 ms. This verifies that workload, not arbitrary `/plan-route`/camera concurrency or absence of all races. Cached post-load file mutation remains I1. |
| Manifest completeness enforcement/origin binding | **F** | F1; cryptographic authentication is not supplied by the self-contained checksum design. |
| Initialization/internal error route response | **F** | F2. |
| Continued integrity of served file bytes | **I** | I1. |
| Full clean-clone test gate, including rebuild | **I** | I2; 9 skips. |
| Numerical documentation/every SVG number claim | **I** | I3; card rendering is deterministic, underlying summaries/prose still require reconciliation. |
| Complexity <=15 / safety classification evidence | **I** | I4; requirement attribution clarified below. |
| README/submission readiness evidence | **I** | I5. |

These 15 rows define the executive totals: **8 T + 2 F + 5 I**. I exercised every requested checklist category but cannot infer 100% path coverage, provenance truth, or formal NASA compliance from those categories.

## INDEPENDENT NUMERICAL CROSS-CHECKS

I used the spherical haversine formula with **R = 3,396,190 m** and no flattening. My independent segment test checks endpoint inclusion and all segment/ring-edge intersections, rather than the card's 40 samples per segment. The two M2 intersections are real in the committed vector geometry; I leave planner-grid interpretation to Part 2.

| Quantity / spatial support | Recomputed result | Interpretation |
|---|---:|---|
| Science stop Sol 413 -> Sol 609 | **555.142655 m** | SVG displays 555.1 m. |
| Science stop Sol 413 -> Sol 753 | **1,925.712074 m** | SVG displays 1,925.7 m; current route note agrees. |
| Simulated EVA polyline length | **2,213.561735 m** | Stored/displayed 2,213.6 m agrees after rounding. |
| M2 exported polyline spherical length | **2,290.584196 m** | Stored 2,290.43 m / card 2,290.4 m; inspect metric and coordinate rounding before claiming identical recalculation. |
| M2 maximum walkback to Sol 413 science origin | **1,927.661658 m** | SVG 1,927.7 m agrees. Using the snapped M2 first vertex as origin instead yields 1,925.975442 m; I do not conflate these origins. |
| M2 exact obstacle contacts | **2 / 82** | `OBS-JEZ-001`, `OBS-JEZ-013`; matches SVG. The simulated route touches three different polygons and makes no obstacle-aware safety guarantee. |
| Grid verdict counts | **332 GO / 1,104 CAUTION / 164 NO_GO** | Total 1,600. |
| Missing layer keys | **3** | `crism_mtrdr_18m`, `meda_pds4_env`, `themis_ti_100m`; matches SVG/pack. |
| Sol 700 measured rover tilt | **20.3345°** | SVG rounds to 20.33°. |
| Sol 700 nearest stored cell center (`JEZ-R27-C37`) | **64 m 11.19°, 4 m 10.92°** | The SVG intentionally uses nearest-center selection (`map_card.py:190`); `/cell` also uses nearest-center selection. This is not the exact waypoint slope. |
| Sol 700 bbox floor-containing index (`JEZ-R27-C38`) | **64 m 13.31°, 4 m 12.68°** | A distinct cell assignment; I do not call 11.19° wrong by substituting this convention. |
| Sol 700 exact waypoint validation sample | **64 m 12.649°, 4 m 18.108°, 1 m 18.562°** | Another distinct spatial support. The route note's rounded 64 m 12.65° agrees with this sample, not the nearest-center value. The note's 1 m peak 23.13° is not this point sample and needs an explicit neighborhood definition. |
| Pack GCR baseline displayed on card | **0.67 mSv/day** | Equals committed constraint with `proxy Curiosity RAD, Gale` note. Equality to the pack is not a physical validation; the protocol's 0.64 baseline differs and is addressed by the physiology/radiation audit. |

I found no `22.1°` Sol 700 4 m value in these three explicitly evaluated supports. A separate neighborhood statistic could differ, but the README does not specify one, so its present comparison is not reproducible from the cited point/cell values.

## TEST EXECUTION LOG

I ran `PYTHONPATH=src` with `PYTHONUTF8=1`. My CLI log records:

```text
python -m marswalk.middleware.cli verify-pack --site jezero
[PACK VERIFIED] site=jezero waypoints=708 cells=1600 files=17
EXIT_CODE=0

python -m ruff check .
All checks passed!
EXIT_CODE=0

python -m ruff format --check .
122 files already formatted
EXIT_CODE=0

python -m ruff check --select C901 --config lint.mccabe.max-complexity=15 src/marswalk/middleware src/marswalk/contracts
Found 3 errors.
EXIT_CODE=1
```

The 122 formatted files include newly added audit evidence; the original pre-report check found 117 files formatted. The explicit C901 check is supplementary and does not change repository Ruff configuration. Its complete three diagnostics are in `independent-cli-checks.log`.

I reran the full suite through `audit_evidence/run_pytest_offline.py` with `-q -ra --tb=short --basetemp=work/part04-independent-full`:

```text
COLLECTED=111
OUTCOMES={'passed': 102, 'failed': 0, 'skipped': 9, 'error': 0, 'xfailed': 0, 'xpassed': 0}
EXIT_CODE=0
```

The exact stdout with path-prefix redaction, elapsed time, warning and skip reasons is linked in `audit_evidence/part04/independent-full-tests.log`. Nine skips occur at `test_b2_split_and_eval.py:38`, `test_b3_sweep_and_timing.py:46` and `:72`, `test_b4_sobol_and_ablation.py:17` and `:36`, `test_engine_phase2b.py:207`, `test_pack_integrity.py:144` and `:181`, and `test_phase4_obstacles_and_routing.py:111`. All explicitly require ignored raw-cache input. The Part 4 slice has 31 collected, 29 passed, 2 skipped. I observed no cache-absence failure, but absence caused skipped scientific/rebuild checks. A Starlette/TestClient deprecation warning is recorded; it did not alter outcomes.

## README & SUBMISSION READINESS GAPS

I confirmed a References & Data Sources section and an AI disclosure section already exist in README. I do not require an exact unnumbered heading. I distinguish source-code and static-card availability from an accessible project submission or public deployment. The reviewed repository evidence does not establish the latter.

The public [NASA-hosted Space Apps submission discussion](https://github.com/nasa/spaceapps/discussions/1973) describes an English project page, a public video of at most 30 seconds or up to seven slides, NASA-data explanation and AI-tool disclosure. I use that discussion as submission guidance, not proof of the team's submission or an authenticated final rulebook. Its described demo options do not imply a mandatory hosted live website. I recommend confirming the final official project-submission checklist and attaching accessible submission/demo evidence before claiming readiness.

The requested complexity threshold is more precisely associated with [NASA SWE-220, NPR 7150.2D section 3.7.5](https://swehb.nasa.gov/spaces/SWEHBVD/pages/105709643/SWE-220%2B-%2BCyclomatic%2BComplexity%2Bfor%2BSafety-Critical%2BSoftware): it applies to identified safety-critical software, and exceedances require reviewed, justified waiver. I have not established MarsWalk's NASA software classification, formal applicability or approval-authority review. I therefore report the measured metric and missing assurance evidence rather than declaring a blanket SWE-134 certification failure.

I require correction or explicitly accepted disposition of F1–F2, completion of the missing verification evidence, and reconciliation of the stale public claims before I would change this audit to VERIFIED. I leave source fixes, journal registration, commit, push and handoff coordination to the authorized coordinator; I do not impersonate `philippe-antigravity` in the journal.
