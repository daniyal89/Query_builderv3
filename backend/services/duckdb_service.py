"""
duckdb_service.py — Manages DuckDB connection lifecycle.

Provides connect, disconnect, execute, and schema-introspection methods.
Thread safety is handled via a threading.Lock since DuckDB connections
are not safe to share across threads.
"""

import threading
from pathlib import Path
from typing import Any, Optional

import duckdb

from backend.models.schema import TableMetadata, ColumnDetail


class DuckDBService:
    """Singleton service managing a single DuckDB connection.

    Attributes:
        _conn: The active duckdb.DuckDBPyConnection or None.
        _db_path: Path to the currently connected .duckdb file.
        _lock: Threading lock guarding all connection operations.
    """

    _conn: Optional[duckdb.DuckDBPyConnection]
    _db_path: Optional[Path]
    _lock: threading.Lock

    def __init__(self) -> None:
        """Initialize the service with no active connection."""
        self._conn = None
        self._db_path = None
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        """Return True if a DuckDB connection is currently open."""
        return self._conn is not None

    def connect(self, db_path: str) -> int:
        """Open a connection to the specified DuckDB file.

        If a connection is already active, it is closed first before
        opening the new one.

        Args:
            db_path: Absolute filesystem path to the .duckdb file.
                     If the file does not exist, DuckDB will create it.

        Returns:
            Number of user tables found in the database.

        Raises:
            FileNotFoundError: If the parent directory does not exist.
            ValueError: If the path is empty or not a valid string.
            RuntimeError: If DuckDB fails to open the file.
        """
        if not db_path or not db_path.strip():
            raise ValueError("Database path cannot be empty.")

        resolved = Path(db_path).resolve()

        # Ensure the parent directory exists (DuckDB can create the file,
        # but the directory must already be there)
        if not resolved.parent.exists():
            raise FileNotFoundError(
                f"Parent directory does not exist: {resolved.parent}"
            )

        with self._lock:
            # Close any existing connection first
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass  # Swallow errors on stale connections

            try:
                self._conn = duckdb.connect(str(resolved), read_only=False)
                self._db_path = resolved
            except duckdb.Error as exc:
                self._conn = None
                self._db_path = None
                raise RuntimeError(f"Failed to open DuckDB database: {exc}") from exc

            # Return the number of user tables
            tables = self._fetch_table_names()
            return len(tables)

    def disconnect(self) -> None:
        """Close the active DuckDB connection and reset state."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
                self._db_path = None

    def list_tables(self) -> list[TableMetadata]:
        """Return metadata for all user-defined tables in the database.

        Queries DuckDB's information_schema for table names, then for each
        table fetches its columns and an approximate row count.

        Returns:
            List of TableMetadata with name, columns, and row_count.

        Raises:
            RuntimeError: If no connection is active.
        """
        self._ensure_connected()

        with self._lock:
            table_names = self._fetch_table_names()
            result: list[TableMetadata] = []

            for name in table_names:
                columns = self._fetch_columns_unlocked(name)
                row_count = self._fetch_row_count_unlocked(name)
                result.append(
                    TableMetadata(
                        table_name=name,
                        columns=columns,
                        row_count=row_count,
                    )
                )

            return result

    def get_columns(self, table_name: str) -> list[ColumnDetail]:
        """Return column details for a specific table.

        Args:
            table_name: Name of the table to introspect.

        Returns:
            Ordered list of ColumnDetail objects.

        Raises:
            RuntimeError: If no connection is active.
            ValueError: If the table does not exist.
        """
        self._ensure_connected()

        with self._lock:
            # Verify the table exists
            existing = self._fetch_table_names()
            if table_name not in existing:
                raise ValueError(f"Table '{table_name}' does not exist.")
            return self._fetch_columns_unlocked(table_name)

    def execute(
        self, sql: str, params: Optional[list[Any]] = None
    ) -> tuple[list[str], list[list[Any]], int]:
        """Execute a SQL statement and return the result set.

        Args:
            sql: The SQL query string (may include ? placeholders).
            params: Optional list of parameter values for placeholders.

        Returns:
            Tuple of (column_names, rows, total_count).

        Raises:
            RuntimeError: If no connection is active.
            duckdb.Error: If the SQL is invalid.
        """
        self._ensure_connected()

        with self._lock:
            assert self._conn is not None  # guarded by _ensure_connected

            if params:
                result = self._conn.execute(sql, params)
            else:
                result = self._conn.execute(sql)

            columns = [desc[0] for desc in result.description] if result.description else []
            rows = result.fetchall()

            return columns, [list(row) for row in rows], len(rows)

    # ──────────────────────────── Private helpers ────────────────────────────

    def _ensure_connected(self) -> None:
        """Raise RuntimeError if no database is connected."""
        if self._conn is None:
            raise RuntimeError("No database connected. Call connect() first.")

    def _fetch_table_names(self) -> list[str]:
        """Return a list of user table names from the current connection.

        Must be called while holding self._lock.
        """
        assert self._conn is not None
        result = self._conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
        return [row[0] for row in result.fetchall()]

    def _fetch_columns_unlocked(self, table_name: str) -> list[ColumnDetail]:
        """Return column details for a table.

        Must be called while holding self._lock.
        """
        assert self._conn is not None
        result = self._conn.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = ? "
            "ORDER BY ordinal_position",
            [table_name],
        )
        return [
            ColumnDetail(
                name=row[0],
                dtype=row[1],
                nullable=(row[2] == "YES"),
            )
            for row in result.fetchall()
        ]

    def _fetch_row_count_unlocked(self, table_name: str) -> int:
        """Return the row count for a table.

        Uses a direct COUNT(*) which is fast on DuckDB due to its
        columnar storage zone-map optimizations.

        Must be called while holding self._lock.
        """
        assert self._conn is not None
        # Use identifier quoting to prevent SQL injection on table names
        result = self._conn.execute(
            f'SELECT COUNT(*) FROM "{table_name}"'
        )
        count = result.fetchone()
        return count[0] if count else 0
