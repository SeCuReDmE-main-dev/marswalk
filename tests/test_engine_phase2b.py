"""Phase 2b Engine Tests: Plithogenic Math, Safety Veto, Async Gates, A*, and Determinism."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any

from marswalk.engine.gates import (
    gate_g0_ingest,
    gate_g1_classify,
    gate_g2_search,
    gate_g3_plan,
    run_gate_with_hold_loop,
)
from marswalk.engine.pipeline import run_engine_pipeline_async
from marswalk.engine.plithogenic import (
    evaluate_cell_plithogenic,
    plithogenic_and_t,
    plithogenic_combine_triplet,
    plithogenic_or_f,
)
from marswalk.engine.validation import ValidationReport
from marswalk.middleware.build_pack import spherical_distance_m
from marswalk.middleware.pack_loader import load_and_verify_pack

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_plithogenic_hand_calculated_cases_and_boundary_identities() -> None:
    """Verify the 3 hand-calculated cases from docs/ENGINE_MATH.md and boundary laws."""
    a = (0.80, 0.10, 0.10)
    b = (0.60, 0.20, 0.20)

    # Case 1: c = 0.0 (zero contradiction -> pure algebraic product / probabilistic sum)
    t1, i1, f1 = plithogenic_combine_triplet(a, b, 0.0)
    assert math.isclose(t1, 0.4800, abs_tol=1e-6)
    assert math.isclose(i1, 0.1500, abs_tol=1e-6)
    assert math.isclose(f1, 0.2800, abs_tol=1e-6)

    # Case 2: c = 1.0 (full contradiction -> t-conorm on T, t-norm on F, conflict added to I)
    t2, i2, f2 = plithogenic_combine_triplet(a, b, 1.0)
    assert math.isclose(t2, 0.9200, abs_tol=1e-6)
    assert math.isclose(i2, 0.3500, abs_tol=1e-6)
    assert math.isclose(f2, 0.0200, abs_tol=1e-6)

    # Case 3: c = 0.5 (half contradiction)
    t3, i3, f3 = plithogenic_combine_triplet(a, b, 0.5)
    assert math.isclose(t3, 0.7000, abs_tol=1e-6)
    assert math.isclose(i3, 0.2500, abs_tol=1e-6)
    assert math.isclose(f3, 0.1500, abs_tol=1e-6)

    # Boundary identities across a grid of values
    for ta in (0.0, 0.25, 0.5, 0.85, 1.0):
        for tb in (0.0, 0.3, 0.7, 1.0):
            assert math.isclose(plithogenic_and_t(ta, tb, 0.0), ta * tb, abs_tol=1e-9)
            assert math.isclose(plithogenic_and_t(ta, tb, 1.0), ta + tb - ta * tb, abs_tol=1e-9)
            for c in (0.0, 0.2, 0.5, 0.8, 1.0):
                val_t = plithogenic_and_t(ta, tb, c)
                val_f = plithogenic_or_f(ta, tb, c)
                assert 0.0 <= val_t <= 1.0
                assert 0.0 <= val_f <= 1.0


def test_lexicographic_safety_veto_is_non_compensatory() -> None:
    """Verify neither prime delta geology (A5) nor 0m science proximity (A6) overrides veto."""
    # 1. Slope > 20.0 deg triggers immediate NO_GO veto despite ideal geology and science
    res_slope = evaluate_cell_plithogenic(
        s1_deg=21.4,
        s4_deg=11.0,
        s16_deg=8.5,
        s64_deg=6.0,
        divergence_deg=15.4,
        roughness_deg=1.2,
        walkback_m=150.0,
        geologic_unit="NHjf1 (Jezero fan 1 delta unit, SIM 3464)",
        dist_to_m20_stop_m=0.0,
    )
    assert res_slope.verdict == "NO_GO"
    assert res_slope.veto_triggered is True
    assert res_slope.dominant_conflict_attr == "A1_multiscale_slope"
    assert "SAFETY VETO" in res_slope.reason

    # 2. Walkback > 2,000 m triggers immediate NO_GO veto despite 1.0 deg flat terrain
    res_wb = evaluate_cell_plithogenic(
        s1_deg=1.0,
        s4_deg=0.9,
        s16_deg=0.8,
        s64_deg=0.7,
        divergence_deg=0.3,
        roughness_deg=0.2,
        walkback_m=2150.0,
        geologic_unit="NHjf1 (Jezero fan 1 delta unit, SIM 3464)",
        dist_to_m20_stop_m=0.0,
    )
    assert res_wb.verdict == "NO_GO"
    assert res_wb.veto_triggered is True
    assert res_wb.dominant_conflict_attr == "A4_walkback_distance"


def test_async_neutrosophic_gates_hold_refinement_and_block() -> None:
    """Verify HOLD triggers scale refinement -> PASS, and exhausted HOLD -> BLOCK."""

    async def _run() -> None:
        # 1. G1 HOLD (coarse 16m step) -> refinement to 8m step -> PASS on attempt 2
        log_pass = []

        async def _refine_to_8m(attempt: int, ctx: dict[str, Any]) -> dict[str, Any]:
            nxt = dict(ctx)
            nxt["cell_step_m"] = 8.0
            nxt["mean_cell_i"] = 0.20
            return nxt

        v_pass = await run_gate_with_hold_loop(
            gate_g1_classify,
            {"cell_step_m": 16.0, "mean_cell_i": 0.40, "validation_mae_4m_deg": 1.6},
            {"tau_t": 0.60, "tau_i": 0.35, "tau_f": 0.25, "max_validation_mae_deg": 6.0},
            _refine_to_8m,
            log_pass,
            max_hold_retries=2,
        )
        assert v_pass.decision == "PASS"
        assert v_pass.attempt == 2
        assert len(log_pass) == 2
        assert log_pass[0].decision == "HOLD"
        assert log_pass[1].decision == "PASS"

        # 2. G2 persistent HOLD (sensitivity Jaccard stays low) -> escalates to BLOCK on attempt 3
        log_block = []

        async def _no_op_refine(attempt: int, ctx: dict[str, Any]) -> dict[str, Any]:
            return dict(ctx)

        v_block = await run_gate_with_hold_loop(
            gate_g2_search,
            {
                "path_found": True,
                "max_path_slope_deg": 12.0,
                "max_walkback_m": 1500.0,
                "sensitivity_jaccard": 0.25,
            },
            {"tau_t": 0.60, "tau_i": 0.35, "tau_f": 0.20},
            _no_op_refine,
            log_block,
            max_hold_retries=2,
        )
        assert v_block.decision == "BLOCK"
        assert v_block.attempt == 3
        assert len(log_block) == 3
        assert log_block[0].decision == "HOLD"
        assert log_block[1].decision == "HOLD"
        assert log_block[2].decision == "BLOCK"

        # 3. G0 immediate BLOCK on invalid Mars sphere radius
        v_g0_bad = await gate_g0_ingest(
            {
                "dtm_sha256": "a" * 64,
                "sphere_radius_m": 6_378_137.0,
                "nodata_fraction": 0.0,
                "coverage_fraction": 1.0,
            },
            {"tau_t": 0.70, "tau_i": 0.25, "tau_f": 0.15},
        )
        assert v_g0_bad.decision == "BLOCK"

        # 4. G3 immediate BLOCK when walkback > 2,000 m
        v_g3_bad = await gate_g3_plan(
            {
                "max_walkback_m": 2400.0,
                "duration_h": 4.5,
                "radiation_msv": 0.12,
                "all_stops_within_2km": False,
                "stop_count": 3,
            },
            {"tau_t": 0.70, "tau_i": 0.25, "tau_f": 0.10},
        )
        assert v_g3_bad.decision == "BLOCK"

    asyncio.run(_run())


def test_validation_report_quantifies_orbital_scale_gap() -> None:
    """Verify validation_report.json proves 4m/16m accuracy vs 64m steep scarp underestimation."""
    val_path = REPO_ROOT / "public_packs" / "jezero" / "v1" / "validation_report.json"
    assert val_path.exists()
    report = ValidationReport.model_validate(json.loads(val_path.read_text(encoding="utf-8")))

    assert report.waypoint_count_in_window >= 140
    assert report.steep_waypoint_count >= 35
    m4 = report.metrics_by_baseline["4"]
    m16 = report.metrics_by_baseline["16"]
    m64 = report.metrics_by_baseline["64"]

    # Intermediate scales (4m, 16m) beat 64m coarse scale on steep delta scarps
    assert m4.steep_mae_deg < m64.steep_mae_deg
    assert m16.steep_mae_deg < m64.steep_mae_deg
    # 64m orbital baseline systematically underestimates steep slopes (negative bias < -1.5 deg)
    assert m64.steep_bias_deg < -1.5


@pytest.mark.skipif(
    not (REPO_ROOT / "datalake").exists(),
    reason="Requires gitignored local datalake/ cache for full DTM rebuild",
)
def test_async_pipeline_determinism_and_astar_envelope(tmp_path: Path) -> None:
    """Verify two independent async runs produce identical SHA-256 hashes and safe A* path."""
    run1_dir = tmp_path / "run1"
    run2_dir = tmp_path / "run2"

    for d in (run1_dir, run2_dir):
        (d / "datalake").mkdir(parents=True, exist_ok=True)
        for fname in (
            "M20_waypoints.json",
            "M20_traverse.json",
            "JEZ_hirise_soc_006_DTM_1m_window_2x2km.tif",
            "SIM3464_metadata.xml",
        ):
            shutil.copyfile(REPO_ROOT / "datalake" / fname, d / "datalake" / fname)
        shutil.copytree(REPO_ROOT / "profiles", d / "profiles")

    res1 = asyncio.run(run_engine_pipeline_async(run1_dir))
    res2 = asyncio.run(run_engine_pipeline_async(run2_dir))
    assert len(res1.gate_log) == len(res2.gate_log)

    for fname in ("hazard_grid.json", "route.geojson", "validation_report.json", "gate_log.jsonl"):
        h1 = hashlib.sha256(
            (run1_dir / "public_packs" / "jezero" / "v1" / fname).read_bytes()
        ).hexdigest()
        h2 = hashlib.sha256(
            (run2_dir / "public_packs" / "jezero" / "v1" / fname).read_bytes()
        ).hexdigest()
        assert h1 == h2, f"Non-deterministic output detected in {fname}"

    pack = load_and_verify_pack(run1_dir, site_id="jezero")
    assert pack.manifest.pack_version == "1.1.0"
    assert pack.hazards.grid_status == "ENGINE"
    assert all(g.decision == "PASS" for g in res1.gate_log)

    eva_feat = next(
        f for f in pack.route.features if f.properties.segment_type == "SIMULATED_ASTRONAUT_EVA"
    )
    assert eva_feat.properties.max_slope_deg is not None
    assert eva_feat.properties.max_slope_deg.value <= 20.0
    assert eva_feat.properties.max_slope_deg.tag == "DERIVED"
    assert eva_feat.properties.max_slope_deg.source_id == "SRC-USGS-HIRISE-DTM-1M"

    coords = eva_feat.geometry.coordinates  # type: ignore[assignment]
    origin_lon, origin_lat = coords[0]
    for lon, lat in coords:
        assert spherical_distance_m(origin_lon, origin_lat, lon, lat) <= 2000.0
