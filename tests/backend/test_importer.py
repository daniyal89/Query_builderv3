"""
test_importer.py — Tests for the POST /api/upload-csv endpoint.

Verifies:
- Valid CSV upload inserts correct number of rows.
- Column mapping is applied correctly.
- Invalid CSV (wrong format, empty) returns 400.
- File size limit enforcement returns 413.
"""

# TODO: Use httpx.AsyncClient with UploadFile fixture and temp DuckDB
