"""
Комплексные тесты для аудита v2:
1. Concurrency & Persistence: BrandRegistry потокобезопасность и блокировка файла.
2. Error Handling & Taxonomy: корректная обработка сбоев загрузки таксономии и деградации.
3. Config & Prior Weights: динамические веса и пороги калибратора через Settings.
4. LLM Fallback: повторные попытки с экспоненциальным backoff и обработка пустых ответов.
5. Usability & Output: человеко-читаемые статусы, пояснения уверенности и причины модерации.
6. Batch Endpoint: валидация формата файлов, пустых массивов, некорректных структур.
7. Security: проверки безопасности окружения и авторизации.
"""
from __future__ import annotations

import io
import json
import logging
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.extractors.llm_extractor import StrictLlmFallbackExtractor
from app.main import app, startup_configuration_checks
from app.services.brand_registry import BrandRegistry, process_file_lock
from app.services.confidence_calibrator import ConfidenceCalibrator
from app.services.pipeline import CascadedExtractionPipeline, TaxonomyManager

client = TestClient(app)


# =========================================================================
# 1. Concurrency & Persistence: BrandRegistry
# =========================================================================

def test_brand_registry_thread_safety_and_file_locking():
    """Проверяет конкурентную регистрацию брендов из множества параллельных потоков."""
    with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tmp:
        tmp.write("existing_brand,ExistingBrand\n")
        tmp_path = tmp.name

    try:
        registry = BrandRegistry(csv_path=tmp_path)
        assert registry.has_brand("existing_brand")

        num_threads = 10
        brands_per_thread = 5
        errors = []

        def worker(thread_idx: int):
            for i in range(brands_per_thread):
                alias = f"brand_t{thread_idx}_i{i}"
                canon = f"Brand_T{thread_idx}_I{i}"
                try:
                    ok = registry.register_brand(alias, canon, persist=True)
                    if not ok:
                        errors.append(f"Failed to register {alias}")
                except Exception as e:
                    errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent registration: {errors}"

        # Проверяем наличие всех зарегистрированных брендов в памяти
        for t in range(num_threads):
            for i in range(brands_per_thread):
                alias = f"brand_t{t}_i{i}"
                assert registry.has_brand(alias)

        # Проверяем, что файл CSV не поврежден и корректно читается
        with open(tmp_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        # 1 начальный + 50 добавленных
        assert len(lines) == 1 + (num_threads * brands_per_thread)

    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
            Path(tmp_path + ".lock").unlink(missing_ok=True)
        except OSError:
            pass


def test_process_file_lock_stale_cleanup():
    """Проверяет автоматическую очистку зависшего .lock файла."""
    with tempfile.NamedTemporaryFile("w+", delete=False) as tmp:
        filepath = tmp.name
    lock_file = filepath + ".lock"

    try:
        # Создаем искусственно устаревший lock-файл
        with open(lock_file, "w") as f:
            f.write("stale_pid_99999")

        # Устанавливаем время модификации на 60 секунд назад
        import os
        import time
        past = time.time() - 60.0
        os.utime(lock_file, (past, past))

        # Блокировка должна обнаружить устаревший файл, удалить его и захватить ресурс
        acquired = False
        with process_file_lock(filepath, timeout=2.0):
            acquired = True

        assert acquired is True
        assert not os.path.exists(lock_file)
    finally:
        try:
            Path(filepath).unlink(missing_ok=True)
            Path(lock_file).unlink(missing_ok=True)
        except OSError:
            pass


# =========================================================================
# 2. Error Handling & Taxonomy Loading
# =========================================================================

def test_taxonomy_manager_missing_file_degradation():
    """Проверяет безопасный переход в режим degraded при отсутствии файла таксономии."""
    fake_path = Path("non_existent_taxonomy_file_12345.json")
    manager = TaxonomyManager(file_path=fake_path)

    assert manager.status == "degraded"
    assert manager.error_message is not None
    assert "не найден" in manager.error_message.lower()
    assert manager.categories_count == 0


def test_taxonomy_manager_corrupted_file():
    """Проверяет фиксацию статуса failed при невалидном JSON таксономии."""
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json", encoding="utf-8") as tmp:
        tmp.write("{ invalid json content ...")
        tmp_path = Path(tmp.name)

    try:
        manager = TaxonomyManager(file_path=tmp_path)
        assert manager.status == "failed"
        assert manager.error_message is not None
        assert "ошибка чтения" in manager.error_message.lower()
    finally:
        tmp_path.unlink(missing_ok=True)


def test_pipeline_with_degraded_taxonomy_adds_warning_and_tier():
    """Проверяет, что пайплайн явно уведомляет пользователя о деградации таксономии."""
    pipeline = CascadedExtractionPipeline(use_gliner=False, use_catalog_enricher=False, use_llm=False)
    # Имитируем деградацию таксономии
    pipeline.taxonomy_manager.status = "degraded"
    pipeline.taxonomy_manager.error_message = "Mocked network failure"

    try:
        res = pipeline.process_card({
            "title": "Смартфон Apple iPhone 15 128GB черный",
            "description": "Новый телефон",
        })

        assert "taxonomy" in res.get("degraded_tiers", [])
        assert any("таксономия" in w.lower() for w in res.get("warnings", []))
        assert res.get("taxonomy_status") == "degraded"
    finally:
        # Восстанавливаем здоровый статус
        pipeline.taxonomy_manager.status = "healthy"
        pipeline.taxonomy_manager.error_message = None


# =========================================================================
# 3. Config & Prior Weights in Settings
# =========================================================================

def test_settings_exposure_and_calibrator_dynamic_weights():
    """Проверяет, что априорные веса и гиперпараметры берутся из Settings, а не захардкожены."""
    calibrator = ConfidenceCalibrator.get_instance()

    # Проверяем наличие всех ключевых настроек
    assert hasattr(settings, "prior_catalog_kb")
    assert hasattr(settings, "prior_flashtext")
    assert hasattr(settings, "prior_gliner")
    assert hasattr(settings, "prior_regex")
    assert hasattr(settings, "calibrator_title_bonus")
    assert hasattr(settings, "consensus_conflict_penalty")
    assert hasattr(settings, "completeness_penalty_power")

    # Проверяем динамическую отдачу весов
    priors = calibrator.get_source_priors()
    assert priors["catalog_kb"] == settings.prior_catalog_kb
    assert priors["gliner"] == settings.prior_gliner

    # Проверяем вычисление калибровки с динамическим весом
    score = calibrator.calibrate_attribute(
        attribute="brand",
        value="Apple",
        raw_confidence=0.95,
        source="flashtext",
        category_key="smartphones",
        in_title=True,
    )
    assert 0.90 <= score <= 0.99


# =========================================================================
# 4. LLM Fallback: Retry with Exponential Backoff & Empty Responses
# =========================================================================

def test_llm_retry_on_transient_http_error():
    """Проверяет, что LLM-экстрактор выполняет повторные попытки при HTTP 429 / 500."""
    extractor = StrictLlmFallbackExtractor(
        api_key="test-key",
        max_retries=2,
        backoff_factor=0.01,  # Быстрый тест без пауз
    )

    mock_resp_500 = MagicMock()
    mock_resp_500.status_code = 500
    mock_resp_500.text = "Internal Server Error"

    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {
        "choices": [{"message": {"content": '{"battery": "5000 мАч"}'}}]
    }

    # Первый вызов 500, второй успешный 200
    with patch("httpx.Client.post", side_effect=[mock_resp_500, mock_resp_200]) as mock_post:
        res = extractor.enrich_missing_attributes(
            brand="Xiaomi",
            model="Redmi 13",
            missing_attrs={"battery"},
            category_key="smartphones",
        )
        assert len(res) == 1
        assert res[0]["value"] == "5000 мАч"
        assert mock_post.call_count == 2


def test_llm_handles_empty_response_and_recovers():
    """Проверяет обработку пустого ответа от LLM и повтор."""
    extractor = StrictLlmFallbackExtractor(
        api_key="test-key",
        max_retries=1,
        backoff_factor=0.01,
    )

    mock_empty_200 = MagicMock()
    mock_empty_200.status_code = 200
    mock_empty_200.json.return_value = {"choices": [{"message": {"content": "   "}}]}

    mock_good_200 = MagicMock()
    mock_good_200.status_code = 200
    mock_good_200.json.return_value = {
        "choices": [{"message": {"content": '{"battery": "4500 мАч"}'}}]
    }

    with patch("httpx.Client.post", side_effect=[mock_empty_200, mock_good_200]):
        res = extractor.enrich_missing_attributes(
            brand="Samsung",
            model="A55",
            missing_attrs={"battery"},
            category_key="smartphones",
        )
        assert len(res) == 1
        assert res[0]["value"] == "4500 мАч"


def test_llm_malformed_json_graceful_handling():
    """Проверяет корректное логирование и откат при невалидном JSON от LLM."""
    extractor = StrictLlmFallbackExtractor(api_key="test-key")

    mock_bad_json = MagicMock()
    mock_bad_json.status_code = 200
    mock_bad_json.json.return_value = {
        "choices": [{"message": {"content": "Вот ваши характеристики: батарея 5000, экран 6.7"}}]
    }

    with patch("httpx.Client.post", return_value=mock_bad_json):
        res = extractor.enrich_missing_attributes(
            brand="Samsung",
            model="Galaxy",
            missing_attrs={"battery"},
            category_key="smartphones",
        )
        assert res == []


# =========================================================================
# 5. Usability & Result Output: Status, Explanations, Review Reasons
# =========================================================================

def test_pipeline_output_usability_fields():
    """Проверяет наличие человеко-читаемых статусов и пояснений к предсказаниям."""
    pipeline = CascadedExtractionPipeline(use_gliner=False, use_catalog_enricher=False, use_llm=False)

    card = {
        "title": "Смартфон Apple iPhone 15 Pro 256GB Black Titanium",
        "description": "Экран 6.1 дюйма, аккумулятор 3274 мАч",
    }
    res = pipeline.process_card(card)

    # 1. Статус карточки
    assert "status" in res
    assert "status_description" in res
    assert "review_reasons" in res
    assert res["status"] in ("approved", "needs_review", "degraded_success")
    assert isinstance(res["status_description"], str)
    assert len(res["status_description"]) > 5

    # 2. Пояснения по каждому атрибуту
    for p in res["predictions"]:
        assert "confidence_reason" in p
        assert p["confidence_reason"] is not None
        assert len(p["confidence_reason"]) > 5
        assert "status" in p
        assert p["status"] in ("valid", "high_confidence", "uncertain", "confirmed_by_consensus", "conflict")


def test_pipeline_output_empty_card_status():
    """Проверяет статус и причины проверки для пустой карточки."""
    pipeline = CascadedExtractionPipeline(use_gliner=False, use_catalog_enricher=False, use_llm=False)
    res = pipeline.process_card({"title": "", "description": ""})

    assert res["status"] == "empty"
    assert res["needs_review"] is True
    assert len(res["review_reasons"]) > 0
    assert "пустая" in res["status_description"].lower()


# =========================================================================
# 6. Batch Endpoint Validation
# =========================================================================

def test_batch_endpoint_rejects_unsupported_extensions():
    """Проверяет отклонение неподдерживаемых типов файлов (не .json и не .csv)."""
    fake_txt = b"some random text"
    files = {"file": ("data.txt", io.BytesIO(fake_txt), "text/plain")}

    resp = client.post("/api/extract/batch", files=files)
    assert resp.status_code == 400
    assert "Неподдерживаемый формат" in resp.json()["detail"]


def test_batch_endpoint_rejects_empty_json_array():
    """Проверяет отклонение пустого массива JSON []."""
    empty_arr = b"[]"
    files = {"file": ("empty.json", io.BytesIO(empty_arr), "application/json")}

    resp = client.post("/api/extract/batch", files=files)
    assert resp.status_code == 400
    assert "не содержит карточек" in resp.json()["detail"]


def test_batch_endpoint_rejects_non_dict_json_items():
    """Проверяет отклонение JSON массива с некорректными элементами (числа, строки)."""
    invalid_items = json.dumps(["invalid", 123, True]).encode("utf-8")
    files = {"file": ("invalid.json", io.BytesIO(invalid_items), "application/json")}

    resp = client.post("/api/extract/batch", files=files)
    assert resp.status_code == 400
    assert "не является объектом" in resp.json()["detail"]


def test_batch_endpoint_rejects_empty_file():
    """Проверяет отклонение файла с нулевым размером."""
    files = {"file": ("zero.json", io.BytesIO(b""), "application/json")}

    resp = client.post("/api/extract/batch", files=files)
    assert resp.status_code == 400
    assert "пустой" in resp.json()["detail"]


# =========================================================================
# 7. Security: Configuration & Startup Checks
# =========================================================================

def test_security_startup_check_logs_critical_in_production(caplog):
    """Проверяет логирование критического предупреждения, если production развернут без API_KEY."""
    caplog.set_level(logging.CRITICAL)

    orig_env = settings.environment
    orig_key = settings.api_key
    try:
        settings.environment = "production"
        settings.api_key = ""

        startup_configuration_checks()

        assert any("CRITICAL SECURITY CONFIGURATION ERROR" in record.message for record in caplog.records)
    finally:
        settings.environment = orig_env
        settings.api_key = orig_key


def test_health_endpoint_reports_taxonomy_and_security():
    """Проверяет, что health эндпоинт отдает статус таксономии и безопасности."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "security" in data
    assert "environment" in data["security"]
    assert "taxonomy_status" in data

    resp_extract_health = client.get("/api/extract/health")
    assert resp_extract_health.status_code == 200
    data_ext = resp_extract_health.json()
    assert "taxonomy" in data_ext
    assert "status" in data_ext["taxonomy"]
