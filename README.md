# MarsWalk — *The Map That Knows At Which Scale It Lies*

[![NASA Space Apps Challenge 2026](https://img.shields.io/badge/NASA_Space_Apps_2026-Interplanetary_Survival_Guide:_Martian_Map-0B3D91)](https://www.spaceappschallenge.org/2026/challenges/interplanetary-survival-guide-martian-map/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Data Contract](https://img.shields.io/badge/Data_Contract-v1.0.0_Frozen-success)](docs/contracts/10_CONTRAT_DONNEES.md)

> **Naming Note (`NB-T08`):** `marswalk` is the technical repository and Python package code name for the multi-scale Martian terrain & EVA verification engine. Our frontend lead **Philippe Pierre (`teammate`)** has full creative freedom to choose the final product brand name and `.spaceapps.earth` domain that best reflects his visual design and user experience.

---

## 1. The Challenge & The Core Discovery

Most planetary mapping tools treat an orbital Digital Terrain Model (DTM) as ground truth. Yet on Mars, **the hazard that breaks a rover wheel or exhausts an astronaut on an Extravehicular Activity (EVA) lives in the scale gap** between orbital pixels (`1 m` HiRISE, `20 m` HRSC, `463 m` MOLA) and the `30 cm` wheel or boot footprint on the ground.

**MarsWalk** solves the *Interplanetary Survival Guide: Martian Map* challenge by confronting multi-scale orbital terrain slopes (`1 m`, `4 m`, `16 m`, `64 m` baselines) against **708 real ground-truth waypoints and measured rover tilts (`Sol 13 → Sol 2022`)** recorded by NASA's Perseverance rover in **Jezero Crater** (`18.38° N, 77.58° E`).

Every number in our data pack carries an explicit provenance tag (`MEASURED`, `DERIVED`, or `SIMULATED`) linked to an official NASA PDS, JPL, USGS, or NASA xEVA reference source, and every terrain cell exposes:
- Multi-scale slope by baseline (`1 m`, `4 m`, `16 m`, `64 m`);
- **Scale Divergence** — where coarse orbital maps hide local meter-scale slope hazards;
- **3-Component Confidence (`t`, `i`, `f`)** — quantifying verified agreement (`t`), scale/coverage uncertainty (`i`), and hazard contradiction (`f`);
- **Actionable EVA Verdict (`GO | CAUTION | NO_GO`)** governed by citable NASA xEVA (`20°` suit limit, `2 km` walkback) and JPL rover (`20°` bedrock, `10°` sand) safety thresholds.

---

## 2. Two-Track Architecture (Zero-Blocking Static Pack + Optional FastAPI)

To guarantee zero frontend blocking and effortless static hosting (Vercel, GitHub Pages, Cloudflare Pages), MarsWalk publishes a **cryptographically signed static site pack** under [`public_packs/jezero/v1/`](public_packs/jezero/v1/manifest.json) alongside an optional local FastAPI query service:

```text
NASA M20 / HiRISE / USGS Raw Data (datalake/ — gitignored)
       │
       ▼  python -m marswalk.middleware.cli build-pack --site jezero
┌──────────────────────────────────────────────────────────────────┐
│ public_packs/jezero/v1/  (Committed & SHA-256 Verified)          │
│  ├─ manifest.json          (CRS: Mars Sphere R=3,396,190m + SHA) │
│  ├─ waypoints.geojson      (708 Perseverance stops + tilt + pan) │
│  ├─ route.geojson          (MEASURED M20 traverse + SIMULATED EVA│
│  ├─ hazard_grid.json       (1m/4m/16m/64m slopes + confidence)   │
│  ├─ hazard_overlay.png     (Transparent RGBA heatmap overlay)    │
│  └─ eva_constraints.json   (Citable NASA xEVA + JPL thresholds)  │
└──────────────┬───────────────────────────────────┬───────────────┘
               │ Direct static fetch()             │ Optional local API
               ▼                                   ▼
      [frontend/ Web App]                 [FastAPI :8000 /v1/sites/jezero/*]
```

---

## 3. Quickstart for Frontend (`frontend/`)

You do **not** need Python running to build the frontend UI. All verified Jezero Crater assets live directly in `public_packs/jezero/v1/`. See [`frontend/README.md`](frontend/README.md) and [`docs/contracts/10_CONTRAT_DONNEES.md`](docs/contracts/10_CONTRAT_DONNEES.md) for the complete 1-page data contract and Mars Trek 25 cm HiRISE WMTS tile integration guide.

```javascript
const packUrl = "/public_packs/jezero/v1";
const [manifest, waypoints, route, hazards, constraints] = await Promise.all([
  fetch(`${packUrl}/manifest.json`).then((r) => r.json()),
  fetch(`${packUrl}/waypoints.geojson`).then((r) => r.json()),
  fetch(`${packUrl}/route.geojson`).then((r) => r.json()),
  fetch(`${packUrl}/hazard_grid.json`).then((r) => r.json()),
  fetch(`${packUrl}/eva_constraints.json`).then((r) => r.json()),
]);
console.log(`Loaded ${waypoints.features.length} Perseverance stops`, manifest.bbox);
```

---

## 4. Quickstart for Middleware & Engine (`src/marswalk/`)

```bash
# 1. Install in editable mode with dev tools
pip install -e ".[dev]"

# 2. Export JSON Schemas (Draft 2020-12) from frozen Pydantic v2 models
python -m marswalk.middleware.cli export-schemas

# 3. Rebuild and verify the Jezero v1 static pack
python -m marswalk.middleware.cli build-pack --site jezero
python -m marswalk.middleware.cli verify-pack --site jezero

# 4. Run the optional FastAPI middleware server (CORS * enabled)
uvicorn marswalk.middleware.api:app --reload --port 8000

# 5. Run linter and test suite (including 500-request concurrency stress test)
ruff check .
ruff format --check .
pytest -q --tb=short
```

---

## 5. Repository Governance & Documentation

- **Data Contract (`v1.0.0` Frozen):** [`docs/contracts/10_CONTRAT_DONNEES.md`](docs/contracts/10_CONTRAT_DONNEES.md)
- **Frontend Integration Guide:** [`frontend/README.md`](frontend/README.md)
- **Branch history (now a single `main`):** [`docs/WORKTREE_TRACE.md`](docs/WORKTREE_TRACE.md)
- **Human-AI Collaboration & AI Disclosure:** [`HUMAN.md`](HUMAN.md) & [`docs/AI_USAGE.md`](docs/AI_USAGE.md)
- **Multi-Agent Rules:** [`AGENTS.md`](AGENTS.md) (`.claude/`, `.antigravity/`, `.antigravity-ide/`, `.gemini/`)
- **Data Licenses & Canadian Open Government Licence Attribution:** [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)
