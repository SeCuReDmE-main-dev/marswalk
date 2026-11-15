"""Tests for MarsWalk frozen Data Contract v1.0.0 and exported Draft 2020-12 JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from marswalk.contracts.models import (
    CONTRACT_VERSION,
    MARS_SPHERE_RADIUS_M,
    EvaConstraints,
    EvaRoute,
    HazardGrid,
    MarsCrs,
    Quantity,
    SiteManifest,
    WaypointFeatureCollection,
)
from marswalk.middleware.build_pack import export_contract_schemas

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_contract_version_and_mars_sphere_constant() -> None:
    """Verify frozen contract version 1.0.0 and Mars sphere radius 3,396,190 m."""
    assert CONTRACT_VERSION == "1.0.0"
    assert MARS_SPHERE_RADIUS_M == 3_396_190.0
    crs = MarsCrs()
    assert crs.sphere_radius_m == 3_396_190.0
    assert crs.lon_domain == "east_positive_0_360"
    assert crs.lat_type == "planetocentric"

    with pytest.raises(ValidationError):
        MarsCrs(sphere_radius_m=3_376_200.0)


def test_quantity_validation_and_immutability() -> None:
    """Verify Quantity rejects NaN/Inf, invalid tags, and mutation."""
    q = Quantity(value=20.0, unit="deg", tag="MEASURED", source_id="SRC-NASA-XEVA")
    assert q.value == 20.0

    with pytest.raises(ValidationError):
        q.value = 15.0  # type: ignore[misc]

    with pytest.raises(ValidationError):
        Quantity(value=float("nan"), unit="deg", tag="MEASURED", source_id="SRC-NASA-XEVA")

    with pytest.raises(ValidationError):
        Quantity(value=float("inf"), unit="deg", tag="MEASURED", source_id="SRC-NASA-XEVA")

    with pytest.raises(ValidationError):
        Quantity(
            value=10.0,
            unit="deg",
            tag="UNKNOWN_TAG",  # type: ignore[arg-type]
            source_id="SRC-NASA-XEVA",
        )


def test_exported_schemas_match_pydantic_models(tmp_path: Path) -> None:
    """Verify schemas/*.schema.json match the live Pydantic v2 models byte-for-byte."""
    schemas_dir = REPO_ROOT / "schemas"
    expected_models = [
        ("SiteManifest", SiteManifest),
        ("WaypointFeatureCollection", WaypointFeatureCollection),
        ("HazardGrid", HazardGrid),
        ("EvaConstraints", EvaConstraints),
        ("EvaRoute", EvaRoute),
    ]

    exported = export_contract_schemas(tmp_path)
    assert len(exported) == len(expected_models)

    for name, _ in expected_models:
        committed_file = schemas_dir / f"{name}.schema.json"
        generated_file = tmp_path / f"{name}.schema.json"
        assert committed_file.exists(), f"Missing schema file: {committed_file}"
        committed_json = json.loads(committed_file.read_text(encoding="utf-8"))
        generated_json = json.loads(generated_file.read_text(encoding="utf-8"))
        assert committed_json["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert committed_json == generated_json
