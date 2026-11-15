"""CLI entrypoint for `bench/eval.py` writing `bench/results/b5_eval.json`."""

from __future__ import annotations

import json
from pathlib import Path

from marswalk.bench.eval import run_and_save_b5_eval


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    payload = run_and_save_b5_eval(repo_root)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
