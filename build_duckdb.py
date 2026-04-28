#!/usr/bin/env python3
"""Create DuckDB table/view from CSV, GZ CSV, or Parquet files."""

from __future__ import annotations

import argparse
import glob
from pathlib import Path
import duckdb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a DuckDB table/view for older/current month files (csv/.gz/.parquet)."
    )
    parser.add_argument("--db", required=True, help="DuckDB file path to create/update.")
    parser.add_argument("--input", required=True, help="Input file path or glob pattern.")
    parser.add_argument("--object-name", required=True, help="DuckDB object name.")
    parser.add_argument("--object-type", choices=("TABLE", "VIEW"), default="TABLE")
    parser.add_argument("--replace", action="store_true", help="Replace existing object if it exists.")
    parser.add_argument("--month-label", default="", help="Optional label (example: MAR_2026) for logs.")
    return parser.parse_args()


def build_relation_sql(input_path: str) -> str:
    sample = input_path.lower()
    if sample.endswith(".parquet") or ".parquet" in sample:
        return f"read_parquet('{input_path}')"
    if (
        sample.endswith(".csv")
        or ".csv" in sample
        or sample.endswith(".tsv")
        or ".tsv" in sample
        or sample.endswith(".gz")
        or ".gz" in sample
    ):
        return f"read_csv_auto('{input_path}', union_by_name = true, filename = true)"

    matches = glob.glob(input_path, recursive=True)
    if matches:
        first = matches[0].lower()
        if first.endswith(".parquet"):
            return f"read_parquet('{input_path}')"
        if (
            first.endswith(".csv")
            or first.endswith(".csv.gz")
            or first.endswith(".tsv")
            or first.endswith(".gz")
        ):
            return f"read_csv_auto('{input_path}', union_by_name = true, filename = true)"

    return f"read_csv_auto('{input_path}', union_by_name = true, filename = true)"


def drop_existing_object(conn: duckdb.DuckDBPyConnection, object_name: str) -> None:
    existing = conn.execute(
        "SELECT table_type FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_name = ? LIMIT 1",
        [object_name],
    ).fetchone()
    if not existing:
        return

    object_sql = f'"{object_name.replace(chr(34), chr(34) * 2)}"'
    if existing[0] == "VIEW":
        conn.execute(f"DROP VIEW {object_sql}")
    else:
        conn.execute(f"DROP TABLE {object_sql}")


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(str(db_path))
    object_name = args.object_name.strip().replace('"', '""')
    object_sql = f'"{object_name}"'

    if args.replace:
        drop_existing_object(conn, args.object_name)

    relation_sql = build_relation_sql(args.input)
    conn.execute(f"CREATE {args.object_type} {object_sql} AS SELECT * FROM {relation_sql}")

    month_text = f" for {args.month_label}" if args.month_label else ""
    print(f"Created {args.object_type} {args.object_name}{month_text} in {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
