"""Answers the two questions the map asks: "what is under my click?" and "can I walk this?".

- `lookup_cell(lon, lat)`: the nearest hazard cell AND the nearest real
  Perseverance stop, so the interface can show the orbital prediction next
  to what the rover actually measured on the ground.
- `evaluate_route(request)`: for 2 to 500 [lon, lat] points, the total
  distance, the farthest walk-back distance from the start (limit: 2 km), the worst
  slope at the 1 m and 64 m baselines, the largest scale divergence, the
  duration, a radiation estimate, a GO / CAUTION / NO_GO verdict and the
  human-readable reasons behind it.

Everything is read from an already verified pack, in memory. Nothing here
downloads data or changes the pack.
"""

from __future__ import annotations

import math
import re

from pydantic import ConfigDict, Field

from marswalk.contracts.models import (
    FrozenContractModel,
    HazardCell,
    Quantity,
    VerdictLiteral,
    Waypoint,
)
from marswalk.engine.eva_human_rf import (
    bullington_nu_max_profile,
    fresnel_j_db,
    metabolic_rate_w,
    rf_verdict,
    walkback_o2_margin_min,
    walkback_return_h,
)
from marswalk.engine.meda_envelope import evaluate_dust_tau_verdict
from marswalk.middleware.build_pack import spherical_distance_m
from marswalk.middleware.pack_loader import LoadedSitePack

_RETAINED_SLOPE_RE = re.compile(r"Retained\s+(?:4|16|64)m\s+slope\s+([0-9]+(?:\.[0-9]+)?)\s+deg")


def _cell_retained_slope_deg(cell: HazardCell) -> float:
    """Return the funnel-retained slope (deg) for a cell, strictly excluding 1m pixel noise."""
    match = _RETAINED_SLOPE_RE.search(cell.reason)
    if match:
        return float(match.group(1))
    return max(
        cell.slope_deg_by_baseline["4"].value,
        cell.slope_deg_by_baseline["16"].value,
        cell.slope_deg_by_baseline["64"].value,
    )


class CellLookupResult(FrozenContractModel):
    """Response payload for `GET /v1/sites/{site_id}/cell`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query_lon: float
    query_lat: float
    distance_to_cell_center_m: float
    cell: HazardCell
    nearest_waypoint: Waypoint
    distance_to_waypoint_m: float


class RouteEvaluationRequest(FrozenContractModel):
    """Request payload for `POST /v1/sites/{site_id}/evaluate-route`."""

    points: list[tuple[float, float]] = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Ordered list of [lon, lat] waypoints on the Mars sphere.",
    )
    walking_speed_km_h: float = Field(default=2.2, gt=0.1, le=15.0)
    spe_alert: bool = Field(
        default=False,
        description="Solar Particle Event (SPE) radiation emergency switch.",
    )
    dust_tau_880nm: float = Field(
        default=0.45,
        ge=0.0,
        le=10.0,
        description="MEDA 880 nm atmospheric dust optical depth (nominal clear season = 0.45).",
    )
    payload_kg: float = Field(
        default=0.0,
        ge=0.0,
        le=120.0,
        description="Additional carried sample / tool payload mass in kg.",
    )
    rf_link_margin_db: float = Field(
        default=6.0,
        ge=0.0,
        le=40.0,
        description="UHF 414.2 MHz link margin (dB) between suit (1.8 m) and rover mast (3.0 m).",
    )


class RouteEvaluationResult(FrozenContractModel):
    """Response payload for `POST /v1/sites/{site_id}/evaluate-route`."""

    site_id: str
    point_count: int
    total_distance_m: Quantity
    walkback_distance_m: Quantity
    walkback_within_limit: bool
    max_slope_1m_deg: Quantity
    max_slope_64m_deg: Quantity
    max_scale_divergence_deg: Quantity
    estimated_duration_h: Quantity
    estimated_radiation_msv: Quantity
    verdict: VerdictLiteral
    reasons: list[str]
    traversed_cell_ids: list[str]
    metabolic_rate_w: Quantity | None = Field(default=None)
    walkback_return_h: Quantity | None = Field(default=None)
    walkback_o2_margin_min: Quantity | None = Field(default=None)
    rf_diffraction_loss_db: Quantity | None = Field(default=None)
    rf_comms_verdict: VerdictLiteral | None = Field(default=None)


class PackQueryService:
    """Fast spatial lookup and route evaluator over a LoadedSitePack."""

    def __init__(self, pack: LoadedSitePack) -> None:
        self.pack = pack
        self._cell_coords = [(c.lon, c.lat, c) for c in pack.hazards.cells]
        self._cell_by_rc: dict[tuple[int, int], HazardCell] = {
            (c.row, c.col): c for c in pack.hazards.cells
        }
        self._wp_coords = [(w.properties.lon, w.properties.lat, w) for w in pack.waypoints.features]

    def _point_in_bbox(self, lon: float, lat: float, eps: float = 1e-6) -> bool:
        """Return True iff (lon, lat) lies within the site hazard grid bounding box."""
        min_lon, min_lat, max_lon, max_lat = self.pack.hazards.bbox
        return (min_lon - eps <= lon <= max_lon + eps) and (min_lat - eps <= lat <= max_lat + eps)

    def _lonlat_to_grid_uv_unclamped(self, lon: float, lat: float) -> tuple[float, float]:
        """Map (lon, lat) to unclamped continuous grid coordinates (u=col_f, v=row_f)."""
        min_lon, min_lat, max_lon, max_lat = self.pack.hazards.bbox
        cols = self.pack.hazards.cols
        rows = self.pack.hazards.rows
        u = (lon - min_lon) / max(1e-12, max_lon - min_lon) * float(cols)
        v = (max_lat - lat) / max(1e-12, max_lat - min_lat) * float(rows)
        return u, v

    def _lonlat_to_grid_uv(self, lon: float, lat: float) -> tuple[float, float]:
        """Map in-bbox (lon, lat) to continuous grid coordinates (u=col_f, v=row_f)."""
        cols = self.pack.hazards.cols
        rows = self.pack.hazards.rows
        u, v = self._lonlat_to_grid_uv_unclamped(lon, lat)
        u = max(0.0, min(float(cols) - 1e-9, u))
        v = max(0.0, min(float(rows) - 1e-9, v))
        return u, v

    def _sample_grid_los_profile(
        self,
        lon0: float,
        lat0: float,
        lon1: float,
        lat1: float,
        dist_m: float,
        step_m: float = 10.0,
    ) -> list[float]:
        """Sample bilinear grid elevations along straight line (lon0, lat0) -> (lon1, lat1)."""
        rows = self.pack.hazards.rows
        cols = self.pack.hazards.cols
        n_samples = max(3, int(math.ceil(max(10.0, dist_m) / max(1.0, step_m))) + 1)
        out: list[float] = []
        for k in range(n_samples):
            frac = k / float(n_samples - 1)
            lon_k = lon0 + frac * (lon1 - lon0)
            lat_k = lat0 + frac * (lat1 - lat0)
            u, v = self._lonlat_to_grid_uv(lon_k, lat_k)
            cf = max(0.0, min(float(cols - 1), u - 0.5))
            rf = max(0.0, min(float(rows - 1), v - 0.5))
            c0 = int(math.floor(cf))
            r0 = int(math.floor(rf))
            c1 = min(cols - 1, c0 + 1)
            r1 = min(rows - 1, r0 + 1)
            dc = cf - c0
            dr = rf - r0
            z00 = self._cell_by_rc[(r0, c0)].elev_m.value
            z01 = self._cell_by_rc[(r0, c1)].elev_m.value
            z10 = self._cell_by_rc[(r1, c0)].elev_m.value
            z11 = self._cell_by_rc[(r1, c1)].elev_m.value
            z_interp = (1.0 - dr) * ((1.0 - dc) * z00 + dc * z01) + dr * (
                (1.0 - dc) * z10 + dc * z11
            )
            out.append(float(z_interp))
        return out

    def _amanatides_woo_supercover(
        self,
        lon0: float,
        lat0: float,
        lon1: float,
        lat1: float,
    ) -> list[HazardCell]:
        """Return all HazardCells touched along segment (lon0, lat0) -> (lon1, lat1).

        Clips the segment to the grid bounding box via Liang-Barsky so mixed in/out-of-bbox
        segments still traverse their exact in-bbox cell path, then runs 2D Amanatides-Woo
        supercover grid traversal with explicit bounds checks and corner-touch inclusion.
        """
        rows = self.pack.hazards.rows
        cols = self.pack.hazards.cols
        u0_raw, v0_raw = self._lonlat_to_grid_uv_unclamped(lon0, lat0)
        u1_raw, v1_raw = self._lonlat_to_grid_uv_unclamped(lon1, lat1)

        du_raw = u1_raw - u0_raw
        dv_raw = v1_raw - v0_raw
        t0, t1 = 0.0, 1.0
        for p_clip, q_clip in (
            (-du_raw, u0_raw),
            (du_raw, float(cols) - u0_raw),
            (-dv_raw, v0_raw),
            (dv_raw, float(rows) - v0_raw),
        ):
            if abs(p_clip) <= 1e-12:
                if q_clip < 0.0:
                    return []
            else:
                r_clip = q_clip / p_clip
                if p_clip < 0.0:
                    if r_clip > t1:
                        return []
                    if r_clip > t0:
                        t0 = r_clip
                else:
                    if r_clip < t0:
                        return []
                    if r_clip < t1:
                        t1 = r_clip

        u0 = max(0.0, min(float(cols) - 1e-9, u0_raw + t0 * du_raw))
        v0 = max(0.0, min(float(rows) - 1e-9, v0_raw + t0 * dv_raw))
        u1 = max(0.0, min(float(cols) - 1e-9, u0_raw + t1 * du_raw))
        v1 = max(0.0, min(float(rows) - 1e-9, v0_raw + t1 * dv_raw))

        c = int(math.floor(u0))
        r = int(math.floor(v0))
        c_end = int(math.floor(u1))
        r_end = int(math.floor(v1))

        visited: list[HazardCell] = []

        def _push(rr: int, cc: int) -> None:
            if 0 <= rr < rows and 0 <= cc < cols:
                cell = self._cell_by_rc.get((rr, cc))
                if cell is not None and (not visited or visited[-1].cell_id != cell.cell_id):
                    visited.append(cell)

        _push(r, c)
        if r == r_end and c == c_end:
            return visited

        du = u1 - u0
        dv = v1 - v0
        step_c = 1 if du > 0.0 else (-1 if du < 0.0 else 0)
        step_r = 1 if dv > 0.0 else (-1 if dv < 0.0 else 0)

        t_delta_c = abs(1.0 / du) if abs(du) > 1e-12 else float("inf")
        t_delta_r = abs(1.0 / dv) if abs(dv) > 1e-12 else float("inf")

        if step_c > 0:
            t_max_c = (math.floor(u0) + 1.0 - u0) / du
        elif step_c < 0:
            t_max_c = (u0 - math.floor(u0)) / (-du)
            if t_max_c <= 0.0:
                t_max_c = t_delta_c
        else:
            t_max_c = float("inf")

        if step_r > 0:
            t_max_r = (math.floor(v0) + 1.0 - v0) / dv
        elif step_r < 0:
            t_max_r = (v0 - math.floor(v0)) / (-dv)
            if t_max_r <= 0.0:
                t_max_r = t_delta_r
        else:
            t_max_r = float("inf")

        max_steps = 2 * (rows + cols) + 4
        corner_eps = 1e-9
        for _ in range(max_steps):
            if r == r_end and c == c_end:
                break
            if abs(t_max_c - t_max_r) <= corner_eps:
                # Corner hit: supercover includes both orthogonal neighbor cells
                _push(r, c + step_c)
                _push(r + step_r, c)
                c += step_c
                r += step_r
                t_max_c += t_delta_c
                t_max_r += t_delta_r
                _push(r, c)
            elif t_max_c < t_max_r:
                c += step_c
                t_max_c += t_delta_c
                _push(r, c)
            else:
                r += step_r
                t_max_r += t_delta_r
                _push(r, c)

        _push(r_end, c_end)
        return visited

    def lookup_cell(self, lon: float, lat: float) -> CellLookupResult:
        """Return the nearest HazardCell and nearest Perseverance Waypoint to (lon, lat)."""
        _, _, best_cell = min(
            self._cell_coords,
            key=lambda item: (item[0] - lon) ** 2 + (item[1] - lat) ** 2,
        )
        dist_cell = round(spherical_distance_m(lon, lat, best_cell.lon, best_cell.lat), 2)

        _, _, best_wp = min(
            self._wp_coords,
            key=lambda item: (item[0] - lon) ** 2 + (item[1] - lat) ** 2,
        )
        dist_wp = round(
            spherical_distance_m(lon, lat, best_wp.properties.lon, best_wp.properties.lat), 2
        )

        return CellLookupResult(
            query_lon=lon,
            query_lat=lat,
            distance_to_cell_center_m=dist_cell,
            cell=best_cell,
            nearest_waypoint=best_wp,
            distance_to_waypoint_m=dist_wp,
        )

    def evaluate_route(self, req: RouteEvaluationRequest) -> RouteEvaluationResult:
        """Evaluate a candidate [lon, lat] polyline against multi-scale hazards & xEVA limits."""
        pts = req.points
        total_dist_m = 0.0
        max_walkback_m = 0.0
        origin_lon, origin_lat = pts[0]

        traversed_cells: list[HazardCell] = []
        seen_ids: set[str] = set()
        out_of_bbox_pts: list[tuple[float, float]] = []

        def _add_cell(cell: HazardCell) -> None:
            if cell.cell_id not in seen_ids:
                seen_ids.add(cell.cell_id)
                traversed_cells.append(cell)

        for idx, (lon, lat) in enumerate(pts):
            if not self._point_in_bbox(lon, lat):
                out_of_bbox_pts.append((lon, lat))
            if idx > 0:
                prev_lon, prev_lat = pts[idx - 1]
                total_dist_m += spherical_distance_m(prev_lon, prev_lat, lon, lat)
                seg_cells = self._amanatides_woo_supercover(prev_lon, prev_lat, lon, lat)
                if seg_cells:
                    for seg_cell in seg_cells:
                        _add_cell(seg_cell)
                else:
                    nearest = min(
                        self.pack.hazards.cells,
                        key=lambda c: (c.lon - lon) ** 2 + (c.lat - lat) ** 2,
                    )
                    _add_cell(nearest)
            else:
                seg_cells = self._amanatides_woo_supercover(lon, lat, lon, lat)
                if seg_cells:
                    for seg_cell in seg_cells:
                        _add_cell(seg_cell)
                else:
                    nearest = min(
                        self.pack.hazards.cells,
                        key=lambda c: (c.lon - lon) ** 2 + (c.lat - lat) ** 2,
                    )
                    _add_cell(nearest)

            wb = spherical_distance_m(origin_lon, origin_lat, lon, lat)
            if wb > max_walkback_m:
                max_walkback_m = wb

        total_dist_m = round(total_dist_m, 2)
        max_walkback_m = round(max_walkback_m, 2)
        walkback_limit_m = self.pack.constraints.walkback_max_km.value * 1000.0
        walkback_ok = max_walkback_m <= walkback_limit_m

        c_first = traversed_cells[0].slope_deg_by_baseline["4"]
        slope_tag = c_first.tag
        slope_src = c_first.source_id

        max_s1 = max(c.slope_deg_by_baseline["1"].value for c in traversed_cells)
        max_retained = max(_cell_retained_slope_deg(c) for c in traversed_cells)
        max_s64 = max(c.slope_deg_by_baseline["64"].value for c in traversed_cells)
        max_div = max(c.scale_divergence.value for c in traversed_cells)

        grade_est = math.tan(math.radians(max_retained))
        met_w = round(metabolic_rate_w(grade=grade_est, payload_kg=req.payload_kg), 1)
        wb_ret_h = round(walkback_return_h(distance_m=max_walkback_m, grade=grade_est), 3)
        wb_o2_min = round(
            walkback_o2_margin_min(
                distance_m=max_walkback_m,
                grade=grade_est,
                payload_kg=req.payload_kg,
            ),
            1,
        )
        nu_candidates: list[float] = []
        for lon_pt, lat_pt in pts[1:]:
            d_los_m = max(10.0, spherical_distance_m(origin_lon, origin_lat, lon_pt, lat_pt))
            los_profile = self._sample_grid_los_profile(
                origin_lon, origin_lat, lon_pt, lat_pt, dist_m=d_los_m, step_m=10.0
            )
            nu_candidates.append(bullington_nu_max_profile(los_profile, d_los_m))
        nu_max = max(nu_candidates) if nu_candidates else -0.78
        rf_loss_db = round(fresnel_j_db(nu_max), 2)
        rf_v = rf_verdict(nu_max=nu_max, link_margin_db=req.rf_link_margin_db)
        dust_v = evaluate_dust_tau_verdict(req.dust_tau_880nm)

        duration_h = round((total_dist_m / 1000.0) / req.walking_speed_km_h, 3)
        rad_msv = round(
            self.pack.constraints.gcr_dose_msv_per_day.value * (duration_h / 24.0),
            4,
        )
        if req.spe_alert:
            rad_msv = round(rad_msv + 150.0, 4)

        reasons: list[str] = []
        verdict: VerdictLiteral = "GO"

        if req.spe_alert:
            verdict = "NO_GO"
            reasons.append(
                "Solar Particle Event (SPE) alert active: immediate abort and return "
                "to rover/habitat shelter required."
            )
        if dust_v == "NO_GO":
            verdict = "NO_GO"
            reasons.append(
                f"Atmospheric dust optical depth (tau_880nm={req.dust_tau_880nm:.2f} > 1.00) "
                "exceeds MEDA EVA visibility and thermal safety threshold."
            )
        if out_of_bbox_pts:
            bad_lon, bad_lat = out_of_bbox_pts[0]
            verdict = "NO_GO"
            reasons.append(
                f"Route point ({bad_lon:.6f}, {bad_lat:.6f}) is out of bbox "
                f"{list(self.pack.hazards.bbox)}."
            )
        if not walkback_ok or wb_ret_h > 1.0:
            verdict = "NO_GO"
            reasons.append(
                f"Walkback distance ({max_walkback_m:.0f} m, return walk {wb_ret_h:.2f} h) "
                "exceeds NASA xEVA 2,000 m / 1.0 h contingency return limit."
            )
        if wb_o2_min < 0.0:
            verdict = "NO_GO"
            reasons.append(
                f"Primary O2 reserve exhausted ({wb_o2_min:.1f} min margin after walkback "
                "+ 30 min dust decontamination ingress)."
            )
        if rf_v == "NO_GO":
            verdict = "NO_GO"
            reasons.append(
                f"UHF 414.2 MHz diffraction loss ({rf_loss_db:.2f} dB) exceeds "
                f"link margin ({req.rf_link_margin_db:.1f} dB)."
            )
        if max_retained >= self.pack.constraints.suit_max_slope_deg.value:
            verdict = "NO_GO"
            reasons.append(
                f"Maximum retained funnel slope ({max_retained:.1f} deg) exceeds "
                f"NASA xEVA 20.0 deg suit limit."
            )
        nogo_cells = [c.cell_id for c in traversed_cells if c.verdict == "NO_GO"]
        if nogo_cells:
            verdict = "NO_GO"
            reasons.append(
                f"Route segment crosses {len(nogo_cells)} NO_GO hazard cell(s) "
                f"({', '.join(nogo_cells[:3])})."
            )
        if duration_h > self.pack.constraints.eva_duration_max_h.value:
            verdict = "NO_GO"
            reasons.append(
                f"Estimated EVA duration ({duration_h:.2f} h) exceeds 8.0 h xEVA ceiling."
            )

        if verdict != "NO_GO":
            if (
                dust_v == "CAUTION"
                or rf_v == "CAUTION"
                or met_w >= 550.0
                or max_retained >= self.pack.constraints.rover_max_slope_sand_deg.value
                or max_div >= 5.0
                or any(c.verdict == "CAUTION" for c in traversed_cells)
            ):
                verdict = "CAUTION"
                reasons.append(
                    f"Route crosses moderate retained slope ({max_retained:.1f} deg), "
                    f"scale divergence ({max_div:.1f} deg), or elevated dust/metabolic load "
                    f"(tau={req.dust_tau_880nm:.2f}, M={met_w:.0f} W)."
                )
            else:
                reasons.append(
                    "All traversed cells and walkback distance satisfy "
                    "NASA xEVA & JPL safety limits."
                )

        return RouteEvaluationResult(
            site_id=self.pack.site_id,
            point_count=len(pts),
            total_distance_m=Quantity(
                value=total_dist_m, unit="m", tag="SIMULATED", source_id="SRC-NASA-XEVA"
            ),
            walkback_distance_m=Quantity(
                value=max_walkback_m, unit="m", tag="SIMULATED", source_id="SRC-NASA-XEVA"
            ),
            walkback_within_limit=walkback_ok,
            max_slope_1m_deg=Quantity(value=max_s1, unit="deg", tag=slope_tag, source_id=slope_src),
            max_slope_64m_deg=Quantity(
                value=max_s64, unit="deg", tag=slope_tag, source_id=slope_src
            ),
            max_scale_divergence_deg=Quantity(
                value=max_div, unit="deg", tag=slope_tag, source_id=slope_src
            ),
            estimated_duration_h=Quantity(
                value=duration_h, unit="h", tag="SIMULATED", source_id="SRC-NASA-XEVA"
            ),
            estimated_radiation_msv=Quantity(
                value=rad_msv,
                unit="mSv",
                tag="SIMULATED",
                source_id="SRC-RAD-GALE",
                note="proxy Curiosity RAD, Gale",
            ),
            verdict=verdict,
            reasons=reasons,
            traversed_cell_ids=[c.cell_id for c in traversed_cells],
            metabolic_rate_w=Quantity(
                value=met_w, unit="W", tag="DERIVED", source_id="SRC-NASA-XEVA"
            ),
            walkback_return_h=Quantity(
                value=wb_ret_h, unit="h", tag="DERIVED", source_id="SRC-NASA-XEVA"
            ),
            walkback_o2_margin_min=Quantity(
                value=wb_o2_min, unit="min", tag="DERIVED", source_id="SRC-NASA-XEVA"
            ),
            rf_diffraction_loss_db=Quantity(
                value=rf_loss_db, unit="dB", tag="DERIVED", source_id="SRC-NASA-XEVA"
            ),
            rf_comms_verdict=rf_v,
        )
