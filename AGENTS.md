# Multi-Agent Engineering Governance (`AGENTS.md`)

This repository is engineered for seamless collaboration between human developers and multiple AI coding assistants (**Claude Code**, **Google Antigravity IDE**, **Gemini**, and **OpenAI Codex**). Every agent operating in this workspace MUST follow the rules below without exception.

---

## 1. Sacred Contract & Coordinate System Rules

1. **Frozen Contract (`v1.0.0`):**
   - The Pydantic v2 contract in [`src/marswalk/contracts/models.py`](src/marswalk/contracts/models.py), exported JSON Schemas in [`schemas/`](schemas/), and static pack files in [`public_packs/jezero/v1/`](public_packs/jezero/v1/) are **immutable** on `main`.
   - Any additive change requires a version bump (`v1.1.0`) and regeneration of `schemas/*.schema.json` + `public_packs/jezero/v1/manifest.json` SHA-256 digests.
2. **Single Geodetic Reference (`Mars Sphere R = 3,396,190 m`):**
   - All exported coordinates MUST use **planetocentric East longitude (`lon ∈ [-180, 360]`) and latitude (`lat ∈ [-90, 90]`) on the IAU 2015 / Mars Trek / USGS sphere of radius `R = 3,396,190.0 m`**.
   - Never apply an ellipsoidal flattening offset (`3,376,200 m`), and never mix local Mars 2020 mission easting/northing meters across products without explicit spherical conversion.
3. **Provenance Tag Discipline (`MEASURED | DERIVED | SIMULATED`):**
   - Every physical `Quantity` object MUST declare its `unit`, `tag` (`MEASURED`, `DERIVED`, or `SIMULATED`), and a valid `source_id` present in `SiteManifest.sources`.
   - Never present a `SIMULATED` astronaut EVA route or a `DERIVED` orbital slope as `MEASURED` telemetry.
4. **Clear UI Vocabulary (`confidence` & `GO | CAUTION | NO_GO`):**
   - In user-facing responses and frontend documentation, always refer to the 3-component uncertainty vector `{t, i, f}` as **`confidence`** (Verified Agreement `t`, Scale/Data Uncertainty `i`, Hazard Contradiction `f`) paired with the actionable verdict **`GO | CAUTION | NO_GO`**.

---

## 2. Branch & Directory Ownership (`Zero Merge Conflict`)

| Path / Branch | Primary Owner | Rule |
| :--- | :--- | :--- |
| `frontend/**` (`feat/ui`) | **Philippe Pierre (`@Maptop`)** | 100% Frontend Lead freedom (stack, UI components, brand name). Backend/middleware agents MUST NEVER modify `frontend/` beyond the initial `frontend/README.md` contract handoff. |
| `src/marswalk/contracts/**`, `schemas/**`, `public_packs/**` | **Shared Contract Layer** | Locked at `v1.0.0`. Verified by `pytest tests/test_contracts_and_schemas.py` and `tests/test_pack_integrity.py`. |
| `src/marswalk/middleware/**` (`feat/engine`) | **Jean-Sebastien Beaulieu (`@EbaAaZ`)** | Deterministic pack builder, SHA-256 verifier, and FastAPI query service. |
| `datalake/**` | **Local Ignored Cache** | Raw NASA GeoTIFFs / JSONs live here locally and are **never** committed to Git. |

---

## 3. Agent-Specific Configuration Directories

- **Claude Code (`.claude/`):** Commands (`/audit-pack`), settings, and contract-immutability rules.
- **Google Antigravity (`.antigravity/` & `.antigravity-ide/`):** Workspace governance rules, verification workflows, and IDE task definitions.
- **Gemini (`.gemini/`):** Code review styleguide and deterministic verification settings.
