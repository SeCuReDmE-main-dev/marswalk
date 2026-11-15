# MarsWalk Data Contract Specification — `v1.0.0` (`docs/contracts/10_CONTRAT_DONNEES.md`)

**Status:** Frozen (`v1.0.0`)  
**Geodetic Reference:** Planetocentric East Longitude (`lon`) & Latitude (`lat`) on the Mars Sphere `R = 3,396,190.0 m` (`IAU2015:49900`)  
**Primary Static Pack Path:** `public_packs/jezero/v1/`  
**JSON Schemas (Draft 2020-12):** `schemas/*.schema.json`

---

## 1. Core Design Principles

1. **Zero Frontend Blocking:** All verified data for Jezero Crater is pre-built, validated, and committed inside `public_packs/jezero/v1/` (`< 5 MB`). The frontend can fetch every file directly as static JSON/GeoJSON/PNG assets or query the optional FastAPI service (`http://localhost:8000/v1/sites/jezero/...`).
2. **Explicit Scientific Provenance (`Quantity`):** Every physical measurement or threshold is wrapped in a `Quantity` object:
   ```json
   {
     "value": 20.0,
     "unit": "deg",
     "tag": "MEASURED",
     "source_id": "SRC-NASA-XEVA"
   }
   ```
   - `MEASURED`: Direct spacecraft/rover telemetry or published engineering specification.
   - `DERIVED`: Computed deterministically from orbital DTMs or telemetry (e.g., multi-scale slope at `1 m / 4 m / 16 m / 64 m`, scale divergence, cumulative radiation dose over an EVA duration).
   - `SIMULATED`: Candidate astronaut EVA paths or hypothetical route plans.
3. **Clear UI Vocabulary (`confidence` + `GO | CAUTION | NO_GO`):**
   Each terrain cell exposes:
   - `confidence: { "t": 0.86, "i": 0.09, "f": 0.05 }` where `t` = verified safety agreement, `i` = scale-gap/coverage uncertainty, and `f` = active hazard contradiction;
   - `verdict`: `"GO"`, `"CAUTION"`, or `"NO_GO"`;
   - `reason`: Plain-English explanation of the governing constraint.

---

## 2. Files in `public_packs/jezero/v1/`

| File | Schema | Content |
| :--- | :--- | :--- |
| `manifest.json` | `schemas/SiteManifest.schema.json` | Site bounding box `[77.223, 18.307, 77.584, 18.669]`, Mars sphere CRS (`R = 3,396,190 m`), Mars Trek HiRISE 25 cm WMTS descriptor, primary source registry (`sources[]`), and `SHA-256` + byte counts for all pack files. |
| `waypoints.geojson` | `schemas/WaypointFeatureCollection.schema.json` | GeoJSON `FeatureCollection` of all **708 Perseverance rover stops** (`Sol 13 → Sol 2022`) with `MEASURED` `elev_geoid_m`, `rover_tilt_deg`, `rover_pitch_deg`, `rover_roll_deg`, `dist_total_m`, and `panorama_url`. |
| `route.geojson` | `schemas/EvaRoute.schema.json` | GeoJSON `FeatureCollection` containing: (1) the `MEASURED` Perseverance traverse polyline, (2) a `SIMULATED` `< 2 km` astronaut EVA loop across the Jezero western fan, and (3) `3` science stops anchored to real Perseverance waypoints and USGS SIM 3464 geologic units. |
| `hazard_grid.json` | `schemas/HazardGrid.schema.json` | Multi-scale terrain grid with slopes at `1 m`, `4 m`, `16 m`, and `64 m` baselines (`slope_deg_by_baseline`), `scale_divergence`, `rock_cfa_pct`, `confidence: {t, i, f}`, `verdict: GO\|CAUTION\|NO_GO`, and nearest Perseverance waypoint ground-truth tilt comparison. |
| `hazard_overlay.png` | RGBA PNG (`[min_lon, min_lat, max_lon, max_lat]`) | Transparent color-coded RGBA image (`GO` = emerald, `CAUTION` = amber, `NO_GO` = crimson) aligned to the exact `hazard_grid.json` bounding box for instant map overlay. |
| `eva_constraints.json` | `schemas/EvaConstraints.schema.json` | Citable safety thresholds: NASA xEVA suit max slope (`20°`), walkback limit (`2.0 km`), EVA duration (`4–8 h`), Apollo practical slope (`15°`) & relief (`150 m`), JPL rover slope limits (`20°` bedrock, `10°` sand), sand ripple hazard (`10 cm`), rock CFA (`7%` OK, `15%` caution), and Curiosity RAD surface GCR dose (`0.67 mSv/day`). |

---

## 3. Optional FastAPI Middleware Endpoints (`marswalk.middleware.api`)

When running `uvicorn marswalk.middleware.api:app --reload --port 8000` (CORS `*` enabled):

- `GET /health` → `{"status": "ok", "contract_version": "1.0.0"}`
- `GET /v1/sites` → List of available verified site packs (`["jezero"]`)
- `GET /v1/sites/{site_id}/manifest` → `SiteManifest`
- `GET /v1/sites/{site_id}/waypoints` → `WaypointFeatureCollection` (`708` stops)
- `GET /v1/sites/{site_id}/route` → `EvaRoute`
- `GET /v1/sites/{site_id}/hazards` → `HazardGrid`
- `GET /v1/sites/{site_id}/constraints` → `EvaConstraints`
- `GET /v1/sites/{site_id}/cell?lon=77.43&lat=18.45` → Nearest `HazardCell` + closest Perseverance ground-truth waypoint comparison
- `POST /v1/sites/{site_id}/evaluate-route` → Evaluates a custom list of `[lon, lat]` points against `EvaConstraints` and the multi-scale hazard grid (`distance_m`, `max_slope_deg`, `scale_divergence_max`, `estimated_duration_h`, `estimated_radiation_msv`, `verdict`).
