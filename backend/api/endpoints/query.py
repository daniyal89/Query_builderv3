"""
query.py — Engine-aware query execution endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import get_db_service, get_oracle_service
from backend.models.query import QueryPayload, QueryPreview, QueryResult
from backend.services.duckdb_service import DuckDBService
from backend.services.error_log_service import ErrorLogService
from backend.services.oracle_service import OracleService
from backend.services.query_builder_service import QueryBuilderService
from backend.services.marcadose_union_service import MarcadoseUnionService

router = APIRouter()
MAX_SQL_TEXT_LENGTH = 50000


def _log_query_error(
    endpoint: str,
    payload: QueryPayload,
    error: Exception | str,
    attempted_sql: str | None,
) -> None:
    ErrorLogService.append(
        {
            "endpoint": endpoint,
            "engine": payload.engine,
            "execution_mode": payload.execution_mode,
            "error": str(error),
            "attempted_sql": attempted_sql,
        }
    )


def _select_engine_service(
    payload: QueryPayload,
    duckdb: DuckDBService,
    oracle: OracleService,
) -> DuckDBService | OracleService:
    if payload.engine == "oracle":
        if not oracle.is_connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No Marcadose database connected. Use POST /api/oracle/connect first.",
            )
        return oracle

    if not duckdb.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No database connected. Use POST /api/duckdb/connect first.",
        )
    return duckdb


@router.post(
    "/query/preview",
    response_model=QueryPreview,
    summary="Preview SQL for the selected engine and query workflow",
)
async def preview_query(
    payload: QueryPayload,
    oracle: OracleService = Depends(get_oracle_service),
) -> QueryPreview:
    del oracle
    attempted_sql: str | None = None

    try:
        if payload.execution_mode == "sql":
            sql = QueryBuilderService.normalize_manual_sql(payload.sql or "")
            if len(sql) > MAX_SQL_TEXT_LENGTH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SQL text exceeds max length of {MAX_SQL_TEXT_LENGTH} characters.",
                )
            if payload.engine == "oracle":
                sql = MarcadoseUnionService.apply(sql, payload.marcadose_union)
                OracleService.ensure_read_only_sql(sql)
            attempted_sql = sql
            preview_sql = QueryBuilderService.add_ai_helper_comment(sql, payload.engine, "manual")
            return QueryPreview(sql=preview_sql, source_mode="sql", can_sync_builder=False)

        sql = QueryBuilderService.build_preview_sql(payload)
        if payload.engine == "oracle":
            sql = MarcadoseUnionService.apply(sql, payload.marcadose_union)
            OracleService.ensure_read_only_sql(sql)
        attempted_sql = sql
        preview_sql = QueryBuilderService.add_ai_helper_comment(sql, payload.engine, "builder")
        return QueryPreview(sql=preview_sql, source_mode="builder", can_sync_builder=True)
    except Exception as exc:
        _log_query_error("/api/query/preview", payload, exc, attempted_sql)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/query",
    response_model=QueryResult,
    summary="Execute a structured query against the selected engine",
)
async def execute_query(
    payload: QueryPayload,
    duckdb: DuckDBService = Depends(get_db_service),
    oracle: OracleService = Depends(get_oracle_service),
) -> QueryResult:
    attempted_sql: str | None = None
    try:
        service: DuckDBService | OracleService = _select_engine_service(payload, duckdb, oracle)

        if payload.execution_mode == "sql":
            executed_sql = QueryBuilderService.normalize_manual_sql(payload.sql or "")
            if len(executed_sql) > MAX_SQL_TEXT_LENGTH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"SQL text exceeds max length of {MAX_SQL_TEXT_LENGTH} characters.",
                )
            if payload.engine == "oracle":
                executed_sql = MarcadoseUnionService.apply(executed_sql, payload.marcadose_union)

            attempted_sql = executed_sql
            columns, rows, total = service.execute(executed_sql)

            if (
                payload.engine == "oracle"
                and payload.mode == "REPORT"
                and payload.marcadose_union
                and payload.marcadose_union.add_grand_total
            ):
                rows = MarcadoseUnionService.append_grand_total(columns, rows)
                total = len(rows)

            return QueryResult(
                columns=columns,
                rows=rows,
                total=total,
                truncated=False,
                executed_sql=executed_sql,
                source_mode="sql",
                message="Statement executed successfully." if not columns else "",
            )

        if payload.mode == "REPORT":
            report_sql, params = QueryBuilderService.build_report_sql(payload)

            if payload.engine == "oracle":
                executed_sql = MarcadoseUnionService.apply(
                    QueryBuilderService.normalize_manual_sql(
                        QueryBuilderService.render_sql(report_sql, params, payload.engine),
                    ),
                    payload.marcadose_union,
                )
                attempted_sql = executed_sql
                _, aggregate_rows, _ = service.execute(executed_sql)
            else:
                _, aggregate_rows, _ = service.execute(report_sql, params)
                executed_sql = QueryBuilderService.render_sql(report_sql, params, payload.engine)
                attempted_sql = executed_sql

            columns, rows = QueryBuilderService.pivot_report_rows(payload, aggregate_rows)

            if payload.marcadose_union and payload.marcadose_union.add_grand_total:
                rows = MarcadoseUnionService.append_grand_total(columns, rows)

            return QueryResult(
                columns=columns,
                rows=rows,
                total=len(rows),
                truncated=False,
                executed_sql=executed_sql,
                source_mode="builder",
                message="Report generated successfully." if not columns else "",
            )

        data_sql, params = QueryBuilderService.build_sql(payload)
        count_sql, count_params = QueryBuilderService.build_count_sql(payload)

        if payload.engine == "oracle":
            executed_sql = MarcadoseUnionService.apply(
                QueryBuilderService.normalize_manual_sql(
                    QueryBuilderService.render_sql(data_sql, params, payload.engine),
                ),
                payload.marcadose_union,
            )
            attempted_sql = executed_sql
            executed_count_sql = MarcadoseUnionService.build_total_count_sql(
                QueryBuilderService.normalize_manual_sql(
                    QueryBuilderService.render_sql(count_sql, count_params, payload.engine),
                ),
                payload.marcadose_union,
            )
            columns, rows, _ = service.execute(executed_sql)
            attempted_sql = executed_count_sql
            _, count_rows, _ = service.execute(executed_count_sql)
        else:
            columns, rows, _ = service.execute(data_sql, params)
            _, count_rows, _ = service.execute(count_sql, count_params)
            executed_sql = QueryBuilderService.render_sql(data_sql, params, payload.engine)
            attempted_sql = executed_sql

        total = count_rows[0][0] if count_rows else 0

        return QueryResult(
            columns=columns,
            rows=rows,
            total=total,
            truncated=payload.limit_rows > 0 and len(rows) == payload.limit_rows,
            executed_sql=executed_sql,
            source_mode="builder",
        )
    except HTTPException as exc:
        _log_query_error("/api/query", payload, exc, attempted_sql)
        raise
    except Exception as exc:
        _log_query_error("/api/query", payload, exc, attempted_sql)
        detail: dict[str, str] | str = str(exc)
        if attempted_sql:
            detail = {"message": str(exc), "executed_sql": attempted_sql}
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
