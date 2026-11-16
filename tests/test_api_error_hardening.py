"""Error-path hardening: a rejected request must answer 422, never crash into a 500.

I keep these separate from the happy-path API tests on purpose: they attack the
code that runs *after* validation fails, where JSON rendering of the rejected
input (NaN / Infinity are not JSON compliant) used to blow up the server.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from marswalk.middleware.api import app

client = TestClient(app, raise_server_exceptions=False)

_JSON = {"content-type": "application/json"}


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/v1/sites/jezero/evaluate-route", '{"points": [[NaN, NaN], [77.4, 18.4]]}'),
        ("/v1/sites/jezero/evaluate-route", '{"points": [[77.4, 18.4], [Infinity, 18.4]]}'),
        ("/v1/sites/jezero/plan-route", '{"waypoints": [[-Infinity, 18.4], [77.4, 18.4]]}'),
        ("/v1/sites/jezero/evaluate-route", '{"points": [[77.4, 18.4]], "payload_kg": NaN}'),
    ],
)
def test_non_finite_coordinates_are_rejected_with_422_not_500(path: str, body: str) -> None:
    resp = client.post(path, content=body, headers=_JSON)
    assert resp.status_code == 422, resp.text
    payload = resp.json()  # must be strictly valid JSON
    assert isinstance(payload["detail"], list) and payload["detail"]
    for err in payload["detail"]:
        assert {"loc", "msg", "type"} <= err.keys()
    # The response must be strict JSON: no NaN / Infinity tokens leak back out.
    json.dumps(payload, allow_nan=False)


def test_validation_errors_do_not_echo_raw_client_input() -> None:
    """The 422 body describes *where* and *why*, never reflects the raw payload back."""
    resp = client.post(
        "/v1/sites/jezero/evaluate-route",
        content='{"points": [[1, 2]], "walking_speed_km_h": "<script>x</script>"}',
        headers=_JSON,
    )
    assert resp.status_code == 422
    assert "<script>" not in resp.text
    for err in resp.json()["detail"]:
        assert "input" not in err


# --- 404 information disclosure -------------------------------------------------

_LEAK_MARKERS = ("Users", "public_packs", ":\\", "/home/", "manifest.json at", "sha256")


def _assert_no_internal_detail(text: str) -> None:
    for marker in _LEAK_MARKERS:
        assert marker not in text, f"404 body leaks internal detail {marker!r}: {text}"


def test_unknown_site_404_does_not_leak_filesystem_paths() -> None:
    resp = client.get("/v1/sites/mars/manifest")
    assert resp.status_code == 404
    _assert_no_internal_detail(resp.text)


def test_tampered_pack_404_is_generic_but_logged_for_the_operator(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed integrity check answers a generic 404; the full reason goes to the server log."""
    import logging

    from marswalk.middleware import api
    from marswalk.middleware.pack_loader import PackIntegrityError

    secret = r"Missing pack file: D:\srv\public_packs\leaktest\v1\route.geojson"

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise PackIntegrityError(secret)

    api.get_query_service.cache_clear()
    monkeypatch.setattr(api, "load_and_verify_pack", _boom)
    try:
        with caplog.at_level(logging.WARNING, logger="marswalk.middleware.api"):
            resp = client.get("/v1/sites/leaktest/route")
    finally:
        api.get_query_service.cache_clear()

    assert resp.status_code == 404
    _assert_no_internal_detail(resp.text)
    assert secret in caplog.text, "operator lost the integrity failure reason"
