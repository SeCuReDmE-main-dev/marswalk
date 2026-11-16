"""Recalculate map-card numbers without importing the card or engine geometry code."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "public_packs/jezero/v1"


def read(name):
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def dist(a, b):
    p, q = math.radians(a[1]), math.radians(b[1])
    h = (
        math.sin((q - p) / 2) ** 2
        + math.cos(p) * math.cos(q) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    )
    return 6792380 * math.atan2(math.sqrt(h), math.sqrt(max(0, 1 - h)))


def orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def between(a, b, p):
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def intersects(a, b, c, d):
    x, y, z, w = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if x * y < 0 and z * w < 0:
        return True
    return any(
        v == 0 and between(p, q, r)
        for v, p, q, r in ((x, a, b, c), (y, a, b, d), (z, c, d, a), (w, c, d, b))
    )


def inside(p, ring):
    parity = False
    for a, b in zip(ring, ring[1:], strict=False):
        if orient(a, b, p) == 0 and between(a, b, p):
            return True
        if (a[1] > p[1]) != (b[1] > p[1]):
            xx = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if xx > p[0]:
                parity = not parity
    return parity


route, grid, obstacles, wp = map(
    read, ("route.geojson", "hazard_grid.json", "obstacles.geojson", "waypoints.geojson")
)
stops = [f for f in route["features"] if f["properties"]["segment_type"] == "SCIENCE_STOP"]
origin = stops[0]["geometry"]["coordinates"]
out = {
    "source_commit": "e38ceba70e9c6273cf35233d3255cd912a7a4809",
    "grid_verdicts": dict(Counter(c["verdict"] for c in grid["cells"])),
    "stops": {},
    "routes": {},
}
for stop in stops:
    out["stops"][str(stop["properties"]["sol"])] = dist(origin, stop["geometry"]["coordinates"])
for feat in route["features"]:
    if feat["properties"]["segment_type"] not in {
        "SIMULATED_ASTRONAUT_EVA",
        "DERIVED_OBSTACLE_AWARE_EVA",
    }:
        continue
    coords = feat["geometry"]["coordinates"]
    hits = []
    for ob in obstacles["features"]:
        ring = ob["geometry"]["coordinates"][0]
        if any(inside(p, ring) for p in coords) or any(
            intersects(a, b, c, d)
            for a, b in zip(coords, coords[1:], strict=False)
            for c, d in zip(ring, ring[1:], strict=False)
        ):
            hits.append(ob["properties"]["obstacle_id"])
    out["routes"][feat["properties"]["feature_id"]] = {
        "distance_m": sum(dist(a, b) for a, b in zip(coords, coords[1:], strict=False)),
        "max_walkback_from_science_origin_m": max(dist(origin, p) for p in coords),
        "exact_segment_polygon_hits": hits,
    }
out["unavailable_layers"] = sorted(
    k
    for k, v in grid["external_layers_status"].items()
    if v.get("tag") == "UNAVAILABLE" or v.get("available") is False
)
out["sol700_waypoint"] = [f["properties"] for f in wp["features"] if f["properties"]["sol"] == 700]
out["gcr_constraint"] = read("eva_constraints.json")["gcr_dose_msv_per_day"]
out["svg_sha256"] = hashlib.sha256(
    (ROOT / "docs/assets/jezero_eva_survival_map.svg").read_bytes()
).hexdigest()
text = json.dumps(out, indent=2)
(Path(__file__).parent / "independent-numbers.json").write_text(text, encoding="utf-8")
print(text)
