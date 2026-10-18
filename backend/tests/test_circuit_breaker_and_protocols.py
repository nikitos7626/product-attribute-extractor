import unittest
from unittest.mock import patch, MagicMock
import httpx
from app.extractors.base import BaseExtractor, KnowledgeBaseInterface, LlmFallbackInterface
from app.extractors.regex_extractor import RegexExtractor
from app.extractors.gliner_extractor import GlinerExtractor
from app.extractors.llm_extractor import StrictLlmFallbackExtractor
from app.services.catalog_enricher import CatalogEnricher
from app.extractors.sanity import AttributeSanityValidator


def test_protocols_runtime_checkable():
    """Тест поддержки @runtime_checkable и соответствия протоколам."""
    regex = RegexExtractor()
    assert isinstance(regex, BaseExtractor)

    enricher = CatalogEnricher()
    assert isinstance(enricher, KnowledgeBaseInterface)

    llm = StrictLlmFallbackExtractor(api_key="test-key")
    assert isinstance(llm, LlmFallbackInterface)
    assert isinstance(llm, BaseExtractor)


def test_circuit_breaker_trips_on_http_500():
    """Тест автоматического размыкания Circuit Breaker при серии ошибок HTTP 500."""
    llm = StrictLlmFallbackExtractor(
        api_key="test-key",
        max_consecutive_failures=3,
        circuit_cooldown_seconds=60.0,
    )
    assert llm.is_circuit_open() is False
    assert llm.consecutive_failures == 0

    mock_resp_500 = MagicMock()
    mock_resp_500.status_code = 500
    mock_resp_500.text = "Internal Server Error"

    with patch("httpx.Client.post", return_value=mock_resp_500):
        # 1-я ошибка
        res1 = llm.enrich_missing_attributes("Apple", "iPhone 16", {"battery"}, "smartphones")
        assert res1 == []
        assert llm.consecutive_failures == 1
        assert llm.is_circuit_open() is False

        # 2-я ошибка
        res2 = llm.enrich_missing_attributes("Apple", "iPhone 16", {"battery"}, "smartphones")
        assert res2 == []
        assert llm.consecutive_failures == 2
        assert llm.is_circuit_open() is False

        # 3-я ошибка -> Предохранитель размыкается!
        res3 = llm.enrich_missing_attributes("Apple", "iPhone 16", {"battery"}, "smartphones")
        assert res3 == []
        assert llm.consecutive_failures == 3
        assert llm.is_circuit_open() is True
        assert llm.health() is False


def test_working_time_sanity_validation():
    """Тест валидатора здравого смысла для времени автономной работы."""
    assert AttributeSanityValidator.is_valid("working_time", "30 ч", "headphones") is True
    assert AttributeSanityValidator.is_valid("working_time", "150 мин", "vacuum_cleaners") is True
    # Мусорный заголовок без цифр должен быть отклонён
    assert AttributeSanityValidator.is_valid("working_time", "Время автономной работы", "headphones") is False
    assert AttributeSanityValidator.is_valid("working_time", "быстрая зарядка", "headphones") is False


def test_llm_grounding_verification():
    """Тест программной проверки заземления LLM-ответов на исходный текст (Grounding & Anti-Hallucination)."""
    llm_strict = StrictLlmFallbackExtractor(api_key="test-key", enforce_grounding=True)
    mock_resp = '{"battery": "5000 мАч", "screen_diagonal": "6.7\\""}'

    with patch.object(StrictLlmFallbackExtractor, "_call_llm", return_value=mock_resp):
        # 1. Текст содержит только батарею (5000), но не содержит диагональ 6.7
        res1 = llm_strict.enrich_missing_attributes(
            brand="SomeUnknownBrand",
            model="ModelX",
            missing_attrs={"battery", "screen_diagonal"},
            category_key="smartphones",
            raw_text="Смартфон с мощным аккумулятором 5000 мАч на 2 дня работы",
        )
        preds1 = {p["attribute"]: p["value"] for p in res1}
        # 5000 мАч заземлено в тексте -> принято
        assert preds1.get("battery") == "5000 мАч"
        # 6.7" не упомянуто в тексте и отсутствует в KB -> отклонено защитой от галлюцинаций
        assert "screen_diagonal" not in preds1

        # 2. Если заземление отключено, принимаются все синтаксически валидные значения
        llm_relaxed = StrictLlmFallbackExtractor(api_key="test-key", enforce_grounding=False)
        res2 = llm_relaxed.enrich_missing_attributes(
            brand="SomeUnknownBrand",
            model="ModelX",
            missing_attrs={"battery", "screen_diagonal"},
            category_key="smartphones",
            raw_text="Краткое описание без цифр",
        )
        preds2 = {p["attribute"]: p["value"] for p in res2}
        assert preds2.get("battery") == "5000 мАч"
        assert preds2.get("screen_diagonal") == '6.7"'

