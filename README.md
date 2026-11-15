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

- **Data Contract (`v1.0.0` / `v1.1.0` Frozen):** [`docs/contracts/10_CONTRAT_DONNEES.md`](docs/contracts/10_CONTRAT_DONNEES.md)
- **Mathematical Specification (`Plithogenic <T, I, F>`, Funnel & Anisotropic `A*`):** [`docs/ENGINE_MATH.md`](docs/ENGINE_MATH.md)
- **Standalone SVG Survival Map Card:** [`docs/assets/jezero_eva_survival_map.svg`](docs/assets/jezero_eva_survival_map.svg)
- **Frontend Integration Guide:** [`frontend/README.md`](frontend/README.md)
- **Branch history (now a single `main`):** [`docs/WORKTREE_TRACE.md`](docs/WORKTREE_TRACE.md)
- **Human-AI Collaboration & AI Disclosure:** [`HUMAN.md`](HUMAN.md) & [`docs/AI_USAGE.md`](docs/AI_USAGE.md)
- **Multi-Agent Rules:** [`AGENTS.md`](AGENTS.md) (`.claude/`, `.antigravity/`, `.antigravity-ide/`, `.gemini/`)
- **Data Licenses & Canadian Open Government Licence Attribution:** [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)

---

## 6. References & Data Sources

Every `MEASURED`, `DERIVED`, and `SIMULATED` quantity in `public_packs/jezero/v1/` is cryptographically bound via `manifest.json` (`SHA-256`) to the following official NASA, JPL, USGS, and peer-reviewed planetary science sources:

1. **NASA/JPL-Caltech Mars 2020 Mission Operations MMGIS Waypoints (`SRC-M20-WAYPOINTS`, `708` stops, Sol 13–2022):** https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json
2. **NASA/JPL-Caltech Mars 2020 Mission Operations MMGIS Traverse Path (`SRC-M20-TRAVERSE`, `45.2 km`):** https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json
3. **NASA/JPL-Caltech/ASU Mars 2020 Raw Images Archive (`SRC-M20-RAW-IMAGES`, Navcam & Mastcam-Z):** https://mars.nasa.gov/mars2020/multimedia/raw-images/
4. **NASA Solar System Treks / MRO HiRISE 25 cm/px Orthorectified Mosaic (`SRC-TREK-HIRISE-25CM`, Fergason et al. 2020):** https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars
5. **USGS Astrogeology Mars 2020 TRN HiRISE 1 m/px Digital Terrain Model Blended with MOLA (`SRC-USGS-HIRISE-DTM-1M`, Fergason et al. 2020):** https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif
6. **USGS Scientific Investigations Map 3464 — Geologic Map of Jezero Crater (`SRC-USGS-SIM3464`, Sun & Stack 2020):** https://doi.org/10.3133/sim3464
7. **NASA Extravehicular Activity (xEVA) System Concept of Operations (`SRC-NASA-XEVA`, EVA-EXP-0042 Rev B, 2020):** https://www.nasa.gov/wp-content/uploads/2017/02/eva-exp-0042_xeva_system_con_ops_rev_b_final_dtd_10192020_ref_doc.pdf
8. **JPL Mars 2020 Surface Traversability Analysis (`SRC-JPL-TRAVERSABILITY`, Ono et al. 2016, IEEE Aerospace Conference):** https://www-robotics.jpl.nasa.gov/media/documents/Data-driven%20surface%20traversability%20analysis%20for%20Mars%202020%20landing%20site%20selection.pdf
9. **MSL Curiosity Radiation Assessment Detector (`SRC-RAD-GALE`, Hassler et al. 2014, *Science* 343(6169), 0.64 mSv/day GCR baseline):** https://www.swri.org/newsroom/press-releases/swri-scientists-publish-first-radiation-measurements-the-surface-of-mars
10. **Apollo EVA Slope & Elevation Envelope (`SRC-APOLLO-SLOPE`, Iqbal et al. 2024, *Acta Astronautica* 223, 184–196):** https://doi.org/10.1016/j.actaastro.2024.07.006

---

## 7. Thoughtful Use of AI (AI Usage Disclosure)

This project was engineered through an iterative, human-directed collaboration between **Jean-Sébastien Beaulieu** (Engine, Plithogenic Math, Geodesy & Middleware Lead) and **Philippe Pierre** (Frontend Cartography, 3D Terrain & UX Lead), using AI coding assistants (Claude Code, Google Gemini / Antigravity, and OpenAI Codex) strictly as verification, code-generation, and hostile-audit instruments under human architectural authority. All scientific equations, physical thresholds, dataset choices, and safety vetoes were defined, cross-checked against primary NASA/USGS data, and verified by deterministic automated test suites (`pytest` + `vitest`) by the human authors. See [`docs/AI_USAGE.md`](docs/AI_USAGE.md) for the complete module-by-module AI disclosure.
