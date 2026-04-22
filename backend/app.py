"""
app.py — FastAPI application factory.

Creates the FastAPI instance, mounts the compiled React static files on the
root path (/), and includes all API routers under the /api prefix. Also
configures the SPA fallback so React Router handles client-side routes.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.api.router import api_router


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application instance.

    - Includes the aggregated API router at /api.
    - Mounts frontend_dist/ as static files at /.
    - Adds a catch-all route for SPA client-side routing fallback.
    """
    application = FastAPI(
        title=settings.APP_TITLE,
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # --- API routes (must be registered BEFORE the static-file mount) ---
    application.include_router(api_router)

    # --- Static files (compiled React build) ---
    static_dir = Path(settings.STATIC_DIR)
    if static_dir.exists() and static_dir.is_dir():
        application.mount(
            "/assets",
            StaticFiles(directory=str(static_dir / "assets")),
            name="static-assets",
        )

        # SPA fallback: serve index.html for any non-API, non-asset route
        @application.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(request: Request, full_path: str) -> FileResponse:
            """Serve index.html for client-side routes handled by React Router."""
            index = static_dir / "index.html"
            if index.exists():
                return FileResponse(str(index))
            return JSONResponse(
                status_code=404,
                content={"detail": "Frontend not built. Run npm run build first."},
            )
    else:
        # Dev mode: frontend_dist doesn't exist yet, just provide a helpful message
        @application.get("/", include_in_schema=False)
        async def dev_root() -> JSONResponse:
            """Placeholder when the frontend build is not available."""
            return JSONResponse(
                content={
                    "message": "API is running. Frontend not built yet.",
                    "docs": "/api/docs",
                }
            )

    return application


app = create_app()
