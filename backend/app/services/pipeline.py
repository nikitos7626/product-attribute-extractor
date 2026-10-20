from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.extractors.base import Prediction
from app.extractors.gliner_extractor import GlinerExtractor
from app.extractors.llm_extractor import StrictLlmFallbackExtractor
from app.extractors.regex_extractor import RegexExtractor
from app.extractors.sanity import AttributeSanityValidator
from app.services.brand_registry import BrandRegistry
from app.services.catalog_enricher import CatalogEnricher
from app.services.confidence_calibrator import ConfidenceCalibrator

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# ПОЛНАЯ ТАКСОНОМИЯ КАТАЛОГА М.ВИДЕО (6 570+ КАТЕГОРИЙ ИЗ skus.pkl)
# --------------------------------------------------------------------------
class TaxonomyManager:
    """
    Менеджер таксономии каталога М.Видео с безопасной обработкой сбоев загрузки
    и явным отслеживанием статуса деградации сервиса (Safe Fallback & Degradation Monitoring).
    """

    _instance: TaxonomyManager | None = None

    def __init__(self, file_path: Path | None = None) -> None:
        if file_path is not None:
            self.path = Path(file_path)
        else:
            default_file = Path(getattr(settings, "taxonomy_path", "data/dictionaries/mvideo_categories.json"))
            if default_file.is_absolute():
                self.path = default_file
            else:
                backend_dir = Path(__file__).resolve().parent.parent.parent
                repo_root = backend_dir.parent
                dict_dir = backend_dir / "data" / "dictionaries"
                if (backend_dir / default_file).is_file():
                    self.path = backend_dir / default_file
                elif (repo_root / default_file).is_file():
                    self.path = repo_root / default_file
                elif (dict_dir / default_file.name).is_file():
                    self.path = dict_dir / default_file.name
                else:
                    self.path = backend_dir / default_file
        self.id_to_name: dict[str, str] = {}
        self.normalized_names: dict[str, str] = {}
        self.status: str = "healthy"  # healthy | degraded | failed
        self.error_message: str | None = None
        self.categories_count: int = 0
        self.load()

    @classmethod
    def get_instance(cls) -> TaxonomyManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self) -> None:
        """Загружает внешнюю таксономию М.Видео с явным протоколированием статуса."""
        try:
            if not self.path.is_file():
                self.status = "degraded"
                self.error_message = f"Файл таксономии не найден по пути: {self.path}"
                logger.warning("TAXONOMY ALERT: %s. Активирован безопасный резервный контур категорий.", self.error_message)
                return

            with open(self.path, "r", encoding="utf-8") as f:
                tax_data = json.load(f)

            if not isinstance(tax_data, dict):
                self.status = "failed"
                self.error_message = f"Некорректная структура JSON таксономии (ожидался словарь, получен {type(tax_data).__name__})"
                logger.error("TAXONOMY ALERT: %s. Активирован безопасный резервный контур категорий.", self.error_message)
                return

            self.id_to_name = tax_data.get("id_to_name", {})
            for name in tax_data.get("all_names", []):
                clean_name = str(name).strip()
                if clean_name:
                    self.normalized_names[clean_name.lower()] = clean_name

            self.categories_count = len(self.normalized_names)
            if self.categories_count == 0:
                self.status = "degraded"
                self.error_message = "Файл таксономии пуст (0 категорий)"
                logger.warning("TAXONOMY WARNING: %s", self.error_message)
            else:
                self.status = "healthy"
                self.error_message = None
                logger.info("Taxonomy loaded successfully: %d categories from %s", self.categories_count, self.path)

        except Exception as e:
            self.status = "failed"
            self.error_message = f"Ошибка чтения таксономии: {e}"
            logger.critical("TAXONOMY CRITICAL ERROR: %s. Активирован безопасный резервный контур категорий.", self.error_message, exc_info=True)


taxonomy_manager = TaxonomyManager.get_instance()
MVIDEO_TAXONOMY_ID_TO_NAME: dict[str, str] = taxonomy_manager.id_to_name
MVIDEO_TAXONOMY_NORMALIZED: dict[str, str] = taxonomy_manager.normalized_names


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
        "gliner_labels": ["бренд", "модель", "система разморозки", "объем", "цвет", "габариты"],
    },

    "headphones": {
        "name_ru": "Наушники",
        "keywords": [
            "наушники", "наушник", "гарнитура", "гарнитуры", "airpods", "tws",
            "earbuds", "buds", "freebuds", "airdots", "earphones", "headphones",
            "headset", "вкладыши", "внутриканальные"
        ],
        "required_attrs": {"brand", "model", "color"},
        "gliner_labels": ["бренд", "модель", "цвет", "время работы"],
    },
    "powerbanks": {
        "name_ru": "Внешние аккумуляторы (Power Bank)",
        "keywords": [
            "внешние аккумуляторы", "аккумуляторы", "портативные аккумуляторы",
            "power bank", "powerbank", "портативное зарядное",
            "повербанк", "пауэрбанк", "внешний аккумулятор",
            "портативный аккумулятор", "аккумулятор портативный", "аккумулятор внешний",
        ],
        "required_attrs": {"brand", "model", "battery", "color"},
        "gliner_labels": ["бренд", "модель", "ёмкость аккумулятора", "мощность", "цвет"],
    },
    "microwaves": {
        "name_ru": "Микроволновые печи",
        "keywords": ["микроволнов", "свч", "микроволновка"],
        "required_attrs": {"brand", "model", "volume", "power", "color"},
        "gliner_labels": ["бренд", "модель", "объем", "мощность", "цвет"],
    },
    "tablets": {
        "name_ru": "Планшеты",
        "keywords": ["планшет", "ipad", "айпад", "таблет", "matepad", "galaxy tab", "xiaomi pad", "redmi pad"],
        "required_attrs": {"brand", "model", "screen_diagonal", "memory_rom", "battery", "color"},
        "gliner_labels": ["бренд", "модель", "объём памяти", "оперативная память", "диагональ экрана", "цвет", "процессор", "ёмкость аккумулятора"],
    },
    "desktops": {
        "name_ru": "Системные блоки и компьютеры",
        "keywords": ["системный блок", "компьютер", "пк", "моноблок", "неттоп", "desktop", "mac mini", "imac", "mac studio", "mac pro"],
        "required_attrs": {"brand", "model", "cpu", "memory_ram", "memory_rom"},
        "gliner_labels": ["бренд", "модель", "процессор", "оперативная память", "объём памяти", "видеокарта", "цвет"],
    },
    "monitors": {
        "name_ru": "Мониторы",
        "keywords": ["монитор", "игровой монитор"],
        "required_attrs": {"brand", "model", "screen_diagonal", "resolution"},
        "gliner_labels": ["бренд", "модель", "диагональ экрана", "разрешение экрана", "частота обновления экрана", "технология экрана"],
    },
    "washing_machines": {
        "name_ru": "Стиральные машины",
        "keywords": ["стиральная машина", "стиралка", "стирально-сушильная"],
        "required_attrs": {"brand", "model", "load_capacity", "color"},
        "gliner_labels": ["бренд", "модель", "загрузка", "скорость отжима", "цвет"],
    },
    "smart_watches": {
        "name_ru": "Смарт-часы",
        "keywords": ["смарт-часы", "умные часы", "apple watch", "galaxy watch", "смарт часы"],
        "required_attrs": {"brand", "model", "color"},
        "gliner_labels": ["бренд", "модель", "цвет", "диагональ экрана", "время работы"],
    },
    "kettles": {
        "name_ru": "Электрические чайники",
        "keywords": ["электрочайник", "чайник электрический", "чайник"],
        "required_attrs": {"brand", "model", "volume", "power", "color"},
        "gliner_labels": ["бренд", "модель", "объем", "мощность", "цвет"],
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
        self.llm_extractor = (
            StrictLlmFallbackExtractor(enforce_grounding=getattr(settings, "enforce_llm_grounding", False))
            if use_llm
            else None
        )
        self.brand_registry = BrandRegistry.get_instance()
        self.calibrator = ConfidenceCalibrator.get_instance()
        self.taxonomy_manager = TaxonomyManager.get_instance()

    def detect_category(self, card: dict[str, Any]) -> tuple[str, str]:
        """
        Определяет категорию товара по метаданным или тексту названия и описания.
        Возвращает (category_key, category_name_ru).

        Архитектура многоуровневой детекции:
        1. Эксплицитная категория в метаданных (raw_cat).
        2. Название товара (Title) — определяющий субъект сущности (с маскированием предлогов
           совместимости 'для смартфона', 'к телефону' и аксессуаров 'чехол для...').
        3. Описание (Description) — с обязательным подавлением комплектных аксессуаров
           ('в комплекте наушники') и аудиоразъемов ('разъем для наушников 3.5 мм').
        4. Аппаратные фингерпринты (экран 5-7.2" + батарея mAh / мобильная ОС / камера -> Смартфоны).
        """
        raw_cat = (card.get("category") or "").strip().lower()
        title = (card.get("title") or "").strip().lower()
        desc = (card.get("description") or "").strip().lower()
        raw_text = (card.get("raw_text") or "").strip().lower()

        if not title and raw_text:
            lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
            if lines:
                title = lines[0].lower()

        # Подавляем секцию комплектации и подарков в названии (если сплошной текст подан в title)
        clean_title = re.sub(
            r"(?:в\s+подарок|подарок|в\s+комплекте|комплектаци\w*|комплект\s+поставки|поставляется\s+с|идут\s+в\s+комплекте)[^.!\n;]+",
            " ",
            title,
            flags=re.IGNORECASE,
        ).strip()

        # ------------------------------------------------------------------
        # Маркеры аксессуаров и сантехники (Защита от утечек)
        # ------------------------------------------------------------------
        has_sanitary_markers = bool(
            re.search(r"\b(?:душ\w*|ванн\w*|смесител\w*)", f"{raw_cat} {title}", flags=re.IGNORECASE)
        )

        ACCESSORY_PATTERN = (
            r"\b(?:"
            r"чех(?:ол|лы|ла|лов|лом|лах|лами|ле)|чехол\w*|"
            r"стекл(?:о|а|ом|е|ах|ами)|стекол|"
            r"пл[её]нк(?:а|и|у|ой|е|ах|ами)|"
            r"кронштейн\w*|"
            r"фильтр\w*|"
            r"насадк\w*|"
            r"кабел\w*|"
            r"адаптер\w*|"
            r"ремеш(?:ок|ка|ки|ком|ках|ками|ке)|ремешок\w*|"
            r"душ\w*|"
            r"сантехник\w*|"
            r"смесител\w*"
            r")\b"
        )

        is_accessory_raw_cat = bool(
            re.search(rf"(?:{ACCESSORY_PATTERN}|\bаксессуар\w*)\b", raw_cat, flags=re.IGNORECASE)
        )

        is_accessory_title = bool(
            re.search(ACCESSORY_PATTERN, clean_title, flags=re.IGNORECASE)
        )

        is_accessory_or_sanitary = is_accessory_raw_cat or is_accessory_title or has_sanitary_markers

        blocked_categories = {"smartphones", "tablets", "tvs", "monitors", "headphones", "laptops", "vacuum_cleaners"} if is_accessory_or_sanitary else set()

        ordered_tech_keys = [
            "tablets",
            "smart_watches",
            "vacuum_cleaners",
            "washing_machines",
            "refrigerators",
            "microwaves",
            "kettles",
            "monitors",
            "desktops",
            "laptops",
            "tvs",
            "smartphones",
            "headphones",
            "powerbanks",
        ]

        # 0. Извлечение raw_cat из category_id, если передан id из каталога
        cat_id = str(card.get("category_id") or card.get("categoryId") or (card.get("categories", {}) if isinstance(card.get("categories"), dict) else {}).get("categoryId") or "").strip()
        if cat_id and cat_id in self.taxonomy_manager.id_to_name:
            raw_cat = self.taxonomy_manager.id_to_name[cat_id].lower()

        # ------------------------------------------------------------------
        # 1. Эксплицитная категория из метаданных (raw_cat)
        # ------------------------------------------------------------------
        if raw_cat:
            if "внешние аккумуляторы" in raw_cat or "портативные аккумуляторы" in raw_cat:
                return "powerbanks", CATEGORY_SCHEMAS["powerbanks"]["name_ru"]

            for cat_key in ordered_tech_keys:
                if cat_key in blocked_categories:
                    continue
                schema = CATEGORY_SCHEMAS.get(cat_key)
                if not schema:
                    continue
                name_ru_clean = schema["name_ru"].lower().split("(")[0].strip()
                if (
                    schema["name_ru"].lower() in raw_cat
                    or name_ru_clean in raw_cat
                    or raw_cat in schema["name_ru"].lower()
                    or cat_key in raw_cat
                ):
                    return cat_key, schema["name_ru"]
                schema_keywords = schema["keywords"]
                if cat_key == "headphones" and has_sanitary_markers:
                    schema_keywords = [kw for kw in schema_keywords if not kw.startswith("гарнитур")]
                for kw in schema_keywords:
                    if re.search(rf"\b{re.escape(kw)}", raw_cat):
                        return cat_key, schema["name_ru"]

            # Если категория есть в полном каталоге М.Видео (напр. «Матрасы», «Смесители», «Шины»):
            if raw_cat in self.taxonomy_manager.normalized_names:
                return "default", self.taxonomy_manager.normalized_names[raw_cat]

        # ------------------------------------------------------------------
        # 2. Детекция по названию товара (Title) — принцип Head Noun
        # ------------------------------------------------------------------
        if clean_title:
            earliest_matches: list[tuple[int, str, str]] = []
            for cat_key in ordered_tech_keys:
                if cat_key in blocked_categories:
                    continue
                schema = CATEGORY_SCHEMAS.get(cat_key)
                if not schema:
                    continue
                schema_keywords = schema["keywords"]
                if cat_key == "headphones" and has_sanitary_markers:
                    schema_keywords = [kw for kw in schema_keywords if not kw.startswith("гарнитур")]
                for kw in schema_keywords:
                    for m in re.finditer(rf"\b{re.escape(kw)}", clean_title, flags=re.IGNORECASE):
                        prefix = clean_title[max(0, m.start() - 15):m.start()].lower()
                        is_compat = bool(re.search(r"\b(?:для|к|под|со)\s*$", prefix))
                        pos = m.start() if not is_compat else m.start() + 10000
                        earliest_matches.append((pos, cat_key, schema["name_ru"]))

            if earliest_matches:
                earliest_matches.sort(key=lambda x: x[0])
                if earliest_matches[0][0] < 5000:
                    return earliest_matches[0][1], earliest_matches[0][2]

        # ------------------------------------------------------------------
        # 3. Детекция по тексту описания (Description) с подавлением ложных
        #    срабатываний от комплектных аксессуаров, аудиопортов и софта
        # ------------------------------------------------------------------
        corpus = f"{title} {desc} {raw_text}".lower()
        clean_corpus = corpus

        # Подавляем секцию комплектации: "в комплекте наушники", "комплектация: блок питания, наушники"
        clean_corpus = re.sub(
            r"(?:в\s+комплекте|комплектаци\w*|комплект\s+поставки|поставляется\s+с|идут\s+в\s+комплекте)[^.!\n;]+",
            " ",
            clean_corpus,
            flags=re.IGNORECASE,
        )
        # Подавляем аудиоразъемы: "разъем для наушников 3.5 мм"
        clean_corpus = re.sub(
            r"(?:разъем|разъём|выход|порт|гнездо|вход|аудиовыход|mini-jack|jack\s*3\.5|3\.5\s*мм)\s+(?:для\s+)?(?:наушник\w*|гарнитур\w*|микрофон\w*)",
            " ",
            clean_corpus,
            flags=re.IGNORECASE,
        )
        # Подавляем удаленное управление: "управление со смартфона"
        clean_corpus = re.sub(
            r"(?:управление|подключение|приложение|синхронизация)\s+(?:с|со|для|через)\s+(?:смартфон\w*|телефон\w*|планшет\w*)",
            " ",
            clean_corpus,
            flags=re.IGNORECASE,
        )
        # Подавляем предлоги совместимости: "для смартфона", "к наушникам"
        clean_corpus = re.sub(
            r"\b(?:для|к|под)\s+(?:смартфон\w*|телефон\w*|айфон\w*|iphone\w*|ноутбук\w*|наушник\w*|телевизор\w*)",
            " ",
            clean_corpus,
            flags=re.IGNORECASE,
        )

        for cat_key in [
            "vacuum_cleaners",
            "refrigerators",
            "microwaves",
            "tvs",
            "laptops",
            "smartphones",
            "headphones",
            "powerbanks",
        ]:
            if cat_key in blocked_categories:
                continue
            schema = CATEGORY_SCHEMAS.get(cat_key)
            if not schema:
                continue
            schema_keywords = schema["keywords"]
            if cat_key == "headphones" and has_sanitary_markers:
                schema_keywords = [kw for kw in schema_keywords if not kw.startswith("гарнитур")]
            for kw in schema_keywords:
                if re.search(rf"\b{re.escape(kw)}", clean_corpus):
                    return cat_key, schema["name_ru"]

        # ------------------------------------------------------------------
        # 4. Аппаратные эвристики и физические маркеры (Hardware Fingerprints)
        # ------------------------------------------------------------------
        if not is_accessory_or_sanitary:
            full_text = f"{title} {desc} {raw_text}".lower()

            # Эвристика смартфона:
            # Экран 5.0-7.2" + аккумулятор mAh / камера МП / мобильные сети / ОС
            has_mobile_screen = bool(re.search(r"\b(?:[56]\.\d{1,2}|7\.[012])\s*(?:\"|дюйм)", full_text))
            has_battery = bool(re.search(r"(?:\d{3,5}\s*(?:мА[·⋅•*.\-\s]?ч|mah|мач|аккум)|(?:мач|mah|аккум)\s*\d{3,5})", full_text, flags=re.IGNORECASE))
            has_mobile_os_net = bool(re.search(r"\b(?:ios|android|hyperos|miui|one\s*ui|5g|4g\s+lte|lte|sim|esim|сим-карт)\b", full_text, flags=re.IGNORECASE))
            has_slash_mem = bool(re.search(r"\b\d{1,2}/\d{2,4}\s*(?:гб|gb)?\b", full_text))
            has_phone_cam = bool(re.search(r"\b(?:камер\w*.*?\d{1,3}\s*мп|\d{1,3}\s*мп)\b", full_text))

            if has_mobile_screen and (has_battery or has_mobile_os_net or has_phone_cam):
                return "smartphones", CATEGORY_SCHEMAS["smartphones"]["name_ru"]

            if has_slash_mem and has_battery:
                return "smartphones", CATEGORY_SCHEMAS["smartphones"]["name_ru"]

            # Эвристика ноутбука: экран 13-17" + CPU/RAM
            has_laptop_screen = bool(re.search(r"\b(?:1[3-7]\.\d|1[3-7])\s*(?:\"|дюйм)", full_text))
            has_pc_cpu = bool(re.search(r"\b(?:intel|ryzen|core\s*i[3579]|apple\s*m[1234])\b", full_text))
            if has_laptop_screen and has_pc_cpu:
                return "laptops", CATEGORY_SCHEMAS["laptops"]["name_ru"]

            # Эвристика ТВ: экран >= 24" + Smart TV / 4K / тюнер
            has_tv_screen = bool(re.search(r"\b(?:[2-9]\d|1[0-1]\d)\s*(?:\"|дюйм)", full_text))
            has_tv_feature = bool(re.search(r"\b(?:smart\s*tv|смарт\s*тв|dvb-[tcs]|тв-тюнер)\b", full_text))
            if has_tv_screen and has_tv_feature:
                return "tvs", CATEGORY_SCHEMAS["tvs"]["name_ru"]

        # 5. Проверка по полной таксономии каталога М.Видео (если не попало в специализированные тех-категории):
        if raw_cat and raw_cat in MVIDEO_TAXONOMY_NORMALIZED:
            return "default", MVIDEO_TAXONOMY_NORMALIZED[raw_cat]

        return "default", CATEGORY_SCHEMAS["default"]["name_ru"]

    @staticmethod
    def _parse_title_structure(title: str, category_name: str) -> tuple[str | None, str | None]:
        """
        Синтаксический эвристический разбор заголовка e-commerce по шаблону:
        [Категория] [Бренд] [Модель] [Характеристики / Цвет]
        """
        if not title or len(title.strip()) < 3:
            return None, None

        clean_t = title.strip()
        # Срезаем префиксы вроде "Восстановленный", "Уцененный", "Новый", "Смарт-", "Беспроводной"
        clean_t = re.sub(
            r"^(?:восстановленн\w*|уцененн\w*|нов\w*|смарт[\s\-]|беспроводн\w*|портативн\w*|робот[\s\-])\s+",
            "",
            clean_t,
            flags=re.IGNORECASE,
        ).strip()

        # Срезаем название категории в начале заголовка (например "Смартфон", "Ноутбук", "Аэрогриль", "Кофеварка", "Пылесос")
        cat_words = [w for w in re.split(r"[^\w]+", category_name.lower()) if len(w) >= 3]
        for cw in cat_words:
            stem = re.sub(r"[иыаяеьъ]+$", "", cw)
            if len(stem) >= 3:
                clean_t = re.sub(rf"^{re.escape(stem)}\w*\s+", "", clean_t, flags=re.IGNORECASE).strip()
            else:
                clean_t = re.sub(rf"^{re.escape(cw)}\w*\s+", "", clean_t, flags=re.IGNORECASE).strip()

        tokens = clean_t.split()
        if not tokens:
            return None, None

        # Если первый токен все еще общее русское название техники/подтипа, а следующий — бренд
        if len(tokens) >= 2 and re.search(r"^[а-яёА-ЯЁ]+$", tokens[0]):
            if re.search(r"(?:гриль|варк|мойк|печ|сос|маш|фон|бук|визор|чайник|утюг|фен|блендер|миксер|плит|рожков|капельн)", tokens[0], re.IGNORECASE):
                if re.search(r"^[a-zA-Z]", tokens[1]) or tokens[1].isupper():
                    tokens = tokens[1:]

        first_token = tokens[0]
        # Проверяем, что первый токен не является числом или технической спецификацией
        if re.search(r"^\d", first_token) or re.search(r"^(?:4k|oled|qled|ips|wi-?fi|bluetooth)$", first_token, re.IGNORECASE):
            return None, None

        candidate_brand = first_token.strip(" ,.-()")
        if len(candidate_brand) < 2:
            return None, None

        # Токены после бренда до первого атрибута (память, ватты, цвет, дюймы, запятая)
        model_tokens = []
        for tok in tokens[1:]:
            tok_low = tok.lower().strip(" ,.-()")
            # Стоп-токены: начало спецификаций, цвета или описательных свойств
            if (
                re.search(r"^\d+(?:[.,]\d+)?\s*(?:гб|gb|тб|tb|м[аa]ч|mah|вт|w|л|l|кг|kg|гц|hz|\"|дюйм)", tok_low)
                or re.search(r"^\d{1,2}/\d{2,4}", tok_low)
                or re.search(r"^[а-яёА-ЯЁ]+(?:ая|яя|ый|ий|ое|ее|ые|ие)$", tok)
                or tok_low in (
                    "черный", "чёрный", "белый", "серый", "синий", "красный",
                    "серебристый", "золотой", "зеленый", "зелёный", "розовый", "фиолетовый",
                    "black", "white", "gray", "silver", "blue", "red", "gold", "green"
                )
                or tok_low in ("с", "со", "для", "на", "в", "и", "без")
            ):
                break
            model_tokens.append(tok)
            if len(model_tokens) >= 4:
                break

        candidate_model = " ".join(model_tokens).strip(" ,.-()") if model_tokens else None
        return candidate_brand, candidate_model

    def process_card(self, card: dict[str, Any]) -> dict[str, Any]:
        """
        Сквозной прогон карточки через 4-этапную воронку.
        """
        # Интеллектуальное авто-разделение сплошного текста (когда карточка введена единым куском)
        card = dict(card)
        warnings_list: list[str] = []
        degraded_tiers: list[str] = []

        if self.use_gliner and (not self.gliner_extractor or not self.gliner_extractor.health()):
            degraded_tiers.append("tier2_gliner")
            warnings_list.append("GLiNER extractor is offline; falling back to Tier 1.")

        if self.use_catalog_enricher and (not self.catalog_enricher or self.catalog_enricher.size() == 0):
            degraded_tiers.append("tier3_catalog_kb")
            warnings_list.append("Catalog KB is empty or missing; catalog enrichment skipped.")

        if self.use_llm and self.llm_extractor and self.llm_extractor.is_circuit_open():
            degraded_tiers.append("tier3_llm")
            warnings_list.append("LLM Circuit Breaker is active; LLM enrichment skipped.")

        if self.taxonomy_manager.status != "healthy":
            degraded_tiers.append("taxonomy")
            warnings_list.append(
                f"Внешняя таксономия работает в деградированном режиме ({self.taxonomy_manager.status}): "
                f"{self.taxonomy_manager.error_message or 'каталог категорий недоступен'}. Активирован безопасный фоллбэк."
            )

        raw_text = (card.get("raw_text") or "").strip()
        raw_title = (card.get("title") or "").strip()
        raw_desc = (card.get("description") or "").strip()

        if raw_text:
            # Для полноты контекста description ВСЕГДА содержит весь сырой текст целиком
            card["description"] = raw_text
            if not raw_title:
                lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
                if lines and len(lines) > 1:
                    card["title"] = lines[0]
                else:
                    parts = re.split(r"(?<!\d)(?<=[.!?])(?:\)|\"|')?\s+(?=[А-ЯA-Z])", raw_text, maxsplit=1)
                    card["title"] = parts[0] if parts else raw_text
        elif raw_title and not raw_desc:
            card["description"] = raw_title
            lines = [line.strip() for line in raw_title.split("\n") if line.strip()]
            if lines and len(lines) > 1:
                card["title"] = lines[0]
            else:
                parts = re.split(r"(?<!\d)(?<=[.!?])(?:\)|\"|')?\s+(?=[А-ЯA-Z])", raw_title, maxsplit=1)
                card["title"] = parts[0] if parts else raw_title

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

        # ------------------------------------------------------------------
        # ЭТАП 2.9: Извлечение бренда и модели для новых/незнакомых товаров
        # (Heuristic Structural Title Parser + LLM New Product Extractor)
        # ------------------------------------------------------------------
        if "brand" not in predictions_map or "model" not in predictions_map:
            title_str = card.get("title") or ""
            heur_brand, heur_model = self._parse_title_structure(title_str, cat_name)
            if heur_brand and "brand" not in predictions_map:
                canon_b, conf, _ = self.brand_registry.match_or_fuzzy_brand(heur_brand)
                predictions_map["brand"] = Prediction(
                    attribute="brand",
                    value=canon_b or heur_brand,
                    confidence=0.88,
                    source="syntax_heuristic",
                    raw=heur_brand,
                )
            if heur_model and "model" not in predictions_map:
                predictions_map["model"] = Prediction(
                    attribute="model",
                    value=heur_model,
                    confidence=0.85,
                    source="syntax_heuristic",
                    raw=heur_model,
                )

            # Если всё ещё нет бренда или модели — вызываем LLM/Reasoning экстрактор нового товара
            if (
                ("brand" not in predictions_map or "model" not in predictions_map)
                and self.use_llm
                and self.llm_extractor
                and self.llm_extractor.is_enabled
            ):
                llm_b, llm_m = self.llm_extractor.extract_brand_and_model_for_new_product(
                    title=title_str,
                    category_name=cat_name,
                    raw_text=raw_text or card.get("description", ""),
                )
                if llm_b and "brand" not in predictions_map:
                    canon_b, conf, _ = self.brand_registry.match_or_fuzzy_brand(llm_b)
                    predictions_map["brand"] = Prediction(
                        attribute="brand",
                        value=canon_b or llm_b,
                        confidence=0.92,
                        source="llm_new_product",
                        raw=llm_b,
                    )
                if llm_m and "model" not in predictions_map:
                    predictions_map["model"] = Prediction(
                        attribute="model",
                        value=llm_m,
                        confidence=0.90,
                        source="llm_new_product",
                        raw=llm_m,
                    )

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

        # Проверка согласованности бренда и модели (защита от конфликта брендов-конкурентов)
        if "brand" in predictions_map and "model" in predictions_map:
            b_val = predictions_map["brand"]["value"]
            m_val = predictions_map["model"]["value"]
            if not AttributeSanityValidator.is_brand_model_compatible(b_val, m_val):
                logger.warning("Incompatible brand '%s' and model '%s'; discarding model.", b_val, m_val)
                del predictions_map["model"]

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
        # ЭТАП 4: Валидация полноты и расчет взвешенной уверенности
        # ------------------------------------------------------------------
        # Фильтрация по строгому белому списку атрибутов категории датасета
        allowed_attrs = AttributeSanityValidator.ALLOWED_ATTRS_BY_CATEGORY.get(cat_key)
        if allowed_attrs:
            predictions_map = {k: v for k, v in predictions_map.items() if k in allowed_attrs}

        all_preds = list(predictions_map.values())
        for p in all_preds:
            if "grounded" not in p:
                p["grounded"] = True
            p["confidence"] = round(float(p["confidence"]), 4)
        final_found = set(predictions_map.keys())
        final_missing = sorted(list(required_attrs - final_found))

        # Научно обоснованный расчёт совместной вероятности корректности карточки
        # (Platt Scaling, Geometric Mean по обязательным атрибутам и Power-law Coverage Penalty)
        overall_conf, final_missing = self.calibrator.calculate_card_confidence(
            predictions=all_preds,
            required_attrs=required_attrs,
            category_key=cat_key,
        )

        # Формируем человеко-читаемые статусы и пояснения уверенности для каждого атрибута
        for p in all_preds:
            attr = p["attribute"]
            conf = p["confidence"]
            src = p.get("source", "")

            if p.get("consensus"):
                c_srcs = ", ".join(p.get("consensus_sources") or [src])
                p["confidence_reason"] = f"Повышенная уверенность ({conf:.2f}): подтверждено независимым консенсусом ({c_srcs})"
                p["status"] = "confirmed_by_consensus"
            elif p.get("conflict"):
                p["confidence_reason"] = f"Сниженная уверенность ({conf:.2f}): зафиксировано разногласие между экстракторами"
                p["status"] = "conflict"
            elif conf >= 0.95:
                p["confidence_reason"] = f"Высокая уверенность ({conf:.2f}): прямое совпадение в каталоге / правилах ({src})"
                p["status"] = "high_confidence"
            elif conf >= self.confidence_threshold:
                p["confidence_reason"] = f"Уверенное извлечение ({conf:.2f}): верифицировано компонентом {src}"
                p["status"] = "valid"
            else:
                p["confidence_reason"] = f"Низкая уверенность ({conf:.2f} < {self.confidence_threshold:.2f}): рекомендуется ручная проверка атрибута '{attr}'"
                p["status"] = "uncertain"

        # Карточка требует проверки человеком (Human-in-the-Loop), если:
        # 1. Итоговая уверенность ниже порога (0.87)
        # 2. Не удалось извлечь хотя бы одно обязательное поле категории (final_missing)
        # 3. Хотя бы один обязательный атрибут имеет уверенность ниже порога (критично для фильтров)
        # 4. Карточка пустая
        low_conf_required = any(
            p["confidence"] < self.confidence_threshold
            for p in all_preds
            if p["attribute"] in required_attrs
        )
        needs_review = (
            (overall_conf < self.confidence_threshold)
            or bool(final_missing)
            or low_conf_required
            or (len(all_preds) == 0)
        )

        # Формируем человеко-читаемый статус карточки и детализированные причины ручной проверки
        review_reasons: list[str] = []
        if len(all_preds) == 0:
            review_reasons.append("Не удалось извлечь ни одного атрибута из предоставленного текста карточки")
            card_status = "empty"
            status_desc = "Карточка пустая: атрибуты не обнаружены в тексте."
        else:
            if final_missing:
                review_reasons.append(f"Пропущены обязательные атрибуты категории '{cat_name}': {', '.join(final_missing)}")
            if overall_conf < self.confidence_threshold:
                review_reasons.append(f"Общая уверенность карточки ({overall_conf:.2f}) ниже допустимого порога ({self.confidence_threshold:.2f})")
            for p in all_preds:
                if p["confidence"] < self.confidence_threshold:
                    review_reasons.append(f"Низкая уверенность поля '{p['attribute']}': {p['confidence']:.2f} (порог {self.confidence_threshold:.2f})")
                if p.get("conflict"):
                    review_reasons.append(f"Зафиксирован конфликт источников для атрибута '{p['attribute']}'")

            if needs_review:
                card_status = "needs_review"
                status_desc = f"Требуется ручная проверка ({len(review_reasons)} замечаний): " + "; ".join(review_reasons[:2])
            elif degraded_tiers:
                card_status = "degraded_success"
                status_desc = f"Атрибуты успешно извлечены, но часть компонентов работала в резервном режиме ({', '.join(degraded_tiers)})."
            else:
                card_status = "approved"
                status_desc = f"Все обязательные атрибуты успешно извлечены и верифицированы (уверенность: {overall_conf:.2f}). Карточка готова к публикации."

        return {
            "external_id": card.get("external_id") or card.get("id"),
            "category": cat_name,
            "category_key": cat_key,
            "predictions": all_preds,
            "missing": final_missing,
            "overall_confidence": round(overall_conf, 4),
            "needs_review": needs_review,
            "status": card_status,
            "status_description": status_desc,
            "review_reasons": review_reasons,
            "warnings": warnings_list,
            "degraded_tiers": degraded_tiers,
            "taxonomy_status": self.taxonomy_manager.status,
        }

