"""FastAPI application factory and entry point."""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.routers import core, features
from app.security import (
    BodySizeLimitMiddleware,
    RateLimiter,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.services.ai_client import AIClient, GeminiClient

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("saathi")


def create_app(settings: Settings | None = None, ai_client: AIClient | None = None) -> FastAPI:
    """Build the app. Tests pass their own settings and a fake AI client."""
    settings = settings or get_settings()
    app = FastAPI(
        title="Saathi — Gig Worker Companion",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.ai = ai_client or GeminiClient(settings)
    logger.info(
        "AI mode: %s", f"Gemini ({settings.gemini_model})" if app.state.ai.enabled else "offline fallback"
    )

    # Middleware runs bottom-up: size limit -> rate limit -> headers -> gzip.
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(settings.rate_limit_per_minute),
        trust_proxy=settings.trust_proxy_headers,
    )
    app.add_middleware(BodySizeLimitMiddleware)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Return field locations and messages only — never echo submitted values back.
        errors = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "message": err["msg"]} for err in exc.errors()
        ]
        return JSONResponse({"detail": "Please check the form.", "errors": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def _unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse({"detail": "Something went wrong. Please try again."}, status_code=500)

    app.include_router(core.router)
    app.include_router(features.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    return app


app = create_app()
