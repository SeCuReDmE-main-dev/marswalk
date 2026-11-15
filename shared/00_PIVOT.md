# MarsWalk Shared Pivot (`shared/00_PIVOT.md`)

## [CONTRACT]
- **Status:** `FROZEN v1.0.0` / `pack_version 1.0.1` (Mars Sphere `R = 3,396,190 m`, planetocentric East `lon/lat`)
- **Static Pack:** `public_packs/jezero/v1/` (`manifest.json`, `waypoints.geojson`, `route.geojson`, `hazard_grid.json`, `hazard_overlay.png`, `eva_constraints.json`)
- **Documentation:** `frontend/README.md` & `docs/contracts/10_CONTRAT_DONNEES.md`

## [ENGINE]
- `[2026-11-14T20:30:00-05:00] (jean / antigravity)`: Pass 1 + Phase 2a honesty fix complete. All `708` real Perseverance waypoints (`Sol 13 -> Sol 2022` with `MEASURED` rover tilt & panorama links) and the `45.2 km` traverse (`MEASURED`) are signed in `public_packs/jezero/v1/`. The `24x16` hazard grid is explicitly tagged `SIMULATED` (`source_id="synthetic-v1"`, `grid_status="PLACEHOLDER"`) with zero `rover_tilt_deg` leakage while Pass 2 builds the real HiRISE DTM engine.

## [FRONTEND]
- `[2026-11-14T20:30:00-05:00] (teammate / codex+antigravity)`: Ready on branch `feat/ui`. Full creative ownership of `frontend/`, final product brand name, and `.spaceapps.earth` domain.
