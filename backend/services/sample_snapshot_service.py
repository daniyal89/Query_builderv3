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
    PREFERRED_DISCOM = "DVVNL"

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
            "SELECT t.table_name, t.table_type, COUNT(c.column_name) AS column_count "
            "FROM information_schema.tables t "
            "LEFT JOIN information_schema.columns c "
            "ON c.table_schema = t.table_schema AND c.table_name = t.table_name "
            "WHERE t.table_schema='main' AND t.table_type IN ('BASE TABLE','VIEW') "
            "GROUP BY t.table_name, t.table_type "
            "ORDER BY "
            "CASE "
            "WHEN UPPER(t.table_name) LIKE '%MASTER%' AND UPPER(t.table_name) LIKE '%DVVNL%' THEN 0 "
            "WHEN UPPER(t.table_name) LIKE '%MASTER%' THEN 1 "
            "WHEN t.table_type='BASE TABLE' THEN 2 "
            "ELSE 3 END, "
            "column_count DESC, t.table_name "
            "LIMIT 1"
        ).fetchall()
        if not table_rows:
            return

        table_name = table_rows[0][0]
        column_count = int(table_rows[0][2] or 0)
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
                "source_column_count": column_count,
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

        column_counts = cls._oracle_column_counts(conn, object_names)
        source_object = cls._select_oracle_source_object(object_names, column_counts=column_counts)
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
                "source_column_count": int(column_counts.get(source_object.upper(), 0)),
                "row_limit": cls.SAMPLE_LIMIT,
                "rows_saved": len(rows),
            },
        )

    @classmethod
    def _oracle_column_counts(cls, conn: Any, object_names: list[str]) -> dict[str, int]:
        normalized = [name.strip() for name in object_names if name and name.strip()]
        pairs: list[tuple[str, str]] = []
        for qualified in normalized:
            if "." in qualified:
                owner, table = qualified.split(".", 1)
            else:
                owner, table = "", qualified
            pairs.append((owner.upper(), table.upper()))

        if not pairs:
            return {}

        binds: dict[str, str] = {}
        clauses: list[str] = []
        for index, (owner, table) in enumerate(pairs):
            owner_key = f"o{index}"
            table_key = f"t{index}"
            if owner:
                clauses.append(f"(owner = :{owner_key} AND table_name = :{table_key})")
                binds[owner_key] = owner
            else:
                clauses.append(f"(table_name = :{table_key})")
            binds[table_key] = table

        query = (
            "SELECT owner, table_name, COUNT(*) AS column_count "
            "FROM all_tab_columns "
            f"WHERE {' OR '.join(clauses)} "
            "GROUP BY owner, table_name"
        )
        cursor = conn.cursor()
        try:
            cursor.execute(query, binds)
            rows = cursor.fetchall()
        finally:
            cursor.close()

        counts: dict[str, int] = {}
        for owner, table_name, column_count in rows:
            key = f"{str(owner).upper()}.{str(table_name).upper()}"
            counts[key] = int(column_count or 0)
            counts[str(table_name).upper()] = int(column_count or 0)
        return counts

    @classmethod
    def _select_oracle_source_object(
        cls,
        object_names: list[str],
        column_counts: dict[str, int] | None = None,
    ) -> str:
        """
        Select only one representative Oracle object for sampling.
        Preference order:
        1) master table/view for preferred discom (e.g., DVVNL),
        2) any object containing MASTER,
        3) first object from list as safe fallback.
        """
        normalized = [name.strip() for name in object_names if name and name.strip()]
        if not normalized:
            return object_names[0]
        counts = {k.upper(): int(v) for k, v in (column_counts or {}).items()}

        def score(name: str) -> tuple[int, int, str]:
            upper = name.upper()
            if "MASTER" in upper and cls.PREFERRED_DISCOM in upper:
                rank = 0
            elif "MASTER" in upper:
                rank = 1
            else:
                rank = 2
            column_count = counts.get(upper, counts.get(upper.split(".")[-1], 0))
            return (rank, -column_count, upper)

        return sorted(normalized, key=score)[0]
