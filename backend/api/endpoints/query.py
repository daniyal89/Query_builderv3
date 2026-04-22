"""
query.py — Query execution endpoint.

POST /api/query
    Receives a structured query payload from the visual query builder,
    translates it to parameterized SQL, executes against DuckDB, and
    returns the tabular result set.
"""

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_connected_db
from backend.models.query import QueryPayload, QueryResult
from backend.services.duckdb_service import DuckDBService
from backend.services.query_builder_service import QueryBuilderService

router = APIRouter()


@router.post(
    "/query",
    response_model=QueryResult,
    summary="Execute a structured query against the connected database",
)
async def execute_query(
    payload: QueryPayload,
    db: DuckDBService = Depends(get_connected_db),
) -> QueryResult:
    """Translate the structured query payload into SQL and execute it.

    Args:
        payload: QueryPayload with table, select, filters, sort, limit, offset.

    Returns:
        QueryResult containing column names, row data, total count, and truncation flag.

    Raises:
        HTTPException 400: If the query payload references invalid tables or columns.
        HTTPException 503: If no database is currently connected.
    """
    try:
        data_sql, params = QueryBuilderService.build_sql(payload)
        count_sql, count_params = QueryBuilderService.build_count_sql(payload)
        
        columns, rows, _ = db.execute(data_sql, params)
        _, count_rows, _ = db.execute(count_sql, count_params)
        
        total = count_rows[0][0] if count_rows else 0
        
        return QueryResult(
            columns=columns,
            rows=rows,
            total=total,
            truncated=len(rows) == payload.limit
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

