"""Optional live API over the verified `public_packs/<site>/v1/` data pack.

Who this is for
    The frontend can work from static files alone. I keep this server for two
    things static files cannot do: finding the cell under a click
    (`GET /v1/sites/{site_id}/cell`) and judging a route the user draws
    (`POST /v1/sites/{site_id}/evaluate-route`).

How to run it
    pip install -e .
    uvicorn marswalk.middleware.api:app --reload
    -> interactive docs at http://127.0.0.1:8000/docs

What it promises
    - Every GET returns exactly the content of the signed pack, validated
      against the v1.0.0 contract. Nothing is recomputed on the fly.
    - If one byte of the pack does not match its SHA-256 fingerprint, the
      pack is refused and the endpoint answers 404 instead of serving
      altered data.
    - CORS is open for GET/POST so a local frontend dev server can call it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from marswalk.contracts.models import (
    CONTRACT_VERSION,
    EvaConstraints,
    EvaRoute,
    HazardGrid,
    ObstacleFeatureCollection,
    SiteManifest,
    WaypointFeatureCollection,
)
from marswalk.middleware.pack_loader import PackIntegrityError, load_and_verify_pack
from marswalk.middleware.query_service import (
    CellLookupResult,
    PackQueryService,
    PlanRouteRequest,
    PlanRouteResult,
    RouteEvaluationRequest,
    RouteEvaluationResult,
    RoverCamerasResponse,
    is_safe_mode_enabled,
)


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=4)
def get_query_service(site_id: str = "jezero") -> PackQueryService:
    """Load and cache the SHA-256 verified site pack query service."""
    try:
        pack = load_and_verify_pack(_default_repo_root(), site_id=site_id)
    except PackIntegrityError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PackQueryService(pack)


app = FastAPI(
    title="MarsWalk Middleware API",
    description=(
        "Multi-scale Martian terrain verification & EVA survival guide middleware "
        "serving cryptographically verified static packs (v1.0.0)."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str | bool]:
    """Return service health, frozen contract version, and live safe-mode flag."""
    return {
        "status": "ok",
        "contract_version": CONTRACT_VERSION,
        "safe_mode": is_safe_mode_enabled(),
    }


@app.get("/v1/sites")
def list_sites() -> dict[str, list[str]]:
    """List available verified site packs."""
    return {"sites": ["jezero"]}


@app.get("/v1/sites/{site_id}/manifest", response_model=SiteManifest)
def get_manifest(site_id: str) -> SiteManifest:
    """Return the signed `manifest.json` for a site pack."""
    return get_query_service(site_id).pack.manifest


@app.get("/v1/sites/{site_id}/waypoints", response_model=WaypointFeatureCollection)
def get_waypoints(site_id: str) -> WaypointFeatureCollection:
    """Return all 708 Perseverance rover waypoints (`waypoints.geojson`)."""
    return get_query_service(site_id).pack.waypoints


@app.get("/v1/sites/{site_id}/route", response_model=EvaRoute)
def get_route(site_id: str) -> EvaRoute:
    """Return `route.geojson` (MEASURED rover traverse + SIMULATED EVA corridor + stops)."""
    return get_query_service(site_id).pack.route


@app.get("/v1/sites/{site_id}/hazards", response_model=HazardGrid)
def get_hazards(site_id: str) -> HazardGrid:
    """Return the multi-scale hazard grid (`hazard_grid.json`)."""
    return get_query_service(site_id).pack.hazards


@app.get("/v1/sites/{site_id}/hazard-overlay.png")
def get_hazard_overlay_png(site_id: str) -> FileResponse:
    """Return the transparent RGBA `hazard_overlay.png` heatmap."""
    svc = get_query_service(site_id)
    png_path = svc.pack.pack_dir / svc.pack.hazards.overlay_file
    return FileResponse(png_path, media_type="image/png")


@app.get("/v1/sites/{site_id}/constraints", response_model=EvaConstraints)
def get_constraints(site_id: str) -> EvaConstraints:
    """Return citable NASA xEVA, Apollo, JPL Rover, and Curiosity RAD thresholds."""
    return get_query_service(site_id).pack.constraints


@app.get("/v1/sites/{site_id}/cell", response_model=CellLookupResult)
def lookup_cell(
    site_id: str,
    lon: float = Query(..., ge=-180.0, le=360.0, description="Planetocentric East longitude"),
    lat: float = Query(..., ge=-90.0, le=90.0, description="Planetocentric latitude"),
) -> CellLookupResult:
    """Look up the nearest multi-scale HazardCell and ground-truth Perseverance waypoint."""
    return get_query_service(site_id).lookup_cell(lon=lon, lat=lat)


@app.post("/v1/sites/{site_id}/evaluate-route", response_model=RouteEvaluationResult)
def evaluate_route(site_id: str, request: RouteEvaluationRequest) -> RouteEvaluationResult:
    """Evaluate a candidate [lon, lat] EVA route against multi-scale hazards & xEVA limits."""
    return get_query_service(site_id).evaluate_route(request)


@app.post("/v1/sites/{site_id}/plan-route", response_model=PlanRouteResult)
def plan_route(site_id: str, request: PlanRouteRequest) -> PlanRouteResult:
    """Plan an obstacle-avoiding EVA route on `planner_grid_10m.png` (`M2` + `M4` + `M6`)."""
    return get_query_service(site_id).plan_route(request)


@app.get("/v1/sites/{site_id}/obstacles", response_model=ObstacleFeatureCollection)
def get_obstacles(site_id: str) -> ObstacleFeatureCollection:
    """Return vectorized `>= ~4 m` boulder/scarp obstacle polygons (`obstacles.geojson`, `M1`)."""
    svc = get_query_service(site_id)
    if svc.pack.obstacles is None:
        raise HTTPException(status_code=404, detail="obstacles.geojson not present in site pack")
    return svc.pack.obstacles


@app.get("/v1/sites/{site_id}/planner-grid-10m.png")
def get_planner_grid_10m_png(site_id: str) -> FileResponse:
    """Return the lossless 8-bit RGBA `planner_grid_10m.png` (`M1`/`M2`)."""
    svc = get_query_service(site_id)
    fname = svc.pack.hazards.planner_grid_file or "planner_grid_10m.png"
    png_path = svc.pack.pack_dir / fname
    if not png_path.exists():
        raise HTTPException(status_code=404, detail="planner_grid_10m.png not present in site pack")
    return FileResponse(png_path, media_type="image/png")


@app.get("/v1/sites/{site_id}/waypoints/{sol}/cameras", response_model=RoverCamerasResponse)
def get_waypoint_cameras(
    site_id: str,
    sol: int,
    azimuth_deg: float | None = Query(default=None, ge=0.0, le=360.0),
    max_azimuth_delta_deg: float = Query(default=90.0, ge=5.0, le=180.0),
    page: int = Query(default=1, ge=1, le=200),
    page_size: int = Query(default=12, ge=1, le=100),
    allow_network: bool = Query(default=False),
) -> RoverCamerasResponse:
    """Return paginated Mars 2020 `raw_images` camera frames for `sol` (`M5` dedicated endpoint)."""
    return get_query_service(site_id).get_waypoint_cameras(
        sol=sol,
        azimuth_deg=azimuth_deg,
        max_azimuth_delta_deg=max_azimuth_delta_deg,
        page=page,
        page_size=page_size,
        allow_network=allow_network,
    )
