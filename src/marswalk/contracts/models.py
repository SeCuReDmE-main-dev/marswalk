"""Frozen Pydantic v2 Data Contract (v1.0.0) for MarsWalk.

All coordinates use planetocentric East longitude and latitude on the
IAU 2015 / NASA Mars Trek / USGS Astrogeology sphere of radius R = 3,396,190 m.

Read this file as a dictionary
    Every field the frontend receives is defined below, with its unit and
    its allowed values. The JSON Schemas in `schemas/` are exported from
    these classes, so the two never disagree.

The three ideas that run through every class
    1. `Quantity`: a number never travels alone. It carries its unit, its
       provenance tag and the id of its source in `manifest.sources[]`.
    2. `ProvenanceTag`: MEASURED (a real instrument), DERIVED (computed from
       real data), SIMULATED (placeholder or model, never shown as real).
    3. `VerdictLiteral`: GO / CAUTION / NO_GO, the only verdict words the
       astronaut ever sees.

The one rule
    v1.0.0 only grows. Fields may be added; none is ever renamed or removed.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ContractVersionLiteral = Literal["1.0.0", "1.1.0"]
CONTRACT_VERSION: ContractVersionLiteral = "1.1.0"
MARS_SPHERE_RADIUS_M: float = 3_396_190.0

ProvenanceTag = Literal["MEASURED", "DERIVED", "SIMULATED", "UNAVAILABLE"]
VerdictLiteral = Literal["GO", "CAUTION", "NO_GO"]
BaselineKey = Literal["1", "4", "16", "64"]
GridStatusLiteral = Literal["PLACEHOLDER", "ENGINE"]
REQUIRED_BASELINES: frozenset[str] = frozenset({"1", "4", "16", "64"})


class FrozenContractModel(BaseModel):
    """Base immutable contract model forbidding undeclared fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Quantity(FrozenContractModel):
    """Physical scalar quantity with mandatory unit, provenance tag, and source ID."""

    value: float = Field(..., description="Numeric scalar value (finite float).")
    unit: str = Field(..., min_length=1, description="Physical unit (e.g. 'm', 'deg', 'mSv/day').")
    tag: ProvenanceTag = Field(
        ...,
        description="Data provenance: MEASURED, DERIVED, or SIMULATED.",
    )
    source_id: str = Field(
        ...,
        min_length=3,
        description="Identifier matching an entry in SiteManifest.sources.",
    )
    note: str | None = Field(
        default=None,
        description="Optional provenance or proxy clarification note.",
    )

    @field_validator("value")
    @classmethod
    def _validate_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("Quantity.value must be a finite number.")
        return v


class Source(FrozenContractModel):
    """Primary NASA, JPL, USGS, or synthetic scaffold reference source."""

    id: str = Field(..., min_length=3, description="Unique source identifier (e.g. SRC-NASA-XEVA).")
    title: str = Field(..., min_length=3, description="Document or dataset title.")
    mission: str = Field(..., min_length=2, description="Mission or institution name.")
    url: str = Field(..., min_length=8, description="Canonical HTTPS URL.")
    license: str = Field(..., min_length=3, description="License or public domain designation.")
    citation: str = Field(..., min_length=5, description="Full bibliographic citation.")


class BasemapLayer(FrozenContractModel):
    """Tiled orbital basemap configuration compatible with NASA Mars Trek WMTS."""

    id: str = Field(..., description="Mars Trek layer identifier.")
    title: str = Field(..., description="Human-readable layer title.")
    template_url: str = Field(
        ...,
        description="WMTS/XYZ tile URL template containing {z}, {row}, and {col}.",
    )
    tile_grid: Literal["geographic_2to1_256px"] = Field(
        default="geographic_2to1_256px",
        description="Mars Trek 2:1 equirectangular geographic grid (EPSG:4326 style, 256x256 px).",
    )
    min_zoom: int = Field(default=0, ge=0, le=22)
    max_zoom: int = Field(default=17, ge=0, le=22)
    bbox: tuple[float, float, float, float] = Field(
        ...,
        description="Bounding box [min_lon, min_lat, max_lon, max_lat] in degrees East/North.",
    )
    resolution_m_per_px: float = Field(default=0.25, gt=0.0)
    source_id: str = Field(..., min_length=3)


class MarsCrs(FrozenContractModel):
    """Coordinate Reference System definition for the Mars sphere R = 3,396,190 m."""

    name: str = Field(default="IAU2015:49900 / Planetocentric East Sphere")
    sphere_radius_m: float = Field(default=MARS_SPHERE_RADIUS_M)
    lon_domain: Literal["east_positive_0_360"] = Field(default="east_positive_0_360")
    lat_type: Literal["planetocentric"] = Field(default="planetocentric")

    @field_validator("sphere_radius_m")
    @classmethod
    def _check_mars_sphere(cls, v: float) -> float:
        if abs(v - MARS_SPHERE_RADIUS_M) > 1e-3:
            raise ValueError(f"Mars sphere radius must be {MARS_SPHERE_RADIUS_M} m.")
        return v


class PackFileDigest(FrozenContractModel):
    """Integrity record for a file inside public_packs/<site>/v1/."""

    path: str = Field(..., min_length=1, description="Relative filename inside the site pack.")
    sha256: str = Field(..., min_length=64, max_length=64, description="Lowercase hex SHA-256.")
    bytes: int = Field(..., gt=0, description="Exact file size in bytes.")


class ManifestInputDigest(FrozenContractModel):
    """Cryptographic record of an upstream raw file actually read during pack generation."""

    source_id: str = Field(
        ..., min_length=3, description="Source ID matching SiteManifest.sources."
    )
    path_or_url: str = Field(..., min_length=3, description="Relative file path or canonical URL.")
    sha256: str = Field(..., min_length=64, max_length=64, description="Lowercase hex SHA-256.")
    bytes_read: int = Field(..., gt=0, description="Exact number of bytes read from the raw input.")


class SiteManifest(FrozenContractModel):
    """Root manifest.json for a signed Martian site pack."""

    contract_version: Literal["1.0.0", "1.1.0"] = Field(default=CONTRACT_VERSION)
    pack_version: str = Field(default="1.0.1", min_length=3)
    site_id: str = Field(..., min_length=2)
    site_name: str = Field(..., min_length=2)
    crs: MarsCrs = Field(default_factory=MarsCrs)
    bbox: tuple[float, float, float, float] = Field(
        ...,
        description="[min_lon, min_lat, max_lon, max_lat] in planetocentric East degrees.",
    )
    basemaps: list[BasemapLayer] = Field(..., min_length=1)
    sources: list[Source] = Field(..., min_length=1)
    inputs: list[ManifestInputDigest] = Field(
        default_factory=list,
        description="Verified raw input files read during pack construction.",
    )
    files: list[PackFileDigest] = Field(..., min_length=1)
    generated_at: str = Field(..., min_length=10, description="ISO-8601 generation timestamp.")

    @model_validator(mode="after")
    def _validate_bbox_and_sources(self) -> SiteManifest:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        if not (min_lon < max_lon and min_lat < max_lat):
            raise ValueError(f"Invalid bounding box ordering: {self.bbox}")
        source_ids = {s.id for s in self.sources}
        for bm in self.basemaps:
            if bm.source_id not in source_ids:
                raise ValueError(f"Basemap {bm.id} references unknown source_id {bm.source_id}")
        for inp in self.inputs:
            if inp.source_id not in source_ids:
                raise ValueError(
                    f"Input {inp.path_or_url} references unknown source_id {inp.source_id}"
                )
        return self


class GeoJsonPointGeometry(FrozenContractModel):
    """GeoJSON Point geometry [lon, lat] or [lon, lat, elev_m]."""

    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float] | tuple[float, float, float]


class GeoJsonLineGeometry(FrozenContractModel):
    """GeoJSON LineString geometry [[lon, lat], ...]."""

    type: Literal["LineString"] = "LineString"
    coordinates: list[tuple[float, float]] = Field(..., min_length=2)


class WaypointProperties(FrozenContractModel):
    """Telemetry properties for a single Perseverance rover stop from M20_waypoints.json."""

    waypoint_id: str = Field(..., min_length=1)
    sol: int = Field(..., ge=0, description="Mars 2020 mission sol.")
    site: int = Field(..., ge=0)
    drive: int = Field(..., ge=0)
    lon: float = Field(..., ge=-180.0, le=360.0)
    lat: float = Field(..., ge=-90.0, le=90.0)
    elev_geoid_m: Quantity
    rover_tilt_deg: Quantity
    rover_pitch_deg: Quantity
    rover_roll_deg: Quantity
    dist_total_m: Quantity
    panorama_url: str | None = Field(default=None)

    @model_validator(mode="after")
    def _check_measured_tags(self) -> WaypointProperties:
        for field_name in (
            "elev_geoid_m",
            "rover_tilt_deg",
            "rover_pitch_deg",
            "rover_roll_deg",
            "dist_total_m",
        ):
            q: Quantity = getattr(self, field_name)
            if q.tag != "MEASURED":
                raise ValueError(f"Waypoint {field_name} must carry tag='MEASURED'.")
        return self


class Waypoint(FrozenContractModel):
    """GeoJSON Feature representing one Perseverance rover waypoint."""

    type: Literal["Feature"] = "Feature"
    geometry: GeoJsonPointGeometry
    properties: WaypointProperties


class WaypointFeatureCollection(FrozenContractModel):
    """GeoJSON FeatureCollection of all Perseverance waypoints in the site pack."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    contract_version: Literal["1.0.0", "1.1.0"] = Field(default=CONTRACT_VERSION)
    site_id: str = Field(..., min_length=2)
    features: list[Waypoint] = Field(..., min_length=1)


class ConfidenceVector(FrozenContractModel):
    """3-component terrain confidence vector exposed to the UI as `confidence`.

    - `t`: Verified agreement between orbital baselines and ground-truth rover telemetry [0, 1].
    - `i`: Scale-gap or coverage uncertainty across baselines [0, 1].
    - `f`: Active hazard contradiction or safety limit exceedance [0, 1].
    """

    t: float = Field(..., ge=0.0, le=1.0, description="Verified safety agreement score [0..1].")
    i: float = Field(..., ge=0.0, le=1.0, description="Scale/coverage uncertainty score [0..1].")
    f: float = Field(..., ge=0.0, le=1.0, description="Hazard contradiction score [0..1].")


class HazardCell(FrozenContractModel):
    """Multi-scale terrain & EVA hazard assessment for a single grid cell."""

    cell_id: str = Field(..., min_length=1)
    row: int = Field(..., ge=0)
    col: int = Field(..., ge=0)
    lon: float = Field(..., ge=-180.0, le=360.0)
    lat: float = Field(..., ge=-90.0, le=90.0)
    size_m: float = Field(..., gt=0.0)
    elev_m: Quantity
    slope_deg_by_baseline: dict[BaselineKey, Quantity] = Field(
        ...,
        description="Terrain slope in degrees at 1m, 4m, 16m, and 64m baselines.",
    )
    scale_divergence: Quantity = Field(
        ...,
        description="Slope divergence (deg) across the 1m..64m baselines.",
    )
    rock_cfa_pct: Quantity | None = Field(
        default=None,
        description="Estimated Cumulative Fractional Area of rocks (%), or None when unavailable.",
    )
    confidence: ConfidenceVector
    verdict: VerdictLiteral = Field(
        ...,
        description="Actionable EVA / rover traversability verdict: GO, CAUTION, or NO_GO.",
    )
    reason: str = Field(..., min_length=3, description="Clear human-readable verdict explanation.")
    nearest_waypoint_sol: int | None = Field(default=None)
    measured_rover_tilt_deg: Quantity | None = Field(default=None)
    solar_shadow_fraction: Quantity | None = Field(default=None)
    hurst_exponent_h: Quantity | None = Field(default=None)
    step_scale_slope_075m_deg: Quantity | None = Field(default=None)
    thermal_inertia_tiu: Quantity | None = Field(default=None)
    crism_olindex3: Quantity | None = Field(default=None)
    crism_d2300: Quantity | None = Field(default=None)
    crism_bd1900_2: Quantity | None = Field(default=None)
    spectral_smectite_caution: bool | None = Field(default=None)
    geologic_unit: str | None = Field(default=None)
    distance_to_contact_m: Quantity | None = Field(default=None)
    aoa_inside: bool | None = Field(default=None)
    calibrated_opinion: ConfidenceVector | None = Field(default=None)
    sky_view_factor: Quantity | None = Field(default=None)
    local_gcr_dose_mgy_per_day: Quantity | None = Field(default=None)
    meda_dust_tau_880nm: Quantity | None = Field(default=None)
    metabolic_rate_w: Quantity | None = Field(default=None)
    walkback_o2_margin_min: Quantity | None = Field(default=None)
    rf_bullington_nu: Quantity | None = Field(default=None)
    rf_diffraction_loss_db: Quantity | None = Field(default=None)
    rf_comms_verdict: VerdictLiteral | None = Field(default=None)
    partial_topographic_refuge: bool | None = Field(default=None)
    partial_refuge_gcr_reduction_pct: Quantity | None = Field(default=None)
    obstacle_mask_fraction: Quantity | None = Field(default=None)

    @field_validator("slope_deg_by_baseline")
    @classmethod
    def _validate_all_baselines(cls, v: dict[BaselineKey, Quantity]) -> dict[BaselineKey, Quantity]:
        if set(v.keys()) != REQUIRED_BASELINES:
            raise ValueError(f"slope_deg_by_baseline must contain exact keys {REQUIRED_BASELINES}.")
        return v


class HazardGrid(FrozenContractModel):
    """Complete multi-scale hazard grid (`hazard_grid.json`) for a site pack."""

    contract_version: Literal["1.0.0", "1.1.0"] = Field(default=CONTRACT_VERSION)
    grid_status: GridStatusLiteral = Field(
        default="PLACEHOLDER",
        description="PLACEHOLDER in Pass 1 synthetic scaffold; ENGINE when built from HiRISE DTM.",
    )
    site_id: str = Field(..., min_length=2)
    bbox: tuple[float, float, float, float]
    rows: int = Field(..., gt=0)
    cols: int = Field(..., gt=0)
    cell_size_m: float = Field(..., gt=0.0)
    baselines_m: tuple[int, int, int, int] = Field(default=(1, 4, 16, 64))
    overlay_file: str = Field(default="hazard_overlay.png")
    planner_grid_file: str | None = Field(default=None)
    obstacles_file: str | None = Field(default=None)
    external_layers_status: dict[str, dict[str, str | float | bool]] | None = Field(default=None)
    cells: list[HazardCell] = Field(..., min_length=1)


class EvaConstraints(FrozenContractModel):
    """Citable NASA xEVA, Apollo, JPL Rover, and Curiosity RAD safety thresholds."""

    contract_version: Literal["1.0.0", "1.1.0"] = Field(default=CONTRACT_VERSION)
    suit_max_slope_deg: Quantity
    apollo_practical_slope_deg: Quantity
    apollo_max_relief_m: Quantity
    walkback_max_km: Quantity
    eva_duration_min_h: Quantity
    eva_duration_max_h: Quantity
    rover_max_slope_rock_deg: Quantity
    rover_max_slope_sand_deg: Quantity
    ripple_hazard_height_cm: Quantity
    rock_cfa_ok_pct: Quantity
    rock_cfa_caution_pct: Quantity
    gcr_dose_msv_per_day: Quantity
    radiation_environment_note: str = Field(..., min_length=10)
    bfo_30d_limit_mgy_eq: Quantity | None = Field(default=None)
    career_dose_limit_msv: Quantity | None = Field(default=None)
    primary_o2_kg: Quantity | None = Field(default=None)
    walkback_metabolic_w: Quantity | None = Field(default=None)
    dust_ingress_decontam_min: Quantity | None = Field(default=None)
    themis_sand_cut_tiu: Quantity | None = Field(default=None)
    rf_freq_mhz: Quantity | None = Field(default=None)
    rf_link_margin_db: Quantity | None = Field(default=None)


class EvaRouteProperties(FrozenContractModel):
    """Properties for a feature in `route.geojson` (traverse, EVA path, stop, or benchmark)."""

    feature_id: str = Field(..., min_length=1)
    segment_type: Literal[
        "MEASURED_ROVER_TRAVERSE",
        "SIMULATED_ASTRONAUT_EVA",
        "DERIVED_OBSTACLE_AWARE_EVA",
        "SCIENCE_STOP",
        "BENCHMARK",
    ]
    title: str = Field(..., min_length=2)
    tag: ProvenanceTag
    source_id: str = Field(..., min_length=3)
    verdict: VerdictLiteral
    distance_m: Quantity | None = Field(default=None)
    max_slope_deg: Quantity | None = Field(default=None)
    estimated_duration_h: Quantity | None = Field(default=None)
    estimated_radiation_msv: Quantity | None = Field(default=None)
    sol: int | None = Field(default=None)
    rover_tilt_deg: Quantity | None = Field(default=None)
    geologic_unit: str | None = Field(default=None)
    panorama_url: str | None = Field(default=None)
    notes: str = Field(..., min_length=3)


class EvaRouteFeature(FrozenContractModel):
    """Single GeoJSON Feature in `route.geojson`."""

    type: Literal["Feature"] = "Feature"
    geometry: GeoJsonLineGeometry | GeoJsonPointGeometry
    properties: EvaRouteProperties


class EvaRoute(FrozenContractModel):
    """Complete `route.geojson` FeatureCollection combining measured traverse & simulated EVA."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    contract_version: Literal["1.0.0", "1.1.0"] = Field(default=CONTRACT_VERSION)
    site_id: str = Field(..., min_length=2)
    features: list[EvaRouteFeature] = Field(..., min_length=2)


class GeoJsonPolygonGeometry(FrozenContractModel):
    """GeoJSON Polygon geometry for mapped obstacle clusters (`obstacles.geojson`)."""

    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[tuple[float, float]]] = Field(..., min_length=1)


class ObstaclePolygonProperties(FrozenContractModel):
    """Metadata and DERIVED provenance for an obstacle polygon (`M1`)."""

    obstacle_id: str = Field(..., min_length=3)
    obstacle_type: Literal["scarp", "large_rock_formation"]
    tag: ProvenanceTag
    source_id: str = Field(..., min_length=3)
    footprint_area_m2: float = Field(..., ge=0.0)
    internal_relief_m: float = Field(..., ge=0.0)
    physical_clearance_m: float = Field(..., ge=0.0)
    resolution_note: str = Field(..., min_length=10)


class ObstaclePolygonFeature(FrozenContractModel):
    """Single GeoJSON Feature in `obstacles.geojson`."""

    type: Literal["Feature"] = "Feature"
    geometry: GeoJsonPolygonGeometry
    properties: ObstaclePolygonProperties


class OnoRoverCfaReference(FrozenContractModel):
    """Ono et al. (2016) rover CFA reference metadata stored alongside `obstacles.geojson`."""

    ok_pct: float = Field(..., ge=0.0, le=100.0)
    caution_pct: float = Field(..., ge=0.0, le=100.0)
    golombek_1p5m_at_15pct: float = Field(..., ge=0.0, le=1.0)


class ObstacleFeatureCollection(FrozenContractModel):
    """GeoJSON FeatureCollection of DTM-derived scarps & >= 4 m formations (`obstacles.geojson`)."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    contract_version: Literal["1.0.0", "1.1.0"] = Field(default=CONTRACT_VERSION)
    site_id: str = Field(..., min_length=2)
    ono_rover_cfa_reference_pct: OnoRoverCfaReference
    features: list[ObstaclePolygonFeature] = Field(default_factory=list)
