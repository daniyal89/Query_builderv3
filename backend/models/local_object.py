"""Models for local DuckDB object creation from files."""

from typing import Literal

from pydantic import BaseModel, Field

from backend.models.schema import TableMetadata


class FileObjectRequest(BaseModel):
    """Request to create a local DuckDB table or view from a file path."""

    file_path: str = Field(..., description="Absolute path to a local CSV/TSV/XLSX file.")
    object_name: str = Field(..., description="DuckDB table or view name to create in the main schema.")
    object_type: Literal["TABLE", "VIEW"] = Field(default="TABLE", description="Type of DuckDB object to create.")
    replace: bool = Field(default=False, description="Replace the object if it already exists.")
    header: bool = Field(default=True, description="Treat the first row as headers.")
    sheet_name: str | None = Field(default=None, description="Optional worksheet name for XLSX files.")


class FileObjectResponse(BaseModel):
    """Response after creating a local DuckDB file-backed object."""

    status: str = Field(..., description="Creation status.")
    message: str = Field(default="", description="Human-readable result message.")
    object_name: str = Field(..., description="Created table/view name.")
    object_type: Literal["TABLE", "VIEW"] = Field(..., description="Created object type.")
    table: TableMetadata = Field(..., description="Schema metadata for the created object.")
