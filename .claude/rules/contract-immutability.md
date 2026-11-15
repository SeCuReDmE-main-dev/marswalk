# Contract Immutability & Geodesy Rule (`.claude/rules/contract-immutability.md`)

1. **Frozen `v1.0.0` Schema:** Do not alter field names, types, or enum literals in `src/marswalk/contracts/models.py` without bumping `contract_version` and regenerating `schemas/*.schema.json`.
2. **Mars Spherical Datum (`R = 3,396,190 m`):** All coordinates in `public_packs/` must be planetocentric East longitude and latitude on the `3,396,190 m` sphere used by NASA Mars Trek and USGS Astrogeology.
3. **Zero Frontend Intrusion:** When working on `feat/engine`, never modify files inside `frontend/`.
