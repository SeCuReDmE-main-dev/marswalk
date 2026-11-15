# Human Team & Collaboration Charter (`HUMAN.md`)

**Event:** 2026 NASA International Space Apps Challenge (48-Hour Sprint)  
**Challenge:** *Interplanetary Survival Guide: Martian Map*  
**Study Site:** Jezero Crater, Mars (`18.38° N, 77.58° E` — Mars 2020 Perseverance Landing & Traverse Region)

---

## 1. Core Team

### Jean-Sebastien Beaulieu (`jean`) — Middleware, Data Contract & Terrain Engine Lead
- **Responsibilities:**
  - Data Contract `v1.0.0` specification (`src/marswalk/contracts/`, `schemas/`, `docs/contracts/10_CONTRAT_DONNEES.md`).
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

1. **Human Direction First:** Every architectural decision, dataset selection, and physical threshold in this repository was reviewed, verified against primary NASA/JPL/USGS documentation, and approved by the human team.
2. **Strict Separation of Facts and Simulation:** Real telemetry from Perseverance (`708` stops, `Sol 13 → Sol 2022`) is strictly separated from derived orbital slopes and simulated astronaut EVA paths via the `MEASURED | DERIVED | SIMULATED` tag system.
3. **Transparent AI Disclosure:** In compliance with official NASA Space Apps Challenge rules, all AI tools used to accelerate code generation, schema validation, and documentation are transparently disclosed in [`docs/AI_USAGE.md`](docs/AI_USAGE.md).

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
