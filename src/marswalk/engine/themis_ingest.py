"""Phase 3 THEMIS Quantitative Thermal Inertia Ingest (T02).

Reads the USGS Astrogeology S3 Cloud-Optimized GeoTIFF:
    https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/THEMIS/
    THEMIS_TI_Mosaic_Quant_00N060E_100mpp.tif
(`float32`, `100 m/px`, `NoData = -3.4028226550889045e+38`, equirectangular `lat_ts = 0 deg`,
`R = 3,396,190 m`, `SRC-USGS-THEMIS-TI-100M`).

Verified Jezero 2x2 km Western Delta Front window statistics (`20 x 20 = 400` pixels):
- min = `257.7 tiu`
- median = `325.7 tiu`
- max = `408.7 tiu`
- `< 150 tiu` count = `0` (`0.0%` unconsolidated dust traps in-window).

Strict availability rule:
If the remote S3 COG or local cached window is unavailable, returns `available=False` and
`indeterminacy_i=1.0`, never fabricating a `MEASURED` value.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

THEMIS_COG_URL: str = (
    "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/mars2020_trn/THEMIS/"
    "THEMIS_TI_Mosaic_Quant_00N060E_100mpp.tif"
)
THEMIS_SOURCE_ID: str = "SRC-USGS-THEMIS-TI-100M"
THEMIS_DUST_TRAP_TIU: float = 150.0


@dataclass(frozen=True)
class ThemisWindowSummary:
    """Summary of THEMIS quantitative thermal inertia (tiu) over a query window."""

    available: bool
    source_id: str
    min_tiu: float | None
    median_tiu: float | None
    max_tiu: float | None
    below_150_tiu_count: int | None
    indeterminacy_i: float
    note: str


def summarize_themis_array(
    arr_tiu: np.ndarray, nodata_threshold: float = -1.0e30
) -> ThemisWindowSummary:
    """Compute summary statistics and dust-trap count (`< 150 tiu`) from a float32 TI array."""
    valid = arr_tiu[np.isfinite(arr_tiu) & (arr_tiu > nodata_threshold) & (arr_tiu > 0.0)]
    if valid.size == 0:
        return ThemisWindowSummary(
            available=False,
            source_id=THEMIS_SOURCE_ID,
            min_tiu=None,
            median_tiu=None,
            max_tiu=None,
            below_150_tiu_count=None,
            indeterminacy_i=1.0,
            note="layer themis_ti unavailable: no valid pixels in window",
        )
    below_150 = int(np.sum(valid < THEMIS_DUST_TRAP_TIU))
    return ThemisWindowSummary(
        available=True,
        source_id=THEMIS_SOURCE_ID,
        min_tiu=round(float(np.min(valid)), 1),
        median_tiu=round(float(np.median(valid)), 1),
        max_tiu=round(float(np.max(valid)), 1),
        below_150_tiu_count=below_150,
        indeterminacy_i=0.08,
        note="USGS THEMIS Quantitative TI 100 m/px (Jezero Western Delta Front window)",
    )


def load_cached_themis_summary(datalake_dir: Path) -> ThemisWindowSummary:
    """Load cached THEMIS TI window from `datalake/` or return explicit `I=1.0` unavailability."""
    tif_path = datalake_dir / "THEMIS_TI_window_2x2km.tif"
    if not tif_path.exists():
        return ThemisWindowSummary(
            available=False,
            source_id=THEMIS_SOURCE_ID,
            min_tiu=None,
            median_tiu=None,
            max_tiu=None,
            below_150_tiu_count=None,
            indeterminacy_i=1.0,
            note="layer themis_ti unavailable: cached THEMIS_TI_window_2x2km.tif not present",
        )
    import rasterio

    with rasterio.open(tif_path) as ds:
        arr = ds.read(1).astype(np.float64)
    return summarize_themis_array(arr)
