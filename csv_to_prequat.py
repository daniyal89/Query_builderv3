#!/usr/bin/env python3
"""Convert CSV (or .csv.gz) to Parquet using DuckDB."""

from __future__ import annotations

import argparse
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
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect()
    conn.execute(
        "COPY (SELECT * FROM read_csv_auto(?, union_by_name = true, filename = true)) "
        "TO ? (FORMAT PARQUET, COMPRESSION ?)",
        [args.input, str(output_path), args.compression],
    )
    print(f"Parquet created at: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
