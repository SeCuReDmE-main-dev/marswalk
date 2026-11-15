# Contributing to MarsWalk (`CONTRIBUTING.md`)

Thank you for contributing to **MarsWalk**! To keep parallel frontend (`feat/ui`) and backend/engine (`feat/engine`) development fast and conflict-free, please follow this workflow.

---

## 1. Branch Workflow

- **`main`:** Protected baseline containing the frozen `v1.0.0` data contract (`src/marswalk/contracts/`, `schemas/`, `public_packs/jezero/v1/`) and verified releases.
- **`feat/ui`:** Owned by **Frontend (teammate)** for all work under `frontend/`.
- **`feat/engine`:** Owned by **Engine (jean)** for middleware and multi-scale terrain engine upgrades under `src/marswalk/` and `tests/`.

---

## 2. Pre-Commit Verification Checklist

Before opening a Pull Request or merging into `main`, run the following three commands from the repository root:

```bash
# 1. Lint check (must return 0 warnings/errors)
ruff check .

# 2. Formatting check
ruff format --check .

# 3. Full test suite (schemas, SHA-256 pack integrity, 500-req load test, repo hygiene)
pytest -q --tb=short
```

---

## 3. Contract Discipline (`v1.0.0`)

1. Do **not** rename or remove fields in `public_packs/jezero/v1/*` or `src/marswalk/contracts/models.py` without coordinating across both teammates.
2. Every physical value added to the contract must use `Quantity(value=..., unit=..., tag="MEASURED"|"DERIVED"|"SIMULATED", source_id=...)` with its `source_id` registered in `manifest.json`.
3. Never commit raw GeoTIFFs or temporary caches (`datalake/` is gitignored).
