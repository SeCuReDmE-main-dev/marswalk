"""Unit tests for Phase 3 CRISM P10 `.lbl` geodesy, P5 Hurst lags, P6 CFA floor, and MEDA."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from marswalk.engine.boulder_cfa import DETECTION_FLOOR_CFA_PCT, estimate_cell_cfa_and_shadow
from marswalk.engine.calibration_aoa import (
    compute_cell_aoa_di,
    evaluate_cell_aoa_and_opinion,
    fit_spatial_aoa_model,
    josang_opinion,
)
from marswalk.engine.carriers import compute_hurst_and_step_slope_3_48m
from marswalk.engine.crism_ingest import (
    parse_crism_pds3_lbl,
    verify_reprojection_vs_reassignment_shift_m,
)
from marswalk.engine.meda_envelope import evaluate_dust_tau_verdict, filter_meda_samples

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = REPO_ROOT / "public_packs" / "jezero" / "v1"

# Synthetic PDS3 label fixtures (NOT the real FRT47A3 / HRL40FF labels, which use a
# 15 deg standard parallel). They only exercise dynamic CENTER_LATITUDE parsing.
SYNTHETIC_LBL_A = """
OBJECT = IMAGE_MAP_PROJECTION
  MAP_PROJECTION_TYPE = "EQUIRECTANGULAR"
  A_AXIS_RADIUS       = 3396.19 <km>
  CENTER_LATITUDE     = 18.45 <deg>
  CENTER_LONGITUDE    = 0.0 <deg>
  MAP_SCALE           = 18.0 <m/pixel>
  BAND_NAME           = ("OLINDEX3", "D2300", "BD2290", "BD1900_2", "BD2500_2")
END_OBJECT = IMAGE_MAP_PROJECTION
"""

SYNTHETIC_LBL_B = """
OBJECT = IMAGE_MAP_PROJECTION
  MAP_PROJECTION_TYPE = "EQUIRECTANGULAR"
  A_AXIS_RADIUS       = 3396.19 <km>
  CENTER_LATITUDE     = 18.375 <deg>
  CENTER_LONGITUDE    = 0.0 <deg>
  MAP_SCALE           = 18.0 <m/pixel>
  BAND_NAME           = ("OLINDEX3", "D2300", "BD2290", "BD1900_2", "BD2500_2")
END_OBJECT = IMAGE_MAP_PROJECTION
"""


def test_p10_crism_lbl_parses_center_latitude_dynamically_and_proves_158km_shift() -> None:
    """Verify P10 dynamic CENTER_LATITUDE parsing + ~158 km shift vs <1 px warp."""
    proj_47a3 = parse_crism_pds3_lbl(SYNTHETIC_LBL_A)
    proj_40ff = parse_crism_pds3_lbl(SYNTHETIC_LBL_B)
    assert proj_47a3.center_latitude_deg == pytest.approx(18.45)
    assert proj_40ff.center_latitude_deg == pytest.approx(18.375)
    assert proj_47a3.a_axis_radius_m == pytest.approx(3396190.0)
    assert "BD2300" not in proj_47a3.band_names
    assert "D2300" in proj_47a3.band_names

    naive_err_m, warped_err_m = verify_reprojection_vs_reassignment_shift_m(77.40, proj_47a3)
    assert naive_err_m > 150_000.0  # ~158 km E-W error if CRS is merely relabeled
    assert warped_err_m < 1.0  # < 1 px (18 m) corner agreement after reprojection


def test_p5_hurst_includes_all_five_lags_on_101m_patch() -> None:
    """Verify P5: centered 101x101 px patch includes all 5 lags (3, 6, 12, 24, 48)."""
    rng = np.random.default_rng(42)
    yy, xx = np.mgrid[0:101, 0:101]
    synth = 0.05 * xx + 0.03 * yy + 0.2 * np.sin(xx / 6.0) + rng.normal(0.0, 0.08, (101, 101))
    h_val, step_075, lags_used, i_boost = compute_hurst_and_step_slope_3_48m(
        synth, slope_3m_deg=6.0, step_x_m=0.9485
    )
    assert lags_used == (3, 6, 12, 24, 48)
    assert 0.15 <= h_val <= 0.95
    assert step_075 >= 6.0
    assert 0.0 <= i_boost <= 0.18


def test_p6_cfa_detection_floor_raises_uncertainty_i() -> None:
    """Verify P6: flat patch hitting Golombek 5% floor raises i_cfa_boost > 0."""
    flat_patch = np.zeros((9, 9), dtype=np.float64)
    est = estimate_cell_cfa_and_shadow(
        flat_patch,
        roughness_rms_m=0.005,
        curvature_m_inv=0.005,
        slope_4m_deg=1.0,
    )
    assert est.rock_cfa_pct == pytest.approx(DETECTION_FLOOR_CFA_PCT)
    assert est.below_detection_floor is True
    assert est.i_cfa_boost > 0.05


def test_meda_sentinel_and_first_calibrated_sol_gates() -> None:
    """Verify MEDA 9999999999 sentinel stripping and RHS sol >= 63 / WS sol >= 36 gates."""
    rhs_early = filter_meda_samples("RHS", sol=40, raw_values=[12.5, 14.0])
    assert rhs_early.valid_values == ()
    assert rhs_early.rejected_count == 2

    ws_valid = filter_meda_samples("WS", sol=45, raw_values=[4.2, 9999999999.0, 5.8])
    assert ws_valid.valid_values == (4.2, 5.8)
    assert ws_valid.rejected_count == 1
    assert evaluate_dust_tau_verdict(0.35) == "GO"
    assert evaluate_dust_tau_verdict(0.75) == "CAUTION"
    assert evaluate_dust_tau_verdict(1.25) == "NO_GO"


def test_aoa_and_josang_opinion_sum_to_one() -> None:
    """Verify Jøsang subjective opinion and Meyer & Pebesma (2021) AOA model."""
    op_in = josang_opinion(18, 2, n_eff=20, inside_aoa=True)
    op_out = josang_opinion(18, 2, n_eff=20, inside_aoa=False)
    assert sum(op_in) == pytest.approx(1.0)
    assert op_out[2] > op_in[2]

    feats = np.array([[4.0, 5.0, 6.0, 1.0], [8.0, 9.0, 10.0, 2.0], [12.0, 11.0, 9.0, 3.0]])
    xy = np.array([[0.0, 0.0], [200.0, 0.0], [0.0, 200.0]])
    labels = np.array([0.0, 0.0, 1.0])
    model = fit_spatial_aoa_model(feats, xy, labels)
    assert model.n_eff_blocks >= 1
    assert model.di_threshold > 0.0
    assert model.mean_train_dist > 0.0

    # Verify DI normalization matches threshold units (DI at training centroid == 0.0)
    di_train = compute_cell_aoa_di(model, (4.0, 5.0, 6.0, 1.0))
    assert di_train == pytest.approx(0.0, abs=1e-9)

    _, op_near = evaluate_cell_aoa_and_opinion(model, (4.0, 5.0, 6.0, 1.0))
    _, op_mid = evaluate_cell_aoa_and_opinion(model, (6.0, 7.0, 8.0, 1.5))
    assert op_near.i != pytest.approx(op_mid.i)


def test_r1_r2_h1_h2_on_built_jezero_pack() -> None:
    """Verify R1 (CFA I-only), R2 (RF LOS), H1 (external layers), and H2 (continuous I)."""
    grid = json.loads((PACK_DIR / "hazard_grid.json").read_text(encoding="utf-8"))
    cells = grid["cells"]
    assert len(cells) == 1600

    # R1: CFA note is honest proxy and never overrides low-slope cells to NO_GO
    for c in cells:
        note = c["rock_cfa_pct"].get("note") or ""
        assert "Golombek F_k(D) calibration" not in note
        assert "proxy" in note or "floor" in note
        if c["rock_cfa_pct"]["value"] >= 15.0:
            assert "CFA" not in c["reason"]

    # R2: Per-cell RF profile samples real HiRISE DTM terrain, so not all 1,600 cells are GO
    rf_verdicts = [c["rf_comms_verdict"] for c in cells]
    assert sum(v != "GO" for v in rf_verdicts) > 0

    # H1: External layers status recorded on HazardGrid with UNAVAILABLE + I=1.0
    ext = grid.get("external_layers_status")
    assert isinstance(ext, dict)
    for missing_key in ("themis_ti_100m", "crism_mtrdr_18m", "meda_pds4_env"):
        assert ext[missing_key]["tag"] == "UNAVAILABLE"
        assert ext[missing_key]["indeterminacy_i"] == pytest.approx(1.0)
    assert ext["sim3464_geology"]["tag"] == "DERIVED"

    # H2: calibrated_opinion.i varies continuously across the 1,600 cells (> 20 distinct values)
    distinct_cal_i = {round(c["calibrated_opinion"]["i"], 4) for c in cells}
    assert len(distinct_cal_i) > 20

    cv_path = REPO_ROOT / "bench" / "results" / "aoa_cv.json"
    assert cv_path.exists()
    cv_data = json.loads(cv_path.read_text(encoding="utf-8"))
    assert cv_data["n_eff_spatial_blocks"] >= 10
    assert 0.5 <= cv_data["spatial_cv_mae_deg"]["funnel"] <= 2.0
    assert cv_data["aoa_heldout_summary"]["distinct_josang_i_count"] > 20
