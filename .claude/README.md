# Claude Code Configuration (`.claude/README.md`)

This directory contains workspace instructions, slash commands, and contract guardrails for **Claude Code** operating inside the `marswalk` repository.

- **`settings.json`:** Project-scoped verification commands (`pytest`, `ruff`) and read/write boundaries.
- **`commands/audit-pack.md`:** Custom `/audit-pack` slash command to verify JSON Schemas, `public_packs/jezero/v1/manifest.json` SHA-256 digests, and `MEASURED | DERIVED | SIMULATED` provenance tags.
- **`rules/contract-immutability.md`:** Enforces the frozen `v1.0.0` Data Contract and spherical Mars CRS (`R = 3,396,190 m`).
