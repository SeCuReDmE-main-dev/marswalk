# Antigravity Workspace Governance (`.antigravity/rules/workspace-governance.md`)

1. **Zero Stubs or Placeholders:** Every Python module in `src/marswalk/` must be fully implemented and covered by `pytest`. `NotImplementedError` and empty placeholder functions are strictly prohibited.
2. **Static Pack First:** `public_packs/jezero/v1/` is the primary contract artifact consumed by `frontend/`. Always keep `manifest.json` SHA-256 digests synchronized via `python -m marswalk.middleware.cli build-pack --site jezero`.
3. **Clean Repository Hygiene:** Never commit raw GeoTIFFs from `datalake/`, local workstation paths, or personal email addresses.
