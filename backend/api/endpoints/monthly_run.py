"""One-click monthly master run: settings, start/status/stop, and per-month progress."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.models.monthly_run import (
    MonthlyAutomationConfig,
    MonthlyRunMarkerResponse,
    MonthlyRunStartRequest,
    MonthlyRunStartResponse,
    MonthlyRunStatusResponse,
    MonthlyRunStepState,
)
from backend.services.monthly_run_service import (
    MonthlyRunAlreadyActive,
    MonthlyRunService,
    default_month,
    derive_plan,
    load_config,
    read_marker,
    save_config,
)
from backend.utils.rate_limits import enforce_rate_limit

router = APIRouter()


@router.get("/automation/config", response_model=MonthlyAutomationConfig)
def get_automation_config() -> MonthlyAutomationConfig:
    try:
        return load_config()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/automation/config", response_model=MonthlyAutomationConfig)
def put_automation_config(payload: MonthlyAutomationConfig) -> MonthlyAutomationConfig:
    save_config(payload)
    return payload


@router.get("/automation/monthly-run/plan")
def get_monthly_run_plan(month: str | None = Query(default=None)) -> dict:
    """What a run for this month would do, derived from the saved settings."""
    try:
        config = load_config()
        plan = derive_plan(month, config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"default_month": default_month(), **plan.as_dict()}


@router.get("/automation/monthly-run/marker", response_model=MonthlyRunMarkerResponse)
def get_monthly_run_marker(month: str | None = Query(default=None)) -> MonthlyRunMarkerResponse:
    try:
        plan = derive_plan(month, load_config())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    marker = read_marker(plan.token)
    if not marker:
        return MonthlyRunMarkerResponse(month=plan.token, exists=False)
    steps = {
        name: MonthlyRunStepState(**{k: v for k, v in state.items() if k in MonthlyRunStepState.model_fields})
        for name, state in (marker.get("steps") or {}).items()
        if isinstance(state, dict)
    }
    return MonthlyRunMarkerResponse(
        month=plan.token,
        exists=True,
        steps=steps,
        last_job_id=marker.get("last_job_id"),
        updated_at=marker.get("updated_at"),
    )


@router.get("/automation/monthly-run/active", response_model=MonthlyRunStatusResponse | None)
def get_active_monthly_run() -> MonthlyRunStatusResponse | None:
    job = MonthlyRunService.active()
    return MonthlyRunStatusResponse(**job) if job else None


@router.post("/automation/monthly-run/start", response_model=MonthlyRunStartResponse)
def start_monthly_run(request: Request, payload: MonthlyRunStartRequest) -> MonthlyRunStartResponse:
    enforce_rate_limit(request, "sidebar_full_pipeline")
    try:
        return MonthlyRunStartResponse(**MonthlyRunService.start(payload))
    except MonthlyRunAlreadyActive as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"message": str(exc), "job_id": exc.job_id}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/automation/monthly-run/status/{job_id}", response_model=MonthlyRunStatusResponse)
def get_monthly_run_status(job_id: str) -> MonthlyRunStatusResponse:
    job = MonthlyRunService.status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Monthly run not found.")
    return MonthlyRunStatusResponse(**job)


@router.post("/automation/monthly-run/stop/{job_id}", response_model=MonthlyRunStatusResponse)
def stop_monthly_run(job_id: str) -> MonthlyRunStatusResponse:
    job = MonthlyRunService.stop(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Monthly run not found.")
    return MonthlyRunStatusResponse(**job)
