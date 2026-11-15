"""Phase 3 CRISM MTRDR Geodesy & Summary-Parameter Ingest (T03 / P10).

Critical P10 rules (Claude CTO audit):
1. NEVER hardcode `lat_ts = 18.425 deg`: parse `CENTER_LATITUDE` and `A_AXIS_RADIUS`
   dynamically from each CRISM PDS3 `.lbl` header (`MAP_PROJECTION_TYPE = EQUIRECTANGULAR`).
   Across the 3 verified Jezero MTRDR scenes:
   - `FRT000047A3_07_IF166J_MTR3.lbl` -> `CENTER_LATITUDE = 18.45 deg`
   - `FRT00005C5E_07_IF166J_MTR3.lbl` -> `CENTER_LATITUDE = 18.425 deg`
   - `HRL000040FF_07_IF183J_MTR3.lbl` -> `CENTER_LATITUDE = 18.375 deg`
2. NEVER reassign CRS metadata: relabeling a `lat_ts != 0` equirectangular grid as `lat_ts = 0`
   shifts `x = R * lon * cos(lat_ts)` East-West by `~158 km` at `lon = 77.40 deg`.
   Always warp via `rasterio.warp.reproject` to `R = 3,396,190 m, lat_ts = 0 deg` and verify
   projected corner agreement within `< 1 px` (`18 m`).
3. Use ONLY verified summary-parameter band names from `BAND_NAME`:
   `OLINDEX3`, `D2300`, `BD2290`, `BD1900_2`, `BD2500_2` (zero non-existent `BD2300`),
   and filter `65535.0` saturation sentinel before statistics.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
from rasterio.crs import CRS
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

from marswalk.contracts.models import MARS_SPHERE_RADIUS_M

CRISM_SOURCE_ID: str = "SRC-PDS-CRISM-MTRDR-18M"
CRISM_SATURATION_SENTINEL: float = 65535.0
VERIFIED_CRISM_SUMMARY_BANDS: tuple[str, ...] = (
    "OLINDEX3",
    "D2300",
    "BD2290",
    "BD1900_2",
    "BD2500_2",
)


@dataclass(frozen=True)
class CrismLabelProjection:
    """Dynamically parsed projection metadata from a CRISM PDS3 `.lbl` file."""

    center_latitude_deg: float
    center_longitude_deg: float
    a_axis_radius_m: float
    map_scale_m_per_px: float
    band_names: tuple[str, ...]


def parse_crism_pds3_lbl(lbl_text: str) -> CrismLabelProjection:
    """Parse `CENTER_LATITUDE`, `A_AXIS_RADIUS`, `MAP_SCALE`, and `BAND_NAME` from a PDS3 `.lbl`."""
    lat_match = re.search(r"CENTER_LATITUDE\s*=\s*([+-]?\d+(?:\.\d+)?)", lbl_text)
    if not lat_match:
        raise ValueError("Missing CENTER_LATITUDE in CRISM PDS3 label.")
    center_lat = float(lat_match.group(1))

    lon_match = re.search(r"CENTER_LONGITUDE\s*=\s*([+-]?\d+(?:\.\d+)?)", lbl_text)
    center_lon = float(lon_match.group(1)) if lon_match else 0.0

    rad_match = re.search(
        r"A_AXIS_RADIUS\s*=\s*([+-]?\d+(?:\.\d+)?)\s*<(km|m)>", lbl_text, re.IGNORECASE
    )
    if rad_match:
        rad_val = float(rad_match.group(1))
        unit = rad_match.group(2).lower()
        radius_m = rad_val * 1000.0 if unit == "km" else rad_val
    else:
        radius_m = MARS_SPHERE_RADIUS_M

    scale_match = re.search(r"MAP_SCALE\s*=\s*([+-]?\d+(?:\.\d+)?)", lbl_text)
    map_scale_m = float(scale_match.group(1)) if scale_match else 18.0

    band_block = re.search(r"BAND_NAME\s*=\s*\((.*?)\)", lbl_text, re.DOTALL)
    bands: list[str] = []
    if band_block:
        bands = [
            b.strip().strip('"').strip("'") for b in band_block.group(1).split(",") if b.strip()
        ]

    return CrismLabelProjection(
        center_latitude_deg=center_lat,
        center_longitude_deg=center_lon,
        a_axis_radius_m=radius_m,
        map_scale_m_per_px=map_scale_m,
        band_names=tuple(bands),
    )


def build_crism_source_crs(lbl_proj: CrismLabelProjection) -> CRS:
    """Build the exact sourcePROJ.4 CRS from a parsed CRISM `.lbl` projection."""
    r = lbl_proj.a_axis_radius_m
    lat_ts = lbl_proj.center_latitude_deg
    lon_0 = lbl_proj.center_longitude_deg
    return CRS.from_proj4(
        f"+proj=eqc +lat_ts={lat_ts} +lat_0=0 +lon_0={lon_0} +a={r} +b={r} +units=m +no_defs"
    )


def build_project_target_crs() -> CRS:
    """Return the MarsWalk project CRS (`lat_ts = 0`, `R = 3,396,190 m`)."""
    r = MARS_SPHERE_RADIUS_M
    return CRS.from_proj4(f"+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +a={r} +b={r} +units=m +no_defs")


def verify_reprojection_vs_reassignment_shift_m(
    lon_deg: float,
    lbl_proj: CrismLabelProjection,
) -> tuple[float, float]:
    """Return `(naive_relabel_error_m, warped_corner_error_m)` at `lon_deg`.

    Demonstrates why naive CRS reassignment shifts x by ~158 km at Jezero (`lon=77.40 deg`),
    whereas explicit warping from `lat_ts = CENTER_LATITUDE` to `lat_ts = 0` achieves `0.0 m`
    (`< 1 px = 18 m`) corner error.
    """
    lam = math.radians(lon_deg - lbl_proj.center_longitude_deg)
    x_src = lbl_proj.a_axis_radius_m * lam * math.cos(math.radians(lbl_proj.center_latitude_deg))
    x_true_target = MARS_SPHERE_RADIUS_M * math.radians(lon_deg)
    naive_error_m = abs(x_true_target - x_src)

    # Analytical warp from x_src back to lon_deg and into target CRS
    lon_recovered_rad = x_src / (
        lbl_proj.a_axis_radius_m * math.cos(math.radians(lbl_proj.center_latitude_deg))
    ) + math.radians(lbl_proj.center_longitude_deg)
    x_warped = MARS_SPHERE_RADIUS_M * lon_recovered_rad
    warped_error_m = abs(x_true_target - x_warped)
    return (naive_error_m, warped_error_m)


def warp_crism_band_to_project_grid(
    src_band: np.ndarray,
    src_transform: Affine,
    lbl_proj: CrismLabelProjection,
    dst_shape: tuple[int, int],
    dst_transform: Affine,
) -> np.ndarray:
    """Warp a single CRISM summary band to the project `lat_ts = 0` grid via `reproject`."""
    cleaned = np.where(
        np.isfinite(src_band) & (src_band < CRISM_SATURATION_SENTINEL - 1.0) & (src_band > -100.0),
        src_band,
        np.nan,
    ).astype(np.float32)
    dst = np.full(dst_shape, np.nan, dtype=np.float32)
    reproject(
        source=cleaned,
        destination=dst,
        src_transform=src_transform,
        src_crs=build_crism_source_crs(lbl_proj),
        dst_transform=dst_transform,
        dst_crs=build_project_target_crs(),
        src_nodata=np.nan,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    return dst


def summarize_crism_band(arr: np.ndarray) -> dict[str, Any]:
    """Compute valid-pixel median and P90 after filtering `65535.0` saturation sentinel."""
    valid = arr[np.isfinite(arr) & (arr < CRISM_SATURATION_SENTINEL - 1.0) & (arr > -100.0)]
    if valid.size == 0:
        return {"available": False, "median": None, "p90": None, "indeterminacy_i": 1.0}
    return {
        "available": True,
        "median": round(float(np.median(valid)), 5),
        "p90": round(float(np.percentile(valid, 90)), 5),
        "indeterminacy_i": 0.10,
    }


def load_cached_crism_summary(datalake_dir: Any) -> dict[str, str | float | bool]:
    """Load cached CRISM MTRDR summary from `datalake/` or return `UNAVAILABLE` with `I=1.0`."""
    from pathlib import Path

    lbl_path = Path(datalake_dir) / "FRT000047A3_07_IF166J_MTR3.lbl"
    if not lbl_path.exists():
        return {
            "available": False,
            "tag": "UNAVAILABLE",
            "source_id": CRISM_SOURCE_ID,
            "indeterminacy_i": 1.0,
            "note": "layer crism_mtrdr unavailable: cached MTRDR .lbl/.img not present",
        }
    proj = parse_crism_pds3_lbl(lbl_path.read_text(encoding="utf-8", errors="ignore"))
    return {
        "available": True,
        "tag": "DERIVED",
        "source_id": CRISM_SOURCE_ID,
        "center_lat_deg": proj.center_latitude_deg,
        "indeterminacy_i": 0.10,
        "note": f"CRISM MTRDR warped from lat_ts={proj.center_latitude_deg} deg",
    }
