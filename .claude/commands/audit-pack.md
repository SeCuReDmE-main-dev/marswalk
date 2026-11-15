# Audit Static Pack & Contract Integrity (`/audit-pack`)

Run a complete deterministic audit of the `marswalk` repository:

1. Execute `python -m marswalk.middleware.cli verify-pack --site jezero` and confirm every file in `public_packs/jezero/v1/` matches its `SHA-256` digest and byte length in `manifest.json`.
2. Execute `pytest -q --tb=short` and verify that:
   - All exported JSON Schemas in `schemas/*.schema.json` match the Pydantic v2 models in `src/marswalk/contracts/models.py`;
   - All `708` Perseverance waypoints carry `MEASURED` tilt telemetry and valid planetocentric coordinates within the Jezero Crater bounding box;
   - Every `Quantity` references a valid `source_id` registered in `SiteManifest.sources`;
   - The 500-request concurrency stress test completes with `0` errors.
3. Execute `ruff check .` and `ruff format --check .`.
