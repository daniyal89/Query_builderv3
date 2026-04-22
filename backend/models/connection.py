"""
connection.py — Pydantic schemas for the DuckDB connection workflow.

Used by POST /api/duckdb/connect to validate the incoming file path
and structure the response confirming connection status.
"""

from pydantic import BaseModel, Field


class ConnectionRequest(BaseModel):
    """Incoming payload to establish a DuckDB connection."""

    db_path: str = Field(
        ...,
        description="Absolute filesystem path to the target .duckdb file.",
        examples=[r"C:\data\analytics.duckdb"],
    )


class ConnectionResponse(BaseModel):
    """Response after a connection attempt."""

    status: str = Field(
        ...,
        description="Connection outcome: 'connected' or 'error'.",
        examples=["connected"],
    )
    db_path: str = Field(
        ...,
        description="Echo of the resolved database path.",
    )
    tables_count: int = Field(
        ...,
        description="Number of user tables found in the database.",
        ge=0,
    )
    message: str = Field(
        default="",
        description="Human-readable status or error message.",
    )
