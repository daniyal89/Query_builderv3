import duckdb
import pandas as pd

from backend.services.merge_service import MergeService


def _master_connection() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute(
        'CREATE TABLE master AS SELECT * FROM (VALUES '
        "('0000000001', 'Alice'), ('0000000002', 'Bob')"
        ') AS t("ACCT_ID", "NAME")'
    )
    return conn


def test_process_enrichment_keeps_text_in_a_mostly_numeric_column() -> None:
    # DuckDB samples only the first 1000 rows of an object column when picking a
    # type. A column that is numeric for thousands of rows and then holds "24B"
    # used to make the whole enrichment fail with "Could not convert string
    # '24B' to INT32".
    row_count = 50_000
    flat_numbers: list[object] = list(range(row_count))
    flat_numbers[row_count - 1] = "24B"
    uploaded = pd.DataFrame(
        {
            "ACCT_ID": ["1", "2"] + ["999"] * (row_count - 2),
            "FLAT_NO": flat_numbers,
        }
    )

    result, stats = MergeService.process_enrichment(
        merged_df=uploaded,
        conn=_master_connection(),
        master_table="master",
        fetch_columns=["NAME"],
        join_keys=[{"fileColumn": "ACCT_ID", "tableColumn": "ACCT_ID"}],
    )

    assert stats == {"matched_rows": 2, "unmatched_rows": row_count - 2, "total_rows": row_count}
    by_account = result.set_index("ACCT_ID")
    assert by_account.loc["0000000001", "NAME"] == "Alice"
    assert by_account.loc["0000000002", "NAME"] == "Bob"
    assert "24B" in set(result["FLAT_NO"])
    assert "0" in set(result["FLAT_NO"])


def test_stringify_object_columns_leaves_typed_columns_alone_and_keeps_nulls() -> None:
    frame = pd.DataFrame(
        {
            "count": [1, 2, 3],
            "amount": [1.5, None, 2.5],
            "mixed": [10, "24B", None],
        }
    )

    out = MergeService.stringify_object_columns(frame)

    assert str(out["count"].dtype) == "int64"
    assert str(out["amount"].dtype) == "float64"
    assert out["mixed"].tolist()[:2] == ["10", "24B"]
    assert pd.isna(out["mixed"].iloc[2])
