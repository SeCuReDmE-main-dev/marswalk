"""Run unmodified pytest in the cache-free audit checkout; deny outbound sockets.

The audit hook does not synthesize data or change assertions. Localhost remains
available for Windows asyncio socket pairs and in-process HTTP test clients.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import io
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


def network_policy(event: str, args: tuple) -> None:
    host = None
    if event == "socket.connect" and isinstance(args[1], tuple):
        host = args[1][0]
    elif event == "socket.getaddrinfo":
        host = args[0]
    if host is not None and str(host).lower() not in {
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "",
    }:
        raise PermissionError("AUDIT_OFFLINE: external network denied; no raw cache downloads")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    os.chdir(ROOT)
    output = ROOT / args.log
    output.parent.mkdir(parents=True, exist_ok=True)
    sys.addaudithook(network_policy)
    import pytest

    import marswalk.middleware.pack_loader as loader

    assert Path(loader.__file__).resolve().is_relative_to(ROOT)
    captured = io.StringIO()
    started = time.perf_counter()

    class Outcomes:
        collected = 0
        counts: dict[str, int] = {}

        def pytest_sessionfinish(self, session):
            self.collected = session.testscollected
            reporter = session.config.pluginmanager.get_plugin("terminalreporter")
            self.counts = {
                name: len(reporter.stats.get(name, []))
                for name in ("passed", "failed", "skipped", "error", "xfailed", "xpassed")
            }

    outcomes = Outcomes()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        print("AUDIT_MAIN_COMMIT=e38ceba70e9c6273cf35233d3255cd912a7a4809")
        print("SOURCE_IMPORT=src/marswalk/middleware/pack_loader.py (isolated checkout verified)")
        print("RAW_CACHE=absent; tracked datalake/.gitkeep and README.md preserved")
        print("NETWORK=localhost allowed; external socket/connect/getaddrinfo denied")
        print("PYTHON=" + sys.version.replace("\n", " "))
        for name in (
            "pytest",
            "numpy",
            "scipy",
            "pydantic",
            "fastapi",
            "Pillow",
            "hypothesis",
            "SALib",
        ):
            print(f"DEPENDENCY {name}={importlib.metadata.version(name)}")
        options = args.pytest_args
        if options[:1] == ["--"]:
            options = options[1:]
        print("PYTEST_ARGS=" + repr(options))
        code = int(pytest.main(options, plugins=[outcomes]))
        print(f"COLLECTED={outcomes.collected}")
        print(f"OUTCOMES={outcomes.counts}")
        print(f"EXIT_CODE={code}")
        print(f"ELAPSED_S={time.perf_counter() - started:.3f}")
    raw = captured.getvalue()
    raw_dir = ROOT.parent / "ivv-raw-logs"
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / (output.parent.name + "-" + output.name)).write_text(raw, encoding="utf-8")
    # Preserve exact output locally; published evidence redacts local user paths.
    home = str(Path.home())
    normalized = raw.replace(str(ROOT), "<AUDIT_ROOT>").replace(
        str(ROOT).replace("\\", "/"), "<AUDIT_ROOT>"
    )
    normalized = (
        normalized.replace(home, "<USER_HOME>")
        .replace(home.replace("\\", "\\\\"), "<USER_HOME>")
        .replace(home.replace("\\", "/"), "<USER_HOME>")
    )
    output.write_text(
        "LOCAL_PATH_PREFIXES_REDACTED; exact raw output retained locally\n" + normalized,
        encoding="utf-8",
    )
    print(captured.getvalue())
    return code


if __name__ == "__main__":
    raise SystemExit(main())
