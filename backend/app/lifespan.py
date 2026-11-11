from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
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
    """
    Управление жизненным циклом сервиса: инициализация каскадного пайплайна и прогрев моделей.
    """
    app.state.pipeline = CascadedExtractionPipeline(use_gliner=True)
    if getattr(settings, "preload_models", True):
        app.state.pipeline.warmup()
    startup_configuration_checks(app.state.pipeline)
    yield
