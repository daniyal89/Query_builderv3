"""
duckdb_service.py — Manages DuckDB connection lifecycle.

Provides connect, disconnect, execute, and schema-introspection methods.
Thread safety is handled via a threading.Lock since DuckDB connections
are not safe to share across threads.
"""

import os
import re
import threading
from pathlib import Path
from typing import Any, Optional

import duckdb

from backend.models.local_object import FileObjectRequest
from backend.models.schema import TableMetadata, ColumnDetail


VALID_OBJECT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SUPPORTED_SOURCE_EXTENSIONS = {".csv", ".tsv", ".xlsx"}


class DuckDBService:
    """Singleton service managing a single DuckDB connection."""

    _conn: Optional[duckdb.DuckDBPyConnection]
    _db_path: Optional[Path]
    _lock: threading.Lock

    def __init__(self) -> None:
        self._conn = None
        self._db_path = None
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    def _normalize_user_path(self, raw_path: str) -> Path:
        value = (raw_path or "").strip()
        if not value:
            raise ValueError("Path cannot be empty.")
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1].strip()
        value = os.path.expandvars(os.path.expanduser(value))
        return Path(value)

    def connect(self, db_path: str) -> int:
        if not db_path or not db_path.strip():
            raise ValueError("Database path cannot be empty.")

        path_obj = self._normalize_user_path(db_path)
        resolved = path_obj.resolve() if path_obj.is_absolute() else (Path.cwd() / path_obj).resolve()

        if not resolved.parent.exists():
            raise FileNotFoundError(f"Parent directory does not exist: {resolved.parent}")

        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass

            try:
                self._conn = duckdb.connect(str(resolved), read_only=False)
                self._db_path = resolved
            except duckdb.Error as exc:
                self._conn = None
                self._db_path = None
                raise RuntimeError(f"Failed to open DuckDB database: {exc}") from exc

            tables = self._fetch_table_entries_unlocked()
            return len(tables)

    def disconnect(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
                self._db_path = None

    def list_tables(self) -> list[TableMetadata]:
        self._ensure_connected()

        with self._lock:
            table_entries = self._fetch_table_entries_unlocked()
            result: list[TableMetadata] = []

            for name, table_type in table_entries:
                columns = self._fetch_columns_unlocked(name)
                row_count = self._fetch_row_count_unlocked(name) if table_type == "BASE TABLE" else 0
                result.append(TableMetadata(table_name=name, columns=columns, row_count=row_count))

            return result

    def get_columns(self, table_name: str) -> list[ColumnDetail]:
        self._ensure_connected()

        with self._lock:
            existing = self._fetch_table_names()
            if table_name not in existing:
                raise ValueError(f"Table '{table_name}' does not exist.")
            return self._fetch_columns_unlocked(table_name)

    def execute(self, sql: str, params: Optional[list[Any]] = None) -> tuple[list[str], list[list[Any]], int]:
        self._ensure_connected()

        with self._lock:
            assert self._conn is not None
            result = self._conn.execute(sql, params) if params else self._conn.execute(sql)
            columns = [desc[0] for desc in result.description] if result.description else []
            rows = result.fetchall()
            return columns, [list(row) for row in rows], len(rows)

    def create_object_from_file(self, payload: FileObjectRequest) -> TableMetadata:
        self._ensure_connected()
        object_name = payload.object_name.strip()
        if not VALID_OBJECT_NAME.fullmatch(object_name):
            raise ValueError(
                "Object name must start with a letter/underscore and contain only letters, numbers, and underscores."
            )

        path_obj = self._normalize_user_path(payload.file_path)
        source_path = path_obj.resolve() if path_obj.is_absolute() else (Path.cwd() / path_obj).resolve()
        if not source_path.exists() or not source_path.is_file():
            raise ValueError(f"Source file does not exist: {source_path}")

        extension = source_path.suffix.lower()
        if extension == ".xls":
            raise ValueError("DuckDB supports .xlsx files, but not legacy .xls files. Save as .xlsx or CSV first.")
        if extension not in SUPPORTED_SOURCE_EXTENSIONS:
            raise ValueError("Supported file types are .csv, .tsv, and .xlsx.")

        object_type = payload.object_type.upper()
        with self._lock:
            assert self._conn is not None
            existing = set(self._fetch_table_names())
            if object_name in existing and not payload.replace:
                raise ValueError(f"Local object '{object_name}' already exists. Enable Replace to overwrite it.")

            relation_sql = self._build_file_relation_sql(
                source_path=source_path,
                header=payload.header,
                sheet_name=payload.sheet_name,
            )
            object_sql = self._quote_identifier(object_name)
            if payload.replace:
                self._conn.execute(f"DROP VIEW IF EXISTS {object_sql}")
                self._conn.execute(f"DROP TABLE IF EXISTS {object_sql}")
            self._conn.execute(f"CREATE {object_type} {object_sql} AS SELECT * FROM {relation_sql}")

            columns = self._fetch_columns_unlocked(object_name)
            row_count = self._fetch_row_count_unlocked(object_name) if object_type == "TABLE" else 0
            return TableMetadata(table_name=object_name, columns=columns, row_count=row_count)

    def _ensure_connected(self) -> None:
        if self._conn is None:
            raise RuntimeError("No database connected. Call connect() first.")

    def _quote_identifier(self, identifier: str) -> str:
        return f'"{identifier.replace(chr(34), chr(34) * 2)}"'

    def _sql_string_literal(self, value: str) -> str:
        return f"'{value.replace(chr(39), chr(39) * 2)}'"

    def _fetch_table_entries_unlocked(self) -> list[tuple[str, str]]:
        assert self._conn is not None
        result = self._conn.execute(
            "SELECT table_name, table_type FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_type IN ('BASE TABLE', 'VIEW') "
            "ORDER BY table_name"
        )
        return [(row[0], row[1]) for row in result.fetchall()]

    def _fetch_table_names(self) -> list[str]:
        return [name for name, _ in self._fetch_table_entries_unlocked()]

    def _load_excel_extension_unlocked(self) -> None:
        assert self._conn is not None
        try:
            self._conn.execute("LOAD excel")
        except duckdb.Error:
            try:
                self._conn.execute("INSTALL excel")
                self._conn.execute("LOAD excel")
            except duckdb.Error as exc:
                raise RuntimeError(
                    "DuckDB could not load the excel extension required for .xlsx files. "
                    "Check internet access for extension install, or use CSV."
                ) from exc

    def _build_file_relation_sql(self, source_path: Path, header: bool, sheet_name: str | None) -> str:
        extension = source_path.suffix.lower()
        path_sql = self._sql_string_literal(str(source_path))
        header_sql = "true" if header else "false"

        if extension == ".csv":
            return f"read_csv_auto({path_sql}, header = {header_sql})"
        if extension == ".tsv":
            return f"read_csv_auto({path_sql}, delim = '\t', header = {header_sql})"
        if extension == ".xlsx":
            self._load_excel_extension_unlocked()
            options = [f"header = {header_sql}"]
            if sheet_name and sheet_name.strip():
                options.append(f"sheet = {self._sql_string_literal(sheet_name.strip())}")
            return f"read_xlsx({path_sql}, {', '.join(options)})"

        raise ValueError("Supported file types are .csv, .tsv, and .xlsx.")

    def _fetch_columns_unlocked(self, table_name: str) -> list[ColumnDetail]:
        assert self._conn is not None
        result = self._conn.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = ? "
            "ORDER BY ordinal_position",
            [table_name],
        )
        return [ColumnDetail(name=row[0], dtype=row[1], nullable=(row[2] == "YES")) for row in result.fetchall()]

    def _fetch_row_count_unlocked(self, table_name: str) -> int:
        assert self._conn is not None
        result = self._conn.execute(f"SELECT COUNT(*) FROM {self._quote_identifier(table_name)}")
        count = result.fetchone()
        return count[0] if count else 0
