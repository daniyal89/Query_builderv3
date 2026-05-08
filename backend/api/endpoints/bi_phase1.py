from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import get_bi_phase1_service
from backend.models.bi_entities import Chart, Dashboard, DataSource, Dataset, Metric, Workspace
from backend.models.bi_phase1_api import (
    BIPhase1CreateChartRequest,
    BIPhase1CreateDashboardRequest,
    BIPhase1CreateDatasetRequest,
    BIPhase1CreateMetricRequest,
    BIPhase1CreateWorkspaceRequest,
    BIPhase1RegisterSourceRequest,
    BIPhase1StateResponse,
)
from backend.services.bi_phase1_service import BIPhase1Service

router = APIRouter()
ACTOR = "bi-phase1-ui"
ROLE = "Editor"


def _translate_bi_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, KeyError):
        detail = str(exc)
        if detail.startswith("'") and detail.endswith("'"):
            detail = detail[1:-1]
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/bi-phase1/state", response_model=BIPhase1StateResponse)
async def get_bi_phase1_state(
    service: BIPhase1Service = Depends(get_bi_phase1_service),
) -> BIPhase1StateResponse:
    return service.get_state()


@router.post("/bi-phase1/workspaces", response_model=Workspace, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: BIPhase1CreateWorkspaceRequest,
    service: BIPhase1Service = Depends(get_bi_phase1_service),
) -> Workspace:
    try:
        return service.create_workspace(
            ACTOR,
            ROLE,
            Workspace(
                id=service._make_id("ws"),
                name=payload.name.strip(),
                description=payload.description.strip(),
            ),
        )
    except Exception as exc:  # pragma: no cover - covered through translated cases
        raise _translate_bi_error(exc) from exc


@router.post("/bi-phase1/data-sources", response_model=DataSource, status_code=status.HTTP_201_CREATED)
async def register_source(
    payload: BIPhase1RegisterSourceRequest,
    service: BIPhase1Service = Depends(get_bi_phase1_service),
) -> DataSource:
    try:
        detected_type, _ = service._resolve_connector(payload.location.strip(), payload.source_type)
        return service.register_source(
            ACTOR,
            ROLE,
            DataSource(
                id=service._make_id("src"),
                workspace_id=payload.workspace_id,
                name=payload.name.strip(),
                source_type=detected_type,
                location=payload.location.strip(),
            ),
        )
    except Exception as exc:  # pragma: no cover - covered through translated cases
        raise _translate_bi_error(exc) from exc


@router.post("/bi-phase1/datasets", response_model=Dataset, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    payload: BIPhase1CreateDatasetRequest,
    service: BIPhase1Service = Depends(get_bi_phase1_service),
) -> Dataset:
    try:
        return service.create_dataset(
            ACTOR,
            ROLE,
            Dataset(
                id=service._make_id("ds"),
                workspace_id=payload.workspace_id,
                data_source_id=payload.data_source_id,
                name=payload.name.strip(),
            ),
        )
    except Exception as exc:  # pragma: no cover - covered through translated cases
        raise _translate_bi_error(exc) from exc


@router.post("/bi-phase1/datasets/{dataset_id}/publish", response_model=Dataset)
async def publish_dataset(
    dataset_id: str,
    service: BIPhase1Service = Depends(get_bi_phase1_service),
) -> Dataset:
    try:
        return service.publish_dataset(ACTOR, ROLE, dataset_id)
    except Exception as exc:  # pragma: no cover - covered through translated cases
        raise _translate_bi_error(exc) from exc


@router.post("/bi-phase1/metrics", response_model=Metric, status_code=status.HTTP_201_CREATED)
async def create_metric(
    payload: BIPhase1CreateMetricRequest,
    service: BIPhase1Service = Depends(get_bi_phase1_service),
) -> Metric:
    try:
        return service.create_metric(
            ACTOR,
            ROLE,
            Metric(
                id=service._make_id("met"),
                dataset_id=payload.dataset_id,
                name=payload.name.strip(),
                expression=payload.expression.strip(),
                aggregation=payload.aggregation,
            ),
        )
    except Exception as exc:  # pragma: no cover - covered through translated cases
        raise _translate_bi_error(exc) from exc


@router.post("/bi-phase1/charts", response_model=Chart, status_code=status.HTTP_201_CREATED)
async def create_chart(
    payload: BIPhase1CreateChartRequest,
    service: BIPhase1Service = Depends(get_bi_phase1_service),
) -> Chart:
    try:
        return service.create_chart(
            ACTOR,
            ROLE,
            Chart(
                id=service._make_id("cht"),
                dataset_id=payload.dataset_id,
                title=payload.title.strip(),
                chart_type=payload.chart_type,
                field_ids=payload.field_ids,
                metric_ids=payload.metric_ids,
            ),
        )
    except Exception as exc:  # pragma: no cover - covered through translated cases
        raise _translate_bi_error(exc) from exc


@router.post("/bi-phase1/dashboards", response_model=Dashboard, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    payload: BIPhase1CreateDashboardRequest,
    service: BIPhase1Service = Depends(get_bi_phase1_service),
) -> Dashboard:
    try:
        return service.create_dashboard(
            ACTOR,
            ROLE,
            Dashboard(
                id=service._make_id("dash"),
                workspace_id=payload.workspace_id,
                name=payload.name.strip(),
                chart_ids=payload.chart_ids,
            ),
        )
    except Exception as exc:  # pragma: no cover - covered through translated cases
        raise _translate_bi_error(exc) from exc
