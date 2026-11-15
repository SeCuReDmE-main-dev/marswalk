"""Command-line interface for MarsWalk schema export, pack build, and SHA-256 verification."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from marswalk.middleware.build_pack import build_jezero_pack, export_contract_schemas
from marswalk.middleware.map_card import generate_survival_map_svg
from marswalk.middleware.pack_loader import load_and_verify_pack


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    """Run the MarsWalk middleware CLI."""
    parser = argparse.ArgumentParser(
        prog="marswalk-cli",
        description="MarsWalk Data Contract & Static Pack Builder CLI (v1.0.0)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("export-schemas", help="Export Draft 2020-12 JSON Schemas into schemas/")

    p_build = sub.add_parser("build-pack", help="Build and sign a static site pack")
    p_build.add_argument("--site", default="jezero", choices=["jezero"])
    p_build.add_argument("--mode", default="engine", choices=["engine", "placeholder"])

    p_verify = sub.add_parser("verify-pack", help="Verify SHA-256 digests and contract schemas")
    p_verify.add_argument("--site", default="jezero", choices=["jezero"])

    p_card = sub.add_parser(
        "generate-map-card",
        help="Generate a standalone SVG EVA survival map card from the verified site pack",
    )
    p_card.add_argument("--site", default="jezero", choices=["jezero"])
    p_card.add_argument(
        "--output",
        default=None,
        help="Optional output SVG path (defaults to docs/assets/<site>_eva_survival_map.svg)",
    )

    args = parser.parse_args(argv)
    root = _repo_root()

    if args.command == "export-schemas":
        written = export_contract_schemas(root / "schemas")
        for p in written:
            print(f"[SCHEMA] {p.relative_to(root)}")
        return 0

    if args.command == "build-pack":
        manifest = build_jezero_pack(root, mode=args.mode)
        print(
            f"[PACK BUILT] site={manifest.site_id} "
            f"contract={manifest.contract_version} pack_version={manifest.pack_version}"
        )
        for f in manifest.files:
            print(f"  - {f.path}: {f.bytes} bytes | sha256={f.sha256}")
        return 0

    if args.command == "verify-pack":
        loaded = load_and_verify_pack(root, site_id=args.site)
        print(
            f"[PACK VERIFIED] site={loaded.site_id} "
            f"waypoints={len(loaded.waypoints.features)} "
            f"cells={len(loaded.hazards.cells)} "
            f"files={len(loaded.manifest.files)}"
        )
        return 0

    if args.command == "generate-map-card":
        out_override = Path(args.output) if args.output is not None else None
        written_svg = generate_survival_map_svg(root, site_id=args.site, output_path=out_override)
        print(f"[MAP CARD] site={args.site} path={written_svg} bytes={written_svg.stat().st_size}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
