"""HTTP hardening: security headers, request-size limit and per-IP rate limiting.

All three are pure ASGI middleware rather than ``BaseHTTPMiddleware``: they never buffer or
re-wrap the response body, add no extra task per request, and pass streaming responses
straight through, which keeps per-request overhead minimal on a small Cloud Run instance.
"""

import time
from collections import deque

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Strict CSP: only our own scripts and styles; no inline script, no third-party origins.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "connect-src 'self'",
        "font-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    ]
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}

MAX_BODY_BYTES = 8_000_000  # base64 photo of up to ~4 MB plus JSON overhead


STATIC_CACHE_CONTROL = "public, max-age=86400"  # static assets: cache a day, ETag revalidates


class SecurityHeadersMiddleware:
    """Add security headers to every response and stop API responses being cached."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if path.startswith("/api/"):
                    headers["Cache-Control"] = "no-store"
                elif path.startswith("/static/"):
                    headers.setdefault("Cache-Control", STATIC_CACHE_CONTROL)
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Reject requests whose declared body is larger than ``MAX_BODY_BYTES``."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            length = Headers(scope=scope).get("content-length")
            if length is not None:
                try:
                    too_big = int(length) > MAX_BODY_BYTES
                except ValueError:
                    await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(
                        scope, receive, send
                    )
                    return
                if too_big:
                    await JSONResponse({"detail": "Request too large"}, status_code=413)(scope, receive, send)
                    return
        await self.app(scope, receive, send)


class RateLimiter:
    """Sliding-window limiter: at most ``limit`` requests per ``window`` seconds per key.

    In-memory is enough for a single small Cloud Run service; a shared store (e.g. Redis or
    Cloud Armor) would be used for a fleet.
    """

    def __init__(self, limit: int, window: float = 60.0, max_keys: int = 10_000) -> None:
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """Record a hit. Returns (allowed, seconds until the next slot frees up)."""
        now = time.monotonic() if now is None else now
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= self.max_keys:
                self._evict(now)
            hits = self._hits[key] = deque()
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            retry_after = max(1, int(self.window - (now - hits[0])) + 1)
            return False, retry_after
        hits.append(now)
        return True, 0

    def _evict(self, now: float) -> None:
        stale = [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]
        for key in stale:
            del self._hits[key]
        if len(self._hits) >= self.max_keys:  # still full: drop the oldest half
            for key in list(self._hits)[: self.max_keys // 2]:
                del self._hits[key]


def client_ip(scope: Scope, trust_proxy: bool) -> str:
    """Client IP, using the first X-Forwarded-For hop when behind a trusted proxy."""
    if trust_proxy:
        forwarded = Headers(scope=scope).get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware:
    """Apply :class:`RateLimiter` to state-changing API calls (POST /api/...)."""

    def __init__(self, app: ASGIApp, limiter: RateLimiter, trust_proxy: bool) -> None:
        self.app = app
        self.limiter = limiter
        self.trust_proxy = trust_proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"].startswith("/api/"):
            allowed, retry_after = self.limiter.allow(client_ip(scope, self.trust_proxy))
            if not allowed:
                response = JSONResponse(
                    {"detail": "Too many requests. Please wait a moment and try again."},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
