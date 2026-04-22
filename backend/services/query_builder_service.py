"""
query_builder_service.py â€” Translates structured query payloads into engine-specific SQL.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from backend.models.connection import EngineName
from backend.models.query import QueryPayload


class QueryBuilderService:
    """Stateless service that builds parameterized SQL from QueryPayload objects."""

    NO_VALUE_OPERATORS = {"IS NULL", "IS NOT NULL"}
    LIST_OPERATORS = {"IN", "NOT IN"}
    RANGE_OPERATORS = {"BETWEEN", "NOT BETWEEN"}
    FRIENDLY_TEXT_OPERATORS = {"CONTAINS", "NOT CONTAINS", "STARTS WITH", "ENDS WITH"}

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
        return f"'{str(value).replace(\"'\", \"''\")}'"

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
    def _build_where_clause(filters: list, engine: EngineName) -> tuple[str, list[Any]]:
        where_clauses: list[str] = []
        params: list[Any] = []

        for filter_condition in filters:
            column = f'"{filter_condition.column}"'
            operator = filter_condition.operator

            if operator in QueryBuilderService.NO_VALUE_OPERATORS:
                where_clauses.append(f"{column} {operator}")
                continue

            if operator in QueryBuilderService.LIST_OPERATORS:
                values = QueryBuilderService._normalize_list_value(filter_condition.value)
                if not values:
                    raise ValueError(f"{operator} filters need at least one value.")
                placeholders = ", ".join(
                    QueryBuilderService._build_placeholders(engine, len(values), len(params) + 1)
                )
                where_clauses.append(f"{column} {operator} ({placeholders})")
                params.extend(values)
                continue

            if operator in QueryBuilderService.RANGE_OPERATORS:
                start, end = QueryBuilderService._normalize_range_value(filter_condition.value)
                left_placeholder = QueryBuilderService._placeholder(engine, len(params) + 1)
                right_placeholder = QueryBuilderService._placeholder(engine, len(params) + 2)
                where_clauses.append(f"{column} {operator} {left_placeholder} AND {right_placeholder}")
                params.extend([start, end])
                continue

            if operator in QueryBuilderService.FRIENDLY_TEXT_OPERATORS:
                sql_operator, pattern = QueryBuilderService._build_text_pattern(operator, filter_condition.value)
                placeholder = QueryBuilderService._placeholder(engine, len(params) + 1)
                where_clauses.append(f"{column} {sql_operator} {placeholder} ESCAPE '\\'")
                params.append(pattern)
                continue

            placeholder = QueryBuilderService._placeholder(engine, len(params) + 1)
            where_clauses.append(f"{column} {operator} {placeholder}")
            params.append(filter_condition.value)

        return " AND ".join(where_clauses) if where_clauses else "", params

    @staticmethod
    def build_sql(payload: QueryPayload) -> tuple[str, list[Any]]:
        """Convert a QueryPayload into a parameterized SQL string supporting two modes."""

        engine = payload.engine
        where_str, params = QueryBuilderService._build_where_clause(payload.filters, engine)
        where_clause = f" WHERE {where_str}" if where_str else ""

        if payload.mode == "REPORT" and payload.pivot:
            if engine == "oracle":
                raise ValueError("Report mode for Marcadose is not implemented yet.")

            pivot = payload.pivot
            subquery = f'SELECT * FROM "{payload.table}"'
            if where_clause:
                subquery += where_clause

            cols_to_pivot = ", ".join([f"'{column}'" for column in pivot.columns]) if pivot.columns else ""
            rows_to_group = ", ".join([f'"{row}"' for row in pivot.rows]) if pivot.rows else ""

            sql = f"""
            PIVOT (
                {subquery}
            )
            """
            if cols_to_pivot:
                sql += f" ON {cols_to_pivot}"
            sql += f' USING {pivot.func}("{pivot.values}")'
            if rows_to_group:
                sql += f" GROUP BY {rows_to_group}"
            return sql, params

        select_cols = [f'"{column}"' for column in payload.select] if payload.select and payload.select != ["*"] else []
        select_clause = ", ".join(select_cols) if select_cols else "*"
        from_clause = f'"{payload.table}"'
        sort_clauses = [f'"{sort.column}" {sort.direction}' for sort in payload.sort]
        order_str = ", ".join(sort_clauses) if sort_clauses else ""

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

        from_clause = f'"{payload.table}"'
        where_str, params = QueryBuilderService._build_where_clause(payload.filters, payload.engine)
        sql = f"SELECT COUNT(*) FROM {from_clause}"
        if where_str:
            sql += f" WHERE {where_str}"
        return sql, params

    @staticmethod
    def build_preview_sql(payload: QueryPayload) -> str:
        """Return rendered SQL text for the current builder state."""

        sql, params = QueryBuilderService.build_sql(payload)
        return QueryBuilderService.render_sql(sql, params, payload.engine)
