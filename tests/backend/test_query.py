"""
test_query.py — Tests for the POST /api/query endpoint.

Verifies:
- Basic SELECT * query returns all columns and rows.
- Filtered queries produce correct result subsets.
- Sort and limit/offset directives are applied correctly.
- Invalid table/column references return 400.
"""

# TODO: Use httpx.AsyncClient with seeded DuckDB test table
