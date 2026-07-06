"""
export.py — Pydantic models for the large CSV export background job API.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.models.query import QueryPayload


class ExportCsvRequest(BaseModel):
    """Request body for starting a server-side CSV export job."""

    payload: QueryPayload = Field(..., description="Query to execute and export.")
    output_path: str = Field(
        ...,
        description="Absolute local path to write the CSV file (e.g. C:\\exports\\result.csv).",
        min_length=4,
    )


class ExportCsvJobStartResponse(BaseModel):
    """Response returned immediately after enqueueing the export job."""

    job_id: str = Field(..., description="Unique ID of the background export job.")
    status: str = Field(default="queued", description="Initial job status.")
    message: str = Field(default="Export job queued.", description="Human-readable status message.")
    output_path: str = Field(..., description="Absolute path where the CSV will be written.")


class ExportCsvJobStatusResponse(BaseModel):
    """Polling response for an in-progress or completed export job."""

    job_id: str = Field(..., description="Unique ID of the export job.")
    status: str = Field(..., description="Job status: queued | running | completed | failed | cancelled.")
    message: str = Field(default="", description="Human-readable progress message.")
    output_path: str | None = Field(default=None, description="Path to the finished CSV file.")
    rows_written: int = Field(default=0, description="Number of rows written so far.")
    started_at: str | None = Field(default=None, description="ISO timestamp when the job started.")
    finished_at: str | None = Field(default=None, description="ISO timestamp when the job finished.")
    last_error: str | None = Field(default=None, description="Last error message if the job failed.")

    model_config = {"extra": "ignore"}
