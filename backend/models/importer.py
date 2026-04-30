"""
importer.py — Pydantic schemas for the CSV import pipeline.

Defines the column-mapping payload and import result used by
POST /api/upload-csv.
"""

import re
from pathlib import PurePath

from pydantic import BaseModel, Field
from pydantic import field_validator


VALID_TARGET_TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ColumnMapping(BaseModel):
    """Maps a single CSV column to a target DuckDB column."""

    csv_column: str = Field(..., description="Header name from the uploaded CSV file.")
    db_column: str = Field(..., description="Target column name in the DuckDB table.")
    skip: bool = Field(default=False, description="If true, this CSV column is ignored during import.")


class CSVMappingPayload(BaseModel):
    """Payload submitted to finalize a CSV import with column mappings."""

    file_id: str = Field(..., description="Temporary file identifier from the initial upload step.")
    target_table: str = Field(..., description="DuckDB table to insert data into.")
    column_map: list[ColumnMapping] = Field(
        ...,
        description="Ordered list of column mapping directives.",
    )
    create_table_if_missing: bool = Field(
        default=False,
        description="If true, auto-create the target table from CSV schema.",
    )

    @field_validator("file_id")
    @classmethod
    def validate_file_id(cls, value: str) -> str:
        normalized = (value or "").strip()
        pure = PurePath(normalized)
        if not normalized or pure.is_absolute() or pure.name != normalized or any(part == ".." for part in pure.parts):
            raise ValueError("file_id is invalid.")
        return normalized

    @field_validator("target_table")
    @classmethod
    def validate_target_table(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not VALID_TARGET_TABLE.fullmatch(normalized):
            raise ValueError(
                "target_table must start with a letter or underscore and contain only letters, numbers, and underscores."
            )
        return normalized


class ImportResult(BaseModel):
    """Outcome summary of a CSV import operation."""

    rows_inserted: int = Field(..., description="Number of rows successfully inserted.", ge=0)
    rows_skipped: int = Field(default=0, description="Number of rows skipped due to errors.", ge=0)
    errors: list[str] = Field(
        default_factory=list,
        description="Human-readable error messages for failed rows.",
    )
    target_table: str = Field(..., description="Table the data was imported into.")
