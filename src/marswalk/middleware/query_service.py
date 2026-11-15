"""In-memory spatial query and EVA route evaluation service over a verified site pack."""

from __future__ import annotations

from pydantic import ConfigDict, Field

from marswalk.contracts.models import (
    FrozenContractModel,
    HazardCell,
    Quantity,
    VerdictLiteral,
    Waypoint,
)
from marswalk.middleware.build_pack import spherical_distance_m
from marswalk.middleware.pack_loader import LoadedSitePack


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


class PackQueryService:
    """Fast spatial lookup and route evaluator over a LoadedSitePack."""

    def __init__(self, pack: LoadedSitePack) -> None:
        self.pack = pack
        self._cell_coords = [(c.lon, c.lat, c) for c in pack.hazards.cells]
        self._wp_coords = [(w.properties.lon, w.properties.lat, w) for w in pack.waypoints.features]

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

        for idx, (lon, lat) in enumerate(pts):
            if idx > 0:
                prev_lon, prev_lat = pts[idx - 1]
                total_dist_m += spherical_distance_m(prev_lon, prev_lat, lon, lat)
            wb = spherical_distance_m(origin_lon, origin_lat, lon, lat)
            if wb > max_walkback_m:
                max_walkback_m = wb

            cell = min(
                self.pack.hazards.cells,
                key=lambda c: (c.lon - lon) ** 2 + (c.lat - lat) ** 2,
            )
            if cell.cell_id not in seen_ids:
                seen_ids.add(cell.cell_id)
                traversed_cells.append(cell)

        total_dist_m = round(total_dist_m, 2)
        max_walkback_m = round(max_walkback_m, 2)
        walkback_limit_m = self.pack.constraints.walkback_max_km.value * 1000.0
        walkback_ok = max_walkback_m <= walkback_limit_m

        c_first = traversed_cells[0].slope_deg_by_baseline["1"]
        slope_tag = c_first.tag
        slope_src = c_first.source_id

        max_s1 = max(c.slope_deg_by_baseline["1"].value for c in traversed_cells)
        max_s64 = max(c.slope_deg_by_baseline["64"].value for c in traversed_cells)
        max_div = max(c.scale_divergence.value for c in traversed_cells)

        duration_h = round((total_dist_m / 1000.0) / req.walking_speed_km_h, 3)
        rad_msv = round(
            self.pack.constraints.gcr_dose_msv_per_day.value * (duration_h / 24.0),
            4,
        )

        reasons: list[str] = []
        verdict: VerdictLiteral = "GO"

        if not walkback_ok:
            verdict = "NO_GO"
            reasons.append(
                f"Walkback distance ({max_walkback_m:.0f} m) exceeds NASA xEVA 2,000 m limit."
            )
        if max_s1 >= self.pack.constraints.suit_max_slope_deg.value:
            verdict = "NO_GO"
            reasons.append(
                f"Maximum 1m slope ({max_s1:.1f} deg) exceeds NASA xEVA 20.0 deg suit limit."
            )
        if duration_h > self.pack.constraints.eva_duration_max_h.value:
            verdict = "NO_GO"
            reasons.append(
                f"Estimated EVA duration ({duration_h:.2f} h) exceeds 8.0 h xEVA ceiling."
            )

        if verdict != "NO_GO":
            if (
                max_s1 >= self.pack.constraints.rover_max_slope_sand_deg.value
                or max_div >= 5.0
                or any(c.verdict == "CAUTION" for c in traversed_cells)
            ):
                verdict = "CAUTION"
                reasons.append(
                    f"Route crosses moderate 1m slope ({max_s1:.1f} deg) "
                    f"or scale divergence ({max_div:.1f} deg)."
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
        )
