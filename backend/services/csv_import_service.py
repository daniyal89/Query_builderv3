"""
csv_import_service.py â€” Handles CSV parsing, column mapping, and DuckDB insertion.

Manages the full import pipeline: read uploaded CSV, apply user-defined
column re-mapping, coerce types, and perform staged bulk-insert into
the target DuckDB table.
"""

from pathlib import Path, PurePath
import tempfile
import uuid

import pandas as pd

from backend.models.importer import ColumnMapping, ImportResult


class CSVImportService:
    """Manages the CSV-to-DuckDB import workflow."""

    TEMP_DIR = Path(tempfile.gettempdir())

    @staticmethod
    def _resolve_temp_path(file_id: str) -> Path:
        normalized = (file_id or "").strip()
        pure = PurePath(normalized)
        if not normalized or pure.is_absolute() or pure.name != normalized or any(part == ".." for part in pure.parts):
            raise ValueError("Invalid file_id.")
        return CSVImportService.TEMP_DIR / normalized

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return f'"{identifier.replace(chr(34), chr(34) * 2)}"'

    @staticmethod
    def save_temp_file(file_bytes: bytes, filename: str) -> str:
        safe_filename = Path(filename or "upload.csv").name or "upload.csv"
        file_id = f"{uuid.uuid4().hex}_{safe_filename}"
        path = CSVImportService._resolve_temp_path(file_id)
        path.write_bytes(file_bytes)
        return file_id

    @staticmethod
    def parse_headers(file_id: str) -> list[str]:
        path = CSVImportService._resolve_temp_path(file_id)
        df = pd.read_csv(path, nrows=0)
        return list(df.columns)

    @staticmethod
    def preview_rows(file_id: str, max_rows: int = 10) -> list[list[str]]:
        path = CSVImportService._resolve_temp_path(file_id)
        df = pd.read_csv(path, nrows=max_rows).fillna("")
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
            path = CSVImportService._resolve_temp_path(file_id)
            df = pd.read_csv(path)

            cols_to_skip = [mapping.csv_column for mapping in column_map if mapping.skip]
            df.drop(columns=[column for column in cols_to_skip if column in df.columns], inplace=True)

            rename_dict = {
                mapping.csv_column: mapping.db_column
                for mapping in column_map
                if not mapping.skip and mapping.csv_column != mapping.db_column
            }
            df.rename(columns=rename_dict, inplace=True)

            rows_inserted = len(df)
            target_table_sql = CSVImportService._quote_identifier(target_table)

            db_conn.register("temp_df", df)
            try:
                db_conn.execute(f"SELECT * FROM {target_table_sql} LIMIT 1")
                db_conn.execute(f"INSERT INTO {target_table_sql} SELECT * FROM temp_df")
            except Exception:
                if create_if_missing:
                    db_conn.execute(f"CREATE TABLE {target_table_sql} AS SELECT * FROM temp_df")
                else:
                    return ImportResult(
                        rows_inserted=0,
                        rows_skipped=rows_inserted,
                        errors=["Target table does not exist."],
                        target_table=target_table,
                    )
            finally:
                try:
                    db_conn.unregister("temp_df")
                except Exception:
                    pass

            path.unlink(missing_ok=True)

            return ImportResult(
                rows_inserted=rows_inserted,
                rows_skipped=0,
                errors=[],
                target_table=target_table,
            )
        except Exception as exc:
            return ImportResult(
                rows_inserted=0,
                rows_skipped=0,
                errors=[str(exc)],
                target_table=target_table,
            )
