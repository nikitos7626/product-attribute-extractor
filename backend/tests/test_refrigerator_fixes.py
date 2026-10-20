from __future__ import annotations

import pytest
from app.services.pipeline import CascadedExtractionPipeline


@pytest.fixture(scope="module")
def pipeline():
    return CascadedExtractionPipeline(use_gliner=False)


def test_refrigerator_haier_useful_volume_and_tier1_optimizations(pipeline):
    """
    Тест исправления 3 проблем для категории 'Холодильники':
    1. Приоритет полезного объема (386 л) над общим (400 л) и камерами (278 л, 108 л).
    2. Извлечение габаритов (dimensions: 59.5x199.8x67.2 см) без штрафа к missing.
    3. Распознавание Total No Frost на уровне Tier 1 (source='regex').
    """
    card = {
        "title": "Холодильник Haier C2F637CFMV (серебристый металлик, Total No Frost)",
        "description": (
            "Вместительный двухкамерный холодильник высотой 199.8 см "
            "(габариты ШхВхГ: 59.5x199.8x67.2 см)... "
            "Общий объем модели составляет 400 л, а полезный объем — 386 л "
            "(из них просторная холодильная камера на 278 л и нижняя морозильная камера на 108 л)..."
        ),
    }
    res = pipeline.process_card(card)

    assert res["category"] == "Холодильники"
    assert res["missing"] == []

    preds = {p["attribute"]: p for p in res["predictions"]}

    # 1. Полезный объем
    assert "volume" in preds
    assert preds["volume"]["value"] == "386 л"
    assert preds["volume"]["source"] == "regex"

    # 2. Габариты
    assert "dimensions" in preds
    assert preds["dimensions"]["value"] == "59.5x199.8x67.2 см"
    assert preds["dimensions"]["source"] == "regex"

    # 3. Система разморозки (Tier 1)
    assert "defrost_system" in preds
    assert preds["defrost_system"]["value"] == "No Frost"
    assert preds["defrost_system"]["source"] == "regex"

    # 4. Бренд и цвет
    assert preds["brand"]["value"] == "Haier"
    assert preds["color"]["value"] == "серебристый"


def test_refrigerator_total_volume_fallback(pipeline):
    """При отсутствии полезного объема берется общий объем."""
    card = {
        "title": "Холодильник ATLANT ХМ-4208-000 белый",
        "description": "Двухкамерный холодильник. Общий объем составляет 185 л. Система капельная.",
    }
    res = pipeline.process_card(card)
    preds = {p["attribute"]: p for p in res["predictions"]}

    assert preds["volume"]["value"] == "185 л"
    assert preds["defrost_system"]["value"] == "Капельная"
    assert preds["defrost_system"]["source"] == "regex"
