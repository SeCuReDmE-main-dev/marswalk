# Security Policy (`SECURITY.md`)

## 1. Supported Versions

| Version | Contract Version | Supported |
| :--- | :--- | :--- |
| `0.1.x` (Space Apps 2026 Release) | `1.0.0` | Yes |

## 2. Security Guarantees & Repository Hygiene

This repository enforces automated security and hygiene checks in [`tests/test_repo_hygiene.py`](tests/test_repo_hygiene.py) and GitHub Actions CI:

1. **Zero Secrets or API Keys:** All NASA datasets (Mars Trek WMTS tiles, Mars 2020 MMGIS JSONs, USGS Astrogeology DTMs) are public, unauthenticated scientific endpoints. No API keys, tokens, or `.env` files are stored in the repository.
2. **Cryptographic Pack Integrity (`SHA-256`):** Every file inside `public_packs/jezero/v1/` is listed in `manifest.json` with its exact byte size and `SHA-256` digest, verified at startup by `marswalk.middleware.pack_loader` and in CI.
3. **Read-Only Middleware Surface:** The optional FastAPI service (`marswalk.middleware.api`) exposes strictly validated, read-only endpoints (`GET` and bounded `POST` over pre-validated Pydantic models) with zero shell execution, zero dynamic code evaluation, and zero filesystem write paths at runtime. One opt-in exception: `GET /v1/sites/{site_id}/waypoints/{sol}/cameras?allow_network=true` may call the NASA `raw_images` feed (4 s timeout) and cache the JSON under `datalake/m20_raw_images/`, but only when the operator sets `MARSWALK_ALLOW_CAMERA_FETCH=1`; a client flag alone never triggers network or disk writes.
4. **Zero Local Machine Leakage:** Automated hygiene tests scan all tracked files to ensure zero workstation paths, zero personal email addresses, and zero unimplemented stubs.

## 3. Reporting a Vulnerability

If you discover a security issue in this repository, please open a GitHub Security Advisory on the repository or contact the maintainers via GitHub (`@SeCuReDmE-main-dev`).

## Emergency stop

MarsWalk provides three independent emergency-stop tiers across domain physics, live API service control, and repository code state:

1. **Domain switch (`spe_alert = true`):** Activating the Solar Particle Event (`spe_alert`) switch on route evaluation immediately forces `verdict = "NO_GO"` and instructs the crew to abort EVA operations toward rover or habitat shielding.
2. **Service switch (`MARSWALK_SAFE_MODE=1`):** Setting `MARSWALK_SAFE_MODE=1` in the runtime environment (read dynamically on every request without restarting the process) disables route approval by forcing `POST /v1/sites/{site_id}/evaluate-route` to return `verdict = "NO_GO"` with reason `"SAFE_MODE: route planning disabled by operator"`, exposes `"safe_mode": true` on `GET /health`, and keeps static map pack `GET` endpoints available so situational awareness stays intact.
3. **Code rollback tag (`demo-stable`):** The annotated Git tag `demo-stable` freezes a verified, fail-safe baseline (`git checkout demo-stable`) for immediate rollback if an operational regression occurs.
