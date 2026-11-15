# public_packs/ — the data you draw (read only)

> *Every number in here can be traced back to a NASA, JPL or USGS source, or it says loudly that it is simulated. That promise is the whole project.*
> — Jean-Sébastien

`public_packs/jezero/v1/` is a **signed static data pack**. The Python builder writes it, `manifest.json` lists every file with its SHA-256 fingerprint and size, and the tests refuse any pack where one byte changed.

**Do not edit these files by hand.** A single change breaks the signature, and the tests (and the API) will reject the pack. If you need a field, ask me through a handoff.

You can copy the folder into your app's public directory, or fetch it from the repository during development.

---

## Every value is a `Quantity`

Almost every number is wrapped like this:

```json
{ "value": 1.182, "unit": "deg", "tag": "MEASURED", "source_id": "SRC-M20-WAYPOINTS", "note": null }
```

- `value`: the number to display.
- `unit`: always show it.
- `tag`: `MEASURED` (a real instrument), `DERIVED` (computed from real data by my engine), `SIMULATED` (a placeholder or model, never presented as real).
- `source_id`: points into `manifest.json` → `sources[]`, where you find the title, mission, URL, license and citation. Perfect for a "source" tooltip.
- `note`: an optional human explanation.

---

## The six files

| File | What it is | Key fields for the UI | Real or simulated today |
|---|---|---|---|
| `manifest.json` | The pack's identity card and signature | `bbox`, `crs`, `basemaps[0]` (Mars Trek tiles), `sources[]`, `files[]` | Real |
| `waypoints.geojson` | The **708 real Perseverance stops** (sol 13 → 2022) | `properties.sol`, `lon`, `lat`, `rover_tilt_deg`, `rover_pitch_deg`, `rover_roll_deg`, `elev_geoid_m`, `dist_total_m`, `panorama_url` | **MEASURED** |
| `route.geojson` | The rover's real traverse + a candidate astronaut walk + science stops | `properties.segment_type`, `tag`, `verdict`, `distance_m`, `max_slope_deg` | Traverse **MEASURED**, astronaut walk **SIMULATED** |
| `hazard_grid.json` | The multi-scale hazard grid | `grid_status`, `cell_size_m`, `rows`, `cols`, `baselines_m`, `cells[]` | See below |
| `hazard_overlay.png` | Transparent color image of the grid, aligned to `hazard_grid.bbox` | Drop it on the map as one image layer | Same status as the grid |
| `eva_constraints.json` | Human and rover limits, each with its source | `suit_max_slope_deg` (20°), `walkback_max_km` (2), `eva_duration_min_h` / `max_h`, `gcr_dose_msv_per_day` | Sourced thresholds |

## The hazard grid, honestly

- Read `grid_status` first.
  - `"PLACEHOLDER"`: values are **synthetic** (`source_id: "synthetic-v1"`), made so you can build the UI tonight. Cells are large (about 600 m). Show a "preview data" badge.
  - `"ENGINE"`: values come from my multi-scale engine reading the real HiRISE 1 m terrain model. Cells will be much smaller, so **never assume a cell size**.
- Each cell: `cell_id`, `row`, `col`, `lon`, `lat`, `size_m`, `elev_m`, `slope_deg_by_baseline` (`"1"`, `"4"`, `"16"`, `"64"`), `scale_divergence`, `confidence {t, i, f}`, `verdict`, `reason`.
- A baseline can be marked unreliable in a future pack (for example the 1 m slope on a 1 m terrain model is mostly pixel noise). If that happens, it keeps its key but its `note` explains why. Show the note; do not hide it.

## Coordinates

Longitude is **planetocentric, East-positive**, latitude planetocentric, on the Mars sphere of radius 3,396,190 m, the same frame as the NASA Mars Trek tiles. Jezero sits around 77.4° E, 18.4° N. No reprojection is needed between the pack and the Mars Trek tiles.
