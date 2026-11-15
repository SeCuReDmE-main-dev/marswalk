"""CLI entrypoint for `bench/spatial_cv.py` writing `bench/results/aoa_cv.json`."""

from __future__ import annotations

import json
from pathlib import Path

from marswalk.bench.spatial_cv import run_and_save_spatial_cv


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    payload = run_and_save_spatial_cv(repo_root)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
