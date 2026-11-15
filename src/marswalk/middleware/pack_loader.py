"""Cryptographic loader, SHA-256 verifier, and DERIVED provenance gate for site packs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from marswalk.contracts.models import (
    EvaConstraints,
    EvaRoute,
    HazardGrid,
    Quantity,
    SiteManifest,
    WaypointFeatureCollection,
)


class PackIntegrityError(RuntimeError):
    """Raised when a static pack fails SHA-256, byte-size, or DERIVED provenance validation."""


@dataclass(frozen=True)
class LoadedSitePack:
    """Verified in-memory representation of a site pack."""

    site_id: str
    pack_dir: Path
    manifest: SiteManifest
    waypoints: WaypointFeatureCollection
    route: EvaRoute
    hazards: HazardGrid
    constraints: EvaConstraints


def _verify_quantities_sources(
    obj: object,
    valid_source_ids: set[str],
    verified_input_source_ids: set[str],
    context: str,
) -> None:
    """Verify every Quantity source_id and require manifest.inputs[] for DERIVED tags."""
    if isinstance(obj, Quantity):
        if obj.source_id not in valid_source_ids:
            raise PackIntegrityError(
                f"{context}: Quantity references unknown source_id '{obj.source_id}'"
            )
        if obj.tag == "DERIVED" and obj.source_id not in verified_input_source_ids:
            raise PackIntegrityError(
                f"{context}: Quantity with tag='DERIVED' and source_id='{obj.source_id}' "
                "has no verified file entry in manifest.inputs[]"
            )
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _verify_quantities_sources(
                v, valid_source_ids, verified_input_source_ids, f"{context}.{k}"
            )
    elif isinstance(obj, (list, tuple)):
        for idx, item in enumerate(obj):
            _verify_quantities_sources(
                item, valid_source_ids, verified_input_source_ids, f"{context}[{idx}]"
            )
    elif hasattr(type(obj), "model_fields"):
        for field_name in getattr(type(obj), "model_fields", {}):
            _verify_quantities_sources(
                getattr(obj, field_name),
                valid_source_ids,
                verified_input_source_ids,
                f"{context}.{field_name}",
            )


def load_and_verify_pack(repo_root: Path, site_id: str = "jezero") -> LoadedSitePack:
    """Load `public_packs/<site_id>/v1/` and verify SHA-256 digests and provenance."""
    pack_dir = repo_root / "public_packs" / site_id / "v1"
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        raise PackIntegrityError(f"Missing manifest.json at {manifest_path}")

    manifest = SiteManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    if manifest.site_id != site_id:
        raise PackIntegrityError(
            f"Manifest site_id '{manifest.site_id}' does not match '{site_id}'"
        )

    for file_entry in manifest.files:
        target = pack_dir / file_entry.path
        if not target.exists():
            raise PackIntegrityError(f"Missing pack file: {target}")
        raw = target.read_bytes()
        if len(raw) != file_entry.bytes:
            raise PackIntegrityError(
                f"Byte size mismatch for {file_entry.path}: "
                f"expected {file_entry.bytes}, got {len(raw)}"
            )
        digest = hashlib.sha256(raw).hexdigest()
        if digest != file_entry.sha256:
            raise PackIntegrityError(
                f"SHA-256 mismatch for {file_entry.path}: "
                f"expected {file_entry.sha256}, got {digest}"
            )

    waypoints = WaypointFeatureCollection.model_validate(
        json.loads((pack_dir / "waypoints.geojson").read_text(encoding="utf-8"))
    )
    route = EvaRoute.model_validate(
        json.loads((pack_dir / "route.geojson").read_text(encoding="utf-8"))
    )
    hazards = HazardGrid.model_validate(
        json.loads((pack_dir / "hazard_grid.json").read_text(encoding="utf-8"))
    )
    constraints = EvaConstraints.model_validate(
        json.loads((pack_dir / "eva_constraints.json").read_text(encoding="utf-8"))
    )

    valid_sources = {s.id for s in manifest.sources}
    verified_inputs = {
        inp.source_id for inp in manifest.inputs if inp.bytes_read > 0 and len(inp.sha256) == 64
    }
    _verify_quantities_sources(waypoints, valid_sources, verified_inputs, "waypoints")
    _verify_quantities_sources(route, valid_sources, verified_inputs, "route")
    _verify_quantities_sources(hazards, valid_sources, verified_inputs, "hazards")
    _verify_quantities_sources(constraints, valid_sources, verified_inputs, "constraints")

    return LoadedSitePack(
        site_id=site_id,
        pack_dir=pack_dir,
        manifest=manifest,
        waypoints=waypoints,
        route=route,
        hazards=hazards,
        constraints=constraints,
    )
