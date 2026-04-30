"""
merge.py — Pydantic schemas for the multi-sheet merge and enrichment pipeline.

Covers the three-phase flow defined in HANDOVER.md §8 (Strict Business Rules):
  1. Upload Sheets  → detect columns across files
  2. Merge Sheets   → resolve column conflicts via ConflictResolutionMap
  3. Enrich Data    → join against the Master Table on composite key

Also includes the local folder merge flow used by the sidebar import page.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ─────────────────────────── Phase 1: Upload Sheets ───────────────────────────


class DetectedColumn(BaseModel):
    """A column discovered in an uploaded sheet."""

    name: str = Field(..., description="Original column header as it appears in the file.")
    source_file: str = Field(..., description="Filename this column was detected in.")
    source_sheet: str = Field(default="Sheet1", description="Sheet/tab name within the file.")
    sample_values: list[str] = Field(
        default_factory=list,
        description="Up to 5 sample values from this column for user preview.",
    )


class UploadSheetsResponse(BaseModel):
    """Response from POST /api/upload-sheets after parsing all uploaded files."""

    file_ids: list[str] = Field(
        ..., description="Temporary identifiers for each uploaded file (used in subsequent steps)."
    )
    detected_columns: list[DetectedColumn] = Field(
        ..., description="Flat list of every column found across all uploaded sheets."
    )
    conflicts: list[str] = Field(
        default_factory=list,
        description="Column names that appear in multiple files with potentially different meanings.",
    )



# ─────────────────────── Sidebar folder merge flow ───────────────────────────


class FolderMergeRequest(BaseModel):
    """Request payload for local recursive folder merge."""

    source_folder: str = Field(..., description="Folder containing files to merge.")
    output_path: str = Field(..., description="Absolute path for the merged output file.")
    include_subfolders: bool = Field(
        default=True,
        description="Whether to scan all nested subfolders recursively.",
    )


class FolderMergeResponse(BaseModel):
    """Response for the local folder merge operation."""

    output_path: str = Field(..., description="Absolute path of the saved merged file.")
    output_format: Literal["csv", "xlsx"] = Field(..., description="Saved output format.")
    total_files: int = Field(..., ge=0, description="Number of source files discovered.")
    merged_items: int = Field(
        ..., ge=0, description="Number of merged datasets, including individual Excel sheets."
    )
    total_rows: int = Field(..., ge=0, description="Total rows written to the merged output.")
    total_columns: int = Field(..., ge=0, description="Total columns written to the merged output.")


# ─────────────────────── Phase 3: Enrich Data ────────────────────────────────


class EnrichmentRequest(BaseModel):
    """Payload for POST /api/enrich-data — specifies what to fetch from the Master Table."""

    merge_id: str = Field(..., description="Identifier of the merged dataset from the merge step.")
    master_table: str = Field(..., description="Name of the DuckDB Master Table to join against.")
    composite_key: Literal["Acc_id+DISCOM", "Acc_id+DIV_CODE"] = Field(
        ..., description="Which composite key to use for the join."
    )
    fetch_columns: list[str] = Field(
        ...,
        description="Column names from the Master Table to fetch and append to the merged data.",
        min_length=1,
    )
    output_format: Literal["xlsx", "csv"] = Field(
        default="xlsx",
        description="Desired format for the downloadable output file.",
    )


class EnrichmentResponse(BaseModel):
    """Response from POST /api/enrich-data after the join is complete."""

    download_url: str = Field(..., description="Relative URL to download the enriched output file.")
    total_rows: int = Field(..., description="Total rows in the output file.", ge=0)
    matched_rows: int = Field(..., description="Rows that found a match in the Master Table.", ge=0)
    unmatched_rows: int = Field(..., description="Rows with no Master Table match.", ge=0)
    output_format: Literal["xlsx", "csv"] = Field(..., description="Format of the output file.")
