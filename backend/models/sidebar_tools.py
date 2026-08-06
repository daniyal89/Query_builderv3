"""Models for Sidebar-6 tooling operations."""

from __future__ import annotations

from pathlib import Path
from pydantic import BaseModel, Field, field_validator

from backend.utils.path_safety import sanitize_local_path_input


class BuildDuckDbRequest(BaseModel):
    db_path: str = Field(..., description="Target DuckDB file path.")
    input_path: str = Field(..., description="Input file path or glob pattern.")
    object_name: str = Field(..., description="DuckDB table/view name.")
    object_type: str = Field(default="TABLE", description="TABLE or VIEW.")
    replace: bool = Field(default=True, description="Replace object if exists.")
    month_label: str | None = Field(default=None, description="Optional label for logging.")

    @field_validator("db_path", "input_path")
    @classmethod
    def validate_paths(cls, value: str) -> str:
        return sanitize_local_path_input(value, "path")

    @field_validator("object_type")
    @classmethod
    def validate_object_type(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if normalized not in {"TABLE", "VIEW"}:
            raise ValueError("object_type must be TABLE or VIEW.")
        return normalized

    @field_validator("object_name")
    @classmethod
    def validate_object_name(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("object_name cannot be empty.")
        return normalized


class MaterialiseMonthRequest(BuildDuckDbRequest):
    """Promote one month to a real TABLE and demote whichever month held that slot.

    Deliberately a ``BuildDuckDbRequest``: promoting *is* a TABLE build, so the
    same validated fields apply and the service can hand the payload straight to
    ``_execute_build_duckdb``.
    """

    object_type: str = Field(default="TABLE", description="Always TABLE for a promote.")
    demote_previous: bool = Field(
        default=True,
        description=(
            "Convert the previously materialised month back to a view. Only ever acts "
            "when that month's parquet is present and still matches it row for row."
        ),
    )


class MaterialiseMonthJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    output_path: str | None = None
    progress_percent: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    #: The month promoted to a TABLE.
    promoted: str | None = None
    promoted_rows: int | None = None
    #: Months converted back to views to make room.
    demoted: list[str] = []
    #: Months left materialised because demoting them could not be proven safe.
    demote_warnings: list[str] = []
    data_quality: str = "ok"  # ok | warning | loss
    reconnect_error: str | None = None


class MaterialiseMonthStartResponse(BaseModel):
    job_id: str
    status: str
    message: str


class CsvToParquetRequest(BaseModel):
    input_path: str = Field(..., description="Input CSV path or glob pattern.")
    output_path: str = Field(
        ...,
        description="Output parquet folder path (or explicit .parquet file path for single-file mode).",
    )
    compression: str = Field(default="zstd", description="Parquet compression codec.")
    hir_file: str | None = Field(default=None, description="Optional HIR Excel file path for enrichment join.")
    supp_mapper_file: str | None = Field(default=None, description="Optional suppMapper Excel file path for enrichment join.")
    overwrite_parquet: bool = Field(default=False, description="Overwrite existing parquet files.")

    @field_validator("input_path", "output_path", "hir_file", "supp_mapper_file")
    @classmethod
    def validate_paths(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return sanitize_local_path_input(value, "path")

    @field_validator("compression")
    @classmethod
    def validate_compression(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        allowed = {"uncompressed", "snappy", "gzip", "zstd", "lz4", "brotli"}
        if normalized not in allowed:
            raise ValueError(
                "compression must be one of: uncompressed, snappy, gzip, zstd, lz4, brotli."
            )
        return normalized


class FileRowAudit(BaseModel):
    """What happened to one source file, in rows."""

    source_file: str
    target_file: str | None = None
    outcome: str = "written"  # written | reused | repaired | skipped | failed
    reason: str = ""
    source_rows: int = 0
    written_rows: int = 0
    quarantined_rows: int = 0
    quarantine_reasons: dict[str, int] = {}
    quarantine_file: str | None = None


class RowReconciliation(BaseModel):
    """Source → parquet → table row balance for a whole run.

    ``unaccounted_rows`` must be zero. Anything else means rows went missing
    without a decision being recorded, which is the failure this pipeline used
    to have no way of detecting.
    """

    source_rows: int = 0
    written_rows: int = 0
    reused_rows: int = 0
    quarantined_rows: int = 0
    unaccounted_rows: int = 0
    table_rows: int | None = None
    balanced: bool = True
    discrepancies: list[str] = []


class SidebarToolResponse(BaseModel):
    status: str = "ok"
    message: str
    output_path: str | None = None
    rows_written: int = 0
    rows_quarantined: int = 0
    data_quality: str = "ok"  # ok | warning | loss


class CsvToParquetJobStartResponse(BaseModel):
    job_id: str
    status: str
    message: str


class CsvToParquetJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    processed_files: int = 0
    total_files: int = 0
    skipped_files: int = 0
    parquet_skipped_details: list[str] = []
    total_input_rows: int = 0
    total_output_rows: int = 0
    current_file: str | None = None
    output_path: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    row_audit: list[FileRowAudit] = []
    row_audit_truncated: bool = False
    reconciliation: RowReconciliation = RowReconciliation()
    data_quality: str = "ok"  # ok | warning | loss


class BuildDuckDbJobStartResponse(BaseModel):
    job_id: str
    status: str
    message: str


class BuildDuckDbJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    output_path: str | None = None
    progress_percent: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    parquet_input_rows: int | None = None
    table_rows: int | None = None
    row_delta: int = 0
    excluded_input_files: list[str] = []
    data_quality: str = "ok"  # ok | warning | loss
    #: Build succeeded but the dashboard could not be reconnected to the database.
    #: The table is fine; the UI needs a manual reconnect. Previously swallowed.
    reconnect_error: str | None = None
    #: TABLE or VIEW — lets the UI say "resolves N rows" rather than "holds N rows".
    object_type: str = "TABLE"


# ─────────────────── Full Pipeline (CSV→Parquet + Build DuckDB) ──────────────


class FullPipelineRequest(BaseModel):
    """Combined request for running CSV→Parquet then Build DuckDB in one shot."""

    # CSV→Parquet fields
    input_path: str = Field(..., description="Input CSV/GZ path or glob pattern.")
    parquet_output_path: str = Field(..., description="Output folder for parquet files.")
    compression: str = Field(default="snappy", description="Parquet compression codec.")
    hir_file: str | None = Field(default=None, description="Optional HIR Excel file path.")
    supp_mapper_file: str | None = Field(default=None, description="Optional suppMapper Excel file path.")
    overwrite_parquet: bool = Field(default=False, description="Overwrite existing parquet files.")

    # Build DuckDB fields
    db_path: str = Field(..., description="Target DuckDB file path.")
    object_name: str = Field(..., description="DuckDB table/view name.")
    object_type: str = Field(default="TABLE", description="TABLE or VIEW.")
    replace: bool = Field(default=True, description="Replace object if exists.")
    month_label: str | None = Field(default=None, description="Optional month label.")

    @field_validator("input_path", "parquet_output_path", "db_path", "hir_file", "supp_mapper_file")
    @classmethod
    def validate_paths(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return sanitize_local_path_input(value, "path")

    @field_validator("object_type")
    @classmethod
    def validate_object_type(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if normalized not in {"TABLE", "VIEW"}:
            raise ValueError("object_type must be TABLE or VIEW.")
        return normalized

    @field_validator("object_name")
    @classmethod
    def validate_object_name(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("object_name cannot be empty.")
        return normalized

    @field_validator("compression")
    @classmethod
    def validate_compression(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        allowed = {"uncompressed", "snappy", "gzip", "zstd", "lz4", "brotli"}
        if normalized not in allowed:
            raise ValueError(
                "compression must be one of: uncompressed, snappy, gzip, zstd, lz4, brotli."
            )
        return normalized


class FullPipelineStartResponse(BaseModel):
    job_id: str
    status: str
    message: str


class FullPipelineStatusResponse(BaseModel):
    job_id: str
    status: str
    message: str
    current_phase: str = "queued"
    # CSV→Parquet progress
    parquet_processed_files: int = 0
    parquet_total_files: int = 0
    parquet_skipped_files: int = 0
    parquet_skipped_details: list[str] = []
    parquet_current_file: str | None = None
    parquet_output_path: str | None = None
    total_input_rows: int = 0
    total_output_rows: int = 0
    # Build DuckDB progress
    build_progress_percent: int = 0
    build_output_path: str | None = None
    parquet_input_rows: int | None = None
    table_rows: int | None = None
    # Overall
    overall_progress_percent: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    row_audit: list[FileRowAudit] = []
    row_audit_truncated: bool = False
    reconciliation: RowReconciliation = RowReconciliation()
    data_quality: str = "ok"  # ok | warning | loss

