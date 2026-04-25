"""
query_builder_service.py — Translates structured query payloads into engine-specific SQL.
"""

from __future__ import annotations

from datetime import date, datetime, time
import re
from typing import Any

from backend.models.connection import EngineName
from backend.models.query import QueryPayload


class QueryBuilderService:
    """Stateless service that builds parameterized SQL from QueryPayload objects."""

    NO_VALUE_OPERATORS = {"IS NULL", "IS NOT NULL"}
    LIST_OPERATORS = {"IN", "NOT IN"}
    RANGE_OPERATORS = {"BETWEEN", "NOT BETWEEN"}
    FRIENDLY_TEXT_OPERATORS = {"CONTAINS", "NOT CONTAINS", "STARTS WITH", "ENDS WITH"}
    NUMERIC_COMPARISON_OPERATORS = {">", "<", ">=", "<="}
    REPORT_VALUE_ALIAS = "__REPORT_VALUE__"

    @staticmethod
    def _normalize_list_value(value: Any) -> list[Any]:
        if isinstance(value, (list, tuple, set)):
            return [item for item in value if item not in (None, "")]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if value in (None, ""):
            return []
        return [value]

    @staticmethod
    def _normalize_range_value(value: Any) -> tuple[Any, Any]:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return value[0], value[1]
        if isinstance(value, str):
            parts = [item.strip() for item in value.split(",")]
            if len(parts) == 2 and all(parts):
                return parts[0], parts[1]
        raise ValueError("BETWEEN filters need two values separated by a comma.")

    @staticmethod
    def _escape_like_value(value: Any) -> str:
        text = str(value)
        return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @staticmethod
    def _build_text_pattern(operator: str, value: Any) -> tuple[str, str]:
        escaped = QueryBuilderService._escape_like_value(value)
        if operator == "CONTAINS":
            return "LIKE", f"%{escaped}%"
        if operator == "NOT CONTAINS":
            return "NOT LIKE", f"%{escaped}%"
        if operator == "STARTS WITH":
            return "LIKE", f"{escaped}%"
        if operator == "ENDS WITH":
            return "LIKE", f"%{escaped}"
        raise ValueError(f"Unsupported friendly text operator: {operator}")

    @staticmethod
    def _is_date_like_column(column_name: str) -> bool:
        return bool(re.search(r"(DATE|TIME|TIMESTAMP)", column_name.upper()))

    @staticmethod
    def _normalize_date_literal_value(value: Any) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return text
        raise ValueError(
            f"Date filters require YYYY-MM-DD values so SQL can use DATE literals. Received '{value}'."
        )

    @staticmethod
    def _date_literal(value: Any) -> str:
        normalized = QueryBuilderService._normalize_date_literal_value(value)
        return f"DATE '{normalized}'"

    @staticmethod
    def _to_float_if_numeric(value: Any) -> float | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                return None
        return None

    @staticmethod
    def _placeholder(engine: EngineName, index: int) -> str:
        return "?" if engine == "duckdb" else f":{index}"

    @staticmethod
    def _build_placeholders(engine: EngineName, count: int, start_index: int) -> list[str]:
        return [QueryBuilderService._placeholder(engine, start_index + offset) for offset in range(count)]

    @staticmethod
    def _sql_literal(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, datetime):
            return f"'{value.isoformat(sep=' ', timespec='seconds')}'"
        if isinstance(value, (date, time)):
            return f"'{value.isoformat()}'"
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

    @staticmethod
    def _replace_first(text: str, old: str, new: str) -> str:
        return text.replace(old, new, 1)

    @staticmethod
    def render_sql(sql: str, params: list[Any], engine: EngineName) -> str:
        rendered = sql
        if engine == "duckdb":
            for value in params:
                rendered = QueryBuilderService._replace_first(
                    rendered,
                    "?",
                    QueryBuilderService._sql_literal(value),
                )
            return rendered

        for index in range(len(params), 0, -1):
            rendered = rendered.replace(
                f":{index}",
                QueryBuilderService._sql_literal(params[index - 1]),
            )
        return rendered

    @staticmethod
    def normalize_manual_sql(sql: str) -> str:
        normalized = sql.strip()
        if not normalized:
            raise ValueError("SQL cannot be empty.")
        normalized = normalized[:-1].rstrip() if normalized.endswith(";") else normalized
        if ";" in normalized:
            raise ValueError("Only a single SQL statement can be executed at a time.")
        return normalized

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        stripped = identifier.strip()
        if not stripped:
            raise ValueError("Identifiers cannot be empty.")
        return f'"{stripped.replace(chr(34), chr(34) * 2)}"'

    @staticmethod
    def _quote_relation_identifier(identifier: str) -> str:
        parts = [part.strip() for part in identifier.strip().split(".") if part.strip()]
        if not parts:
            raise ValueError("Table names cannot be empty.")
        return ".".join(QueryBuilderService._quote_identifier(part) for part in parts)

    @staticmethod
    def _split_column_ref(
        column_ref: str,
        default_table: str,
        known_tables: list[str] | None = None,
    ) -> tuple[str, str]:
        normalized = column_ref.strip()
        if not normalized:
            raise ValueError("Column references cannot be empty.")
        if known_tables:
            for table_name in sorted(known_tables, key=len, reverse=True):
                prefix = f"{table_name}."
                if normalized.startswith(prefix):
                    column_name = normalized[len(prefix) :].strip()
                    if not column_name:
                        raise ValueError(f"Invalid column reference '{column_ref}'.")
                    return table_name.strip(), column_name
        if "." in normalized:
            table_name, column_name = normalized.rsplit(".", 1)
        else:
            table_name, column_name = default_table, normalized
        if not table_name.strip() or not column_name.strip():
            raise ValueError(f"Invalid column reference '{column_ref}'.")
        return table_name.strip(), column_name.strip()

    @staticmethod
    def _build_alias_map(payload: QueryPayload) -> dict[str, str]:
        aliases = {payload.table: "t0"}
        for index, join in enumerate(payload.joins, start=1):
            if join.table in aliases:
                raise ValueError(f"Joined table '{join.table}' is duplicated.")
            aliases[join.table] = f"t{index}"
        return aliases

    @staticmethod
    def _resolve_column_expression(
        column_ref: str,
        alias_by_table: dict[str, str],
        default_table: str,
    ) -> tuple[str, str, str]:
        table_name, column_name = QueryBuilderService._split_column_ref(
            column_ref,
            default_table,
            list(alias_by_table.keys()),
        )
        alias = alias_by_table.get(table_name)
        if alias is None:
            raise ValueError(f"Unknown table reference '{table_name}' in column '{column_ref}'.")
        return table_name, column_name, f"{alias}.{QueryBuilderService._quote_identifier(column_name)}"

    @staticmethod
    def _build_from_clause(payload: QueryPayload, alias_by_table: dict[str, str]) -> str:
        base_alias = alias_by_table[payload.table]
        clauses = [f'{QueryBuilderService._quote_relation_identifier(payload.table)} {base_alias}']
        available_tables = {payload.table}

        for join in payload.joins:
            join_alias = alias_by_table[join.table]
            join_conditions: list[str] = []

            for condition in join.conditions:
                left_table, _, left_expr = QueryBuilderService._resolve_column_expression(
                    condition.left_column,
                    alias_by_table,
                    payload.table,
                )
                right_table, _, right_expr = QueryBuilderService._resolve_column_expression(
                    condition.right_column,
                    alias_by_table,
                    join.table,
                )

                if left_table == join.table or left_table not in available_tables:
                    raise ValueError(
                        f"Join '{join.table}' can only reference the base table or earlier joins on the left side."
                    )
                if right_table != join.table:
                    raise ValueError(
                        f"Join '{join.table}' must match against its own table on the right side of each condition."
                    )

                join_conditions.append(f"{left_expr} = {right_expr}")

            clauses.append(
                f"{join.join_type} JOIN {QueryBuilderService._quote_relation_identifier(join.table)} {join_alias} "
                f"ON {' AND '.join(join_conditions)}"
            )
            available_tables.add(join.table)

        return " ".join(clauses)

    @staticmethod
    def _build_select_clause(payload: QueryPayload, alias_by_table: dict[str, str]) -> str:
        if not payload.select or payload.select == ["*"]:
            if payload.joins:
                return ", ".join(f"{alias}.*" for alias in alias_by_table.values())
            return "*"

        select_expressions: list[str] = []
        for column_ref in payload.select:
            table_name, column_name, expression = QueryBuilderService._resolve_column_expression(
                column_ref,
                alias_by_table,
                payload.table,
            )
            if payload.joins:
                alias_name = f"{table_name}.{column_name}"
                select_expressions.append(f"{expression} AS {QueryBuilderService._quote_identifier(alias_name)}")
            else:
                select_expressions.append(expression)
        return ", ".join(select_expressions)

    @staticmethod
    def _build_where_clause(
        filters: list,
        engine: EngineName,
        alias_by_table: dict[str, str],
        default_table: str,
    ) -> tuple[str, list[Any]]:
        where_clauses: list[str] = []
        params: list[Any] = []

        for filter_condition in filters:
            _, column_name, column_expr = QueryBuilderService._resolve_column_expression(
                filter_condition.column,
                alias_by_table,
                default_table,
            )
            operator = filter_condition.operator
            use_date_literals = QueryBuilderService._is_date_like_column(column_name)
            numeric_value = QueryBuilderService._to_float_if_numeric(filter_condition.value)
            should_use_numeric_cast = (
                engine == "duckdb"
                and not use_date_literals
                and operator in QueryBuilderService.NUMERIC_COMPARISON_OPERATORS
                and numeric_value is not None
            )
            filter_column_expr = (
                f"TRY_CAST({column_expr} AS DOUBLE)" if should_use_numeric_cast else column_expr
            )

            if operator in QueryBuilderService.NO_VALUE_OPERATORS:
                where_clauses.append(f"{column_expr} {operator}")
                continue

            if operator in QueryBuilderService.LIST_OPERATORS:
                values = QueryBuilderService._normalize_list_value(filter_condition.value)
                if not values:
                    raise ValueError(f"{operator} filters need at least one value.")
                if use_date_literals:
                    literals = ", ".join(QueryBuilderService._date_literal(value) for value in values)
                    where_clauses.append(f"{column_expr} {operator} ({literals})")
                else:
                    placeholders = ", ".join(
                        QueryBuilderService._build_placeholders(engine, len(values), len(params) + 1)
                    )
                    where_clauses.append(f"{column_expr} {operator} ({placeholders})")
                    params.extend(values)
                continue

            if operator in QueryBuilderService.RANGE_OPERATORS:
                start, end = QueryBuilderService._normalize_range_value(filter_condition.value)
                if use_date_literals:
                    where_clauses.append(
                        f"{filter_column_expr} {operator} {QueryBuilderService._date_literal(start)} AND {QueryBuilderService._date_literal(end)}"
                    )
                else:
                    start_numeric = QueryBuilderService._to_float_if_numeric(start)
                    end_numeric = QueryBuilderService._to_float_if_numeric(end)
                    should_use_range_numeric_cast = (
                        engine == "duckdb"
                        and start_numeric is not None
                        and end_numeric is not None
                    )
                    range_column_expr = (
                        f"TRY_CAST({column_expr} AS DOUBLE)" if should_use_range_numeric_cast else column_expr
                    )
                    left_placeholder = QueryBuilderService._placeholder(engine, len(params) + 1)
                    right_placeholder = QueryBuilderService._placeholder(engine, len(params) + 2)
                    where_clauses.append(
                        f"{range_column_expr} {operator} {left_placeholder} AND {right_placeholder}"
                    )
                    params.extend(
                        [
                            start_numeric if should_use_range_numeric_cast else start,
                            end_numeric if should_use_range_numeric_cast else end,
                        ]
                    )
                continue

            if operator in QueryBuilderService.FRIENDLY_TEXT_OPERATORS:
                sql_operator, pattern = QueryBuilderService._build_text_pattern(operator, filter_condition.value)
                placeholder = QueryBuilderService._placeholder(engine, len(params) + 1)
                where_clauses.append(f"{column_expr} {sql_operator} {placeholder} ESCAPE '\\'")
                params.append(pattern)
                continue

            if use_date_literals:
                where_clauses.append(
                    f"{filter_column_expr} {operator} {QueryBuilderService._date_literal(filter_condition.value)}"
                )
            else:
                placeholder = QueryBuilderService._placeholder(engine, len(params) + 1)
                where_clauses.append(f"{filter_column_expr} {operator} {placeholder}")
                params.append(numeric_value if should_use_numeric_cast else filter_condition.value)

        return " AND ".join(where_clauses) if where_clauses else "", params

    @staticmethod
    def _build_order_clause(payload: QueryPayload, alias_by_table: dict[str, str]) -> str:
        if not payload.sort:
            return ""

        sort_clauses = []
        for sort in payload.sort:
            _, _, column_expr = QueryBuilderService._resolve_column_expression(
                sort.column,
                alias_by_table,
                payload.table,
            )
            sort_clauses.append(f"{column_expr} {sort.direction}")
        return ", ".join(sort_clauses)

    @staticmethod
    def _report_fields(payload: QueryPayload) -> tuple[list[str], list[str], str]:
        if payload.mode != "REPORT" or not payload.pivot:
            raise ValueError("Report configuration is required for Generate Report mode.")

        row_fields = [field.strip() for field in payload.pivot.rows if field.strip()]
        column_fields = [field.strip() for field in payload.pivot.columns if field.strip()]
        value_field = payload.pivot.values.strip()
        if not value_field:
            raise ValueError("Select a Values field before generating a report.")
        return row_fields, column_fields, value_field

    @staticmethod
    def build_report_sql(payload: QueryPayload) -> tuple[str, list[Any]]:
        """Build the grouped aggregate SQL that feeds the Python pivot renderer.

        Oracle does not support fully dynamic PIVOT columns without XML output, so
        both engines use the same safe pattern: aggregate in SQL, then reshape the
        grouped result into a table before returning it to the UI.
        """

        row_fields, column_fields, value_field = QueryBuilderService._report_fields(payload)
        alias_by_table = QueryBuilderService._build_alias_map(payload)
        from_clause = QueryBuilderService._build_from_clause(payload, alias_by_table)
        where_str, params = QueryBuilderService._build_where_clause(
            payload.filters,
            payload.engine,
            alias_by_table,
            payload.table,
        )

        select_expressions: list[str] = []
        group_expressions: list[str] = []

        for index, field in enumerate(row_fields, start=1):
            _, _, expression = QueryBuilderService._resolve_column_expression(field, alias_by_table, payload.table)
            select_expressions.append(f'{expression} AS {QueryBuilderService._quote_identifier(f"__REPORT_ROW_{index}__")}')
            group_expressions.append(expression)

        for index, field in enumerate(column_fields, start=1):
            _, _, expression = QueryBuilderService._resolve_column_expression(field, alias_by_table, payload.table)
            select_expressions.append(
                f'{expression} AS {QueryBuilderService._quote_identifier(f"__REPORT_COLUMN_{index}__")}'
            )
            group_expressions.append(expression)

        _, _, value_expression = QueryBuilderService._resolve_column_expression(value_field, alias_by_table, payload.table)
        aggregate_expression = f"{payload.pivot.func}({value_expression})"
        select_expressions.append(
            f"{aggregate_expression} AS {QueryBuilderService._quote_identifier(QueryBuilderService.REPORT_VALUE_ALIAS)}"
        )

        sql = f"SELECT {', '.join(select_expressions)} FROM {from_clause}"
        if where_str:
            sql += f" WHERE {where_str}"
        if group_expressions:
            sql += f" GROUP BY {', '.join(group_expressions)}"
            sql += f" ORDER BY {', '.join(str(index) for index in range(1, len(group_expressions) + 1))}"
        return sql, params

    @staticmethod
    def _format_report_value(value: Any) -> str:
        return "(null)" if value is None else str(value)

    @staticmethod
    def _format_pivot_heading(column_fields: list[str], values: tuple[Any, ...]) -> str:
        if len(column_fields) == 1:
            return QueryBuilderService._format_report_value(values[0])
        return " | ".join(
            f"{field}={QueryBuilderService._format_report_value(value)}"
            for field, value in zip(column_fields, values)
        )

    @staticmethod
    def pivot_report_rows(payload: QueryPayload, aggregate_rows: list[list[Any]]) -> tuple[list[str], list[list[Any]]]:
        """Reshape grouped aggregate rows into an Excel-style pivot table."""

        row_fields, column_fields, value_field = QueryBuilderService._report_fields(payload)
        value_label = f"{payload.pivot.func}({value_field})"
        value_index = len(row_fields) + len(column_fields)

        if not column_fields:
            columns = [*row_fields, value_label]
            rows = [list(row[: len(row_fields)]) + [row[value_index]] for row in aggregate_rows]
            return columns, rows

        pivot_labels: list[str] = []
        seen_pivot_labels: set[str] = set()
        rows_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
        row_order: list[tuple[Any, ...]] = []

        for aggregate_row in aggregate_rows:
            row_key = tuple(aggregate_row[: len(row_fields)])
            pivot_key = tuple(aggregate_row[len(row_fields) : value_index])
            pivot_label = QueryBuilderService._format_pivot_heading(column_fields, pivot_key)

            if pivot_label not in seen_pivot_labels:
                seen_pivot_labels.add(pivot_label)
                pivot_labels.append(pivot_label)

            if row_key not in rows_by_key:
                row_order.append(row_key)
                rows_by_key[row_key] = {}

            rows_by_key[row_key][pivot_label] = aggregate_row[value_index]

        if not pivot_labels:
            return [*row_fields, value_label], []

        columns = [*row_fields, *pivot_labels]
        rows = [
            [*row_key, *[rows_by_key[row_key].get(pivot_label) for pivot_label in pivot_labels]]
            for row_key in row_order
        ]
        return columns, rows

    @staticmethod
    def build_sql(payload: QueryPayload) -> tuple[str, list[Any]]:
        """Convert a QueryPayload into a parameterized SQL string supporting two modes."""

        if payload.mode == "REPORT":
            return QueryBuilderService.build_report_sql(payload)

        engine = payload.engine
        alias_by_table = QueryBuilderService._build_alias_map(payload)
        from_clause = QueryBuilderService._build_from_clause(payload, alias_by_table)
        where_str, params = QueryBuilderService._build_where_clause(
            payload.filters,
            engine,
            alias_by_table,
            payload.table,
        )
        where_clause = f" WHERE {where_str}" if where_str else ""

        select_clause = QueryBuilderService._build_select_clause(payload, alias_by_table)
        order_str = QueryBuilderService._build_order_clause(payload, alias_by_table)

        sql = f"SELECT {select_clause} FROM {from_clause}"
        if where_clause:
            sql += where_clause
        if order_str:
            sql += f" ORDER BY {order_str}"

        if engine == "duckdb":
            if payload.limit_rows > 0:
                sql += f" LIMIT {payload.limit_rows}"
            if payload.offset > 0:
                sql += f" OFFSET {payload.offset}"
        else:
            if payload.offset > 0:
                sql += f" OFFSET {payload.offset} ROWS"
            if payload.limit_rows > 0:
                if payload.offset > 0:
                    sql += f" FETCH NEXT {payload.limit_rows} ROWS ONLY"
                else:
                    sql += f" FETCH FIRST {payload.limit_rows} ROWS ONLY"

        return sql, params

    @staticmethod
    def build_count_sql(payload: QueryPayload) -> tuple[str, list[Any]]:
        """Convert a QueryPayload into a parameterized SQL string for counting total rows."""

        alias_by_table = QueryBuilderService._build_alias_map(payload)
        from_clause = QueryBuilderService._build_from_clause(payload, alias_by_table)
        where_str, params = QueryBuilderService._build_where_clause(
            payload.filters,
            payload.engine,
            alias_by_table,
            payload.table,
        )
        sql = f"SELECT COUNT(*) FROM {from_clause}"
        if where_str:
            sql += f" WHERE {where_str}"
        return sql, params

    @staticmethod
    def build_preview_sql(payload: QueryPayload) -> str:
        """Return rendered SQL text for the current builder state."""

        sql, params = QueryBuilderService.build_sql(payload)
        return QueryBuilderService.render_sql(sql, params, payload.engine)
