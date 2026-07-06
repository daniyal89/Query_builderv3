"""
export.py — Background-job endpoint for writing large query results directly to a CSV file.

Instead of loading millions of rows into Python memory and serialising them as
JSON over HTTP, this endpoint hands the SQL off to DuckDB's native COPY command
which streams rows straight to disk.  The frontend polls the job-status endpoint
for progress and retrieves the final file path on completion.

Endpoints
---------
POST /api/query/export-csv/start
    Enqueue an export job.  Returns immediately with a job_id.

GET  /api/query/export-csv/status/{job_id}
    Poll the current status / rows_written count.

POST /api/query/export-csv/cancel/{job_id}
    Request cancellation of a running export.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.api.deps import get_db_service
from backend.models.export import (
    ExportCsvJobStartResponse,
    ExportCsvJobStatusResponse,
    ExportCsvRequest,
)
from backend.models.query import QueryPayload
from backend.services.duckdb_service import DuckDBService
from backend.services.error_log_service import ErrorLogService
from backend.services.job_runtime import (
    BackgroundJobCancelled,
    BackgroundJobPolicy,
    job_runtime,
)
from backend.services.query_builder_service import QueryBuilderService
from backend.utils.path_safety import sanitize_local_path_input
from backend.utils.rate_limits import enforce_rate_limit

router = APIRouter()

EXPORT_CSV_JOB_TYPE = "query.export_csv"
EXPORT_CSV_POLICY = BackgroundJobPolicy(max_attempts=1, retry_backoff_seconds=0)

# Rows above this threshold are sent through the server-side disk export path
LARGE_EXPORT_ROW_THRESHOLD = 200_000


def _update_export_job(job_id: str, **updates: Any) -> None:
    """Merge *updates* into the job snapshot (non-blocking helper)."""
    job_runtime.update_job(job_id, **updates)


def _run_export_job(job_id: str, payload: ExportCsvRequest, db: DuckDBService) -> None:
    """Background worker: build SQL → COPY to disk → update snapshot."""
    try:
        _update_export_job(
            job_id,
            status="running",
            message="Building SQL…",
            started_at=datetime.now().isoformat(timespec="seconds"),
        )

        query = payload.payload

        # ── Build the SQL (same logic as /api/query, but with no row limit) ──
        if query.execution_mode == "sql":
            rendered_sql = QueryBuilderService.normalize_manual_sql(query.sql or "")
        else:
            # Builder mode — render with limit_rows=0 (unlimited)
            unlim_query = query.model_copy(update={"limit_rows": 0})
            data_sql, params = QueryBuilderService.build_sql(unlim_query)
            rendered_sql = QueryBuilderService.render_sql(data_sql, params, query.engine)

        job_runtime.raise_if_cancelled(job_id)

        _update_export_job(job_id, message="Writing CSV to disk…")

        # ── Validate & resolve the output path ───────────────────────────────
        sanitized = sanitize_local_path_input(payload.output_path, "output_path")
        out_path = Path(sanitized).expanduser().resolve()

        # Ensure .csv extension
        if out_path.suffix.lower() != ".csv":
            out_path = out_path.with_suffix(".csv")

        out_path.parent.mkdir(parents=True, exist_ok=True)

        # ── Execute COPY TO disk ─────────────────────────────────────────────
        rows_written = db.export_to_csv(rendered_sql, str(out_path))

        job_runtime.raise_if_cancelled(job_id)

        _update_export_job(
            job_id,
            status="completed",
            message=f"Export complete — {rows_written:,} rows written to {out_path.name}.",
            output_path=str(out_path),
            rows_written=rows_written,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )

    except BackgroundJobCancelled:
        _update_export_job(
            job_id,
            status="cancelled",
            message="Export cancelled by user.",
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )

    except Exception as exc:
        ErrorLogService.append(
            {
                "endpoint": "/api/query/export-csv/start",
                "method": "POST",
                "status_code": 500,
                "error": str(exc),
                "exception_type": type(exc).__name__,
                "job_id": job_id,
                "stage": "background_worker",
            }
        )
        _update_export_job(
            job_id,
            status="failed",
            message=f"Export failed: {exc}",
            last_error=str(exc),
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
        raise


@router.post(
    "/query/export-csv/start",
    response_model=ExportCsvJobStartResponse,
    summary="Start a background CSV export job (writes directly to disk — suited for very large results)",
    tags=["Query"],
)
async def start_export_csv(
    request: Request,
    payload: ExportCsvRequest,
    db: DuckDBService = Depends(get_db_service),
) -> ExportCsvJobStartResponse:
    """Enqueue a server-side CSV export job and return immediately.

    The client should poll ``GET /api/query/export-csv/status/{job_id}`` until
    ``status`` is ``completed`` or ``failed``.
    """
    enforce_rate_limit(request, "query_export_csv")

    if not db.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No database connected. Use POST /api/duckdb/connect first.",
        )

    # Validate output path before starting the job
    try:
        sanitize_local_path_input(payload.output_path, "output_path")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid output path: {exc}",
        ) from exc

    # Resolve the final output path for the response
    out_path = Path(payload.output_path).expanduser().resolve()
    if out_path.suffix.lower() != ".csv":
        out_path = out_path.with_suffix(".csv")

    job_id = uuid.uuid4().hex

    job_runtime.start_job(
        job_type=EXPORT_CSV_JOB_TYPE,
        job_id=job_id,
        initial_snapshot={
            "job_id": job_id,
            "status": "queued",
            "message": "Export job queued.",
            "output_path": str(out_path),
            "rows_written": 0,
            "started_at": None,
            "finished_at": None,
            "last_error": None,
        },
        payload=payload.model_dump(mode="json"),
        policy=EXPORT_CSV_POLICY,
        worker=lambda running_job_id: _run_export_job(running_job_id, payload, db),
    )

    return ExportCsvJobStartResponse(
        job_id=job_id,
        status="queued",
        message="Export job queued. Poll /status/{job_id} for progress.",
        output_path=str(out_path),
    )


@router.get(
    "/query/export-csv/status/{job_id}",
    response_model=ExportCsvJobStatusResponse,
    summary="Poll the status of a CSV export job",
    tags=["Query"],
)
async def get_export_csv_status(job_id: str) -> ExportCsvJobStatusResponse:
    """Return the current snapshot of the export job."""
    job = job_runtime.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export job '{job_id}' not found.",
        )
    return ExportCsvJobStatusResponse(**job)


@router.post(
    "/query/export-csv/cancel/{job_id}",
    response_model=ExportCsvJobStatusResponse,
    summary="Request cancellation of a running CSV export job",
    tags=["Query"],
)
async def cancel_export_csv(job_id: str) -> ExportCsvJobStatusResponse:
    """Signal the running export worker to stop at the next checkpoint."""
    job = job_runtime.stop_job(job_id, "Cancellation requested by user.")
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export job '{job_id}' not found.",
        )
    return ExportCsvJobStatusResponse(**job)
