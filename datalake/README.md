# Local NASA Raw Data Cache (`datalake/`)

This directory stores downloaded raw NASA/USGS files locally during pack generation (`M20_waypoints.json`, `M20_traverse.json`, HiRISE DTM subsets) and is intentionally ignored by Git (`.gitignore`).

To populate or refresh the local cache and rebuild `public_packs/jezero/v1/`, run:

```bash
python -m marswalk.middleware.cli build-pack --site jezero
```
