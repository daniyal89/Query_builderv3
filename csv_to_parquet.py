#!/usr/bin/env python3
"""Convert CSV (or .csv.gz) to Parquet using DuckDB."""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import duckdb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert CSV/.gz to Parquet.")
    parser.add_argument("--input", required=True, help="Input CSV path or glob (supports .gz).")
    parser.add_argument("--output", required=True, help="Output parquet file path.")
    parser.add_argument("--compression", default="zstd", help="Parquet compression codec.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = args.input
    if not glob.glob(input_path, recursive=True) and ".csv.gz" in input_path.lower():
        fallback = input_path[:-7] + ".gz"
        if glob.glob(fallback, recursive=True):
            input_path = fallback

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect()
    input_sql = f"'{input_path.replace(chr(39), chr(39) * 2)}'"
    output_sql = f"'{str(output_path).replace(chr(39), chr(39) * 2)}'"
    compression_sql = f"'{args.compression.replace(chr(39), chr(39) * 2)}'"
    conn.execute(
        f"COPY (SELECT * FROM read_csv_auto({input_sql}, union_by_name = true, filename = true)) "
        f"TO {output_sql} (FORMAT PARQUET, COMPRESSION {compression_sql})",
    )
    print(f"Parquet created at: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
