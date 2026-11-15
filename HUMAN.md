# Human Team & Collaboration Charter (`HUMAN.md`)

**Event:** 2026 NASA International Space Apps Challenge (48-Hour Sprint)  
**Challenge:** *Interplanetary Survival Guide: Martian Map*  
**Study Site:** Jezero Crater, Mars (`18.38° N, 77.58° E` — Mars 2020 Perseverance Landing & Traverse Region)

---

## 1. Core Team

### Jean-Sebastien Beaulieu (`@EbaAaZ`) — Middleware, Data Contract & Terrain Engine Lead
- **Responsibilities:**
  - Data Contract `v1.0.0` specification (`src/marswalk/contracts/`, `schemas/`, `docs/contracts/10_CONTRAT_DONNEES.md`).
  - NASA Mars 2020 (`M20_waypoints.json`, `M20_traverse.json`), USGS HiRISE DTM (`1 m`), and Mars Trek WMTS (`25 cm`) data ingestion and geodetic alignment (`R = 3,396,190 m`).
  - Deterministic static pack generation (`public_packs/jezero/v1/`), SHA-256 cryptographic verification, FastAPI middleware (`src/marswalk/middleware/`), and multi-scale terrain verification engine.
- **ORCID:** [0009-0007-2904-0443](https://orcid.org/0009-0007-2904-0443)

### Philippe Pierre (`@Maptop`) — Frontend Architecture, UX & Product Brand Lead
- **Responsibilities:**
  - Full creative and architectural ownership of `frontend/` (`feat/ui` branch).
  - Final product brand name and `.spaceapps.earth` domain selection reflecting the visual identity and user experience of the application.
  - Interactive Martian map experience, multi-scale hazard inspection, Perseverance waypoint explorer, and astronaut EVA route planner.

---

## 2. Human-in-the-Loop Engineering Principles

1. **Human Direction First:** Every architectural decision, dataset selection, and physical threshold in this repository was reviewed, verified against primary NASA/JPL/USGS documentation, and approved by the human team.
2. **Strict Separation of Facts and Simulation:** Real telemetry from Perseverance (`708` stops, `Sol 13 → Sol 2022`) is strictly separated from derived orbital slopes and simulated astronaut EVA paths via the `MEASURED | DERIVED | SIMULATED` tag system.
3. **Transparent AI Disclosure:** In compliance with official NASA Space Apps Challenge rules, all AI tools used to accelerate code generation, schema validation, and documentation are transparently disclosed in [`docs/AI_USAGE.md`](docs/AI_USAGE.md).
