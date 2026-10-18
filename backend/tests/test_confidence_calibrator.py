import pytest
from app.services.confidence_calibrator import ConfidenceCalibrator


def test_temperature_scaling_gliner():
    calibrator = ConfidenceCalibrator.get_instance()
    
    # Очень высокий сырой скор 0.99 масштабируется температурой T=1.25
    calibrated = calibrator.calibrate_attribute(
        attribute="cpu",
        value="Snapdragon 8 Gen 3",
        raw_confidence=0.99,
        source="gliner",
        category_key="smartphones",
        in_title=False,
    )
    assert 0.85 <= calibrated <= 0.98
    assert calibrated < 0.99  # Сглажен overconfidence


def test_multi_source_consensus_boost():
    calibrator = ConfidenceCalibrator.get_instance()

    predictions = {
        "memory_rom": {
            "attribute": "memory_rom",
            "value": "256 ГБ",
            "confidence": 0.92,
            "source": "regex",
        }
    }
    # Альтернативный источник (GLiNER) извлёк то же самое значение
    alternatives = {
        "memory_rom": [
            {"source": "gliner", "value": "256 ГБ", "confidence": 0.88}
        ]
    }

    calibrator.apply_multi_source_consensus(predictions, alternatives)

    # Байесовское объединение: 1 - (1 - 0.92)*(1 - 0.88) = 1 - 0.08*0.12 = 0.9904
    pred = predictions["memory_rom"]
    assert pred.get("consensus") is True
    assert pred["confidence"] >= 0.95
    assert "regex" in pred["consensus_sources"]
    assert "gliner" in pred["consensus_sources"]


def test_multi_source_conflict_penalty():
    calibrator = ConfidenceCalibrator.get_instance()

    predictions = {
        "memory_rom": {
            "attribute": "memory_rom",
            "value": "256 ГБ",
            "confidence": 0.90,
            "source": "regex",
        }
    }
    # Альтернативный источник извлёк ДРУГОЕ значение (конфликт)
    alternatives = {
        "memory_rom": [
            {"source": "gliner", "value": "128 ГБ", "confidence": 0.85}
        ]
    }

    calibrator.apply_multi_source_consensus(predictions, alternatives)

    pred = predictions["memory_rom"]
    assert pred.get("conflict") is True
    assert pred["confidence"] < 0.90  # Наложен штраф за разногласие


def test_geometric_mean_card_penalty():
    calibrator = ConfidenceCalibrator.get_instance()
    required = {"brand", "model", "screen_diagonal", "memory_rom", "battery", "color"}

    # Сценарий А: Все обязательные поля заполнены с хорошей уверенностью
    full_card_preds = [
        {"attribute": "brand", "value": "Apple", "confidence": 0.96},
        {"attribute": "model", "value": "iPhone 15", "confidence": 0.95},
        {"attribute": "screen_diagonal", "value": '6.1"', "confidence": 0.94},
        {"attribute": "memory_rom", "value": "128 ГБ", "confidence": 0.95},
        {"attribute": "battery", "value": "3349 мАч", "confidence": 0.92},
        {"attribute": "color", "value": "черный", "confidence": 0.95},
    ]
    conf_full, missing_full = calibrator.calculate_card_confidence(full_card_preds, required, "smartphones")
    assert len(missing_full) == 0
    assert conf_full >= 0.90

    # Сценарий Б: Пропущено 3 обязательных поля из 6
    half_card_preds = [
        {"attribute": "brand", "value": "Apple", "confidence": 0.96},
        {"attribute": "model", "value": "iPhone 15", "confidence": 0.95},
        {"attribute": "color", "value": "черный", "confidence": 0.95},
    ]
    conf_half, missing_half = calibrator.calculate_card_confidence(half_card_preds, required, "smartphones")
    assert len(missing_half) == 3
    # Нелинейный штраф: (3/6)^1.5 = 0.353 -> итоговый скор резко обрушивается
    assert conf_half < 0.40


def test_expected_calibration_error_calculation():
    calibrator = ConfidenceCalibrator.get_instance()

    # Идеально откалиброванные предсказания
    y_true = [1, 1, 1, 1, 0, 0, 0, 0]
    y_prob = [0.9, 0.85, 0.8, 0.75, 0.2, 0.15, 0.1, 0.05]

    ece = calibrator.expected_calibration_error(y_true, y_prob, n_bins=2)
    assert 0.0 <= ece <= 0.25
