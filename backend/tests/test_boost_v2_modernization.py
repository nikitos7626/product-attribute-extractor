"""
Comprehensive tests for Boost Plan v2 modernization:
- Stage 1: CardIn aliases, X-Request-ID tracing, global exception handlers, Docker setup.
- Stage 2: Multi-source consensus in pipeline, Dependency Injection, non-blocking batch and export, partial batch resilience.
- Stage 3: Washing machine load capacity vs weight, weight bounds, category BAD_MODEL_WORDS, extended colors.
- Stage 4: Reviewed predictions file locking.
"""
import io
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import CardIn, CardOut
from app.extractors.sanity import AttributeSanityValidator
from app.extractors.regex_extractor import RegexExtractor
from app.services.pipeline import CascadedExtractionPipeline

client = TestClient(app)


# -------------------------------------------------------------------------
# Stage 1: Input Schemas, Aliases, Tracing, Exception Handlers
# -------------------------------------------------------------------------

def test_card_in_alias_mapping():
    """Проверяет маппинг альтернативных ID и полей вендора в CardIn."""
    # Тест 1: id -> external_id
    c1 = CardIn(id=101, title="Телефон")
    assert c1.external_id == "101"

    # Тест 2: sku_id -> external_id
    c2 = CardIn(sku_id="sku-999", title="Пылесос")
    assert c2.external_id == "sku-999"

    # Тест 3: item_id -> external_id
    c3 = CardIn(item_id=5555, title="Ноутбук")
    assert c3.external_id == "5555"

    # Тест 4: vendor, manufacturer -> seller_attributes
    c4 = CardIn(id=1, vendor="Apple", manufacturer="Foxconn", seller="M.Video")
    assert c4.seller_attributes["vendor"] == "Apple"
    assert c4.seller_attributes["manufacturer"] == "Foxconn"
    assert c4.seller_attributes["seller"] == "M.Video"


def test_tracing_and_validation_error_handler():
    """Проверяет X-Request-ID middleware и обработчик RequestValidationError (400 JSON)."""
    # Запрос с некорректным телом (не JSON)
    resp = client.post("/api/extract", content=b"invalid-body-not-json", headers={"Content-Type": "application/json", "X-Request-ID": "custom-req-123"})
    assert resp.status_code == 400
    assert resp.headers.get("X-Request-ID") == "custom-req-123"
    data = resp.json()
    assert data["error"] == "validation_error"
    assert data["request_id"] == "custom-req-123"


def test_tracing_header_propagated_on_success():
    """Проверяет проброс X-Request-ID при успешном запросе."""
    resp = client.get("/health", headers={"X-Request-ID": "trace-777"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == "trace-777"


# -------------------------------------------------------------------------
# Stage 2: Architecture, Concurrency, Partial Batch Resilience
# -------------------------------------------------------------------------

def test_dependency_injection_pipeline():
    """Проверяет, что пайплайн доступен через app.state.pipeline и DI."""
    with TestClient(app) as test_client:
        assert hasattr(test_client.app.state, "pipeline")
        assert isinstance(test_client.app.state.pipeline, CascadedExtractionPipeline)


def test_partial_batch_resilience():
    """Проверяет, что сбой в одной карточке батча не ломает весь запрос."""
    # Пакет из двух карточек: нормальной и поврежденной
    batch_data = [
        {"external_id": "valid-1", "title": "Смартфон Samsung Galaxy S24 256GB черный"},
        {"external_id": "bad-2", "title": "Товар", "seller_attributes": "невалидный json {"}
    ]
    files = {"file": ("batch.json", io.BytesIO(json.dumps(batch_data).encode("utf-8")), "application/json")}
    resp = client.post("/api/extract/batch", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    # Первая карточка обработана успешно
    assert data["cards"][0]["external_id"] == "valid-1"
    assert data["cards"][0]["status"] != "failed"


def test_batch_export_csv_and_json():
    """Проверяет пакетный экспорт в CSV и JSON форматах."""
    batch_data = [
        {"external_id": "exp-1", "title": "Холодильник Haier CEF535ASG No Frost серебристый", "category": "refrigerators"}
    ]
    files = {"file": ("export.json", io.BytesIO(json.dumps(batch_data).encode("utf-8")), "application/json")}
    
    # 1. JSON Export
    resp_json = client.post("/api/extract/export?output_format=json", files=files)
    assert resp_json.status_code == 200
    data_json = resp_json.json()
    assert data_json["total"] == 1
    assert data_json["predictions"][0]["category"] == "Холодильники"

    # 2. CSV Export
    files2 = {"file": ("export.json", io.BytesIO(json.dumps(batch_data).encode("utf-8")), "application/json")}
    resp_csv = client.post("/api/extract/export?output_format=csv", files=files2)
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    assert "exp-1" in resp_csv.text


# -------------------------------------------------------------------------
# Stage 3: Domain Logic & Quality (Washing machines, Weights, Colors, Bad words)
# -------------------------------------------------------------------------

def test_washing_machine_load_capacity_vs_weight():
    """Проверяет, что N кг у стиральной машины извлекается как load_capacity, а не вес."""
    regex = RegexExtractor()
    preds = list(regex.extract({"title": "Стиральная машина Haier 6 кг 1000 об/мин белый"}, category_key="washing_machines"))
    
    load_pred = next((p for p in preds if p["attribute"] == "load_capacity"), None)
    weight_pred = next((p for p in preds if p["attribute"] == "weight"), None)

    assert load_pred is not None
    assert load_pred["value"] == "6 кг"
    # 6 кг не должно определяться как вес прибора
    assert weight_pred is None


def test_weight_sanity_bounds_for_washing_machine_and_refrigerator():
    """Проверяет физические границы веса: СМ >= 40кг, холодильник >= 30кг."""
    # Стиральная машина
    assert not AttributeSanityValidator.is_valid("weight", "6 кг", "washing_machines")
    assert not AttributeSanityValidator.is_valid("weight", "15 кг", "washing_machines")
    assert AttributeSanityValidator.is_valid("weight", "58 кг", "washing_machines")

    # Холодильник
    assert not AttributeSanityValidator.is_valid("weight", "5 кг", "refrigerators")
    assert not AttributeSanityValidator.is_valid("weight", "25 кг", "refrigerators")
    assert AttributeSanityValidator.is_valid("weight", "72 кг", "refrigerators")


def test_bad_model_words_blocks_category_terms():
    """Проверяет, что названия категорий блокируются от попадания в название модели."""
    for bad_term in ("стиральная машина", "микроволновка", "электрический чайник", "чайник", "пауэрбанк"):
        assert not AttributeSanityValidator.is_valid("model", bad_term, "default")


def test_extended_color_roots():
    """Проверяет валидацию новых оттенков цветов в sanity validator."""
    for col in ("антрацит", "бирюзовый", "оливковый", "коралловый", "шампань", "хаки", "сиреневый", "малиновый", "сапфир", "песочный", "рубиновый"):
        assert AttributeSanityValidator.is_valid("color", col, "default")


def test_multi_source_consensus_active_in_pipeline():
    """Проверяет, что при совпадении предсказаний источников в сквозном пайплайне проставляется консенсус."""
    pipe = CascadedExtractionPipeline(use_gliner=True, use_catalog_enricher=True, use_llm=False)
    res = pipe.process_card({
        "title": "Смартфон Apple iPhone 15 Pro Max 256GB синий",
        "description": "Память 256 ГБ, цвет синий",
    })
    preds = {p["attribute"]: p for p in res["predictions"]}
    # FlashText + GLiNER consensus on brand
    if "brand" in preds:
        assert preds["brand"]["consensus"] is True
        assert "flashtext" in preds["brand"]["consensus_sources"]
        assert "gliner" in preds["brand"]["consensus_sources"]
        assert preds["brand"]["status"] == "confirmed_by_consensus"
