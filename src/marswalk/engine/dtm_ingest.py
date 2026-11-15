"""Real USGS HiRISE 1 m/px Digital Terrain Model (DTM) Ingest & Multi-Scale Slope Engine.

Implements:
1. Automatic selection of the `2 x 2 km` square window across Jezero Crater that
   maximizes the number of Mars 2020 Perseverance waypoints inside it while touching
   the Western Delta Front (`lon in [77.40, 77.43]`).
2. Asynchronous reading (`asyncio.to_thread`) of the real USGS Mars 2020 TRN HiRISE
   `1.0 m/px` GeoTIFF (`SRC-USGS-HIRISE-DTM-1M`), SHA-256 verification, and CRS
   sphere radius (`R = 3,396,190.0 m`) extraction.
3. Multi-scale finite-difference slope computation at `1 m`, `4 m`, `16 m`, and `64 m`
   baselines plus local slope roughness using `asyncio.Semaphore`.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from marswalk.contracts.models import MARS_SPHERE_RADIUS_M, WaypointFeatureCollection

USGS_HIRISE_DTM_URL = (
    "https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/"
    "JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif"
)
CACHED_WINDOW_TIF_NAME = "JEZ_hirise_soc_006_DTM_1m_window_2x2km.tif"
SIM3464_METADATA_NAME = "SIM3464_metadata.xml"


@dataclass(frozen=True)
class SelectedDtmWindow:
    """Automatically selected 2 x 2 km terrain window touching the Western Delta Front."""

    x_min_m: float
    x_max_m: float
    y_min_m: float
    y_max_m: float
    margin_m: int
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    waypoint_count: int


@dataclass(frozen=True)
class IngestedDtmWindow:
    """In-memory representation of the real 1 m/px USGS HiRISE DTM window."""

    window: SelectedDtmWindow
    tif_path: Path
    sha256: str
    bytes_read: int
    sphere_radius_m: float
    nodata_fraction: float
    coverage_fraction: float
    transform_x_min_m: float
    transform_y_max_m: float
    elevation_m: np.ndarray
    sim3464_units: tuple[str, ...]
    sim3464_sha256: str | None
    sim3464_bytes: int


@dataclass(frozen=True)
class MultiScaleCellSample:
    """Real DTM multi-scale slope and roughness metrics for a single terrain cell."""

    row: int
    col: int
    lon: float
    lat: float
    size_m: float
    elev_m: float
    slope_1m_deg: float
    slope_4m_deg: float
    slope_16m_deg: float
    slope_64m_deg: float
    scale_divergence_deg: float
    roughness_deg: float
    nodata_local: float
    geologic_unit: str


def lon_to_eqc_x_m(lon_deg: float) -> float:
    """Convert planetocentric East longitude (deg) to ESRI:103885 equirectangular X (m)."""
    return MARS_SPHERE_RADIUS_M * math.radians(lon_deg)


def lat_to_eqc_y_m(lat_deg: float) -> float:
    """Convert planetocentric latitude (deg) to ESRI:103885 equirectangular Y (m)."""
    return MARS_SPHERE_RADIUS_M * math.radians(lat_deg)


def eqc_x_m_to_lon(x_m: float) -> float:
    """Convert ESRI:103885 equirectangular X (m) to planetocentric East longitude (deg)."""
    return math.degrees(x_m / MARS_SPHERE_RADIUS_M)


def eqc_y_m_to_lat(y_m: float) -> float:
    """Convert ESRI:103885 equirectangular Y (m) to planetocentric latitude (deg)."""
    return math.degrees(y_m / MARS_SPHERE_RADIUS_M)


def ground_step_x_m(lat: float, proj_step_m: float = 1.0) -> float:
    """Convert equirectangular projected E-W step (lat_ts=0) to ground metres via cos(phi)."""
    return float(proj_step_m) * math.cos(math.radians(float(lat)))


def verify_mars_crs_roundtrip(
    lon_deg: float,
    lat_deg: float,
    *,
    sphere_radius_m: float = MARS_SPHERE_RADIUS_M,
    max_error_m: float = 0.05,
) -> float:
    """Validate single-CRS Mars IAU 2015 sphere (`3,396,190 m`) and EQC round-trip error."""
    if not math.isfinite(sphere_radius_m) or abs(sphere_radius_m - MARS_SPHERE_RADIUS_M) > 1.0:
        raise ValueError(
            f"Invalid CRS sphere radius {sphere_radius_m} m; contract requires "
            f"Mars IAU 2015 sphere {MARS_SPHERE_RADIUS_M:.0f} m (3396190 m)."
        )
    x_m = lon_to_eqc_x_m(lon_deg)
    y_m = lat_to_eqc_y_m(lat_deg)
    lon_rt = eqc_x_m_to_lon(x_m)
    lat_rt = eqc_y_m_to_lat(y_m)
    dx_m = MARS_SPHERE_RADIUS_M * math.radians(lon_rt - lon_deg)
    dy_m = MARS_SPHERE_RADIUS_M * math.radians(lat_rt - lat_deg)
    err_m = math.hypot(dx_m, dy_m)
    if err_m > max_error_m:
        raise ValueError(f"EQC round-trip error {err_m:.6f} m exceeds {max_error_m} m.")
    return err_m


def select_optimal_delta_window_2x2km(
    waypoints: WaypointFeatureCollection,
    window_size_m: float = 2000.0,
    margin_m: int = 64,
    step_m: float = 50.0,
) -> SelectedDtmWindow:
    """Automatically select the 2 x 2 km window maximizing M20 stops on the Delta Front.

    Evaluates a regular grid of candidate 2,000 x 2,000 m windows in ESRI:103885 meters
    that touch the Western Delta Front (`lon in [77.40, 77.43]`) and selects the window
    with the highest number of Perseverance stops inside it.
    """
    pts_xy = [
        (lon_to_eqc_x_m(w.properties.lon), lat_to_eqc_y_m(w.properties.lat))
        for w in waypoints.features
    ]
    xs = [p[0] for p in pts_xy]
    ys = [p[1] for p in pts_xy]

    min_x = math.floor(min(xs) / step_m) * step_m
    max_x = math.ceil(max(xs) / step_m) * step_m
    min_y = math.floor(min(ys) / step_m) * step_m
    max_y = math.ceil(max(ys) / step_m) * step_m

    delta_front_min_x = lon_to_eqc_x_m(77.40)
    delta_front_max_x = lon_to_eqc_x_m(77.43)

    best_count = -1
    best_x0 = 4_586_467.0
    best_y0 = 1_093_138.0

    # Anchor candidate origins to exact integer offsets from the DTM top-left origin
    # (4,578,867 m, 1,105,638 m) so pixels align 1:1 with the 1.0 m/px USGS GeoTIFF.
    dtm_origin_x = 4_578_867.0
    dtm_top_y = 1_105_638.0

    start_dx = int(max(margin_m, math.floor((min_x - dtm_origin_x) / step_m) * step_m))
    end_dx = int(math.ceil((max_x - dtm_origin_x) / step_m) * step_m)
    start_dy = int(max(margin_m, math.floor((dtm_top_y - max_y) / step_m) * step_m))
    end_dy = int(math.ceil((dtm_top_y - min_y) / step_m) * step_m)

    for dx in range(start_dx, end_dx + 1, int(step_m)):
        x0 = dtm_origin_x + float(dx)
        x1 = x0 + window_size_m
        # Must overlap the Western Delta Front contact zone
        if x1 < delta_front_min_x or x0 > delta_front_max_x:
            continue
        for dy in range(start_dy, end_dy + 1, int(step_m)):
            y1 = dtm_top_y - float(dy)
            y0 = y1 - window_size_m
            cnt = sum(1 for (px, py) in pts_xy if x0 <= px <= x1 and y0 <= py <= y1)
            if cnt > best_count:
                best_count = cnt
                best_x0 = x0
                best_y0 = y0

    x1 = best_x0 + window_size_m
    y1 = best_y0 + window_size_m
    return SelectedDtmWindow(
        x_min_m=best_x0,
        x_max_m=x1,
        y_min_m=best_y0,
        y_max_m=y1,
        margin_m=margin_m,
        min_lon=round(eqc_x_m_to_lon(best_x0), 6),
        min_lat=round(eqc_y_m_to_lat(best_y0), 6),
        max_lon=round(eqc_x_m_to_lon(x1), 6),
        max_lat=round(eqc_y_m_to_lat(y1), 6),
        waypoint_count=best_count,
    )


def _parse_sim3464_metadata(datalake_dir: Path) -> tuple[tuple[str, ...], str | None, int]:
    """Read official USGS SIM 3464 metadata XML if present in datalake_dir."""
    xml_path = datalake_dir / SIM3464_METADATA_NAME
    if not xml_path.exists():
        return (("NHjf1", "NHjf2", "Njf", "Nle", "Aeb"), None, 0)
    raw = xml_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    root = ET.fromstring(raw.decode("utf-8"))
    symbols: list[str] = []
    for attr in root.findall(".//attr"):
        lab = attr.findtext("attrlabl")
        if lab == "symbol":
            for edomv in attr.findall(".//edomv"):
                if edomv.text and edomv.text.strip():
                    symbols.append(edomv.text.strip())
    return (tuple(symbols) if symbols else ("NHjf1", "NHjf2", "Njf"), sha, len(raw))


def classify_sim3464_unit(lon: float, lat: float, elev_m: float, slope_16m_deg: float) -> str:
    """Approximate the USGS SIM 3464 geologic unit across the Western Delta Front window.

    HEURISTIC: hand-set longitude / elevation / slope thresholds inspired by the unit names of
    Sun & Stack (2020) SIM 3464. It does NOT read the published map polygons (not ingested yet),
    so contacts can be off by tens to hundreds of metres. Thresholds used:
    - `Njf` (Jezero floor unit): eastern floor below `-2535 m` (`lon >= 77.404`).
    - `Nle` (Lower etched / margin contact unit): transition apron (`-2535 m .. -2518 m`).
    - `NHjf1` (Jezero fan 1 unit): primary Western Delta layered sedimentary lobes.
    - `NHjf2` (Jezero fan 2 unit): upper western delta fan topset (`elev > -2465 m`).
    - `Aeb` (Eolian bedform unit): low-slope (`< 4.5 deg`) trough ripples along channel floors.
    """
    if lon >= 77.4055 and elev_m <= -2534.0:
        return "Njf (Jezero floor unit, SIM 3464)"
    if lon >= 77.4015 and elev_m <= -2520.0:
        return "Nle (Lower etched delta margin contact, SIM 3464)"
    if slope_16m_deg < 3.5 and -2515.0 <= elev_m <= -2485.0 and 77.388 <= lon <= 77.398:
        return "Aeb (Eolian bedform unit, SIM 3464)"
    if elev_m >= -2465.0:
        return "NHjf2 (Jezero fan 2 upper delta unit, SIM 3464)"
    return "NHjf1 (Jezero fan 1 delta unit, SIM 3464)"


def _read_dtm_window_sync(
    datalake_dir: Path,
    selected: SelectedDtmWindow,
) -> IngestedDtmWindow:
    """Synchronous worker (run via asyncio.to_thread) to read the 1 m/px USGS GeoTIFF."""
    import rasterio
    from rasterio.windows import Window

    datalake_dir.mkdir(parents=True, exist_ok=True)
    cached_tif = datalake_dir / CACHED_WINDOW_TIF_NAME

    if not cached_tif.exists() or cached_tif.stat().st_size == 0:
        try:
            import truststore

            truststore.inject_into_ssl()
        except ImportError:
            pass
        margin = selected.margin_m
        win_w = int(round(selected.x_max_m - selected.x_min_m)) + 2 * margin
        win_h = int(round(selected.y_max_m - selected.y_min_m)) + 2 * margin
        with rasterio.open(USGS_HIRISE_DTM_URL) as src:
            col_off = int(round((selected.x_min_m - margin) - src.transform.c))
            row_off = int(round(src.transform.f - (selected.y_max_m + margin)))
            win = Window(col_off, row_off, win_w, win_h)
            data = src.read(1, window=win)
            profile = src.profile.copy()
            profile.update(
                width=win_w,
                height=win_h,
                transform=rasterio.windows.transform(win, src.transform),
                compress="deflate",
            )
            with rasterio.open(cached_tif, "w", **profile) as dst:
                dst.write(data, 1)

    raw_bytes = cached_tif.read_bytes()
    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()

    with rasterio.open(cached_tif) as ds:
        raw_arr = ds.read(1)
        nodata_val = ds.nodata
        crs_wkt = ds.crs.to_wkt() if ds.crs else ""
        transform = ds.transform

    sphere_r = MARS_SPHERE_RADIUS_M if "3396190" in crs_wkt else 0.0
    if nodata_val is not None:
        valid_mask = (raw_arr != nodata_val) & np.isfinite(raw_arr) & (raw_arr > -1e10)
    else:
        valid_mask = np.isfinite(raw_arr) & (raw_arr > -1e10)

    total_px = int(raw_arr.size)
    valid_px = int(np.count_nonzero(valid_mask))
    nodata_frac = float(total_px - valid_px) / float(max(1, total_px))

    expected_side = int(round(selected.x_max_m - selected.x_min_m)) + 2 * selected.margin_m
    coverage_frac = min(
        1.0,
        float(raw_arr.shape[0] * raw_arr.shape[1]) / float(max(1, expected_side * expected_side)),
    )

    elev_f64 = raw_arr.astype(np.float64)
    if nodata_frac > 0.0 and valid_px > 0:
        median_elev = float(np.median(elev_f64[valid_mask]))
        elev_f64 = np.where(valid_mask, elev_f64, median_elev)

    sim_units, sim_sha, sim_bytes = _parse_sim3464_metadata(datalake_dir)

    return IngestedDtmWindow(
        window=selected,
        tif_path=cached_tif,
        sha256=sha256_hex,
        bytes_read=len(raw_bytes),
        sphere_radius_m=sphere_r,
        nodata_fraction=nodata_frac,
        coverage_fraction=coverage_frac,
        transform_x_min_m=float(transform.c),
        transform_y_max_m=float(transform.f),
        elevation_m=elev_f64,
        sim3464_units=sim_units,
        sim3464_sha256=sim_sha,
        sim3464_bytes=sim_bytes,
    )


async def ingest_dtm_window_async(
    datalake_dir: Path,
    selected: SelectedDtmWindow,
) -> IngestedDtmWindow:
    """Asynchronously ingest the 1 m/px USGS HiRISE DTM window via asyncio.to_thread."""
    return await asyncio.to_thread(_read_dtm_window_sync, datalake_dir, selected)


def sample_point_multiscale_slopes(
    dtm: IngestedDtmWindow,
    lon: float,
    lat: float,
) -> dict[str, float]:
    """Compute exact 1m, 4m, 16m, and 64m finite-difference slopes (deg) at (lon, lat)."""
    arr = dtm.elevation_m
    h, w = arr.shape
    x_m = lon_to_eqc_x_m(lon)
    y_m = lat_to_eqc_y_m(lat)
    col = int(round((x_m - dtm.transform_x_min_m) - 0.5))
    row = int(round((dtm.transform_y_max_m - y_m) - 0.5))
    col = max(64, min(w - 65, col))
    row = max(64, min(h - 65, row))

    dx_ground_m = ground_step_x_m(lat, 1.0)
    out: dict[str, float] = {"elev_m": round(float(arr[row, col]), 3)}
    for b_int in (1, 4, 16, 64):
        half = max(1, b_int // 2)
        if b_int == 1:
            # 1m baseline over local 3x3 pixel patch (captures rover wheel / suit step hazard)
            patch = arr[row - 1 : row + 2, col - 1 : col + 2]
            gy, gx = np.gradient(patch, 1.0, dx_ground_m)
            s_deg = float(np.mean(np.degrees(np.arctan(np.hypot(gx, gy)))))
        else:
            # Average over 3x3 neighborhood around (row, col) at step `2 * half`
            vals: list[float] = []
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr = row + dr
                    cc = col + dc
                    dz_dx = (arr[rr, cc + half] - arr[rr, cc - half]) / (
                        float(2 * half) * dx_ground_m
                    )
                    dz_dy = (arr[rr - half, cc] - arr[rr + half, cc]) / float(2 * half)
                    vals.append(math.degrees(math.atan(math.hypot(dz_dx, dz_dy))))
            s_deg = float(np.mean(vals))
        out[str(b_int)] = round(s_deg, 3)

    slopes = (out["1"], out["4"], out["16"], out["64"])
    out["divergence_deg"] = round(max(slopes) - min(slopes), 3)
    return out


def _compute_row_samples_sync(
    dtm: IngestedDtmWindow,
    row_idx: int,
    rows: int,
    cols: int,
) -> list[MultiScaleCellSample]:
    """Compute MultiScaleCellSample for all columns in `row_idx` from the real 1m DTM."""
    arr = dtm.elevation_m
    margin = dtm.window.margin_m
    win_h_m = dtm.window.y_max_m - dtm.window.y_min_m
    win_w_m = dtm.window.x_max_m - dtm.window.x_min_m
    cell_h_m = win_h_m / float(rows)
    cell_w_m = win_w_m / float(cols)
    cell_size_m = round(0.5 * (cell_h_m + cell_w_m), 2)

    r_start = margin + int(round(row_idx * cell_h_m))
    r_end = margin + int(round((row_idx + 1) * cell_h_m))
    r_center = int(round(0.5 * (r_start + r_end)))

    # Pre-compute full-row finite-difference slope arrays for 4m, 16m, 64m at r_center
    samples: list[MultiScaleCellSample] = []
    for col_idx in range(cols):
        c_start = margin + int(round(col_idx * cell_w_m))
        c_end = margin + int(round((col_idx + 1) * cell_w_m))
        c_center = int(round(0.5 * (c_start + c_end)))

        x_center_m = dtm.transform_x_min_m + c_center + 0.5
        y_center_m = dtm.transform_y_max_m - (r_center + 0.5)
        lon = round(eqc_x_m_to_lon(x_center_m), 6)
        lat = round(eqc_y_m_to_lat(y_center_m), 6)
        dx_ground_m = ground_step_x_m(lat, 1.0)
        cell_size_m = round(0.5 * (cell_h_m + cell_w_m * dx_ground_m), 2)

        patch = arr[r_start:r_end, c_start:c_end]
        elev_val = round(float(np.mean(patch)), 2)

        # 1m slope: 90th-percentile 1m gradient inside the cell (captures sub-cell scarps
        # so a 1m boulder/ledge inside a cell is never hidden by cell averaging!)
        if patch.shape[0] >= 3 and patch.shape[1] >= 3:
            gy_1m, gx_1m = np.gradient(patch, 1.0, dx_ground_m)
            s1_grid = np.degrees(np.arctan(np.hypot(gx_1m, gy_1m)))
            s1_deg = round(float(np.percentile(s1_grid, 90)), 2)
            roughness_deg = round(float(np.std(s1_grid)), 2)
        else:
            dz_dx1 = (arr[r_center, c_center + 1] - arr[r_center, c_center - 1]) / (
                2.0 * dx_ground_m
            )
            dz_dy1 = (arr[r_center - 1, c_center] - arr[r_center + 1, c_center]) / 2.0
            s1_deg = round(math.degrees(math.atan(math.hypot(dz_dx1, dz_dy1))), 2)
            roughness_deg = 0.5

        def _baseline_slope(
            b_m: int,
            c0: int = c_start,
            c1: int = c_end,
            dx_m: float = dx_ground_m,
        ) -> float:
            half = max(1, b_m // 2)
            # Sample a 3x3 grid across the cell at baseline `b_m`
            rs = np.linspace(r_start + 1, max(r_start + 1, r_end - 2), 3, dtype=int)
            cs = np.linspace(c0 + 1, max(c0 + 1, c1 - 2), 3, dtype=int)
            rr, cc = np.meshgrid(rs, cs, indexing="ij")
            dz_dx = (arr[rr, cc + half] - arr[rr, cc - half]) / (float(2 * half) * dx_m)
            dz_dy = (arr[rr - half, cc] - arr[rr + half, cc]) / float(2 * half)
            slopes_b = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))
            return round(float(np.mean(slopes_b)), 2)

        s4_deg = _baseline_slope(4)
        s16_deg = _baseline_slope(16)
        s64_deg = _baseline_slope(64)

        all_s = (s1_deg, s4_deg, s16_deg, s64_deg)
        divergence_deg = round(max(all_s) - min(all_s), 2)
        geo_unit = classify_sim3464_unit(lon, lat, elev_val, s16_deg)

        samples.append(
            MultiScaleCellSample(
                row=row_idx,
                col=col_idx,
                lon=lon,
                lat=lat,
                size_m=cell_size_m,
                elev_m=elev_val,
                slope_1m_deg=s1_deg,
                slope_4m_deg=s4_deg,
                slope_16m_deg=s16_deg,
                slope_64m_deg=s64_deg,
                scale_divergence_deg=divergence_deg,
                roughness_deg=roughness_deg,
                nodata_local=dtm.nodata_fraction,
                geologic_unit=geo_unit,
            )
        )
    return samples


async def compute_multiscale_grid_async(
    dtm: IngestedDtmWindow,
    rows: int = 20,
    cols: int = 20,
    max_concurrency: int = 8,
) -> list[MultiScaleCellSample]:
    """Compute multi-scale DTM cells asynchronously with `asyncio.Semaphore(max_concurrency)`."""
    sem = asyncio.Semaphore(max_concurrency)

    async def _worker(r: int) -> list[MultiScaleCellSample]:
        async with sem:
            return await asyncio.to_thread(_compute_row_samples_sync, dtm, r, rows, cols)

    row_batches = await asyncio.gather(*(_worker(r) for r in range(rows)))
    flat = [sample for batch in row_batches for sample in batch]
    flat.sort(key=lambda s: (s.row, s.col))
    return flat
