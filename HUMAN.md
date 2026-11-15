# Human Team & Collaboration Charter (`HUMAN.md`)

**Event:** 2026 NASA International Space Apps Challenge (48-Hour Sprint)  
**Challenge:** *Interplanetary Survival Guide: Martian Map*  
**Study Site:** Jezero Crater, Mars (`18.38° N, 77.58° E` — Mars 2020 Perseverance Landing & Traverse Region)  
**Engine window:** a 2 × 2 km window on the western delta front (`77.3767–77.4105° E`, `18.4478–18.4815° N`), analysed cell by cell on the HiRISE 1 m terrain model

---

## 1. Core Team

### Jean-Sebastien Beaulieu (`jean`) — Middleware, Data Contract & Terrain Engine Lead
- **Responsibilities:**
  - Data Contract specification (`v1.1.0`, additive over `v1.0.0`) (`src/marswalk/contracts/`, `schemas/`, `docs/contracts/10_CONTRAT_DONNEES.md`).
  - NASA Mars 2020 (`M20_waypoints.json`, `M20_traverse.json`), USGS HiRISE DTM (`1 m`), and Mars Trek WMTS (`25 cm`) data ingestion and geodetic alignment (`R = 3,396,190 m`).
  - Deterministic static pack generation (`public_packs/jezero/v1/`), SHA-256 cryptographic verification, FastAPI middleware (`src/marswalk/middleware/`), and multi-scale terrain verification engine.
- **ORCID:** [0009-0007-2904-0443](https://orcid.org/0009-0007-2904-0443)

### Philippe Pierre (`teammate`) — Frontend Architecture, UX & Product Brand Lead
- **Responsibilities:**
  - Full creative and architectural ownership of `frontend/` (on `main`).
  - Final product brand name and `.spaceapps.earth` domain selection reflecting the visual identity and user experience of the application.
  - Interactive Martian map experience, multi-scale hazard inspection, Perseverance waypoint explorer, and astronaut EVA route planner.

---

## 2. Human-in-the-Loop Engineering Principles

1. **Human Direction First:** I decide every architectural choice, dataset and physical threshold of the engine; Philippe decides everything in the frontend. AI agents write and audit code, but nothing is merged without my approval. A threshold with a primary source cites it; a value without one is tagged as an internal margin or an uncalibrated heuristic, never as a fact.
2. **Strict Separation of Facts and Simulation:** Real telemetry from Perseverance (`708` stops, `Sol 13 → Sol 2022`) is strictly separated from derived orbital slopes and simulated astronaut EVA paths via the `MEASURED | DERIVED | SIMULATED` tag system.
3. **Transparent AI Disclosure:** In compliance with official NASA Space Apps Challenge rules, all AI tools used to accelerate code generation, schema validation, and documentation are transparently disclosed in [`docs/AI_USAGE.md`](docs/AI_USAGE.md).
4. **Safety before features:** the route evaluator never answers `GO` on missing data, and an operator can switch route approval off at any time (`MARSWALK_SAFE_MODE=1`, see [`SECURITY.md`](SECURITY.md)).

## Where the project stands (2026-11-15)

- **Done:** the data contract, the signed Jezero pack (`v1.1.0`, 1,600 cells of ~48 m from the real HiRISE terrain model), the live API, and the safety layer (fail-safe answers, operator safe mode, `demo-stable` rollback tag).
- **Done (Phase 4):** a route planner that draws a walk around scarps and rock formations of about 4 m and more (`/plan-route`, `obstacles.geojson`). It takes about 1.5 s per plan today.
- **Honest limits:** the engine is tested on one 2 × 2 km window and checked against 147 real rover stops. On those stops it is not yet better than a simple fixed 16 m slope; I publish that result instead of hiding it.

The detailed phase table for agents is in [`AGENTS.md`](AGENTS.md).

---

## 3. Where each of us works (start here)

Every folder a human needs has its own `HUMAN.md`: a short, honest map written for people, not for machines.

| Folder | Owner | Read first |
|---|---|---|
| `frontend/` | Frontend lead (full ownership) | [`frontend/HUMAN.md`](frontend/HUMAN.md) |
| `public_packs/` | Engine (read only for the UI) | [`public_packs/HUMAN.md`](public_packs/HUMAN.md) |
| `schemas/` | Engine (read only for the UI) | [`schemas/HUMAN.md`](schemas/HUMAN.md) |
| `shared/` | Both of us | [`shared/HUMAN.md`](shared/HUMAN.md) |
| `src/marswalk/` | Engine | [`src/marswalk/HUMAN.md`](src/marswalk/HUMAN.md) |

## 4. Why I build this

I have spent years chasing things that are hard to see: neutrinos, fractal structure, the moment a phenomenon begins or ends depending on the scale you look at it. Mars gave me a concrete version of that question. An orbital map is true at one scale and quietly wrong at another, and an astronaut pays for the difference with their legs, their oxygen and their safety.

So I hold this project to one rule: **say what is measured, what is derived and what is simulated, every time, on every number.** Beautiful is welcome. Fake is not.

— Jean-Sébastien Beaulieu
