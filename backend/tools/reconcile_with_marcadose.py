"""Division-wise consumer counts, local vs Marcadose, and where they differ.

The local pipeline does not keep every source row. Rows whose ACCT_ID is blank or
non-numeric are written to a ``_quarantine`` directory and deliberately excluded
from the master, because a consumer record with no usable account id cannot be
joined to anything. Oracle holds those rows. So a raw count difference is expected,
and the useful question is whether it is *fully explained* by the quarantine.

This reports, per DISCOM and per division:

    local master rows + quarantined rows = what the source actually contained

Run it against the parquet rather than the .duckdb so it works while the app has
the database open, and because for a month stored as a view the parquet *is* the
data.

Example::

    python -m backend.tools.reconcile_with_marcadose \\
        --parquet "D:/DATA/MASTER/JUN_26_PAR" --by-division --out jun_local.csv

It also prints the Oracle SQL to run on the Marcadose side. Pass the result back
with --oracle-csv to get a reconciled diff.
"""

from __future__ import annotations

import argparse
import csv
import glob as globmod
from pathlib import Path

import duckdb

from backend.services.duckdb_session import apply_session_settings
from backend.services.sidebar_tools_service import (
    QUARANTINE_DIR_NAME,
    _is_readable_input_file,
    _sql_string_list_literal,
)


def _split_sources(root: Path) -> tuple[list[str], list[str]]:
    """(master files, quarantine files) under *root*."""
    master: list[str] = []
    quarantined: list[str] = []
    for item in globmod.glob(f"{root.as_posix()}/**/*.parquet", recursive=True):
        if QUARANTINE_DIR_NAME in Path(item).parts:
            quarantined.append(item)
        elif _is_readable_input_file(item):
            master.append(item)
    return master, quarantined


def _counts(conn: duckdb.DuckDBPyConnection, files: list[str], keys: list[str]) -> dict:
    if not files:
        return {}
    key_sql = ", ".join(f'"{k}"' for k in keys)
    rows = conn.execute(
        f"SELECT {key_sql}, count(*) FROM read_parquet("
        f"{_sql_string_list_literal(sorted(files))}, union_by_name = true) "
        f"GROUP BY {key_sql}"
    ).fetchall()
    return {tuple(str(v) if v is not None else "" for v in r[:-1]): int(r[-1]) for r in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", required=True, help="A month's parquet root.")
    parser.add_argument("--by-division", action="store_true", help="DIV_CODE detail, not just DISCOM.")
    parser.add_argument("--out", help="Write the local counts to this CSV.")
    parser.add_argument(
        "--oracle-csv",
        help="CSV of Marcadose counts to diff against: DISCOM,DIV_CODE,COUNT (header optional).",
    )
    args = parser.parse_args()

    root = Path(args.parquet)
    keys = ["DISCOM", "DIV_CODE"] if args.by_division else ["DISCOM"]
    master, quarantined = _split_sources(root)

    conn = duckdb.connect()
    apply_session_settings(conn)
    local = _counts(conn, master, keys)
    rejected = _counts(conn, quarantined, keys)

    print(f"{root}")
    print(f"  {len(master)} master parquet file(s), {len(quarantined)} quarantine file(s)\n")

    header = " / ".join(keys)
    print(f"{header:<28} {'local master':>14} {'quarantined':>13} {'source total':>14}")
    print("-" * 74)
    total_local = total_rejected = 0
    for key in sorted(set(local) | set(rejected)):
        lo, qa = local.get(key, 0), rejected.get(key, 0)
        total_local += lo
        total_rejected += qa
        print(f"{' / '.join(key):<28} {lo:>14,} {qa:>13,} {lo + qa:>14,}")
    print("-" * 74)
    print(f"{'TOTAL':<28} {total_local:>14,} {total_rejected:>13,} {total_local + total_rejected:>14,}")

    if total_rejected:
        print(
            f"\n{total_rejected:,} row(s) are in Marcadose but deliberately not in the local "
            "master: their ACCT_ID was blank or non-numeric. That is the expected gap."
        )
    else:
        print("\nNothing was quarantined, so local and Marcadose should agree exactly.")

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([*keys, "LOCAL_ROWS", "QUARANTINED_ROWS"])
            for key in sorted(set(local) | set(rejected)):
                writer.writerow([*key, local.get(key, 0), rejected.get(key, 0)])
        print(f"\nwrote {args.out}")

    group_sql = ", ".join(keys)
    print("\n--- run this on Marcadose, for the same month ---")
    print(
        f"SELECT {group_sql}, COUNT(*) AS CNT\n"
        "FROM MERCADOS.CM_MASTER_DATA_<MON>_<YYYY>_<DISCOM>\n"
        f"GROUP BY {group_sql} ORDER BY {group_sql};"
    )
    print("(one table per DISCOM, or use the app's DISCOM UNION report)")

    if args.oracle_csv:
        oracle: dict[tuple[str, ...], int] = {}
        with open(args.oracle_csv, newline="", encoding="utf-8") as handle:
            for row in csv.reader(handle):
                if not row or not row[-1].strip().lstrip("-").isdigit():
                    continue  # header or blank
                oracle[tuple(v.strip() for v in row[:-1])] = int(row[-1])

        print(f"\n{'key':<28} {'marcadose':>12} {'local':>12} {'quarantined':>12} {'unexplained':>12}")
        print("-" * 80)
        unexplained_total = 0
        for key in sorted(set(oracle) | set(local) | set(rejected)):
            orc, lo, qa = oracle.get(key, 0), local.get(key, 0), rejected.get(key, 0)
            unexplained = orc - lo - qa
            unexplained_total += unexplained
            flag = "  <--" if unexplained else ""
            print(f"{' / '.join(key):<28} {orc:>12,} {lo:>12,} {qa:>12,} {unexplained:>12,}{flag}")
        print("-" * 80)
        print(f"{'TOTAL UNEXPLAINED':<28} {unexplained_total:>51,}")
        if unexplained_total:
            print(
                "\nA non-zero unexplained figure means the difference is NOT just quarantine.\n"
                "Most likely: that division's CSV never arrived over FTP, or Marcadose was\n"
                "updated after the extract was taken."
            )
        else:
            print("\nEvery row is accounted for: local + quarantined == Marcadose.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
