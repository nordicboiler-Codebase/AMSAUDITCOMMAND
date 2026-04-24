"""Simple in-process token-bucket rate limiter.

For production behind multiple workers, replace with Redis-based slowapi/limits.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, *, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window = window_seconds
        self._buckets: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] <= now - self.window:
                bucket.popleft()
            if len(bucket) >= self.max_calls:
                retry_in = int(self.window - (now - bucket[0]))
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many requests; retry in {retry_in}s",
                )
            bucket.append(now)


login_limiter = RateLimiter(max_calls=10, window_seconds=60)
nlq_limiter = RateLimiter(max_calls=30, window_seconds=60)
global_limiter = RateLimiter(max_calls=600, window_seconds=60)


def _key_for(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


async def global_rate_limit(request: Request) -> None:
    global_limiter.hit(_key_for(request))


async def login_rate_limit(request: Request) -> None:
    login_limiter.hit(_key_for(request))


async def nlq_rate_limit(request: Request) -> None:
    nlq_limiter.hit(_key_for(request))
