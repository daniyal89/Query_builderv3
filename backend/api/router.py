"""
router.py — Aggregates all endpoint sub-routers into a single APIRouter.

This router is included by app.py with the /api prefix so that every
endpoint defined in the endpoints/ package is served under /api/*.
"""

from fastapi import APIRouter

from backend.api.endpoints import connection, schema, query, importer, merge

api_router = APIRouter(prefix="/api")

# --- Register sub-routers ---
api_router.include_router(connection.router, tags=["Connection"])
api_router.include_router(schema.router, tags=["Schema"])
api_router.include_router(query.router, tags=["Query"])
api_router.include_router(importer.router, tags=["Importer"])
api_router.include_router(merge.router, tags=["Merge & Enrichment"])
