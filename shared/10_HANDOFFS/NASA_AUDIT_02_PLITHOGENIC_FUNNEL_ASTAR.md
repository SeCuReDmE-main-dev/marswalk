# Audit 02 — Fusion, funnel, gates, A* and benchmarks

## Identity, baseline and limits

I performed this audit as **OpenAI Codex**, in a fresh delegated context against pinned `main` commit `e38ceba70e9c6273cf35233d3255cd912a7a4809` on the report-only branch `feat/external-audits`. I am not Antigravity, NASA staff, or a NASA certification authority. This is a code and evidence audit inspired by the requested IV&V checklist; I do not certify compliance with NPR 7150.2D or NASA-STD-8739.8B.

I used an isolated checkout on the **same machine**, with the existing installed Python dependency environment. I verified the imported implementation belonged to this checkout. I did not use the author's ignored raw data cache: `datalake/` contained only tracked `.gitkeep` and `README.md`. The pytest harness denied external sockets/DNS and permitted localhost for Windows asyncio. I did not fetch raw NASA products, modify implementation/tests/frontend/contracts/schemas/packs, or change git refs. I inspected the Part 2 files and their direct data/dependency interfaces. I did not perform an independent full NASA standards assessment or rerun raw-DTM benchmarks without their input data.

## EXECUTIVE VERDICT

**REJECTED for safety/readiness assurance.** Passing tests do not establish the claimed veto, evidence-gate, or exact smoothing-cost guarantees.

| Counting unit | Count |
|---|---:|
| SEV-1 findings — REJECTED / F | 4 |
| SEV-2 findings — HALF-DONE / I | 3 |
| SEV-3 findings — documentation/property qualifications | 3 |
| VERIFIED / T checklist checks | 6 of 13 |

I count each finding ID once; checklist checks are a separate denominator. The 13 checks below contain **6 VERIFIED, 4 PARTIAL, 3 REJECTED**. A check can include multiple findings; a SEV-2 finding is not counted again as a SEV-1 finding. SEV-1 denotes a reproducible safety/readiness invariant breach, SEV-2 an incomplete guarantee or reproducibility/attribution gap, and SEV-3 a narrower documentation or property mismatch.

The assigned suite returned **45 passed, 5 skipped, 0 failed, 0 xfailed; exit 0**. The five skipped raw-DTM benchmarks prevent satisfying the repository's **zero-skips** verification gate. I therefore do not report this slice as fully verified.

## Mandatory checklist disposition

| Check | Disposition | Actual evidence and qualification |
|---|---|---|
| C01: Fusion at contradiction `c=0, .5, 1` | VERIFIED | Independent arithmetic matches all three implemented outputs; see numerical table below. |
| C02: Non-compensatory slope/walkback veto | REJECTED | The legacy six-attribute function vetoes correctly, but the active funnel can return `GO` for admitted 4 m slope 25°, and production walkback is reduced/clamped before veto. B02. |
| C03: Published/adapted/novel mathematics and entropy claims | PARTIAL | T/F equations match their documented arithmetic; the conflict boost in I is an adaptation presented under established mathematics, and the initial entropy need not meet the claimed floor. B07/B10. |
| C04: M2 admissibility and graph optimum | VERIFIED | `v_max=2.4 km/h`; finite nonnegative standard edge weights imply `cost >= distance/v_max`. Thirty seeded grids match an independently implemented scalar-edge Dijkstra search. This establishes the 8-connected graph result at weight 1, not a continuous-terrain optimum. |
| C05: M2 supercover bounds and blocked corners | VERIFIED | All 625 directed center-to-center segments in a 5×5 grid match an exact rational closed-square intersection oracle. Negative endpoints and a blocked orthogonal diagonal touch are rejected. |
| C06: Legacy `search_astar.py` endpoint/corner safety | REJECTED | A `NO_GO` 30° goal is reachable with walkback limit 0; two blocked orthogonal cells do not prevent a diagonal; a blocked start equal to goal returns success. B03. |
| C07: String pulling cannot increase physical risk-weighted line integral | PARTIAL | The guard compares a proxy with equal lengths assigned to every touched cell. A deterministic counterexample increases the actual piecewise-cell integral. B05. |
| C08: Packed M2 route versus obstacles | VERIFIED | Two of 82 exported bounding polygons have positive interior intersection, but zero route segments touch blocked PNG cells. The bounding polygons enclose free gaps; this is not proof of a raster collision. |
| C09: Persistent HOLD helper escalation | VERIFIED | With unchanged evidence the actual helper produces `HOLD, HOLD, BLOCK` after two refinements. |
| C10: Real pipeline gate evidence and fail-closed inputs | REJECTED | Production callbacks change metrics without recomputation; G1 also labels scale coherence as validation error and reports 8 m for a 48.71 m grid. Missing/NaN gate evidence can pass. B01/B04. |
| C11: Sweep/bootstrap/ablation/Sobol/timing reproduction | PARTIAL | Sweep record hashes and selection are internally consistent; raw-DTM reruns skip. B3/B6/B7/B8 lack a pack/input fingerprint. I do not claim independently reproduced Sobol or bootstrap intervals. B06. |
| C12: Pipeline notes and mathematical benchmark prose | PARTIAL | Sol 700's 12.65° agrees with its exact waypoint sample, while nearest-center cell C37 has 11.19°. Its hardcoded 23.13° peak lacks defined sampling support; ENGINE_MATH benchmark numbers/significance are stale. B08/B09. |
| C13: Tune/test membership and available benchmark hashes | VERIFIED | Public pack gives 75 odd-sol and 72 even-sol in-window IDs with no ID overlap; B5 evaluation/bootstrap manifest hashes match the current manifest digest. This verifies membership/hash binding, not statistical spatial independence. |

## FINDINGS TABLE

| ID / severity | File:line | Proof and impact | Surgical suggested fix |
|---|---|---|---|
| **B01 / SEV-1** | `src/marswalk/engine/pipeline.py:912`, `:972`, `:981`, `:983`, `:1014` | I compiled and executed the actual nested callback ASTs without executing the pack builder. G0 changes nodata `.20→.05`, coverage `.80→1.0` and obtains PASS without re-ingesting. G1 changes mean I `.60→.3375` and reported step `8→4` without changing a grid. G2 changes Jaccard `.30→.55` without rerunning a route. Separately, the committed G1 record says **8 m** and test MAE **0.8634°**; actual pack cell size is **48.71 m**, and independent `mean(abs(s4-s16))=0.8633625°`, proving this is interscale coherence, not measured held-out error. These are accepted readiness claims without the represented evidence. | Replace metric-editing callbacks with real re-ingest/reclassification/search operations that return recomputed measurements, or retain HOLD and let it block. Feed actual grid spacing and explicitly named held-out validation metrics into G1; expose coherence separately. Do not replace the represented evidence with a more convenient number. |
| **B02 / SEV-1** | `src/marswalk/engine/funnel.py:259`, `:401`, `:409`; `src/marswalk/engine/pipeline.py:276`, `:367`, `:377` | The active profile (`p=3`, five retained carriers) on `{4:25°,16:3°,64:2°}`, valid source, walkback 100 m, returns **GO**, retained slope **2.931°**, confidence `{t:.9486,i:.3069,f:.0578}` after pruning 4 m `I_slope`. The hard threshold is tested on the retained weighted slope, not on the admitted physical 4 m slope. Production additionally passes `min(1950, .75*physical_walkback)` into both carriers and veto: a physical 2500 m becomes 1875 m, and the 2000 m veto is unreachable for every positive physical distance. This proves a component/pipeline assurance defect; it does **not** demonstrate a deployed API `GO` on that synthetic terrain or claim the packed M2 path violates its separate guards. | Apply the sourced hard safety envelope to valid admitted physical scales and actual walkback before pruning/utility aggregation. Keep excluded 1 m diagnostic noise separate. Remove the distance reduction/clamp from safety inputs; if needed for an experiment, name/tag it as a simulated variable and never use it for safety verdicts. Preserve the physical violation through later stages. |
| **B03 / SEV-1** | `src/marswalk/engine/search_astar.py:75`, `:112`, `:121` | The legacy 8-connected search returns `[(0,0),(1,1)]` when the goal is `NO_GO`, 30° slope, and configured maximum walkback is **0 m**. It also returns this diagonal with both adjacent orthogonal cells `NO_GO`, and returns a one-cell path when start=goal is blocked. These failures are in `search_astar.py`, still used by the pack pipeline, **not** the hardened M2 search. | Centralize bounds/finite-data/verdict/slope/walkback/corridor validation and apply it to start and goal as well as intermediate cells before the start=goal shortcut. Require both orthogonal cells to be admissible for a diagonal. Revalidate exact stop-to-grid anchor segments before exporting coordinates. |
| **B04 / SEV-1** | `src/marswalk/engine/gates.py:65`, `:67`, `:137`, `:138`, `:139`, `:249` | `gate_g1_classify({}, {})` passes using favorable fabricated defaults. G1 with all three readiness metrics NaN passes. G3 with NaN walkback, duration and dose, three stops and `all_stops_within_2km=True` passes because comparisons with NaN are false. G0 with zero coverage and a 64-character string of `z` reports coverage 1 and a verified SHA. The helper's correct HOLD escalation does not repair inputs already classified PASS. This is an internal stage-gate proof, not an API exception-containment test. | Require every readiness field, validate finite numeric domains and SHA syntax, and return BLOCK with explicit invalid-evidence reasons before comparisons. Distinguish an absent field from zero; do not use `value or 1.0` for coverage. Validate evidence hashes against bytes at the responsible layer rather than treating string length as verification. |
| **B05 / SEV-2** | `src/marswalk/engine/planner_m2.py:324`, `:343`, `:737` | The claimed exact line integral uses `ds=total_distance/len(supercover_cells)` even though crossed-cell lengths differ and corner-only touches have zero length. On the seeded flat-risk grid in the evidence script, raw graph cost is **218.3416098519 s**, reported smoothed cost **216.464577 s**, but independent exact segment-cell clipping gives smoothed cost **218.5192959171 s**. A shortcut that increases cost by **0.1776860652 s** is accepted. No blocked cells are involved. | Compute cell-entry/exit parameters and integrate each cost density over its actual positive segment length. Keep zero-length corner touches in safety checks with zero integration weight. Use one consistently defined cost measure for raw budgets, accepted shortcuts and final telemetry; document discretization error separately. |
| **B06 / SEV-2** | `tests/test_b2_split_and_eval.py:38`; `tests/test_b3_sweep_and_timing.py:46`, `:72`; `tests/test_b4_sobol_and_ablation.py:17`, `:36`; `src/marswalk/bench/eval.py:55`; `bench/results/b3_sweep.json:1`, `b6_ablation.json:1`, `b7_sobol.json:1`, `b8_timing.json:1` | All five raw-DTM benchmark tests skip without the ignored TIFF. Observation extraction calls raw-cache ingest; no committed observation table contains all roughness/carrier inputs needed to reproduce the funnel. B3/B6/B7/B8 have neither `sha256_pack` nor an equivalent input/engine fingerprint; their metric-record SHA proves internal consistency, not which terrain/code generated it. B5 hashes do match. I cannot conclude the unfingerprinted results are current or stale from their numbers alone. | Commit a small deterministic, provenance-tagged observation fixture with complete inputs and hashes, or provide an explicit reproducible small-input acquisition process. Add input/code/profile/dependency fingerprints to every benchmark record and rerun on pack rebuild. Separate raw-data integration tests from an offline executable benchmark verification gate; do not silently count skips as full verification. |
| **B07 / SEV-2** | `docs/ENGINE_MATH.md:49`, `:53`; `src/marswalk/engine/plithogenic.py:72` | The conflict-amplified indeterminacy `mean(i)+c*abs(t_a-t_b)` executes as documented, but is placed under **Established mathematics** alongside the cited plithogenic operator. The primary source's neutrosophic indeterminacy construction averages fuzzy t-norm/t-conorm; it does not supply this truth-conflict boost. For the tested i values, product/probabilistic-sum averaging is `.25`; the code gives `.75` at c=1 because of the added truth disagreement. Thus arithmetic correctness does not establish the attribution. | Label the conflict boost explicitly as a project adaptation/proposal, cite the exact primary-source section for the T/F operators, and explain/calibrate the added I term independently. Do not imply that citation validates the safety behavior or calibrated probability interpretation. |
| **B08 / SEV-3** | `docs/ENGINE_MATH.md:99`, `:100` | Documentation reports funnel MAE **1.4792°** and says worse than 16 m with interval excluding zero, and indistinguishable from 64 m. Committed current records instead give **1.2468°**, 16 m difference CI **[-.0241,.3300]** (contains zero), and 64 m CI **[-.9515,-.1188]** (excludes zero). The JSON still honestly reports FAIL against the best fixed point MAE; the prose's significance conclusions are obsolete. | Generate or update these numbers and interval interpretations directly from current benchmark JSON, preserving the honest point-estimate FAIL against 16 m. |
| **B09 / SEV-3** | `src/marswalk/engine/pipeline.py:752`, `:754`, `:755`; `public_packs/jezero/v1/route.geojson:1646` | The Sol 700 note hardcodes measured tilt 20.33°, 1 m DTM peak 23.13°, and 64 m slope 12.65°. **12.65° is supported** by the exact waypoint validation sample **12.649°**, so I do not reject it merely because nearest-center C37 has 11.19°. The exact waypoint 1 m value is **18.562°** and C37 is **19.08°**; the peak 23.13° has no declared neighborhood/aggregation in this note or builder. I cannot verify that peak claim from the public evidence. | Format measured tilt and point-sampled slopes from the corresponding records. If a neighborhood peak is intended, publish its window, coordinate support, baseline definition and value. Distinguish waypoint samples, nearest-center cells and bbox-containing cells; do not substitute one for another without labeling. |
| **B10 / SEV-3** | `docs/ENGINE_MATH.md:51`; `src/marswalk/engine/funnel.py:241`, `:370` | Three identical valid triplets `T=.9,I=.1,F=.1` across 4/16/64 m return `entropy_bits=0` with configured `h_min=.7`. The pruning stop prevents reducing candidate entropy, but never enforces the floor on the starting pool. Positive I is instead guaranteed by the explicit minimum `.01` (example returns `.025`), not by a theorem that the initial entropy is positive. | State the precise conditional property: pruning does not cross below the floor when input entropy starts above it. Treat low initial diversity explicitly, and identify the numerical I minimum as a separate internal rule. If an unconditional entropy requirement is intended, validate it on entry. |

## ALGORITHM & BENCHMARK VERIFICATION

### Fusion boundaries and scope of safety claims

For `a=(.8,.1,.2)` and `b=(.3,.4,.6)`, I independently computed product T `.24`, probabilistic-sum T `.86`, probabilistic-sum F `.68`, product F `.12`, mean I `.25`, and truth disagreement `.50`:

| c | Expected and executed confidence `(t,i,f)` |
|---:|---|
| 0 | `(.24,.25,.68)` |
| .5 | `(.55,.50,.40)` |
| 1 | `(.86,.75,.12)` within floating point rounding |

The six-attribute legacy fusion function returns `NO_GO` for slope **20.01°** or walkback **2000.01 m** even with favorable delta geology and zero science-stop distance. Those tests verify the explicit legacy veto. That function is not the active carrier/funnel path in `pipeline.py`; B02 concerns the latter. Geology and science proximity are absent from the active five-carrier set, so I do not claim they directly compensate its hazards.

The primary source supports contradiction-weighted mixtures of t-norm and t-conorm; its neutrosophic indeterminacy treatment differs from the added truth-conflict term. I classify that term as an adaptation, not an algebra bug. See [Smarandache, sections II.3.4 and II.6](https://arxiv.org/pdf/1808.03948).

### M2 graph search, supercover and smoothing

I verified **8**, not 16, neighbor directions in both search implementations. For standard M2 nonnegative penalties, physical walking speed is clamped at `2.4000000000000004 km/h = .6666666666666667 m/s`. Therefore every edge costs at least its ground length divided by this speed; the ground-distance triangle inequality makes `h=d/v_max` admissible and consistent for heuristic weight 1. The speed bound is a property of the implemented adapted speed function, not a physiological validation of that function.

My scalar-edge Dijkstra implementation uses its own heap/distance loop and agrees with M2 A* on **30** deterministic 8×9 grids. I checked **17,280** directional edges against the scalar formula; maximum finite scalar/vector discrepancy was **8.526512829121202e-14 s**, with no invalid-edge disagreement. I do not extend this result to weighted heuristics greater than 1, invalid caller-supplied negative cost weights, continuous paths, or terrain below grid resolution.

My independent exact-rational Liang–Barsky cell-square oracle matched the M2 supercover cell sets on **625** directed segments including corner touches. The hardened M2 diagonal guard and nonnegative index checks work for these cases. The legacy `search_astar.py` failures in B03 are separate.

The reproducible smoothing counterexample is `probe_algorithms.py`, log key `cost_guard_true_line_integral_counterexample`. It records the full 6×7 risk matrix, metric steps `(9.485,10) m`, raw and smoothed paths, and cost counters. Raw path is `(0,0),(1,1),(2,2),(3,3),(4,4),(4,5),(5,6)`; smoothed path is `(0,0),(1,1),(2,2),(4,5),(5,6)`. All gradients/caution/blocked masks are zero. I integrated flat-cell cost density `(1+1.4*risk)/speed` over exact rational segment-square length fractions; zero-length corner touches contribute no cost. The guard accepted a shortcut with higher actual cost, as B05 quantifies.

### Packed route versus exported polygons

The packed `ROUTE-EVA-M2-OBSTACLE-AWARE` has **52** vertices. Independent segment/polygon clipping finds positive interior overlap with **OBS-JEZ-001** (about **82.144 m**) and **OBS-JEZ-013** (about **71.542 m**), hence **2/82** exported polygons. I checked all **51** segments against the decoded planner PNG with M2 supercover and found **zero blocked-cell crossings**.

The dependency's polygon exporter (`src/marswalk/engine/obstacles_m1.py:384`, `:416`) constructs axis-aligned **bounding rectangles** of connected blocked clusters, not exact outlines. These rectangles include free gaps. Thus polygon intersection is principally an exported-geometry semantic limitation here; calling it a demonstrated smoothed-route raster collision would be incorrect. This result does not prove sub-grid physical clearance or obstacle recall.

### Benchmark arithmetic and reproducibility limits

I independently counted **75 odd-sol tuning** and **72 even-sol test** waypoints in the pack's window, with no overlapping waypoint IDs. Parity partitioning does not itself make terrain samples spatially independent. The existing spatial CV record explicitly states that funnel parameters are frozen, not refit per fold, and that rover samples are presence-only; I retain those caveats.

The current manifest SHA-256 is `d93d3c3951359935f886c3029c67c71cfe63839f9608d79f0d91c2801fe944a5`. B5 evaluation and bootstrap reference exactly that hash. I rebuilt all **128** parameter combinations and independently recalculated every sweep metric-record SHA and the deterministic winner selection: **0 hash mismatches**, matching winner `p=3,tau_max=.2,h_min=.7,eps=.005`. This checks record self-consistency, not re-execution of terrain evaluations.

B6 records keep the same five carriers as the profile and report joint MAE change `1.3324−1.3293=.0031°`. Its `variance_index` is the normalized **input carrier T variance**, per `sobol_ablation.py:178`, not a Sobol attribution of output determination variance. B7 does run SALib on the **MAE output**, with p discretized to integers. The stored ST drift `.0001` across its two seeds is numerically consistent; p's ST confidence half-width is about `.2274`, so a small between-seed drift does not establish a narrowly known sensitivity index. [SALib's official Sobol API](https://salib.readthedocs.io/en/latest/api/SALib.analyze.html#SALib.analyze.sobol.analyze) defines these output-based indices and confidence results.

I could not rerun the actual B5 observation extraction/bootstrap, B3 terrain sweep, B6 reduction, B7 Sobol terrain evaluation, or B8 raw-window timing without the ignored input TIFF. I did not synthesize replacements or treat the saved JSON as fresh execution. B8's stored **1.5739 s / 384 cells** and the larger routing timing records remain historical machine measurements, not timings I measured in this audit. The synthetic M2 checks above have no performance pass/fail threshold, so concurrent audits do not affect their mathematical conclusions.

## TEST EXECUTION LOG

I used the shared offline harness with the existing installed audit environment and `PYTHONPATH=src`, `PYTHONUTF8=1`. `-o addopts=` removes the repository's duplicate quiet flag only; it does not change tests or assertions. The exact final arguments are:

```text
python shared/10_HANDOFFS/audit_evidence/run_pytest_offline.py --log shared/10_HANDOFFS/audit_evidence/part02/tests.log -- -q -ra --tb=short -o addopts= tests/test_b0_prefilter_and_g1.py tests/test_b1_funnel_and_attacks.py tests/test_b2_split_and_eval.py tests/test_b3_sweep_and_timing.py tests/test_b4_sobol_and_ablation.py tests/test_b5_pack_funnel_and_1m_note.py tests/test_phase3_route.py --basetemp=work/part02-pytest
```

The complete combined stdout/stderr and exit code are in [tests.log](audit_evidence/part02/tests.log). Literal local machine/user path prefixes are replaced by `<AUDIT_ROOT>`/`<USER_HOME>` and labeled; the unredacted raw log is retained locally outside the checkout. The captured terminal result is:

```text
45 passed, 5 skipped, 1 warning in 3.36s
EXIT_CODE=0
ELAPSED_S=3.665
```

The warning is a Starlette/httpx dependency deprecation. The skips are exactly:

```text
tests/test_b2_split_and_eval.py:38  B5 evaluation
tests/test_b3_sweep_and_timing.py:46  B3 terrain sweep
tests/test_b3_sweep_and_timing.py:72  B8 terrain timing
tests/test_b4_sobol_and_ablation.py:17  B7 Sobol sensitivity
tests/test_b4_sobol_and_ablation.py:36  B6 carrier ablation
Reason for all five: Requires gitignored local datalake/JEZ_hirise_soc_006_DTM_1m_window_2x2km.tif
```

My reproducible numerical evidence is [probe_algorithms.py](audit_evidence/part02/probe_algorithms.py), with complete executed output in [probes.log](audit_evidence/part02/probes.log), ending `EXIT_CODE=0`. It reads the frozen pack and executes isolated numerical cases; it writes no production artifacts. I ran `ruff check` and `ruff format --check` on this new evidence script successfully. The parent audit consolidates repository-wide verification and handoff; I made no journal entry, commit, push or phase-closure assertion.
