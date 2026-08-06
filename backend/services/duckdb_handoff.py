"""Tracks when a build has taken the dashboard's DuckDB connection away.

DuckDB permits a single writer per file, so a build disconnects the dashboard
singleton for its duration. While that is true, every DuckDB endpoint would
otherwise answer a bare ``503 No database connected`` — indistinguishable from
"the app has lost its database", which is what it looks like to the operator.
This flag lets those endpoints answer ``409`` ("busy, retry") instead.

Counted rather than boolean: a full-pipeline run and a standalone build can both
be in flight, and the first one to finish must not clear the other's handoff.

Phase 7 of the improvement plan moves the whole disconnect/reconnect dance in
here as ``exclusive_duckdb()``; for now this module only owns the flag.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_depth = 0


def begin() -> None:
    """Record that the dashboard connection has been handed to a writer."""
    global _depth
    with _lock:
        _depth += 1


def end() -> None:
    """Record that one writer has finished with the dashboard connection."""
    global _depth
    with _lock:
        _depth = max(0, _depth - 1)


def is_handed_off() -> bool:
    return _depth > 0
