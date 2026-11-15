"""Tests for MarsWalk FastAPI middleware endpoints and 500-request concurrency stress test."""

from __future__ import annotations

import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from marswalk.middleware.api import app

client = TestClient(app)


def test_all_rest_endpoints_return_200_and_valid_schemas() -> None:
    """Verify all GET and POST endpoints on /v1/sites/jezero/*."""
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json() == {"status": "ok", "contract_version": "1.1.0", "safe_mode": False}

    r_sites = client.get("/v1/sites")
    assert r_sites.status_code == 200
    assert "jezero" in r_sites.json()["sites"]

    r_manifest = client.get("/v1/sites/jezero/manifest")
    assert r_manifest.status_code == 200
    assert r_manifest.json()["site_id"] == "jezero"
    assert r_manifest.json()["pack_version"] == "1.1.0"

    r_wp = client.get("/v1/sites/jezero/waypoints")
    assert r_wp.status_code == 200
    assert len(r_wp.json()["features"]) == 708

    r_route = client.get("/v1/sites/jezero/route")
    assert r_route.status_code == 200
    assert len(r_route.json()["features"]) == 7

    r_haz = client.get("/v1/sites/jezero/hazards")
    assert r_haz.status_code == 200
    assert r_haz.json()["grid_status"] == "ENGINE"
    assert len(r_haz.json()["cells"]) == 1600

    r_png = client.get("/v1/sites/jezero/hazard-overlay.png")
    assert r_png.status_code == 200
    assert r_png.headers["content-type"] == "image/png"
    assert len(r_png.content) > 100

    r_const = client.get("/v1/sites/jezero/constraints")
    assert r_const.status_code == 200
    assert r_const.json()["suit_max_slope_deg"]["value"] == 20.0

    r_cell = client.get("/v1/sites/jezero/cell?lon=77.450886&lat=18.444627")
    assert r_cell.status_code == 200
    cell_data = r_cell.json()
    assert cell_data["cell"]["verdict"] in ("GO", "CAUTION", "NO_GO")
    assert cell_data["nearest_waypoint"]["properties"]["sol"] == 13


def test_route_evaluation_go_and_nogo() -> None:
    """Verify POST /v1/sites/jezero/evaluate-route distinguishes safe and unsafe routes."""
    r_safe = client.post(
        "/v1/sites/jezero/evaluate-route",
        json={
            "points": [
                [77.3950, 18.4650],
                [77.3960, 18.4655],
            ],
            "walking_speed_km_h": 2.5,
        },
    )
    assert r_safe.status_code == 200
    safe_body = r_safe.json()
    assert safe_body["walkback_within_limit"] is True
    assert safe_body["verdict"] in ("GO", "CAUTION")

    r_unsafe = client.post(
        "/v1/sites/jezero/evaluate-route",
        json={
            "points": [
                [77.450886, 18.444627],
                [77.408763, 18.458109],
                [77.257976, 18.453010],
            ],
            "walking_speed_km_h": 2.2,
        },
    )
    assert r_unsafe.status_code == 200
    unsafe_body = r_unsafe.json()
    assert unsafe_body["walkback_within_limit"] is False
    assert unsafe_body["verdict"] == "NO_GO"


def test_500_concurrent_requests_zero_errors() -> None:
    """Execute 500 concurrent requests across /cell and /evaluate-route with 0 errors."""
    total_requests = 500

    def _worker(idx: int) -> tuple[int, float]:
        t0 = time.perf_counter()
        if idx % 2 == 0:
            lon = 77.378 + (idx % 20) * 0.0015
            lat = 18.450 + (idx % 8) * 0.0035
            resp = client.get(f"/v1/sites/jezero/cell?lon={lon:.5f}&lat={lat:.5f}")
        else:
            resp = client.post(
                "/v1/sites/jezero/evaluate-route",
                json={
                    "points": [
                        [77.3950, 18.4650],
                        [77.3960, 18.4655],
                    ],
                    "walking_speed_km_h": 2.2,
                },
            )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return resp.status_code, elapsed_ms

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(_worker, range(total_requests)))

    statuses = [s for s, _ in results]
    latencies_ms = sorted(lat for _, lat in results)
    p50_ms = statistics.median(latencies_ms)
    p95_ms = latencies_ms[int(0.95 * len(latencies_ms)) - 1]

    assert all(s == 200 for s in statuses), f"Non-200 statuses detected: {set(statuses)}"
    assert p95_ms < 500.0, f"p95 latency too high: {p95_ms:.2f} ms"
    print(f"\n[LOAD TEST 500 REQ] errors=0 | p50={p50_ms:.2f}ms | p95={p95_ms:.2f}ms")
