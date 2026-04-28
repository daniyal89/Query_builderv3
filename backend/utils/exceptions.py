"""
exceptions.py — Custom exception classes and FastAPI exception handlers.

Provides consistent, structured JSON error responses across all endpoints.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DatabaseNotConnectedError(Exception):
    """Raised when an operation requires an active DuckDB connection but none exists."""
    pass


class InvalidPathError(Exception):
    """Raised when a user-supplied file path is invalid or inaccessible."""
    pass


class QueryBuildError(Exception):
    """Raised when the query builder cannot construct valid SQL from the payload."""
    pass


class CSVParseError(Exception):
    """Raised when the uploaded CSV file cannot be parsed."""
    pass


def register_exception_handlers(app: FastAPI) -> None:
    """Attach custom exception handlers to the FastAPI application.

    Maps each custom exception class to an appropriate HTTP status code
    and returns a consistent JSON error envelope:
    {"error": "<ExceptionClassName>", "detail": "<message>", "request_id": "<id>"}
    """

    def _request_id_from(request: Request) -> str:
        return getattr(request.state, "request_id", "unknown")

    @app.exception_handler(DatabaseNotConnectedError)
    async def handle_database_not_connected(request: Request, exc: DatabaseNotConnectedError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "error": "DatabaseNotConnectedError",
                "detail": str(exc) or "Database is not connected.",
                "request_id": _request_id_from(request),
            },
        )

    @app.exception_handler(InvalidPathError)
    async def handle_invalid_path(request: Request, exc: InvalidPathError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": "InvalidPathError",
                "detail": str(exc) or "Invalid or inaccessible path.",
                "request_id": _request_id_from(request),
            },
        )

    @app.exception_handler(QueryBuildError)
    async def handle_query_build_error(request: Request, exc: QueryBuildError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "QueryBuildError",
                "detail": str(exc) or "Unable to construct query.",
                "request_id": _request_id_from(request),
            },
        )

    @app.exception_handler(CSVParseError)
    async def handle_csv_parse_error(request: Request, exc: CSVParseError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": "CSVParseError",
                "detail": str(exc) or "CSV parsing failed.",
                "request_id": _request_id_from(request),
            },
        )
