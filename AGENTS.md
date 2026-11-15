# Multi-Agent Engineering Governance (`AGENTS.md`)

I (Jean-Sébastien Beaulieu) build this repository with several AI coding assistants (**Claude Code**, **Google Antigravity IDE**, **Gemini**, **OpenAI Codex**). The frontend belongs to Philippe Pierre. Every agent working here MUST follow the rules below without exception.

---

## 0. Where the project stands (2026-11-15)

| Phase | Scope | State |
|---|---|---|
| 1 | Data contract `v1.0.0`, signed static pack, FastAPI middleware | Done, on `main` |
| 2 | Multi-scale terrain engine (funnel, gates, A*), real HiRISE 1 m DTM | Done, on `main` |
| 3 | Contract `v1.1.0`, 40 × 40 engine grid (1,600 cells of ~48 m), `cos φ` ground metres, RF / radiation / metabolic / AOA layers, spatial-block CV | Done, audit `VERIFIED`, merged on `main` (`79064e3`) |
| 5 | Fail-safe route evaluation, operator safe mode, repo hygiene, `demo-stable` tag | Done on `feat/phase3`, not merged yet, not yet audited by Claude |
| 4 | Obstacle-aware route planner (`/plan-route`, `obstacles.geojson`, modules M1–M6) | **In progress, not shipped.** Nothing from Phase 4 is in the pack or the API yet |

Phase 5 was run before Phase 4 on purpose: the safety guards had to exist before a planner could build on them.

---

## 1. Sacred Contract & Coordinate System Rules

1. **Additive contract (`v1.1.0`):**
   - The current contract is `CONTRACT_VERSION = "1.1.0"`. Models accept `Literal["1.0.0", "1.1.0"]`, so every `v1.0.0` document stays valid.
   - The Pydantic v2 contract in [`src/marswalk/contracts/models.py`](src/marswalk/contracts/models.py), the JSON Schemas in [`schemas/`](schemas/) and the pack in [`public_packs/jezero/v1/`](public_packs/jezero/v1/) change **only additively** (new optional fields). Never rename or remove a field.
   - Any contract change requires regenerating `schemas/*.schema.json` (`marswalk-cli export-schemas`) and the pack (`marswalk-cli build-pack`), then `marswalk-cli verify-pack`.
2. **Single Geodetic Reference (`Mars Sphere R = 3,396,190 m`):**
   - All exported coordinates MUST use **planetocentric East longitude and planetocentric latitude on the IAU 2015 / Mars Trek / USGS sphere of radius `R = 3,396,190.0 m`**.
   - The HiRISE DTM is equirectangular with a 0° standard parallel: an E-W pixel is `cos φ` ground metres (`0.9485 m` at Jezero). Use `dtm_ingest.ground_step_x_m(lat)` for every E-W distance, gradient or lag.
   - Never apply an ellipsoidal flattening offset, and never mix Mars 2020 local easting/northing metres across products without explicit spherical conversion.
3. **Provenance Tag Discipline (`MEASURED | DERIVED | SIMULATED`):**
   - Every physical `Quantity` MUST declare `unit`, `tag` and a `source_id` present in `SiteManifest.sources`.
   - Never present a `SIMULATED` astronaut route or a `DERIVED` orbital value as `MEASURED`.
   - An uncalibrated heuristic is never presented as a published model. Example: `rock_cfa_pct` is a 1 m DTM roughness proxy; it feeds the uncertainty `i` only and never decides a verdict.
   - A data layer that is absent is reported as `UNAVAILABLE` with `indeterminacy_i = 1.0` (see `hazard_grid.external_layers_status`), never filled with an invented value.
4. **Clear UI Vocabulary (`confidence` & `GO | CAUTION | NO_GO`):**
   - Refer to the vector `{t, i, f}` as **`confidence`** (Verified Agreement `t`, Scale/Data Uncertainty `i`, Hazard Contradiction `f`), always paired with the verdict **`GO | CAUTION | NO_GO`**.

---

## 2. Safety invariants (Phases 3 and 5)

1. **Never `GO` on missing or bad data.** A required value that is `None`, `NaN` or `Inf`, or an internal error, returns HTTP 200 with `verdict = "NO_GO"` and a reason starting with `FAIL_SAFE:`.
2. **Operator stop.** `MARSWALK_SAFE_MODE=1` (read on every request) forces route evaluation to `NO_GO` and shows `"safe_mode": true` on `GET /health`. Static map endpoints stay available. See [`SECURITY.md`](SECURITY.md).
3. **`spe_alert = true` is a global abort.** It always gives `NO_GO`. Terrain shelter never compensates it.
4. **More dust, more payload or an SPE never improves a verdict** (monotonicity, tested).
5. **No route outside the grid is ever `GO`**, and a segment is checked on every cell it touches (supercover), not only at its vertices.
6. **Measured rover tilt is ground truth, never an input.** The prefilter, carriers, funnel, gates and A* must not read `rover_tilt_deg`. It is used only to validate.
7. **No threshold without a source.** A new number that changes a verdict cites a primary source, or is tagged as an internal margin and documented.

---

## 3. Verification gate (before saying "done")

```bash
ruff check . && ruff format --check .
python -m pytest -q --tb=short
PYTHONPATH=src python -m marswalk.middleware.cli verify-pack
```

- 100 % green, 0 skipped, 0 xfailed. Never weaken a test threshold to make it pass. Never edit an oracle test (`tests/test_phase3_route.py`, section A).
- After a pack rebuild, rerun the benchmarks so `sha256_pack` in `bench/results/*.json` matches `manifest.json`.
- A phase is closed only when the hostile audit file `.claude/audits/LAST_CLAUDE_VERDICT.md` says `STATUS: VERIFIED (0 REJECTED / 0 HALF-DONE)`.

---

## 4. Branch & Directory Ownership (`Zero Merge Conflict`)

| Path / Branch | Owner | Rule |
| :--- | :--- | :--- |
| `frontend/**` | **Philippe Pierre (`teammate`)** | Full frontend freedom (stack, UI, brand name). Backend agents MUST NEVER modify `frontend/`. |
| `src/marswalk/contracts/**`, `schemas/**`, `public_packs/**` | **Shared contract layer** | Additive only (`v1.1.0`). Guarded by `tests/test_contracts_and_schemas.py` and `tests/test_pack_integrity.py`. |
| `src/marswalk/engine/**`, `src/marswalk/middleware/**`, `bench/**` | **Jean-Sébastien Beaulieu (`jean`)** | Terrain engine, pack builder, SHA-256 verifier, FastAPI query service, benchmarks. |
| `datalake/**` | **Local ignored cache** | Raw NASA / USGS files stay local and are **never** committed. |
| Feature work | `feat/<phase>` branches | Never commit feature work directly on `main`. Never push or merge without Jean-Sébastien's approval. |

Commit messages are written in the first person singular ("I add…", "I fix…").

---

## 5. Agent-Specific Configuration Directories

- **Claude Code (`.claude/`):** commands, settings, contract-immutability rules, hostile audits.
- **Google Antigravity (`.antigravity/` & `.antigravity-ide/`):** workspace rules, verification workflows, IDE tasks.
- **Gemini (`.gemini/`):** code review styleguide and deterministic verification settings.
