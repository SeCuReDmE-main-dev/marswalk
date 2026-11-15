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

## The files

`manifest.json` signs ten files. The six you draw:

| File | What it is | Key fields for the UI | Real or simulated today |
|---|---|---|---|
| `manifest.json` | The pack's identity card and signature | `bbox` (the whole Jezero region), `crs`, `basemaps[0]` (Mars Trek tiles), `sources[]`, `files[]` | Real |
| `waypoints.geojson` | The **708 real Perseverance stops** (sol 13 → 2022) | `properties.sol`, `lon`, `lat`, `rover_tilt_deg`, `rover_pitch_deg`, `rover_roll_deg`, `elev_geoid_m`, `dist_total_m`, `panorama_url` | **MEASURED** |
| `route.geojson` | The rover's real traverse + a candidate astronaut walk + science stops | `properties.segment_type`, `tag`, `verdict`, `distance_m`, `max_slope_deg` | Traverse **MEASURED**, astronaut walk **SIMULATED** |
| `hazard_grid.json` | The multi-scale hazard grid | `grid_status`, `cell_size_m`, `rows`, `cols`, `baselines_m`, `cells[]` | See below |
| `hazard_overlay.png` | Transparent color image of the grid, aligned to `hazard_grid.bbox` | Drop it on the map as one image layer | Same status as the grid |
| `eva_constraints.json` | Human and rover limits, each with its source | `suit_max_slope_deg` (20°), `walkback_max_km` (2), `eva_duration_min_h` / `max_h` (4 / 8 h), `rock_cfa_ok_pct` / `rock_cfa_caution_pct` (7 / 15 %, rover), `gcr_dose_msv_per_day` | Sourced thresholds |

The other four are for audit, not for drawing: `validation_report.json` and `gate_log.jsonl` (how the engine decided), and `profiles/*.json` (the engine's frozen parameters).

## The hazard grid, honestly

- Read `grid_status` first. **Today (pack v1.1.0) it is `"ENGINE"`: 40 × 40 cells (1,600 cells of about 48 m) over a 2 × 2 km window of the delta front, slopes DERIVED from the real HiRISE 1 m terrain model with cos(φ) ground-metre scaling.**
  - The grid covers only `hazard_grid.bbox` (`77.3767–77.4105° E`, `18.4478–18.4815° N`), much smaller than `manifest.bbox`. Outside it there is **no** hazard information: show the area as "not analysed", never as safe.
  - `"PLACEHOLDER"` (older packs only): synthetic values. If you ever see it, show a "preview data" badge. **Never assume a cell size**: read `cell_size_m`.
- Verdicts today: 332 `GO`, 1,104 `CAUTION`, 164 `NO_GO`.
- Each cell: `cell_id`, `row`, `col`, `lon`, `lat`, `size_m`, `elev_m`, `slope_deg_by_baseline` (`"1"`, `"4"`, `"16"`, `"64"`), `scale_divergence`, `rock_cfa_pct`, `confidence {t, i, f}`, `verdict`, `reason`.
- The `"1"` slope baseline carries a `note`: on a 1 m terrain model it is mostly pixel noise, so the engine does not use it. Show the note; do not hide it.

### The v1.1.0 fields (optional, read the caveats)

| Field | What it means | Caveat to show |
|---|---|---|
| `rock_cfa_pct` | Rough estimate of the ground covered by rocks | A **heuristic** from the 1 m terrain model, not a rock count. It only raises uncertainty `i`; it never decides the verdict. 5 % means "below what orbit can detect", not "no rocks". |
| `rf_comms_verdict` | Can a suit radio (1.8 m) reach the rover mast (3.0 m) at 414.2 MHz from this cell? | Computed from the rover at the first science stop (Sol 413). Conservative: most cells behind the delta scarp are `NO_GO`. Separate from the terrain `verdict`. |
| `sky_view_factor` | Fraction of open sky above the cell | Terrain blocks only a few % of radiation dose. It is **not** a shelter for a solar storm. |
| `hurst_exponent_h`, `solar_shadow_fraction` | Roughness texture, shadowed fraction | Derived values, for experts. |
| `geologic_unit` | USGS SIM 3464 map unit | From the published geologic map. |
| `aoa_inside`, `calibrated_opinion` | Is this cell similar to places the rover actually visited, and the confidence learned from them | `aoa_inside = false` means the engine is extrapolating. Show it. |
| `external_layers_status` (grid level) | Which extra data layers were used | THEMIS, CRISM and MEDA are `UNAVAILABLE` today (uncertainty 1.0): no value is invented for them. |

Nothing from the route planner in progress (`obstacles.geojson`, planned routes) is in this pack yet.

## Coordinates

Longitude is **planetocentric, East-positive**, latitude planetocentric, on the Mars sphere of radius 3,396,190 m, the same frame as the NASA Mars Trek tiles. Jezero sits around 77.4° E, 18.4° N. No reprojection is needed between the pack and the Mars Trek tiles.
