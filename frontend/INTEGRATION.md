# Marswalk frontend / middleware handoff

The frontend is a React + TypeScript + Leaflet app. It owns display and interaction; the middleware owns scientific calculations and supplied assessments. No contract, schema, backend or frozen pack files were changed.

## Run locally

Node 22 or newer is recommended. From the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open the Local URL printed by Vite (port 5173 by default). `predev` copies the existing static pack and selected logo into ignored `public/` directories. No Python server, API key or account is required for this mode. NASA imagery and panorama links still require network access; external failures do not become fake imagery or observations.

## Connect the team's middleware

Create `frontend/.env.local` with:

```dotenv
VITE_DATA_MODE=api
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_SITE_ID=jezero
```

Restart Vite after changing environment variables. `VITE_API_BASE_URL` is the service origin or path prefix **before** `/v1/sites`; do not put a complete site endpoint there. Use an HTTPS API when the deployed frontend is served over HTTPS. The API must allow the frontend origin through CORS. All `VITE_*` settings are public browser configuration, never secrets.

The adapter consumes these existing endpoints without changing the UI:

| GET endpoint                   | Response schema             |
| ------------------------------ | --------------------------- |
| `/v1/sites/{site}/manifest`    | `SiteManifest`              |
| `/v1/sites/{site}/hazards`     | `HazardGrid`                |
| `/v1/sites/{site}/route`       | `EvaRoute`                  |
| `/v1/sites/{site}/waypoints`   | `WaypointFeatureCollection` |
| `/v1/sites/{site}/constraints` | `EvaConstraints`            |

Each response is the direct object, **not** wrapped in `{data: ...}`. Runtime validation imports the shared `schemas/*.schema.json` (currently supporting contracts 1.0.0 and 1.1.0). Generated types were refreshed for main's Phase 3 contract and the 40×40 pack; grid dimensions are read from the payload. Coordinate values must remain planetocentric east longitude/latitude on the 3,396,190 m Mars sphere. API-mode loading validates shapes, site identity and quantity-source references. Middleware remains responsible for verifying its stored pack hashes; the UI does not claim API responses were byte-hash-verified.

For externally hosted static packs instead:

```dotenv
VITE_DATA_MODE=static
VITE_PACK_URL=https://example.org/public_packs/jezero/v1
VITE_SITE_ID=jezero
```

The static host must allow browser fetches/CORS and supply consistent bytes matching `manifest.files`. Static mode checks the consumed JSON/GeoJSON payload digests and byte counts, including obstacles when present. It does not claim a cryptographic signature, scientific validation, or verification of unconsumed pack files.

## Change points

- `src/data/types.ts`: public `MarswalkDataSource` interface and combined UI data model.
- `src/data/source.ts`: shared static/API adapter, validation, hash checks and errors. All data requests are centralized here.
- `src/data/config.ts`: environment mapping. To connect another endpoint shape, adapt the source here/above rather than rewriting components.
- `src/data/generated/`: generated TypeScript contract DTOs. Run `npm run types:generate` after an agreed schema update; do not manually edit generated files or the shared schema.
- `src/domain.ts`: UI geometry, coverage containment, safe links, route-feature filtering and export helpers.
- `src/MapView.tsx`: geographic map presentation and callbacks; it does not fetch middleware data or evaluate routes.
- `src/App.tsx`: guide, selected entities, evidence panels and source dialogs.
- `src/RoverImage.tsx` and `src/data/images.ts`: canonical stop images prefer the bundled JPEG after checking its manifest byte count and SHA-256. If the local copy cannot be loaded, the component tries the supplied NASA URL. Other rover observations use their supplied image URL. Frames are labeled Navcam images, not 360-degree panoramas.

The data source accepts an `AbortSignal` for cancellation. Requests fail visibly; the app does not silently switch API failures to an old static pack. The Reload data control fetches again.

## Scientific/display boundaries

- Cell, route and science-stop assessments are distinct. The browser displays their supplied verdicts and does not infer a verdict from the selected baseline.
- 1 m baseline is diagnostic only. 64/16/4 m controls compare actual slope values, not map zoom.
- Assessment rectangles derive from grid bbox, row and col. Outside that coverage returns Not assessed, not a nearest-cell verdict.
- Null matched tilt/rock fields remain Unavailable. Rover records are independently browsable; no per-cell ground-truth match is fabricated.
- Route features tagged BENCHMARK are excluded from the astronaut candidate/science-stop UI.
- Measured hazard benchmarks have a separate selector under **Check the evidence** and optional B1/B2 map markers. Their reference verdict and measured tilt remain distinct from the containing cell's orbital slope; outside-grid references never borrow a nearest-cell terrain verdict. **Layers** can compare the original simulated walk with the supplied obstacle-aware walk. Both routes and the benchmark references are preserved separately in exported summaries.
- Max distance from start is frontend-derived spherical distance over the supplied candidate vertices. It is not a traversable return-path distance. Original route notes and reference constraints remain visible separately.
- Quantities retain value, unit, tag, source_id and note. Source buttons resolve through the manifest. Radiation proxy notes are displayed.
- External tile geometry uses Leaflet EPSG:4326 with the geographic 2:1 WMTS grid; the map's distance function uses the Mars sphere, not Earth's radius.
- A global Viking color mosaic sits beneath the local HiRISE grayscale footprint. It is display context only, never additional assessed terrain. NASA's [tile catalog](https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars) and [Viking WMTS capabilities](https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/WMTSCapabilities.xml) specify JPEG tiles, a geographic 2:1 grid and native matrices 0–7; higher display zoom overzooms that coarse context. Network errors remain visible. No red tint is applied to the imagery.
- The map labels Jezero, Mars, outlines the assessed window with its dimensions derived on the Mars sphere, and states that outside terrain is not assessed. **Jezero context** fits the manifest's wider regional extent; the hazard legend hides at regional zoom where the cells are too small to interpret. **Assessed area** and **Fit route** restore the close view.
- The local fallback backdrop is a coarse raster made from the actual grid elevations and labeled DERIVED. It is not high-resolution imagery. NASA tiles are a separate attributed layer.

## Connected engine features

The supplied `DERIVED_OBSTACLE_AWARE_EVA` is preferred over the original simulated route. The map can toggle the pack's `obstacles.geojson` (82 DERIVED outlines in the current pack). Static loading verifies the obstacle file's digest and size along with the four original payloads. The planner's encoded 10 m PNG remains an engine input; it is not misrepresented as a photograph or a terrain verdict layer.

Use **Plan walk** in the header to add ordered science stops or pick points on the map. **Plan around obstacles** calls `POST /v1/sites/{site}/plan-route` (2–32 points); **Assess drawn path** calls `/evaluate-route` (2–500 points). The scenario controls send dust optical depth, additional payload, radio link margin and solar-particle-event status. No scientific calculations are duplicated in React. Results retain the supplied provenance, reasons, effort, oxygen return margin, radio status and planner details. Editing points or scenarios aborts outstanding requests and clears the previous result. Live assessments can be exported separately from the supplied pack summary.

The live service address is `VITE_API_BASE_URL` in both static and API modes. Static browsing does not require a server: connect explicitly in the planner. API mode checks health automatically. Health is polled every 10 seconds and checked before and after route requests. Operator stop or connection failure clears live results and disables planning; a banner explains the state. A matching manifest (file digests/sizes and Mars CRS) is required before live planning. Restart/rebuild Vite when changing API configuration. On a deployed site, configure an HTTPS middleware URL; localhost is only for local development.

**Inspect the terrain** exposes optional environment, geology, applicability, calibrated confidence, refuge, effort and radio fields in a collapsed section, preserving unavailable values and scientific caveats. **Nearby rover evidence** uses `/cell` and labels the nearest observation as context. **Check the evidence → Rover camera frames** uses `/waypoints/{sol}/cameras`, with pagination and an optional azimuth filter. Requests always send `allow_network=false`; live NASA fetching remains an operator decision. Empty caches have a visible unavailable state.

`src/data/engine.ts` centralizes all live requests, cancellation/timeouts, response-schema validation, site identity and provenance checks. Refresh the frontend-owned API schema snapshots from the backend models, then regenerate types:

```powershell
# Run with the repository's Python environment from the repo root:
python frontend/scripts/export-api-contracts.py
cd frontend
npm run types:generate
```

These commands edit only frontend snapshots/types. They do not change the shared contracts, backend, or pack.

The app is a planning/hackathon prototype, not astronaut navigation or NASA safety certification. No simulated live GPS, oxygen, weather or battery telemetry is shown.

After pulling main through `3509d93`, the three science-stop photos use the five-image bundle introduced by `ffde828`. All three replacement remote URLs returned HTTP 200 JPEGs in a direct check; all three science-stop images also decoded at 800 px width in the browser from verified pack copies. Canonical local copies are matched by exact source URL, not just by sol, to avoid substituting an unrelated observation. Images at stops 1, 2 and 3 no longer depend on remote NASA access in static pack mode.

## Optional 3D terrain presentation

**Map / 3D terrain** switches the main workspace between Leaflet and a lazy-loaded Canvas terrain preview. The preview uses only the existing elevation samples from the assessed grid (currently 40 × 40, approximately 49 m spacing), with local east/north distances on the shared Mars sphere. The mesh interpolates between samples; it is not a new full-resolution 1 m terrain model. Selecting a model sample opens its existing terrain assessment in the guide. A 3D route pick snaps to a sample centre; outside-window route vertices are not projected onto the terrain.

The default satellite surface composites the manifest's NASA HiRISE WMTS imagery using its geographic 2:1 tile grid, then maps it onto the coarse mesh. If tiles cannot load, shaded relief stays available with an explicit texture-unavailable message. The coarse imagery grid and view interpolation are presentation only; the scientific route planner and its 10 m raster remain backend-owned. No new npm dependency or startup pack request is required; the 3D code and optional texture requests start only when that view opens.

**View settings** offers satellite imagery, shaded relief or supplied terrain-assessment colors, an optional model grid, and 1–4× vertical exaggeration. True scale is the default; any exaggeration is labeled and never changes a verdict or safety limit. **Orbit camera** is opt-in, stops during manual manipulation, respects the operating system's reduced-motion preference, and can be disabled through the local reduced-motion control. Keyboard arrows rotate; +/- zoom; Home resets. These are visual camera animations, not simulated telemetry or astronaut motion.

Validation: 22 frontend tests pass, including Mars-scale mesh distances, preservation of every original elevation sample, outside-window handling, legacy route fallback and WMTS texture alignment. Production build passes. Browser checks covered satellite texture loading, orbit/pause, reduced motion, surface/grid/height settings, sample inspection, map restoration, desktop and mobile layout with no horizontal overflow. The wider backend rebuild limitations documented above remain separate from this display-only feature.

## Discussion #1 follow-up: data availability

The **Sources** dialog now has **Local data & network limits**. It distinguishes bundled data from NASA tiles/photos and the optional engine server, reads the bundled JPEG count from `manifest.files`, and displays external-layer status/reasons/uncertainty from the current pack. The per-cell environment panel retains its detailed availability report. Geological units remain explicitly approximate.

Bundled assets do not make the hosted app an offline installation: there is no service worker. A downloaded production build can be served locally; API pack mode still needs its configured server. Local canonical images are preferred and verified before using a remote fallback. NASA texture failures retain coarse relief; unavailable camera caches do not trigger live downloads.

The image, route, benchmark and engine integration work is on `feat/frontend-engine-integration`; this does not mean it has been merged into `main`. The four independent Antigravity audits requested in `HO-002` are a separate outstanding handoff. Frontend checks here do not substitute for those audits or claim NASA certification.

## Interactive walk preview

Open **Walk preview** below the map. Play/pause a visual rehearsal of the supplied candidate route, scrub the distance slider or elevation chart, restart, or jump to the nearest route position for a science stop. An orange position marker follows the same coordinates in the map and optional 3D view. **Inspect cell** opens the existing terrain evidence in the guide; elevation and route source buttons open the manifest records. The panel starts collapsed, keeps manual scrubbing available under OS reduced motion, and stops playback on close, backgrounding, source inspection or cell inspection.

This previews the supplied pack route, not a new live planner result. Distance along the path is computed on the shared Mars sphere from its vertices; rounding may differ from the pack's stored summary. The 45-second playback is a presentation speed, not an astronaut travel-time model or live tracking. `routePreview.ts` preserves the containing cell's original elevation Quantity, provenance, verdict and confidence; it does not calculate a safety decision. The profile samples at bounded display intervals (at most 241 points), repeats coarse cell elevations and leaves gaps outside coverage or where elevation is unavailable. It is not a high-resolution terrain cross-section or a segment-by-segment safety proof. Geological and safety limitations elsewhere still apply.

Checks: 25 frontend tests pass, including the actual supplied path, Mars distances, exact endpoints, duplicate vertices, stop projection, unavailable elevation and outside-grid gaps. Browser checks at desktop and 390 px mobile covered play/pause and replay, keyboard End, chart scrubbing, stop jumps, map/3D synchronization, cell/source inspection and marker removal on close. No JavaScript errors or horizontal overflow were observed. Screenshots are in `frontend/screenshots/walk-preview-desktop.png` and `walk-preview-mobile.png`.

Repository gate on this change: Ruff and verification of all 17 pack files pass. The Python suite needs local socket permissions for Windows asyncio/TestClient; after rerunning outside the sandbox, `pytest -x` reaches `test_async_pipeline_determinism_and_astar_envelope` and fails because the local ignored `datalake/SIM3464_metadata.xml` is absent. The full gate is not green. No backend tests, thresholds or data-pack files were changed to mask it.

## Build and validate

```powershell
npm test
npm run build
npm run preview
```

`dist/` is a static deployable frontend, including the copied pack. For subpath hosting, set `VITE_BASE_PATH=/your-path/` at build time; default pack/brand URLs follow that base. API config is compiled into the build, so rebuild after changing production URLs. No hosting account or deployment was created as part of this branch.

Automated frontend tests exercise the real pack, tamper rejection, API mapping, malformed responses, source/scope safety, Mars distances, route preference, input validation, pack mismatch and read-only camera requests. For a running middleware integration check, start the server and run `node --import tsx scripts/smoke-engine.ts` from `frontend/`. Override `MARSWALK_API_URL` if needed; `EXPECT_SAFE_MODE=1` checks a server deliberately started in operator stop mode.

Validation on 2026-11-15: frontend tests and production build pass; live API smoke passes (1,600 cells, 82 obstacles, planning, assessment, SPE NO_GO, outside-coverage FAIL_SAFE, camera cache unavailable). Desktop and 390 px mobile browser checks covered point picking, scenario invalidation, collapse with tips off, layer toggles, camera empty state, nearest rover lookup, safe mode and server outage. The committed pack verifies all 12 files. Full Python regressions exposed two existing/environment-sensitive failures: missing local `datalake/SIM3464_metadata.xml`, and a fresh `hazard_overlay.png` whose byte hash differs from the committed image. No backend or frozen pack was edited to hide these failures.
