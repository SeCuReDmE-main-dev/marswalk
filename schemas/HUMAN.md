# schemas/ — the contract, in a language your tools understand (read only)

> *The contract is my promise to you: the shape of the data will not move under your feet.*
> — Jean-Sébastien

These JSON Schema files (Draft 2020-12) are **exported automatically** from the Python contract in `src/marswalk/contracts/models.py`. They describe exactly what each pack file looks like. Do not edit them by hand: run `marswalk export-schemas` (or ask me) and they are regenerated.

| Schema | Describes |
|---|---|
| `SiteManifest.schema.json` | `manifest.json` |
| `WaypointFeatureCollection.schema.json` | `waypoints.geojson` |
| `EvaRoute.schema.json` | `route.geojson` |
| `HazardGrid.schema.json` | `hazard_grid.json` |
| `EvaConstraints.schema.json` | `eva_constraints.json` |

## Why they help you

1. **TypeScript types for free.** For example with the `json-schema-to-typescript` package:
   ```bash
   npx json-schema-to-typescript schemas/HazardGrid.schema.json -o frontend/src/types/HazardGrid.d.ts
   ```
   Your editor then autocompletes `cell.confidence.t` and warns you before a typo reaches the judges.
2. **Validation in development.** A validator such as Ajv can check the files you load and tell you immediately if a pack is broken.

## The one rule of the contract

Version `1.0.0` only **grows**: new optional fields can appear, but no existing field is ever removed or renamed. If your code works today, it keeps working tomorrow.
