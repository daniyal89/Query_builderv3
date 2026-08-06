"""Compare a materialised month against a parquet-backed view, honestly.

The 0.3-2s figure that motivated views was measured with hand-written predicates.
The query builder does not emit those: it wraps every filtered column in
``TRIM``/``UPPER``/``TRY_CAST`` (``query_builder_service._build_condition_sql``). So
the benchmark has to run the SQL the application actually produces.

Measured on DuckDB 1.5.3, with one file per DISCOM and one per month:

- ``TRIM(DISCOM) = 'DVVNL'`` and ``UPPER(TRIM(CAST(...))) IN (...)`` **do** prune —
  20,000 of 100,000 rows read. DuckDB reasons through those wrappers.
- The date filter does **not**. ``_duckdb_date_expression`` wraps the column in a
  9-branch ``COALESCE`` of ``TRY_CAST``/``TRY_STRPTIME``, and that read all 100,000
  rows to return 20,000 — the whole month, every time, for any date filter.

So ``rows_read`` below is the number that matters, not elapsed time on warm cache:
it says whether a query touched the month or just the part it needed.

Run it against the real storage — the parquet lives on a mapped network drive in
production, and numbers from a local SSD do not transfer.

Example::

    python -m backend.tools.benchmark_view_vs_table \\
        --db "G:/MASTER/uppcl_latest.duckdb" \\
        --table Master_0626 --view Master_0626_view \\
        --explain

Both objects must already exist and cover the same month; build one as a TABLE and
one as a VIEW over the same parquet first. Read-only: it issues nothing but SELECTs.
"""

from __future__ import annotations

import argparse
import re
import statistics
import time
from typing import Any

import duckdb

from backend.models.query import (
    AggregateRule,
    FilterCondition,
    PivotConfig,
    QueryPayload,
    SortClause,
)
from backend.services.duckdb_session import apply_session_settings
from backend.services.query_builder_service import QueryBuilderService


def _payload(table: str, **overrides: Any) -> QueryPayload:
    base: dict[str, Any] = {
        "execution_mode": "builder",
        "engine": "duckdb",
        "table": table,
        "select": ["ACCT_ID", "DISCOM", "TOTAL_AMT"],
        "filters": [],
        "sort": [],
        "limit_rows": 100,
        "offset": 0,
        "mode": "LIST",
        "group_by": [],
        "aggregates": [],
    }
    base.update(overrides)
    return QueryPayload(**base)


def _scenarios(table: str) -> list[tuple[str, QueryPayload]]:
    """The shapes an operator actually runs, not the ones that benchmark well."""
    return [
        ("select * limit 100", _payload(table, select=["*"])),
        (
            "filter DISCOM = one division",
            _payload(
                table,
                filters=[FilterCondition(column="DISCOM", operator="=", value="DVVNL")],
            ),
        ),
        (
            "filter on a DATE-named column",
            # Hits _duckdb_date_expression: a 9-branch COALESCE of TRY_CAST /
            # TRY_STRPTIME evaluated per row.
            _payload(
                table,
                filters=[
                    FilterCondition(column="BILL_DATE", operator=">=", value="2026-06-01")
                ],
            ),
        ),
        (
            "order by amount desc limit 100",
            _payload(table, sort=[SortClause(column="TOTAL_AMT", direction="DESC")]),
        ),
        (
            "group by DISCOM",
            _payload(
                table,
                mode="LIST",
                select=["DISCOM"],
                group_by=["DISCOM"],
                aggregates=[AggregateRule(column="ACCT_ID", func="COUNT")],
            ),
        ),
        (
            "monthly pivot report",
            _payload(
                table,
                mode="REPORT",
                pivot=PivotConfig(
                    rows=["DISCOM"],
                    columns=["CATEGORY"],
                    aggregates=[AggregateRule(column="TOTAL_AMT", func="SUM")],
                ),
            ),
        ),
    ]


def _time_sql(
    conn: duckdb.DuckDBPyConnection, sql: str, params: list[Any], repeats: int
) -> tuple[float, str | None]:
    timings: list[float] = []
    error: str | None = None
    for _ in range(repeats):
        started = time.perf_counter()
        try:
            conn.execute(sql, params) if params else conn.execute(sql)
            conn.fetchall()
        except Exception as exc:  # a missing column is a real result, not a crash
            return 0.0, f"{type(exc).__name__}: {exc}"
        timings.append(time.perf_counter() - started)
    return (statistics.median(timings), error)


def _rows_read(
    conn: duckdb.DuckDBPyConnection, sql: str, params: list[Any], month_rows: int | None
) -> str:
    """How many rows the parquet scan actually read.

    The presence of a ``Filters:`` line in the plan is *not* the signal — DuckDB
    prints it whether or not it can skip data with it. Actual cardinality from
    EXPLAIN ANALYZE is the only honest measure of "did this touch the whole month".
    """
    try:
        rows = (
            conn.execute(f"EXPLAIN ANALYZE {sql}", params).fetchall()
            if params
            else conn.execute(f"EXPLAIN ANALYZE {sql}").fetchall()
        )
    except Exception:
        return ""
    plan = "\n".join(str(row[-1]) for row in rows)
    if "READ_PARQUET" not in plan.upper():
        return "native table"
    tail = plan.split("READ_PARQUET")[-1]
    found = re.findall(r"([\d,]+) Rows", tail) or re.findall(r"~?([\d,]+) rows", tail)
    if not found:
        return "rows read: unknown"
    read = int(found[0].replace(",", ""))
    if month_rows and month_rows > 0:
        share = read / month_rows
        verdict = "whole month" if share > 0.95 else f"{share:.0%} of month"
        return f"read {read:,} rows ({verdict})"
    return f"read {read:,} rows"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--table", required=True, help="A materialised month.")
    parser.add_argument("--view", required=True, help="A parquet-backed view of the same month.")
    parser.add_argument("--repeats", type=int, default=3, help="Median of N runs (default 3).")
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Also report how many rows each view query actually read from parquet.",
    )
    args = parser.parse_args()

    conn = duckdb.connect(args.db, read_only=True)
    apply_session_settings(conn)

    month_rows: int | None = None
    try:
        month_rows = int(
            conn.execute(f'SELECT count(*) FROM "{args.view}"').fetchone()[0]
        )
        print(f"{args.view} resolves {month_rows:,} rows\n")
    except Exception as exc:
        print(f"could not count {args.view}: {exc}\n")

    print(f"{'scenario':<34} {'table':>9} {'view':>9} {'ratio':>7}  note")
    print("-" * 92)

    for label, template in _scenarios(args.table):
        row: dict[str, float] = {}
        note = ""
        for kind, object_name in (("table", args.table), ("view", args.view)):
            payload = template.model_copy(update={"table": object_name})
            data_sql, params = QueryBuilderService.build_sql(payload)
            seconds, error = _time_sql(conn, data_sql, params, args.repeats)
            if error:
                note = error
                row[kind] = 0.0
                continue
            row[kind] = seconds
            if args.explain and kind == "view":
                note = _rows_read(conn, data_sql, params, month_rows)

        table_s, view_s = row.get("table", 0.0), row.get("view", 0.0)
        ratio = f"{view_s / table_s:.1f}x" if table_s > 0 else "-"
        print(f"{label:<34} {table_s:>8.3f}s {view_s:>8.3f}s {ratio:>7}  {note}")

    # /api/query also runs an unbounded COUNT whenever the first page comes back
    # full, so a truncated result costs both of these.
    print()
    print("Count query, which /api/query still runs for a full first page:")
    for kind, object_name in (("table", args.table), ("view", args.view)):
        count_sql, count_params = QueryBuilderService.build_count_sql(
            _payload(object_name, filters=[FilterCondition(column="DISCOM", operator="=", value="DVVNL")])
        )
        seconds, error = _time_sql(conn, count_sql, count_params, args.repeats)
        print(f"  {kind:<8} {seconds:>8.3f}s  {error or ''}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
