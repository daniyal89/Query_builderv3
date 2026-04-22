"""
csv_import_service.py — Handles CSV parsing, column mapping, and DuckDB insertion.

Manages the full import pipeline: read uploaded CSV, apply user-defined
column re-mapping, coerce types, and perform staged bulk-insert into
the target DuckDB table.
"""

from pathlib import Path
from typing import BinaryIO

from backend.models.importer import ColumnMapping, ImportResult


import os
import tempfile
import uuid
from typing import BinaryIO
import pandas as pd

from backend.models.importer import ColumnMapping, ImportResult


class CSVImportService:
    """Manages the CSV-to-DuckDB import workflow."""

    @staticmethod
    def save_temp_file(file: BinaryIO, filename: str) -> str:
        file_id = f"{uuid.uuid4()}_{filename}"
        path = os.path.join(tempfile.gettempdir(), file_id)
        with open(path, "wb") as f:
            f.write(file.read())
        return file_id

    @staticmethod
    def parse_headers(file_id: str) -> list[str]:
        path = os.path.join(tempfile.gettempdir(), file_id)
        df = pd.read_csv(path, nrows=0)
        return list(df.columns)

    @staticmethod
    def preview_rows(file_id: str, max_rows: int = 10) -> list[list[str]]:
        path = os.path.join(tempfile.gettempdir(), file_id)
        df = pd.read_csv(path, nrows=max_rows).fillna("")
        # Return as list of string columns
        return [list(map(str, row)) for row in df.itertuples(index=False)]

    @staticmethod
    def import_csv(
        file_id: str,
        target_table: str,
        column_map: list[ColumnMapping],
        db_conn,
        create_if_missing: bool = True,
    ) -> ImportResult:
        try:
            path = os.path.join(tempfile.gettempdir(), file_id)
            df = pd.read_csv(path)
            
            # Identify columns to skip
            cols_to_skip = [m.csv_column for m in column_map if m.skip]
            df.drop(columns=[c for c in cols_to_skip if c in df.columns], inplace=True)
            
            # Identify columns to rename
            rename_dict = {m.csv_column: m.db_column for m in column_map if not m.skip and m.csv_column != m.db_column}
            df.rename(columns=rename_dict, inplace=True)
            
            rows_inserted = len(df)
            
            # Register using duckdb connection
            db_conn.register('temp_df', df)
            
            # Create or insert
            try:
                db_conn.execute(f"SELECT * FROM {target_table} LIMIT 1")
                # Table exists, append
                db_conn.execute(f"INSERT INTO {target_table} SELECT * FROM temp_df")
            except:
                if create_if_missing:
                    db_conn.execute(f"CREATE TABLE {target_table} AS SELECT * FROM temp_df")
                else:
                    return ImportResult(rows_inserted=0, rows_skipped=rows_inserted, errors=["Target table does not exist."], target_table=target_table)
            
            # cleanup
            os.remove(path)
            
            return ImportResult(
                rows_inserted=rows_inserted,
                rows_skipped=0,
                errors=[],
                target_table=target_table
            )
        except Exception as e:
            return ImportResult(
                rows_inserted=0,
                rows_skipped=0,
                errors=[str(e)],
                target_table=target_table
            )
