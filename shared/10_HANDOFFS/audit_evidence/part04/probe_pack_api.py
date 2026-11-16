"""Independent pack arithmetic and isolated mutation/API probes; never edits source pack."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)


def distance(a, b):
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    )
    return 2 * 3396190 * math.atan2(math.sqrt(h), math.sqrt(max(0, 1 - h)))


def main():
    from fastapi.testclient import TestClient

    from marswalk.middleware import api
    from marswalk.middleware.build_pack import export_contract_schemas
    from marswalk.middleware.map_card import generate_survival_map_svg
    from marswalk.middleware.pack_loader import PackIntegrityError, load_and_verify_pack

    base = ROOT / "public_packs/jezero/v1"

    def read(name):
        return json.loads((base / name).read_text(encoding="utf-8"))

    manifest, route, hazards, waypoints = map(
        read, ("manifest.json", "route.geojson", "hazard_grid.json", "waypoints.geojson")
    )
    actual = {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}
    listed = {f["path"] for f in manifest["files"]}
    results = {
        "commit": "e38ceba70e9c6273cf35233d3255cd912a7a4809",
        "manifest_sha256": hashlib.sha256((base / "manifest.json").read_bytes()).hexdigest(),
        "listed_files": len(listed),
        "total_listed_bytes": sum(f["bytes"] for f in manifest["files"]),
        "files_not_listed_excluding_manifest": sorted(actual - listed - {"manifest.json"}),
        "source_count": len(manifest["sources"]),
        "sources": [{"id": s["id"], "url": s["url"]} for s in manifest["sources"]],
        "waypoints": len(waypoints["features"]),
        "grid_cells": len(hazards["cells"]),
    }
    ids = {s["id"] for s in manifest["sources"]}
    quantities = []

    def walk(obj):
        if isinstance(obj, dict):
            if {"value", "unit", "tag", "source_id"} <= obj.keys():
                quantities.append(obj)
            for val in obj.values():
                walk(val)
        elif isinstance(obj, list):
            for val in obj:
                walk(val)

    for name in ("waypoints.geojson", "route.geojson", "hazard_grid.json", "eva_constraints.json"):
        walk(read(name))
    results["quantity_count"] = len(quantities)
    results["quantity_unknown_sources"] = sorted(
        {q["source_id"] for q in quantities if q["source_id"] not in ids}
    )
    benchmark = next(f for f in route["features"] if f["properties"].get("sol") == 700)
    lon, lat = benchmark["geometry"]["coordinates"][:2]
    w, s, e, n = hazards["bbox"]
    row = min(hazards["rows"] - 1, int((n - lat) / (n - s) * hazards["rows"]))
    col = min(hazards["cols"] - 1, int((lon - w) / (e - w) * hazards["cols"]))
    cell = next(c for c in hazards["cells"] if c["row"] == row and c["col"] == col)
    results["sol700"] = {
        "cell": cell["cell_id"],
        "tilt_deg": benchmark["properties"]["rover_tilt_deg"]["value"],
        "slopes": {k: v["value"] for k, v in cell["slope_deg_by_baseline"].items()},
        "cell_verdict": cell["verdict"],
    }
    nearest = min(hazards["cells"], key=lambda c: (c["lon"] - lon) ** 2 + (c["lat"] - lat) ** 2)
    validation = read("validation_report.json")
    results["sol700_nearest_center"] = {
        "cell": nearest["cell_id"],
        "slopes": {k: v["value"] for k, v in nearest["slope_deg_by_baseline"].items()},
    }
    results["sol700_validation_samples"] = [
        p
        for p in validation["samples"]
        if p.get("sol") == 700 or "SOL700" in str(p.get("waypoint_id", ""))
    ]
    results["routes"] = []
    for f in route["features"]:
        if f["properties"]["segment_type"] not in {
            "DERIVED_OBSTACLE_AWARE_EVA",
            "SIMULATED_ASTRONAUT_EVA",
        }:
            continue
        points = f["geometry"]["coordinates"]
        results["routes"].append(
            {
                "type": f["properties"]["segment_type"],
                "distance_m_recomputed": sum(
                    distance(a, b) for a, b in zip(points, points[1:], strict=False)
                ),
                "walkback_m_recomputed": max(distance(points[0], p) for p in points),
                "stored_distance_m": f["properties"]["distance_m"]["value"],
                "verdict": f["properties"]["verdict"],
            }
        )
    (ROOT / "work").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "work", prefix="part04-probe-") as temp:
        tmp = Path(temp)
        destination = tmp / "public_packs/jezero/v1"
        shutil.copytree(base, destination)
        rejected = []
        for name in sorted(listed):
            target = destination / name
            original = target.read_bytes()
            altered = bytearray(original)
            altered[0] ^= 1
            target.write_bytes(altered)
            try:
                load_and_verify_pack(tmp)
            except PackIntegrityError:
                rejected.append(name)
            finally:
                target.write_bytes(original)
        results["one_byte_mutations_rejected"] = rejected
        modified_manifest = json.loads(json.dumps(manifest))
        modified_manifest["files"] = [
            f for f in modified_manifest["files"] if f["path"] != "waypoints.geojson"
        ]
        (destination / "manifest.json").write_text(json.dumps(modified_manifest), encoding="utf-8")
        mutated_waypoints = json.loads(json.dumps(waypoints))
        mutated_waypoints["features"][0]["properties"]["rover_tilt_deg"]["value"] = 88.0
        (destination / "waypoints.geojson").write_text(
            json.dumps(mutated_waypoints), encoding="utf-8"
        )
        try:
            loaded = load_and_verify_pack(tmp)
            results["omitted_waypoints_hash_accepted_tilt_deg"] = loaded.waypoints.features[
                0
            ].properties.rover_tilt_deg.value
        except Exception as exc:
            results["omitted_waypoints_result"] = type(exc).__name__
        shutil.copyfile(base / "manifest.json", destination / "manifest.json")
        shutil.copyfile(base / "waypoints.geojson", destination / "waypoints.geojson")
        with patch.object(api, "_default_repo_root", return_value=tmp):
            api.get_query_service.cache_clear()
            client = TestClient(api.app, raise_server_exceptions=False)
            url = "/v1/sites/jezero/panoramas/sol_0700_ncam.jpg"
            first = client.get(url)
            target = destination / "panoramas/sol_0700_ncam.jpg"
            altered = bytearray(target.read_bytes())
            altered[-10] ^= 1
            target.write_bytes(altered)
            second = client.get(url)
            results["cached_file_integrity"] = {
                "before_http": first.status_code,
                "after_mutation_http": second.status_code,
                "served_bytes_changed": first.content != second.content,
                "served_sha_matches_manifest": hashlib.sha256(second.content).hexdigest()
                == next(
                    f["sha256"]
                    for f in manifest["files"]
                    if f["path"] == "panoramas/sol_0700_ncam.jpg"
                ),
            }
            results["path_traversal_http"] = {
                p: client.get("/v1/sites/jezero/panoramas/" + p).status_code
                for p in (
                    "%2e%2e%2fmanifest.json",
                    "..%5cmanifest.json",
                    "unlisted.jpg",
                    "sol_0700_ncam.jpg/extra",
                )
            }
            api.get_query_service.cache_clear()
        schemas = export_contract_schemas(tmp / "schemas")
        results["schema_byte_equality"] = {
            p.name: p.read_bytes() == (ROOT / "schemas" / p.name).read_bytes() for p in schemas
        }
        generated = generate_survival_map_svg(ROOT, output_path=tmp / "map.svg")
        results["svg_byte_equal"] = (
            generated.read_bytes()
            == (ROOT / "docs/assets/jezero_eva_survival_map.svg").read_bytes()
        )
        results["svg_sha256"] = hashlib.sha256(generated.read_bytes()).hexdigest()
    payload = {"points": [[77.39, 18.46], [77.391, 18.461]]}
    client = TestClient(api.app, raise_server_exceptions=False)
    with patch.dict(os.environ, {"MARSWALK_SAFE_MODE": "1"}):
        results["safe_mode"] = {
            "health": client.get("/health").json(),
            "evaluate": client.post("/v1/sites/jezero/evaluate-route", json=payload).json()[
                "verdict"
            ],
            "plan": client.post(
                "/v1/sites/jezero/plan-route", json={"waypoints": payload["points"]}
            ).json()["verdict"],
        }
    with patch.object(
        api, "get_query_service", side_effect=RuntimeError("audit service initialization error")
    ):
        results["service_initialization_error_http"] = {
            name: client.post("/v1/sites/jezero/" + name, json=body).status_code
            for name, body in (
                ("evaluate-route", payload),
                ("plan-route", {"waypoints": payload["points"]}),
            )
        }
    api.get_query_service.cache_clear()
    text = json.dumps(results, indent=2)
    (ROOT / "shared/10_HANDOFFS/audit_evidence/part04/probe-results.json").write_text(
        text, encoding="utf-8"
    )
    print(text)


if __name__ == "__main__":
    main()
