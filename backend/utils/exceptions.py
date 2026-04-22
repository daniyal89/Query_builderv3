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
    {"error": "<ExceptionClassName>", "detail": "<message>"}
    """
    # TODO: Register handlers for each custom exception
    pass
