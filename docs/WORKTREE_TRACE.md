# Repository Worktree & Branch Trace (`docs/WORKTREE_TRACE.md`)

This document maps the exact directory structure, branch topology, and data flow of the **MarsWalk** repository so both teammates and judges can trace every file from raw NASA telemetry to the interactive frontend.

---

## 1. Branch Topology (single `main`, separate folders)

```text
main   (contract v1.0.0 + signed pack public_packs/jezero/v1/ + middleware + multi-scale engine + frontend/)
```

- **History:** the first evening used three branches (`feat/ui`, `feat/engine`, `docs/philippe-onboarding`). For a team of two, they were merged into `main` on 2026-11-14 at about 22h30 EST and deleted. The full history stays in `git log`.
- **Why one branch is enough:** the frontend works only in `frontend/`, the engine only in `src/`, `tests/`, `bench/`, `public_packs/` and `schemas/`. The folders never overlap, so two people can push to `main` without stepping on each other.

---

## 2. Directory & File Trace

```text
marswalk/
├── README.md                          # Project overview, architecture & quickstart
├── LICENSE                            # Apache-2.0 open-source license
├── NOTICE                             # Copyright & attribution notice
├── THIRD_PARTY_NOTICES.md             # NASA/JPL/USGS citations + Open Government Licence – Canada
├── CITATION.cff                       # Academic & hackathon citation metadata
├── AGENTS.md                          # Multi-agent rules (Claude, Antigravity, Gemini, Codex)
├── HUMAN.md                           # Human team charter & responsibilities
├── SECURITY.md                        # Security guarantees & SHA-256 verification policy
├── CONTRIBUTING.md                    # Branch workflow & pre-commit checklist
├── CODE_OF_CONDUCT.md                 # Contributor Covenant v2.1
├── pyproject.toml                     # Python package, Ruff & Pytest configuration
├── .claude/                           # Claude Code workspace configuration & audit commands
├── .antigravity/                      # Google Antigravity governance rules & workflows
├── .antigravity-ide/                  # Antigravity IDE task & workspace definitions
├── .gemini/                           # Gemini code review styleguide & settings
├── .github/                           # GitHub Actions CI & PR/Issue templates
├── datalake/                          # Gitignored local cache for raw NASA JSONs & GeoTIFFs
├── docs/
│   ├── AI_USAGE.md                    # Official NASA Space Apps AI transparency disclosure
│   ├── WORKTREE_TRACE.md              # This branch & directory topology trace
│   └── contracts/
│       └── 10_CONTRAT_DONNEES.md      # Frozen v1.0.0 Data Contract specification
├── frontend/
│   └── README.md                      # 10-line fetch() quickstart + Mars Trek WMTS guide for teammate
├── schemas/                           # Auto-generated JSON Schemas (Draft 2020-12)
│   ├── SiteManifest.schema.json
│   ├── WaypointFeatureCollection.schema.json
│   ├── HazardGrid.schema.json
│   ├── EvaConstraints.schema.json
│   └── EvaRoute.schema.json
├── public_packs/
│   └── jezero/
│       └── v1/                        # Committed, SHA-256 signed static data pack (< 5 MB)
│           ├── manifest.json
│           ├── waypoints.geojson
│           ├── route.geojson
│           ├── hazard_grid.json
│           ├── hazard_overlay.png
│           └── eva_constraints.json
├── src/
│   └── marswalk/
│       ├── __init__.py
│       ├── contracts/                 # Frozen Pydantic v2 models (v1.0.0)
│       │   ├── __init__.py
│       │   └── models.py
│       └── middleware/                # Deterministic builder, SHA-256 loader, FastAPI & CLI
│           ├── __init__.py
│           ├── build_pack.py
│           ├── pack_loader.py
│           ├── query_service.py
│           ├── api.py
│           └── cli.py
└── tests/                             # Automated verification suite
    ├── test_contracts_and_schemas.py
    ├── test_pack_integrity.py
    ├── test_api_and_load.py
    └── test_repo_hygiene.py
```
