"""Phase 4 Obstacle-Aware Route Map & M1-M6 Engineering Specification Tests.

Verifies all CTO blockers (`X1`-`X3`), major corrections (`C1`-`C7`), arbitrations
(#1 PNG `10 m` grid `< 5 MB`, #2 dedicated `/waypoints/{sol}/cameras` endpoint only,
#3 additive `route.geojson`), and `VERDICT_DEEP_RESEARCH_PHASE4.md` rectifications
(`F1`-`F3`, `H1`-`H4`, `I1`-`I6`, and missing angles).
"""

from __future__ import annotations

import ast
import asyncio
import math
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from marswalk.engine.boulder_cfa import (
    DETECTION_FLOOR_CFA_PCT,
    ROVER_CFA_CAUTION_PCT,
    ROVER_CFA_OK_PCT,
)
from marswalk.engine.dtm_ingest import (
    ground_step_x_m,
    ingest_dtm_window_async,
    select_optimal_delta_window_2x2km,
)
from marswalk.engine.eva_human_rf import (
    ROVER_MAST_HEIGHT_M,
    SUIT_ANTENNA_HEIGHT_M,
    evaluate_route_rf_fresnel_bullington,
    first_fresnel_radius_m,
    tobler_xeva_kmh,
)
from marswalk.engine.kinematics_m4 import (
    SUIT_MASS_CSRM_REF_KG,
    SUIT_MASS_MKIII_KG,
    compare_suited_metabolic_models,
    grade_frac_to_slope_deg,
    minetti_2002_quintic_poly_j_per_kg_m,
    minetti_2002_table_j_per_kg_m,
    slope_deg_to_grade_frac,
)
from marswalk.engine.m20_raw_images_m5 import (
    M20_RAW_IMAGES_FEED_TEMPLATE,
    parse_m20_raw_images_payload,
)
from marswalk.engine.obstacles_m1 import (
    PHYSICAL_CLEARANCE_RADIUS_M,
    PlannerGrid10m,
    apply_physical_clearance_buffer_1m,
    load_planner_grid_10m_png,
    save_planner_grid_10m_png,
    validate_m1_against_ground_truth,
)
from marswalk.engine.planner_m2 import (
    V_MAX_XEVA_KMH,
    _astar_single_leg,
    in_grid_bounds,
    plan_obstacle_aware_route,
    string_pull_with_cost_guard,
    supercover_grid_cells,
)
from marswalk.engine.topographic_refuge_m3 import (
    SPE_REFUGE_ROUTING_WEIGHT,
    analytical_finite_wall_sky_occlusion,
    compute_partial_topographic_refuge,
)
from marswalk.middleware.api import app, get_query_service
from marswalk.middleware.pack_loader import load_and_verify_pack
from marswalk.middleware.query_service import PackQueryService

REPO_ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_x2_no_fabricated_cfa_threshold_11_or_10_pct() -> None:
    """Verify `X2`/`R1`/`F2`: zero `11.0`/`10.0` CFA verdict thresholds in engine AST."""
    assert ROVER_CFA_OK_PCT == 7.0
    assert ROVER_CFA_CAUTION_PCT == 15.0
    assert DETECTION_FLOOR_CFA_PCT == 5.0

    for rel_path in (
        "src/marswalk/engine/pipeline.py",
        "src/marswalk/engine/boulder_cfa.py",
        "src/marswalk/engine/obstacles_m1.py",
    ):
        source = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
        float_literals = [
            float(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        ]
        assert 11.0 not in float_literals, f"Found fabricated 11.0 float literal in {rel_path}"

        # Ensure no comparison in AST tests any `cfa` variable against 10.0 or 11.0
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                segment = ast.get_source_segment(source, node) or ""
                if "cfa" in segment.lower():
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Constant) and isinstance(sub.value, (int, float)):
                            assert float(sub.value) not in (10.0, 11.0), (
                                f"Forbidden CFA threshold in {rel_path}: {segment}"
                            )


@pytest.mark.skipif(
    not (REPO_ROOT / "datalake" / "JEZ_hirise_soc_006_DTM_1m_window_2x2km.tif").exists(),
    reason="Requires gitignored local datalake/ DTM GeoTIFF",
)
def test_c1_m1_specificity_even_sols_and_recall_sim3464_and_sol700() -> None:
    """Verify `C1`: 147 stops, even-sol specificity, DTM self-consistency (not independent)."""
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    win = select_optimal_delta_window_2x2km(pack.waypoints)
    dtm = asyncio.run(ingest_dtm_window_async(REPO_ROOT / "datalake", win))

    val = validate_m1_against_ground_truth(
        dtm.elevation_m,
        dtm.transform_x_min_m,
        dtm.transform_y_max_m,
        pack.hazards.bbox,
        pack.waypoints.features,
    )
    assert val.total_window_stops == 147
    assert val.even_sol_gentle_stops > 30
    assert val.even_sol_specificity >= 0.95
    assert val.dtm_relief_scarp_pixels > 50
    assert val.dtm_relief_self_consistency_recall >= 0.85
    # Sol 700 is a visited Perseverance stop on a > 20 deg slope (exceeds astronaut suit limit)
    assert val.sol_700_slope_4m_deg > 20.0
    assert val.sol_700_exceeds_20deg_limit is True
    assert val.ono_rover_cfa_reference_pct == (7.0, 15.0)


def test_c2_c3_formations_4m_and_physical_clearance_corridor_preservation(
    tmp_path: Path,
) -> None:
    """Verify `C3` & Arbitration #1: >= 2 m corridor stays open; PNG lossless; pack < 5 MB."""
    assert math.isclose(PHYSICAL_CLEARANCE_RADIUS_M, 0.85, abs_tol=1e-9)

    # 1) Corridor >= 2.0 m wide (2 clear 1 m pixels between walls at cols 8 and 11) stays open
    mask_open = np.zeros((21, 21), dtype=bool)
    mask_open[5:16, 8] = True
    mask_open[5:16, 11] = True  # cols 9 and 10 give a ~2.0 m clear passage
    buf_open = apply_physical_clearance_buffer_1m(mask_open, step_x_m=1.0, step_y_m=1.0)
    assert not bool(np.all(buf_open[10, 9:11])), ">= 2.0 m corridor was wrongly closed!"

    # 2) Narrow gap of 1.0 m (walls at cols 8 and 10, single pixel col 9) closes (`2*0.85 > 1.0`)
    mask_narrow = np.zeros((21, 21), dtype=bool)
    mask_narrow[5:16, 8] = True
    mask_narrow[5:16, 10] = True
    buf_narrow = apply_physical_clearance_buffer_1m(mask_narrow, step_x_m=1.0, step_y_m=1.0)
    assert bool(buf_narrow[10, 9]), "Narrow 1.0 m gap (< 1.70 m suit+sigma clearance) stayed open!"

    # 3) Lossless PNG flag roundtrip & zero 7.07 m cross-cell dilation on 10 m grid
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    total_pack_bytes = sum(f.bytes for f in pack.manifest.files)
    assert total_pack_bytes < 5_000_000
    assert pack.planner_grid_10m is not None
    assert pack.planner_grid_10m.rows == 200
    assert pack.planner_grid_10m.cols == 190

    synth = PlannerGrid10m(
        rows=12,
        cols=12,
        bbox=pack.hazards.bbox,
        step_x_ground_m=9.485,
        step_y_ground_m=10.0,
        blocked_mask=np.eye(12, dtype=bool),
        caution_mask=np.fliplr(np.eye(12, dtype=bool)),
        toe_refuge_mask=np.zeros((12, 12), dtype=bool),
        grad_x=np.zeros((12, 12), dtype=np.float64),
        grad_y=np.zeros((12, 12), dtype=np.float64),
        risk_penalty_01=np.full((12, 12), 0.25, dtype=np.float64),
    )
    out_png = tmp_path / "grid.png"
    save_planner_grid_10m_png(synth, out_png)
    reloaded = load_planner_grid_10m_png(out_png, bbox=pack.hazards.bbox)
    assert np.array_equal(reloaded.blocked_mask, synth.blocked_mask)
    assert np.array_equal(reloaded.caution_mask, synth.caution_mask)


def test_c4_astar_admissibility_with_vmax_2p4_kmh() -> None:
    """Verify `C4`/`H3`: `V_MAX = 2.4 km/h` at `-5%` guarantees exact Dijkstra optimality."""
    assert math.isclose(tobler_xeva_kmh(0.0), 2.0147, rel_tol=1e-3)
    assert math.isclose(tobler_xeva_kmh(-0.05), 2.4, rel_tol=1e-6)
    assert tobler_xeva_kmh(-0.05) > tobler_xeva_kmh(0.0)
    assert math.isclose(V_MAX_XEVA_KMH, 2.4, rel_tol=1e-6)

    # Construct a terrain with a -5% downhill channel (where v = 2.4 km/h > 2.0 km/h)
    rows, cols = 24, 24
    rng = np.random.default_rng(42)
    gx = rng.uniform(-0.12, 0.12, size=(rows, cols))
    gy = rng.uniform(-0.12, 0.12, size=(rows, cols))
    gx[8:14, :] = -0.05  # optimal -5% downhill going East
    gy[8:14, :] = 0.0
    blocked = np.zeros((rows, cols), dtype=bool)
    blocked[4:18, 12] = True
    blocked[11, 12] = False  # narrow gate

    grid = PlannerGrid10m(
        rows=rows,
        cols=cols,
        bbox=(77.3832, 18.4465, 77.4170, 18.4802),
        step_x_ground_m=9.48526,
        step_y_ground_m=10.0,
        blocked_mask=blocked,
        caution_mask=np.zeros((rows, cols), dtype=bool),
        toe_refuge_mask=np.zeros((rows, cols), dtype=bool),
        grad_x=gx,
        grad_y=gy,
        risk_penalty_01=rng.uniform(0.0, 0.6, size=(rows, cols)),
    )
    ok_dijk, _, g_dijk, exp_dijk = _astar_single_leg(
        grid, (10, 2), (14, 21), heuristic_weight=0.0, pure_time_only=True
    )
    ok_astar, _, g_astar, exp_astar = _astar_single_leg(
        grid, (10, 2), (14, 21), heuristic_weight=1.0, pure_time_only=True
    )
    assert ok_dijk and ok_astar
    assert math.isclose(g_astar[-1], g_dijk[-1], rel_tol=0.0, abs_tol=1e-9)
    assert exp_astar <= exp_dijk


def test_h2_string_pulling_cost_guard_prevents_risk_inflation() -> None:
    """Verify `H2`: string-pulling rejects shortcuts that cross high-risk terrain."""
    rows, cols = 20, 20
    risk = np.zeros((rows, cols), dtype=np.float64)
    # High-risk ridge across the middle (unblocked, so geometric LOS would cut straight across)
    risk[4:16, 8:12] = 1.0
    risk[17:, :] = 0.0  # low-risk southern corridor

    grid = PlannerGrid10m(
        rows=rows,
        cols=cols,
        bbox=(77.3832, 18.4465, 77.4170, 18.4802),
        step_x_ground_m=9.48526,
        step_y_ground_m=10.0,
        blocked_mask=np.zeros((rows, cols), dtype=bool),
        caution_mask=risk > 0.5,
        toe_refuge_mask=np.zeros((rows, cols), dtype=bool),
        grad_x=np.zeros((rows, cols), dtype=np.float64),
        grad_y=np.zeros((rows, cols), dtype=np.float64),
        risk_penalty_01=risk,
    )
    ok, raw_path, cum_g, _ = _astar_single_leg(grid, (10, 2), (10, 17), heuristic_weight=1.0)
    assert ok
    _, audit = string_pull_with_cost_guard(grid, raw_path, cum_g)
    assert audit.rejected_by_cost_guard_count > 0
    assert audit.smoothed_cost_s <= audit.raw_cost_s + 1e-6


def test_h3_supercover_bounds_and_homogeneity_and_dynamic_cos_phi() -> None:
    """Verify `H3` & `C6a`: bounds safety (no `-1` wrap), corner supercover, dynamic `cos(phi)`."""
    assert not in_grid_bounds(-1, 0, 10, 10)
    assert not in_grid_bounds(0, -1, 10, 10)
    ok_neg, cells_neg = supercover_grid_cells(10, 10, -1, 2, 3, 4)
    assert not ok_neg and cells_neg == []

    # Diagonal corner crossing from (0, 0) to (2, 2) must include orthogonal touch cells
    ok_diag, cells_diag = supercover_grid_cells(5, 5, 0, 0, 2, 2)
    assert ok_diag
    assert (0, 1) in cells_diag and (1, 0) in cells_diag
    assert all(0 <= r < 5 and 0 <= c < 5 for r, c in cells_diag)

    # Dynamic cos(phi_c): Jezero center 18.46335 deg -> 0.948526 (not hardcoded)
    cos_jezero = ground_step_x_m(18.46335, 1.0)
    cos_equator = ground_step_x_m(0.0, 1.0)
    assert round(cos_jezero, 6) == 0.948526
    assert round(cos_equator, 6) == 1.0


def test_c5_partial_topographic_refuge_non_inert_and_zero_spe_bias() -> None:
    """Verify `C5` & `I1`-`I3`: non-inert scarp-toe refuge, `[7.0, 9.1]%`, zero SPE detour."""
    # Exact analytical finite vs infinite wall occlusion
    occ_inf = analytical_finite_wall_sky_occlusion(10.0, 2.0, wall_width_m=None)
    occ_fin = analytical_finite_wall_sky_occlusion(10.0, 2.0, wall_width_m=20.0)
    assert 0.35 < occ_fin < occ_inf < 0.50

    r35 = compute_partial_topographic_refuge(0.35)
    assert math.isclose(r35.expected_gcr_reduction_min_pct, 7.0, abs_tol=1e-3)
    assert math.isclose(r35.expected_gcr_reduction_max_pct, 9.1, abs_tol=1e-3)
    r40 = compute_partial_topographic_refuge(0.40)
    assert math.isclose(r40.expected_gcr_reduction_min_pct, 8.0, abs_tol=1e-3)
    assert math.isclose(r40.expected_gcr_reduction_max_pct, 10.4, abs_tol=1e-3)
    assert SPE_REFUGE_ROUTING_WEIGHT == 0.0

    # Non-inertness on actual Jezero pack (`P2` / `C5`)
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    refuge_cells = [c for c in pack.hazards.cells if c.partial_topographic_refuge is True]
    assert 0 < len(refuge_cells) < len(pack.hazards.cells)

    # Zero forbidden solar shelter string anywhere in `src/`
    forbidden_phrase = "SPE" + " shelter"
    for py_file in (REPO_ROOT / "src").rglob("*.py"):
        txt = py_file.read_text(encoding="utf-8")
        assert forbidden_phrase.lower() not in txt.lower(), f"Forbidden phrase in {py_file}"

    # Under spe_alert=True, planner never detours toward toe_refuge_mask cells
    toe_mask = np.zeros((15, 15), dtype=bool)
    toe_mask[1, :] = True  # wall refuge far to the north
    grid = PlannerGrid10m(
        rows=15,
        cols=15,
        bbox=pack.hazards.bbox,
        step_x_ground_m=9.48526,
        step_y_ground_m=10.0,
        blocked_mask=np.zeros((15, 15), dtype=bool),
        caution_mask=np.zeros((15, 15), dtype=bool),
        toe_refuge_mask=toe_mask,
        grad_x=np.zeros((15, 15), dtype=np.float64),
        grad_y=np.zeros((15, 15), dtype=np.float64),
        risk_penalty_01=np.zeros((15, 15), dtype=np.float64),
    )
    wpts = [(77.3860, 18.4550), (77.4050, 18.4550)]
    res_spe = plan_obstacle_aware_route(grid, wpts, spe_alert=True)
    assert res_spe.reachable is True
    assert res_spe.verdict == "NO_GO"
    assert all(r != 1 for r, _ in res_spe.smoothed_grid_path)


def test_c6_m4_grade_vs_angle_minetti_table_vs_poly_and_121kg_suit_mass() -> None:
    """Verify `C6b`/`C6c`/`I4`/`I5`: grade != deg, Table 1 != quintic, 121 kg suit mass."""
    assert math.isclose(grade_frac_to_slope_deg(-0.10), -5.710593, abs_tol=1e-5)
    assert math.isclose(slope_deg_to_grade_frac(20.0), math.tan(math.radians(20.0)), abs_tol=1e-9)

    # Minetti (2002) Table 1 published experimental means (`MEASURED`)
    assert math.isclose(minetti_2002_table_j_per_kg_m(0.0), 1.64, abs_tol=1e-4)
    assert math.isclose(minetti_2002_table_j_per_kg_m(-0.10), 0.81, abs_tol=1e-4)
    assert math.isclose(minetti_2002_table_j_per_kg_m(-0.45), 3.46, abs_tol=1e-4)
    assert math.isclose(minetti_2002_table_j_per_kg_m(0.45), 17.33, abs_tol=1e-4)

    # Minetti (2002) quintic regression polynomial (`DERIVED`)
    assert math.isclose(minetti_2002_quintic_poly_j_per_kg_m(0.0), 2.50, abs_tol=1e-3)
    assert math.isclose(minetti_2002_quintic_poly_j_per_kg_m(-0.10), 1.127125, abs_tol=1e-4)
    assert math.isclose(minetti_2002_quintic_poly_j_per_kg_m(-0.45), 3.606, abs_tol=1e-2)
    assert math.isclose(minetti_2002_quintic_poly_j_per_kg_m(0.45), 17.601, abs_tol=1e-2)

    # Canonical repository suit mass = 121.0 kg; CSRM reference point check (W=75, L=104, v=0.625)
    assert SUIT_MASS_MKIII_KG == 121.0
    cmp_default = compare_suited_metabolic_models()
    assert cmp_default.suit_mass_kg == 121.0
    assert cmp_default.norcross_tag == "MEASURED"
    assert cmp_default.pandolf_tag == "DERIVED"

    cmp_csrm = compare_suited_metabolic_models(
        grade_frac=0.0,
        speed_m_s=0.625,
        body_mass_kg=75.0,
        suit_mass_kg=SUIT_MASS_CSRM_REF_KG,
        terrain_eta=1.0,
        gravity_ratio=0.3794,
    )
    assert math.isclose(cmp_csrm.pandolf_csrm_all_g_scaled_w, 343.65, abs_tol=0.5)
    assert math.isclose(cmp_csrm.pandolf_carr_newman_unscaled_postural_w, 413.47, abs_tol=0.5)


def test_m5_raw_images_dedicated_endpoint_and_zero_mars_photos() -> None:
    """Verify `F3`, `H4`, Arbitration #2: dedicated `/cameras` endpoint, zero legacy URL."""
    retired_host = "api.nasa.gov/" + "mars-photos"
    for py_file in (REPO_ROOT / "src").rglob("*.py"):
        assert retired_host not in py_file.read_text(encoding="utf-8")
    assert "feed=raw_images" in M20_RAW_IMAGES_FEED_TEMPLATE
    assert "&sol={sol}" in M20_RAW_IMAGES_FEED_TEMPLATE

    sample_payload = {
        "images": [
            {
                "imageid": f"NLF_0700_{idx:04d}",
                "sol": 700,
                "site": 38,
                "drive": 1204,
                "attitude": "(0.707, 0.0, 0.0, 0.707)",
                "camera": {
                    "instrument": "NAVCAM_LEFT",
                    "model_type": "CAHVOR",
                    "camera_model_component_list": {"c": [1, 2, 3]},
                },
                "extended": {"mastAz": str((40.0 + idx * 5.0) % 360.0), "mastEl": "-8.5"},
                "image_files": {"medium": f"https://mars.nasa.gov/m20/{idx}.jpg"},
            }
            for idx in range(15)
        ]
    }
    p1 = parse_m20_raw_images_payload(
        sample_payload, target_azimuth_deg=50.0, max_azimuth_delta_deg=45.0, page=1, page_size=4
    )
    assert p1.total_matching > 4
    assert len(p1.items) == 4
    assert p1.items[0].sol == 700
    assert p1.items[0].site == 38
    assert p1.items[0].drive == 1204
    assert p1.items[0].camera_model_type == "CAHVOR"

    # Dedicated offline endpoint returns valid RoverCamerasResponse without network I/O
    r_cam = client.get("/v1/sites/jezero/waypoints/700/cameras?allow_network=false")
    assert r_cam.status_code == 200
    assert r_cam.json()["sol"] == 700
    assert r_cam.json()["source_status"] in ("cached", "offline_unavailable")

    # `/plan-route` has ZERO camera fields
    r_plan = client.post(
        "/v1/sites/jezero/plan-route",
        json={"waypoints": [[77.4070, 18.4520], [77.4035, 18.4545]]},
    )
    assert r_plan.status_code == 200
    plan_json = r_plan.json()
    assert plan_json["reachable"] is True
    assert not any("camera" in k.lower() for k in plan_json)


def test_m6_fresnel_bullington_unification_and_antenna_heights() -> None:
    """Verify `M6` (`I6`): `c/F1 = 0.60 <-> nu = -0.8485 -> 0 dB`, `3.0 m` mast & `1.8 m` suit."""
    assert ROVER_MAST_HEIGHT_M == 3.0
    assert SUIT_ANTENNA_HEIGHT_M == 1.8

    # Construct a 1000 m profile whose midpoint clears LOS by exactly 0.60 * F1
    dist_m = 1000.0
    f1_mid = first_fresnel_radius_m(500.0, 500.0)
    bulge_mid = (500.0 * 500.0) / (2.0 * 3_396_190.0)
    z_los_mid = 0.5 * (ROVER_MAST_HEIGHT_M + SUIT_ANTENNA_HEIGHT_M)
    z_mid_for_0p6_f1 = z_los_mid - 0.60 * f1_mid - bulge_mid
    prof = [-20.0, z_mid_for_0p6_f1, -20.0]
    prof[0] = 0.0
    prof[-1] = 0.0

    rf = evaluate_route_rf_fresnel_bullington(prof, dist_m)
    assert rf.h_tx_rover_mast_m == 3.0
    assert rf.h_rx_suit_antenna_m == 1.8
    assert math.isclose(rf.nu_max, -0.60 * math.sqrt(2.0), abs_tol=1e-3)
    assert math.isclose(rf.min_clearance_over_f1, 0.60, abs_tol=1e-3)
    assert rf.diffraction_loss_db == 0.0
    assert rf.verdict == "GO"


def test_route_geojson_preserves_measured_and_adds_derived_m2_route() -> None:
    """Verify Arbitration #3: `route.geojson` keeps `MEASURED` traverse + adds `M2` `DERIVED`."""
    r_route = client.get("/v1/sites/jezero/route")
    assert r_route.status_code == 200
    feats = r_route.json()["features"]
    by_id = {f["properties"]["feature_id"]: f for f in feats}

    assert "ROUTE-M20-MEASURED-TRAVERSE" in by_id
    assert by_id["ROUTE-M20-MEASURED-TRAVERSE"]["properties"]["tag"] == "MEASURED"
    assert "ROUTE-XEVA-SIMULATED-FAN-CORRIDOR" in by_id
    assert "ROUTE-EVA-M2-OBSTACLE-AWARE" in by_id

    m2_feat = by_id["ROUTE-EVA-M2-OBSTACLE-AWARE"]
    assert m2_feat["properties"]["segment_type"] == "DERIVED_OBSTACLE_AWARE_EVA"
    assert m2_feat["properties"]["tag"] == "DERIVED"
    assert m2_feat["properties"]["source_id"] == "SRC-USGS-HIRISE-DTM-1M"
    assert len(m2_feat["geometry"]["coordinates"]) >= 2

    r_obs = client.get("/v1/sites/jezero/obstacles")
    assert r_obs.status_code == 200
    obs_json = r_obs.json()
    assert len(obs_json["features"]) > 10

    r_grid = client.get("/v1/sites/jezero/planner-grid-10m.png")
    assert r_grid.status_code == 200
    assert r_grid.headers["content-type"] == "image/png"


def test_plan_route_respects_safe_mode_and_failsafe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify `X3`: `/plan-route` enforces per-request `MARSWALK_SAFE_MODE` and `FAIL_SAFE`."""
    payload = {"waypoints": [[77.4070, 18.4520], [77.4035, 18.4545]]}

    # 1) Dynamic operator safe-mode stop
    monkeypatch.setenv("MARSWALK_SAFE_MODE", "1")
    r_safe = client.post("/v1/sites/jezero/plan-route", json=payload)
    assert r_safe.status_code == 200
    body_safe = r_safe.json()
    assert body_safe["verdict"] == "NO_GO"
    assert body_safe["reachable"] is False
    assert "SAFE_MODE: route planning disabled by operator" in body_safe["reasons"]

    # 2) Unset safe mode -> works again immediately without server restart
    monkeypatch.delenv("MARSWALK_SAFE_MODE", raising=False)
    r_ok = client.post("/v1/sites/jezero/plan-route", json=payload)
    assert r_ok.status_code == 200
    assert r_ok.json()["reachable"] is True

    # 3) Internal engine exception -> HTTP 200 NO_GO FAIL_SAFE
    get_query_service.cache_clear()

    def _boom(self: PackQueryService, req: object) -> object:
        raise RuntimeError("synthetic planner failure")

    monkeypatch.setattr(PackQueryService, "_plan_route_impl", _boom)
    r_err = client.post("/v1/sites/jezero/plan-route", json=payload)
    assert r_err.status_code == 200
    body_err = r_err.json()
    assert body_err["verdict"] == "NO_GO"
    assert "FAIL_SAFE: engine error" in body_err["reasons"]
