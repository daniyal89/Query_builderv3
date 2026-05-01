"""
connection.py â€” Pydantic schemas for local DuckDB and Marcadose Oracle connections.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.utils.path_safety import sanitize_local_path_input


EngineName = Literal["duckdb", "oracle"]


class ConnectionRequest(BaseModel):
    """Incoming payload to establish a DuckDB connection."""

    db_path: str = Field(
        ...,
        description="Absolute filesystem path to the target .duckdb file.",
        examples=[r"C:\data\analytics.duckdb"],
    )

    @field_validator("db_path")
    @classmethod
    def validate_db_path(cls, value: str) -> str:
        return sanitize_local_path_input(value, "db_path")


class ConnectionResponse(BaseModel):
    """Response after a DuckDB connection attempt."""

    status: str = Field(
        ...,
        description="Connection outcome: 'connected' or 'error'.",
        examples=["connected"],
    )
    db_path: str = Field(..., description="Echo of the resolved database path.")
    tables_count: int = Field(..., description="Number of user tables found in the database.", ge=0)
    message: str = Field(default="", description="Human-readable status or error message.")


class OracleConnectionRequest(BaseModel):
    """Incoming payload to establish a Marcadose Oracle connection."""

    host: str = Field(..., description="Oracle database host name or IP.")
    port: int = Field(default=1521, description="Listener port.", ge=1, le=65535)
    sid: str = Field(..., description="Oracle SID for the Marcadose database.")
    username: str = Field(..., description="Read-only Oracle username.")
    password: str = Field(..., description="Oracle password.")


class OracleConnectionResponse(BaseModel):
    """Response after an Oracle connection attempt."""

    status: str = Field(..., description="Connection outcome.")
    tables_count: int = Field(..., description="Number of discovered tables/views.", ge=0)
    message: str = Field(default="", description="Human-readable status or error message.")
    schema_name: str = Field(..., description="Connected Oracle schema name.")
