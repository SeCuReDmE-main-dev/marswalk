"""Phase 5 fail-safe tests: missing/NaN data, engine exceptions, and optional layer absence."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marswalk.contracts.models import Quantity
from marswalk.middleware.api import app, get_query_service
from marswalk.middleware.pack_loader import load_and_verify_pack
from marswalk.middleware.query_service import PackQueryService, RouteEvaluationRequest

REPO_ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _fresh_service() -> PackQueryService:
    return PackQueryService(load_and_verify_pack(REPO_ROOT, site_id="jezero"))


def _find_two_adjacent_go_cells(svc: PackQueryService) -> tuple[object, object]:
    by_rc = {(c.row, c.col): c for c in svc.pack.hazards.cells}
    for (r, c), cell_a in sorted(by_rc.items()):
        if cell_a.verdict != "GO":
            continue
        cell_b = by_rc.get((r, c + 1))
        if cell_b is not None and cell_b.verdict == "GO":
            return cell_a, cell_b
    raise AssertionError("Expected at least two horizontally adjacent GO cells in Jezero pack")


def test_nan_slope_cell_forces_no_go() -> None:
    """Any NaN or infinite required slope in a traversed or queried cell forces NO_GO."""
    svc = _fresh_service()
    cell_a, cell_b = _find_two_adjacent_go_cells(svc)
    nan_q = Quantity.model_construct(
        value=float("nan"),
        unit="deg",
        tag="DERIVED",
        source_id="SRC-USGS-HIRISE-DTM-1M",
    )
    bad_slopes = dict(cell_a.slope_deg_by_baseline)  # type: ignore[attr-defined]
    bad_slopes["4"] = nan_q
    object.__setattr__(cell_a, "slope_deg_by_baseline", bad_slopes)

    req = RouteEvaluationRequest(points=[(cell_a.lon, cell_a.lat), (cell_b.lon, cell_b.lat)])  # type: ignore[attr-defined]
    res = svc.evaluate_route(req)
    assert res.verdict == "NO_GO"
    assert any(
        r.startswith(f"FAIL_SAFE: missing slope_deg_by_baseline[4] in {cell_a.cell_id}")  # type: ignore[attr-defined]
        for r in res.reasons
    )

    lookup = svc.lookup_cell(cell_a.lon, cell_a.lat)  # type: ignore[attr-defined]
    assert lookup.cell.verdict == "NO_GO"
    assert lookup.cell.reason.startswith(
        f"FAIL_SAFE: missing slope_deg_by_baseline[4] in {cell_a.cell_id}"  # type: ignore[attr-defined]
    )


def test_missing_required_quantity_forces_no_go() -> None:
    """A None required quantity (e.g. elev_m or scale_divergence) forces NO_GO."""
    svc = _fresh_service()
    cell_a, cell_b = _find_two_adjacent_go_cells(svc)
    object.__setattr__(cell_b, "scale_divergence", None)

    req = RouteEvaluationRequest(points=[(cell_a.lon, cell_a.lat), (cell_b.lon, cell_b.lat)])  # type: ignore[attr-defined]
    res = svc.evaluate_route(req)
    assert res.verdict == "NO_GO"
    assert any(
        r.startswith(f"FAIL_SAFE: missing scale_divergence in {cell_b.cell_id}")  # type: ignore[attr-defined]
        for r in res.reasons
    )

    lookup = svc.lookup_cell(cell_b.lon, cell_b.lat)  # type: ignore[attr-defined]
    assert lookup.cell.verdict == "NO_GO"
    assert lookup.cell.reason.startswith(
        f"FAIL_SAFE: missing scale_divergence in {cell_b.cell_id}"  # type: ignore[attr-defined]
    )


def test_engine_exception_returns_no_go_not_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """An internal engine exception returns HTTP 200 with NO_GO and zero traceback leakage."""
    svc = get_query_service("jezero")

    def _boom(_req: RouteEvaluationRequest) -> None:
        raise RuntimeError("synthetic internal failure secret_stack_frame")

    monkeypatch.setattr(svc, "_evaluate_route_impl", _boom)
    resp = client.post(
        "/v1/sites/jezero/evaluate-route",
        json={"points": [[77.3950, 18.4650], [77.3960, 18.4655]]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "NO_GO"
    assert "FAIL_SAFE: engine error" in body["reasons"]
    assert "secret_stack_frame" not in resp.text
    assert "Traceback" not in resp.text


def test_optional_layer_absent_never_improves_verdict() -> None:
    """Missing optional telemetry appears in reasons and never improves verdict."""
    rank = {"GO": 0, "CAUTION": 1, "NO_GO": 2}
    svc_present = _fresh_service()
    svc_absent = _fresh_service()

    all_available = {
        k: {**(v if isinstance(v, dict) else {}), "available": True}
        for k, v in (svc_present.pack.hazards.external_layers_status or {}).items()
    }
    all_missing = {
        k: {**(v if isinstance(v, dict) else {}), "available": False}
        for k, v in (svc_absent.pack.hazards.external_layers_status or {}).items()
    }
    object.__setattr__(svc_present.pack.hazards, "external_layers_status", all_available)
    object.__setattr__(svc_absent.pack.hazards, "external_layers_status", all_missing)

    cell_a, cell_b = _find_two_adjacent_go_cells(svc_present)
    pts_go = [(cell_a.lon, cell_a.lat), (cell_b.lon, cell_b.lat)]  # type: ignore[attr-defined]
    res_present_go = svc_present.evaluate_route(RouteEvaluationRequest(points=pts_go))
    res_absent_go = svc_absent.evaluate_route(RouteEvaluationRequest(points=pts_go))
    assert res_absent_go.verdict != "NO_GO"
    assert rank[res_absent_go.verdict] >= rank[res_present_go.verdict]
    assert "layer themis_ti_100m unavailable" in res_absent_go.reasons
    assert "layer crism_mtrdr_18m unavailable" in res_absent_go.reasons

    pts_caution = [(77.3950, 18.4650), (77.3960, 18.4655)]
    res_present_caut = svc_present.evaluate_route(RouteEvaluationRequest(points=pts_caution))
    res_absent_caut = svc_absent.evaluate_route(RouteEvaluationRequest(points=pts_caution))
    assert rank[res_absent_caut.verdict] >= rank[res_present_caut.verdict]
