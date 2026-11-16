"""Part 1 independent arithmetic and synthetic counterexamples; no raw data download."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

from marswalk.engine import calibration_aoa as aoa  # noqa: E402
from marswalk.engine import crism_ingest as crism  # noqa: E402
from marswalk.engine import dtm_ingest as dtm  # noqa: E402
from marswalk.engine import obstacles_m1 as m1  # noqa: E402
from marswalk.engine import sim3464_ingest as geology  # noqa: E402
from marswalk.engine import themis_ingest as themis  # noqa: E402

EVIDENCE = ROOT / "shared/10_HANDOFFS/audit_evidence/part01"
PACK = ROOT / "public_packs/jezero/v1"
RADIUS_M = 3396190.0  # Independently specified by the requested contract.


def read_json(filename: str) -> dict:
    return json.loads((PACK / filename).read_text(encoding="utf-8"))


def relative_module(module: object) -> str:
    source = Path(module.__file__).resolve()
    assert source.is_relative_to(ROOT), "Import escaped the audit checkout"
    return source.relative_to(ROOT).as_posix()


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def main() -> None:
    output: dict = {"source_imports": {}}
    for module in (aoa, crism, dtm, m1, geology, themis):
        output["source_imports"][module.__name__] = relative_module(module)
    hazard = read_json("hazard_grid.json")
    validation = read_json("validation_report.json")
    waypoint_features = read_json("waypoints.geojson")["features"]
    obstacles = read_json("obstacles.geojson")["features"]
    waypoints = {w["properties"]["waypoint_id"]: w["properties"] for w in waypoint_features}
    min_lon, min_lat, max_lon, max_lat = hazard["bbox"]
    center_lat = (min_lat + max_lat) / 2
    cos_lat = math.cos(math.radians(center_lat))
    window_width = RADIUS_M * math.radians(max_lon - min_lon) * cos_lat
    window_height = RADIUS_M * math.radians(max_lat - min_lat)
    pack_results: dict = {
        "total_waypoints": len(waypoints),
        "validation_samples": len(validation["samples"]),
        "bbox": hazard["bbox"],
        "center_lat_deg": center_lat,
        "ground_EW_m_per_projected_m": cos_lat,
        "EW_overstatement_if_cos_omitted_pct": (1 / cos_lat - 1) * 100,
        "window_ground_width_m": window_width,
        "window_ground_height_m": window_height,
        "planner_expected_step_x_m": window_width / 190,
        "planner_expected_step_y_m": window_height / 200,
        "radius_manifest_m": read_json("manifest.json")["crs"]["sphere_radius_m"],
        "obstacle_count": len(obstacles),
        "obstacle_types": sorted({o["properties"]["obstacle_type"] for o in obstacles}),
        "minimum_obstacle_footprint_area_m2": min(
            o["properties"]["footprint_area_m2"] for o in obstacles
        ),
        "minimum_obstacle_relief_m": min(o["properties"]["internal_relief_m"] for o in obstacles),
        "maximum_obstacle_relief_m": max(o["properties"]["internal_relief_m"] for o in obstacles),
        "clearance_values_m": sorted({o["properties"]["physical_clearance_m"] for o in obstacles}),
        "physical_corridor_diameter_m": 2 * (0.40 + 0.45),
        "external_layers": hazard["external_layers_status"],
    }
    mismatched_ids = []
    max_tilt_rounding = 0.0
    max_coords_error = 0.0
    for sample in validation["samples"]:
        wp = waypoints.get(sample["waypoint_id"])
        if wp is None:
            mismatched_ids.append(sample["waypoint_id"])
            continue
        max_tilt_rounding = max(
            max_tilt_rounding,
            abs(sample["measured_rover_tilt_deg"] - wp["rover_tilt_deg"]["value"]),
        )
        max_coords_error = max(
            max_coords_error, abs(sample["lon"] - wp["lon"]), abs(sample["lat"] - wp["lat"])
        )
    pack_results["unmatched_validation_waypoint_ids"] = mismatched_ids
    pack_results["max_report_vs_waypoint_tilt_rounding_deg"] = max_tilt_rounding
    pack_results["max_report_vs_waypoint_coordinate_error_deg"] = max_coords_error
    pack_results["metrics_from_report_stored_slopes_minus_pack_tilt"] = {}
    for subset_name, subset in (
        ("all", validation["samples"]),
        ("odd", [s for s in validation["samples"] if s["sol"] % 2]),
        ("even", [s for s in validation["samples"] if not s["sol"] % 2]),
    ):
        metrics = {}
        for baseline in ("1", "4", "16", "64"):
            errors = [
                s["dtm_slope_deg_by_baseline"][baseline]
                - waypoints[s["waypoint_id"]]["rover_tilt_deg"]["value"]
                for s in subset
            ]
            steep_errors = [
                s["dtm_slope_deg_by_baseline"][baseline]
                - waypoints[s["waypoint_id"]]["rover_tilt_deg"]["value"]
                for s in subset
                if waypoints[s["waypoint_id"]]["rover_tilt_deg"]["value"] >= 8
            ]
            metrics[baseline] = {
                "n": len(errors),
                "mae_deg": mean([abs(e) for e in errors]),
                "rmse_deg": math.sqrt(mean([e * e for e in errors])),
                "bias_deg": mean(errors),
                "n_steep": len(steep_errors),
                "steep_mae_deg": mean([abs(e) for e in steep_errors]),
                "steep_bias_deg": mean(steep_errors),
            }
        pack_results["metrics_from_report_stored_slopes_minus_pack_tilt"][subset_name] = metrics
    output["independent_pack_arithmetic"] = pack_results

    # Exact plane cross-check with independent analytic angle and row-axis convention.
    yy, xx = np.mgrid[:161, :161]
    sx = math.cos(math.radians(18.46))
    plane = 0.3 * xx * sx - 0.4 * yy
    gx, gy, slp = m1.compute_4m_slope_deg_array(plane, sx)
    output["analytic_plane"] = {
        "expected_slope_deg": math.degrees(math.atan(0.5)),
        "actual_slope_deg": float(slp[80, 80]),
        "actual_gx": float(gx[80, 80]),
        "actual_gy": float(gy[80, 80]),
    }

    # A diagonal sample contributes to Horn's weighted kernel, but not central differences.
    impulse = np.zeros((9, 9))
    impulse[2, 6] = 4.0
    _, _, impulse_slp = m1.compute_4m_slope_deg_array(impulse, sx)
    horn_gx = 4.0 / (8 * 2 * sx)
    horn_gy = 4.0 / (8 * 2)
    output["not_horn_counterexample"] = {
        "input": "9x9 zero elevation; z[row=2,col=6]=4m; evaluate row=4,col=4",
        "central_difference_slope_deg": float(impulse_slp[4, 4]),
        "horn_3x3_2m_sample_spacing_slope_deg": math.degrees(
            math.atan(math.hypot(horn_gx, horn_gy))
        ),
    }

    # A 2m high step produces a continuous >20deg scarp straddling a 10m cell seam.
    step_z = np.zeros((100, 100))
    step_z[:, 50:] = 2.0
    lon0, lat0 = 77.4, 18.46
    x0 = RADIUS_M * math.radians(lon0)
    y1 = RADIUS_M * math.radians(lat0)
    small_bbox = (
        lon0,
        math.degrees((y1 - 100) / RADIUS_M),
        math.degrees((x0 + 100) / RADIUS_M),
        lat0,
    )
    raw_obstacle, step_slopes, _, _ = m1.extract_formations_and_scarps_1m(step_z, 18.46)
    grid, poly = m1.build_planner_grid_10m_from_window(step_z, x0, y1, small_bbox, rows=10, cols=10)
    output["seam_scarp_erasure"] = {
        "input": "100x100 1m raster, z=0 at col<50 else z=2m; 10x10 planner cells",
        "detected_obstacle_pixels_1m": int(raw_obstacle.sum()),
        "slope_4m_deg_max": float(step_slopes.max()),
        "detected_obstacle_fraction_in_each_adjacent_cell": [
            float(raw_obstacle[:10, 40:50].mean()),
            float(raw_obstacle[:10, 50:60].mean()),
        ],
        "blocked_planner_cells": int(grid.blocked_mask.sum()),
        "caution_planner_cells": int(grid.caution_mask.sum()),
        "exported_obstacle_polygons": len(poly["features"]),
    }

    # Clearance pixels are existentially clear: a valid endpoint does not clear the centre.
    one_obstacle = np.zeros((9, 9), dtype=bool)
    one_obstacle[4, 4] = True
    buffered = m1.apply_physical_clearance_buffer_1m(one_obstacle, 1.0)
    output["physical_clearance_raster"] = {
        "input": "one solid obstacle pixel at row=4,col=4; 1m square pixels",
        "blocked_pixels_after_buffer": int(buffered.sum()),
        "adjacent_pixel_4_5_blocked": bool(buffered[4, 5]),
        "adjacent_pixel_center_distance_to_solid_m": 0.5,
        "required_clearance_m": 0.85,
    }
    corridor_outputs = {}
    for width in (1, 2):
        walls = np.zeros((9, 9), dtype=bool)
        walls[:, :3] = True
        walls[:, 3 + width :] = True
        corridor = m1.apply_physical_clearance_buffer_1m(walls, sx)
        corridor_outputs[f"{width}_pixel_gap"] = {
            "actual_ground_width_m": width * sx,
            "open_interior_pixels": int((~corridor[2:7, 3 : 3 + width]).sum()),
        }
    output["physical_corridors"] = corridor_outputs

    # Synthetic GeoTIFFs remain in an ephemeral subfolder of my evidence directory.
    with tempfile.TemporaryDirectory(prefix="synthetic_", dir=EVIDENCE) as tmp:
        scratch = Path(tmp)
        selected = dtm.SelectedDtmWindow(
            x0 + 64,
            x0 + 96,
            y1 - 96,
            y1 - 64,
            64,
            *[math.degrees(v / RADIUS_M) for v in (x0 + 64, y1 - 96, x0 + 96, y1 - 64)],
            waypoint_count=0,
        )
        for kind in ("nodata_hole", "ellipsoid", "two_metre_pixels"):
            case = scratch / kind
            case.mkdir()
            z = np.full((160, 160), -2500.0, dtype=np.float32)
            if kind == "nodata_hole":
                z[64:96, 64:96] = -9999
            if kind == "two_metre_pixels":
                z += np.arange(160, dtype=np.float32)[None, :]
            b_radius = 3376200 if kind == "ellipsoid" else RADIUS_M
            resolution = 2 if kind == "two_metre_pixels" else 1
            crs = rasterio.crs.CRS.from_proj4(
                f"+proj=eqc +lat_ts=0 +a={RADIUS_M} +b={b_radius} +units=m +no_defs"
            )
            with rasterio.open(
                case / dtm.CACHED_WINDOW_TIF_NAME,
                "w",
                driver="GTiff",
                width=160,
                height=160,
                count=1,
                dtype="float32",
                nodata=-9999,
                transform=from_origin(x0, y1, resolution, resolution),
                crs=crs,
            ) as dst:
                dst.write(z, 1)
            ingested = dtm._read_dtm_window_sync(case, selected)
            cell = dtm._compute_row_samples_sync(ingested, 0, 1, 1)[0]
            output[f"synthetic_ingest_{kind}"] = {
                "reported_sphere_radius_m": ingested.sphere_radius_m,
                "input_b_radius_m": b_radius,
                "input_pixel_spacing_m": resolution,
                "output_nodata_fraction": ingested.nodata_fraction,
                "output_cell_nodata_local": cell.nodata_local,
                "output_cell_elevation_m": cell.elev_m,
                "output_cell_slope_1m_deg": cell.slope_1m_deg,
                "output_cell_slope_4m_deg": cell.slope_4m_deg,
                "output_elevation_all_finite": bool(np.isfinite(ingested.elevation_m).all()),
                "analytic_input_slope_deg": (
                    math.degrees(math.atan(1 / (resolution * sx)))
                    if kind == "two_metre_pixels"
                    else 0
                ),
            }
        absent = scratch / "missing_layers"
        absent.mkdir()
        output["missing_themis"] = vars(themis.load_cached_themis_summary(absent))
        output["missing_crism"] = crism.load_cached_crism_summary(absent)
        (absent / "FRT000047A3_07_IF166J_MTR3.lbl").write_text(
            "CENTER_LATITUDE = 15.0\nA_AXIS_RADIUS = 3396.19 <km>\n", encoding="utf-8"
        )
        output["label_only_crism"] = crism.load_cached_crism_summary(absent)

    small_aoa = aoa.fit_spatial_aoa_model(np.empty((0, 4)), np.empty((0, 2)), np.empty((0,)))
    inside, opinion = aoa.evaluate_cell_aoa_and_opinion(small_aoa, (0, 0, 0, 0))
    output["empty_calibration"] = {
        "input_training_observations": 0,
        "output_cv_feasible": small_aoa.cv_feasible,
        "output_n_eff_blocks": small_aoa.n_eff_blocks,
        "inside_aoa": inside,
        "opinion": opinion.model_dump(),
    }
    for label, inputs in (
        ("oversampled", (1800, 200, 20)),
        ("outside", (18, 2, 0)),
    ):
        output[f"josang_{label}"] = aoa.josang_opinion(*inputs)
    output["geology_missing_defaults"] = {
        "empty": vars(geology.classify_sim3464_unit_context("")),
        "unrecognized": vars(geology.classify_sim3464_unit_context("UNKNOWN")),
    }
    thin = np.zeros((20, 20), dtype=bool)
    thin[10, 2:18] = True
    output["area_filter_does_not_enforce_width"] = {
        "input_shape_px": [1, 16],
        "retained_pixels": int(m1._filter_connected_components_min_area(thin, 16).sum()),
    }
    output["input_sha256"] = {
        name: hashlib.sha256((PACK / name).read_bytes()).hexdigest()
        for name in (
            "hazard_grid.json",
            "waypoints.geojson",
            "validation_report.json",
            "obstacles.geojson",
        )
    }
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
