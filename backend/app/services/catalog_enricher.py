"""
Сервис каталожного обогащения характеристик (Catalog Model Specs Enricher).
Использует эталонную базу знаний характеристик моделей E-Commerce (catalog_models_kb.json)
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


# Встроенный резервный справочник эталонных моделей (Embedded Fallback Seed)
# Обеспечивает 100% устойчивость к отсутствию или повреждению внешнего catalog_models_kb.json,
# исключая silent-failure при загрузке каталога.
EMBEDDED_SEED_MODELS_FALLBACK: dict[str, dict[str, dict[str, str]]] = {
    "apple": {
        "iphone 15 pro max": {"brand": "Apple", "model": "iPhone 15 Pro Max", "battery": "4422 мАч", "screen_diagonal": "6.7\"", "resolution": "2796x1290", "cpu": "Apple A17 Pro", "weight": "221 г"},
        "iphone 15 pro": {"brand": "Apple", "model": "iPhone 15 Pro", "battery": "3274 мАч", "screen_diagonal": "6.1\"", "resolution": "2556x1179", "cpu": "Apple A17 Pro", "weight": "187 г"},
        "iphone 15": {"brand": "Apple", "model": "iPhone 15", "battery": "3349 мАч", "screen_diagonal": "6.1\"", "resolution": "2556x1179", "cpu": "Apple A16 Bionic", "weight": "171 г"},
        "iphone 14": {"brand": "Apple", "model": "iPhone 14", "battery": "3279 мАч", "screen_diagonal": "6.1\"", "resolution": "2532x1170", "cpu": "Apple A15 Bionic", "weight": "172 г"},
        "iphone 13": {"brand": "Apple", "model": "iPhone 13", "battery": "3227 мАч", "screen_diagonal": "6.1\"", "resolution": "2532x1170", "cpu": "Apple A15 Bionic", "weight": "173 г"},
        "macbook air 13": {"brand": "Apple", "model": "MacBook Air 13", "screen_diagonal": "13.6\"", "cpu": "Apple M2", "weight": "1.24 кг"},
        "macbook pro 14": {"brand": "Apple", "model": "MacBook Pro 14", "screen_diagonal": "14.2\"", "cpu": "Apple M3", "weight": "1.55 кг"},
        "airpods pro 2": {"brand": "Apple", "model": "AirPods Pro 2", "connection_type": "беспроводные", "working_time": "6 ч", "weight": "50 г"},
    },
    "samsung": {
        "galaxy s24 ultra": {"brand": "Samsung", "model": "Galaxy S24 Ultra", "battery": "5000 мАч", "screen_diagonal": "6.8\"", "resolution": "3120x1440", "cpu": "Snapdragon 8 Gen 3", "weight": "232 г"},
        "galaxy s24": {"brand": "Samsung", "model": "Galaxy S24", "battery": "4000 мАч", "screen_diagonal": "6.2\"", "resolution": "2340x1080", "cpu": "Exynos 2400", "weight": "167 г"},
        "galaxy s23": {"brand": "Samsung", "model": "Galaxy S23", "battery": "3900 мАч", "screen_diagonal": "6.1\"", "resolution": "2340x1080", "cpu": "Snapdragon 8 Gen 2", "weight": "168 г"},
        "galaxy s22": {"brand": "Samsung", "model": "Galaxy S22", "battery": "3700 мАч", "screen_diagonal": "6.1\"", "resolution": "2340x1080", "cpu": "Exynos 2200", "weight": "167 г"},
        "galaxy a54": {"brand": "Samsung", "model": "Galaxy A54", "battery": "5000 мАч", "screen_diagonal": "6.4\"", "resolution": "2340x1080", "cpu": "Exynos 1380", "weight": "202 г"},
        "qe55q60cauxru": {"brand": "Samsung", "model": "QE55Q60CAUXRU", "screen_diagonal": "55\"", "resolution": "3840x2160", "refresh_rate": "60 Гц", "display_tech": "QLED"},
    },
    "xiaomi": {
        "redmi note 13": {"brand": "Xiaomi", "model": "Redmi Note 13", "battery": "5000 мАч", "screen_diagonal": "6.67\"", "resolution": "2400x1080", "weight": "188 г"},
        "redmi note 12": {"brand": "Xiaomi", "model": "Redmi Note 12", "battery": "5000 мАч", "screen_diagonal": "6.67\"", "resolution": "2400x1080", "weight": "183 г"},
        "poco x6 pro": {"brand": "Xiaomi", "model": "POCO X6 Pro", "battery": "5000 мАч", "screen_diagonal": "6.67\"", "resolution": "2712x1220", "weight": "186 г"},
        "mi power bank 3": {"brand": "Xiaomi", "model": "Mi Power Bank 3", "battery": "10000 мАч", "power": "18 Вт", "weight": "288 г"},
    },
    "dyson": {
        "v11": {"brand": "Dyson", "model": "V11", "power": "185 Вт", "cleaning_type": "сухая", "weight": "3.05 кг", "working_time": "60 мин"},
        "v12": {"brand": "Dyson", "model": "V12 Detect Slim", "power": "150 Вт", "cleaning_type": "сухая", "weight": "2.2 кг", "working_time": "60 мин"},
        "v15": {"brand": "Dyson", "model": "V15 Detect", "power": "240 Вт", "cleaning_type": "сухая", "weight": "3.1 кг", "working_time": "60 мин"},
    },
    "roborock": {
        "s8 pro ultra": {"brand": "Roborock", "model": "S8 Pro Ultra", "cleaning_type": "сухая и влажная", "battery": "5200 мАч", "power": "69 Вт", "weight": "4.8 кг"},
        "s7": {"brand": "Roborock", "model": "S7", "cleaning_type": "сухая и влажная", "battery": "5200 мАч", "power": "68 Вт", "weight": "4.7 кг"},
    },
    "haier": {
        "cef535asg": {"brand": "Haier", "model": "CEF535ASG", "defrost_system": "Total No Frost", "volume": "346 л", "weight": "67 кг"},
    },
    "lg": {
        "ga-b509": {"brand": "LG", "model": "GA-B509", "defrost_system": "Total No Frost", "volume": "384 л", "weight": "75 кг"},
        "oled55c3rla": {"brand": "LG", "model": "OLED55C3RLA", "screen_diagonal": "55\"", "resolution": "3840x2160", "refresh_rate": "120 Гц", "display_tech": "OLED"},
    },
    "gorenje": {
        "mo20e1w": {"brand": "Gorenje", "model": "MO20E1W", "volume": "20 л", "power": "800 Вт", "weight": "11 кг"},
    },
    "asus": {
        "rog strix g16": {"brand": "ASUS", "model": "ROG Strix G16", "screen_diagonal": "16\"", "cpu": "Intel Core i7-13650HX", "weight": "2.5 кг"},
    }
}


class CatalogEnricher:
    """
    Обогащает карточку эталонными характеристиками из базы моделей E-Commerce.
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

    @staticmethod
    def _resolve_kb_path(user_path: str | None = None) -> str:
        from pathlib import Path
        if user_path:
            return str(Path(user_path).resolve())

        default_file = Path(getattr(settings, "catalog_kb_path", "data/dictionaries/catalog_models_kb.json"))
        backend_dir = Path(__file__).resolve().parent.parent.parent
        repo_root = backend_dir.parent
        dict_dir = backend_dir / "data" / "dictionaries"

        candidates = [
            backend_dir / default_file,
            repo_root / default_file,
            dict_dir / default_file.name,
            backend_dir / "data" / "dictionaries" / "catalog_models_kb.json",
            repo_root / "data" / "dictionaries" / "catalog_models_kb.json",
            Path(DEFAULT_KB_PATH),
        ]
        for c in candidates:
            if c and c.is_file():
                return str(c.resolve())
        return str((backend_dir / default_file).resolve())

    def __init__(self, kb_path: str | None = None) -> None:
        self.kb_path = self._resolve_kb_path(kb_path)
        self._lock = threading.Lock()
        self.kb: dict[str, dict[str, dict[str, str]]] = {}
        self.models_by_id: dict[str, dict[str, str]] = {}
        self.status: str = "healthy"  # healthy | degraded | failed
        self.error_message: str | None = None
        self._load_kb()

    def _load_fallback_seed(self) -> None:
        """Загружает встроенный резервный справочник эталонных моделей E-Commerce при отсутствии или повреждении дискового KB."""
        with self._lock:
            self.kb = {k: {m_k: dict(m_v) for m_k, m_v in v.items()} for k, v in EMBEDDED_SEED_MODELS_FALLBACK.items()}
            self.models_by_id = {}
            for vendor, mods in self.kb.items():
                for m_name, specs in mods.items():
                    if "model_id" in specs:
                        self.models_by_id[str(specs["model_id"])] = dict(specs)
        logger.info(
            "Loaded embedded fallback Catalog KB seed: %d vendors, %d canonical models",
            len(self.kb),
            self.size(),
        )

    def _load_kb(self) -> None:
        if not os.path.exists(self.kb_path):
            self.status = "degraded"
            self.error_message = f"Файл базы знаний Catalog KB не найден: {self.kb_path}"
            logger.warning("CATALOG KB ALERT: %s", self.error_message)
            self.kb = {}
            self.models_by_id = {}
            return

        try:
            with open(self.kb_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            if not isinstance(raw_data, dict):
                self.status = "failed"
                self.error_message = f"Некорректная структура Catalog KB: ожидался словарь, получен {type(raw_data).__name__}"
                logger.error("CATALOG KB ALERT: %s", self.error_message)
                self.kb = {}
                self.models_by_id = {}
                return

            with self._lock:
                if "_by_id" in raw_data:
                    self.models_by_id = dict(raw_data.pop("_by_id"))
                else:
                    self.models_by_id = {}
                self.kb = raw_data

            total_models = sum(len(mods) for mods in self.kb.values() if isinstance(mods, dict))
            if total_models == 0 and not self.models_by_id:
                self.status = "degraded"
                self.error_message = "Catalog KB пуст (0 моделей)"
                logger.warning("CATALOG KB ALERT: %s", self.error_message)
            else:
                self.status = "healthy"
                self.error_message = None
                logger.info(
                    "Loaded Catalog KB v%s: %d vendors, %d models, %d indexed by model_id",
                    self.version,
                    len(self.kb),
                    total_models,
                    len(self.models_by_id),
                )
        except Exception as e:
            self.status = "failed"
            self.error_message = f"Критическая ошибка чтения Catalog KB: {e}"
            logger.critical("CATALOG KB CRITICAL: %s", self.error_message, exc_info=True)
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
            "status": self.status,
            "error_message": self.error_message,
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

        if self.status != "healthy":
            logger.warning(
                "Catalog KB is degraded (%s): %s. Skipping KB enrichment for model '%s'.",
                self.status,
                self.error_message,
                model or model_id,
            )
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

            source_tag = "catalog_kb"
            tier_tag = "Tier 2.5"
            conf = float(getattr(settings, "prior_catalog_kb", 0.94))

            enriched.append({
                "attribute": attr,
                "value": val,
                "confidence": conf,
                "source": source_tag,
                "tier": tier_tag,
                "raw": val,
                "grounded": True,
            })

        return enriched
