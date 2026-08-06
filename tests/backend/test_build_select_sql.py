"""`_build_select_sql_for_schema` must never emit a column twice.

The build used to pass parquet written by its own phase 1 — which already holds
DISCOM and CATEGORY — through a SELECT that re-derived both. DISCOM survived
because the source copy was dropped; CATEGORY did not, so DuckDB silently renamed
the second one and every built month carried both CATEGORY and CATEGORY_1, with
9 REGEXP_EXTRACT per row spent computing a value the file already had.
"""

import glob as globmod
from pathlib import Path
from uuid import uuid4

import duckdb
import pytest

from backend.models.sidebar_tools import BuildDuckDbRequest
from backend.services.sidebar_tools_service import (
    QUARANTINE_DIR_NAME,
    _build_select_sql_for_schema,
    _execute_build_duckdb,
    _is_readable_input_file,
    _resolve_view_relation_sql,
)


def _parquet(path: Path, **columns: str) -> str:
    """Write a single-row parquet and return a read_parquet() relation over it."""
    con = duckdb.connect()
    cols = ", ".join(f"'{value}' AS \"{name}\"" for name, value in columns.items())
    con.execute(f"COPY (SELECT {cols}) TO '{path.as_posix()}' (FORMAT PARQUET)")
    return f"read_parquet('{path.as_posix()}')"


def _columns_of(select_sql: str) -> list[str]:
    con = duckdb.connect()
    result = con.execute(f"SELECT * FROM ({select_sql}) LIMIT 0")
    return [desc[0] for desc in result.description]


@pytest.fixture
def parquet_relation(tmp_path: Path) -> str:
    """Parquet as phase 1 writes it: DIV_CODE, SUPPLY_TYPE and both derived cols."""
    return _parquet(
        tmp_path / "phase1.parquet",
        ACCT_ID="0000000001",
        DIV_CODE="DIV211321",
        SUPPLY_TYPE="49",
        DISCOM="DVVNL",
        CATEGORY="LMV-4",
    )


def test_parquet_source_does_not_duplicate_category(parquet_relation: str) -> None:
    col_names = ["ACCT_ID", "DIV_CODE", "SUPPLY_TYPE", "DISCOM", "CATEGORY"]

    sql = _build_select_sql_for_schema(
        parquet_relation, col_names, derive="if_missing", legacy_category_alias=False
    )
    columns = _columns_of(sql)

    assert columns.count("CATEGORY") == 1
    assert "CATEGORY_1" not in columns
    assert columns.count("DISCOM") == 1


def test_if_missing_does_not_recompute_what_parquet_already_holds(parquet_relation: str) -> None:
    """The 9 REGEXP_EXTRACT per row are the cost this mode exists to avoid."""
    col_names = ["ACCT_ID", "DIV_CODE", "SUPPLY_TYPE", "DISCOM", "CATEGORY"]

    sql = _build_select_sql_for_schema(
        parquet_relation, col_names, derive="if_missing", legacy_category_alias=False
    )

    assert "REGEXP_EXTRACT" not in sql.upper()
    assert "starts_with" not in sql


def test_if_missing_still_derives_a_genuinely_absent_column(tmp_path: Path) -> None:
    """Older parquet without CATEGORY must still get one."""
    relation = _parquet(
        tmp_path / "old.parquet",
        ACCT_ID="0000000001",
        DIV_CODE="DIV211321",
        SUPPLY_TYPE="49",
    )
    col_names = ["ACCT_ID", "DIV_CODE", "SUPPLY_TYPE"]

    sql = _build_select_sql_for_schema(
        relation, col_names, derive="if_missing", legacy_category_alias=False
    )
    columns = _columns_of(sql)

    assert columns.count("CATEGORY") == 1
    assert columns.count("DISCOM") == 1
    con = duckdb.connect()
    assert con.execute(f"SELECT CATEGORY, DISCOM FROM ({sql})").fetchone() == ("LMV-4", "DVVNL")


def test_always_rederives_and_drops_the_source_copy(parquet_relation: str) -> None:
    """CSV sources are not trusted — but the re-derived column must not collide."""
    col_names = ["ACCT_ID", "DIV_CODE", "SUPPLY_TYPE", "DISCOM", "CATEGORY"]

    sql = _build_select_sql_for_schema(
        parquet_relation, col_names, derive="always", legacy_category_alias=False
    )
    columns = _columns_of(sql)

    assert columns.count("CATEGORY") == 1
    assert columns.count("DISCOM") == 1
    assert "CATEGORY_1" not in columns
    assert "REGEXP_EXTRACT" in sql.upper(), "'always' must actually re-derive"


def test_discom_is_kept_when_it_cannot_be_rederived(tmp_path: Path) -> None:
    """Without DIV_CODE there is nothing to derive from, so keep what we have.

    The old code dropped DISCOM unconditionally, losing the column outright.
    """
    relation = _parquet(
        tmp_path / "no_div.parquet", ACCT_ID="0000000001", DISCOM="DVVNL"
    )

    sql = _build_select_sql_for_schema(
        relation, ["ACCT_ID", "DISCOM"], derive="always", legacy_category_alias=False
    )
    columns = _columns_of(sql)

    assert columns == ["ACCT_ID", "DISCOM"]
    con = duckdb.connect()
    assert con.execute(f"SELECT DISCOM FROM ({sql})").fetchone() == ("DVVNL",)


def test_legacy_alias_exposes_category_1_with_the_same_value(parquet_relation: str) -> None:
    """Saved queries reference either name for one release."""
    col_names = ["ACCT_ID", "DIV_CODE", "SUPPLY_TYPE", "DISCOM", "CATEGORY"]

    sql = _build_select_sql_for_schema(
        parquet_relation, col_names, derive="if_missing", legacy_category_alias=True
    )
    columns = _columns_of(sql)

    assert columns.count("CATEGORY") == 1
    assert columns.count("CATEGORY_1") == 1
    con = duckdb.connect()
    category, legacy = con.execute(f'SELECT "CATEGORY", "CATEGORY_1" FROM ({sql})').fetchone()
    assert category == legacy == "LMV-4", "CATEGORY_1 was never a distinct value"


def test_legacy_alias_is_absent_when_there_is_no_category(tmp_path: Path) -> None:
    relation = _parquet(tmp_path / "plain.parquet", ACCT_ID="0000000001")

    sql = _build_select_sql_for_schema(
        relation, ["ACCT_ID"], derive="if_missing", legacy_category_alias=True
    )

    assert _columns_of(sql) == ["ACCT_ID"]


def test_an_unknown_derive_mode_is_rejected(parquet_relation: str) -> None:
    with pytest.raises(ValueError, match="derive must be"):
        _build_select_sql_for_schema(parquet_relation, ["ACCT_ID"], derive="sometimes")


# ── The quarantine exclusion must survive a shadowing `filename` column ───────


def _month_with_quarantine(root: Path, *, physical_filename_column: bool) -> None:
    """A month as the pipeline writes it: good rows plus a quarantined reject file.

    Some months' parquet carries a physical `filename` column and some do not —
    measured on real data, FEB 2026 (153 cols) and JUL 2026 (165) do, MAR–JUN (164)
    do not. A physical column shadows read_parquet's virtual one, so the exclusion
    has to work either way.
    """
    div = root / "DVVNL"
    quarantine = div / QUARANTINE_DIR_NAME
    quarantine.mkdir(parents=True)
    extra = ", 'D:/csv/DVVNL_DIV1.csv.gz' AS filename" if physical_filename_column else ""
    con = duckdb.connect()
    con.execute(
        f"COPY (SELECT i AS ACCT_ID, 'DIV211321' AS DIV_CODE, '49' AS SUPPLY_TYPE{extra} "
        f"FROM range(5) t(i)) TO '{(div / 'part.parquet').as_posix()}' (FORMAT PARQUET)"
    )
    # As pipeline_sql.build_rejects_sql writes it: the rejected rows plus a marker
    # column that must never become part of the master.
    con.execute(
        f"COPY (SELECT 99 AS ACCT_ID, 'DIV211321' AS DIV_CODE, '49' AS SUPPLY_TYPE{extra}, "
        f"'ACCT_ID_BLANK' AS __reject_reason) "
        f"TO '{(quarantine / 'part.ACCT_ID_INVALID.parquet').as_posix()}' (FORMAT PARQUET)"
    )


def _validated(root: Path) -> tuple[str, list[str]]:
    """The glob and the classified file list, exactly as the build computes them."""
    pattern = f"{root.as_posix()}/**/*.parquet"
    files = [item for item in globmod.glob(pattern, recursive=True) if _is_readable_input_file(item)]
    return pattern, files


@pytest.mark.parametrize("physical_filename_column", [False, True])
def test_quarantined_rows_stay_out_of_a_view(
    tmp_path: Path, physical_filename_column: bool
) -> None:
    """The rejected row must not be resolvable through the month's view.

    Parametrised over a physical `filename` column because real months differ: it
    used to shadow read_parquet's virtual one, so a filename predicate silently
    tested the source CSV path and let the rejected row through.
    """
    root = tmp_path / uuid4().hex[:8]
    _month_with_quarantine(root, physical_filename_column=physical_filename_column)

    relation = _resolve_view_relation_sql(*_validated(root))
    con = duckdb.connect()

    assert con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0] == 5
    assert con.execute(f"SELECT max(ACCT_ID) FROM {relation}").fetchone()[0] != 99


def test_the_view_is_still_live_for_files_added_later(tmp_path: Path) -> None:
    """The whole point of a view: a new division file appears without a rebuild."""
    root = tmp_path / uuid4().hex[:8]
    _month_with_quarantine(root, physical_filename_column=False)
    relation = _resolve_view_relation_sql(*_validated(root))
    con = duckdb.connect()
    assert con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0] == 5

    duckdb.connect().execute(
        "COPY (SELECT 500 AS ACCT_ID, 'DIV211321' AS DIV_CODE, '49' AS SUPPLY_TYPE) "
        f"TO '{(root / 'DVVNL' / 'part-002.parquet').as_posix()}' (FORMAT PARQUET)"
    )

    assert con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0] == 6


def test_a_quarantine_file_added_later_still_cannot_be_resolved(tmp_path: Path) -> None:
    """Structural, not a filter: a new reject file lands in a subdirectory the
    per-division glob cannot descend into."""
    root = tmp_path / uuid4().hex[:8]
    _month_with_quarantine(root, physical_filename_column=False)
    relation = _resolve_view_relation_sql(*_validated(root))
    con = duckdb.connect()

    duckdb.connect().execute(
        "COPY (SELECT 777 AS ACCT_ID, 'DIV211321' AS DIV_CODE, '49' AS SUPPLY_TYPE, "
        "'ACCT_ID_BLANK' AS __reject_reason) TO "
        f"'{(root / 'DVVNL' / QUARANTINE_DIR_NAME / 'later.parquet').as_posix()}' (FORMAT PARQUET)"
    )

    assert con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0] == 5


def test_an_ancestor_directory_named_like_quarantine_is_harmless(tmp_path: Path) -> None:
    """A path merely containing the word must not wipe out the month.

    A substring predicate did exactly that — and this repo's own pytest tmp
    directory for the quarantine tests ("...test_quarantined_rows...") triggered it,
    making every file vanish and the build fail on a baffling count mismatch.
    """
    root = tmp_path / "uppcl_quarantine_review" / uuid4().hex[:8]
    _month_with_quarantine(root, physical_filename_column=False)

    relation = _resolve_view_relation_sql(*_validated(root))

    assert duckdb.connect().execute(f"SELECT count(*) FROM {relation}").fetchone()[0] == 5


def test_a_file_named_like_quarantine_is_still_included(tmp_path: Path) -> None:
    """Only the _quarantine directory is excluded, not a lookalike file name."""
    root = tmp_path / uuid4().hex[:8]
    div = root / "DVVNL"
    div.mkdir(parents=True)
    duckdb.connect().execute(
        "COPY (SELECT 1 AS ACCT_ID) TO "
        f"'{(div / 'div_quarantine_A.parquet').as_posix()}' (FORMAT PARQUET)"
    )

    relation = _resolve_view_relation_sql(*_validated(root))

    assert duckdb.connect().execute(f"SELECT count(*) FROM {relation}").fetchone()[0] == 1


def test_the_view_relation_exposes_only_data_columns(tmp_path: Path) -> None:
    """No scan helper column leaks, and a real `filename` column is kept as data."""
    root = tmp_path / uuid4().hex[:8]
    _month_with_quarantine(root, physical_filename_column=True)

    relation = _resolve_view_relation_sql(*_validated(root))
    columns = _columns_of(f"SELECT * FROM {relation}")

    assert "__source_file" not in columns
    assert "filename" in columns
    assert "__reject_reason" not in columns, "quarantine schema must not reach the view"


@pytest.mark.parametrize("physical_filename_column", [False, True])
def test_a_month_with_quarantined_rows_still_builds_as_a_view(
    tmp_path: Path, physical_filename_column: bool
) -> None:
    """Quarantined rows are routine, so they must not make a month unbuildable.

    The row-count verification compares the view against the validated footers. When
    the exclusion failed to fire, that check aborted the build and the month was
    simply absent from the database.
    """
    root = tmp_path / uuid4().hex[:8]
    _month_with_quarantine(root, physical_filename_column=physical_filename_column)
    db_path = root / "built.duckdb"

    outcome = _execute_build_duckdb(
        BuildDuckDbRequest(
            db_path=str(db_path),
            input_path=str(root),
            object_name="part_table",
            object_type="VIEW",
            replace=True,
        )
    )

    assert outcome.table_rows == 5
    con = duckdb.connect(str(db_path))
    assert con.execute("SELECT count(*) FROM part_table").fetchone()[0] == 5


def test_a_view_and_a_table_of_the_same_month_have_the_same_schema(tmp_path: Path) -> None:
    """`union_by_name` resolves a view's schema across every matched file, so the
    quarantine file's internal `__reject_reason` used to become a master column —
    and shared column types widened. The two storage modes must be interchangeable."""
    root = tmp_path / uuid4().hex[:8]
    _month_with_quarantine(root, physical_filename_column=False)

    schemas = {}
    for kind in ("VIEW", "TABLE"):
        db_path = root / f"{kind.lower()}.duckdb"
        _execute_build_duckdb(
            BuildDuckDbRequest(
                db_path=str(db_path),
                input_path=str(root),
                object_name="part_table",
                object_type=kind,
                replace=True,
            )
        )
        con = duckdb.connect(str(db_path))
        schemas[kind] = con.execute(
            "SELECT column_name, data_type FROM duckdb_columns() "
            "WHERE table_name = 'part_table' ORDER BY column_index"
        ).fetchall()

    assert schemas["VIEW"] == schemas["TABLE"]
    assert "__reject_reason" not in [name for name, _ in schemas["VIEW"]]


# ── End to end: the built table is what the operator actually queries ──────────


def test_a_built_table_has_exactly_one_category_column(tmp_path: Path) -> None:
    """The defect as it appeared in production: CATEGORY *and* CATEGORY_1.

    Verified on the real file — every built month carried both. Here the whole
    build runs against phase-1-shaped parquet and the table is inspected.
    """
    src = tmp_path / "in"
    src.mkdir()
    _parquet(
        src / "part.parquet",
        ACCT_ID="0000000001",
        DIV_CODE="DIV211321",
        SUPPLY_TYPE="49",
        DISCOM="DVVNL",
        CATEGORY="LMV-4",
    )
    db_path = tmp_path / "built.duckdb"

    _execute_build_duckdb(
        BuildDuckDbRequest(
            db_path=str(db_path),
            input_path=str(src / "*.parquet"),
            object_name="part_table",
            object_type="TABLE",
            replace=True,
        )
    )

    con = duckdb.connect(str(db_path))
    columns = [
        row[0]
        for row in con.execute(
            "SELECT column_name FROM duckdb_columns() WHERE table_name = 'part_table' "
            "ORDER BY column_index"
        ).fetchall()
    ]

    assert columns.count("CATEGORY") == 1
    assert columns.count("DISCOM") == 1
    # CATEGORY_1 survives deliberately for one release, as an alias of CATEGORY —
    # not as a second silently-renamed duplicate.
    assert columns.count("CATEGORY_1") == 1
    category, legacy, discom = con.execute(
        'SELECT "CATEGORY", "CATEGORY_1", "DISCOM" FROM part_table'
    ).fetchone()
    assert category == legacy == "LMV-4"
    assert discom == "DVVNL"
