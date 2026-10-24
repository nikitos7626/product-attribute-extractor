from __future__ import annotations







import json



import logging



import re



from collections import defaultdict



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

from app.services.web_retriever import WebModelRetriever



from app.services.confidence_calibrator import ConfidenceCalibrator







logger = logging.getLogger(__name__)







# --------------------------------------------------------------------------



# ПОЛНАЯ ТАКСОНОМИЯ КАТАЛОГА E-COMMERCE (6 570+ КАТЕГОРИЙ ИЗ skus.pkl)



# --------------------------------------------------------------------------



class TaxonomyManager:



    """



    Менеджер таксономии каталога E-Commerce с безопасной обработкой сбоев загрузки



    и явным отслеживанием статуса деградации сервиса (Safe Fallback & Degradation Monitoring).



    """







    _instance: TaxonomyManager | None = None







    def __init__(self, file_path: Path | None = None) -> None:



        if file_path is not None:



            self.path = Path(file_path)



        else:



            default_file = Path(getattr(settings, "taxonomy_path", "data/dictionaries/categories.json"))



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







    def _load_fallback_taxonomy(self) -> None:
        """Загружает встроенный резервный справочник таксономии E-Commerce."""
        fallback_map = {
            "1": "Смартфоны", "2": "Ноутбуки", "3": "Телевизоры", "4": "Пылесосы",
            "5": "Холодильники", "6": "Наушники", "7": "Внешние аккумуляторы",
            "8": "Микроволновые печи", "9": "Стиральные машины", "10": "Планшеты"
        }
        self.id_to_name = dict(fallback_map)
        for name in fallback_map.values():
            self.normalized_names[name.lower()] = name
        self.categories_count = 0
        logger.info("Loaded embedded fallback taxonomy: %d categories", self.categories_count)

    def load(self) -> None:



        """Загружает внешнюю таксономию E-Commerce с явным протоколированием статуса."""



        try:



            if not self.path.is_file():



                self.status = "degraded"



                self.error_message = f"Файл таксономии не найден по пути: {self.path}"



                logger.warning("TAXONOMY ALERT: %s. Активирован безопасный резервный контур категорий.", self.error_message)
                self._load_fallback_taxonomy()



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



CATALOG_TAXONOMY_ID_TO_NAME: dict[str, str] = taxonomy_manager.id_to_name



CATALOG_TAXONOMY_NORMALIZED: dict[str, str] = taxonomy_manager.normalized_names











# --------------------------------------------------------------------------



# ТАКСОНОМИЯ И СХЕМЫ АТРИБУТОВ ПО КАТЕГОРИЯМ КАТАЛОГА E-COMMERCE



# --------------------------------------------------------------------------



CATEGORY_SCHEMAS: dict[str, dict[str, Any]] = {



    "smartphones": {



        "name_ru": "Смартфоны",



        "keywords": [



            "смартфон", "телефон", "iphone", "айфон", "мобильный", "сотовый",



            "galaxy", "гэлакси", "гелакси", "redmi", "poco", "realme", "motorola", "моторола", "infinix", "инфиникс",



            "xperia", "pixel", "пиксель", "oneplus", "oppo", "vivo", "honor", "хонор",



            "huawei", "хуавей", "xiaomi", "сяоми", "samsung", "самсунг", "tecno", "текно",
            "phone", "smartphone", "nothing phone", "носинг фон", "nothing",



        ],



        "required_attrs": {"brand", "model", "memory_ram", "memory_rom", "screen_diagonal", "battery", "color"},



        "gliner_labels": ["бренд", "модель", "объём памяти", "оперативная память", "диагональ экрана", "цвет", "процессор", "ёмкость аккумулятора"],



    },



    "laptops": {



        "name_ru": "Ноутбуки",



        "keywords": ["ноутбук", "лэптоп", "ideapad", "thinkpad", "macbook", "ноут", "zenbook", "vivobook", "redmibook"],



        "required_attrs": {"brand", "model", "color", "cpu", "memory_ram", "memory_rom", "screen_diagonal"},



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



        "required_attrs": {"brand", "model", "color", "cleaning_type", "power"},



        "gliner_labels": ["бренд", "модель", "тип уборки", "время работы", "цвет", "объем пылесборника"],



    },



    "refrigerators": {



        "name_ru": "Холодильники",



        "keywords": ["холодильник", "морозильник", "морозильная", "no frost"],



        "required_attrs": {"brand", "model", "color", "defrost_system", "volume"},



        "gliner_labels": ["бренд", "модель", "система разморозки", "объем", "цвет", "габариты"],



    },







    "headphones": {



        "name_ru": "Наушники",



        "keywords": [



            "наушники", "наушник", "гарнитура", "гарнитуры", "airpods", "tws",



            "earbuds", "buds", "freebuds", "airdots", "earphones", "headphones",



            "headset", "вкладыши", "внутриканальные"



        ],



        "required_attrs": {"brand", "model", "color", "connection_type"},



        "gliner_labels": ["бренд", "модель", "цвет", "время работы", "тип подключения"],



        "subtypes": {



            "wired": {



                "name_ru": "Проводные наушники",



                "allowed_attrs": {"brand", "model", "color", "weight", "connection_type"},



                "forbidden_attrs": {"working_time", "battery"},



            },



            "wireless": {



                "name_ru": "Беспроводные наушники",



                "allowed_attrs": {"brand", "model", "color", "weight", "working_time", "battery", "connection_type"},



                "forbidden_attrs": set(),



            },



        },



    },



    "powerbanks": {



        "name_ru": "Внешние аккумуляторы (Power Bank)",



        "keywords": [



            "внешние аккумуляторы", "аккумуляторы", "портативные аккумуляторы",



            "power bank", "powerbank", "портативное зарядное",



            "повербанк", "пауэрбанк", "внешний аккумулятор",



            "портативный аккумулятор", "аккумулятор портативный", "аккумулятор внешний",



        ],



        "required_attrs": {"brand", "model", "color", "battery", "power"},



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



        "required_attrs": {"brand", "model", "memory_ram", "memory_rom", "screen_diagonal", "battery", "color"},



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



            и активирует целевую таксономию атрибутов E-Commerce.







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



        use_web_retriever: bool = False,



        use_llm: bool = True,



        confidence_threshold: float = 0.87,



        gliner_threshold: float = 0.30,



        fast_mode: bool = False,



    ) -> None:



        self.confidence_threshold = confidence_threshold



        self.fast_mode = fast_mode or getattr(settings, "fast_mode", False)



        if self.fast_mode:



            use_gliner = False



            use_llm = False

            use_web_retriever = False



        self.use_gliner = use_gliner



        self.use_catalog_enricher = use_catalog_enricher



        self.use_web_retriever = use_web_retriever



        self.use_llm = use_llm



        self.regex_extractor = RegexExtractor()



        self.gliner_extractor = GlinerExtractor(threshold=gliner_threshold) if use_gliner else None



        self.catalog_enricher = CatalogEnricher.get_instance() if use_catalog_enricher else None



        self.web_retriever = WebModelRetriever(enabled=use_web_retriever) if use_web_retriever else None



        self.llm_extractor = (



            StrictLlmFallbackExtractor(enforce_grounding=getattr(settings, "enforce_llm_grounding", False))



            if use_llm



            else None



        )



        self.brand_registry = BrandRegistry.get_instance()



        self.calibrator = ConfidenceCalibrator.get_instance()



        self.taxonomy_manager = TaxonomyManager.get_instance()



    def warmup(self) -> None:

        """

        Предварительный прогрев нейросетей и компонентов (Eager Loading / Pre-warming).

        Загружает веса GLiNER в память до приёма входящего трафика, устраняя задержку первого холодного запроса (Cold Start).

        """

        if self.use_gliner and self.gliner_extractor:

            try:

                logger.info("Eager Loading: прогрев нейросети GLiNER (%s)...", self.gliner_extractor.model_name)

                self.gliner_extractor._ensure_model()

                logger.info("Eager Loading: модель GLiNER успешно прогрета и готова к мгновенному инференсу.")

            except Exception as e:

                logger.warning("Eager Loading: сбой прогрева GLiNER (активирован безопасный fallback): %s", e)







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
            r"сумк\w*|"
            r"рюкзак\w*|"
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







            # Если категория есть в полном каталоге E-Commerce (напр. «Матрасы», «Смесители», «Шины»):



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







        # 5. Проверка по полной таксономии каталога (если не попало в специализированные тех-категории):



        if raw_cat and raw_cat in CATALOG_TAXONOMY_NORMALIZED:



            return "default", CATALOG_TAXONOMY_NORMALIZED[raw_cat]







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



            r"^(?:восстановленн\w*|уцененн\w*|нов\w*|смарт[\s\-]|беспроводн\w*|проводн\w*|портативн\w*|робот[\s\-]|true\s*wireless\b|tws\b)\s+",



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



        rem_tokens = tokens[1:]



        for i, tok in enumerate(rem_tokens):



            tok_low = tok.lower().strip(" ,.-()")



            next_tok_low = rem_tokens[i + 1].lower().strip(" ,.-()") if i + 1 < len(rem_tokens) else ""



            if re.match(r"^\d+(?:[.,]\d+)?$", tok_low) and (



                next_tok_low in ("кг", "kg", "об/мин", "об/м", "обмин", "rpm", "гб", "gb", "тб", "tb", "мач", "mah", "вт", "w", "л", "l", "гц", "hz", "см", "cm", "мм", "mm", "v", "в", "дюйм", "дюймов", "\"")



                or next_tok_low.startswith("об/")



            ):



                break



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







        if self.fast_mode:



            degraded_tiers.append("fast_mode")



            warnings_list.append("Fast mode active: using deterministic Tier 1 and KB extractors only.")



        elif self.use_gliner and (not self.gliner_extractor or not self.gliner_extractor.health()):



            degraded_tiers.append("tier2_gliner")



            warnings_list.append("GLiNER extractor is offline; falling back to Tier 1.")







        if self.use_catalog_enricher:

            kb_obj = getattr(self, "catalog_enricher", None)

            kb_status = getattr(kb_obj, "status", "unavailable") if kb_obj else "missing"

            kb_size = kb_obj.size() if kb_obj else 0

            if not kb_obj or kb_status != "healthy" or kb_size == 0:

                degraded_tiers.append("tier2_5_catalog_kb")

                kb_err = getattr(kb_obj, "error_message", None) if kb_obj else "Каталожный модуль не инициализирован"

                warnings_list.append(

                    f"Каталожный справочник моделей работает в деградированном режиме ({kb_status}): "

                    f"{kb_err or '0 моделей в базе'}. Обогащение переключено на правила и LLM."

                )







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







        raw_text_lower = f"{card.get('title', '')} {card.get('description', '')} {card.get('raw_text', '')}".lower()



        # ------------------------------------------------------------------



        # ЭТАП 1: Определение категории товара



        # ------------------------------------------------------------------



        cat_key, cat_name = self.detect_category(card)



        schema = CATEGORY_SCHEMAS.get(cat_key, CATEGORY_SCHEMAS["default"])



        gliner_labels: list[str] = list(schema["gliner_labels"])



        required_attrs: set[str] = set(schema["required_attrs"])



        is_hp_wired = False



        is_hp_wireless = False



        effective_cat_key = cat_key



        if cat_key == "headphones":



            full_card_text = f"{raw_title} {raw_desc} {raw_text} {card.get('category', '')} {card.get('raw_cat', '')}".lower()



            is_hp_wired = AttributeSanityValidator.is_wired_headphones(full_card_text)



            is_hp_wireless = AttributeSanityValidator.is_wireless_headphones(full_card_text)



            if is_hp_wired:



                effective_cat_key = "headphones_wired"



                gliner_labels = [lbl for lbl in gliner_labels if lbl != "время работы"]



            elif is_hp_wireless:



                effective_cat_key = "headphones_wireless"







        predictions_map: dict[str, Prediction] = {}



        extracted_alternatives: dict[str, list[dict[str, Any]]] = defaultdict(list)



        # ------------------------------------------------------------------

        # ЭТАП 0.5: Обработка и валидация атрибутов продавца (Seller Attributes)

        # ------------------------------------------------------------------

        seller_attrs = card.get("seller_attributes") or {}

        if isinstance(seller_attrs, dict) and seller_attrs:

            ATTR_SYNONYMS = {

                "диагональ": "screen_diagonal",

                "экран": "screen_diagonal",

                "процессор": "cpu",

                "память": "memory_rom",

                "встроенная_память": "memory_rom",

                "оперативная_память": "memory_ram",

                "озу": "memory_ram",

                "пзу": "memory_rom",

                "разрешение": "resolution",

                "аккумулятор": "battery",

                "батарея": "battery",

                "цвет": "color",

                "бренд": "brand",

                "марка": "brand",

                "производитель": "brand",

                "модель": "model",

                "мощность": "power",

                "объем": "volume",

                "тип_уборки": "cleaning_type",

                "система_размораживания": "defrost_system",

                "rom": "memory_rom",

                "ram": "memory_ram",

                "storage": "memory_rom",

                "internal_memory": "memory_rom",

                "ssd": "memory_rom",

                "hdd": "memory_rom",

                "diagonal": "screen_diagonal",

                "screen": "screen_diagonal",

                "display": "screen_diagonal",

                "battery_capacity": "battery",

                "battery_mah": "battery",

                "vendor": "brand",

            }

            for s_key, s_val in seller_attrs.items():

                s_key_str = str(s_key).strip().lower().replace("-", "_").replace(" ", "_")

                s_val_str = str(s_val).strip()

                if not s_key_str or not s_val_str:

                    continue

                canon_key = ATTR_SYNONYMS.get(s_key_str, s_key_str)

                if AttributeSanityValidator.is_valid(canon_key, s_val_str, effective_cat_key):

                    p_seller = {

                        "attribute": canon_key,

                        "value": s_val_str,

                        "confidence": 0.95,

                        "source": "seller_attributes",

                        "tier": "Tier 0.5",

                        "raw": s_val_str,

                        "grounded": True,

                    }

                    extracted_alternatives[canon_key].append(dict(p_seller))

                    if canon_key not in predictions_map:

                        predictions_map[canon_key] = p_seller







        # ------------------------------------------------------------------



        # ЭТАП 2: Tier 1 (Regex + FlashText)



        # ------------------------------------------------------------------



        t1_preds = self.regex_extractor.extract(card, category_key=effective_cat_key)



        for p in t1_preds:



            # Строгая валидация физического здравого смысла и кросс-загрязнений



            if not AttributeSanityValidator.is_valid(p["attribute"], p["value"], effective_cat_key, raw_text=raw_text or raw_desc):



                continue



            predictions_map[p["attribute"]] = p



            extracted_alternatives[p["attribute"]].append(dict(p))







        found_attrs = set(predictions_map.keys())



        missing_attrs = required_attrs - found_attrs







        # ------------------------------------------------------------------



        # ЭТАП 3: Tier 2 (GLiNER Zero-Shot NER) — таргетированно под категорию



        # ------------------------------------------------------------------



        if self.use_gliner and self.gliner_extractor:



            raw_text_lower = f"{card.get('title', '')} {card.get('description', '')} {card.get('raw_text', '')}".lower()



            needed_labels = []



            for lbl in gliner_labels:



                attr = self.gliner_extractor.LABEL_TO_ATTR.get(lbl)



                if attr not in required_attrs:



                    if attr == "cpu" and not re.search(r"\b(чип|chip|cpu|процессор|ядер\w*|ghz|ггц|snapdragon|exynos|dimensity|bionic|tensor|kirin|core|ryzen)\b", raw_text_lower):



                        continue



                needed_labels.append(lbl)







            if needed_labels:



                try:



                    t2_preds = self.gliner_extractor.extract(card, target_labels=needed_labels, category_key=effective_cat_key)



                except Exception as e:



                    logger.warning("GLiNER extraction failed: %s; falling back to Tier 1", e)



                    if "tier2_gliner" not in degraded_tiers:



                        degraded_tiers.append("tier2_gliner")



                        warnings_list.append(f"GLiNER model extraction unavailable ({e}); gracefully degraded to Tier 1 rules.")



                    t2_preds = []



                for p in t2_preds:



                    attr = p["attribute"]



                    # Строгая валидация физического здравого смысла (отсечение перепутанных Гц в батарее и т.д.)



                    if not AttributeSanityValidator.is_valid(attr, p["value"], effective_cat_key, raw_text=raw_text or raw_desc):



                        continue



                    extracted_alternatives[attr].append(dict(p))



                    existing = predictions_map.get(attr)



                    if existing is None:



                        predictions_map[attr] = p



                    elif existing.get("source") == "flashtext" and existing.get("confidence", 0) >= 0.80:



                        # Словарный бренд/цвет из FlashText — эталонный детерминированный источник



                        continue



                    elif attr == "resolution" and any(c in str(existing.get("value", "")) for c in ("×", "x", "*")):



                        # Точное пиксельное разрешение (3840×2160) не должно затираться абстрактным 4K / UHD



                        continue



                    elif attr in ("cleaning_type", "model") and existing.get("source") == "regex":
                        # Детерминированный regex для модели или типа уборки (с учетом отрицаний) не должен затираться сырым span из GLiNER
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







        # Коррекция цвета из материала корпуса для смартфонов и смарт-часов (титановый корпус -> титановый цвет)



        if "color" not in predictions_map and cat_key in ("smartphones", "smart_watches"):



            if "из титана" in raw_text_lower or "титанов" in raw_text_lower:



                if not re.search(r"\b(?:черн\w*|чёрн\w*|бел\w*|син\w*|сер\w*|золот\w*|зелен\w*|розов\w*)\b", raw_text_lower):



                    p_col = Prediction(



                        attribute="color",



                        value="титановый",



                        confidence=0.92,



                        source="material_chassis_fallback",



                        raw="титана",



                        grounded=True,



                    )



                    predictions_map["color"] = p_col



                    extracted_alternatives["color"].append(dict(p_col))







        # ------------------------------------------------------------------



        # ЭТАП 2.9: Извлечение бренда и модели для новых/незнакомых товаров



        # (Heuristic Structural Title Parser + LLM New Product Extractor)



        # ------------------------------------------------------------------



        if "brand" not in predictions_map or "model" not in predictions_map:



            title_str = card.get("title") or ""



            heur_brand, heur_model = self._parse_title_structure(title_str, cat_name)



            if heur_brand and "brand" not in predictions_map:



                if AttributeSanityValidator.is_valid("brand", heur_brand, cat_key):



                    canon_b, conf, _ = self.brand_registry.match_or_fuzzy_brand(heur_brand)



                    p_brand = Prediction(



                        attribute="brand",



                        value=canon_b or heur_brand,



                        confidence=0.88,



                        source="syntax_heuristic",



                        raw=heur_brand,



                    )



                    predictions_map["brand"] = p_brand



                    extracted_alternatives["brand"].append(dict(p_brand))



            if heur_model and "model" not in predictions_map:



                if AttributeSanityValidator.is_valid("model", heur_model, cat_key):



                    p_model = Prediction(



                        attribute="model",



                        value=heur_model,



                        confidence=0.85,



                        source="syntax_heuristic",



                        raw=heur_model,



                    )



                    predictions_map["model"] = p_model



                    extracted_alternatives["model"].append(dict(p_model))







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



                    if AttributeSanityValidator.is_valid("brand", llm_b, cat_key):



                        canon_b, conf, _ = self.brand_registry.match_or_fuzzy_brand(llm_b)



                        p_llm_b = Prediction(



                            attribute="brand",



                            value=canon_b or llm_b,



                            confidence=0.92,



                            source="llm_new_product",



                            raw=llm_b,



                        )



                        predictions_map["brand"] = p_llm_b



                        extracted_alternatives["brand"].append(dict(p_llm_b))



                if llm_m and "model" not in predictions_map:



                    if AttributeSanityValidator.is_valid("model", llm_m, cat_key):



                        p_llm_m = Prediction(



                            attribute="model",



                            value=llm_m,



                            confidence=0.90,



                            source="llm_new_product",



                            raw=llm_m,



                        )



                        predictions_map["model"] = p_llm_m



                        extracted_alternatives["model"].append(dict(p_llm_m))







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



        # ЭТАП 2.5: Каталожное обогащение (Tier 2.5) (Catalog Model Specs Enrichment)



        # Если после Tier 1 и Tier 2 остались пропущенные обязательные атрибуты,



        # но бренд и модель надежно определены, подтягиваем эталонные спецификации из базы E-Commerce.



        # ------------------------------------------------------------------



        current_missing = required_attrs - set(predictions_map.keys())



        card_model_id = card.get("model_id") or card.get("external_id") or card.get("sku_id") or card.get("id")



        if self.use_catalog_enricher and self.catalog_enricher and current_missing and (("brand" in predictions_map and "model" in predictions_map) or card_model_id):



            b_val = predictions_map.get("brand", {}).get("value", "")



            m_val = predictions_map.get("model", {}).get("value", "")



            enriched_preds = self.catalog_enricher.enrich(



                brand=b_val,



                model=m_val,



                missing_attrs=current_missing,



                category_key=cat_key,



                model_id=str(card_model_id) if card_model_id else None,



            )



            for p in enriched_preds:



                attr = p["attribute"]



                extracted_alternatives[attr].append(dict(p))



                if attr not in predictions_map:



                    predictions_map[attr] = p







        # ------------------------------------------------------------------

        NON_ENRICHABLE_FROM_MODEL = set()

        still_missing = required_attrs - set(predictions_map.keys())

        # ЭТАП 3.2: Tier 3 Автоматический поиск модели в открытых источниках (Web Model Retriever)

        # Ищет модель в международных и отечественных базах (GSM Arena, DeviceSpecifications, DNS, DuckDuckGo)

        # ------------------------------------------------------------------

        if (

            self.use_web_retriever

            and self.web_retriever

            and still_missing

            and ("brand" in predictions_map or "model" in predictions_map)

        ):

            b_val = predictions_map.get("brand", {}).get("value", "")

            m_val = predictions_map.get("model", {}).get("value", "")

            web_preds = self.web_retriever.retrieve_model_specs(

                brand=b_val,

                model=m_val,

                category_key=cat_key,

                missing_attrs=still_missing,

                title=raw_title or card.get("title", ""),

            )

            for p in web_preds:

                attr = p["attribute"]

                p["tier"] = "Tier 3: LLM Fallback"

                p["source"] = "llm_fallback"

                extracted_alternatives[attr].append(dict(p))

                if attr not in predictions_map:

                    predictions_map[attr] = p

            still_missing = (required_attrs - set(predictions_map.keys())) - NON_ENRICHABLE_FROM_MODEL



        # ------------------------------------------------------------------



        # ЭТАП 3.8: Tier 3 Строгий LLM-фоллбэк (Strict LLM Fallback)



        # Если после базы E-Commerce все еще есть пропущенные обязательные атрибуты,



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



                p["tier"] = "Tier 3: LLM Fallback"



                p["source"] = p.get("source") or "llm_strict"



                extracted_alternatives[attr].append(dict(p))



                if attr not in predictions_map:



                    predictions_map[attr] = p







        # Автоматическая динамическая регистрация нового бренда в BrandRegistry



        if "brand" in predictions_map and self.brand_registry:



            b_val = predictions_map["brand"]["value"]



            if not self.brand_registry.has_brand(b_val):



                if predictions_map["brand"].get("confidence", 0) >= 0.88:



                    self.brand_registry.register_brand(b_val, persist=False)







        # Автоматическое динамическое самообучение базы знаний моделей (Auto-Learning Model Registry)



        if (



            self.catalog_enricher



            and "brand" in predictions_map



            and "model" in predictions_map



        ):



            b_val = predictions_map["brand"]["value"]



            m_val = predictions_map["model"]["value"]



            reliable_specs = {



                attr: str(p["value"]).strip()



                for attr, p in predictions_map.items()



                if attr not in ("brand", "model", "category")



                and p.get("confidence", 0.0) >= 0.88



                and p.get("status") in ("high_confidence", "valid")



            }



            if reliable_specs:



                card_mid = card.get("model_id") or card.get("external_id") or card.get("sku_id") or card.get("id")



                self.catalog_enricher.register_model_specs(



                    brand=b_val,



                    model=m_val,



                    specs=reliable_specs,



                    model_id=str(card_mid) if card_mid else None,



                    persist=False,



                )







        # ------------------------------------------------------------------



        # ЭТАП 3.9: Слабый консенсус источников (Snorkel Multi-Source Consensus)



        # ------------------------------------------------------------------



        if cat_key == "headphones":



            if is_hp_wired:



                predictions_map.pop("working_time", None)



                predictions_map.pop("battery", None)



                extracted_alternatives.pop("working_time", None)



                extracted_alternatives.pop("battery", None)



                if "connection_type" not in predictions_map:



                    p_conn = Prediction(



                        attribute="connection_type",



                        value="проводные",



                        confidence=0.97,



                        source="domain_rule",



                        raw="проводные",



                        grounded=True,



                    )



                    predictions_map["connection_type"] = p_conn



                    extracted_alternatives["connection_type"].append(dict(p_conn))



            elif is_hp_wireless:



                if "connection_type" not in predictions_map:



                    p_conn = Prediction(



                        attribute="connection_type",



                        value="беспроводные",



                        confidence=0.97,



                        source="domain_rule",



                        raw="беспроводные",



                        grounded=True,



                    )



                    predictions_map["connection_type"] = p_conn



                    extracted_alternatives["connection_type"].append(dict(p_conn))







        # Коррекция характеристик пылесосов с учетом отрицаний в тексте
        if cat_key == "vacuum_cleaners" or "cleaning_type" in predictions_map:
            full_card_text = f"{card.get('title', '')} {card.get('description', '')} {card.get('raw_text', '')}".strip()
            # 1. Если cleaning_type не найден или требует калибровки
            if "cleaning_type" not in predictions_map:
                ct_pred = self.regex_extractor._find_cleaning_type(full_card_text, title=card.get("title", ""))
                if ct_pred and AttributeSanityValidator.is_valid("cleaning_type", ct_pred["value"], cat_key, raw_text=full_card_text):
                    predictions_map["cleaning_type"] = ct_pred
                    extracted_alternatives["cleaning_type"].append(dict(ct_pred))
            else:
                # Проверяем на противоречие с отрицаниями в тексте
                curr_ct = str(predictions_map["cleaning_type"]["value"]).lower()
                if "влажн" in curr_ct or "комбинир" in curr_ct:
                    if self.regex_extractor.is_wet_cleaning_negated(full_card_text):
                        p_fix = Prediction(
                            attribute="cleaning_type",
                            value="сухая",
                            confidence=0.96,
                            source="domain_rule_negation",
                            raw="сухая (отрицание влажной уборки)",
                            grounded=True,
                        )
                        predictions_map["cleaning_type"] = p_fix
                        extracted_alternatives["cleaning_type"].append(dict(p_fix))
                elif "сух" in curr_ct:
                    if self.regex_extractor.is_dry_cleaning_negated(full_card_text):
                        p_fix = Prediction(
                            attribute="cleaning_type",
                            value="влажная",
                            confidence=0.96,
                            source="domain_rule_negation",
                            raw="влажная (отрицание сухой уборки)",
                            grounded=True,
                        )
                        predictions_map["cleaning_type"] = p_fix
                        extracted_alternatives["cleaning_type"].append(dict(p_fix))

        # Защита от мусорных слов в названии модели
        if "model" in predictions_map:
            if not AttributeSanityValidator.is_valid("model", predictions_map["model"]["value"], cat_key, raw_text=raw_text or raw_desc):
                del predictions_map["model"]
                # Попытка восстановить модель через эвристический парсер заголовка или regex
                t_str = card.get("title") or ""
                _, heur_m = self._parse_title_structure(t_str, cat_name)
                if heur_m and AttributeSanityValidator.is_valid("model", heur_m, cat_key, raw_text=raw_text or raw_desc):
                    p_rec = Prediction(
                        attribute="model",
                        value=self.regex_extractor._canon_model(heur_m),
                        confidence=0.92,
                        source="heuristic_title_recovery",
                        raw=heur_m,
                        grounded=True,
                    )
                    predictions_map["model"] = p_rec
                    extracted_alternatives["model"].append(dict(p_rec))

        self.calibrator.apply_multi_source_consensus(predictions_map, extracted_alternatives)







        # ------------------------------------------------------------------



        # ЭТАП 4: Валидация полноты и расчет взвешенной уверенности



        # ------------------------------------------------------------------



        # Фильтрация по строгому белому списку атрибутов категории датасета



        allowed_attrs = AttributeSanityValidator.ALLOWED_ATTRS_BY_CATEGORY.get(effective_cat_key) or AttributeSanityValidator.ALLOWED_ATTRS_BY_CATEGORY.get(cat_key)



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



            if not p.get("tier"):

                if src == "catalog_kb":

                    p["tier"] = "Tier 2.5"

                elif src in ("flash_text", "regex"):

                    p["tier"] = "Tier 1"

                elif src == "gliner":

                    p["tier"] = "Tier 2"

                elif src in ("llm_fallback", "llm_strict"):

                    p["tier"] = "Tier 3"

                else:

                    p["tier"] = "Tier 1"







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



        # Строгий контроль качества (Zero-Trust Generative AI):

        # Если использован генеративный LLM Fallback (Tier 3), карточка обязана пройти валидацию оператора

        llm_preds_attrs = [

            p["attribute"]

            for p in all_preds

            if p.get("source") in ("llm_strict", "llm_fallback") or p.get("tier") == "Tier 3"

        ]

        has_llm_preds = bool(llm_preds_attrs)

        force_review_on_llm = getattr(settings, "force_review_on_llm", True)



        needs_review = (



            (overall_conf < self.confidence_threshold)



            or bool(final_missing)



            or low_conf_required



            or (len(all_preds) == 0)



            or (force_review_on_llm and has_llm_preds)



        )







        # Формируем человеко-читаемый статус карточки и детализированные причины ручной проверки



        review_reasons: list[str] = []



        if len(all_preds) == 0:



            review_reasons.append("Не удалось извлечь ни одного атрибута из предоставленного текста карточки")



            card_status = "empty"



            status_desc = "Карточка пустая: атрибуты не обнаружены в тексте."



        else:



            if force_review_on_llm and has_llm_preds:

                review_reasons.append(f"Использован генеративный LLM Fallback (Tier 3) для атрибутов: {', '.join(llm_preds_attrs)}. Требуется подтверждение модератора.")



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



            "subcategory": "wired" if is_hp_wired else ("wireless" if is_hp_wireless else None),



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







