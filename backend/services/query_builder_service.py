"""
query_builder_service.py — Translates structured query payloads into SQL.

Converts the frontend's QueryPayload (table, columns, filters, sort, limit)
into a safe, parameterized SQL string for execution by DuckDBService.
"""

from backend.models.query import QueryPayload


class QueryBuilderService:
    """Stateless service that builds parameterized SQL from QueryPayload objects."""

    @staticmethod
    def _build_where_clause(filters: list) -> tuple[str, list]:
        where_clauses = []
        params = []
        for f in filters:
            col = f'"{f.column}"'
            op = f.operator
            if op in ("IS NULL", "IS NOT NULL"):
                where_clauses.append(f"{col} {op}")
            elif op == "IN":
                if not isinstance(f.value, list) or not f.value:
                    where_clauses.append("1=0")
                else:
                    placeholders = ", ".join(["?"] * len(f.value))
                    where_clauses.append(f"{col} {op} ({placeholders})")
                    params.extend(f.value)
            else:
                where_clauses.append(f"{col} {op} ?")
                params.append(f.value)
        return " AND ".join(where_clauses) if where_clauses else "", params

    @staticmethod
    def build_sql(payload: QueryPayload) -> tuple[str, list]:
        """Convert a QueryPayload into a parameterized SQL string supporting two modes."""
        
        where_str, params = QueryBuilderService._build_where_clause(payload.filters)
        where_clause = f" WHERE {where_str}" if where_str else ""

        if payload.mode == "REPORT" and payload.pivot:
            # PIVOT Mode Execution
            p = payload.pivot
            
            # PIVOT requires an ON clause, USING clause, and GROUP BY clause.
            # DuckDB subquery allows us to apply filters first.
            
            # Subquery to filter raw data
            subquery = f'SELECT * FROM "{payload.table}"'
            if where_clause:
                subquery += where_clause
                
            cols_to_pivot = ", ".join([f"'{c}'" for c in p.columns]) if p.columns else ""
            rows_to_group = ", ".join([f'"{r}"' for r in p.rows]) if p.rows else ""
            
            sql = f"""
            PIVOT (
                {subquery}
            )
            """
            
            if cols_to_pivot:
                sql += f" ON {cols_to_pivot}"
            
            sql += f' USING {p.func}("{p.values}")'
            
            if rows_to_group:
                sql += f" GROUP BY {rows_to_group}"

            return sql, params

        else:
            # LIST Mode Execution (Legacy / standard selection)
            select_cols = [f'"{c}"' for c in payload.select] if payload.select and payload.select != ["*"] else []
            select_clause = ", ".join(select_cols) if select_cols else "*"
            
            from_clause = f'"{payload.table}"'
            
            sort_clauses = []
            for s in payload.sort:
                sort_clauses.append(f'"{s.column}" {s.direction}')
            order_str = ", ".join(sort_clauses) if sort_clauses else ""
            
            sql = f"SELECT {select_clause} FROM {from_clause}"
            if where_clause:
                sql += where_clause
            if order_str:
                sql += f" ORDER BY {order_str}"
                
            if payload.limit_rows > 0:
                sql += f" LIMIT {payload.limit_rows}"
            
            if payload.offset > 0:
                sql += f" OFFSET {payload.offset}"
                
            return sql, params

    @staticmethod
    def build_count_sql(payload: QueryPayload) -> tuple[str, list]:
        """Convert a QueryPayload into a parameterized SQL string for counting total rows.

        Args:
            payload: The structured query definition from the frontend.

        Returns:
            Tuple of (count_sql_string, parameter_values).
        """
        from_clause = f'"{payload.table}"'
        where_str, params = QueryBuilderService._build_where_clause(payload.filters)
        
        sql = f"SELECT COUNT(*) FROM {from_clause}"
        if where_str:
            sql += f" WHERE {where_str}"
            
        return sql, params
