"""
test_query_builder_service.py â€” Unit tests for QueryBuilderService.
"""

from backend.models.query import FilterCondition, QueryPayload
from backend.services.query_builder_service import QueryBuilderService


def build_payload(*filters: FilterCondition) -> QueryPayload:
    return QueryPayload(table="master", filters=list(filters))


def test_build_where_clause_supports_not_in_from_comma_string() -> None:
    payload = build_payload(FilterCondition(column="DISCOM", operator="NOT IN", value="A, B, C"))

    sql, params = QueryBuilderService.build_sql(payload)

    assert 'WHERE "DISCOM" NOT IN (?, ?, ?)' in sql
    assert params == ["A", "B", "C"]


def test_build_where_clause_supports_between_from_text_input() -> None:
    payload = build_payload(FilterCondition(column="LOAD", operator="BETWEEN", value="10, 20"))

    sql, params = QueryBuilderService.build_sql(payload)

    assert 'WHERE "LOAD" BETWEEN ? AND ?' in sql
    assert params == ["10", "20"]


def test_build_where_clause_supports_contains_with_escaped_like_pattern() -> None:
    payload = build_payload(FilterCondition(column="ACCOUNT_NAME", operator="CONTAINS", value="50%_done"))

    sql, params = QueryBuilderService.build_sql(payload)

    assert 'WHERE "ACCOUNT_NAME" LIKE ? ESCAPE' in sql
    assert params == [r"%50\%\_done%"]


def test_build_where_clause_supports_null_checks_without_params() -> None:
    payload = build_payload(FilterCondition(column="DIV_CODE", operator="IS NOT NULL", value=None))

    sql, params = QueryBuilderService.build_sql(payload)

    assert 'WHERE "DIV_CODE" IS NOT NULL' in sql
    assert params == []


def test_build_where_clause_uses_oracle_bind_variables_for_oracle_engine() -> None:
    payload = QueryPayload(
        engine="oracle",
        table="MASTER",
        filters=[FilterCondition(column="DISCOM", operator="IN", value=["A", "B"])],
        limit_rows=25,
        offset=10,
    )

    sql, params = QueryBuilderService.build_sql(payload)

    assert 'WHERE "DISCOM" IN (:1, :2)' in sql
    assert "OFFSET 10 ROWS FETCH NEXT 25 ROWS ONLY" in sql
    assert params == ["A", "B"]


def test_build_preview_sql_renders_literal_values_for_editor() -> None:
    payload = QueryPayload(
        table="master",
        filters=[FilterCondition(column="DISCOM", operator="IN", value=["A", "B"])],
    )

    preview_sql = QueryBuilderService.build_preview_sql(payload)

    assert 'WHERE "DISCOM" IN (\'A\', \'B\')' in preview_sql
    assert "LIMIT 1000" in preview_sql


def test_normalize_manual_sql_rejects_multiple_statements() -> None:
    try:
        QueryBuilderService.normalize_manual_sql("SELECT 1; SELECT 2")
    except ValueError as exc:
        assert "single SQL statement" in str(exc)
    else:
        raise AssertionError("Expected normalize_manual_sql to reject multiple statements.")


def test_render_sql_keeps_oracle_placeholder_indexes_intact() -> None:
    sql = 'SELECT * FROM "MASTER" WHERE "C1" IN (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10)'
    params = [str(index) for index in range(1, 11)]

    rendered = QueryBuilderService.render_sql(sql, params, "oracle")

    assert "('1', '2', '3', '4', '5', '6', '7', '8', '9', '10')" in rendered
