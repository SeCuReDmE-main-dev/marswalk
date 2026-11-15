## Summary

- **Track (folder):** `frontend/` | engine (`src/`, `tests/`, `bench/`, `public_packs/`)
- **Contract Impact:** None (`v1.0.0` preserved) | Additive bump

## Verification Checklist

- [ ] `ruff check .` and `ruff format --check .` pass with 0 warnings
- [ ] `python -m marswalk.middleware.cli verify-pack --site jezero` passes
- [ ] `pytest -q --tb=short` passes (100% green)
- [ ] No files outside my branch track (`frontend/` vs `src/marswalk/`) were modified without coordination
