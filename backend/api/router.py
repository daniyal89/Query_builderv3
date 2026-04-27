"""
router.py — Aggregates all endpoint sub-routers into a single APIRouter.

This router is included by app.py with the /api prefix so that every
endpoint defined in the endpoints/ package is served under /api/*.
"""

from fastapi import APIRouter

from backend.api.endpoints import (
    connection,
    ftp_download,
    google_drive,
    importer,
    local_object,
    merge,
    oracle,
    query,
    schema,
    sidebar_tools,
    system,
)

api_router = APIRouter(prefix="/api")

api_router.include_router(connection.router, tags=["Connection"])
api_router.include_router(schema.router, tags=["Schema"])
api_router.include_router(oracle.router, tags=["Marcadose"])
api_router.include_router(query.router, tags=["Query"])
api_router.include_router(local_object.router, tags=["Local DuckDB Objects"])
api_router.include_router(importer.router, tags=["Importer"])
api_router.include_router(merge.router, tags=["Merge & Enrichment"])
api_router.include_router(system.router, tags=["System"])
api_router.include_router(ftp_download.router, tags=["FTP Download"])
api_router.include_router(google_drive.router, tags=["Google Drive"])
api_router.include_router(sidebar_tools.router, tags=["Sidebar Tools"])
