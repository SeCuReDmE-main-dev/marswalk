# Contributing to MarsWalk (`CONTRIBUTING.md`)

Thank you for contributing to **MarsWalk**! We are a team of two, so I keep it simple: everyone works on `main`, in separate folders.

---

## 1. One Branch, Separate Folders

- **`main`** is the only long-lived branch. Pull before you start, push small commits often.
- **`frontend/`** belongs to the frontend lead (teammate). The engine never edits it.
- **`src/marswalk/`, `tests/`, `bench/`, `public_packs/`, `schemas/`** belong to the engine (jean). The frontend reads them and never edits them.
- **`shared/`** is common ground: handoffs and journal, through `tools/spaceapps_bridge.py`.
- Because the folders do not overlap, two people pushing to `main` almost never conflict. If a short experiment needs a branch, it is merged back and deleted the same day.

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
