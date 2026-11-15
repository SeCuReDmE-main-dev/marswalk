# MarsWalk Phase 2b — Neutrosophic Gates & Plithogenic Multi-Attribute Terrain Engine (`docs/ENGINE_MATH.md`)

This document specifies the exact mathematical formulations implemented in `src/marswalk/engine/` for the 4-stage Martian terrain verification and EVA route planning pipeline.

---

## 1. Four-Stage Asynchronous Pipeline with Neutrosophic Evidence Gates

```text
INGEST ──[G0]──► CLASSIFY ──[G1]──► SEARCH ──[G2]──► PLAN ──[G3]──► PACK
                 (Plithogenic)      (2-Agent A*)    (xEVA Sortie)
```

Each gate $G_k$ ($k \in \{0, 1, 2, 3\}$) is an asynchronous function:
$$\text{gate}_k(\text{ctx}) \longrightarrow \text{GateVerdict}\langle T, I, F, \text{decision}, \text{reasons} \rangle$$
that evaluates **the quality of the evidence entering the next stage** (never conflated with terrain slope itself):

- **`BLOCK`** if $F > \tau_F$: Hard closed failure — pipeline halts immediately and nothing is written.
- **`HOLD`** if $I \ge \tau_I$ (and $F \le \tau_F$): High epistemic indeterminacy — the orchestrator automatically refines the scale or sampling window (up to `max_hold_retries = 2` retries). If $I \ge \tau_I$ persists after 2 retries, the gate transitions to `BLOCK`.
- **`PASS`** if $T \ge \tau_T$ and $F \le \tau_F$ and $I < \tau_I$.

Every gate evaluation is appended deterministically to `public_packs/jezero/v1/gate_log.jsonl`.

---

## 2. Multi-Scale DTM Slope & Scale Divergence (`INGEST` & `CLASSIFY`)

From the USGS Mars 2020 TRN HiRISE Digital Terrain Model (`JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif`, `1.0 m/px` on the Mars sphere $R = 3\,396\,190\text{ m}$), terrain slope at baseline $L \in \{1, 4, 16, 64\}\text{ m}$ is computed via centered finite differences over step $L$:

$$\frac{\partial z}{\partial x}\Big|_L = \frac{z(x + L/2, y) - z(x - L/2, y)}{L}, \qquad \frac{\partial z}{\partial y}\Big|_L = \frac{z(x, y + L/2) - z(x, y - L/2)}{L}$$

$$\theta_L(x, y) = \arctan\!\left(\sqrt{\left(\frac{\partial z}{\partial x}\Big|_L\right)^2 + \left(\frac{\partial z}{\partial y}\Big|_L\right)^2}\right) \cdot \frac{180}{\pi}$$

The **Scale Divergence** $\Delta\theta$ and **Scale Roughness** $\sigma_{\text{res}}$ are:
$$\Delta\theta(x, y) = \max_{L \in \{1,4,16,64\}} \theta_L(x, y) - \min_{L \in \{1,4,16,64\}} \theta_L(x, y)$$

**Strict Ground-Truth Separation Rule:** Perseverance's measured `rover_tilt_deg` ($N = 708$ stops) is **never** passed into `CLASSIFY`, `SEARCH`, or `PLAN`. It is used exclusively in `VALIDATION` to compute the Mean Absolute Error (MAE) and signed bias of $\theta_L$ at $L \in \{1, 4, 16, 64\}\text{ m}$.

---

## 3. Plithogenic Multi-Attribute Aggregation (`profiles/plithogenic_eva_v1.json`)

Each cell is evaluated across 6 pre-registered attributes $A_1, \dots, A_6$, where each attribute $A_m$ yields a Neutrosophic triplet $(t_m, i_m, f_m) \in [0, 1]^3$ and a contradiction degree $c_m = c(v_m, v_{\text{dom}, m}) \in [0, 1]$ with respect to its dominant ideal value $v_{\text{dom}, m}$.

### 3.1 Plithogenic Conjunction ($\wedge_p$), Disjunction ($\vee_p$), and Conflict-Aware Indeterminacy ($\oplus_p$)

Given two attribute states $(t_a, i_a, f_a)$ and $(t_b, i_b, f_b)$ with effective contradiction degree $c \in [0, 1]$:

1. **Plithogenic Truth Aggregation ($\wedge_p$):**
   $$t_a \wedge_p t_b = (1 - c)\cdot (t_a \cdot t_b) + c \cdot (t_a + t_b - t_a \cdot t_b)$$
2. **Plithogenic Falsehood Aggregation ($\vee_p$, dual of $\wedge_p$):**
   $$f_a \vee_p f_b = (1 - c)\cdot (f_a + f_b - f_a \cdot f_b) + c \cdot (f_a \cdot f_b)$$
3. **Conflict-Amplified Indeterminacy ($i_{a \oplus_p b}$):**
   $$i_{a \oplus_p b} = \min\!\left(1.0, \; \frac{i_a + i_b}{2} + c \cdot |t_a - t_b|\right)$$

### 3.2 Three Exact Hand-Calculated Verification Cases (Tested in `tests/test_engine_phase2b.py`)

- **Case 1 — Zero Contradiction ($c = 0.0$, pure algebraic t-norm / t-conorm):**
  Let $(t_a, i_a, f_a) = (0.80, 0.10, 0.10)$ and $(t_b, i_b, f_b) = (0.50, 0.20, 0.30)$ with $c = 0.0$:
  - $t = 1.0 \cdot (0.80 \cdot 0.50) + 0 = 0.40$
  - $f = 1.0 \cdot (0.10 + 0.30 - 0.03) + 0 = 0.37$
  - $i = \frac{0.10 + 0.20}{2} + 0.0 \cdot |0.80 - 0.50| = 0.15$
- **Case 2 — Full Contradiction ($c = 1.0$, boundary t-conorm / t-norm):**
  With the same inputs and $c = 1.0$:
  - $t = 0 + 1.0 \cdot (0.80 + 0.50 - 0.40) = 0.90$
  - $f = 0 + 1.0 \cdot (0.10 \cdot 0.30) = 0.03$
  - $i = \min(1.0, \, 0.15 + 1.0 \cdot |0.80 - 0.50|) = 0.45$
- **Case 3 — Partial Contradiction ($c = 0.5$, conflict increases indeterminacy):**
  With the same inputs and $c = 0.5$:
  - $t = 0.5 \cdot 0.40 + 0.5 \cdot 0.90 = 0.65$
  - $f = 0.5 \cdot 0.37 + 0.5 \cdot 0.03 = 0.20$
  - $i = 0.15 + 0.5 \cdot 0.30 = 0.30$

---

## 4. Lexicographic Non-Compensatory Safety Veto

Before plithogenic aggregation is allowed to assign a cell verdict:
1. If $\theta_{1\text{m}} > 20.0^\circ$ (NASA xEVA suit limit) **or** walkback distance $d_{\text{walkback}} > 2000.0\text{ m}$, the cell is immediately locked to **`NO_GO`** ($f \ge 0.90$).
2. **Science never compensates for safety:** even if $A_5$ (Delta target geology) and $A_6$ (Perseverance sample proximity) have $t = 1.0$, a safety veto unconditionally outputs `NO_GO`.

---

## 5. Two-Agent A* Path Search (`SEARCH`)

Grid search runs over the active window with edge traversal cost:
$$\text{cost}(u \to v) = d(u, v) \cdot \left(1 + \alpha \cdot \theta_{1\text{m}}(v) + \beta \cdot (1 - T(v)) + \gamma \cdot I(v)\right)$$
where $(\alpha, \beta, \gamma) = (0.12, 1.50, 1.20)$ and any cell with verdict `NO_GO` has $\text{cost} = +\infty$.
1. **Scout Rover Pass:** Validates a continuous traversable corridor obeying JPL rover limits ($\le 20^\circ$ bedrock, $\le 10^\circ$ sand/aeolian).
2. **Astronaut EVA Pass:** Computes the optimal crewed footpath within the rover-validated corridor obeying $d_{\text{walkback}} \le 2000\text{ m}$ and $\theta_{1\text{m}} \le 20^\circ$.
