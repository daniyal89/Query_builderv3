"""Sidebar-6 tooling endpoints.

Thin HTTP layer: request validation, rate limiting and background-job
bookkeeping. The actual work lives in
:mod:`backend.services.sidebar_tools_service`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status

from backend.models.sidebar_tools import (
    BuildDuckDbJobResponse,
    BuildDuckDbJobStartResponse,
    BuildDuckDbRequest,
    CsvToParquetJobResponse,
    CsvToParquetJobStartResponse,
    CsvToParquetRequest,
    FullPipelineRequest,
    FullPipelineStartResponse,
    FullPipelineStatusResponse,
    MaterialiseMonthJobResponse,
    MaterialiseMonthRequest,
    MaterialiseMonthStartResponse,
    SidebarToolResponse,
)
from backend.services.job_runtime import job_runtime
from backend.services.sidebar_tools_service import (
    BUILD_DUCKDB_JOB_TYPE,
    BUILD_DUCKDB_POLICY,
    CSV_TO_PARQUET_JOB_TYPE,
    CSV_TO_PARQUET_POLICY,
    FULL_PIPELINE_JOB_TYPE,
    FULL_PIPELINE_POLICY,
    MATERIALISE_JOB_TYPE,
    MATERIALISE_POLICY,
    _build_csv_to_parquet_targets,
    _execute_build_duckdb,
    _run_build_duckdb_job,
    _run_csv_to_parquet_job,
    _run_full_pipeline_job,
    _run_materialise_month_job,
    execute_csv_to_parquet,
)
from backend.utils.rate_limits import enforce_rate_limit

router = APIRouter()


@router.post("/sidebar-tools/build-duckdb", response_model=SidebarToolResponse)
def build_duckdb(request: Request, payload: BuildDuckDbRequest) -> SidebarToolResponse:
    try:
        enforce_rate_limit(request, "sidebar_build_duckdb")
        outcome = _execute_build_duckdb(payload)
        return SidebarToolResponse(
            message=outcome.message,
            output_path=outcome.output_path,
            rows_written=outcome.table_rows or 0,
            data_quality=outcome.data_quality,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sidebar-tools/build-duckdb/start", response_model=BuildDuckDbJobStartResponse)
def build_duckdb_start(request: Request, payload: BuildDuckDbRequest) -> BuildDuckDbJobStartResponse:
    enforce_rate_limit(request, "sidebar_build_duckdb")
    job_id = uuid.uuid4().hex
    job_runtime.start_job(
        job_type=BUILD_DUCKDB_JOB_TYPE,
        job_id=job_id,
        initial_snapshot={
            "job_id": job_id,
            "status": "queued",
            "message": "Build job queued.",
            "output_path": None,
            "progress_percent": 0,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        },
        payload=payload.model_dump(mode="json"),
        policy=BUILD_DUCKDB_POLICY,
        worker=lambda running_job_id: _run_build_duckdb_job(running_job_id, payload),
    )
    return BuildDuckDbJobStartResponse(job_id=job_id, status="queued", message="Build DuckDB job started.")


@router.get("/sidebar-tools/build-duckdb/status/{job_id}", response_model=BuildDuckDbJobResponse)
def build_duckdb_status(job_id: str) -> BuildDuckDbJobResponse:
    job = job_runtime.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build DuckDB job not found.")
    return BuildDuckDbJobResponse(**job)


@router.post("/sidebar-tools/build-duckdb/stop/{job_id}", response_model=BuildDuckDbJobResponse)
def build_duckdb_stop(job_id: str) -> BuildDuckDbJobResponse:
    job = job_runtime.stop_job(job_id, "Stop requested. Waiting for operation to finish...")
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Build DuckDB job not found.")
    return BuildDuckDbJobResponse(**job)


@router.post("/sidebar-tools/csv-to-parquet", response_model=SidebarToolResponse)
def csv_to_parquet(request: Request, payload: CsvToParquetRequest) -> SidebarToolResponse:
    try:
        enforce_rate_limit(request, "sidebar_csv_to_parquet")
        return execute_csv_to_parquet(payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sidebar-tools/csv-to-parquet/start", response_model=CsvToParquetJobStartResponse)
def csv_to_parquet_start(request: Request, payload: CsvToParquetRequest) -> CsvToParquetJobStartResponse:
    enforce_rate_limit(request, "sidebar_csv_to_parquet")
    try:
        files, output_root, _, single_target = _build_csv_to_parquet_targets(payload)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex
    job_runtime.start_job(
        job_type=CSV_TO_PARQUET_JOB_TYPE,
        job_id=job_id,
        initial_snapshot={
            "job_id": job_id,
            "status": "queued",
            "message": "CSV to Parquet conversion queued.",
            "processed_files": 0,
            "total_files": len(files),
            "skipped_files": 0,
            "current_file": None,
            "output_path": str(single_target if single_target is not None else output_root),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        },
        payload=payload.model_dump(mode="json"),
        policy=CSV_TO_PARQUET_POLICY,
        worker=lambda running_job_id: _run_csv_to_parquet_job(running_job_id, payload),
    )
    return CsvToParquetJobStartResponse(job_id=job_id, status="queued", message="CSV to Parquet job started.")


@router.get("/sidebar-tools/csv-to-parquet/status/{job_id}", response_model=CsvToParquetJobResponse)
def csv_to_parquet_status(job_id: str) -> CsvToParquetJobResponse:
    job = job_runtime.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CSV to Parquet job not found.")
    return CsvToParquetJobResponse(**job)


@router.post("/sidebar-tools/csv-to-parquet/stop/{job_id}", response_model=CsvToParquetJobResponse)
def csv_to_parquet_stop(job_id: str) -> CsvToParquetJobResponse:
    job = job_runtime.stop_job(job_id, "Stop requested. Waiting for current file to finish...")
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CSV to Parquet job not found.")
    return CsvToParquetJobResponse(**job)


# ──────────────── Full Pipeline (CSV→Parquet + Build DuckDB) ─────────────────


@router.post("/sidebar-tools/full-pipeline/start", response_model=FullPipelineStartResponse)
def full_pipeline_start(request: Request, payload: FullPipelineRequest) -> FullPipelineStartResponse:
    enforce_rate_limit(request, "sidebar_full_pipeline")
    job_id = uuid.uuid4().hex
    job_runtime.start_job(
        job_type=FULL_PIPELINE_JOB_TYPE,
        job_id=job_id,
        initial_snapshot={
            "job_id": job_id,
            "status": "queued",
            "message": "Full pipeline queued.",
            "current_phase": "queued",
            "parquet_processed_files": 0,
            "parquet_total_files": 0,
            "parquet_skipped_files": 0,
            "parquet_current_file": None,
            "parquet_output_path": None,
            "build_progress_percent": 0,
            "build_output_path": None,
            "overall_progress_percent": 0,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        },
        payload=payload.model_dump(mode="json"),
        policy=FULL_PIPELINE_POLICY,
        worker=lambda running_job_id: _run_full_pipeline_job(running_job_id, payload),
    )
    return FullPipelineStartResponse(job_id=job_id, status="queued", message="Full pipeline job started.")


@router.get("/sidebar-tools/full-pipeline/status/{job_id}", response_model=FullPipelineStatusResponse)
def full_pipeline_status(job_id: str) -> FullPipelineStatusResponse:
    job = job_runtime.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Full pipeline job not found.")
    return FullPipelineStatusResponse(**job)


@router.post("/sidebar-tools/full-pipeline/stop/{job_id}", response_model=FullPipelineStatusResponse)
def full_pipeline_stop(job_id: str) -> FullPipelineStatusResponse:
    job = job_runtime.stop_job(job_id, "Stop requested. Waiting for current operation to finish…")
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Full pipeline job not found.")
    return FullPipelineStatusResponse(**job)


# ─────────── Materialise: move the fast slot from one month to another ────────


@router.post("/sidebar-tools/materialise/start", response_model=MaterialiseMonthStartResponse)
def materialise_month_start(
    request: Request, payload: MaterialiseMonthRequest
) -> MaterialiseMonthStartResponse:
    """Promote a month to a real TABLE, handing the slot back from the previous one.

    Long-running by nature (~41 minutes for ~46M rows), so it is a job from the
    start rather than a synchronous endpoint.
    """
    enforce_rate_limit(request, "sidebar_build_duckdb")
    job_id = uuid.uuid4().hex
    job_runtime.start_job(
        job_type=MATERIALISE_JOB_TYPE,
        job_id=job_id,
        initial_snapshot={
            "job_id": job_id,
            "status": "queued",
            "message": "Materialise queued.",
            "output_path": None,
            "progress_percent": 0,
            "promoted": None,
            "promoted_rows": None,
            "demoted": [],
            "demote_warnings": [],
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        },
        payload=payload.model_dump(mode="json"),
        policy=MATERIALISE_POLICY,
        worker=lambda running_job_id: _run_materialise_month_job(running_job_id, payload),
    )
    return MaterialiseMonthStartResponse(
        job_id=job_id, status="queued", message="Materialise job started."
    )


@router.get(
    "/sidebar-tools/materialise/status/{job_id}", response_model=MaterialiseMonthJobResponse
)
def materialise_month_status(job_id: str) -> MaterialiseMonthJobResponse:
    job = job_runtime.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Materialise job not found.")
    return MaterialiseMonthJobResponse(**job)


@router.post(
    "/sidebar-tools/materialise/stop/{job_id}", response_model=MaterialiseMonthJobResponse
)
def materialise_month_stop(job_id: str) -> MaterialiseMonthJobResponse:
    job = job_runtime.stop_job(job_id, "Stop requested. Waiting for the current step to finish...")
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Materialise job not found.")
    return MaterialiseMonthJobResponse(**job)
