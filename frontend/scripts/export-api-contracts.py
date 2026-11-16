"""Copy middleware response schemas into the frontend, without editing backend contracts."""

import json
from pathlib import Path

from marswalk.contracts.models import ObstacleFeatureCollection
from marswalk.engine.validation import ValidationReport
from marswalk.middleware.query_service import (
    CellLookupResult,
    PlanRouteRequest,
    PlanRouteResult,
    RouteEvaluationRequest,
    RouteEvaluationResult,
    RoverCamerasResponse,
)

destination = Path(__file__).resolve().parents[1] / "src/data/api-schemas"
destination.mkdir(parents=True, exist_ok=True)
for model in (
    ValidationReport,
    ObstacleFeatureCollection,
    CellLookupResult,
    PlanRouteRequest,
    PlanRouteResult,
    RouteEvaluationRequest,
    RouteEvaluationResult,
    RoverCamerasResponse,
):
    (destination / f"{model.__name__}.json").write_text(
        json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8"
    )
    print(f"Exported {model.__name__}")
