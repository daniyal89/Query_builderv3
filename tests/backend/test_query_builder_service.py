import pytest
from pydantic import ValidationError

from backend.models.query import FilterCondition, JoinClause, JoinCondition, QueryPayload, SortClause
from backend.services.query_builder_service import QueryBuilderService


def test_build_preview_sql_renders_joined_query_with_aliases() -> None:
    payload = QueryPayload(
        engine="duckdb",
        table="master",
        select=["master.ACCT_ID", "usage_view.STATUS"],
        filters=[FilterCondition(column="usage_view.STATUS", operator="=", value="ACTIVE")],
        sort=[SortClause(column="usage_view.STATUS", direction="DESC")],
        joins=[
            JoinClause(
                table="usage_view",
                join_type="LEFT",
                conditions=[
                    JoinCondition(
                        left_column="master.ACCT_ID",
                        right_column="usage_view.ACCT_ID",
                    )
                ],
            )
        ],
        limit_rows=25,
        offset=5,
    )

    sql = QueryBuilderService.build_preview_sql(payload)

    assert 'SELECT t0."ACCT_ID" AS "master.ACCT_ID", t1."STATUS" AS "usage_view.STATUS"' in sql
    assert 'FROM "master" t0 LEFT JOIN "usage_view" t1 ON t0."ACCT_ID" = t1."ACCT_ID"' in sql
    assert 'WHERE t1."STATUS" = \'ACTIVE\'' in sql
    assert 'ORDER BY t1."STATUS" DESC' in sql
    assert sql.endswith("LIMIT 25 OFFSET 5")


def test_build_count_sql_keeps_join_structure() -> None:
    payload = QueryPayload(
        engine="oracle",
        table="master",
        select=[],
        filters=[FilterCondition(column="detail.FLAG", operator="=", value="Y")],
        sort=[],
        joins=[
            JoinClause(
                table="detail",
                join_type="INNER",
                conditions=[
                    JoinCondition(
                        left_column="master.ACCT_ID",
                        right_column="detail.ACCT_ID",
                    )
                ],
            )
        ],
    )

    sql, params = QueryBuilderService.build_count_sql(payload)

    assert sql == (
        'SELECT COUNT(*) FROM "master" t0 INNER JOIN "detail" t1 '
        'ON t0."ACCT_ID" = t1."ACCT_ID" WHERE t1."FLAG" = :1'
    )
    assert params == ["Y"]


def test_oracle_schema_qualified_table_names_are_quoted_by_part() -> None:
    payload = QueryPayload(
        engine="oracle",
        table="MERCADOS.CM_MASTER_DATA_0326_DVVNL",
        select=["MERCADOS.CM_MASTER_DATA_0326_DVVNL.ACCT_ID"],
        filters=[FilterCondition(column="MERCADOS.CM_MASTER_DATA_0326_DVVNL.DISCOM", operator="=", value="DVVNL")],
        limit_rows=10,
    )

    sql = QueryBuilderService.build_preview_sql(payload)

    assert 'SELECT t0."ACCT_ID" FROM "MERCADOS"."CM_MASTER_DATA_0326_DVVNL" t0' in sql
    assert 'WHERE t0."DISCOM" = \'DVVNL\'' in sql
    assert sql.endswith("FETCH FIRST 10 ROWS ONLY")


def test_query_payload_rejects_duplicate_join_tables() -> None:
    with pytest.raises(ValidationError):
        QueryPayload(
            engine="duckdb",
            table="master",
            joins=[
                JoinClause(
                    table="detail",
                    join_type="LEFT",
                    conditions=[
                        JoinCondition(
                            left_column="master.ACCT_ID",
                            right_column="detail.ACCT_ID",
                        )
                    ],
                ),
                JoinClause(
                    table="detail",
                    join_type="INNER",
                    conditions=[
                        JoinCondition(
                            left_column="master.ACCT_ID",
                            right_column="detail.DIV_CODE",
                        )
                    ],
                ),
            ],
        )


def test_query_payload_allows_repeated_join_table_when_aliases_are_unique() -> None:
    payload = QueryPayload(
        engine="duckdb",
        table="master",
        joins=[
            JoinClause(
                table="detail",
                alias="detail_primary",
                join_type="LEFT",
                conditions=[
                    JoinCondition(
                        left_column="master.ACCT_ID",
                        right_column="detail_primary.ACCT_ID",
                    )
                ],
            ),
            JoinClause(
                table="detail",
                alias="detail_secondary",
                join_type="INNER",
                conditions=[
                    JoinCondition(
                        left_column="detail_primary.DIV_CODE",
                        right_column="detail_secondary.DIV_CODE",
                    )
                ],
            ),
        ],
    )

    sql = QueryBuilderService.build_preview_sql(payload)

    assert 'LEFT JOIN "detail" t1 ON t0."ACCT_ID" = t1."ACCT_ID"' in sql
    assert 'INNER JOIN "detail" t2 ON t1."DIV_CODE" = t2."DIV_CODE"' in sql


def test_repeated_join_aliases_flow_through_select_filter_and_sort() -> None:
    payload = QueryPayload(
        engine="duckdb",
        table="master",
        select=["detail_secondary.STATUS"],
        filters=[FilterCondition(column="detail_primary.FLAG", operator="=", value="Y")],
        sort=[SortClause(column="detail_secondary.STATUS", direction="ASC")],
        joins=[
            JoinClause(
                table="detail",
                alias="detail_primary",
                join_type="LEFT",
                conditions=[
                    JoinCondition(
                        left_column="master.ACCT_ID",
                        right_column="detail_primary.ACCT_ID",
                    )
                ],
            ),
            JoinClause(
                table="detail",
                alias="detail_secondary",
                join_type="INNER",
                conditions=[
                    JoinCondition(
                        left_column="detail_primary.RELATED_ID",
                        right_column="detail_secondary.RELATED_ID",
                    )
                ],
            ),
        ],
    )

    sql = QueryBuilderService.build_preview_sql(payload)

    assert 'SELECT t2."STATUS" AS "detail_secondary.STATUS"' in sql
    assert 'WHERE t1."FLAG" = \'Y\'' in sql
    assert 'ORDER BY t2."STATUS" ASC' in sql


def test_query_payload_rejects_duplicate_join_aliases() -> None:
    with pytest.raises(ValidationError):
        QueryPayload(
            engine="duckdb",
            table="master",
            joins=[
                JoinClause(
                    table="detail",
                    alias="detail_link",
                    join_type="LEFT",
                    conditions=[
                        JoinCondition(
                            left_column="master.ACCT_ID",
                            right_column="detail_link.ACCT_ID",
                        )
                    ],
                ),
                JoinClause(
                    table="other_detail",
                    alias="detail_link",
                    join_type="INNER",
                    conditions=[
                        JoinCondition(
                            left_column="master.ACCT_ID",
                            right_column="detail_link.ACCT_ID",
                        )
                    ],
                ),
            ],
        )


def test_oracle_report_sql_uses_grouped_select_instead_of_disabled_pivot() -> None:
    payload = QueryPayload(
        engine="oracle",
        table="MASTER",
        mode="REPORT",
        pivot={
            "rows": ["DIV_CODE"],
            "columns": ["DISCOM"],
            "values": "LOAD",
            "func": "SUM",
        },
        filters=[FilterCondition(column="STATUS", operator="=", value="ACTIVE")],
    )

    sql, params = QueryBuilderService.build_report_sql(payload)

    assert 'SELECT t0."DIV_CODE" AS "__REPORT_ROW_1__"' in sql
    assert 't0."DISCOM" AS "__REPORT_COLUMN_1__"' in sql
    assert 'SUM(t0."LOAD") AS "__REPORT_VALUE__"' in sql
    assert 'FROM "MASTER" t0' in sql
    assert 'WHERE t0."STATUS" = :1' in sql
    assert 'GROUP BY t0."DIV_CODE", t0."DISCOM" ORDER BY 1, 2' in sql
    assert params == ["ACTIVE"]


def test_report_sql_can_group_by_joined_columns() -> None:
    payload = QueryPayload(
        engine="oracle",
        table="MASTER",
        mode="REPORT",
        joins=[
            JoinClause(
                table="DETAIL",
                join_type="LEFT",
                conditions=[
                    JoinCondition(
                        left_column="MASTER.ACCT_ID",
                        right_column="DETAIL.ACCT_ID",
                    )
                ],
            )
        ],
        pivot={
            "rows": ["MASTER.DIV_CODE"],
            "columns": ["DETAIL.STATUS"],
            "values": "MASTER.LOAD",
            "func": "SUM",
        },
    )

    sql, params = QueryBuilderService.build_report_sql(payload)

    assert 'FROM "MASTER" t0 LEFT JOIN "DETAIL" t1 ON t0."ACCT_ID" = t1."ACCT_ID"' in sql
    assert 't0."DIV_CODE" AS "__REPORT_ROW_1__"' in sql
    assert 't1."STATUS" AS "__REPORT_COLUMN_1__"' in sql
    assert 'SUM(t0."LOAD") AS "__REPORT_VALUE__"' in sql
    assert params == []


def test_pivot_report_rows_returns_excel_style_columns() -> None:
    payload = QueryPayload(
        table="master",
        mode="REPORT",
        pivot={
            "rows": ["DIV_CODE"],
            "columns": ["DISCOM"],
            "values": "LOAD",
            "func": "SUM",
        },
    )

    columns, rows = QueryBuilderService.pivot_report_rows(
        payload,
        [
            ["DIV1", "PVVNL", 10],
            ["DIV1", "DVVNL", 20],
            ["DIV2", "PVVNL", 30],
        ],
    )

    assert columns == ["DIV_CODE", "PVVNL", "DVVNL"]
    assert rows == [["DIV1", 10, 20], ["DIV2", 30, None]]


def test_oracle_date_filter_uses_date_literal_in_preview_sql() -> None:
    payload = QueryPayload(
        engine="oracle",
        table="MERCADOS.CM_MASTER_DATA_MAR_2026_KESCO",
        mode="REPORT",
        pivot={
            "rows": ["DISCOM"],
            "columns": ["METER_READ_REMARK"],
            "values": "ACCT_ID",
            "func": "COUNT",
        },
        filters=[
            FilterCondition(column="OPR_FLG", operator="=", value="Y"),
            FilterCondition(column="LAST_BILL_DATE", operator=">=", value="2026-03-01"),
        ],
    )

    sql = QueryBuilderService.build_preview_sql(payload)

    assert "t0.\"OPR_FLG\" = 'Y'" in sql
    assert "t0.\"LAST_BILL_DATE\" >= DATE '2026-03-01'" in sql


def test_count_sql_uses_date_literals_without_params_for_date_columns() -> None:
    payload = QueryPayload(
        engine="oracle",
        table="MASTER",
        filters=[FilterCondition(column="LAST_BILL_DATE", operator=">=", value="2026-03-01")],
    )

    sql, params = QueryBuilderService.build_count_sql(payload)

    assert sql == "SELECT COUNT(*) FROM \"MASTER\" t0 WHERE t0.\"LAST_BILL_DATE\" >= DATE '2026-03-01'"
    assert params == []


def test_duckdb_date_like_column_uses_flexible_date_parsing_expression() -> None:
    payload = QueryPayload(
        engine="duckdb",
        table="master",
        filters=[FilterCondition(column="LAST_BILL_DATE", operator="=", value="2026-03-01")],
    )

    sql, params = QueryBuilderService.build_sql(payload)

    assert "COALESCE(" in sql
    assert "TRY_STRPTIME(CAST(t0.\"LAST_BILL_DATE\" AS VARCHAR), '%d-%b-%Y')" in sql
    assert "TRY_STRPTIME(CAST(t0.\"LAST_BILL_DATE\" AS VARCHAR), '%d-%m-%Y')" in sql
    assert "= DATE '2026-03-01'" in sql
    assert params == []


def test_duckdb_numeric_comparison_casts_varchar_like_column() -> None:
    payload = QueryPayload(
        engine="duckdb",
        table="master",
        filters=[FilterCondition(column="ARREAR", operator=">", value="1000")],
    )

    sql, params = QueryBuilderService.build_sql(payload)

    assert "TRY_CAST(t0.\"ARREAR\" AS DOUBLE) > ?" in sql
    assert params == [1000.0]


def test_duckdb_between_casts_varchar_like_column_when_bounds_are_numeric() -> None:
    payload = QueryPayload(
        engine="duckdb",
        table="master",
        filters=[FilterCondition(column="TOTAL_OUTSTANDING", operator="BETWEEN", value="100,200")],
    )

    sql, params = QueryBuilderService.build_sql(payload)

    assert "TRY_CAST(t0.\"TOTAL_OUTSTANDING\" AS DOUBLE) BETWEEN ? AND ?" in sql
    assert params == [100.0, 200.0]


def test_duckdb_keeps_string_comparison_when_filter_value_is_not_numeric() -> None:
    payload = QueryPayload(
        engine="duckdb",
        table="master",
        filters=[FilterCondition(column="DISCOM", operator="=", value="DVVNL")],
    )

    sql, params = QueryBuilderService.build_sql(payload)

    assert "TRY_CAST(" not in sql
    assert "t0.\"DISCOM\" = ?" in sql
    assert params == ["DVVNL"]


def test_add_ai_helper_comment_prefixes_sql_with_engine_and_source_context() -> None:
    sql = 'SELECT t0."id" FROM "employees" t0 LIMIT 5'

    preview_sql = QueryBuilderService.add_ai_helper_comment(sql, "duckdb", "builder")

    assert preview_sql.startswith("/* AI_CONTEXT")
    assert "engine: duckdb" in preview_sql
    assert "source_mode: builder" in preview_sql
    assert "limit_semantics: Uses LIMIT/OFFSET for pagination." in preview_sql
    assert preview_sql.endswith(sql)


def test_normalize_manual_sql_strips_ai_helper_comment_before_validation() -> None:
    sql_with_helper = """/* AI_CONTEXT
engine: oracle-marcadose
source_mode: manual
marcadose_read_only: true
*/
SELECT * FROM CUSTOMER
"""

    normalized = QueryBuilderService.normalize_manual_sql(sql_with_helper)

    assert normalized == "SELECT * FROM CUSTOMER"
