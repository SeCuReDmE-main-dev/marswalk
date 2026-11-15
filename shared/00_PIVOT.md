# MarsWalk Shared Pivot (`shared/00_PIVOT.md`)

## [CONTRACT]
- **Status:** `FROZEN v1.0.0` (Mars Sphere `R = 3,396,190 m`, planetocentric East `lon/lat`)
- **Static Pack:** `public_packs/jezero/v1/` (`manifest.json`, `waypoints.geojson`, `route.geojson`, `hazard_grid.json`, `hazard_overlay.png`, `eva_constraints.json`)
- **Documentation:** `frontend/README.md` & `docs/contracts/10_CONTRAT_DONNEES.md`

## [ENGINE]
- `[2026-11-14T20:10:00Z] (@EbaAaZ / antigravity)`: Pass 1 complete (`12/12` pytest green, `500` concurrent requests `0` errors). All `708` real Perseverance waypoints (`Sol 13 -> Sol 2022` with ground-truth rover tilt & panorama links) and the `24x16` multi-scale hazard grid (`1m/4m/16m/64m`) are signed and committed in `public_packs/jezero/v1/`.

## [FRONTEND]
- `[2026-11-14T20:10:00Z] (@Maptop / codex+antigravity)`: Ready on branch `feat/ui`. Full creative ownership of `frontend/`, final product brand name, and `.spaceapps.earth` domain.
