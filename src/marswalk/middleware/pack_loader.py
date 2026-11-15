"""Cryptographic loader, SHA-256 verifier, and DERIVED provenance gate for site packs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from marswalk.contracts.models import (
    EvaConstraints,
    EvaRoute,
    HazardGrid,
    ObstacleFeatureCollection,
    Quantity,
    SiteManifest,
    WaypointFeatureCollection,
)
from marswalk.engine.obstacles_m1 import PlannerGrid10m, load_planner_grid_10m_png

_SAFE_SITE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class PackIntegrityError(RuntimeError):
    """Raised when a static pack fails SHA-256, byte-size, or DERIVED provenance validation."""


def validate_safe_site_id(site_id: str) -> str:
    """Reject empty, overlong, or path-traversing `site_id` strings before disk/cache lookup."""
    if not isinstance(site_id, str) or not _SAFE_SITE_ID_RE.fullmatch(site_id):
        raise PackIntegrityError(f"Invalid site_id '{site_id}'")
    return site_id


def resolve_pack_relative_path(pack_dir: Path, rel_path: str) -> Path:
    """Resolve `rel_path` strictly inside `pack_dir` (rejects `..`, `:`, `\\`, absolute paths)."""
    if (
        not isinstance(rel_path, str)
        or not rel_path
        or "\\" in rel_path
        or ":" in rel_path
        or rel_path.startswith("/")
        or ".." in rel_path.split("/")
    ):
        raise PackIntegrityError(f"Unsafe pack-relative path '{rel_path}'")
    base_resolved = pack_dir.resolve()
    candidate = (base_resolved / rel_path).resolve()
    if candidate == base_resolved or not candidate.is_relative_to(base_resolved):
        raise PackIntegrityError(f"Pack file escapes pack directory: '{rel_path}'")
    return candidate


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
    obstacles: ObstacleFeatureCollection | None = None
    planner_grid_10m: PlannerGrid10m | None = None


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
    safe_site = validate_safe_site_id(site_id)
    packs_root = (repo_root / "public_packs").resolve()
    pack_dir = (packs_root / safe_site / "v1").resolve()
    if not pack_dir.is_relative_to(packs_root):
        raise PackIntegrityError(f"Pack directory escapes public_packs: {safe_site}")
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        raise PackIntegrityError(f"Missing manifest.json at {manifest_path}")

    manifest = SiteManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    if manifest.site_id != safe_site:
        raise PackIntegrityError(
            f"Manifest site_id '{manifest.site_id}' does not match '{safe_site}'"
        )

    for file_entry in manifest.files:
        target = resolve_pack_relative_path(pack_dir, file_entry.path)
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

    file_paths_in_manifest = {f.path for f in manifest.files}
    obstacles: ObstacleFeatureCollection | None = None
    if "obstacles.geojson" in file_paths_in_manifest:
        obstacles = ObstacleFeatureCollection.model_validate(
            json.loads((pack_dir / "obstacles.geojson").read_text(encoding="utf-8"))
        )
        for idx, feat in enumerate(obstacles.features):
            p = feat.properties
            if p.source_id not in valid_sources:
                raise PackIntegrityError(
                    f"obstacles.features[{idx}]: unknown source_id '{p.source_id}'"
                )
            if p.tag == "DERIVED" and p.source_id not in verified_inputs:
                raise PackIntegrityError(
                    f"obstacles.features[{idx}]: DERIVED source_id '{p.source_id}' "
                    "missing from manifest.inputs[]"
                )

    planner_grid: PlannerGrid10m | None = None
    if "planner_grid_10m.png" in file_paths_in_manifest:
        planner_grid = load_planner_grid_10m_png(
            pack_dir / "planner_grid_10m.png",
            bbox=hazards.bbox,
        )

    return LoadedSitePack(
        site_id=site_id,
        pack_dir=pack_dir,
        manifest=manifest,
        waypoints=waypoints,
        route=route,
        hazards=hazards,
        constraints=constraints,
        obstacles=obstacles,
        planner_grid_10m=planner_grid,
    )
