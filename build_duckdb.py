#!/usr/bin/env python3
"""Build a month into DuckDB from the command line.

A thin wrapper over the same code path the Data Tools page uses. It has to be:
the page prints a ready-to-paste `python build_duckdb.py ... --object-type VIEW`
command, which is a promise that the two produce the same object.

This script used to reimplement the build, and had drifted badly — no
DISCOM/CATEGORY derivation, no per-column MERCADOS casts, no
`hive_partitioning = false`, no `_quarantine` exclusion, and no row-count
verification. A month built here therefore had a *different schema* from one built
in the UI, under the same `Master_MMYY` name, and could include rows the pipeline
had deliberately quarantined. Delegating removes that class of bug permanently.

Importing the service pulls in pandas, so startup is ~2s rather than ~0.3s. That is
a fair trade for a monthly batch script that shares the repo's virtualenv.
"""

from __future__ import annotations

import argparse

from backend.models.sidebar_tools import BuildDuckDbRequest, MaterialiseMonthRequest
from backend.services.sidebar_tools_service import _execute_build_duckdb, _materialise_month


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a month into DuckDB. By default this creates a VIEW over the "
            "month's parquet (about 2 seconds, no extra disk). Use --materialise to "
            "copy the rows in instead (about 41 minutes and 11.7 GB), which also "
            "converts the previously materialised month back to a view."
        )
    )
    parser.add_argument("--db", required=True, help="DuckDB file path to create/update.")
    parser.add_argument("--input", required=True, help="Parquet file, folder, or glob.")
    parser.add_argument("--object-name", required=True, help="DuckDB object name.")
    parser.add_argument(
        "--object-type",
        choices=("TABLE", "VIEW"),
        default="VIEW",
        help="VIEW (default) reads the parquet in place; TABLE copies the rows in.",
    )
    parser.add_argument(
        "--materialise",
        action="store_true",
        help=(
            "Make this the fast month: build it as a TABLE and convert whichever month "
            "currently holds that slot back to a view (only when its parquet is still "
            "present and still matches, otherwise it is left alone)."
        ),
    )
    parser.add_argument(
        "--replace", action="store_true", help="Replace the existing object if present."
    )
    parser.add_argument("--month-label", default="", help="Example: MAR_2026. Required for MASTER_*.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    common = {
        "db_path": args.db,
        "input_path": args.input,
        "object_name": args.object_name,
        "replace": args.replace,
        "month_label": args.month_label or None,
    }

    if args.materialise:
        outcome = _materialise_month(MaterialiseMonthRequest(**common, object_type="TABLE"))
        print(outcome.message)
        for warning in outcome.demote_warnings:
            print(f"  warning: {warning}")
        return 0

    build = _execute_build_duckdb(BuildDuckDbRequest(**common, object_type=args.object_type))
    print(build.message)
    if build.data_quality != "ok":
        print(f"  data quality: {build.data_quality}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
