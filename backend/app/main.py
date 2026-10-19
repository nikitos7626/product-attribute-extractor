import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.routers import extract
from app.schemas import CardIn, CardOut


app = FastAPI(
    title="M.Video Product Attribute Extraction API",
    description="Промышленный сервис извлечения, валидации и нормализации характеристик товаров М.Видео с многоуровневым каскадом (FastRules -> GLiNER Zero-Shot -> Catalog KB -> Strict LLM Guardrail).",
    version="0.2.1",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_auth_middleware(request: Request, call_next):
    """
    Промышленная защита API: если settings.api_key задан в окружении,
    все защищенные эндпоинты требуют заголовок X-API-Key или Bearer-токен.
    Если api_key не задан — работает режим открытого доступа для локальных тестов.
    """
    if not settings.api_key:
        return await call_next(request)

    public_paths = {"/", "/health", "/docs", "/redoc", "/openapi.json", "/api", "/api/info", "/api/extract/health"}
    if request.url.path in public_paths or request.method == "OPTIONS":
        return await call_next(request)

    provided_key = request.headers.get("X-API-Key")
    auth_header = request.headers.get("Authorization", "")
    if not provided_key and auth_header.startswith("Bearer "):
        provided_key = auth_header[7:].strip()

    if not provided_key or provided_key != settings.api_key:
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized: Invalid or missing API key. Provide X-API-Key header or Bearer token."},
        )

    return await call_next(request)


app.include_router(extract.router)


@app.post("/extract", response_model=CardOut, tags=["extract"], summary="Извлечение характеристик карточки (Root Alias)")
def extract_alias(card: CardIn) -> CardOut:
    """
    Основной стандартизированный эндпоинт для автоматических тестеров: POST /extract -> CardOut.
    Дублирует /api/extract для максимальной совместимости со спецификацией М.Видео.
    """
    return extract._run(card)


@app.get("/", summary="Интерактивный веб-интерфейс М.Видео AI")
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
            "service": "M.Video Product Attribute Extraction API",
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
                "health": "GET /api/extract/health",
                "swagger_docs": "/docs",
                "openapi_schema": "/openapi.json",
            },
        })
    static_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    return FileResponse(static_file)


@app.get("/api", summary="Спецификация и каталог эндпоинтов сервиса")
@app.get("/api/info", summary="Метаданные сервиса и статус компонентов")
def api_info() -> dict:
    """
    Прямой машиночитаемый дескриптор сервиса для интеграторов и внешних агентов (без зависимости от Accept).
    """
    return {
        "service": "M.Video Product Attribute Extraction API",
        "version": "0.2.1",
        "status": "online",
        "pipeline": "CascadedExtractionPipeline",
        "architecture_tiers": [
            "Tier 1: FastRules (Regex + FlashText brands/colors) [< 1ms]",
            "Tier 2: Targeted Zero-Shot NER (urchade/gliner_multi-v2.1) [model/cpu]",
            "Tier 3: Catalog Knowledge Base (catalog_models_kb.json) + Strict LLM Guardrail",
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
            "health": "GET /health",
            "health_api": "GET /api/extract/health",
            "swagger_docs": "/docs",
            "openapi_schema": "/openapi.json",
        },
    }


@app.get("/health", summary="Health Check")
def root_health() -> dict:
    return {"ok": True, "status": "online", "version": "0.2.1"}