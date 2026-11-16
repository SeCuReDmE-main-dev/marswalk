"""Capture Part 1 probe stdout, stderr, and exit code without local paths in evidence."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent


def main() -> int:
    env = dict(os.environ, PYTHONPATH="src", PYTHONUTF8="1")
    source = "shared/10_HANDOFFS/audit_evidence/part01/probe_geodesy.py"
    result = subprocess.run(
        [sys.executable, source],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    raw = (
        f"COMMAND=python {source}\nSTDOUT_BEGIN\n{result.stdout}STDOUT_END\n"
        f"STDERR_BEGIN\n{result.stderr}STDERR_END\nEXIT_CODE={result.returncode}\n"
    )
    raw_path = ROOT.parent / "ivv-raw-logs/part01-probes.log"
    raw_path.parent.mkdir(exist_ok=True)
    raw_path.write_text(raw, encoding="utf-8")
    sanitized = raw.replace(str(ROOT), "<AUDIT_CHECKOUT>").replace(str(Path.home()), "<USER_HOME>")
    (EVIDENCE / "probes.log").write_text(sanitized, encoding="utf-8")
    (EVIDENCE / "probe_output.json").write_text(result.stdout, encoding="utf-8")
    print(f"PROBE_EXIT_CODE={result.returncode}; stdout/stderr captured in part01/probes.log")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
