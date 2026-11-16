"""Independent Part 3 audit arithmetic and adversarial probes; no raw downloads."""

from __future__ import annotations

import dataclasses
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from pydantic import ValidationError

from marswalk.engine import eva_human_rf as rf
from marswalk.engine import kinematics_m4 as kin
from marswalk.engine import m20_raw_images_m5 as camera
from marswalk.engine import meda_envelope as meda
from marswalk.engine import radiation_svf as rad
from marswalk.engine import topographic_refuge_m3 as refuge
from marswalk.middleware.pack_loader import load_and_verify_pack
from marswalk.middleware.query_service import PackQueryService, PlanRouteRequest

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


def reject_network(event: str, args: tuple) -> None:
    if event.startswith("socket.") and event in {"socket.connect", "socket.getaddrinfo"}:
        raise PermissionError("Part 3 physics probe forbids every network connection")


sys.addaudithook(reject_network)


def close(actual: float, expected: float, tolerance: float = 1e-6) -> None:
    assert math.isclose(actual, expected, abs_tol=tolerance, rel_tol=0.0), (actual, expected)


def independent_mr(grade: float, payload: float = 0.0) -> float:
    # Independent interpolation of the implementation's stated anchors, not source validation.
    vo2 = float(np.interp(grade, [0, 0.1, 0.15, 0.2, 0.3], [16, 18.3, 20.8, 23.8, 31.8]))
    return vo2 * 70 / 1000 * 20100 / 60 * (1 + payload / 191 * (1 + 2 * grade))


def independent_oxygen(grade: float, payload: float, distance: float) -> dict:
    nominal = independent_mr(0.02, payload)
    returning = max(2505000 / 3600, independent_mr(grade, payload))
    ingress = independent_mr(0)
    speed = 2.4 * math.exp(-3.5 * abs(grade + 0.05))
    hours = distance / (1000 * speed)
    grams_per_wh = 3600 * 1.429 / 20100
    used = grams_per_wh * (nominal * 3 + returning * hours + ingress * 0.5)
    margin = (754 - used) / (returning * grams_per_wh / 60)
    close(rf.walkback_o2_margin_min(distance, grade, payload), margin)
    return {"nominal_w": nominal, "walkback_w": returning, "used_g": used, "margin_min": margin}


def main() -> None:
    results: dict = {
        "commit": "e38ceba70e9c6273cf35233d3255cd912a7a4809",
        "identity": "Codex independent audit context; same machine and existing dependency venv",
        "network": "Every outbound connection denied; no raw data downloaded",
    }
    modules = [rf, kin, camera, meda, rad, refuge]
    for module in modules:
        assert Path(module.__file__).resolve().is_relative_to(ROOT)
    results["source_imports"] = [Path(m.__file__).relative_to(ROOT).as_posix() for m in modules]
    results["datalake_files"] = sorted(
        p.relative_to(ROOT).as_posix() for p in (ROOT / "datalake").rglob("*") if p.is_file()
    )

    theta = math.degrees(math.atan(-0.1))
    grade20 = math.tan(math.radians(20))
    close(kin.grade_frac_to_slope_deg(-0.1), theta)
    close(kin.slope_deg_to_grade_frac(20), grade20)
    poly = (
        280.5 * (-0.1) ** 5
        - 58.7 * (-0.1) ** 4
        - 76.8 * (-0.1) ** 3
        + 51.9 * (-0.1) ** 2
        + 19.6 * (-0.1)
        + 2.5
    )
    close(kin.minetti_2002_quintic_poly_j_per_kg_m(-0.1), poly)
    results["grade_and_minetti"] = {
        "minus10percent_angle_deg": theta,
        "20deg_grade_fraction": grade20,
        "quintic_minus10percent": poly,
    }
    # Original Minetti 2002 Table 2, printed p.1042; exact means only, no figure digitization.
    published = {
        -0.45: 3.46,
        -0.4: 3.23,
        -0.35: 2.65,
        -0.3: 2.18,
        -0.2: 1.30,
        -0.1: 0.81,
        0: 1.64,
        0.1: 4.68,
        0.2: 8.07,
        0.3: 11.29,
        0.35: 12.72,
        0.4: 14.75,
        0.45: 17.33,
    }
    results["minetti_published_comparison"] = [
        {
            "grade": g,
            "published_table2": v,
            "implementation": kin.minetti_2002_table_j_per_kg_m(g),
            "delta": round(kin.minetti_2002_table_j_per_kg_m(g) - v, 6),
        }
        for g, v in published.items()
    ]

    w, load, speed, gravity = 75, 104, 0.625, 0.3794
    standing = 1.5 * w
    carrying = 2 * (w + load) * (load / w) ** 2
    locomotion = (w + load) * 1.5 * speed**2
    comparison = kin.compare_suited_metabolic_models(
        body_mass_kg=w, suit_mass_kg=load, speed_m_s=speed
    )
    close(
        comparison.pandolf_csrm_all_g_scaled_w,
        round(gravity * (standing + carrying + locomotion), 2),
    )
    close(
        comparison.pandolf_carr_newman_unscaled_postural_w,
        round(standing + gravity * (carrying + locomotion), 2),
    )
    results["pandolf_reference"] = dataclasses.asdict(comparison)
    results["measured_tag_attack"] = dataclasses.asdict(
        kin.compare_suited_metabolic_models(
            grade_frac=0.7, body_mass_kg=80, suit_mass_kg=104, payload_kg=60, speed_m_s=1.2
        )
    )
    results["oxygen_payloads"] = {str(p): independent_oxygen(0, p, 1000) for p in (0, 60, 120)}
    results["oxygen_floor_isolated_no_nominal"] = {
        str(p): rf.walkback_o2_margin_min(1000, payload_kg=p, nominal_eva_elapsed_h=0)
        for p in (0, 60, 120)
    }
    close(
        results["oxygen_floor_isolated_no_nominal"]["0"],
        results["oxygen_floor_isolated_no_nominal"]["60"],
    )
    results["tobler_level_kmh"] = rf.tobler_xeva_kmh(0)
    results["return_2000m_h"] = rf.walkback_return_h(2000)

    # Independent midpoint quadrature of wall's solid angle horizon integral.
    h, d, half_w = 10, 2, 10
    az = np.linspace(-math.atan(half_w / d), math.atan(half_w / d), 1000001)
    horizon_tan = h * np.cos(az) / d
    integral = float(np.trapezoid(horizon_tan / np.sqrt(1 + horizon_tan**2), az) / (2 * math.pi))
    close(refuge.analytical_finite_wall_sky_occlusion(h, d, 2 * half_w), integral)
    close(refuge.analytical_finite_wall_sky_occlusion(h, d, None), math.atan(h / d) / math.pi)
    results["svf_wall"] = {
        "finite_quadrature": integral,
        "finite_function": refuge.analytical_finite_wall_sky_occlusion(h, d, 2 * half_w),
        "infinite": refuge.analytical_finite_wall_sky_occlusion(h, d, None),
    }
    results["gcr_at_035_occlusion"] = dataclasses.asdict(
        refuge.compute_partial_topographic_refuge(0.35)
    )
    close(rad.ehresmann_dose_factor(0.65), 0.93)
    results["gcr_baselines"] = {
        "code_msv_day": rad.OPEN_SKY_GCR_DOSE_MSV_PER_DAY,
        "code_mgy_day": rad.OPEN_SKY_GCR_DOSE_MGY_PER_DAY,
        "Hassler_2014_msv_day": 0.64,
        "source_usv_h": 1000 * 0.64 / 24,
        "code_usv_h": 1000 * rad.OPEN_SKY_GCR_DOSE_MSV_PER_DAY / 24,
    }

    wavelength = 299792458 / 414200000
    radius = math.sqrt(wavelength * 500 * 500 / 1000)
    bulge = 500 * 500 / (2 * 3396190)
    v = -0.6 * math.sqrt(2)
    terrain = (3 + 1.8) / 2 - 0.6 * radius - bulge
    assessment = rf.evaluate_route_rf_fresnel_bullington([0, terrain, 0], 1000)
    close(rf.UHF_WAVELENGTH_M, wavelength)
    close(rf.first_fresnel_radius_m(500, 500), radius)
    close(assessment.nu_max, v)
    assert assessment.diffraction_loss_db == 0
    results["fresnel"] = {
        "wavelength_m": wavelength,
        "midpoint_f1_m": radius,
        "bulge_m": bulge,
        "assessment": dataclasses.asdict(assessment),
    }
    # LoS profile: the code gives J(v), while ITU 526 section 4.5.1 eq57 adds taper correction.
    flat = rf.evaluate_route_rf_fresnel_bullington([0, 0, 0], 1000)
    corrected = flat.diffraction_loss_db + (1 - math.exp(-flat.diffraction_loss_db / 6)) * (
        10 + 0.02 * 1
    )
    results["bullington_omitted_eq57"] = {
        "code": dataclasses.asdict(flat),
        "itu_section451_loss_db_from_unrounded_v": rf.fresnel_j_db(
            rf.bullington_nu_max_profile([0, 0, 0], 1000)
        )
        + (1 - math.exp(-rf.fresnel_j_db(rf.bullington_nu_max_profile([0, 0, 0], 1000)) / 6))
        * 10.02,
        "itu_rounded_loss_db": corrected,
        "itu_verdict_at_6db": "NO_GO" if corrected > 6 else "GO",
    }
    dtm = np.zeros((3, 1001))
    dtm[:, 501:505] = 20  # 4m-wide formation, detectable at 1m resolution.
    sampled = rf.sample_dtm_los_profile(dtm, 1, 0, 1, 1000, 1000, step_m=8)
    results["rf_sampling_alias"] = {
        "sample_count": len(sampled),
        "sampled_peak_m": max(sampled),
        "true_peak_m": float(dtm.max()),
        "sampled_verdict": rf.evaluate_route_rf_fresnel_bullington(sampled, 1000).verdict,
        "dense_verdict": rf.evaluate_route_rf_fresnel_bullington(dtm[1].tolist(), 1000).verdict,
    }
    # Narrower shifted ridge entirely between 8m samples (496, 504).
    dtm[:, :] = 0
    dtm[:, 499:503] = 20
    sampled = rf.sample_dtm_los_profile(dtm, 1, 0, 1, 1000, 1000, step_m=8)
    results["rf_sampling_alias_4m_between_samples"] = {
        "sampled_peak_m": max(sampled),
        "true_peak_m": float(dtm.max()),
        "sampled": dataclasses.asdict(rf.evaluate_route_rf_fresnel_bullington(sampled, 1000)),
        "dense": dataclasses.asdict(rf.evaluate_route_rf_fresnel_bullington(dtm[1].tolist(), 1000)),
    }

    results["invalid_helpers"] = {
        "dust_nan": meda.evaluate_dust_tau_verdict(float("nan")),
        "dust_negative": meda.evaluate_dust_tau_verdict(-1),
        "rf_all_nan": dataclasses.asdict(
            rf.evaluate_route_rf_fresnel_bullington([float("nan")] * 3, 1000)
        ),
        "svf_all_nan": rad.compute_sky_view_factor_32az(np.full((100, 100), np.nan), 50, 50),
    }
    results["meda_boundaries"] = {
        str(t): meda.evaluate_dust_tau_verdict(t) for t in (0, 0.5, 0.500001, 1, 1.000001)
    }
    results["meda_filters"] = {
        "WS35": dataclasses.asdict(meda.filter_meda_samples("WS", 35, [2])),
        "WS36": dataclasses.asdict(meda.filter_meda_samples("WS", 36, [2])),
        "RHS62": dataclasses.asdict(meda.filter_meda_samples("RHS", 62, [0.5])),
        "RHS63": dataclasses.asdict(meda.filter_meda_samples("RHS", 63, [0.5])),
        "PS_sentinels": dataclasses.asdict(
            meda.filter_meda_samples("PS", 1, [700, 9999999999, float("nan"), float("inf")])
        ),
    }
    fake_cache = OUT / "malformed_meda_cache"
    fake_cache.mkdir(exist_ok=True)
    (fake_cache / "MEDA_env_summary.csv").write_text("", encoding="utf-8")
    results["meda_empty_file"] = meda.load_cached_meda_summary(fake_cache)
    (fake_cache / "MEDA_env_summary.csv").unlink()
    fake_cache.rmdir()
    results["meda_no_file"] = meda.load_cached_meda_summary(OUT / "nonexistent_cache")
    no_cache = OUT / "camera_offline_probe"
    offline = camera.fetch_or_load_m20_sol_cameras(no_cache, 700, allow_network=False)
    results["camera_offline"] = {
        "result": dataclasses.asdict(offline),
        "created_directory": no_cache.exists(),
    }
    pack = load_and_verify_pack(ROOT, "jezero")
    results["pack_summary"] = {
        "rf_counts": dict(Counter(c.rf_comms_verdict for c in pack.hazards.cells)),
        "cells": len(pack.hazards.cells),
        "partial_refuges": sum(c.partial_topographic_refuge is True for c in pack.hazards.cells),
        "meda": pack.hazards.external_layers_status["meda_pds4_env"],
    }
    waypoints = json.loads(
        (ROOT / "public_packs/jezero/v1/waypoints.geojson").read_text(encoding="utf-8")
    )
    urls = [f["properties"].get("panorama_url", "") or "" for f in waypoints["features"]]
    results["panorama_urls"] = {
        "count": len(urls),
        "nonempty": sum(bool(u) for u in urls),
        "mmgis": sum("mmgis-maps" in u for u in urls),
    }
    service = PackQueryService(pack)
    points = [[77.4070, 18.4520], [77.4048, 18.4535]]
    spe = service.plan_route(PlanRouteRequest(waypoints=points, spe_alert=True))
    results["spe_service"] = {"verdict": spe.verdict, "reasons": spe.reasons}
    results["request_invalid_dust"] = {}
    for name, value in [("nan", float("nan")), ("inf", float("inf")), ("negative", -1)]:
        try:
            PlanRouteRequest(waypoints=points, dust_tau_880nm=value)
            outcome = "accepted"
        except ValidationError:
            outcome = "rejected"
        results["request_invalid_dust"][name] = outcome
    serialized = json.dumps(results, indent=2, allow_nan=False)
    (OUT / "physics-probe.json").write_text(serialized + "\n", encoding="utf-8")
    (OUT / "physics-probe.log").write_text(serialized + "\nEXIT_CODE=0\n", encoding="utf-8")
    print(serialized)
    print("EXIT_CODE=0")


if __name__ == "__main__":
    main()
