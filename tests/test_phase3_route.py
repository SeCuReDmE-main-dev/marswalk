"""Phase 3 test route: math oracle, live regressions, and conformance gates.

Three layers, read top to bottom:

* A. ORACLE (always runs). Reference formulas recomputed from primary sources.
  These lock the numbers that the Phase 3 engine must reproduce.
* B. LIVE REGRESSIONS (strict xfail). Bugs I reproduced on the current API.
  When the fix lands, the test XPASSes and pytest fails until the marker is removed.
* C. CONFORMANCE (skipped until the Phase 3 module or field exists).
  Each test activates by itself as soon as Antigravity ships the named symbol.
"""

from __future__ import annotations

import importlib
import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marswalk.middleware.api import app

R_MARS_M = 3_396_190.0
PHI_JEZERO_DEG = 18.465
BBOX = (77.376709, 18.447804, 77.41045, 18.481545)
PACK_DIR = Path(__file__).resolve().parents[1] / "public_packs" / "jezero" / "v1"
client = TestClient(app)


# --------------------------------------------------------------------------- oracle helpers
def fresnel_j_db(nu: float) -> float:
    """ITU-R P.526-16 eq. (31) knife-edge loss."""
    if nu <= -0.78:
        return 0.0
    return 6.9 + 20.0 * math.log10(math.sqrt((nu - 0.1) ** 2 + 1.0) + nu - 0.1)


def flat_ground_nu_max(d_m: float, h_tx: float = 1.8, h_rx: float = 3.0) -> float:
    """Bullington nu_max over a flat Mars profile with curvature bulge d1*d2/(2R)."""
    lam = 299_792_458.0 / 414.2e6
    best = -1e9
    for i in range(1, 400):
        d1 = d_m * i / 400.0
        d2 = d_m - d1
        los = h_tx + (h_rx - h_tx) * d1 / d_m
        h = d1 * d2 / (2.0 * R_MARS_M) - los
        best = max(best, h * math.sqrt(2.0 / lam * (1.0 / d1 + 1.0 / d2)))
    return best


def ehresmann_factor(svf: float, eta_s: float = 0.20) -> float:
    return max(0.19, 1.0 - eta_s * (1.0 - svf))


def tobler_xeva_kmh(grade: float) -> float:
    """Tobler 1993 rescaled x0.4 so that flat ground gives the xEVA 2 km/h."""
    return 0.4 * 6.0 * math.exp(-3.5 * abs(grade + 0.05))


def o2_g_per_h(metabolic_w: float) -> float:
    return 60.0 * metabolic_w / 20_100.0 * 60.0 * 1.429


def josang(r: float, s: float, w: float = 2.0) -> tuple[float, float, float]:
    total = r + s + w
    return s / total, r / total, w / total


# --------------------------------------------------------------------------- A. ORACLE
def test_a1_cos_phi_ground_metres() -> None:
    cos_phi = math.cos(math.radians(PHI_JEZERO_DEG))
    assert cos_phi == pytest.approx(0.9485, abs=1e-4)
    proj_x = R_MARS_M * math.radians(BBOX[2] - BBOX[0])
    assert proj_x == pytest.approx(2000.0, abs=5.0)
    assert proj_x * cos_phi == pytest.approx(1897.0, abs=5.0)


def test_a2_crism_relabel_shifts_longitude_by_about_158_km() -> None:
    k = 3_394_839.813 * math.cos(math.radians(15.0)) / R_MARS_M
    err_km = (77.39 - 77.39 * k) * math.pi / 180.0 * R_MARS_M / 1000.0
    assert 150.0 < err_km < 165.0


def test_a3_itu_knife_edge_anchor_points() -> None:
    assert fresnel_j_db(-0.78) == pytest.approx(0.0, abs=0.05)
    assert fresnel_j_db(0.0) == pytest.approx(6.03, abs=0.05)


def test_a4_uhf_go_rule_nu_le_minus_078_is_unreachable_beyond_about_100_m() -> None:
    """Break finding: flat ground already violates nu <= -0.78 past ~100 m at 414.2 MHz.

    A GO rule on nu alone turns the whole map into CAUTION. GO must be J <= margin - fade.
    """
    assert flat_ground_nu_max(50.0) <= -0.78
    assert flat_ground_nu_max(500.0) > -0.78
    assert fresnel_j_db(flat_ground_nu_max(2000.0)) < 6.0  # still inside a 6 dB margin


def test_a5_ehresmann_albedo_floor_is_mathematically_inert() -> None:
    """1 - 0.2*(1-SVF) >= 0.8 for SVF in [0,1]: the 0.19 floor can never bind."""
    assert min(ehresmann_factor(s / 100.0) for s in range(101)) == pytest.approx(0.8)
    assert 1.0 - ehresmann_factor(1.0 - 0.19) == pytest.approx(0.038, abs=1e-3)
    assert 1.0 - (1.0 - 0.19) == pytest.approx(0.19)  # naive dose ~ SVF: 5x too strong


def test_a6_walkback_1h_is_not_2km_on_slopes_and_ingress_halves_range() -> None:
    assert tobler_xeva_kmh(0.0) == pytest.approx(2.0, abs=0.02)
    uphill_10 = tobler_xeva_kmh(math.tan(math.radians(10.0)))
    assert 2.0 / uphill_10 > 1.5  # 2 km straight line at 10 deg up takes > 1.5 h
    assert tobler_xeva_kmh(0.0) * (1.0 - 0.5) == pytest.approx(1.0, abs=0.02)


def test_a7_metabolic_anchors_and_santee_unscaled_overshoot() -> None:
    assert o2_g_per_h(2505e3 / 3600.0) == pytest.approx(178.0, abs=1.0)
    norcross_level_w = 16.0 * 70.0 / 1000.0 * 20_100.0 / 60.0
    assert norcross_level_w == pytest.approx(375.0, abs=1.0)
    santee_level_w = 3.28 * (70.0 + 121.0) + 71.1  # Earth-calibrated, suit mass included
    assert santee_level_w / norcross_level_w > 1.8  # must be recalibrated, never used raw
    assert 2220e3 / 3600.0 < 31.8 * 70.0 / 1000.0 * 20_100.0 / 60.0  # 30 % grade > STD-3001


def test_a8_josang_floor_depends_on_effective_sample_size() -> None:
    _, _, i_20 = josang(r=0.0, s=20.0)
    assert i_20 == pytest.approx(2.0 / 22.0)
    _, _, i_300 = josang(r=0.0, s=300.0)
    assert i_300 < 0.01  # raw N (correlated stops) collapses I: N_eff must be declustered
    t, f, i = josang(0.0, 0.0)
    assert (t, f, i) == (0.0, 0.0, 1.0)


def test_a9_hurst_extrapolation_is_sensitive_outside_fitted_lags() -> None:
    assert 0.75 ** (0.7 - 1.0) == pytest.approx(1.090, abs=1e-3)
    assert 0.25 ** (0.3 - 1.0) > 2.5  # 3 m -> 0.75 m at H=0.3 more than doubles tan(slope)


# --------------------------------------------------------------------------- B. LIVE REGRESSIONS
def _cells() -> dict[tuple[int, int], dict]:
    grid = json.loads((PACK_DIR / "hazard_grid.json").read_text(encoding="utf-8"))
    return {(c["row"], c["col"]): c for c in grid["cells"]}


def _find_go_nogo_go_row() -> tuple[dict, dict] | None:
    cells = _cells()
    rows = 1 + max(r for r, _ in cells)
    cols = 1 + max(c for _, c in cells)
    for r in range(rows):
        verdicts = [cells[(r, c)]["verdict"] for c in range(cols)]
        for a in range(cols):
            for b in range(a + 2, cols):
                inner = verdicts[a + 1 : b]
                if verdicts[a] == verdicts[b] == "GO" and "NO_GO" in inner:
                    return cells[(r, a)], cells[(r, b)]
    return None


def test_b1_out_of_bbox_route_is_never_go() -> None:
    resp = client.post(
        "/v1/sites/jezero/evaluate-route",
        json={"points": [[80.0, 10.0], [80.001, 10.0]]},
    )
    assert resp.status_code == 422 or resp.json()["verdict"] == "NO_GO"


def test_b2_segment_crossing_no_go_cells_is_no_go() -> None:
    pair = _find_go_nogo_go_row()
    assert pair is not None
    a, b = pair
    resp = client.post(
        "/v1/sites/jezero/evaluate-route",
        json={"points": [[a["lon"], a["lat"]], [b["lon"], b["lat"]]]},
    )
    assert resp.json()["verdict"] == "NO_GO"


# --------------------------------------------------------------------------- C. CONFORMANCE
def _symbol(module: str, name: str):
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError:
        pytest.skip(f"{module} not shipped yet")
    if not hasattr(mod, name):
        pytest.skip(f"{module}.{name} not shipped yet")
    return getattr(mod, name)


def _phase3_pack() -> dict:
    grid = json.loads((PACK_DIR / "hazard_grid.json").read_text(encoding="utf-8"))
    if grid.get("contract_version") != "1.1.0":
        pytest.skip("pack still v1.0.0")
    return grid


def _request_supports(field: str) -> None:
    from marswalk.middleware.query_service import RouteEvaluationRequest

    if field not in RouteEvaluationRequest.model_fields:
        pytest.skip(f"RouteEvaluationRequest.{field} not shipped yet")


def test_c1_ground_step_matches_oracle() -> None:
    fn = _symbol("marswalk.engine.dtm_ingest", "ground_step_x_m")
    assert fn(PHI_JEZERO_DEG) == pytest.approx(0.9485, abs=1e-4)
    assert fn(0.0) == pytest.approx(1.0)


def test_c2_dose_factor_matches_ehresmann_oracle() -> None:
    fn = _symbol("marswalk.engine.radiation_svf", "ehresmann_dose_factor")
    for svf in (0.0, 0.5, 0.809, 1.0):
        assert fn(svf) == pytest.approx(ehresmann_factor(svf), abs=1e-6)


def test_c3_rf_loss_matches_itu_and_go_uses_link_margin() -> None:
    fn = _symbol("marswalk.engine.eva_human_rf", "fresnel_j_db")
    for nu in (-1.0, -0.78, -0.3, 0.0, 1.0, 3.0):
        assert fn(nu) == pytest.approx(fresnel_j_db(nu), abs=0.01)
    verdict = _symbol("marswalk.engine.eva_human_rf", "rf_verdict")
    assert verdict(nu_max=flat_ground_nu_max(1500.0), link_margin_db=6.0) == "GO"
    assert verdict(nu_max=2.0, link_margin_db=6.0) == "NO_GO"


def test_c4_metabolic_rate_inside_norcross_band_and_monotone_uphill() -> None:
    fn = _symbol("marswalk.engine.eva_human_rf", "metabolic_rate_w")
    level = fn(grade=0.0, payload_kg=0.0)
    assert 340.0 <= level <= 420.0
    rates = [fn(grade=g / 100.0, payload_kg=0.0) for g in (0, 10, 15, 20, 30)]
    assert rates == sorted(rates)
    assert 680.0 <= rates[-1] <= 820.0
    assert fn(grade=0.1, payload_kg=20.0) > fn(grade=0.1, payload_kg=0.0)


def test_c5_walkback_uses_path_time_and_counts_ingress_outside_the_hour() -> None:
    fn = _symbol("marswalk.engine.eva_human_rf", "walkback_return_h")
    assert fn(distance_m=2000.0, grade=0.0) == pytest.approx(1.0, abs=0.03)
    assert fn(distance_m=1000.0, grade=math.tan(math.radians(10.0))) > 0.9


def test_c6_josang_floor_and_vacuous_outside_aoa() -> None:
    fn = _symbol("marswalk.engine.calibration_aoa", "josang_opinion")
    t, f, i = fn(r=0.0, s=50.0, n_eff=20, inside_aoa=True)
    assert i >= 2.0 / 22.0 - 1e-9
    assert t + f + i == pytest.approx(1.0)
    assert fn(r=3.0, s=40.0, n_eff=20, inside_aoa=False)[2] == pytest.approx(1.0)


def test_c7_pack_v11_grid_is_40x40_and_verdicts_are_not_degenerate() -> None:
    grid = _phase3_pack()
    assert (grid["rows"], grid["cols"]) == (40, 40)
    assert len(grid["cells"]) == 1600
    n = len(grid["cells"])
    share = {v: sum(c["verdict"] == v for c in grid["cells"]) / n for v in ("GO", "NO_GO")}
    assert share["GO"] >= 0.05, "conjunctive D2 gates collapsed the map to CAUTION"
    assert share["NO_GO"] >= 0.05


def test_c8_cfa_floor_is_not_a_vacuous_fill() -> None:
    grid = _phase3_pack()
    values = {round(c["rock_cfa_pct"]["value"], 3) for c in grid["cells"] if c["rock_cfa_pct"]}
    assert len(values) > 1, "every cell sits on the 5 % floor: CFA carries no signal"


def test_c9_v11_models_still_accept_v10_documents() -> None:
    """Additive bump: Literal["1.1.0"] alone would reject every v1.0.0 document."""
    from typing import get_args

    from marswalk.contracts import models

    if models.CONTRACT_VERSION != "1.1.0":
        pytest.skip("contract still v1.0.0")
    for model in (models.HazardGrid, models.EvaConstraints, models.SiteManifest):
        accepted = get_args(model.model_fields["contract_version"].annotation)
        assert "1.0.0" in accepted and "1.1.0" in accepted, model.__name__


def _route(**extra) -> str:
    pair = [[77.3950, 18.4650], [77.3960, 18.4655]]
    resp = client.post("/v1/sites/jezero/evaluate-route", json={"points": pair, **extra})
    assert resp.status_code == 200
    return resp.json()["verdict"]


_RANK = {"GO": 0, "CAUTION": 1, "NO_GO": 2}


def test_c10_spe_alert_forces_no_go() -> None:
    _request_supports("spe_alert")
    assert _route(spe_alert=True) == "NO_GO"


def test_c11_dust_tau_is_monotone_and_respects_boundaries() -> None:
    _request_supports("dust_tau_880nm")
    ranks = [_RANK[_route(dust_tau_880nm=t)] for t in (0.25, 0.5, 0.75, 1.0, 1.01, 2.0)]
    assert ranks == sorted(ranks), "more dust must never improve the verdict"
    assert _route(dust_tau_880nm=2.0) == "NO_GO"
    assert _route(dust_tau_880nm=1.0) != "NO_GO"


@pytest.mark.parametrize("bad", [{"dust_tau_880nm": -0.1}, {"payload_kg": -5.0}])
def test_c12_physically_impossible_inputs_are_rejected(bad: dict) -> None:
    _request_supports(next(iter(bad)))
    resp = client.post(
        "/v1/sites/jezero/evaluate-route",
        json={"points": [[77.395, 18.465], [77.396, 18.466]], **bad},
    )
    assert resp.status_code == 422
