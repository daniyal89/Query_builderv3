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


class CsvToParquetRequest(BaseModel):
    input_path: str = Field(..., description="Input CSV path or glob pattern.")
    output_path: str = Field(
        ...,
        description="Output parquet folder path (or explicit .parquet file path for single-file mode).",
    )
    compression: str = Field(default="zstd", description="Parquet compression codec.")
    hir_file: str | None = Field(default=None, description="Optional HIR Excel file path for enrichment join.")
    supp_mapper_file: str | None = Field(default=None, description="Optional suppMapper Excel file path for enrichment join.")

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


class SidebarToolResponse(BaseModel):
    status: str = "ok"
    message: str
    output_path: str | None = None


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
    current_file: str | None = None
    output_path: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


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
