from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers.system import FRONTEND_DIR


def setup_middlewares(app: FastAPI) -> None:
    """
    Регистрация глобальных middleware и монтирование статических ассетов.
    """
    # 1. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Монтирование модульного фронтенда (/static, /css, /js)
    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
        if (FRONTEND_DIR / "css").exists():
            app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
        if (FRONTEND_DIR / "js").exists():
            app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")

    # 3. HTTP Request Tracing Middleware
    @app.middleware("http")
    async def request_id_tracing_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # 4. HTTP API Key Authentication Middleware
    @app.middleware("http")
    async def api_key_auth_middleware(request: Request, call_next):
        if not settings.api_key:
            return await call_next(request)

        public_paths = {
            "/",
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api",
            "/api/info",
            "/api/extract/health",
        }
        if (
            request.url.path in public_paths
            or request.url.path.startswith("/static")
            or request.url.path.startswith("/css")
            or request.url.path.startswith("/js")
            or request.url.path == "/favicon.ico"
            or request.method == "OPTIONS"
        ):
            return await call_next(request)

        provided_key = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization", "")
        if not provided_key and auth_header.startswith("Bearer "):
            provided_key = auth_header[7:].strip()

        if not provided_key or provided_key != settings.api_key:
            req_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID") or str(uuid.uuid4())
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: Invalid or missing API key. Provide X-API-Key header or Bearer token."},
                headers={"X-Request-ID": req_id},
            )

        return await call_next(request)
