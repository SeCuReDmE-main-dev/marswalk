# Security Policy (`SECURITY.md`)

## 1. Supported Versions

| Version | Contract Version | Supported |
| :--- | :--- | :--- |
| `0.1.x` (Space Apps 2026 Release) | `1.0.0` | Yes |

## 2. Security Guarantees & Repository Hygiene

This repository enforces automated security and hygiene checks in [`tests/test_repo_hygiene.py`](tests/test_repo_hygiene.py) and GitHub Actions CI:

1. **Zero Secrets or API Keys:** All NASA datasets (Mars Trek WMTS tiles, Mars 2020 MMGIS JSONs, USGS Astrogeology DTMs) are public, unauthenticated scientific endpoints. No API keys, tokens, or `.env` files are stored in the repository.
2. **Cryptographic Pack Integrity (`SHA-256`):** Every file inside `public_packs/jezero/v1/` is listed in `manifest.json` with its exact byte size and `SHA-256` digest, verified at startup by `marswalk.middleware.pack_loader` and in CI.
3. **Read-Only Middleware Surface:** The optional FastAPI service (`marswalk.middleware.api`) exposes strictly validated, read-only endpoints (`GET` and bounded `POST` over pre-validated Pydantic models) with zero shell execution, zero dynamic code evaluation, and zero filesystem write paths at runtime.
4. **Zero Local Machine Leakage:** Automated hygiene tests scan all tracked files to ensure zero workstation paths, zero personal email addresses, and zero unimplemented stubs.

## 3. Reporting a Vulnerability

If you discover a security issue in this repository, please open a GitHub Security Advisory on the repository or contact the maintainers via GitHub (`@SeCuReDmE-main-dev`).
