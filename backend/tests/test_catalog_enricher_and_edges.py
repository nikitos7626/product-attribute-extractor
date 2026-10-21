"""
Тесты каталожного обогащения (CatalogEnricher) и краевых случаев (Edge Cases).
Проверяют:
1. Автоматическое дозаполнение отсутствующих характеристик из базы каталога М.Видео.
2. Равенство брендов (срабатывание для флагманов и редких моделей).
3. Приоритет текста продавца над каталогом (Grounding Guardrail).
4. Корректную обработку неизвестных брендов (Graceful Fallback).
5. Защиту от грязного ввода (шум, спецсимволы, кавычки).
6. Защиту от дублирования бренда в названии модели.
"""
from __future__ import annotations

import pytest
from app.services.pipeline import CascadedExtractionPipeline


@pytest.fixture(scope="module")
def pipeline():
    return CascadedExtractionPipeline(use_gliner=True, use_catalog_enricher=True)


def test_edge_case_1_auto_enrichment_galaxy_s22(pipeline):
    """
    Кейс: Продавец указал только бренд, модель и цвет, забыв написать батарею и диагональ.
    Ожидание: CatalogEnricher автоматически подтягивает батарею (4500 мАч) и диагональ (6.6")
    из базы М.Видео, и карточка публикуется без отправки в ручную очередь.
    """
    card = {
        "title": "Смартфон Samsung Galaxy S22+ 256GB фантом белый",
        "description": "Продам отличный флагман в идеальном состоянии, в комплекте коробка и провод.",
    }
    res = pipeline.process_card(card)
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    sources = {p["attribute"]: p.get("source") for p in res["predictions"]}

    assert preds["brand"] == "Samsung"
    assert "Galaxy S22" in preds["model"]
    assert preds["color"] == "белый"
    assert preds["memory_rom"] == "256 ГБ"

    # Батарея и экран должны быть автоматически дозаполнены из каталога
    assert "battery" in preds
    assert "мАч" in preds["battery"]
    assert sources["battery"] == "catalog_kb"

    assert "screen_diagonal" in preds
    assert sources["screen_diagonal"] == "catalog_kb"

    # Карточка полностью заполнена, отсутствующих полей нет
    assert res["missing"] == []
    assert res["needs_review"] is False


def test_edge_case_2_seller_grounding_priority(pipeline):
    """
    Кейс: Приоритет текста продавца (Grounding Check).
    Если продавец явно указал память 512 ГБ, а в базе каталога базовая модель на 128/256 ГБ,
    система ОБЯЗАНА сохранить значение продавца (512 ГБ), а не перезаписывать его базой!
    """
    card = {
        "title": "Samsung Galaxy S22+ 512GB черный",
        "description": "Максимальная комплектация на 512 Гб встроенной памяти, экран 6.6 дюймов.",
    }
    res = pipeline.process_card(card)
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}

    # Память должна остаться 512 ГБ из текста продавца
    assert preds["memory_rom"] == "512 ГБ"
    # Батарея дозаполнена из каталога
    assert "battery" in preds
    assert "мАч" in preds["battery"]


def test_edge_case_3_unknown_brand_graceful_fallback(pipeline):
    """
    Кейс: Неизвестный/новый бренд (NovaTech), которого нет в каталоге.
    Ожидание: Система не падает, извлекает то, что есть в тексте,
    и честно отправляет в очередь модерации (needs_review=True).
    """
    card = {
        "title": "Смартфон NovaTech Quantum X 128GB Черный",
        "description": "Новый китайский телефон, быстрый и удобный.",
    }
    res = pipeline.process_card(card)
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}

    # Извлечено то, что физически было в тексте
    assert preds.get("memory_rom") == "128 ГБ"
    assert preds.get("color") in ["черный", "чёрный"]
    # Недостающие обязательные поля (экран, батарея) не выдуманы
    assert "battery" in res["missing"] or "screen_diagonal" in res["missing"]
    assert res["needs_review"] is True


def test_edge_case_4_noisy_dirty_input(pipeline):
    """
    Кейс: Экстремально грязный ввод с кавычками, скобками, множественными пробелами и капсом.
    Ожидание: Корректная очистка и нормализация значений.
    """
    card = {
        "title": "  \n\n<< Смартфон >>   SAMSUNG   Galaxy   S22+ !!!   (256GB, фантом   БЕЛЫЙ)  \n\n",
        "description": "   Аккумулятор:   4500 мАч ,   диагональ: 6.6\"   -- СУПЕР СОСТОЯНИЕ!! ",
    }
    res = pipeline.process_card(card)
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}

    assert preds["brand"] == "Samsung"
    assert preds["color"] == "белый"
    assert preds["memory_rom"] == "256 ГБ"
    assert "4500" in preds["battery"]
    assert "6.6" in preds["screen_diagonal"].replace(",", ".")
    assert res["needs_review"] is False


def test_edge_case_5_brand_duplication_guard(pipeline):
    """
    Кейс: Продавец написал 'Xiaomi Redmi Note 13 Pro'.
    Ожидание: Бренд = 'Xiaomi', модель = 'Redmi Note 13 Pro' (без дублирования 'Xiaomi').
    """
    card = {
        "title": "Смартфон Xiaomi Redmi Note 13 Pro 8/256GB черный",
        "description": "Батарея 5000 мАч, дисплей 6.67 дюймов AMOLED.",
    }
    res = pipeline.process_card(card)
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}

    assert preds["brand"] == "Xiaomi"
    assert not preds["model"].lower().startswith("xiaomi")
    assert "Redmi Note 13 Pro" in preds["model"]


def test_dynamic_model_registration_by_id_and_auto_enrichment(pipeline):
    """
    Проверяет:
    1. Автоматическую регистрацию новой модели по model_id в CatalogEnricher на лету.
    2. Мгновенное обогащение последующей карточки того же model_id, где продавец опустил характеристики.
    """
    enricher = pipeline.catalog_enricher
    assert enricher is not None

    test_model_id = "MODEL-AUTOTEST-777"
    test_brand = "QuantumTech"
    test_model = "HyperPhone X"
    test_specs = {
        "battery": "6800 мАч",
        "screen_diagonal": '6.8"',
        "cpu": "Snapdragon 8 Gen 4",
    }

    # 1. Регистрация спецификаций модели по ID
    ok = enricher.register_model_specs(
        brand=test_brand,
        model=test_model,
        specs=test_specs,
        model_id=test_model_id,
        persist=False,
    )
    assert ok is True

    # 2. Поиск по model_id
    found_by_id = enricher.find_model_specs(model_id=test_model_id)
    assert found_by_id is not None
    assert found_by_id["battery"] == "6800 мАч"
    assert found_by_id["cpu"] == "Snapdragon 8 Gen 4"

    # 3. Поиск по brand + model
    found_by_name = enricher.find_model_specs(brand=test_brand, model=test_model)
    assert found_by_name is not None
    assert found_by_name["battery"] == "6800 мАч"

    # 4. Прогон карточки в пайплайне: продавец указал только model_id, память и цвет
    card = {
        "model_id": test_model_id,
        "title": f"Смартфон {test_brand} {test_model} 12/256GB черный",
        "description": "Продам новый телефон в коробке.",
    }
    res = pipeline.process_card(card)
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    sources = {p["attribute"]: p.get("source") for p in res["predictions"]}

    assert preds["brand"].lower() == test_brand.lower()
    assert preds["model"] == test_model
    assert preds["color"] in ("черный", "чёрный")
    assert preds["memory_rom"] == "256 ГБ"

    # Батарея и диагональ должны автоматически подтянуться из базы по model_id!
    assert preds["battery"] == "6800 мАч"
    assert sources["battery"] == "catalog_kb"
    assert preds["screen_diagonal"] == '6.8"'
    assert sources["screen_diagonal"] == "catalog_kb"
