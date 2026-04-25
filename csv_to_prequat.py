#!/usr/bin/env python3
"""Backward-compatible entrypoint for the renamed csv_to_parquet script."""

from csv_to_parquet import main


if __name__ == "__main__":
    raise SystemExit(main())
