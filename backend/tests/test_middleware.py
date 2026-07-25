"""
Unit tests for middleware.py (MaxBodySizeMiddleware, RateLimitMiddleware).

These exercise the ASGI classes directly against a minimal fake downstream
app, rather than through the shared main.app/client fixture — main.app is a
single process-wide instance (its middleware state persists across every
test in the session), so testing real rate-limit/size-limit *enforcement*
against it would either pollute other tests or be flaky depending on test
order/timing. Direct instantiation gives each test an isolated instance.
"""

import time

import pytest

from middleware import MaxBodySizeMiddleware, RateLimitMiddleware, RequestEntityTooLarge


def _http_scope(headers: list[tuple[bytes, bytes]] | None = None, client=("1.2.3.4", 1)):
    return {"type": "http", "headers": headers or [], "client": client}


async def _noop_app(scope, receive, send):
    """Drains the full request body, like Starlette's real body-reading loop
    does (via more_body), rather than reading only the first chunk."""
    more_body = True
    while more_body:
        message = await receive()
        more_body = message.get("more_body", False)
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _single_body_receive(body: bytes):
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _chunked_receive(chunks: list[bytes]):
    remaining = list(chunks)

    async def receive():
        if remaining:
            chunk = remaining.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(remaining)}
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


class _SendRecorder:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def status(self):
        for m in self.messages:
            if m["type"] == "http.response.start":
                return m["status"]
        return None


# ── MaxBodySizeMiddleware ─────────────────────────────────────────────────────


async def test_body_within_limit_passes_through():
    mw = MaxBodySizeMiddleware(_noop_app, max_body_size=100)
    send = _SendRecorder()
    scope = _http_scope(headers=[(b"content-length", b"10")])

    await mw(scope, _single_body_receive(b"x" * 10), send)

    assert send.status == 200


async def test_content_length_over_limit_is_rejected_before_reading_body():
    mw = MaxBodySizeMiddleware(_noop_app, max_body_size=100)
    scope = _http_scope(headers=[(b"content-length", b"1000")])

    with pytest.raises(RequestEntityTooLarge):
        await mw(scope, _single_body_receive(b"x" * 1000), _SendRecorder())


async def test_chunked_body_without_content_length_over_limit_is_rejected():
    """A client that omits Content-Length (or understates it) can't bypass
    the limit — the receive wrapper counts bytes as they stream in."""
    mw = MaxBodySizeMiddleware(_noop_app, max_body_size=10)
    scope = _http_scope(headers=[])  # no content-length header at all
    send = _SendRecorder()

    with pytest.raises(RequestEntityTooLarge):
        await mw(scope, _chunked_receive([b"x" * 6, b"x" * 6]), send)


async def test_chunked_body_under_limit_passes_through():
    mw = MaxBodySizeMiddleware(_noop_app, max_body_size=100)
    scope = _http_scope(headers=[])
    send = _SendRecorder()

    await mw(scope, _chunked_receive([b"x" * 6, b"x" * 6]), send)

    assert send.status == 200


async def test_non_http_scope_bypasses_middleware():
    mw = MaxBodySizeMiddleware(_noop_app, max_body_size=1)
    scope = {"type": "lifespan"}
    send = _SendRecorder()

    await mw(scope, _single_body_receive(b"x" * 1000), send)

    assert send.status == 200


# ── RateLimitMiddleware ────────────────────────────────────────────────────────


async def test_requests_within_limit_pass_through():
    mw = RateLimitMiddleware(_noop_app, max_requests=3, window_seconds=60)
    scope = _http_scope()

    for _ in range(3):
        send = _SendRecorder()
        await mw(scope, _single_body_receive(b""), send)
        assert send.status == 200


async def test_request_over_limit_is_rejected_with_429():
    mw = RateLimitMiddleware(_noop_app, max_requests=2, window_seconds=60)
    scope = _http_scope()

    for _ in range(2):
        await mw(scope, _single_body_receive(b""), _SendRecorder())

    send = _SendRecorder()
    await mw(scope, _single_body_receive(b""), send)

    assert send.status == 429
    retry_after = dict(
        next(m for m in send.messages if m["type"] == "http.response.start")[
            "headers"
        ]
    )[b"retry-after"]
    assert int(retry_after) >= 0


async def test_different_clients_are_tracked_independently():
    mw = RateLimitMiddleware(_noop_app, max_requests=1, window_seconds=60)

    send_a = _SendRecorder()
    await mw(_http_scope(client=("1.1.1.1", 1)), _single_body_receive(b""), send_a)
    send_b = _SendRecorder()
    await mw(_http_scope(client=("2.2.2.2", 1)), _single_body_receive(b""), send_b)

    assert send_a.status == 200
    assert send_b.status == 200


async def test_window_reset_allows_requests_again():
    mw = RateLimitMiddleware(_noop_app, max_requests=1, window_seconds=60)
    scope = _http_scope()

    await mw(scope, _single_body_receive(b""), _SendRecorder())
    # Force the tracked window to look expired without sleeping in real time.
    key = "1.2.3.4"
    count, _window_start = mw._counts[key]
    mw._counts[key] = (count, time.monotonic() - 61)

    send = _SendRecorder()
    await mw(scope, _single_body_receive(b""), send)

    assert send.status == 200


async def test_non_http_scope_bypasses_rate_limit():
    mw = RateLimitMiddleware(_noop_app, max_requests=0, window_seconds=60)
    send = _SendRecorder()

    await mw({"type": "lifespan"}, _single_body_receive(b""), send)

    assert send.status == 200


async def test_stale_clients_are_pruned_once_tracking_grows_too_large():
    mw = RateLimitMiddleware(_noop_app, max_requests=100, window_seconds=60)
    mw._MAX_TRACKED_CLIENTS = 2

    # Two old, expired entries plus one fresh request should trigger a prune
    # that drops the expired ones.
    now = time.monotonic()
    mw._counts = {"old-1": (1, now - 120), "old-2": (1, now - 120)}

    send = _SendRecorder()
    await mw(_http_scope(client=("3.3.3.3", 1)), _single_body_receive(b""), send)

    assert send.status == 200
    assert "old-1" not in mw._counts
    assert "old-2" not in mw._counts
    assert "3.3.3.3" in mw._counts
