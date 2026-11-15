"""Repository hygiene tests enforcing zero local paths, zero secrets, and zero Discord handles."""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

IGNORED_DIRS = {
    ".git",
    "datalake",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
}


def _iter_repo_text_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(REPO_ROOT).parts
        if any(p in IGNORED_DIRS or p.endswith(".egg-info") for p in rel_parts):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip"}:
            continue
        files.append(path)
    return files


def test_zero_local_paths_and_zero_excluded_terms() -> None:
    """Verify no tracked file contains local paths, Discord handles, or excluded claims."""
    forbidden_substrings = [
        "C:\\" + "Users",
        "c:\\" + "users",
        "C:/" + "Users",
        "c:/" + "users",
        "@" + "EbaAaZ",
        "@" + "Maptop",
        "WeatherNext",
        "orbital AI heat",
        "orbital digestion",
        "O(" + "1)",
    ]
    this_file = Path(__file__).resolve()

    for path in _iter_repo_text_files():
        if path.resolve() == this_file:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in forbidden_substrings:
            assert token not in text, (
                f"Forbidden token '{token}' found in {path.relative_to(REPO_ROOT)}"
            )


def test_zero_not_implemented_stubs_in_src() -> None:
    """Verify no Python module in src/marswalk/ contains NotImplementedError stubs."""
    src_dir = REPO_ROOT / "src" / "marswalk"
    for py_file in src_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert "NotImplementedError" not in text, f"Stub found in {py_file}"


def test_no_backend_directory_in_pass_1() -> None:
    """Verify Pass 1 preserves the clean contract + middleware structure without backend/."""
    assert not (REPO_ROOT / "backend").exists()
    assert not (REPO_ROOT / "src" / "marswalk" / "backend").exists()


def test_no_secret_patterns_in_tracked_files() -> None:
    """Scan all tracked text files from `git ls-files` for secret tokens and `.env`."""
    this_file = Path(__file__).resolve()
    binary_suffixes = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".pdf",
        ".zip",
        ".tif",
        ".tiff",
    }
    secret_patterns = [
        ("ghp_", re.compile(r"\bghp_[A-Za-z0-9_]+")),
        ("github_pat_", re.compile(r"\bgithub_pat_[A-Za-z0-9_]+")),
        ("sk-", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
        ("e2b_", re.compile(r"\be2b_[A-Za-z0-9]{10,}\b")),
        ("AKIA", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        ("xox", re.compile(r"\bxox[bap]-[A-Za-z0-9-]+")),
        ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
        (
            "non_empty_password_or_secret",
            re.compile(
                r"(?m)^[ \t]*(?:export[ \t]+)?(?:PASSWORD|SECRET)[ \t]*=[ \t]*['\"]?[^\s'\"#]+"
            ),
        ),
    ]

    tracked_raw = subprocess.check_output(
        ["git", "ls-files"], cwd=REPO_ROOT, text=True, encoding="utf-8"
    )
    for rel_str in tracked_raw.splitlines():
        rel_str = rel_str.strip()
        if not rel_str:
            continue
        path = (REPO_ROOT / rel_str).resolve()
        assert path.name != ".env" and not path.name.startswith(".env."), (
            f"Tracked .env file is forbidden: {rel_str}"
        )
        if path == this_file or not path.is_file():
            continue
        if path.suffix.lower() in binary_suffixes:
            continue
        raw_bytes = path.read_bytes()
        if b"\x00" in raw_bytes[:4096]:
            continue
        text = raw_bytes.decode("utf-8", errors="ignore")
        for pat_name, rx in secret_patterns:
            assert rx.search(text) is None, (
                f"Secret pattern '{pat_name}' detected in tracked file {rel_str}"
            )


def test_bridge_rejects_path_traversal(tmp_path: Path) -> None:
    """Verify spaceapps_bridge rejects `..`, leading `/`, `\\`, and drive letters."""
    bridge_path = REPO_ROOT / "tools" / "spaceapps_bridge.py"
    spec = importlib.util.spec_from_file_location("spaceapps_bridge", bridge_path)
    assert spec is not None and spec.loader is not None
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)

    vault_dir = tmp_path / "shared"
    canary_json = tmp_path / "outside_canary.json"
    canary_initial = '{"status": "UNTOUCHED"}\n'
    canary_json.write_text(canary_initial, encoding="utf-8")

    # Seed one valid ticket inside shared/10_HANDOFFS/
    created = bridge.handoff_create(
        sender="claude", to="antigravity", title="Valid", body="Valid ticket", vault_dir=vault_dir
    )
    assert created["id"] == "HO-001"

    malicious_inputs = [
        "../../outside_canary",
        "../outside_canary",
        "HO-001/../../outside_canary",
        "/outside_canary",
        "\\outside_canary",
        "D:/outside_canary",
        "D:\\outside_canary",
    ]
    for bad_id in malicious_inputs:
        with pytest.raises(ValueError):
            bridge.handoff_ack(handoff_id=bad_id, by_agent="tester", vault_dir=vault_dir)
        with pytest.raises(ValueError):
            bridge.pivot_append(section=bad_id, text="probe", vault_dir=vault_dir)
        with pytest.raises(ValueError):
            bridge._safe_child_path(vault_dir / "10_HANDOFFS", f"{bad_id}.json")

        mcp_resp = bridge.handle_mcp_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "handoff_ack", "arguments": {"handoff_id": bad_id}},
            },
            vault_dir=vault_dir,
        )
        assert mcp_resp is not None
        assert mcp_resp["result"]["isError"] is True

    # Ensure zero files were modified or created outside shared/
    assert canary_json.read_text(encoding="utf-8") == canary_initial
    outside_items = {p.name for p in tmp_path.iterdir()}
    assert outside_items == {"shared", "outside_canary.json"}
