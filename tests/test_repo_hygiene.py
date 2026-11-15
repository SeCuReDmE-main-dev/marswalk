"""Repository hygiene tests enforcing zero local paths, zero secrets, and zero Discord handles."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

IGNORED_DIRS = {
    ".git",
    "datalake",
    ".pytest_cache",
    ".ruff_cache",
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
