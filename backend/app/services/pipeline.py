from __future__ import annotations

import logging
import re
from typing import Any

from app.extractors.base import Prediction
from app.extractors.gliner_extractor import GlinerExtractor
from app.extractors.llm_extractor import StrictLlmFallbackExtractor
from app.extractors.regex_extractor import RegexExtractor
from app.extractors.sanity import AttributeSanityValidator
from app.services.brand_registry import BrandRegistry
from app.services.catalog_enricher import CatalogEnricher

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# ТАКСОНОМИЯ И СХЕМЫ АТРИБУТОВ ПО КАТЕГОРИЯМ КАТАЛОГА М.ВИДЕО
# --------------------------------------------------------------------------
CATEGORY_SCHEMAS: dict[str, dict[str, Any]] = {
    "smartphones": {
        "name_ru": "Смартфоны",
        "keywords": [
            "смартфон", "телефон", "iphone", "айфон", "мобильный", "сотовый",
            "galaxy", "гэлакси", "гелакси", "redmi", "poco", "realme", "motorola", "моторола", "infinix", "инфиникс",
            "xperia", "pixel", "пиксель", "oneplus", "oppo", "vivo", "honor", "хонор",
            "huawei", "хуавей", "xiaomi", "сяоми", "samsung", "самсунг", "tecno", "текно",
        ],
        "required_attrs": {"brand", "model", "memory_rom", "screen_diagonal", "battery", "color"},
        "gliner_labels": ["бренд", "модель", "объём памяти", "оперативная память", "диагональ экрана", "цвет", "процессор", "ёмкость аккумулятора"],
    },
    "laptops": {
        "name_ru": "Ноутбуки",
        "keywords": ["ноутбук", "лэптоп", "ideapad", "thinkpad", "macbook", "ноут", "zenbook", "vivobook", "redmibook"],
        "required_attrs": {"brand", "model", "cpu", "memory_ram", "memory_rom", "screen_diagonal"},
        "gliner_labels": ["бренд", "модель", "процессор", "оперативная память", "объём памяти", "диагональ экрана", "видеокарта", "цвет"],
    },
    "tvs": {
        "name_ru": "Телевизоры",
        "keywords": ["телевизор", "smart tv", "led тв", "тв-панель", "телевизоры", "телевизора"],
        "required_attrs": {"brand", "model", "screen_diagonal", "resolution"},
        "gliner_labels": ["бренд", "модель", "диагональ экрана", "разрешение экрана", "технология экрана", "частота обновления экрана"],
    },
    "vacuum_cleaners": {
        "name_ru": "Пылесосы",
        "keywords": ["пылесос", "робот-пылесос", "vacuum", "клининг"],
        "required_attrs": {"brand", "model", "cleaning_type", "color"},
        "gliner_labels": ["бренд", "модель", "тип уборки", "время работы", "цвет", "объем пылесборника"],
    },
    "refrigerators": {
        "name_ru": "Холодильники",
        "keywords": ["холодильник", "морозильник", "морозильная", "no frost"],
        "required_attrs": {"brand", "model", "defrost_system", "color"},
        "gliner_labels": ["бренд", "модель", "система разморозки", "объем", "цвет"],
    },
    "headphones": {
        "name_ru": "Наушники",
        "keywords": ["наушники", "гарнитура", "airpods", "tws", "earbuds"],
        "required_attrs": {"brand", "model", "color"},
        "gliner_labels": ["бренд", "модель", "цвет", "время работы"],
    },
    "powerbanks": {
        "name_ru": "Внешние аккумуляторы (Power Bank)",
        "keywords": [
            "повербанк", "пауэрбанк", "power bank", "powerbank", "внешний аккумулятор",
            "портативный аккумулятор", "портативное зарядное", "аккумулятор портативный", "аккумулятор внешний"
        ],
        "required_attrs": {"brand", "model", "battery", "color"},
        "gliner_labels": ["бренд", "модель", "ёмкость аккумулятора", "мощность", "цвет"],
    },
    "default": {
        "name_ru": "Электроника и техника",
        "keywords": [],
        "required_attrs": {"brand", "model", "color"},
        "gliner_labels": ["бренд", "модель", "цвет"],
    },
}


class CascadedExtractionPipeline:
    """
    Каскадный оркестратор извлечения характеристик промышленного уровня:

    ЭТАП 1: Детекция категории товара (Category Classifier)
            Понимает, что перед нами — смартфон, пылесос, ТВ или холодильник,
            и активирует целевую таксономию атрибутов М.Видео.

    ЭТАП 2: Базовые правила и словари (Tier 1 Fast Rules)
            Сверхбыстро (< 1 мс) снимает бренды, цвета и шаблонные числа (RAM, ROM, экран, батарею).

    ЭТАП 3: Таргетированный Zero-Shot NER (Tier 2 GLiNER)
            Дособирает недостающие сущности (модель, процессор, тип уборки),
            фокусируясь строго на атрибутах определенной категории.

    ЭТАП 4: Валидация и калибровка уверенности (HITL)
            Проверяет полноту карточки, рассчитывает средневзвешенную уверенность
            и определяет статус публикации.
    """

    def __init__(
        self,
        use_gliner: bool = True,
        use_catalog_enricher: bool = True,
        use_llm: bool = True,
        confidence_threshold: float = 0.87,
        gliner_threshold: float = 0.30,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.use_gliner = use_gliner
        self.use_catalog_enricher = use_catalog_enricher
        self.use_llm = use_llm
        self.regex_extractor = RegexExtractor()
        self.gliner_extractor = GlinerExtractor(threshold=gliner_threshold) if use_gliner else None
        self.catalog_enricher = CatalogEnricher() if use_catalog_enricher else None
        self.llm_extractor = StrictLlmFallbackExtractor() if use_llm else None
        self.brand_registry = BrandRegistry.get_instance()

    def detect_category(self, card: dict[str, Any]) -> tuple[str, str]:
        """
        Определяет категорию товара по метаданным или тексту названия и описания.
        Возвращает (category_key, category_name_ru).
        """
        raw_cat = (card.get("category") or "").lower()
        title = (card.get("title") or "").lower()
        desc = (card.get("description") or "").lower()
        text_corpus = f"{raw_cat} {title} {desc}"

        # 1. Порядок проверки категорий: специфичные крупные приборы имеют высший приоритет,
        # чтобы бренд Xiaomi/Samsung не стягивал пылесосы или телевизоры в смартфоны.
        priority_order = [
            "vacuum_cleaners",
            "refrigerators",
            "tvs",
            "laptops",
            "headphones",
            "powerbanks",
            "smartphones",
        ]
        for cat_key in priority_order:
            schema = CATEGORY_SCHEMAS.get(cat_key)
            if not schema:
                continue
            for kw in schema["keywords"]:
                if re.search(rf"\b{re.escape(kw)}", text_corpus):
                    return cat_key, schema["name_ru"]

        # 2. Эвристика: экран <= 7.2" и аккумулятор mAh / мобильные паттерны -> Смартфоны
        has_mobile_screen = bool(re.search(r"\b(?:[56]\.\d{1,2}|7\.[012])\s*(?:\"|дюйм)", text_corpus))
        has_battery = bool(re.search(r"(?:\d{3,5}\s*(?:мач|mah|аккум)|(?:мач|mah|аккум)\s*\d{3,5})", text_corpus))
        if has_mobile_screen and has_battery:
            return "smartphones", CATEGORY_SCHEMAS["smartphones"]["name_ru"]

        if re.search(r"\b\d{1,2}/\d{2,4}\s*(?:гб|gb)?\b", text_corpus) and has_battery:
            return "smartphones", CATEGORY_SCHEMAS["smartphones"]["name_ru"]

        return "default", CATEGORY_SCHEMAS["default"]["name_ru"]

    def process_card(self, card: dict[str, Any]) -> dict[str, Any]:
        """
        Сквозной прогон карточки через 4-этапную воронку.
        """
        # Интеллектуальное авто-разделение сплошного текста (когда карточка введена единым куском)
        card = dict(card)
        raw_text = (card.get("raw_text") or "").strip()
        raw_title = (card.get("title") or "").strip()
        raw_desc = (card.get("description") or "").strip()

        if raw_text:
            # Для полноты контекста description ВСЕГДА содержит весь сырой текст целиком
            card["description"] = raw_text
            if not raw_title:
                lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
                if lines and len(lines[0]) < 120:
                    card["title"] = lines[0]
                else:
                    parts = re.split(r"(?<=[.!?])\s+", raw_text, maxsplit=1)
                    if len(parts) == 2 and len(parts[0]) < 120:
                        card["title"] = parts[0]
                    else:
                        card["title"] = raw_text
        elif raw_title and not raw_desc:
            card["description"] = raw_title
            lines = [line.strip() for line in raw_title.split("\n") if line.strip()]
            if lines and len(lines[0]) < 120:
                card["title"] = lines[0]
            else:
                card["title"] = raw_title

        # ------------------------------------------------------------------
        # ЭТАП 1: Определение категории товара
        # ------------------------------------------------------------------
        cat_key, cat_name = self.detect_category(card)
        schema = CATEGORY_SCHEMAS.get(cat_key, CATEGORY_SCHEMAS["default"])
        gliner_labels: list[str] = schema["gliner_labels"]
        required_attrs: set[str] = schema["required_attrs"]

        predictions_map: dict[str, Prediction] = {}

        # ------------------------------------------------------------------
        # ЭТАП 2: Tier 1 (Regex + FlashText)
        # ------------------------------------------------------------------
        t1_preds = self.regex_extractor.extract(card, category_key=cat_key)
        for p in t1_preds:
            # Строгая валидация физического здравого смысла и кросс-загрязнений
            if not AttributeSanityValidator.is_valid(p["attribute"], p["value"], cat_key):
                continue
            predictions_map[p["attribute"]] = p

        found_attrs = set(predictions_map.keys())
        missing_attrs = required_attrs - found_attrs

        # ------------------------------------------------------------------
        # ЭТАП 3: Tier 2 (GLiNER Zero-Shot NER) — таргетированно под категорию
        # ------------------------------------------------------------------
        if self.use_gliner and self.gliner_extractor and missing_attrs:
            # Запрашиваем у GLiNER только те сущности, которых нет в Tier 1:
            # Если атрибут не обязателен для категории (например процессор у смартфона),
            # запрашиваем его у GLiNER только при наличии ключевых маркеров в тексте
            raw_text_lower = f"{card.get('title', '')} {card.get('description', '')} {card.get('raw_text', '')}".lower()
            needed_labels = []
            for lbl in gliner_labels:
                attr = self.gliner_extractor.LABEL_TO_ATTR.get(lbl)
                if attr in predictions_map and predictions_map[attr]["confidence"] >= 0.88:
                    continue
                if attr not in required_attrs:
                    if attr == "cpu" and not re.search(r"\b(чип|chip|cpu|процессор|ядер\w*|ghz|ггц|snapdragon|exynos|dimensity|bionic|tensor|kirin|core|ryzen)\b", raw_text_lower):
                        continue
                needed_labels.append(lbl)

            if needed_labels:
                t2_preds = self.gliner_extractor.extract(card, target_labels=needed_labels, category_key=cat_key)
                for p in t2_preds:
                    attr = p["attribute"]
                    # Строгая валидация физического здравого смысла (отсечение перепутанных Гц в батарее и т.д.)
                    if not AttributeSanityValidator.is_valid(attr, p["value"], cat_key):
                        continue
                    existing = predictions_map.get(attr)
                    if existing is None:
                        predictions_map[attr] = p
                    elif existing.get("source") == "flashtext" and existing.get("confidence", 0) >= 0.80:
                        # Словарный бренд/цвет из FlashText — эталонный детерминированный источник
                        continue
                    elif existing.get("confidence", 0) < p["confidence"]:
                        predictions_map[attr] = p

        # Канонизация и валидация бренда через BrandRegistry (с защитой от опечаток и поддержкой кандидатов)
        if "brand" in predictions_map:
            raw_b = predictions_map["brand"]["value"]
            canon_b, conf, is_fuzzy_or_cand = self.brand_registry.match_or_fuzzy_brand(raw_b)
            if canon_b:
                predictions_map["brand"]["value"] = canon_b
                if is_fuzzy_or_cand:
                    predictions_map["brand"]["confidence"] = min(predictions_map["brand"]["confidence"], conf)

        # Коррекция линеек для смартфонов: Galaxy / Гэлакси -> бренд Samsung
        if cat_key == "smartphones" and "brand" in predictions_map:
            if predictions_map["brand"]["value"].lower() in {"galaxy", "гэлакси"}:
                predictions_map["brand"]["value"] = "Samsung"
                predictions_map["brand"]["confidence"] = 0.95

        # Если бренд не найден, но в модели указана известная линейка (Galaxy, iPhone, Redmi):
        if "brand" not in predictions_map and "model" in predictions_map:
            m_low = predictions_map["model"]["value"].lower()
            if "galaxy" in m_low or "гэлакси" in m_low or re.match(r"^[szanmfe]\d{1,2}\b", m_low):
                predictions_map["brand"] = Prediction(attribute="brand", value="Samsung", confidence=0.95, source="rule_subbrand", raw=m_low)
            elif "iphone" in m_low:
                predictions_map["brand"] = Prediction(attribute="brand", value="Apple", confidence=0.98, source="rule_subbrand", raw=m_low)
            elif "redmi" in m_low or "poco" in m_low:
                predictions_map["brand"] = Prediction(attribute="brand", value="Xiaomi", confidence=0.95, source="rule_subbrand", raw=m_low)

        # Очистка названия бренда из начала названия модели ("Sony KD50X85TJ" -> "KD50X85TJ")
        if "brand" in predictions_map and "model" in predictions_map:
            b_val = predictions_map["brand"]["value"]
            m_val = predictions_map["model"]["value"]
            if m_val.lower().strip() == b_val.lower().strip():
                del predictions_map["model"]
            else:
                clean_m = re.sub(rf"^{re.escape(b_val)}\s+", "", m_val, flags=re.IGNORECASE).strip()
                if clean_m and len(clean_m) >= 2 and clean_m.lower() != b_val.lower():
                    predictions_map["model"]["value"] = clean_m

        # Защита от перепутывания сущностей: процессор не может дублировать бренд или модель устройства
        if "cpu" in predictions_map:
            cpu_val = predictions_map["cpu"]["value"].lower().strip()
            b_val = predictions_map.get("brand", {}).get("value", "").lower().strip()
            m_val = predictions_map.get("model", {}).get("value", "").lower().strip()
            if (b_val and b_val == cpu_val) or (m_val and m_val == cpu_val) or (b_val and m_val and f"{b_val} {m_val}" == cpu_val):
                del predictions_map["cpu"]


        # ------------------------------------------------------------------
        # ЭТАП 3.5: Каталожное обогащение (Catalog Model Specs Enrichment)
        # Если после Tier 1 и Tier 2 остались пропущенные обязательные атрибуты,
        # но бренд и модель надежно определены, подтягиваем эталонные спецификации из базы М.Видео.
        # ------------------------------------------------------------------
        current_missing = required_attrs - set(predictions_map.keys())
        if self.use_catalog_enricher and self.catalog_enricher and current_missing and "brand" in predictions_map and "model" in predictions_map:
            b_val = predictions_map["brand"]["value"]
            m_val = predictions_map["model"]["value"]
            enriched_preds = self.catalog_enricher.enrich(
                brand=b_val,
                model=m_val,
                missing_attrs=current_missing,
                category_key=cat_key,
            )
            for p in enriched_preds:
                attr = p["attribute"]
                if attr not in predictions_map:
                    predictions_map[attr] = p

        # ------------------------------------------------------------------
        # ЭТАП 3.8: Tier 3 Строгий LLM-фоллбэк (Strict LLM Fallback)
        # Если после базы М.Видео все еще есть пропущенные обязательные атрибуты,
        # делаем точечный запрос в LLM со строгой валидацией по ID модели
        # ------------------------------------------------------------------
        # Атрибуты, которые принципиально нельзя додумывать по названию модели (вариативные свойства конкретного оффера)
        NON_ENRICHABLE_FROM_MODEL = {"color"}
        still_missing = (required_attrs - set(predictions_map.keys())) - NON_ENRICHABLE_FROM_MODEL
        if (
            self.use_llm
            and self.llm_extractor
            and self.llm_extractor.is_enabled
            and still_missing
            and "brand" in predictions_map
            and "model" in predictions_map
        ):
            b_val = predictions_map["brand"]["value"]
            m_val = predictions_map["model"]["value"]
            llm_preds = self.llm_extractor.enrich_missing_attributes(
                brand=b_val,
                model=m_val,
                missing_attrs=still_missing,
                category_key=cat_key,
                raw_text=raw_text or card.get("description", ""),
            )
            for p in llm_preds:
                attr = p["attribute"]
                if attr not in predictions_map:
                    predictions_map[attr] = p

        # Автоматическая динамическая регистрация нового бренда в BrandRegistry
        if "brand" in predictions_map and self.brand_registry:
            b_val = predictions_map["brand"]["value"]
            if not self.brand_registry.has_brand(b_val):
                if predictions_map["brand"].get("confidence", 0) >= 0.88:
                    self.brand_registry.register_brand(b_val)

        # ------------------------------------------------------------------
        # ЭТАП 4: Валидация полноты и расчет уверенности
        # ------------------------------------------------------------------
        all_preds = list(predictions_map.values())
        final_found = set(predictions_map.keys())
        final_missing = sorted(list(required_attrs - final_found))

        if all_preds:
            avg_conf = sum(p["confidence"] for p in all_preds) / len(all_preds)
        else:
            avg_conf = 0.0

        # Карточка требует проверки человеком (Human-in-the-Loop), если:
        # 1. Средняя уверенность ниже порога (0.75)
        # 2. Не удалось извлечь хотя бы одно обязательное поле категории (final_missing)
        # 3. Хотя бы один обязательный атрибут имеет уверенность ниже 0.75 (критично для фильтров)
        # 4. Карточка пустая
        low_conf_required = any(
            p["confidence"] < self.confidence_threshold
            for p in all_preds
            if p["attribute"] in required_attrs
        )
        needs_review = (
            (avg_conf < self.confidence_threshold)
            or bool(final_missing)
            or low_conf_required
            or (len(all_preds) == 0)
        )

        return {
            "external_id": card.get("external_id") or card.get("id"),
            "category": cat_name,
            "category_key": cat_key,
            "predictions": all_preds,
            "missing": final_missing,
            "overall_confidence": round(avg_conf, 4),
            "needs_review": needs_review,
        }
