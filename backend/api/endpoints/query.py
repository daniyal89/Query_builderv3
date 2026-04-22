"""
query.py â€” Engine-aware query execution endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import get_db_service, get_oracle_service
from backend.models.query import QueryPayload, QueryPreview, QueryResult
from backend.services.duckdb_service import DuckDBService
from backend.services.oracle_service import OracleService
from backend.services.query_builder_service import QueryBuilderService

router = APIRouter()


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

    try:
        if payload.execution_mode == "sql":
            sql = QueryBuilderService.normalize_manual_sql(payload.sql or "")
            if payload.engine == "oracle":
                OracleService.ensure_read_only_sql(sql)
            return QueryPreview(sql=sql, source_mode="sql", can_sync_builder=False)

        sql = QueryBuilderService.build_preview_sql(payload)
        return QueryPreview(sql=sql, source_mode="builder", can_sync_builder=True)
    except Exception as exc:
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
    try:
        service: DuckDBService | OracleService = _select_engine_service(payload, duckdb, oracle)
        if payload.execution_mode == "sql":
            executed_sql = QueryBuilderService.normalize_manual_sql(payload.sql or "")
            columns, rows, total = service.execute(executed_sql)
            return QueryResult(
                columns=columns,
                rows=rows,
                total=total,
                truncated=False,
                executed_sql=executed_sql,
                source_mode="sql",
                message="Statement executed successfully." if not columns else "",
            )

        data_sql, params = QueryBuilderService.build_sql(payload)
        count_sql, count_params = QueryBuilderService.build_count_sql(payload)
        columns, rows, _ = service.execute(data_sql, params)
        _, count_rows, _ = service.execute(count_sql, count_params)
        total = count_rows[0][0] if count_rows else 0
        executed_sql = QueryBuilderService.render_sql(data_sql, params, payload.engine)

        return QueryResult(
            columns=columns,
            rows=rows,
            total=total,
            truncated=payload.limit_rows > 0 and len(rows) == payload.limit_rows,
            executed_sql=executed_sql,
            source_mode="builder",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
