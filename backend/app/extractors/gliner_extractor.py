from __future__ import annotations

import logging
import re
from typing import Any

import torch
from gliner import GLiNER

from app.extractors.base import Prediction
from app.extractors.normalization.dictionaries import BRANDS, COLORS
from app.extractors.normalization.units import UnitNormalizer
from app.extractors.sanity import AttributeSanityValidator

logger = logging.getLogger(__name__)






class GlinerExtractor:
    """
    Tier 2: Zero-shot NER экстрактор на базе GLiNER (urchade/gliner_multi-v2.1).

    Специализируется на извлечении сложных сущностей, плохо покрываемых регулярками:
    - Модель / Серия (iPhone 15 Pro Max, RedmiBook 16, WH-1000XM5)
    - Процессор / Чипсет (Apple A17 Pro, Snapdragon 8 Gen 2, Intel Core i5)
    - Редкие бренды и составные цвета.
    """

    name: str = "gliner"
    version: str = "0.2.1"

    # Приоритетные метки для названия (максимальная плотность сущностей модели и бренда)
    TITLE_LABELS: list[str] = ["модель", "бренд", "цвет"]

    # Приоритетные метки для описания (процессор, доп. характеристики)
    DESC_LABELS: list[str] = ["процессор", "чипсет", "модель", "бренд", "цвет"]

    LABEL_TO_ATTR: dict[str, str] = {
        "бренд": "brand",
        "модель": "model",
        "цвет": "color",
        "процессор": "cpu",
        "чипсет": "cpu",
        "объём памяти": "memory_rom",
        "оперативная память": "memory_ram",
        "диагональ экрана": "screen_diagonal",
        "ёмкость аккумулятора": "battery",
        "частота обновления экрана": "refresh_rate",
        "разрешение экрана": "resolution",
        "тип уборки": "cleaning_type",
        "время работы": "working_time",
        "система разморозки": "defrost_system",
        "технология экрана": "display_tech",
        "объем": "volume",
    }

    _NUM_UNIT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([a-zA-Zа-яА-ЯёЁ\"']*)")

    def __init__(
        self,
        model_name: str = "urchade/gliner_multi-v2.1",
        threshold: float = 0.30,
        device: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.threshold = threshold
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model: GLiNER | None = None
        self._units = UnitNormalizer()
        self._validator = AttributeSanityValidator

    def _ensure_model(self) -> GLiNER:
        if self._model is None:
            logger.info("Загрузка модели GLiNER (%s) на устройство %s...", self.model_name, self.device)
            self._model = GLiNER.from_pretrained(self.model_name)
            self._model.to(self.device)
            self._model.eval()
        return self._model

    def get_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "model_name": self.model_name,
            "threshold": self.threshold,
            "device": str(self.device),
            "loaded": self._model is not None,
        }

    def health(self) -> bool:
        try:
            self._ensure_model()
            return True
        except Exception as e:
            logger.error("Health check failed for GLiNER: %s", e)
            return False

    def extract(
        self,
        card: dict[str, Any],
        target_labels: list[str] | None = None,
        category_key: str = "default",
    ) -> list[Prediction]:
        title = (card.get("title") or "").strip()
        description = (card.get("description") or "").strip()

        try:
            model = self._ensure_model()
        except Exception as e:
            logger.warning("GLiNER model unavailable (%s); falling back to rule & KB extractors.", e)
            return []

        predictions: list[Prediction] = []
        seen_attrs: set[str] = set()

        try:
            # Пасс 1: Заголовок (Title) — извлекаем все целевые метки категории
            if title:
                t_labels = target_labels or self.TITLE_LABELS
                title_entities = model.predict_entities(title, t_labels, threshold=self.threshold)
                for ent in sorted(title_entities, key=lambda x: float(x.get("score", 0.0)), reverse=True):
                    pred = self._entity_to_prediction(ent, is_title=True, category_key=category_key)
                    if pred and pred["attribute"] not in seen_attrs:
                        predictions.append(pred)
                        seen_attrs.add(pred["attribute"])

            # Пасс 2: Описание (Description) — процессор, чипсет, отсутствующие поля
            if description:
                d_labels = target_labels or self.DESC_LABELS
                desc_entities = model.predict_entities(description, d_labels, threshold=self.threshold)
                for ent in sorted(desc_entities, key=lambda x: float(x.get("score", 0.0)), reverse=True):
                    pred = self._entity_to_prediction(ent, is_title=False, category_key=category_key)
                    if pred and pred["attribute"] not in seen_attrs:
                        predictions.append(pred)
                        seen_attrs.add(pred["attribute"])
        except Exception as e:
            logger.error("Error during GLiNER prediction: %s; falling back gracefully.", e)

        return predictions

    def _entity_to_prediction(self, ent: dict, is_title: bool, category_key: str = "default") -> Prediction | None:
        label = ent["label"]
        attr_key = self.LABEL_TO_ATTR.get(label)
        if not attr_key:
            return None

        raw_text = ent["text"].strip()
        score = float(ent["score"])

        # Валидация физического здравого смысла и контекста категории
        if not self._validator.is_valid(attr_key, raw_text, category_key=category_key):
            return None

        # Нормализация
        canon_val = self._normalize(attr_key, raw_text)
        if not canon_val:
            return None

        if not self._validator.is_valid(attr_key, canon_val, category_key=category_key):
            return None

        # Калибровка уверенности:
        # Валидированная сущность, прошедшая проверку типов и нормализацию,
        # калибруется в диапазон [0.88, 0.98]
        norm_score = max(0.0, min(1.0, (score - self.threshold) / max(0.001, 1.0 - self.threshold)))
        title_boost = 0.03 if is_title else 0.0
        conf = min(0.98, 0.88 + 0.08 * norm_score + title_boost)

        return Prediction(
            attribute=attr_key,
            value=canon_val,
            confidence=round(conf, 4),
            source="gliner",
            raw=raw_text,
        )

    def _normalize(self, attr_key: str, raw: str) -> str:
        raw_clean = raw.strip().rstrip(".,;:")
        low = raw_clean.lower()

        if attr_key == "brand":
            return BRANDS.get(low, raw_clean)

        if attr_key == "color":
            # Очистка префиксов вида "колор голд", "цв синий", "цвет черный"
            clean_color = re.sub(r"^(?:цвет|колор|цв\.?|color[:\s]*)\s*", "", raw_clean, flags=re.I).strip()
            low_color = clean_color.lower()
            if low_color in COLORS:
                c_val = COLORS[low_color]
                return c_val[0] if isinstance(c_val, tuple) else c_val
            for word in low_color.split():
                if word in COLORS:
                    c_val = COLORS[word]
                    return c_val[0] if isinstance(c_val, tuple) else c_val
            return clean_color

        if attr_key in ("memory_rom", "memory_ram"):
            m = self._NUM_UNIT_RE.search(raw_clean)
            if m:
                val, unit = m.group(1), m.group(2) or "ГБ"
                try:
                    return self._units.memory(val, unit)
                except Exception:
                    pass
            return raw_clean

        if attr_key == "screen_diagonal":
            m = re.search(r"(\d+(?:[.,]\d+)?)", raw_clean)
            if m:
                try:
                    return self._units.screen_diagonal(m.group(1))
                except Exception:
                    pass
            return raw_clean

        if attr_key == "battery":
            m = re.search(r"(\d+)", raw_clean.replace(" ", ""))
            if m:
                try:
                    return self._units.battery(m.group(1))
                except Exception:
                    pass
            return raw_clean

        if attr_key == "refresh_rate":
            m = re.search(r"(\d+)", raw_clean)
            if m:
                try:
                    return self._units.refresh_rate(m.group(1))
                except Exception:
                    pass
            return raw_clean

        if attr_key == "resolution":
            m = re.search(r"(\d{3,4})\s*[*xXхХ×]\s*(\d{3,4})", raw_clean)
            if m:
                try:
                    return self._units.resolution(m.group(1), m.group(2))
                except Exception:
                    pass
            return raw_clean

        if attr_key == "cleaning_type":
            if "сух" in low and "влажн" in low:
                return "сухая и влажная"
            if "влажн" in low:
                return "влажная"
            if "сух" in low:
                return "сухая"
            return raw_clean

        if attr_key == "defrost_system":
            if "no frost" in low or "ноу фрост" in low:
                return "No Frost"
            return raw_clean

        if attr_key == "display_tech":
            for k, canon in AttributeSanityValidator.ALLOWED_DISPLAY_TECHS.items():
                if k in low:
                    return canon
            return raw_clean

        return raw_clean
