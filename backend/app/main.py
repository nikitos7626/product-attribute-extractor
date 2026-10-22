import logging

import os

import uuid

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import Depends, FastAPI, File, Request, UploadFile

from fastapi.exceptions import RequestValidationError

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import FileResponse, JSONResponse

from fastapi.staticfiles import StaticFiles

from app.config import settings

from app.routers import extract

from app.schemas import BatchOut, CardIn, CardOut, ReviewOverrideIn, ReviewQueueClearResponse, ReviewQueueResponse

from app.services.pipeline import CascadedExtractionPipeline, TaxonomyManager

logger = logging.getLogger(__name__)



def startup_configuration_checks(pipeline: CascadedExtractionPipeline | None = None) -> None:

    """

    Проверка конфигурации безопасности и целостности компонентов при старте сервиса.

    Предупреждает о незащищенном production-режиме и статусе таксономии.

    """

    env = getattr(settings, "environment", "development").lower()

    if not settings.api_key:

        if env in ("prod", "production"):

            logger.critical(

                "CRITICAL SECURITY CONFIGURATION ERROR: Service is running in PRODUCTION mode without API_KEY configured! "

                "All protected endpoints are vulnerable to unauthorized access. Configure API_KEY in production."

            )

        else:

            logger.warning(

                "SECURITY NOTICE: API_KEY is empty. Service running in open development/testing mode (env=%s).",

                env,

            )

    else:

        logger.info("Security active: API_KEY authorization enabled for protected endpoints (env=%s).", env)

    tax_mgr = pipeline.taxonomy_manager if pipeline else TaxonomyManager.get_instance()

    if tax_mgr.status != "healthy":

        logger.warning(

            "TAXONOMY ALERT: Taxonomy status is '%s' (%s). Safe schema fallback is active.",

            tax_mgr.status,

            tax_mgr.error_message,

        )



@asynccontextmanager

async def lifespan(app: FastAPI):

    app.state.pipeline = CascadedExtractionPipeline(use_gliner=True)

    if getattr(settings, "preload_models", True):

        app.state.pipeline.warmup()

    startup_configuration_checks(app.state.pipeline)

    yield



app = FastAPI(

    title="M.Video Product Attribute Extraction API",

    description="Промышленный сервис извлечения, валидации и нормализации характеристик товаров М.Видео с многоуровневым каскадом (FastRules -> GLiNER Zero-Shot -> Catalog KB -> Strict LLM Guardrail).",

    version="0.2.1",

    docs_url="/docs",

    redoc_url="/redoc",

    lifespan=lifespan,

)



app.add_middleware(

    CORSMiddleware,

    allow_origins=settings.cors_origins_list,

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)

# Монтирование модульного фронтенда (/static)



def get_frontend_dir() -> Path:

    """Определяет путь к изолированной директории frontend."""

    repo_root = Path(__file__).resolve().parent.parent.parent

    if (repo_root / "frontend" / "index.html").exists():

        return repo_root / "frontend"

    for candidate in (Path("/app/frontend"), Path("/frontend"), Path(__file__).resolve().parent.parent / "frontend"):

        if (candidate / "index.html").exists():

            return candidate

    return Path(__file__).resolve().parent / "static"





FRONTEND_DIR = get_frontend_dir()

if FRONTEND_DIR.exists():

    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    if (FRONTEND_DIR / "css").exists():

        app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")

    if (FRONTEND_DIR / "js").exists():

        app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")



@app.middleware("http")

async def request_id_tracing_middleware(request: Request, call_next):

    """

    Трассировочный middleware: генерирует или пробрасывает X-Request-ID для всех HTTP-запросов.

    """

    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    request.state.request_id = request_id

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id

    return response



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

    if request.url.path in public_paths or request.url.path.startswith("/static") or request.method == "OPTIONS":

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



# --------------------------- Глобальные обработчики исключений ---------------------------



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

app.include_router(extract.router)



@app.post("/extract", response_model=CardOut, response_model_exclude_none=True, tags=["extract"], summary="Извлечение характеристик карточки (Root Alias)")



def extract_alias(

    card: CardIn,

    pipeline: CascadedExtractionPipeline = Depends(extract.get_pipeline),

) -> CardOut:

    """

    Основной стандартизированный эндпоинт для автоматических тестеров: POST /extract -> CardOut.

    Дублирует /api/extract для максимальной совместимости со спецификацией М.Видео.

    """

    return extract._run(card, pipeline=pipeline)



@app.post("/extract/batch", response_model=BatchOut, response_model_exclude_none=True, tags=["extract"], summary="Пакетное извлечение характеристик (Root Alias)")



@app.post("/batch", response_model=BatchOut, response_model_exclude_none=True, tags=["extract"], summary="Пакетное извлечение характеристик (Root Alias)")

async def extract_batch_alias(

    file: UploadFile = File(...),

    pipeline: CascadedExtractionPipeline = Depends(extract.get_pipeline),

) -> BatchOut:

    """

    Пакетная обработка карточек товаров: POST /extract/batch или POST /batch -> BatchOut.

    Дублирует /api/extract/batch для максимальной совместимости со спецификацией М.Видео.

    """

    return await extract.extract_batch(file=file, pipeline=pipeline)


@app.get("/review-queue", response_model=ReviewQueueResponse, tags=["extract"], summary="Очередь модерации (Root Alias)")
@app.get("/review/queue", response_model=ReviewQueueResponse, tags=["extract"], summary="Очередь модерации (Root Alias)")
@app.get("/api/review/queue", response_model=ReviewQueueResponse, tags=["extract"], summary="Очередь модерации (API Alias)")
@app.get("/api/review-queue", response_model=ReviewQueueResponse, tags=["extract"], summary="Очередь модерации (API Alias)")
def review_queue_root_alias(limit: int = 5) -> ReviewQueueResponse:
    return extract.get_review_queue(limit=limit)


@app.post("/api/review/queue/clear", response_model=ReviewQueueClearResponse, tags=["extract"])
@app.post("/api/review-queue/clear", response_model=ReviewQueueClearResponse, tags=["extract"])
@app.delete("/api/review/queue", response_model=ReviewQueueClearResponse, tags=["extract"])
@app.delete("/api/review-queue", response_model=ReviewQueueClearResponse, tags=["extract"])
@app.post("/review/queue/clear", response_model=ReviewQueueClearResponse, tags=["extract"])
@app.post("/review-queue/clear", response_model=ReviewQueueClearResponse, tags=["extract"])
@app.delete("/review/queue", response_model=ReviewQueueClearResponse, tags=["extract"])
@app.delete("/review-queue", response_model=ReviewQueueClearResponse, tags=["extract"])
def clear_review_queue_root_alias() -> ReviewQueueClearResponse:
    return extract.clear_review_queue()


@app.post("/api/review-override", tags=["extract"])
@app.post("/api/review/override", tags=["extract"])
@app.post("/review-override", tags=["extract"])
@app.post("/review/override", tags=["extract"])
def review_override_root_alias(body: ReviewOverrideIn) -> dict:
    return extract.submit_review_override(body)




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

                "model_register": "POST /api/extract/models/register",

                "health": "GET /api/extract/health",

                "swagger_docs": "/docs",

                "openapi_schema": "/openapi.json",

            },

        })

    static_file = str(FRONTEND_DIR / "index.html")

    return FileResponse(static_file)



@app.get("/api", summary="Спецификация и каталог эндпоинтов сервиса")



@app.get("/api/info", summary="Метаданные сервиса и статус компонентов")



def api_info(request: Request) -> dict:

    """

    Прямой машиночитаемый дескриптор сервиса для интеграторов и внешних агентов (без зависимости от Accept).

    """

    pipe = getattr(request.app.state, "pipeline", None) or extract.get_pipeline()

    return {

        "service": "M.Video Product Attribute Extraction API",

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



@app.get("/health", summary="Health Check")



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

