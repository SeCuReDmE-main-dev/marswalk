"""Block B1 Tests: 10-Carrier Vector, Multi-Scale Fractal Pruning Funnel, and Section 5 Attacks."""

from __future__ import annotations

import hashlib
import inspect
import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from marswalk.engine import carriers, funnel
from marswalk.engine.carriers import REQUIRED_CARRIERS, build_cell_carrier_triplets
from marswalk.engine.funnel import CarrierScaleTriplet, FunnelParams, run_cell_funnel


def test_p1_rejected() -> None:
    """Section 5 Attack: p = 1 erases cliffs as single-scale spikes -> must raise ValueError."""
    with pytest.raises(ValueError, match="p"):
        FunnelParams(p=1, tau_max=0.25, h_min=0.5, eps=0.01)


def test_tau_max_1_rejected() -> None:
    """Section 5 Attack: tau_max = 1.0 prunes everything (I*=0) -> must raise ValueError."""
    with pytest.raises(ValueError, match="tau_max"):
        FunnelParams(p=2, tau_max=1.0, h_min=0.5, eps=0.01)
    with pytest.raises(ValueError, match="tau_max"):
        FunnelParams(p=2, tau_max=0.0, h_min=0.5, eps=0.01)


def test_h_min_zero_rejected_and_eps_zero_rejected() -> None:
    """Section 5 Attacks: H_min <= 0 or eps < 1e-4 must raise ValueError."""
    with pytest.raises(ValueError, match="h_min"):
        FunnelParams(p=2, tau_max=0.25, h_min=0.0, eps=0.01)
    with pytest.raises(ValueError, match="eps"):
        FunnelParams(p=2, tau_max=0.25, h_min=0.5, eps=0.0)


def test_missing_carrier_rejected_and_zero_rover_tilt_access() -> None:
    """Claim A & Section 5 Attack: missing carrier rejected; rover_tilt never read."""
    assert len(REQUIRED_CARRIERS) == 10
    with pytest.raises(ValueError, match="carrier"):
        carriers.validate_carrier_names(("I_source", "I_slope"))

    for mod in (carriers, funnel):
        src = inspect.getsource(mod)
        assert "rover_tilt" not in src


@settings(max_examples=60, deadline=None, database=None)
@given(
    t_vals=st.lists(
        st.floats(min_value=0.05, max_value=0.95, allow_nan=False, allow_infinity=False),
        min_size=30,
        max_size=30,
    )
)
def test_funnel_terminates(t_vals: list[float]) -> None:
    """Benchmark B1: Guaranteed termination in <= len(E) // 2 iterations everywhere."""
    scales = (64, 16, 4)
    triplets: list[CarrierScaleTriplet] = []
    idx = 0
    for cname in REQUIRED_CARRIERS:
        for sc in scales:
            tv = t_vals[idx]
            fv = round(1.0 - tv, 4)
            iv = 0.08
            triplets.append(CarrierScaleTriplet(carrier=cname, scale_m=sc, t=tv, i=iv, f=fv))
            idx += 1

    params = FunnelParams(p=2, tau_max=0.35, h_min=0.30, eps=0.005)
    out = run_cell_funnel(triplets, params=params, slopes_by_scale={4: 6.0, 16: 5.5, 64: 5.0})
    assert out.iterations <= len(triplets) // 2
    assert out.i_star > 0.0


def test_persistent_hazard_never_pruned() -> None:
    """Benchmark B3: 100% of hazards across >= p neighboring scales remain NO_GO/CAUTION."""
    params = FunnelParams(p=2, tau_max=0.35, h_min=0.30, eps=0.005)
    survived = 0
    total = 50
    for trial in range(total):
        base_slope = 2.0 + (trial % 5) * 0.5
        triplets = build_cell_carrier_triplets(
            slopes_by_scale={4: base_slope, 16: base_slope, 64: base_slope},
            roughness_rms_m=0.01 + (trial % 4) * 0.005,
            fractal_d=2.18 + (trial % 5) * 0.03,
            curvature_m_inv=0.02,
            walkback_m=300.0 + trial * 10.0,
            nodata_fraction=0.0,
            source_id="SRC-USGS-HIRISE-DTM-1M",
            dtm_resolution_m=1.0,
        )
        # Inject persistent high F >= 0.82 on 2 neighboring scales (16m and 4m) of I_slope
        injected: list[CarrierScaleTriplet] = []
        for tr in triplets:
            if tr.carrier == "I_slope" and tr.scale_m in (16, 4):
                injected.append(
                    CarrierScaleTriplet(
                        carrier=tr.carrier,
                        scale_m=tr.scale_m,
                        t=0.12,
                        i=tr.i,
                        f=0.88,
                    )
                )
            else:
                injected.append(tr)

        res = run_cell_funnel(
            injected,
            params=params,
            slopes_by_scale={4: 22.0, 16: 21.0, 64: base_slope},
        )
        if res.verdict in ("NO_GO", "CAUTION") and res.persistent_hazard_detected:
            survived += 1

    assert survived == total, f"B3 FAIL: {total - survived} persistent hazards were erased!"


def test_single_scale_spike_pruned() -> None:
    """Benchmark B4: >= 95% of isolated spikes injected on a single scale are pruned."""
    params = FunnelParams(p=2, tau_max=0.30, h_min=0.30, eps=0.005)
    pruned_count = 0
    total = 60
    target_scales = (64, 16, 4)

    for trial in range(total):
        spike_scale = target_scales[trial % 3]
        triplets = build_cell_carrier_triplets(
            slopes_by_scale={4: 3.2, 16: 2.9, 64: 2.5},
            roughness_rms_m=0.015,
            fractal_d=2.22,
            curvature_m_inv=0.03,
            walkback_m=450.0 + (trial % 10) * 50.0,
            nodata_fraction=0.01,
            source_id="SRC-USGS-HIRISE-DTM-1M",
            dtm_resolution_m=1.0,
        )
        injected: list[CarrierScaleTriplet] = []
        for tr in triplets:
            if tr.carrier == "I_texture" and tr.scale_m == spike_scale:
                injected.append(
                    CarrierScaleTriplet(
                        carrier="I_texture",
                        scale_m=spike_scale,
                        t=0.04,
                        i=tr.i,
                        f=0.96,
                    )
                )
            else:
                injected.append(tr)

        res = run_cell_funnel(injected, params=params, slopes_by_scale={4: 3.2, 16: 2.9, 64: 2.5})
        was_pruned = any(
            step["carrier"] == "I_texture" and step["scale_m"] == spike_scale for step in res.trace
        )
        if was_pruned and not res.persistent_hazard_detected:
            pruned_count += 1

    rate = pruned_count / float(total)
    assert rate >= 0.95, f"B4 FAIL: single-scale spike prune rate {rate:.2%} < 95%"


def test_entropy_floor() -> None:
    """Benchmark B9: 0% of cells collapse to I* == 0 across varied terrain profiles."""
    params = FunnelParams(p=2, tau_max=0.25, h_min=0.50, eps=0.01)
    for idx in range(50):
        s_base = float(idx % 24)
        triplets = build_cell_carrier_triplets(
            slopes_by_scale={4: s_base + 1.2, 16: s_base + 0.4, 64: max(0.2, s_base - 0.8)},
            roughness_rms_m=0.005 * (idx % 12),
            fractal_d=2.05 + 0.015 * (idx % 40),
            curvature_m_inv=0.01 * (idx % 15),
            walkback_m=float((idx * 37) % 1950),
            nodata_fraction=0.0,
            source_id="SRC-USGS-HIRISE-DTM-1M",
            dtm_resolution_m=1.0,
        )
        res = run_cell_funnel(
            triplets,
            params=params,
            slopes_by_scale={4: s_base + 1.2, 16: s_base + 0.4, 64: max(0.2, s_base - 0.8)},
        )
        assert res.i_star > 0.0, f"B9 FAIL: I* collapsed to 0 on cell {idx}"


def test_deterministic() -> None:
    """Benchmark B2: 3 consecutive runs produce byte-identical SHA-256 digests."""
    params = FunnelParams(p=2, tau_max=0.25, h_min=0.50, eps=0.01)
    hashes: list[str] = []
    for _ in range(3):
        records = []
        for idx in range(25):
            slopes = {4: 4.5 + idx * 0.6, 16: 3.9 + idx * 0.5, 64: 3.1 + idx * 0.4}
            triplets = build_cell_carrier_triplets(
                slopes_by_scale=slopes,
                roughness_rms_m=0.02,
                fractal_d=2.28,
                curvature_m_inv=0.04,
                walkback_m=600.0,
                nodata_fraction=0.0,
                source_id="SRC-USGS-HIRISE-DTM-1M",
                dtm_resolution_m=1.0,
            )
            res = run_cell_funnel(triplets, params=params, slopes_by_scale=slopes)
            records.append(res.to_dict())
        raw = json.dumps(records, sort_keys=True).encode("utf-8")
        hashes.append(hashlib.sha256(raw).hexdigest())

    assert hashes[0] == hashes[1] == hashes[2]
