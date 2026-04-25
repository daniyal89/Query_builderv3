"""Capture one-time sample rows after database connections."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SampleSnapshotService:
    """Stores one-time sample snapshots (up to 1000 rows) for DuckDB and Marcadose."""

    ROOT_DIR = Path("samples")
    DUCKDB_DIR = ROOT_DIR / "duckdb"
    ORACLE_DIR = ROOT_DIR / "marcadose"
    SAMPLE_LIMIT = 1000

    @staticmethod
    def _slug(value: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
        return safe.strip("_") or "default"

    @staticmethod
    def _write_csv(path: Path, columns: list[str], rows: list[list[Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows(rows)

    @staticmethod
    def _write_meta(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    @classmethod
    def capture_duckdb_once(cls, conn: Any, db_path: Path) -> None:
        db_slug = cls._slug(db_path.stem)
        sample_csv = cls.DUCKDB_DIR / f"{db_slug}_sample.csv"
        sample_meta = cls.DUCKDB_DIR / f"{db_slug}_sample.meta.json"
        if sample_csv.exists():
            return

        table_rows = conn.execute(
            "SELECT table_name, table_type FROM information_schema.tables "
            "WHERE table_schema='main' AND table_type IN ('BASE TABLE','VIEW') "
            "ORDER BY CASE WHEN table_type='BASE TABLE' THEN 0 ELSE 1 END, table_name LIMIT 1"
        ).fetchall()
        if not table_rows:
            return

        table_name = table_rows[0][0]
        quoted = f'"{table_name.replace(chr(34), chr(34) * 2)}"'
        result = conn.execute(f"SELECT * FROM {quoted} LIMIT {cls.SAMPLE_LIMIT}")
        columns = [desc[0] for desc in (result.description or [])]
        rows = [list(row) for row in result.fetchall()]
        if not columns:
            return

        cls._write_csv(sample_csv, columns, rows)
        cls._write_meta(
            sample_meta,
            {
                "engine": "duckdb",
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "db_path": str(db_path),
                "source_table": table_name,
                "row_limit": cls.SAMPLE_LIMIT,
                "rows_saved": len(rows),
            },
        )

    @classmethod
    def capture_oracle_once(cls, conn: Any, schema_name: str, connection_label: str, object_names: list[str]) -> None:
        target_slug = cls._slug(f"{schema_name}_{connection_label}")
        sample_csv = cls.ORACLE_DIR / f"{target_slug}_sample.csv"
        sample_meta = cls.ORACLE_DIR / f"{target_slug}_sample.meta.json"
        if sample_csv.exists() or not object_names:
            return

        source_object = object_names[0]
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT * FROM {source_object} FETCH FIRST {cls.SAMPLE_LIMIT} ROWS ONLY")
            columns = [desc[0] for desc in (cursor.description or [])]
            rows = [list(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

        if not columns:
            return

        cls._write_csv(sample_csv, columns, rows)
        cls._write_meta(
            sample_meta,
            {
                "engine": "oracle",
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "schema_name": schema_name,
                "connection_label": connection_label,
                "source_object": source_object,
                "row_limit": cls.SAMPLE_LIMIT,
                "rows_saved": len(rows),
            },
        )
