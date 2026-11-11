from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


def setup_exception_handlers(app: FastAPI) -> None:
    """
    Регистрация глобальных обработчиков исключений API.
    """
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        req_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID") or str(uuid.uuid4())
        return JSONResponse(
            status_code=400,
            content={
                "error": "validation_error",
                "detail": exc.errors(),
                "request_id": req_id,
            },
            headers={"X-Request-ID": req_id},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID") or str(uuid.uuid4())
        logger.exception("Unhandled server exception [request_id=%s]: %s", req_id, exc)
        env = getattr(settings, "environment", "development").lower()
        detail = str(exc) if env not in ("prod", "production") else "Internal server error occurred."
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "detail": detail,
                "request_id": req_id,
            },
            headers={"X-Request-ID": req_id},
        )
