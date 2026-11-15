"""Block B0 Tests: Boolean Prefilter (5 binary cases + B10 nodata) and G1 Gate Isolation."""

from __future__ import annotations

import asyncio
import inspect
import math

from marswalk.engine import gates
from marswalk.engine.prefilter import prefilter_cell, prefilter_scale


def test_prefilter_case1_nodata_and_nan() -> None:
    """Attack: DTM with 30% nodata or NaN must be caught cleanly before T/I/F (B10)."""
    res_nan = prefilter_cell(
        lon=77.39,
        lat=18.46,
        bbox=(77.37, 18.44, 77.42, 18.49),
        slope_deg=float("nan"),
        nodata_fraction=0.0,
        source_id="SRC-USGS-HIRISE-DTM-1M",
    )
    assert res_nan["keep"] is False
    assert "nan" in res_nan["reason"].lower() or "nodata" in res_nan["reason"].lower()
    assert res_nan["verdict"] in ("CAUTION", "NO_GO")

    res_nodata30 = prefilter_cell(
        lon=77.39,
        lat=18.46,
        bbox=(77.37, 18.44, 77.42, 18.49),
        slope_deg=6.5,
        nodata_fraction=0.30,
        source_id="SRC-USGS-HIRISE-DTM-1M",
    )
    assert res_nodata30["keep"] is False
    assert "nodata" in res_nodata30["reason"].lower()
    assert res_nodata30["verdict"] == "CAUTION"


def test_prefilter_case2_out_of_bbox() -> None:
    """Out-of-bbox coordinates are rejected before T/I/F."""
    res = prefilter_cell(
        lon=78.50,
        lat=18.46,
        bbox=(77.37, 18.44, 77.42, 18.49),
        slope_deg=4.0,
        nodata_fraction=0.0,
        source_id="SRC-USGS-HIRISE-DTM-1M",
    )
    assert res["keep"] is False
    assert "bbox" in res["reason"].lower()
    assert res["verdict"] == "NO_GO"


def test_prefilter_case3_scale_below_twice_dtm_resolution() -> None:
    """Attack: 1m baseline on a 1m/px DTM (< 2x resolution) is rejected as pixel noise."""
    s1 = prefilter_scale(baseline_m=1.0, dtm_resolution_m=1.0)
    assert s1["keep"] is False
    assert "2" in s1["reason"] or "resolution" in s1["reason"].lower()

    s4 = prefilter_scale(baseline_m=4.0, dtm_resolution_m=1.0)
    assert s4["keep"] is True


def test_prefilter_case4_unadmitted_source() -> None:
    """Unadmitted upstream source_id is rejected before T/I/F."""
    res = prefilter_cell(
        lon=77.39,
        lat=18.46,
        bbox=(77.37, 18.44, 77.42, 18.49),
        slope_deg=4.0,
        nodata_fraction=0.0,
        source_id="UNKNOWN-UNVERIFIED-BLOG",
    )
    assert res["keep"] is False
    assert "source" in res["reason"].lower()
    assert res["verdict"] == "NO_GO"


def test_prefilter_case5_cliff_over_45_deg_direct_nogo() -> None:
    """Slope > 45 deg is immediately classified as a cliff (NO_GO) without entering T/I/F."""
    res = prefilter_cell(
        lon=77.39,
        lat=18.46,
        bbox=(77.37, 18.44, 77.42, 18.49),
        slope_deg=48.2,
        nodata_fraction=0.0,
        source_id="SRC-USGS-HIRISE-DTM-1M",
    )
    assert res["keep"] is False
    assert "cliff" in res["reason"].lower()
    assert res["verdict"] == "NO_GO"

    # Valid gradual cell passes prefilter
    ok = prefilter_cell(
        lon=77.39,
        lat=18.46,
        bbox=(77.37, 18.44, 77.42, 18.49),
        slope_deg=12.4,
        nodata_fraction=0.02,
        source_id="SRC-USGS-HIRISE-DTM-1M",
    )
    assert ok["keep"] is True
    assert ok["verdict"] is None


def test_g1_does_not_emit_terrain_tif() -> None:
    """Verify M3: G1 gate produces PASS/HOLD/BLOCK without fabricating terrain T/I/F."""
    src = inspect.getsource(gates.gate_g1_classify)
    # Ensure arbitrary magic constants (0.30 + (...)/10.0) were removed
    assert "/ 10.0" not in src
    assert "0.95" not in src

    async def _check() -> None:
        cfg = {
            "max_validation_mae_deg": 4.5,
            "max_mean_cell_i": 0.35,
            "max_cell_step_m": 8.0,
        }
        v_pass = await gates.gate_g1_classify(
            {"cell_step_m": 8.0, "mean_cell_i": 0.18, "validation_test_mae_deg": 1.65},
            cfg,
        )
        assert v_pass.decision == "PASS"
        assert "ConfidenceVector" not in repr(v_pass)

        v_block = await gates.gate_g1_classify(
            {"cell_step_m": 8.0, "mean_cell_i": 0.18, "validation_test_mae_deg": 6.20},
            cfg,
        )
        assert v_block.decision == "BLOCK"
        assert math.isfinite(float(v_block.metrics["validation_test_mae_deg"]))

    asyncio.run(_check())
