# Gemini Code Review Styleguide (`.gemini/styleguide.md`)

1. **Python 3.10+ & Ruff Compliance:** All Python code under `src/` and `tests/` must pass `ruff check .` (`E, F, I, UP, B`) and `ruff format --check .` with a 100-character line limit.
2. **Pydantic v2 Frozen Models:** All data contract models in `src/marswalk/contracts/models.py` must use `ConfigDict(frozen=True, extra="forbid")`.
3. **Deterministic Static Pack:** Running `build-pack` twice on the same inputs must produce byte-identical JSON/GeoJSON/PNG outputs (`SHA-256` invariant).
4. **Scientific Honesty:** Never mix `MEASURED`, `DERIVED`, and `SIMULATED` quantities without explicit `Quantity.tag` and `Quantity.source_id` metadata.
