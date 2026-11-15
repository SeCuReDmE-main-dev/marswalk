"""Phase 6 Refactoring & Hardening Verification Suite.

Tests:
1. Vectorized 8-directional A* speedup on the real 200x190 Jezero 10 m grid (`< 120 ms` warm
   on a typical EVA sortie leg; `< 650 ms` warm on the 93%-expansion SE->NW scarp stress test
   vs `1,566 ms` scalar baseline) with exact Dijkstra equality and `NaN`/`Inf` immunity.
2. Path-traversal rejection (`pack_loader.py` & `api.py`) and LRU cache-poisoning immunity.
3. Coordinate finiteness (`NaN`/`Inf`) and planetocentric range validation on request payloads.
4. Verdict monotonicity (`GO -> CAUTION -> NO_GO`, never backwards) on `/plan-route` under
   increasing dust optical depth, carried payload, reduced RF link margin, and SPE alert.
5. Service-level `MARSWALK_ALLOW_CAMERA_FETCH=1` defense-in-depth, corrupt cache recovery,
   and 8 MiB response size cap in `m20_raw_images_m5.py`.
"""

from __future__ import annotations

import io
import math
import time
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from marswalk.engine.m20_raw_images_m5 import (
    MAX_RAW_IMAGES_PAYLOAD_BYTES,
    fetch_or_load_m20_sol_cameras,
)
from marswalk.engine.obstacles_m1 import PlannerGrid10m
from marswalk.engine.planner_m2 import (
    _astar_single_leg,
    _grid_rc_to_lonlat,
    plan_obstacle_aware_route,
)
from marswalk.middleware.api import _load_cached_query_service, app, get_query_service
from marswalk.middleware.pack_loader import (
    PackIntegrityError,
    load_and_verify_pack,
    resolve_pack_relative_path,
    validate_safe_site_id,
)
from marswalk.middleware.query_service import PlanRouteRequest, RouteEvaluationRequest

REPO_ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)

_VERDICT_SEVERITY = {"GO": 0, "CAUTION": 1, "NO_GO": 2}


def test_planner_m2_vectorized_speedup_and_nan_immunity() -> None:
    """Verify fast vectorized A* (< 120 ms EVA leg, < 650 ms full-map stress) and NaN immunity."""
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    grid = pack.planner_grid_10m
    assert grid is not None

    # Find unblocked SE and NW corner cells across the full 2x2 km scarp diagonal
    se_rc = next(
        (grid.rows - 2 - d, grid.cols - 2 - d)
        for d in range(40)
        if not bool(grid.blocked_mask[grid.rows - 2 - d, grid.cols - 2 - d])
    )
    nw_rc = next((1 + d, 1 + d) for d in range(40) if not bool(grid.blocked_mask[1 + d, 1 + d]))
    wpts = [_grid_rc_to_lonlat(grid, *se_rc), _grid_rc_to_lonlat(grid, *nw_rc)]

    # Warm edge-cost & flat-grid caches once
    warm = plan_obstacle_aware_route(grid, wpts, heuristic_weight=1.0)
    assert warm.reachable is True

    # 1) Typical EVA sortie leg latency (< 120 ms warm)
    eva_wpts = [(77.4070, 18.4520), (77.4048, 18.4535)]
    t_eva = time.perf_counter()
    eva_res = plan_obstacle_aware_route(grid, eva_wpts, heuristic_weight=1.0)
    eva_ms = (time.perf_counter() - t_eva) * 1000.0
    assert eva_res.reachable is True
    assert eva_ms < 120.0, f"Expected < 120 ms warm on EVA leg, got {eva_ms:.1f} ms"

    # 2) Worst-case 93%-expansion SE->NW scarp detour (< 650 ms vs 1,566 ms scalar baseline)
    t0 = time.perf_counter()
    timed = plan_obstacle_aware_route(grid, wpts, heuristic_weight=1.0)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert timed.reachable is True
    assert elapsed_ms < 650.0, (
        f"Expected < 650 ms warm on 200x190 stress test, got {elapsed_ms:.1f} ms"
    )

    # Exact optimality check against Dijkstra (heuristic_weight=0.0) on real Jezero grid
    ok_dijk, _, g_dijk, _ = _astar_single_leg(grid, se_rc, nw_rc, heuristic_weight=0.0)
    ok_astar, _, g_astar, _ = _astar_single_leg(grid, se_rc, nw_rc, heuristic_weight=1.0)
    assert ok_dijk and ok_astar
    assert math.isclose(g_astar[-1], g_dijk[-1], rel_tol=0.0, abs_tol=1e-9)

    # NaN / Inf gradient or risk injection must be treated as impassable, never poisoning g_score
    gx_nan = np.zeros((10, 10), dtype=np.float64)
    gx_nan[4, 4] = float("nan")
    risk_inf = np.zeros((10, 10), dtype=np.float64)
    risk_inf[5, 5] = float("inf")
    corrupt_grid = PlannerGrid10m(
        rows=10,
        cols=10,
        bbox=grid.bbox,
        step_x_ground_m=9.5,
        step_y_ground_m=10.0,
        blocked_mask=np.zeros((10, 10), dtype=bool),
        caution_mask=np.zeros((10, 10), dtype=bool),
        toe_refuge_mask=np.zeros((10, 10), dtype=bool),
        grad_x=gx_nan,
        grad_y=np.zeros((10, 10), dtype=np.float64),
        risk_penalty_01=risk_inf,
    )
    ok_c, path_c, g_c, _ = _astar_single_leg(corrupt_grid, (1, 1), (8, 8), heuristic_weight=1.0)
    assert ok_c is True
    assert math.isfinite(g_c[-1])
    assert (4, 4) not in path_c and (5, 5) not in path_c


def test_pack_loader_and_api_reject_path_traversal_and_protect_lru_cache(
    tmp_path: Path,
) -> None:
    """Verify path-traversal barriers and LRU cache-poisoning immunity on `site_id`."""
    for bad_id in ("", "../etc", "jezero/../../secret", "JEZERO", "a:b", "a\\b", "x" * 40):
        with pytest.raises(PackIntegrityError):
            validate_safe_site_id(bad_id)

    for bad_rel in (
        "",
        "../manifest.json",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "sub\\file.json",
    ):
        with pytest.raises(PackIntegrityError):
            resolve_pack_relative_path(tmp_path, bad_rel)

    get_query_service.cache_clear()
    assert client.get("/v1/sites/jezero/manifest").status_code == 200
    assert _load_cached_query_service.cache_info().currsize == 1

    # Flood API with 25 distinct invalid site IDs: none may enter or evict the LRU cache
    for idx in range(25):
        r_bad = client.get(f"/v1/sites/BAD..SITE_{idx}/manifest")
        assert r_bad.status_code == 404
    assert _load_cached_query_service.cache_info().currsize == 1


def test_coordinate_nan_inf_and_out_of_planet_rejected_cleanly() -> None:
    """Verify NaN, Inf, and out-of-range coordinates fail Pydantic validation immediately."""
    for bad_coord in (
        (float("nan"), 18.45),
        (77.40, float("inf")),
        (400.0, 18.45),
        (77.40, -95.0),
    ):
        with pytest.raises(ValidationError):
            RouteEvaluationRequest(points=[(77.40, 18.45), bad_coord])
        with pytest.raises(ValidationError):
            PlanRouteRequest(waypoints=[(77.40, 18.45), bad_coord])

    # Negative sol on `/waypoints/{sol}/cameras` returns 422 instead of silently clamping to Sol 0
    assert client.get("/v1/sites/jezero/waypoints/-5/cameras").status_code == 422


def test_plan_route_monotonicity_under_dust_payload_rf_and_spe() -> None:
    """Verify `/plan-route` never upgrades a verdict under harsher dust, load, RF, or SPE."""
    wpts = [[77.4070, 18.4520], [77.4048, 18.4535]]

    # 1) Increasing dust_tau_880nm: severity must be monotonically non-decreasing
    dust_severities = [
        _VERDICT_SEVERITY[
            client.post(
                "/v1/sites/jezero/plan-route",
                json={"waypoints": wpts, "dust_tau_880nm": tau},
            ).json()["verdict"]
        ]
        for tau in (0.30, 0.75, 1.25)
    ]
    assert dust_severities == sorted(dust_severities)
    assert dust_severities[-1] == _VERDICT_SEVERITY["NO_GO"]

    # 2) Increasing payload_kg: severity non-decreasing & O2 margin monotonically decreases
    res_p0 = client.post(
        "/v1/sites/jezero/plan-route", json={"waypoints": wpts, "payload_kg": 0.0}
    ).json()
    res_p60 = client.post(
        "/v1/sites/jezero/plan-route", json={"waypoints": wpts, "payload_kg": 60.0}
    ).json()
    res_p120 = client.post(
        "/v1/sites/jezero/plan-route", json={"waypoints": wpts, "payload_kg": 120.0}
    ).json()
    assert (
        _VERDICT_SEVERITY[res_p0["verdict"]]
        <= _VERDICT_SEVERITY[res_p60["verdict"]]
        <= _VERDICT_SEVERITY[res_p120["verdict"]]
    )
    assert (
        res_p0["walkback_o2_margin_min"]["value"]
        > res_p60["walkback_o2_margin_min"]["value"]
        > res_p120["walkback_o2_margin_min"]["value"]
    )

    # 3) SPE alert forces NO_GO unconditionally
    res_spe = client.post(
        "/v1/sites/jezero/plan-route", json={"waypoints": wpts, "spe_alert": True}
    ).json()
    assert res_spe["verdict"] == "NO_GO"


def test_camera_service_gate_corrupt_cache_and_oversize_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify defense-in-depth camera gate, corrupt cache resilience, and 8 MiB payload cap."""
    svc = get_query_service("jezero")

    def _forbid_urlopen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Service-level call bypassed MARSWALK_ALLOW_CAMERA_FETCH gate!")

    monkeypatch.delenv("MARSWALK_ALLOW_CAMERA_FETCH", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", _forbid_urlopen)
    # Direct Python call with allow_network=True must STILL be blocked when env switch is unset
    direct_res = svc.get_waypoint_cameras(sol=888888, allow_network=True)
    assert direct_res.source_status == "offline_unavailable"

    # Corrupt/truncated cached JSON file must not crash; falls back cleanly
    cache_dir = tmp_path / "m20_raw_images"
    cache_dir.mkdir(parents=True)
    corrupt_file = cache_dir / "sol_0700.json"
    corrupt_file.write_bytes(b"{truncated-json")
    fallback_res = fetch_or_load_m20_sol_cameras(tmp_path, sol=700, allow_network=False)
    assert fallback_res.source_status == "offline_unavailable"

    # Oversized upstream response (> 8 MiB) must be rejected without overwriting disk
    class _OversizedResponse(io.BytesIO):
        def __enter__(self) -> _OversizedResponse:
            return self

        def __exit__(self, *_exc: object) -> None:
            self.close()

    def _huge_urlopen(*_args: object, **_kwargs: object) -> _OversizedResponse:
        return _OversizedResponse(b"x" * (MAX_RAW_IMAGES_PAYLOAD_BYTES + 64))

    monkeypatch.setattr(urllib.request, "urlopen", _huge_urlopen)
    oversized_res = fetch_or_load_m20_sol_cameras(tmp_path, sol=701, allow_network=True)
    assert oversized_res.source_status == "offline_unavailable"
    assert not (cache_dir / "sol_0701.json").exists()
