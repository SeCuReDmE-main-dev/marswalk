"""Block B5 Tests: Regenerated Pack Funnel Provenance, 1m Baseline Note, and Math Tiers."""

from __future__ import annotations

import json
from pathlib import Path

from marswalk.engine.carriers import build_cell_carrier_triplets
from marswalk.middleware.pack_loader import load_and_verify_pack

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_1M_NOTE = "below 2x DTM resolution: pixel-scale noise, excluded from the funnel"


def test_baseline_1m_kept_with_note_and_excluded_from_funnel() -> None:
    """Claude CTO 22h sync (NB-001.a): '1' kept with note, excluded from funnel."""
    pack = load_and_verify_pack(REPO_ROOT, site_id="jezero")
    assert len(pack.hazards.cells) == 384

    for cell in pack.hazards.cells:
        assert set(cell.slope_deg_by_baseline.keys()) == {"1", "4", "16", "64"}
        q1 = cell.slope_deg_by_baseline["1"]
        assert q1.tag == "DERIVED"
        assert q1.source_id == "SRC-USGS-HIRISE-DTM-1M"
        assert q1.note == EXPECTED_1M_NOTE

        # Verify 4m, 16m, 64m remain clean without the 1m exclusion note
        for b_key in ("4", "16", "64"):
            assert cell.slope_deg_by_baseline[b_key].note is None

        # Verify I* > 0 everywhere (B9) and zero forbidden UI jargon in cell.reason
        assert cell.confidence.i > 0.0
        reason_lower = cell.reason.lower()
        assert "t/i/f" not in reason_lower
        assert "plithogenic" not in reason_lower
        assert "plithogénique" not in reason_lower

    # Directly verify the funnel carrier builder excludes scale 1m on 1.0 m/px DTM
    triplets = build_cell_carrier_triplets(
        slopes_by_scale={1: 32.0, 4: 8.5, 16: 6.2, 64: 4.8},
        roughness_rms_m=0.04,
        fractal_d=2.24,
        curvature_m_inv=0.02,
        walkback_m=400.0,
        nodata_fraction=0.0,
        source_id="SRC-USGS-HIRISE-DTM-1M",
        dtm_resolution_m=1.0,
    )
    assert all(tr.scale_m != 1 for tr in triplets)
    assert {tr.scale_m for tr in triplets} == {4, 16, 64}


def test_b5_pack_sha256_matches_b5_eval_record() -> None:
    """Verify bench/results/b5_eval.json sha256_pack matches regenerated manifest.json."""
    import hashlib

    manifest_sha = hashlib.sha256(
        (REPO_ROOT / "public_packs" / "jezero" / "v1" / "manifest.json").read_bytes()
    ).hexdigest()
    b5_eval = json.loads(
        (REPO_ROOT / "bench" / "results" / "b5_eval.json").read_text(encoding="utf-8")
    )
    assert b5_eval["sha256_pack"] == manifest_sha


def test_engine_math_has_three_epistemic_tiers_and_section_7_links() -> None:
    """Verify docs/ENGINE_MATH.md distinguishes established math, proposals, and pytest proofs."""
    doc = (REPO_ROOT / "docs" / "ENGINE_MATH.md").read_text(encoding="utf-8")
    assert "Established mathematics" in doc
    assert "I propose" in doc
    assert "Tested by" in doc
    assert "https://stac.astrogeology.usgs.gov/docs/data/mars/hirise_dtms/" in doc
    assert "https://pgda.gsfc.nasa.gov/products/70" in doc
    assert "https://www.sciencedirect.com/science/article/pii/S0307904X13004642" in doc
    assert ("O(" + "1)") not in doc
