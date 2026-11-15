"""Tests for Jezero v1 static pack SHA-256 integrity, deterministic rebuild, and data bounds."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from marswalk.middleware.build_pack import build_jezero_pack
from marswalk.middleware.pack_loader import load_and_verify_pack

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_jezero_pack_loads_and_verifies_sha256() -> None:
    """Verify all files in public_packs/jezero/v1/ pass SHA-256 and Pydantic checks."""
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    assert pack.site_id == "jezero"
    assert pack.manifest.contract_version == "1.0.0"
    assert len(pack.manifest.files) == 5

    # Total pack size must be strictly under 5 MB for instant static hosting
    total_bytes = sum(f.bytes for f in pack.manifest.files)
    assert total_bytes < 5 * 1024 * 1024

    # All 708 Perseverance waypoints must be present and inside manifest.bbox
    assert len(pack.waypoints.features) == 708
    min_lon, min_lat, max_lon, max_lat = pack.manifest.bbox
    sols: list[int] = []
    max_tilt = 0.0
    for wp in pack.waypoints.features:
        lon = wp.properties.lon
        lat = wp.properties.lat
        assert min_lon <= lon <= max_lon
        assert min_lat <= lat <= max_lat
        assert wp.properties.rover_tilt_deg.tag == "MEASURED"
        assert wp.properties.elev_geoid_m.tag == "MEASURED"
        sols.append(wp.properties.sol)
        if wp.properties.rover_tilt_deg.value > max_tilt:
            max_tilt = wp.properties.rover_tilt_deg.value

    assert min(sols) == 13
    assert max(sols) == 2022
    assert max_tilt > 20.0  # Sol 1578 recorded 20.68 deg tilt


def test_hazard_grid_baselines_and_confidence() -> None:
    """Verify every cell in hazard_grid.json has 1/4/16/64m baselines and valid verdicts."""
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    assert pack.hazards.rows == 16
    assert pack.hazards.cols == 24
    assert len(pack.hazards.cells) == 384

    verdicts = {c.verdict for c in pack.hazards.cells}
    assert verdicts == {"GO", "CAUTION", "NO_GO"}

    for cell in pack.hazards.cells:
        assert set(cell.slope_deg_by_baseline.keys()) == {"1", "4", "16", "64"}
        assert cell.scale_divergence.value >= 0.0
        assert 0.0 <= cell.confidence.t <= 1.0
        assert 0.0 <= cell.confidence.i <= 1.0
        assert 0.0 <= cell.confidence.f <= 1.0


def test_deterministic_pack_rebuild_produces_identical_sha256(tmp_path: Path) -> None:
    """Verify running build_jezero_pack twice produces byte-for-byte identical SHA-256 digests."""
    # Reuse cached M20 JSON files from datalake/ to avoid redundant network downloads
    tmp_datalake = tmp_path / "datalake"
    tmp_datalake.mkdir(parents=True, exist_ok=True)
    for fname in ("M20_waypoints.json", "M20_traverse.json"):
        shutil.copy2(REPO_ROOT / "datalake" / fname, tmp_datalake / fname)

    manifest_rebuild = build_jezero_pack(tmp_path)
    pack_committed = load_and_verify_pack(REPO_ROOT, site_id="jezero")

    committed_digests = {f.path: f.sha256 for f in pack_committed.manifest.files}
    rebuilt_digests = {f.path: f.sha256 for f in manifest_rebuild.files}
    assert committed_digests == rebuilt_digests

    committed_manifest_sha = hashlib.sha256(
        (REPO_ROOT / "public_packs" / "jezero" / "v1" / "manifest.json").read_bytes()
    ).hexdigest()
    rebuilt_manifest_sha = hashlib.sha256(
        (tmp_path / "public_packs" / "jezero" / "v1" / "manifest.json").read_bytes()
    ).hexdigest()
    assert committed_manifest_sha == rebuilt_manifest_sha
