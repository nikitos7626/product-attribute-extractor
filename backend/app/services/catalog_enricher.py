"""
Сервис каталожного обогащения характеристик (Catalog Model Specs Enricher).
Использует эталонную базу знаний характеристик моделей М.Видео (catalog_models_kb.json)
для автоматического дозаполнения недостающих параметров, если продавец не указал их в тексте.
Поддерживает динамическое самообучение (Auto-Learning Feedback Loop) и регистрацию моделей по model_id.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Any

from app.config import settings
from app.extractors.base import KnowledgeBaseInterface, Prediction
from app.extractors.sanity import AttributeSanityValidator

logger = logging.getLogger(__name__)

DEFAULT_KB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    settings.catalog_kb_path,
)


class CatalogEnricher:
    """
    Обогащает карточку эталонными характеристиками из базы моделей М.Видео.
    Реализует интерфейс KnowledgeBaseInterface с поддержкой версионирования,
    горячей перезагрузки, поиска по model_id и автоматического самообучения (Auto-Learning).
    """

    version: str = settings.catalog_kb_version
    _instance: "CatalogEnricher | None" = None
    _singleton_lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(cls, kb_path: str | None = None) -> "CatalogEnricher":
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls(kb_path=kb_path)
        return cls._instance

    def __init__(self, kb_path: str | None = None) -> None:
        self.kb_path = kb_path or DEFAULT_KB_PATH
        self._lock = threading.Lock()
        self.kb: dict[str, dict[str, dict[str, str]]] = {}
        self.models_by_id: dict[str, dict[str, str]] = {}
        self._load_kb()

    def _load_kb(self) -> None:
        if not os.path.exists(self.kb_path):
            logger.warning("Catalog KB file not found at %s", self.kb_path)
            self.kb = {}
            self.models_by_id = {}
            return

        try:
            with open(self.kb_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            with self._lock:
                if isinstance(raw_data, dict) and "_by_id" in raw_data:
                    self.models_by_id = dict(raw_data.pop("_by_id"))
                else:
                    self.models_by_id = {}
                self.kb = raw_data

            total_models = sum(len(mods) for mods in self.kb.values() if isinstance(mods, dict))
            logger.info(
                "Loaded Catalog KB v%s: %d vendors, %d models, %d indexed by model_id",
                self.version,
                len(self.kb),
                total_models,
                len(self.models_by_id),
            )
        except Exception as e:
            logger.error("Failed to load Catalog KB from %s: %s", self.kb_path, e)
            self.kb = {}
            self.models_by_id = {}

    def reload(self) -> bool:
        """Горячая перезагрузка базы знаний с диска."""
        try:
            self._load_kb()
            return True
        except Exception as e:
            logger.error("Reload failed for Catalog KB: %s", e)
            return False

    def size(self) -> int:
        """Возвращает общее количество эталонных моделей в базе знаний."""
        return sum(len(mods) for mods in self.kb.values() if isinstance(mods, dict))

    def get(self, key: str) -> dict[str, Any] | None:
        """Возвращает все модели указанного вендора/бренда."""
        return self.kb.get(key.strip().lower())

    def get_info(self) -> dict[str, Any]:
        """Возвращает метаданные базы знаний."""
        return {
            "name": "catalog_models_kb",
            "version": self.version,
            "path": self.kb_path,
            "vendors_count": len(self.kb),
            "models_count": self.size(),
            "models_by_id_count": len(self.models_by_id),
            "status": "ready" if self.kb or self.models_by_id else "empty",
        }

    def register_model_specs(
        self,
        brand: str,
        model: str,
        specs: dict[str, str],
        model_id: str | None = None,
        persist: bool = True,
    ) -> bool:
        """
        Динамическое самообучение базы знаний: сохраняет эталонные характеристики модели
        по model_id и brand+model с атомарной синхронизацией на диск.
        """
        if not specs:
            return False

        b_key = brand.strip().lower() if brand else ""
        m_key = model.strip().lower() if model else ""

        with self._lock:
            # 1. Регистрация в вендорском дереве (brand -> model)
            if b_key and m_key:
                if b_key not in self.kb:
                    self.kb[b_key] = {}
                if m_key not in self.kb[b_key]:
                    self.kb[b_key][m_key] = {}

                for k, v in specs.items():
                    if v and str(v).strip():
                        self.kb[b_key][m_key][k] = str(v).strip()

            # 2. Регистрация по model_id / SKU ID
            if model_id:
                mid_key = str(model_id).strip()
                if mid_key not in self.models_by_id:
                    self.models_by_id[mid_key] = {}
                if b_key and "brand" not in self.models_by_id[mid_key]:
                    self.models_by_id[mid_key]["brand"] = brand.strip()
                if m_key and "model" not in self.models_by_id[mid_key]:
                    self.models_by_id[mid_key]["model"] = model.strip()

                for k, v in specs.items():
                    if v and str(v).strip():
                        self.models_by_id[mid_key][k] = str(v).strip()

        if persist:
            self._save_kb_atomic()

        logger.info(
            "Auto-learned model specs in Catalog KB: brand='%s', model='%s', model_id='%s', attrs=%d",
            brand,
            model,
            model_id,
            len(specs),
        )
        return True

    def _save_kb_atomic(self) -> None:
        """Потокобезопасная и межпроцессно-безопасная атомарная запись KB на диск."""
        try:
            from app.services.brand_registry import process_file_lock

            with process_file_lock(self.kb_path, timeout=5.0):
                with self._lock:
                    dump_data = dict(self.kb)
                    if self.models_by_id:
                        dump_data["_by_id"] = self.models_by_id

                    tmp_file = f"{self.kb_path}.tmp.{os.getpid()}"
                    with open(tmp_file, "w", encoding="utf-8") as f:
                        json.dump(dump_data, f, ensure_ascii=False, indent=2)
                    os.replace(tmp_file, self.kb_path)
        except Exception as e:
            logger.warning("Failed to atomically persist Catalog KB: %s", e)

    def find_model_specs(
        self,
        brand: str | None = None,
        model: str | None = None,
        model_id: str | None = None,
    ) -> dict[str, str] | None:
        """
        Ищет спецификации модели:
        1. Сначала по model_id (если передан идентификатор модели или SKU).
        2. Затем по brand + model (прямое совпадение, подстрока, fuzzy search).
        """
        # 1. Поиск по model_id
        if model_id:
            mid_key = str(model_id).strip()
            with self._lock:
                if mid_key in self.models_by_id:
                    return dict(self.models_by_id[mid_key])

        if not brand or not model or not self.kb:
            return None

        b_key = brand.strip().lower()
        vendor_models = self.kb.get(b_key)
        if not vendor_models:
            # Попробуем найти среди всех вендоров частичное совпадение
            for v, v_mods in self.kb.items():
                if isinstance(v_mods, dict) and (v in b_key or b_key in v):
                    vendor_models = v_mods
                    break

        if not vendor_models or not isinstance(vendor_models, dict):
            return None

        m_clean = model.strip().lower()
        # 1. Прямое совпадение
        if m_clean in vendor_models:
            return dict(vendor_models[m_clean])

        # 2. Поиск по подстроке (например "galaxy s22+ 8/128gb" содержит "galaxy s22+")
        best_match = None
        longest_key_len = 0
        for k, specs in vendor_models.items():
            if not isinstance(specs, dict):
                continue
            if (k in m_clean or m_clean in k) and len(k) > longest_key_len:
                best_match = specs
                longest_key_len = len(k)

        if best_match and longest_key_len >= 3:
            return dict(best_match)

        # 3. Fuzzy search через rapidfuzz если доступен
        try:
            from rapidfuzz import fuzz, process

            choices = list(vendor_models.keys())
            match = process.extractOne(m_clean, choices, scorer=fuzz.token_set_ratio)
            if match and match[1] >= 85:
                res = vendor_models[match[0]]
                if isinstance(res, dict):
                    return dict(res)
        except ImportError:
            pass

        return None

    def enrich(
        self,
        brand: str,
        model: str,
        missing_attrs: set[str],
        category_key: str,
        model_id: str | None = None,
    ) -> list[Prediction]:
        """
        Возвращает список предсказаний для недостающих атрибутов, найденных в каталоге
        по model_id или паре brand+model.
        """
        if not missing_attrs:
            return []

        specs = self.find_model_specs(brand=brand, model=model, model_id=model_id)
        if not specs:
            return []

        enriched: list[Prediction] = []
        for attr in missing_attrs:
            val = specs.get(attr)
            if not val:
                continue

            # Валидация физического здравого смысла
            if not AttributeSanityValidator.is_valid(attr, val, category_key):
                continue

            enriched.append({
                "attribute": attr,
                "value": val,
                "confidence": float(getattr(settings, "prior_catalog_kb", 0.94)),
                "source": "catalog_kb",
                "tier": "Tier 2.5",
                "raw": val,
                "grounded": True,
            })

        return enriched
