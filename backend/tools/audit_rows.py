"""Read-only row audit: source CSVs → Parquet → DuckDB table.

Answers "how many rows did this month actually lose, and where?" for data that
was already built, without touching anything. Use it to decide which past months
need reprocessing now that the pipeline accounts for every row.

Counting is cheap: parquet totals come from the file footers, and the source
count is a single DuckDB scan per file.

Example::

    python -m backend.tools.audit_rows \\
        --sources "D:/master/FEB_2026" \\
        --parquet "D:/parquet/FEB_2026" \\
        --db monthly.duckdb --table Master_0226
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import duckdb

from backend.services.sidebar_tools_service import (
    QUARANTINE_DIR_NAME,
    _classify_input_file,
    _resolve_csv_parquet_read_sql,
)

CSV_SUFFIXES = ("**/*.csv.gz", "**/*.gz", "**/*.csv", "**/*.tsv", "**/*.txt")


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _find_source_files(root: Path) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in CSV_SUFFIXES:
        for item in glob.glob(str((root / pattern).as_posix()), recursive=True):
            path = Path(item)
            if path.is_file() and QUARANTINE_DIR_NAME not in path.parts:
                found[str(path.resolve())] = path
    return sorted(found.values(), key=str)


def _find_parquet_files(root: Path) -> list[Path]:
    files = []
    for item in glob.glob(str((root / "**/*.parquet").as_posix()), recursive=True):
        usable, _reason = _classify_input_file(item)
        if usable:
            files.append(Path(item))
    return sorted(files, key=str)


def _count_source_rows(conn: duckdb.DuckDBPyConnection, path: Path) -> int | None:
    try:
        relation = _resolve_csv_parquet_read_sql(str(path))
        row = conn.execute(f"SELECT count(*) FROM {relation}").fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return None


def _count_parquet_rows(conn: duckdb.DuckDBPyConnection, path: Path) -> int | None:
    try:
        row = conn.execute(
            f"SELECT sum(num_rows) FROM parquet_file_metadata({_sql_literal(str(path))})"
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else None
    except Exception:
        return None


def _stem_key(path: Path) -> str:
    """Match a source file to its parquet by name, ignoring the extensions."""
    name = path.name
    for suffix in (".csv.gz", ".csv", ".tsv", ".txt", ".gz", ".parquet"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)].lower()
    return path.stem.lower()


def audit(
    sources: Path | None,
    parquet_root: Path | None,
    db_path: Path | None,
    table: str | None,
) -> int:
    conn = duckdb.connect()
    conn.execute("PRAGMA disable_progress_bar")

    source_rows_total = 0
    parquet_rows_total = 0
    per_file: list[tuple[str, int | None, int | None]] = []

    source_counts: dict[str, tuple[Path, int | None]] = {}
    if sources:
        source_files = _find_source_files(sources)
        print(f"Scanning {len(source_files)} source file(s) under {sources}...", file=sys.stderr)
        for path in source_files:
            count = _count_source_rows(conn, path)
            source_counts[_stem_key(path)] = (path, count)
            source_rows_total += count or 0

    parquet_counts: dict[str, tuple[Path, int | None]] = {}
    if parquet_root:
        parquet_files = _find_parquet_files(parquet_root)
        print(f"Reading {len(parquet_files)} parquet footer(s) under {parquet_root}...", file=sys.stderr)
        for path in parquet_files:
            count = _count_parquet_rows(conn, path)
            parquet_counts[_stem_key(path)] = (path, count)
            parquet_rows_total += count or 0

    quarantined_total = 0
    if parquet_root:
        for item in glob.glob(str((parquet_root / f"**/{QUARANTINE_DIR_NAME}/*.parquet").as_posix()), recursive=True):
            quarantined_total += _count_parquet_rows(conn, Path(item)) or 0

    table_rows: int | None = None
    if db_path and table:
        try:
            with duckdb.connect(str(db_path), read_only=True) as db_conn:
                row = db_conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()
                table_rows = int(row[0]) if row else 0
        except Exception as exc:
            print(f"Could not read {table} from {db_path}: {exc}", file=sys.stderr)

    # ── Report ───────────────────────────────────────────────────────────────
    print()
    if sources:
        print(f"source   {source_rows_total:>14,}")
    if parquet_root:
        delta = parquet_rows_total - source_rows_total if sources else 0
        suffix = f"  ({delta:+,})" if sources else ""
        print(f"parquet  {parquet_rows_total:>14,}{suffix}")
        if quarantined_total:
            print(f"  of which quarantined elsewhere: {quarantined_total:,}")
    if table_rows is not None:
        base = parquet_rows_total if parquet_root else source_rows_total
        delta = table_rows - base if base else 0
        suffix = f"  ({delta:+,})" if base else ""
        print(f"table    {table_rows:>14,}{suffix}")

    # Per-file breakdown, worst first.
    if sources and parquet_root:
        for key, (path, src_count) in source_counts.items():
            pq_path, pq_count = parquet_counts.get(key, (None, None))
            per_file.append((path.name, src_count, pq_count))
        problems = [
            (name, s, p)
            for name, s, p in per_file
            if s is None or p is None or s != p
        ]
        if problems:
            problems.sort(key=lambda item: -((item[1] or 0) - (item[2] or 0)))
            print(f"\n{len(problems)} file(s) do not balance:")
            for name, s, p in problems[:40]:
                s_text = "unreadable" if s is None else f"{s:,}"
                p_text = "MISSING" if p is None else f"{p:,}"
                print(f"  {name:<48s} {s_text:>12s} -> {p_text:>12s}")
            if len(problems) > 40:
                print(f"  ... and {len(problems) - 40} more")
        else:
            print("\nEvery source file balances against its parquet.")

    orphans = set(parquet_counts) - set(source_counts) if sources and parquet_root else set()
    if orphans:
        print(f"\n{len(orphans)} parquet file(s) have no matching source (left over from an earlier run?):")
        for key in sorted(orphans)[:20]:
            print(f"  {parquet_counts[key][0].name}")

    balanced = True
    if sources and parquet_root and source_rows_total != parquet_rows_total:
        balanced = False
    if table_rows is not None and parquet_root and table_rows != parquet_rows_total:
        balanced = False
    return 0 if balanced else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only row audit across the CSV → Parquet → DuckDB pipeline."
    )
    parser.add_argument("--sources", type=Path, help="Folder of source CSV/.gz files.")
    parser.add_argument("--parquet", type=Path, help="Folder of generated parquet files.")
    parser.add_argument("--db", type=Path, help="DuckDB database file.")
    parser.add_argument("--table", type=str, help="Table name inside --db.")
    args = parser.parse_args(argv)

    if not any([args.sources, args.parquet, args.db]):
        parser.error("give at least one of --sources, --parquet or --db/--table")
    if bool(args.db) != bool(args.table):
        parser.error("--db and --table must be given together")

    return audit(args.sources, args.parquet, args.db, args.table)


if __name__ == "__main__":
    raise SystemExit(main())
