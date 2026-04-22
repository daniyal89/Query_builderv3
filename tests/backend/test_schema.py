"""
test_schema.py — Tests for schema introspection endpoints.

Verifies:
- GET /api/tables returns correct list of TableMetadata.
- GET /api/tables/{name}/columns returns correct ColumnDetail list.
- 503 when no database is connected.
- 404 when requesting columns for a non-existent table.
"""

# TODO: Use httpx.AsyncClient with pre-connected DuckDB fixture
