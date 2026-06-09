"""
alter_db.py - Models for modifying local master tables.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AlterDbDerivedRequest(BaseModel):
    db_path: str = Field(..., description="Path to the local DuckDB database")
    table_name: str = Field(..., description="Name of the table to alter")
    new_column_name: str = Field(..., description="Name of the column to add")
    column_type: str = Field(..., description="Data type of the new column (e.g., VARCHAR, INTEGER)")
    sql_formula: str = Field(..., description="SQL formula to calculate the derived column value")

    model_config = ConfigDict(extra="forbid")


class AlterDbJoinRequest(BaseModel):
    db_path: str = Field(..., description="Path to the local DuckDB database")
    table_name: str = Field(..., description="Name of the table to alter")
    new_column_name: str = Field(..., description="Name of the column to add")
    column_type: str = Field(..., description="Data type of the new column (e.g., VARCHAR, INTEGER)")
    file_path: str = Field(..., description="Path to the CSV or XLSX file containing the new data")
    join_master_col: str = Field(..., description="Column name in the master table to join on")
    join_file_col: str = Field(..., description="Column name in the file to join on")
    value_file_col: str = Field(..., description="Column name in the file containing the value to pull")

    model_config = ConfigDict(extra="forbid")

class AlterDbDropRequest(BaseModel):
    db_path: str = Field(..., description="Path to the local DuckDB database")
    table_name: str = Field(..., description="Name of the table to alter")
    column_name: str = Field(..., description="Name of the column to drop")

    model_config = ConfigDict(extra="forbid")

class AlterDbJobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "cancelling", "cancelled", "completed", "failed"]
    message: str
    progress_percent: int = 0
    started_at: str | None = None
    finished_at: str | None = None
