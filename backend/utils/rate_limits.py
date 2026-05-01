"""Simple in-memory rate limiting for high-cost API endpoints."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class RateLimitPolicy:
    max_requests: int
    window_seconds: int
    label: str


DEFAULT_RATE_LIMIT_POLICIES: dict[str, RateLimitPolicy] = {
    "query_preview": RateLimitPolicy(max_requests=120, window_seconds=60, label="query preview"),
    "query_execute": RateLimitPolicy(max_requests=30, window_seconds=60, label="query execution"),
    "ftp_download_start": RateLimitPolicy(max_requests=5, window_seconds=60, label="FTP download start"),
    "drive_auth_login": RateLimitPolicy(max_requests=5, window_seconds=300, label="Google Drive login"),
    "drive_upload_start": RateLimitPolicy(max_requests=5, window_seconds=60, label="Google Drive upload start"),
    "drive_download_start": RateLimitPolicy(max_requests=5, window_seconds=60, label="Google Drive download start"),
    "sidebar_build_duckdb": RateLimitPolicy(max_requests=6, window_seconds=60, label="DuckDB build"),
    "sidebar_csv_to_parquet": RateLimitPolicy(max_requests=6, window_seconds=60, label="CSV to Parquet"),
}


class InMemoryRateLimiter:
    """Per-client sliding-window limiter for local single-process deployments."""

    def __init__(self, policies: dict[str, RateLimitPolicy]) -> None:
        self._lock = threading.Lock()
        self._policies = dict(policies)
        self._events: dict[tuple[str, str], deque[float]] = {}

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def set_policy(self, name: str, policy: RateLimitPolicy) -> None:
        with self._lock:
            self._policies[name] = policy
            stale_keys = [key for key in self._events if key[0] == name]
            for key in stale_keys:
                self._events.pop(key, None)

    def get_policy(self, name: str) -> RateLimitPolicy:
        with self._lock:
            policy = self._policies.get(name)
        if policy is None:
            raise KeyError(f"Unknown rate limit policy '{name}'.")
        return policy

    @staticmethod
    def _client_key(request: Request) -> str:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            first_hop = forwarded_for.split(",")[0].strip()
            if first_hop:
                return first_hop
        if request.client and request.client.host:
            return request.client.host
        return "unknown-client"

    def enforce(self, request: Request, policy_name: str) -> None:
        policy = self.get_policy(policy_name)
        client_key = self._client_key(request)
        event_key = (policy_name, client_key)
        now = time.monotonic()
        window_start = now - policy.window_seconds

        with self._lock:
            timestamps = self._events.setdefault(event_key, deque())
            while timestamps and timestamps[0] <= window_start:
                timestamps.popleft()

            if len(timestamps) >= policy.max_requests:
                retry_after = max(1, math.ceil((timestamps[0] + policy.window_seconds) - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Too many {policy.label} requests from this client. "
                        f"Try again in {retry_after} second(s)."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )

            timestamps.append(now)


rate_limiter = InMemoryRateLimiter(DEFAULT_RATE_LIMIT_POLICIES)


def enforce_rate_limit(request: Request, policy_name: str) -> None:
    rate_limiter.enforce(request, policy_name)
