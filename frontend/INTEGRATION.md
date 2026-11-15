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

The static host must allow browser fetches/CORS and supply consistent bytes matching `manifest.files`. Static mode checks the four consumed JSON/GeoJSON payload digests and byte counts. It does not claim a cryptographic signature, scientific validation, or verification of unconsumed pack files.

## Change points

- `src/data/types.ts`: public `MarswalkDataSource` interface and combined UI data model.
- `src/data/source.ts`: shared static/API adapter, validation, hash checks and errors. All data requests are centralized here.
- `src/data/config.ts`: environment mapping. To connect another endpoint shape, adapt the source here/above rather than rewriting components.
- `src/data/generated/`: generated TypeScript contract DTOs. Run `npm run types:generate` after an agreed schema update; do not manually edit generated files or the shared schema.
- `src/domain.ts`: UI geometry, coverage containment, safe links, route-feature filtering and export helpers.
- `src/MapView.tsx`: geographic map presentation and callbacks; it does not fetch middleware data or evaluate routes.
- `src/App.tsx`: guide, selected entities, evidence panels and source dialogs.

The data source accepts an `AbortSignal` for cancellation. Requests fail visibly; the app does not silently switch API failures to an old static pack. The Reload data control fetches again.

## Scientific/display boundaries

- Cell, route and science-stop assessments are distinct. The browser displays their supplied verdicts and does not infer a verdict from the selected baseline.
- 1 m baseline is diagnostic only. 64/16/4 m controls compare actual slope values, not map zoom.
- Assessment rectangles derive from grid bbox, row and col. Outside that coverage returns Not assessed, not a nearest-cell verdict.
- Null matched tilt/rock fields remain Unavailable. Rover records are independently browsable; no per-cell ground-truth match is fabricated.
- Route features tagged BENCHMARK are excluded from the astronaut candidate/science-stop UI.
- Max distance from start is frontend-derived spherical distance over the supplied candidate vertices. It is not a traversable return-path distance. Original route notes and reference constraints remain visible separately.
- Quantities retain value, unit, tag, source_id and note. Source buttons resolve through the manifest. Radiation proxy notes are displayed.
- External tile geometry uses Leaflet EPSG:4326 with the geographic 2:1 WMTS grid; the map's distance function uses the Mars sphere, not Earth's radius.
- The local fallback backdrop is a coarse raster made from the actual grid elevations and labeled DERIVED. It is not high-resolution imagery. NASA tiles are a separate attributed layer.

## Deferred until middleware agreement

Arbitrary route drawing, route evaluation and automatic rerouting are intentionally not wired to `/cell` or `/evaluate-route`. Phase 3 middleware now includes segment traversal, outside-coverage handling and NO_GO propagation; the earlier frontend-branch concerns about those behaviors predate that update. Connecting editable routes still requires agreement on the current request parameters, response fields and user-facing scenario controls. The initial frontend inspects the supplied candidate. This keeps UI integration independent from the scientific engine work.

Contract 1.1.0 also supplies optional shadow, geology, area-of-applicability, calibrated opinion, sky-view and RF assessment fields. Their generated types are available for follow-up screens; the initial UI continues to display the original confidence vector and does not silently replace it with calibrated opinion or claim those additional panels are implemented.

The app is a planning/hackathon prototype, not astronaut navigation or NASA safety certification. No simulated live GPS, oxygen, weather or battery telemetry is shown.

## Build and validate

```powershell
npm test
npm run build
npm run preview
```

`dist/` is a static deployable frontend, including the copied pack. For subpath hosting, set `VITE_BASE_PATH=/your-path/` at build time; default pack/brand URLs follow that base. API config is compiled into the build, so rebuild after changing production URLs. No hosting account or deployment was created as part of this branch.

Automated tests exercise the real pack, tamper rejection, API endpoint mapping, malformed responses, source/scope safety, Mars distances, feature filtering and coverage. API adapter tests use a fetch mock returning the real contract payloads; they do not claim a running middleware integration test.
