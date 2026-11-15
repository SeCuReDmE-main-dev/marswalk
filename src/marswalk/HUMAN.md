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
| `middleware/api.py` | Optional web server (FastAPI) exposing the same data plus two live endpoints. | Only if you use the live API |
| `middleware/cli.py` | The `marswalk` command: `build-pack`, `verify-pack`, `export-schemas`. | No |
| `engine/` (coming in my next pass) | The multi-scale terrain engine that will replace the placeholder grid. | No |

## Static files or live API?

**Static files are the default**: faster, free to host, nothing to keep running. Use the live API only if you want two things that static files cannot do:

1. `GET /v1/sites/jezero/cell?lon=77.45&lat=18.44` returns the hazard cell under a click **and** the nearest real Perseverance stop.
2. `POST /v1/sites/jezero/evaluate-route` with `{"points": [[lon, lat], ...]}` (2 to 500 points) returns the total distance, walk-back distance, worst slopes at 1 m and 64 m, duration, radiation estimate, verdict and human reasons for a route the user draws.

Run it locally:

```bash
pip install -e .
uvicorn marswalk.middleware.api:app --reload
```

Then open `http://127.0.0.1:8000/docs`: every endpoint is documented and testable from the browser. CORS is open for GET and POST, so your dev server can call it directly.
