# Frontend Integration Guide (`frontend/README.md`)

Welcome **Philippe (`@Maptop`)**!  
You have **100% creative and technical ownership** of `frontend/` (`feat/ui` branch) — framework, map library, visual style, and the final product brand name & `.spaceapps.earth` domain name.

Everything you need to render the Jezero Crater map, the **708 real Perseverance stops**, the multi-scale hazard grid (`1 m / 4 m / 16 m / 64 m`), and the EVA route is already pre-computed, validated, and committed as static files inside [`../public_packs/jezero/v1/`](../public_packs/jezero/v1/). **You do not need to run Python or a backend server to build or deploy the UI.**

---

## 1. Load the Entire Pack in 10 Lines of JavaScript

Copy or serve `public_packs/jezero/v1/` from your public static directory (or fetch it from the repo root during dev):

```javascript
const PACK_BASE = "/public_packs/jezero/v1";

export async function loadJezeroPack() {
  const [manifest, waypoints, route, hazards, constraints] = await Promise.all([
    fetch(`${PACK_BASE}/manifest.json`).then((r) => r.json()),
    fetch(`${PACK_BASE}/waypoints.geojson`).then((r) => r.json()),
    fetch(`${PACK_BASE}/route.geojson`).then((r) => r.json()),
    fetch(`${PACK_BASE}/hazard_grid.json`).then((r) => r.json()),
    fetch(`${PACK_BASE}/eva_constraints.json`).then((r) => r.json()),
  ]);
  return { manifest, waypoints, route, hazards, constraints };
}
```

---

## 2. NASA Mars Trek 25 cm HiRISE Basemap Tiles (Important Projection Note!)

The official NASA Mars Trek HiRISE `25 cm/px` orthomosaic for Jezero Crater is pre-configured in `manifest.basemaps[0]`:

- **Tile URL Template:**
  ```text
  https://trek.nasa.gov/tiles/Mars/EQ/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd/1.0.0/default/default028mm/{z}/{row}/{col}.png
  ```
- **Zoom Levels:** `0` to `17`
- **Jezero Bounding Box (`[minLon, minLat, maxLon, maxLat]`):** `[77.223, 18.307, 77.584, 18.669]`
- **Heads-Up on Tile Grid (`geographic_2to1_256px`):**
  Mars Trek serves tiles on a **2:1 Equirectangular / Geographic grid (`EPSG:4326` style, `{z}/{row}/{col}`, where `{row}` is `y` and `{col}` is `x`)**, **not** Web Mercator (`EPSG:3857`):
  - **Leaflet (`L.CRS.EPSG4326`)**, **OpenLayers (`EPSG:4326`)**, or **CesiumJS (`GeographicTilingScheme`)** display these tiles natively out of the box (note `{y}` = `{row}` and `{x}` = `{col}`).
  - **MapLibre GL JS** assumes Web Mercator (`EPSG:3857`) by default and requires a custom raster/canvas reprojection or deck.gl `BitmapLayer` workaround for geographic WMTS grids.
- **Instant Hazard Image Overlay (`hazard_overlay.png`):**
  `public_packs/jezero/v1/hazard_overlay.png` is a transparent RGBA heatmap aligned to `hazards.bbox` (`[minLon, minLat, maxLon, maxLat]`). You can drop it onto any map as a single `ImageOverlay` / `BitmapLayer` in 3 lines of code!

---

## 3. Key Data Highlights for the UI & Judges

1. **708 Real Perseverance Stops (`waypoints.geojson`):**
   - Every feature has `properties.sol` (`13 → 2022`), `elev_geoid_m.value`, **`rover_tilt_deg.value` (actual tilt measured by the rover on the ground!)**, `rover_pitch_deg.value`, `rover_roll_deg.value`, `dist_total_m.value`, and `panorama_url` (direct link to the ground panorama image at that stop).
2. **The "Scale Gap" Hook (`hazard_grid.json`):**
   - Each cell has `slope_deg_by_baseline["1"]`, `["4"]`, `["16"]`, and `["64"]` plus `scale_divergence`.
   - When the user switches between `64 m` (coarse orbital view) and `1 m` (fine scale) or clicks a Perseverance waypoint, they can see **where the coarse orbital map looks flat (`GO`) while the meter-scale slope or measured rover tilt spikes (`CAUTION` / `NO_GO`)**.
3. **UI Wording Rule:**
   - Every cell has `confidence: { t, i, f }` and `verdict: "GO" | "CAUTION" | "NO_GO"` plus a human-readable `reason`.
   - On screen, label `{ t, i, f }` simply as **Confidence** (Agreement `t`, Scale Uncertainty `i`, Hazard Risk `f`) alongside the **GO / CAUTION / NO_GO** badge and the **`MEASURED` / `DERIVED` / `SIMULATED`** data tag.
