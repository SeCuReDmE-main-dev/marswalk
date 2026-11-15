# src/marswalk/ — the engine room (you only need to visit, never to repair)

> *This is where I spend my nights. You should never have to fix anything here: if something below breaks your screen, it is my bug, and I want to know.*
> — Jean-Sébastien

## The map of the engine room

| Folder / file | What it does | Do you need it? |
|---|---|---|
| `contracts/models.py` | **The data contract.** Every field you receive is defined here, with its meaning, unit and allowed values. | Yes, as a **dictionary**: open it when you wonder what a field means. |
| `middleware/build_pack.py` | Downloads the NASA, JPL and USGS sources, builds `public_packs/jezero/v1/` and signs it. | No |
| `middleware/pack_loader.py` | Loads a pack and **refuses** it if one fingerprint, size or source does not match. | No |
| `middleware/query_service.py` | Finds the cell under a click and evaluates a drawn astronaut route. | Only if you use the live API |
| `middleware/api.py` | Optional web server (FastAPI) exposing the same data plus live endpoints (cell lookup, route evaluation, route planning, cameras). | Only if you use the live API |
| `middleware/cli.py` | The `marswalk-cli` command: `build-pack`, `verify-pack`, `export-schemas`. | No |
| `engine/` | The multi-scale terrain engine that reads the real HiRISE 1 m terrain model and writes the hazard grid (slopes, roughness, radio, radiation, effort, geology). | No |
| `engine/obstacles_m1.py`, `planner_m2.py`, `kinematics_m4.py`, `topographic_refuge_m3.py`, `m20_raw_images_m5.py` | The obstacle-aware route planner: detects scarps and formations of about 4 m and more on the terrain model, then plans a walk around them on a 10 m grid. Used by `POST /v1/sites/jezero/plan-route`. | Only if you use the live API |

## Static files or live API?

**Static files are the default**: faster, free to host, nothing to keep running. Use the live API only if you want what static files cannot do:

1. `GET /v1/sites/jezero/cell?lon=77.395&lat=18.465` returns the hazard cell under a click **and** the nearest real Perseverance stop.
   - A click outside the analysed window (`77.3767–77.4105° E`, `18.4478–18.4815° N`) returns the nearest edge cell for context only, with `verdict: "NO_GO"`, `confidence` `{t: 0, i: 1, f: 0}` and a reason starting with `FAIL_SAFE:`. Show it as "not analysed here".
2. `POST /v1/sites/jezero/evaluate-route` with `{"points": [[lon, lat], ...]}` (2 to 500 points) returns the total distance, walk-back distance, worst slopes, duration, radiation estimate, effort (W), oxygen margin, radio verdict, verdict and human reasons for a route the user draws.
   - Optional scenario switches: `spe_alert` (solar storm: always `NO_GO`), `dust_tau_880nm` (more dust never improves the verdict), `payload_kg`, `rf_link_margin_db`, `walking_speed_km_h`.
   - A point outside the window gives `NO_GO`. A segment is checked on every cell it crosses, not only at its ends.

3. `POST /v1/sites/jezero/plan-route` with `{"waypoints": [[lon, lat], ...]}` plans a walk that goes around scarps and rock formations, and returns the line, distance, walk-back, worst along-slope and cross-slope, effort, oxygen margin, radio check and verdict. Same scenario switches as above; with `spe_alert` the verdict is `NO_GO` and the line is the fastest return, with no detour.
4. `GET /v1/sites/jezero/waypoints/{sol}/cameras` lists rover camera frames for a stop (cached data only, unless the server operator enables live fetch).

### Safety behaviour you can rely on

- **Missing or broken data never gives `GO`.** The API answers HTTP 200 with `verdict: "NO_GO"` and a reason starting with `FAIL_SAFE:`. Show that reason as is.
- **Operator stop.** If `MARSWALK_SAFE_MODE=1` is set on the server, route evaluation always returns `NO_GO` ("SAFE_MODE: route planning disabled by operator") and `GET /health` shows `"safe_mode": true`. Map data stays available. Show a banner when `safe_mode` is true.

Run it locally:

```bash
pip install -e .
uvicorn marswalk.middleware.api:app --reload
```

Then open `http://127.0.0.1:8000/docs`: every endpoint is documented and testable from the browser. CORS is open for GET and POST, so your dev server can call it directly.
