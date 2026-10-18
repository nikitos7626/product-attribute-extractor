"""
Тесты динамической регистрации брендов (BrandRegistry) и строгого LLM-фоллбэка (StrictLlmFallbackExtractor).
"""
from __future__ import annotations

import uuid
from unittest.mock import patch
import pytest

from app.extractors.llm_extractor import StrictLlmFallbackExtractor
from app.extractors.regex_extractor import RegexExtractor
from app.services.brand_registry import BrandRegistry
from app.services.pipeline import CascadedExtractionPipeline


def test_dynamic_brand_registration():
    """
    Проверяет:
    1. Регистрацию нового бренда в BrandRegistry на лету.
    2. Мгновенную реакцию RegexExtractor (FlashText) без перезапуска сервиса.
    """
    registry = BrandRegistry.get_instance()
    uid = uuid.uuid4().hex[:6]
    test_alias = f"novatech_{uid}"
    test_canon = f"NovaTech_{uid.upper()}"

    # До регистрации
    assert not registry.has_brand(test_alias)

    # Регистрация (in-memory test with persist=False)
    ok = registry.register_brand(test_alias, test_canon, persist=False)
    assert ok is True

    assert registry.has_brand(test_alias)
    assert registry.get_canonical(test_alias) == test_canon

    # RegexExtractor должен сразу находить этот бренд благодаря подписке
    extractor = RegexExtractor()
    preds = extractor.extract({"title": f"Смартфон {test_canon} Pro 256GB"})
    brand_preds = [p for p in preds if p["attribute"] == "brand"]
    assert len(brand_preds) == 1
    assert brand_preds[0]["value"] == test_canon


def test_strict_llm_fallback_disabled_by_default_without_key():
    """
    Проверяет безопасный фоллбэк: если API-ключ не задан, LLM не вызывается и не падает.
    """
    extractor = StrictLlmFallbackExtractor(api_key="")
    assert extractor.is_enabled is False
    res = extractor.enrich_missing_attributes(
        brand="BrandX",
        model="ModelY",
        missing_attrs={"battery", "screen_diagonal"},
        category_key="smartphones",
    )
    assert res == []


def test_strict_llm_fallback_success_mocked():
    """
    Проверяет успешное заполнение недостающих полей через LLM при наличии строгой валидации.
    """
    extractor = StrictLlmFallbackExtractor(api_key="test-key", api_base="https://api.openai.com/v1")
    assert extractor.is_enabled is True

    mock_llm_response = '{"battery": "5000 мАч", "screen_diagonal": "6.67\\""}'

    with patch.object(extractor, "_call_llm", return_value=mock_llm_response):
        res = extractor.enrich_missing_attributes(
            brand="Poco",
            model="X6 Pro",
            missing_attrs={"battery", "screen_diagonal"},
            category_key="smartphones",
        )

        preds = {p["attribute"]: p["value"] for p in res}
        sources = {p["attribute"]: p["source"] for p in res}

        assert preds["battery"] == "5000 мАч"
        assert preds["screen_diagonal"] == '6.67"'
        assert sources["battery"] == "llm_strict"
        assert sources["screen_diagonal"] == "llm_strict"


def test_strict_llm_fallback_sanity_rejection_mocked():
    """
    Проверяет Guardrail: если LLM галлюцинирует абсурдное значение (120 000 мАч для телефона),
    AttributeSanityValidator его отсекает, и галлюцинация не попадает в результат.
    """
    extractor = StrictLlmFallbackExtractor(api_key="test-key")

    mock_insane_response = '{"battery": "120000 мАч", "screen_diagonal": "6.7\\""}'

    with patch.object(extractor, "_call_llm", return_value=mock_insane_response):
        res = extractor.enrich_missing_attributes(
            brand="SuperPhone",
            model="Pro",
            missing_attrs={"battery", "screen_diagonal"},
            category_key="smartphones",
        )

        preds = {p["attribute"]: p["value"] for p in res}
        # 120 000 мАч отсеяно валидатором здравого смысла
        assert "battery" not in preds
        # 6.7" валидно и принято
        assert preds["screen_diagonal"] == '6.7"'


def test_pipeline_with_mocked_llm_enrichment():
    """
    Проверяет полный сквозной пайплайн с точечным вызовом LLM при отсутствии данных в каталоге.
    """
    pipeline = CascadedExtractionPipeline(use_gliner=False, use_catalog_enricher=False, use_llm=True)
    pipeline.llm_extractor.is_enabled = True

    mock_resp = '{"battery": "4800 мАч", "screen_diagonal": "6.5\\""}'
    with patch.object(pipeline.llm_extractor, "_call_llm", return_value=mock_resp):
        res = pipeline.process_card({
            "title": "Смартфон Samsung Galaxy S25 256GB белый",
            "description": "Продам телефон",
        })

        preds = {p["attribute"]: p["value"] for p in res["predictions"]}
        sources = {p["attribute"]: p.get("source") for p in res["predictions"]}

        assert preds["brand"] == "Samsung"
        assert preds["memory_rom"] == "256 ГБ"
        assert preds["battery"] == "4800 мАч"
        assert sources["battery"] == "llm_strict"


def test_llm_normalization_nested_and_numeric():
    """
    Проверяет, что LLM extractor корректно преобразует сырые числа, единицы и вложенные структуры
    в стандартные форматы М.Видео (мАч, дюймы, ГБ).
    """
    extractor = StrictLlmFallbackExtractor(api_key="test-key")
    mock_resp = '{"battery": 5000, "screen_diagonal": 6.78, "memory_ram": {"capacity": "12 GB"}}'

    with patch.object(extractor, "_call_llm", return_value=mock_resp):
        res = extractor.enrich_missing_attributes(
            brand="Realme",
            model="GT 6T",
            missing_attrs={"battery", "screen_diagonal", "memory_ram"},
            category_key="smartphones",
        )

        preds = {p["attribute"]: p["value"] for p in res}
        assert preds["battery"] == "5000 мАч"
        assert preds["screen_diagonal"] == '6.78"'
        assert preds["memory_ram"] == "12 ГБ"


def test_llm_verify_new_brand():
    """
    Проверяет валидацию кандидата в бренды через LLM (YES / NO).
    """
    extractor = StrictLlmFallbackExtractor(api_key="test-key")

    with patch.object(extractor, "_call_llm", return_value="YES"):
        assert extractor.verify_new_brand("Tecno", "смартфон Tecno Spark 20") is True

    with patch.object(extractor, "_call_llm", return_value="NO"):
        assert extractor.verify_new_brand("СуперДевайс", "купить СуперДевайс со скидкой") is False


def test_reasoning_model_fallback_parsing():
    """
    Проверяет извлечение JSON из блока reasoning думающих моделей (DeepSeek / Reasoning),
    когда поле content пустое или None.
    """
    extractor = StrictLlmFallbackExtractor(api_key="test-key")

    mock_reasoning_json = '{"brand": "DEMIAND", "model": "Tison Pro DK-2100"}'
    with patch.object(extractor, "_call_llm", return_value=mock_reasoning_json):
        b, m = extractor.extract_brand_and_model_for_new_product(
            title="Аэрогриль DEMIAND Tison Pro DK-2100 5.5л 1800Вт черный",
            category_name="Аэрогрили",
        )
        assert b == "DEMIAND"
        assert m == "Tison Pro DK-2100"


def test_title_structural_heuristic_new_product():
    """
    Проверяет синтаксический эвристический парсер заголовка e-commerce
    [Категория] [Бренд] [Модель] [Характеристики].
    """
    b1, m1 = CascadedExtractionPipeline._parse_title_structure(
        "Аэрогриль DEMIAND Tison Pro DK-2100 5.5л 1800Вт черный",
        "Аэрогрили",
    )
    assert b1 == "DEMIAND"
    assert m1 == "Tison Pro DK-2100"

    b2, m2 = CascadedExtractionPipeline._parse_title_structure(
        "Кофеварка HiBREW H10A рожковая серебристая",
        "Кофеварки",
    )
    assert b2 == "HiBREW"
    assert m2 == "H10A"


def test_pipeline_new_unknown_product_end_to_end():
    """
    Сквозной тест: полностью незнакомый китайский товар автоматически получает
    бренд, модель и характеристики без падений.
    """
    pipeline = CascadedExtractionPipeline(use_gliner=False, use_catalog_enricher=False, use_llm=False)
    res = pipeline.process_card({
        "title": "Аэрогриль DEMIAND Tison Pro DK-2100 5.5л 1800Вт черный",
        "description": "Мощный аэрогриль с антипригарным покрытием",
    })

    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds.get("brand") == "DEMIAND"
    assert preds.get("model") == "Tison Pro DK-2100"
    assert preds.get("color") in ("черный", "чёрный")

