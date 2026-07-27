"""ASGI middleware providing basic abuse guardrails: a hard cap on request
body size and a per-client-IP rate limit. The API previously had neither, so
a single caller could send an arbitrarily large upload or hammer any route
with unbounded request volume.

Both are deliberately simple, in-process implementations (no Redis/shared
store) — Aktilot's backend runs as a single process per docker-compose.yml,
so there is no multi-instance deployment to coordinate across yet. If that
changes, these should move to a shared store instead.
"""

import json
import math
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestEntityTooLarge(Exception):
    """Internal signal raised by limited_receive() when a streamed body
    crosses the limit — caught by __call__ itself, never propagated to the
    ASGI app (see MaxBodySizeMiddleware's docstring for why)."""


def _get_header(scope: Scope, name: bytes) -> bytes | None:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value
    return None


class MaxBodySizeMiddleware:
    """Rejects requests whose body exceeds max_body_size.

    A declared Content-Length above the limit is rejected immediately, before
    any body is read. For requests without a (trustworthy) Content-Length —
    e.g. chunked transfer-encoding — the receive channel is wrapped to count
    bytes as they arrive and abort as soon as the running total crosses the
    limit, so a client can't bypass the check by simply omitting or
    understating Content-Length.

    The 413 response is written directly by this middleware rather than via
    FastAPI's @app.exception_handler mechanism: this middleware is added
    last, which in Starlette's stack makes it the *outermost* user
    middleware — above (outside) ExceptionMiddleware, which is what actually
    dispatches registered exception handlers. An exception raised here would
    otherwise propagate past ExceptionMiddleware entirely and surface as a
    generic unhandled 500, not the intended 413.
    """

    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = _get_header(scope, b"content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = 0
            if declared_size > self.max_body_size:
                await self._reject(send)
                return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        total_bytes = 0

        async def limited_receive() -> Message:
            nonlocal total_bytes
            message = await receive()
            if message["type"] == "http.request":
                total_bytes += len(message.get("body", b""))
                if total_bytes > self.max_body_size:
                    raise RequestEntityTooLarge(
                        f"Request body exceeds the {self.max_body_size}-byte limit"
                    )
            return message

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestEntityTooLarge:
            if response_started:
                # The app already started responding before the body was
                # fully read (unusual) — too late to send a fresh 413.
                raise
            await self._reject(send)

    async def _reject(self, send: Send) -> None:
        body = json.dumps(
            {"detail": f"Request body exceeds the {self.max_body_size}-byte limit"}
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})


class RateLimitMiddleware:
    """Fixed-window rate limit, keyed by client IP.

    Simple and cheap rather than maximally accurate: each client gets
    max_requests per window_seconds; the window resets on the first request
    after it elapses. Tracked-client state is pruned once it grows past
    _MAX_TRACKED_CLIENTS to bound memory instead of growing forever as new
    IPs show up. If every tracked entry is still fresh (nothing to prune) —
    e.g. a sustained stream of unique client IPs — the oldest entry is
    evicted instead, so _MAX_TRACKED_CLIENTS stays a hard bound rather than
    just a pruning trigger.
    """

    _MAX_TRACKED_CLIENTS = 10_000

    def __init__(self, app: ASGIApp, max_requests: int, window_seconds: int) -> None:
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._counts: dict[str, tuple[int, float]] = {}

    def _prune_stale(self, now: float) -> None:
        cutoff = now - self.window_seconds
        self._counts = {
            key: value for key, value in self._counts.items() if value[1] >= cutoff
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        key = client[0] if client else "unknown"
        now = time.monotonic()

        if len(self._counts) >= self._MAX_TRACKED_CLIENTS and key not in self._counts:
            self._prune_stale(now)
            if len(self._counts) >= self._MAX_TRACKED_CLIENTS:
                # Still at capacity even after pruning — every tracked entry
                # is fresh (e.g. a sustained stream of unique client IPs).
                # Evict the oldest to keep this a hard bound rather than
                # growing without limit; dicts preserve insertion order.
                del self._counts[next(iter(self._counts))]

        count, window_start = self._counts.get(key, (0, now))
        if now - window_start >= self.window_seconds:
            count, window_start = 0, now
        count += 1
        self._counts[key] = (count, window_start)

        if count > self.max_requests:
            # Ceiling, not round — rounding down to 0 while time still
            # remains in the window would invite an immediate retry that
            # gets rejected again.
            retry_after = max(0, math.ceil(self.window_seconds - (now - window_start)))
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"retry-after", str(retry_after).encode()),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"detail":"Rate limit exceeded. Try again later."}',
                }
            )
            return

        await self.app(scope, receive, send)
