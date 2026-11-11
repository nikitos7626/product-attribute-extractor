from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.routers import extract
from app.schemas import (
    BatchOut,
    CardIn,
    CardOut,
    ReviewOverrideIn,
    ReviewQueueClearResponse,
    ReviewQueueResponse,
)
from app.services.pipeline import CascadedExtractionPipeline

logger = logging.getLogger(__name__)

router = APIRouter()


def get_frontend_dir() -> Path:
    """Определяет путь к изолированной директории frontend."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    if (repo_root / "frontend" / "index.html").exists():
        return repo_root / "frontend"
    for candidate in (
        Path("/app/frontend"),
        Path("/frontend"),
        Path(__file__).resolve().parent.parent.parent / "frontend",
        Path(__file__).resolve().parent.parent / "frontend",
    ):
        if (candidate / "index.html").exists():
            return candidate
    return Path(__file__).resolve().parent.parent / "static"


FRONTEND_DIR = get_frontend_dir()


# --------------------------- UI & System Info ---------------------------


@router.get("/", summary="Интерактивный веб-интерфейс М.Видео AI", include_in_schema=False)
def root_ui(request: Request):
    """
    Интерактивный веб-интерфейс М.Видео AI.
    Если запрос отправлен клиентом API или скриптом (Accept: application/json без text/html),
    возвращает JSON со схемой и ссылками на эндпоинты.
    Для браузеров и интеграторов также доступны постоянные маршруты /api и /api/info.
    """
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse({
            "service": "E-Commerce Product Attribute Extraction API",
            "version": "0.2.1",
            "status": "online",
            "endpoints": {
                "extract": "POST /api/extract",
                "extract_alias": "POST /extract",
                "batch": "POST /api/extract/batch",
                "export": "POST /api/extract/export",
                "review_queue": "GET /api/extract/review-queue",
                "review_override": "POST /api/extract/review-override",
                "metrics": "GET /api/extract/metrics",
                "taxonomy": "GET /api/extract/taxonomy",
                "brand_register": "POST /api/extract/brands/register",
                "model_register": "POST /api/extract/models/register",
                "health": "GET /api/extract/health",
                "swagger_docs": "/docs",
                "openapi_schema": "/openapi.json",
            },
        })
    static_file = str(FRONTEND_DIR / "index.html")
    return FileResponse(static_file)


@router.get("/api", summary="Спецификация и каталог эндпоинтов сервиса", include_in_schema=False)
@router.get("/api/info", summary="Метаданные сервиса и статус компонентов", tags=["system"])
def api_info(request: Request) -> dict:
    """
    Прямой машиночитаемый дескриптор сервиса для интеграторов и внешних агентов (без зависимости от Accept).
    """
    pipe = getattr(request.app.state, "pipeline", None) or extract.get_pipeline()
    return {
        "service": "E-Commerce Product Attribute Extraction API",
        "version": "0.2.1",
        "status": "online",
        "pipeline": "CascadedExtractionPipeline",
        "architecture_tiers": [
            "Tier 1: FastRules (Regex + FlashText brands/colors) [< 1ms]",
            "Tier 2: Targeted Zero-Shot NER (urchade/gliner_multi-v2.1) [model/cpu]",
            "Tier 2.5: Catalog Knowledge Base (catalog_models_kb.json) [< 0.1ms]",
            "Tier 3: Strict LLM Fallback (Circuit Breaker + Grounding Verification)",
            "Tier 4: SanityValidator (physical bounds, category whitelist, confidence calibration)",
        ],
        "endpoints": {
            "extract_root": "POST /extract",
            "extract_api": "POST /api/extract",
            "extract_batch": "POST /api/extract/batch",
            "export_predictions": "POST /api/extract/export",
            "review_queue": "GET /api/extract/review-queue",
            "review_override": "POST /api/extract/review-override",
            "metrics": "GET /api/extract/metrics",
            "taxonomy": "GET /api/extract/taxonomy",
            "brand_register": "POST /api/extract/brands/register",
            "model_register": "POST /api/extract/models/register",
            "health": "GET /health",
            "health_api": "GET /api/extract/health",
            "swagger_docs": "/docs",
            "openapi_schema": "/openapi.json",
        },
        "security": {
            "api_key_required": bool(settings.api_key),
            "environment": getattr(settings, "environment", "development"),
        },
        "taxonomy": {
            "status": pipe.taxonomy_manager.status,
            "categories_count": pipe.taxonomy_manager.categories_count,
        },
    }


@router.get("/health", summary="Health Check", tags=["system"])
def root_health(request: Request) -> dict:
    pipe = getattr(request.app.state, "pipeline", None) or extract.get_pipeline()
    return {
        "ok": True,
        "status": "online",
        "version": "0.2.1",
        "security": {
            "api_key_required": bool(settings.api_key),
            "environment": getattr(settings, "environment", "development"),
        },
        "taxonomy_status": pipe.taxonomy_manager.status,
    }


# --------------------------- Extraction Root Aliases ---------------------------


@router.post(
    "/extract",
    response_model=CardOut,
    response_model_exclude_none=True,
    tags=["extract"],
    summary="Извлечение характеристик карточки (Root Alias)",
)
def extract_alias(
    card: CardIn,
    pipeline: CascadedExtractionPipeline = Depends(extract.get_pipeline),
) -> CardOut:
    """
    Основной стандартизированный эндпоинт для автоматических тестеров: POST /extract -> CardOut.
    Дублирует /api/extract для максимальной совместимости со спецификацией М.Видео.
    """
    return extract._run(card, pipeline=pipeline)


@router.post(
    "/extract/batch",
    response_model=BatchOut,
    response_model_exclude_none=True,
    tags=["extract"],
    include_in_schema=False,
)
@router.post(
    "/batch",
    response_model=BatchOut,
    response_model_exclude_none=True,
    tags=["extract"],
    include_in_schema=False,
)
async def extract_batch_alias(
    request: Request,
    file: UploadFile | None = File(None),
    pipeline: CascadedExtractionPipeline = Depends(extract.get_pipeline),
) -> BatchOut:
    """
    Пакетная обработка карточек товаров: POST /extract/batch или POST /batch -> BatchOut.
    Дублирует /api/extract/batch для максимальной совместимости со спецификацией М.Видео.
    """
    return await extract.extract_batch(request=request, file=file, pipeline=pipeline)


# --------------------------- Review Queue Aliases ---------------------------


@router.get("/review-queue", response_model=ReviewQueueResponse, tags=["extract"], include_in_schema=False)
@router.get("/review/queue", response_model=ReviewQueueResponse, tags=["extract"], include_in_schema=False)
@router.get("/api/review/queue", response_model=ReviewQueueResponse, tags=["extract"], include_in_schema=False)
@router.get("/api/review-queue", response_model=ReviewQueueResponse, tags=["extract"], include_in_schema=False)
def review_queue_root_alias(limit: int = 5) -> ReviewQueueResponse:
    return extract.get_review_queue(limit=limit)


@router.post("/api/review/queue/clear", response_model=ReviewQueueClearResponse, tags=["extract"], include_in_schema=False)
@router.post("/api/review-queue/clear", response_model=ReviewQueueClearResponse, tags=["extract"], include_in_schema=False)
@router.delete("/api/review/queue", response_model=ReviewQueueClearResponse, tags=["extract"], include_in_schema=False)
@router.delete("/api/review-queue", response_model=ReviewQueueClearResponse, tags=["extract"], include_in_schema=False)
@router.post("/review/queue/clear", response_model=ReviewQueueClearResponse, tags=["extract"], include_in_schema=False)
@router.post("/review-queue/clear", response_model=ReviewQueueClearResponse, tags=["extract"], include_in_schema=False)
@router.delete("/review/queue", response_model=ReviewQueueClearResponse, tags=["extract"], include_in_schema=False)
@router.delete("/review-queue", response_model=ReviewQueueClearResponse, tags=["extract"], include_in_schema=False)
def clear_review_queue_root_alias() -> ReviewQueueClearResponse:
    return extract.clear_review_queue()


@router.post("/api/review-override", tags=["extract"], include_in_schema=False)
@router.post("/api/review/override", tags=["extract"], include_in_schema=False)
@router.post("/review-override", tags=["extract"], include_in_schema=False)
@router.post("/review/override", tags=["extract"], include_in_schema=False)
def review_override_root_alias(body: ReviewOverrideIn) -> dict:
    return extract.submit_review_override(body)
