---
description: Rebuild and verify the Jezero v1 static pack, JSON schemas, and FastAPI test suite
---

1. Export the Draft 2020-12 JSON Schemas:
   ```bash
   python -m marswalk.middleware.cli export-schemas
   ```
2. Build and verify the Jezero v1 static pack:
   ```bash
   python -m marswalk.middleware.cli build-pack --site jezero
   python -m marswalk.middleware.cli verify-pack --site jezero
   ```
3. Run Ruff and Pytest:
   ```bash
   ruff check .
   ruff format --check .
   pytest -q --tb=short
   ```
