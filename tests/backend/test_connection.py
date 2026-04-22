"""
test_connection.py — Tests for the POST /api/duckdb/connect endpoint.

Verifies:
- Successful connection with a valid .duckdb file path.
- 400 error for invalid or non-existent paths.
- Response schema matches ConnectionResponse model.
"""

# TODO: Use httpx.AsyncClient with app fixture
# TODO: Create temp .duckdb file in pytest fixture for valid-path tests
