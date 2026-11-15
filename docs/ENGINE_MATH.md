# MarsWalk Phase 2b v2 — Terrain Verification Engine Mathematics & Epistemic Tiers (`docs/ENGINE_MATH.md`)

Every mathematical formula, design choice, and claim in `src/marswalk/engine/` and `src/marswalk/bench/` is classified into three explicit epistemic tiers:

1. **Established mathematics** — standard mathematical, geodetic, or planetary terrain definitions with primary source citations.
2. **I propose** — domain heuristics, pre-registered thresholds, and multi-scale pruning choices designed for this Jezero EVA survival engine.
3. **Tested by** — executable `pytest` verification proving deterministic invariants, adversarial failure guards, and empirical rover benchmarks on disk.

---

## 1. Mars Geodesy, Finite-Difference Slopes, and Pixel-Scale Exclusion (`prefilter.py`, `dtm_ingest.py`)

### Established mathematics
- **Mars Equirectangular Projection (`ESRI:103885`, IAU 2015 sphere $R = 3\,396\,190\text{ m}$):**
  $$x = R \cdot \lambda_{\text{rad}}, \qquad y = R \cdot \varphi_{\text{rad}}$$
  and centered finite-difference slope at spatial baseline $L \in \{4, 16, 64\}\text{ m}$ on the `1.0 m/px` USGS Mars 2020 TRN HiRISE DTM (`SRC-USGS-HIRISE-DTM-1M`):
  $$\frac{\partial z}{\partial x}\Big|_L = \frac{z(x + L/2, y) - z(x - L/2, y)}{L}, \qquad \frac{\partial z}{\partial y}\Big|_L = \frac{z(x, y + L/2) - z(x, y - L/2)}{L}$$
  $$\theta_L(x, y) = \arctan\!\left(\sqrt{\left(\frac{\partial z}{\partial x}\Big|_L\right)^2 + \left(\frac{\partial z}{\partial y}\Big|_L\right)^2}\right) \cdot \frac{180}{\pi}$$
  - Sources (Section 7.D):
    - USGS Astrogeology, *HiRISE DTMs and Orthoimages* (vertical precision vs. baseline slope error: *"a 3-meter topographic error could turn flat terrain into a 9° slope over a 20-m baseline"*): https://stac.astrogeology.usgs.gov/docs/data/mars/hirise_dtms/
    - *Slope and Roughness Maps from HiRISE DTMs* (PlanetData 2023): https://www.hou.usra.edu/meetings/planetdata2023/pdf/7031.pdf
    - *Evaluating Stereo DTM Quality at Mars Rover Landing Sites* (Remote Sensing 2021): https://www.mdpi.com/2072-4292/13/17/3511
- **Local Fractal Dimension ($D = 3 - H$) and Detrended Surface Roughness:**
  - Isotropic variogram scaling $\gamma(h) = \frac{1}{2}\mathbb{E}[(z(\mathbf{u}+\mathbf{h}) - z(\mathbf{u}))^2] \propto h^{2H}$ yields Hurst exponent $H \in (0, 1)$ and local surface fractal dimension $D = 3 - H \in [2, 3]$.
  - Sources (Section 7.D):
    - NASA PGDA, *Lunar Slopes and Hurst Exponent* ($H \to D$ variogram relation): https://pgda.gsfc.nasa.gov/products/70
    - Taud & Parrot (2005), *Measurement of DEM roughness using the local fractal dimension*: https://journals.openedition.org/geomorphologie/622
    - Brožová et al. (2021), *Multiscale analysis of surface roughness*: https://nhess.copernicus.org/preprints/nhess-2021-85/nhess-2021-85-manuscript-version4.pdf
- **Human xEVA Operational Constraints ($20^\circ$ slope, $2.0\text{ km}$ walkback):**
  - NASA *xEVA System Concept of Operations*: https://www.nasa.gov/wp-content/uploads/2020/01/topic_1-_eva_lunar_surface_concept_of_operations.pdf

### I propose
- **Boolean Layer-1 Pre-Filter (`prefilter.py`):** Before any graded determination, crisp binary conditions are resolved immediately and never leak into indeterminacy $I$:
  1. Spatial baselines $L < 2 \times \Delta x_{\text{DTM}}$ (`1 m` on a `1.0 m/px` DTM) are excluded from the funnel (`slope_deg_by_baseline["1"]` is preserved in the v1 contract with `note: "below 2x DTM resolution: pixel-scale noise, excluded from the funnel"`).
  2. Out-of-bbox coordinates, unadmitted upstream `source_id`, `NaN`/`nodata` cells (`nodata > 20%`), and vertical cliffs ($\theta > 45^\circ \to \text{NO\_GO}$, reason `"cliff"`) exit immediately.

### Tested by
- `test_prefilter_rejects_baseline_below_2x_resolution_1m_on_1m_dtm` (`tests/test_b0_prefilter_and_g1.py`)
- `test_prefilter_nodata_and_nan_never_become_indeterminacy` (`tests/test_b0_prefilter_and_g1.py`)
- `test_prefilter_cliff_above_45_deg_is_direct_no_go` (`tests/test_b0_prefilter_and_g1.py`)
- `test_crs_roundtrip_and_mixed_sphere_attack` (`tests/test_b3_sweep_and_timing.py`)
- `test_baseline_1m_kept_with_note_and_excluded_from_funnel` (`tests/test_b5_pack_funnel_and_1m_note.py`)

---

## 2. Multi-Scale Fractal Pruning Funnel & Entropy Floor (`carriers.py`, `funnel.py`)

### Established mathematics
- **Discrete Shannon Entropy ($H(T)$ in bits) and Neutrosophic / Outlier-Robust Entropy Measures:**
  $$H(T) = -\sum_{b=1}^{B} p_b \log_2 p_b$$
  used as a diversity floor ($H(T) \ge H_{\min} > 0$) preventing survivor collapse to a zero-dispersion scalar ($I^* > 0$), alongside plithogenic contradiction-weighted aggregation:
  $$t_a \wedge_p t_b = (1 - c)(t_a t_b) + c(t_a + t_b - t_a t_b), \qquad f_a \vee_p f_b = (1 - c)(f_a + f_b - f_a f_b) + c(f_a f_b)$$
  $$i_{a \oplus_p b} = \min\!\left(1.0, \; \frac{i_a + i_b}{2} + c \cdot |t_a - t_b|\right)$$
  - Sources (Sections 7.A & 7.B):
    - Smarandache (2018), *Plithogeny, Plithogenic Set, Logic, Probability, and Statistics*: https://arxiv.org/abs/1808.03948
    - Ye (2014), *Single valued neutrosophic cross-entropy*: https://www.sciencedirect.com/science/article/pii/S0307904X13004642
    - Aydogdu (2015), *Entropy and Similarity of Interval Valued Neutrosophic Sets*: https://digitalrepository.unm.edu/cgi/viewcontent.cgi?article=1095&context=nss_journal
    - Qamar & Hassan (2020), *Entropy, Distance and Similarity of Q-neutrosophic Soft Sets*: https://pmc.ncbi.nlm.nih.gov/articles/PMC7513197/
    - *Neutrosophic Statistics with Outliers Data* (2025): https://distantreader.org/stacks/journals-ojs/ijaa/ijaa-4134.pdf
    - *Dual-Indeterminacy Neutrosophic Fusion*: https://www.americaspg.com/article/4466/pdf/stream
    - *Modified Plithogenic Sets in Criterion Reduction* (criterion ablation foundation): https://fs.unm.edu/NSS/5ModifiedPlithogenic.pdf

### I propose
- **Multi-Scale Persistence Pruning Funnel (`funnel.py`, `profiles/funnel_v1.json`):**
  - Given cell triplets $E = \{(\text{carrier}, L, T, I, F)\}$ across $L \in \{64, 16, 4\}\text{ m}$:
    1. At each step, identify $f^* = \arg\max F$ and $t^* = \arg\min T$.
    2. **Persistence safety rule:** if $F(f^*) \ge 0.50$ (or $T(t^*) \le 0.50$) persists across $\ge p$ neighboring scales for the same carrier, the hazard is structural (a real delta scarp, never pixel noise): pruning stops immediately and fixes `NO_GO` or `CAUTION`.
    3. Otherwise form $E' = E \setminus \{f^*, t^*\}$. Stop if $|E'| < 2$, pruned share $> \tau_{\max}$, or $H(T_{E'}) < H_{\min}$.
    4. Converge on $T_c = \frac{1}{2}(Q_{0.75}(T_E) + \max T_E)$ when $|T_c^{(k)} - T_c^{(k-1)}| < \varepsilon$, bounded strictly to $\le \lfloor |E|/2 \rfloor$ iterations.
- **Stage Evidence Gates (`gates.py`, `profiles/gates_v1.json`):**
  - Discrete stage gates `G0..G3` emit `PASS | HOLD | BLOCK` over pipeline stage quality only; `G1` never fabricates terrain cell confidence from validation error.

### Tested by
- `test_funnel_terminates` (B1: iterations $\le |E| // 2$, `tests/test_b1_funnel_and_attacks.py`)
- `test_deterministic` (B2: identical SHA-256 across 3 runs, `tests/test_b1_funnel_and_attacks.py`)
- `test_persistent_hazard_never_pruned` (B3: $50/50 = 100\%$ survival, `tests/test_b1_funnel_and_attacks.py`)
- `test_single_scale_spike_pruned` (B4: $\ge 95\%$ single-scale spike pruning, `tests/test_b1_funnel_and_attacks.py`)
- `test_entropy_floor` (B9: $I^* > 0$ everywhere, `tests/test_b1_funnel_and_attacks.py`)
- `test_p1_rejected`, `test_tau_max_1_rejected`, `test_h_min_zero_and_eps_zero_rejected` (`tests/test_b1_funnel_and_attacks.py`)
- `test_g1_does_not_emit_terrain_tif` (`tests/test_b0_prefilter_and_g1.py`)
- `test_plithogenic_hand_calculated_cases_and_boundary_identities` (`tests/test_engine_phase2b.py`)

---

## 3. Disjoint Rover Validation, Sweet Spot (B3/B5), Sensitivity (B7), and Carrier Reduction (B6)

### Established mathematics
- **Strict Train/Test Disjoint Evaluation & Saltelli-Sobol Variance Decomposition:**
  - Rover chassis tilt (`MEASURED` IMU inclination from `M20_waypoints.json`, https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json ; proxy formulation in *Learning to Drive on Mars*, https://arxiv.org/html/2609.24952v1) is partitioned into **odd sols** (`sol % 2 == 1`, $n_{\text{tune}} = 75$ in window) for hyperparameter tuning/ablation and **even sols** (`sol % 2 == 0`, $n_{\text{test}} = 72$ in window) for held-out test reporting.
  - Global variance-based sensitivity indices ($S_1, S_T$) are computed via Saltelli sampling in `SALib` (https://salib.readthedocs.io/).

### I propose
- **Sweet-Spot Hyperparameters (`profiles/funnel_v1.json`, `bench/results/b3_sweep.json`):**
  - Selected across 128 combinations ($p \in \{2,3\} \times \tau_{\max} \in \{0.1,0.2,0.3,0.4\} \times H_{\min} \in \{0.3,0.5,0.7,1.0\} \times \varepsilon \in \{0.005,0.01,0.02,0.05\}$) strictly on odd sols subject to `B3 = PASS` and `B9 = PASS`:
    $$p = 3, \quad \tau_{\max} = 0.20, \quad H_{\min} = 0.70\text{ bit}, \quad \varepsilon = 0.005$$
- **Carrier Reduction Decision (`bench/results/b6_ablation.json`):**
  - **I keep 5 carriers (`I_scale`, `I_slope`, `I_rough`, `I_diverge`, `I_constraint`) because** each contributes $\ge 0.05$ of normalized determination variance across odd sols, whereas the 5 pruned carriers (`I_source`, `I_coverage`, `I_texture`, `I_uncertainty`, `I_fractal`) each have variance index $< 0.05$ (binary `source` and `nodata` checks are already enforced by `prefilter.py`) and their joint removal shifts odd-sol MAE by only $+0.0031^\circ$ ($1.3293^\circ \to 1.3324^\circ \le 0.10^\circ$) while keeping `B3` and `B9` at `PASS`.
- **Empirical Held-Out Even-Sol Benchmark (`bench/results/b5_eval.json`, $n_{\text{test}} = 72$) & Timing (`b8_timing.json`):**
  - Held-out even sols: `mae_funnel = 1.4792°` vs `mae_fixed_4m = 1.7127°` and `mae_fixed_64m = 1.7965°` (beats both `4 m` and `64 m` fixed baselines; honest disclosure: fixed `16 m` point MAE is `1.1437°` on benign rover stops because the ~3 m rover chassis + stop localization aligns with 16 m smoothing, whereas the funnel conservatively retains steeper 4 m slopes when hazards persist).
  - Empirical wall-clock runtime on the `2 × 2 km` HiRISE `1.0 m/px` window (`384` cells) is recorded in `bench/results/b8_timing.json` without claiming any asymptotic complexity class.

### Tested by
- `test_split_is_disjoint` and `test_b5_eval_writes_honest_even_sol_metrics` (`tests/test_b2_split_and_eval.py`)
- `test_b3_128_combo_sweep_selects_valid_odd_sol_sweet_spot` and `test_b8_2x2km_window_timing_recorded_without_big_o` (`tests/test_b3_sweep_and_timing.py`)
- `test_b7_sobol_sensitivity_two_seeds_stable` and `test_b6_leave_one_out_ablation_and_reduction_rule` (`tests/test_b4_sobol_and_ablation.py`)
- `test_hazard_grid_is_strictly_independent_of_rover_tilt_deg` (`tests/test_pack_integrity.py`)
- `test_b5_pack_sha256_matches_b5_eval_record` (`tests/test_b5_pack_funnel_and_1m_note.py`)
