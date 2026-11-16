# Part 03 — xEVA human, RF, radiation, camera and MEDA audit

## Reviewer, target and independence

I am **OpenAI Codex**, reviewing commit `e38ceba70e9c6273cf35233d3255cd912a7a4809` in a separate reviewer context on 2026-11-15. I am not NASA staff or Antigravity, and I do not issue NASA certification, human-rating approval, or an NPR/NASA-STD compliance determination. The requested NASA IV&V checklist supplies the review topics, not institutional authority.

I used a clean checkout on the same Windows machine and reused the installed dependency virtual environment. This is independent reviewer context and cache isolation, not Philippe's independent-machine experiment. I verified imports resolve to this checkout. `datalake/` contained only tracked `.gitkeep` and `README.md`; I downloaded no raw data. I changed no backend, frontend, pack, schema, test, or Git reference. I followed the current authorization to produce reports and evidence without journal impersonation, commits, pushes or handoff acknowledgments.

I inspected the six requested engine modules and both requested test files. I read the pack and the minimal production call sites needed to distinguish helper defects from API containment.

## EXECUTIVE VERDICT

**REJECTED for the claimed RF model fidelity; incomplete physiology/provenance verification.** The successful test process is insufficient to close the repository's verification gate because it skips one required DTM test. Two synthetic RF counterexamples produce an optimistic `GO`. I have not established an unsafe route on the actual Jezero terrain, which cannot be independently reconstructed here without the omitted DTM.

| Classification | Count | Meaning in this report |
|---|---:|---|
| SEVERITY 1 — REJECTED / F | 2 | Reproducible optimistic RF model outputs contradict the stated model/resolution |
| SEVERITY 2 — HALF-DONE / I | 8 | Wrong scientific values, provenance defects, unsupported assumptions, helper validation gaps, or omitted verification |
| VERIFIED / T | 11 | The bounded assertion groups V01–V11 below; these do not certify the surrounding models |
| SEVERITY 3 | 0 | Minor prose mistakes are included with their substantive finding |

The finding counts are individual issues, not test counts. The verified counts are explicitly enumerated below; I do not combine them into a misleading assurance percentage.

## TEST EXECUTION LOG

I ran the unchanged requested files with the shared audit harness, `PYTHONPATH=src`, `PYTHONUTF8=1`, and an isolated `work/part03-pytest` basetemp. The harness denied remote DNS/socket connections while permitting localhost for Windows TestClient. It did not replace network responses, change assertions, manufacture a cache, or remove skip markers.

```text
python shared/10_HANDOFFS/audit_evidence/run_pytest_offline.py \
  --log shared/10_HANDOFFS/audit_evidence/part03/tests.log -- \
  -q -ra --tb=short --basetemp=work/part03-pytest \
  tests/test_phase4_obstacles_and_routing.py tests/test_phase6_hardening.py
```

I used the existing virtual environment interpreter; `python` above is the portable command spelling. Environment versions were Python 3.12.10, pytest 9.2.0, NumPy 2.5.4, SciPy 1.18.1, Pydantic 2.14.3, FastAPI 0.163.1, Pillow 13.0.0, Hypothesis 6.170.15 and SALib 1.6.0.

- Final result: **16 passed, 1 skipped, 0 failed, exit 0**, elapsed 2.961 seconds. The double quiet configuration suppresses the ordinary passed-count summary; the log preserves the progress marks and exact skip. No performance assertion failed during concurrent reviews, so I make no isolated-machine timing claim.
- Exact test stdout/stderr and exit code are retained locally in `../ivv-raw-logs/part03-tests.log`. The shareable [test log](audit_evidence/part03/tests.log) changes only local checkout/home prefixes, as its header declares.
- My initial run had three fixture setup errors because the `work/` parent of basetemp did not exist. I preserved the [initial environment error log](audit_evidence/part03/tests-initial-basetemp-error.log), created that parent, and reran. Those errors are reviewer setup errors, not product defects.
- The skip is `tests/test_phase4_obstacles_and_routing.py:111`, reason `Requires gitignored local datalake/ DTM GeoTIFF` (F03-10).
- The independent [physics probe](audit_evidence/part03/physics_probe.py) completed with exit 0, writing [JSON results](audit_evidence/part03/physics-probe.json) and [stdout-equivalent log](audit_evidence/part03/physics-probe.log); its captured [stderr](audit_evidence/part03/physics-probe.stderr.log) is empty. Ruff check and format check passed for this added script.

## FINDINGS TABLE

All locations below are repository-relative at the audited commit. Suggested fixes are recommendations only; I implemented none.

| ID | Severity and location | Mathematical/code proof and scope | Surgical suggested fix |
|---|---|---|---|
| F03-01 | **SEV-1** — `src/marswalk/engine/eva_human_rf.py:75`, `:301` | The routine computes the maximum individual knife-edge parameter and applies only `J(nu)`. It omits the Bullington transition correction in ITU-R P.526-16 §4.5.1 eq.57 and the transhorizon equivalent-point construction, eqs.53–56. For `[0,0,0]`, 1,000 m, default antenna heights, the code gives `nu=-0.248450`, **3.9315 dB / GO**. The §4.5.1 correction gives **8.748039 dB / NO_GO** at the same 6 dB budget. This is a model-level false acceptance relative to the named Bullington model, not proof of a current Jezero route failure. [ITU primary recommendation, pp.28–29](https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.526-16-202511-I%21%21PDF-E.pdf). | Implement the stated Bullington algorithm including the appropriate path cases and correction; separately validate any Mars adaptation. Alternatively explicitly expose a single-edge heuristic with uncertainty and prevent its optimistic bound from establishing communication safety. Add this independent counterexample to a focused verification test. |
| F03-02 | **SEV-1** — `src/marswalk/engine/eva_human_rf.py:143` | Rounded point sampling at 8 m can miss a resolved 4 m formation. A 3×1,001 flat synthetic 1 m DTM with columns `499:503` raised 20 m gives sampled peak **0 m**, **GO / 3.9963 dB**, versus all 1 m samples **NO_GO / 18.4359 dB**. The production pack builder calls this helper with `step_m=8.0` (`pipeline.py:413`). I cannot quantify occurrence in the real terrain without its DTM. | Sample all intersected native DTM pixels, or conservatively retain interval maxima with physical sample distances. Mark insufficient coverage unavailable. Test ridges shifted through every sampling phase. |
| F03-03 | **SEV-2** — `src/marswalk/engine/kinematics_m4.py:30`, `:83`; `tests/test_phase4_obstacles_and_routing.py:331` | The alleged published measured table contains wrong values; nine of thirteen directly comparable published anchors disagree. At grade `+0.10`, code **3.92** vs published **4.68 J/kg/m**. Tests check only four matching anchors. The actual source is **Table 2**, not Table 1. The quintic is implemented correctly, but its docstring at `:107` incorrectly says 1.1325 at −10%; execution yields **1.127125**. | Transcribe Table 2 with source/page evidence, identify interpolated points as derived, correct the table reference and quintic prose, and verify every published anchor rather than four selected values. Keep this diagnostic separate from operational O2. |
| F03-04 | **SEV-2** — `src/marswalk/engine/kinematics_m4.py:63`, `:169`; `src/marswalk/engine/eva_human_rf.py:187`, `:200` | `norcross_tag` is unconditionally `MEASURED`, including arbitrary body/suit masses, payload scaling, downhill adaptation and extrapolation. A grade 0.70, 80 kg body, 104 kg suit, 60 kg payload case produces **3,047.98 W / MEASURED**. No measurement of that input is established. The operational model uses 70 kg by default, not the prompt's 75/80 kg. It retains a 0.32 g anchor for Mars while 0.3794 scaling occurs only in comparative Pandolf diagnostics. | Tag transformed predictions `DERIVED`, preserve source observations separately, expose validity domain and reference body/suit/gravity, and qualify the Mars extrapolation. Do not relabel a 70 kg scenario as the source cohort mean. |
| F03-05 | **SEV-2** — `src/marswalk/engine/eva_human_rf.py:45`, `:226` | At zero grade, payloads **0, 60, 120 kg** all produce the same **695.833333 W** contingency burn. Default O2 margins decline only because the assumed preceding three hours become more costly. Setting nominal elapsed time to zero makes all three margins exactly **208.068864 min**. Thus the monotonicity test does not verify payload sensitivity of contingency walkback. The 2,505 kJ/h conversion is correct, but the primary source calls it an average of a simulated lunar walk, not a validated universal Mars/2 km/h minimum. [NASA OCHMO-TB-050, p.6](https://www.nasa.gov/wp-content/uploads/2025/09/ochmo-tb-050-spacesuits.pdf). | State and justify the floor as an internal adaptation, document what loads it already includes, and validate a conservative payload treatment above that baseline. Add a check isolating return consumption from nominal elapsed consumption. Expose the hardcoded 3 h/2% nominal scenario instead of implying route-integrated consumption. |
| F03-06 | **SEV-2** — `src/marswalk/engine/radiation_svf.py:31`; `public_packs/jezero/v1/eva_constraints.json:81` | The code and pack attribute **0.67 mSv/day** to Hassler 2014, while that paper reports **0.64 ± 0.12 mSv/day**: **27.916667** vs **26.666667 uSv/h**. Gale proxy attribution is explicit and correct; exact numeric source attribution is not. [Hassler primary article, Table 1, p.3](https://www.scienceintheclassroom.org/sites/default/files/research-papers/1244797.full_.pdf). | Use the cited value with its temporal/site scope or cite the actual source of 0.67 and document any deliberate conservative margin. Reconcile the pack/builder/docs through the contract-prescribed regeneration workflow, without editing a frozen pack alone. Establish a source and detector medium for the separate 0.233 mGy/day constant. |
| F03-07 | **SEV-2** — `src/marswalk/engine/meda_envelope.py:95` | File existence alone switches the layer to `available=True`, `MEASURED`, `i=0.05`; the loader never reads CSV bytes or verifies measurements. The probe's **zero-byte** `MEDA_env_summary.csv` receives that status. The actual audited pack correctly has the layer unavailable. | Parse and validate content, units, time coverage, calibration/quality flags and finite values before returning available. Empty/malformed data must retain `UNAVAILABLE`, `i=1.0`, with a diagnostic reason. |
| F03-08 | **SEV-2** — `src/marswalk/engine/meda_envelope.py:37`; supporting caller `src/marswalk/middleware/query_service.py:872` | Dust thresholds 0.50 and 1.00 are hardcoded and change verdicts; I found no primary human EVA threshold source or explicit internal-margin designation. A MEDA data-source citation does not establish a human thermal/visibility safety limit. The API reason nevertheless calls 1.00 a MEDA safety threshold. Boundary behavior is verified, the claimed safety basis is unverified. | Designate and document internal scenario margins, with rationale and limitations, or supply the precise primary safety requirement and applicability. Correct the response explanation so instrument provenance is not presented as human-limit validation. |
| F03-09 | **SEV-2** — `src/marswalk/engine/eva_human_rf.py:92`; `src/marswalk/engine/radiation_svf.py:88`; `src/marswalk/engine/meda_envelope.py:83` | Three helper probes fail open: all-NaN RF profile produces **nu=−1e9 / 0 dB / GO**; all-NaN DTM produces **SVF=1.0**; dust NaN produces **GO**. I verified `PlanRouteRequest` rejects NaN/Inf/negative dust, so this is **not** evidence of a client/API dust bypass. Core RF/SVF ingestion still requires its own finite-data proof. | Validate finite inputs and profile/DTM coverage at scientific function boundaries; return explicit unavailability or raise a domain exception contained as fail-safe by the caller. Add helper tests and preserve existing API rejection. |
| F03-10 | **SEV-2** — `tests/test_phase4_obstacles_and_routing.py:111` | The raw-DTM-dependent specificity/recall test skips in the required cache-free environment. Exit 0 therefore does not satisfy `AGENTS.md`'s 100% green, zero-skipped rule. | Supply a provenance-preserving redistributable fixture or an independent equivalent check and explicitly require the real-data check in its designated environment. Do not remove the test or weaken thresholds. Until then record this assurance gap. |

## INDEPENDENT PHYSICS VERIFICATION

I recomputed the following in the attached script, using independent arithmetic or numerical quadrature before comparing to module outputs. Recomputing an implemented formula verifies arithmetic, not its human or flight applicability.

| Output | Independent result | Assessment |
|---|---:|---|
| Grade `−0.10` converted by `atan` | **−5.7105931375 deg** | Angle and fractional grade are separated correctly |
| Terrain angle 20 deg converted by `tan` | **0.3639702343** | Not 20% grade |
| Minetti quintic at grade −0.10 | **1.127125 J/kg/m** | Implemented coefficients match; docstring number is stale |
| Pandolf reference, W=75 kg, L=104 kg, v=0.625 m/s, eta=1, g ratio=0.3794 | **343.65 W** all terms scaled; **413.46 W** unscaled standing term | Algebra matches the declared comparative conventions; both are `DERIVED` |
| O2 zero-payload nominal power at 2% grade | **385.987 W** | A fixed scenario, not actual route integration |
| 1 km return, flat, 0 kg payload | **432.779606 g** total O2 used; **108.220730 min** margin | Includes nominal 3 h and ingress 0.5 h |
| Same return, 60 kg payload | **529.603786 g**, **75.600188 min** | Return power remains at floor |
| Same return, 120 kg payload | **626.427966 g**, **42.979646 min** | Return power remains at floor |
| Finite 10 m wall, 2 m standoff, 20 m width | Quadrature **0.4114312855**, analytic rounded **0.411431** sky occlusion | Independent horizon integration agrees |
| Infinite wall with same height/standoff | **0.437167** occlusion | Correct finite/infinite ordering and hemispherical limit |
| Occlusion 0.35 × eta 0.20–0.26 | **7.0–9.1%** GCR reduction | Correct arithmetic of an adapted extrapolation; not an SPE prediction |
| Wavelength, `299792458/414200000` | **0.7237867166 m** | Correct |
| 1 km link midpoint first Fresnel radius | **13.4516422470 m** | Correct |
| Mars midpoint bulge, `500×500/(2×3396190)` | **0.0368059502 m** | Correct |
| Clearance `0.60 F1` | **nu=−0.8485281374**, **0 dB** single-edge loss | Correct parameter identity and zero-loss branch |
| Flat Tobler xEVA speed | **2.014696850 km/h** | Documented 2.0 baseline is approximate; 2 km return takes **0.992705181 h** |

The Minetti source values are experimental terrestrial treadmill costs; I do not treat their agreement as suited Mars validation. The exact mismatches below come from the original article's Table 2, printed p.1042. I accessed an article reproduction on a third-party host because the publisher page presented an anti-bot barrier. [Original DOI](https://doi.org/10.1152/japplphysiol.01177.2001), [article PDF mirror](https://runscribe.com/wp-content/uploads/power/Minetti2002.pdf).

| Grade | Published walking mean | Code |
|---:|---:|---:|
| −0.40 | 3.23 | 2.97 |
| −0.35 | 2.65 | 2.55 |
| −0.30 | 2.18 | 2.09 |
| −0.20 | 1.30 | 1.22 |
| +0.10 | 4.68 | 3.92 |
| +0.20 | 8.07 | 7.36 |
| +0.30 | 11.29 | 11.95 |
| +0.35 | 12.72 | 14.43 |
| +0.40 | 14.75 | 15.93 |

For Norcross I checked the primary report rather than accepting an attribution string. Its Table 1 reports a six-person mean body mass **80.7 kg**. Pages 70–71 describe a preliminary model using speed, grade, dimensions, pressure and suit mass, and limit its generalization. The code's 70 kg interpolation/payload model is an adaptation; I did not independently validate the five VO2 anchors by digitizing the report's graph. The 121 kg test suit and maximum tested 0.32 g condition are supported; 0.3794 g is outside that tested range. [Norcross NASA/TP-2010-216125 record and downloadable report](https://ntrs.nasa.gov/citations/20110003409).

The eta=0.20 coefficient reproduces the observed 19%-occlusion / 3.8%-dose-reduction ratio, but extending one observed geometry linearly to other walls and Jezero remains an adaptation. I have no independent Jezero dosimeter or radiation-transport calculation. [Ehresmann 2021 primary study, §3.2](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2021JE006851), [Guo 2021 primary article record and full text](https://elib.dlr.de/143278/).

## Verified checklist predicates and limits

| ID | Bounded predicate I verified | Evidence/limit |
|---|---|---|
| V01 | Degree/grade conversion uses tangent and inverse tangent | Numerical checks above, finite ordinary inputs only |
| V02 | The Minetti quintic implements the stated polynomial | Independent coefficient evaluation; table defect remains F03-03 |
| V03 | The two Pandolf diagnostic conventions evaluate their declared algebra | Independent W/L/v/g calculation; downhill Minetti input inherits F03-03 |
| V04 | O2 W→L→g conversion and nominal/return/ingress bookkeeping are dimensionally consistent | Independent mass budget; the scenario and floor are not physiological validation |
| V05 | Finite wall solid-angle occlusion agrees with independent quadrature | One finite geometry plus infinite-wall limit; no claim of measured dose protection |
| V06 | 35% occlusion produces 7.0–9.1% under the declared eta band | Arithmetic verified; linear extrapolation remains unvalidated |
| V07 | SPE is a global `NO_GO`; refuge routing weight is zero | Phase4/phase6 tests plus direct service probe returned `NO_GO` |
| V08 | Wavelength, F1, Mars bulge, antenna endpoint order and 60% clearance identity are correct | 3.0 m rover endpoint, 1.8 m suit endpoint; assumed heights are not verified flight hardware measurements; F03-01 remains |
| V09 | RF is described and computed as direct rover/suit communication, not orbital relay | Fixed Sol 413 origin call chain; pack count **1,347 NO_GO / 1,600 = 84.1875%**, 13 CAUTION, 240 GO; geometry cannot be rebuilt without DTM |
| V10 | Camera offline fallback does not fetch or create its cache directory; retired service pattern is absent from source | Requested tests passed; direct probe returned `offline_unavailable`; **708** populated panorama URLs and **zero** `mmgis-maps` URLs. This proves string/content checks, not HTTP liveness of every URL |
| V11 | MEDA missing-file state and implemented sentinel/calibration filters behave as declared | Missing layer `UNAVAILABLE/i=1`; finite 700 retained, NaN/Inf/sentinel rejected; WS switches at sol36, RHS at sol63. Actual pack retains unavailable state; empty-file failure is F03-07 |

The MEDA archive's own README supports rejecting wind data before sol36 and humidity before sol63. I did not find a human EVA dust threshold or independently confirm the exact `9999999999` convention in an individual archived PDS4 label during this no-raw-download review; the script verifies its implemented behavior only. [MEDA primary archive README](https://atmos.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/readme.txt), [instrument RDR SIS](https://atmos.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/document/meda_env_rdr_sis.pdf).

I observed five cells marked partial topographic refuge, so the flag is nonempty. That does not validate the heuristic toe-pixel search as a true maximum, the internal 0.22 classification threshold as a human safety threshold, or fast egress to a real habitat. No terrain shelter is credited against an SPE in the inspected functions.

I leave phase closure and the existing hostile-audit status untouched. Full repository gates and consolidation belong to the parent audit run; this report establishes only the stated slice results and evidence.
