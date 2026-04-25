"""Models for local DuckDB object creation from files."""

from typing import Literal

from pydantic import BaseModel, Field
from pydantic import field_validator

from backend.models.schema import TableMetadata
from backend.utils.path_safety import sanitize_local_path_input


class FileObjectRequest(BaseModel):
    """Request to create a local DuckDB table or view from a file path."""

    file_path: str = Field(..., description="Absolute path to a local CSV/TSV/XLSX file.")
    object_name: str = Field(..., description="DuckDB table or view name to create in the main schema.")
    object_type: Literal["TABLE", "VIEW"] = Field(default="TABLE", description="Type of DuckDB object to create.")
    replace: bool = Field(default=False, description="Replace the object if it already exists.")
    header: bool = Field(default=True, description="Treat the first row as headers.")
    sheet_name: str | None = Field(default=None, description="Optional worksheet name for XLSX files.")
    header_names: list[str] = Field(
        default_factory=list,
        description="Optional custom output column names in source-column order.",
    )

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        return sanitize_local_path_input(value, "file_path")


class FileObjectResponse(BaseModel):
    """Response after creating a local DuckDB file-backed object."""

    status: str = Field(..., description="Creation status.")
    message: str = Field(default="", description="Human-readable result message.")
    object_name: str = Field(..., description="Created table/view name.")
    object_type: Literal["TABLE", "VIEW"] = Field(..., description="Created object type.")
    table: TableMetadata = Field(..., description="Schema metadata for the created object.")


class FilePreviewRequest(BaseModel):
    """Request to preview first rows before creating local object."""

    file_path: str = Field(..., description="Absolute path to a local CSV/TSV/XLSX file.")
    header: bool = Field(default=True, description="Treat the first row as headers.")
    sheet_name: str | None = Field(default=None, description="Optional worksheet name for XLSX files.")
    limit_rows: int = Field(default=10, ge=1, le=50, description="Preview row count.")

    @field_validator("file_path")
    @classmethod
    def validate_preview_file_path(cls, value: str) -> str:
        return sanitize_local_path_input(value, "file_path")


class FilePreviewResponse(BaseModel):
    """Preview response for local file object creation."""

    columns: list[str] = Field(default_factory=list)
    rows: list[list[str | int | float | None]] = Field(default_factory=list)
