"""
main.py — Unified entry point for the Local DuckDB Data Dashboard.

Starts a Uvicorn server hosting the FastAPI application and automatically
opens the local URL in the user's default browser. When packaged via
PyInstaller, this is the single entry point for the .exe.
"""

import socket
import sys
import threading
import webbrowser

import uvicorn

from backend.config import settings


def open_browser(url: str, delay: float = 1.5) -> None:
    """Open the given URL in the default browser after a short delay.

    The delay allows Uvicorn to finish binding to the port before the
    browser attempts to connect.

    Args:
        url: The full URL to open (e.g., http://127.0.0.1:8741).
        delay: Seconds to wait before opening the browser.
    """
    def _open() -> None:
        webbrowser.open(url)

    timer = threading.Timer(delay, _open)
    timer.daemon = True
    timer.start()


def find_available_port(preferred: int = 8741) -> int:
    """Return the preferred port if available, otherwise find a free one.

    Attempts to bind a temporary socket to the preferred port. Falls back
    to an OS-assigned ephemeral port on failure.

    Args:
        preferred: The port to try first.

    Returns:
        An available port number.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", preferred))
            return preferred
    except OSError:
        # Port is occupied — let the OS pick one
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def main() -> None:
    """Application entry point.

    1. Resolves an available port.
    2. Spawns a background thread to open the browser.
    3. Starts Uvicorn synchronously on the main thread.
    """
    port = find_available_port(settings.PORT)
    url = f"http://{settings.HOST}:{port}"

    print(f"Starting DuckDB Data Dashboard at {url}")
    print("Press Ctrl+C to stop.\n")

    open_browser(url)

    uvicorn.run(
        "backend.app:app",
        host=settings.HOST,
        port=port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
