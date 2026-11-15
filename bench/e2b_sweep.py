"""CLI entrypoint for Block B3: 128-combination sweet-spot sweep & B8 2x2 km timing."""

from __future__ import annotations

import json
from pathlib import Path

from marswalk.bench.e2b_sweep import measure_b8_window_timing, run_sweet_spot_sweep_128


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sweep = run_sweet_spot_sweep_128(repo_root)
    timing = measure_b8_window_timing(repo_root)
    print(
        json.dumps(
            {
                "execution_backend": sweep["execution_backend"],
                "sweet_spot": sweep["sweet_spot"],
                "b8_seconds": timing["seconds"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
