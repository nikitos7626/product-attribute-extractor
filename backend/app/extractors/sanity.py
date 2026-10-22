"""



Централизованный модуль валидации физического здравого смысла (Sanity Check)



и защиты от галлюцинаций / перепутанных единиц измерения.







Применяется на ВСЕХ уровнях каскада:



  - Tier 1: Regex & FlashText



  - Tier 2: GLiNER Zero-Shot NER



  - Tier 3: LLM Fallback



  - Pipeline Master Gate: финальный аудит перед выдачей JSON в каталог.



"""



from __future__ import annotations







import re



from typing import Any











class AttributeSanityValidator:



    """



    Строгий физический и контекстный валидатор атрибутов товаров.



    Проверяет:



      1. Запрещенные единицы (кросс-загрязнение: Гц в батарее, дюймы в памяти и т.д.)



      2. Физические допустимые диапазоны с учетом категории товара



      3. Атрибуты, недопустимые для данной категории (например, экран у пылесоса или память у холодильника)



      4. Черный список маркетингового мусора (для цвета и модели)



    """







    # Матрицы экрана



    ALLOWED_DISPLAY_TECHS: dict[str, str] = {



        "triluminos": "Triluminos",



        "oled": "OLED",



        "олед": "OLED",



        "amoled": "AMOLED",



        "super amoled": "Super AMOLED",



        "superamoled": "Super AMOLED",



        "qled": "QLED",



        "клед": "QLED",



        "neo qled": "Neo QLED",



        "ips": "IPS",



        "ипс": "IPS",



        "va": "VA",



        "tn": "TN",



        "nanocell": "NanoCell",



        "mini led": "Mini-LED",



        "mini-led": "Mini-LED",



        "retina": "Retina",



        "poled": "pOLED",
        "qned": "QNED",
        "led": "LED",
        "лед": "LED",
        "dled": "Direct LED",



    }







    # Недопустимые атрибуты по категориям (защита от мусора и кросс-загрязнения)



    FORBIDDEN_ATTRS_BY_CATEGORY: dict[str, set[str]] = {



        "smartphones": {



            "power", "volume", "warranty", "cleaning_type", "defrost_system",



            "working_time", "bagless",



        },



        "laptops": {



            "cleaning_type", "defrost_system", "power", "working_time", "volume",



            "warranty", "bagless",



        },



        "vacuum_cleaners": {



            "memory_rom", "memory_ram", "screen_diagonal", "refresh_rate",



            "resolution", "cpu", "os", "defrost_system",



        },



        "refrigerators": {



            "memory_rom", "memory_ram", "screen_diagonal", "refresh_rate",



            "resolution", "cpu", "os", "cleaning_type", "battery", "power",



            "working_time",



        },



        "headphones": {



            "screen_diagonal", "refresh_rate", "resolution", "memory_rom",



            "memory_ram", "cleaning_type", "defrost_system", "power", "cpu",



            "os", "volume",



        },



        "headphones_wired": {



            "working_time", "battery",



            "screen_diagonal", "refresh_rate", "resolution", "memory_rom",



            "memory_ram", "cleaning_type", "defrost_system", "power", "cpu",



            "os", "volume",



        },



        "headphones_wireless": {



            "screen_diagonal", "refresh_rate", "resolution", "memory_rom",



            "memory_ram", "cleaning_type", "defrost_system", "power", "cpu",



            "os", "volume",



        },



        "tvs": {



            "cleaning_type", "defrost_system", "battery", "memory_ram",



            "working_time", "cpu", "os", "memory_rom", "volume", "warranty",



        },



        "powerbanks": {



            "memory_rom", "memory_ram", "screen_diagonal", "refresh_rate",



            "resolution", "cpu", "os", "cleaning_type", "defrost_system",



            "working_time", "volume",



        },



        "microwaves": {



            "screen_diagonal", "refresh_rate", "resolution", "cpu", "os",



            "cleaning_type", "battery", "defrost_system",



        },



        "tablets": {



            "power", "warranty", "cleaning_type", "defrost_system",



            "working_time", "bagless", "load_capacity", "spin_speed",



        },



        "desktops": {



            "cleaning_type", "defrost_system", "power", "working_time", "volume",



            "warranty", "bagless", "battery", "load_capacity", "spin_speed",



        },



        "monitors": {



            "cleaning_type", "defrost_system", "battery", "memory_ram",



            "working_time", "cpu", "os", "memory_rom", "volume", "warranty",



            "load_capacity", "spin_speed",



        },



        "washing_machines": {



            "screen_diagonal", "refresh_rate", "resolution", "cpu", "os",



            "memory_rom", "memory_ram", "battery", "defrost_system", "cleaning_type",



        },



        "smart_watches": {



            "cleaning_type", "defrost_system", "power", "volume", "warranty",



            "load_capacity", "spin_speed", "gpu",



        },



        "kettles": {



            "screen_diagonal", "refresh_rate", "resolution", "cpu", "os",



            "memory_rom", "memory_ram", "battery", "cleaning_type", "defrost_system",



            "load_capacity", "spin_speed", "gpu",



        },



    }







    # Белый список допустимых атрибутов по категориям из датасета



    ALLOWED_ATTRS_BY_CATEGORY: dict[str, set[str]] = {



        "smartphones": {"brand", "model", "memory_rom", "memory_ram", "screen_diagonal", "battery", "color", "cpu", "os", "weight", "resolution", "refresh_rate"},



        "laptops": {"brand", "model", "cpu", "memory_ram", "memory_rom", "screen_diagonal", "color", "os", "battery", "weight", "gpu"},



        "tvs": {"brand", "model", "screen_diagonal", "resolution", "refresh_rate", "color", "power", "display_tech"},



        "tv": {"brand", "model", "screen_diagonal", "resolution", "refresh_rate", "color", "power", "display_tech"},



        "vacuum_cleaners": {"brand", "model", "power", "cleaning_type", "battery", "weight", "color", "working_time", "volume"},



        "refrigerators": {"brand", "model", "defrost_system", "color", "volume", "warranty", "dimensions", "weight"},



        "headphones": {"brand", "model", "color", "weight", "working_time", "connection_type"},



        "headphones_wired": {"brand", "model", "color", "weight", "connection_type"},



        "headphones_wireless": {"brand", "model", "color", "weight", "working_time", "battery", "connection_type"},



        "powerbanks": {"brand", "model", "battery", "color", "power", "weight"},



        "microwaves": {"brand", "model", "volume", "power", "color", "weight"},



        "tablets": {"brand", "model", "memory_rom", "memory_ram", "screen_diagonal", "battery", "color", "cpu", "os", "weight", "resolution", "refresh_rate"},



        "desktops": {"brand", "model", "cpu", "memory_ram", "memory_rom", "color", "os", "weight", "gpu"},



        "monitors": {"brand", "model", "screen_diagonal", "resolution", "refresh_rate", "color", "power", "display_tech"},



        "washing_machines": {"brand", "model", "load_capacity", "spin_speed", "color", "weight", "power"},



        "smart_watches": {"brand", "model", "screen_diagonal", "battery", "color", "working_time", "weight", "os"},



        "kettles": {"brand", "model", "volume", "power", "color", "weight"},



        "default": {"brand", "model", "color", "weight", "power", "volume"},



    }







    # Корни реальных цветов



    COLOR_ROOTS: set[str] = {



        "черн", "чёрн", "бел", "син", "красн", "сер", "золот", "зелен", "зелён",



        "титан", "фиолет", "желт", "жёлт", "оранж", "розов", "серебр", "коричн",



        "голуб", "бежев", "борд", "бронз", "перламутр", "мятн", "лавандов", "изумруд",



        "графит", "black", "white", "blue", "red", "grey", "gray", "gold", "green",



        "purple", "yellow", "orange", "pink", "silver", "brown", "cyan", "titanium",



        "midnight", "starlight", "violet", "emerald", "mint", "dark", "light",



        "антрацит", "бирюз", "оливк", "коралл", "шампань", "хаки", "сиренев", "малинов", "сапфир", "песочн", "рубин",
        "нержавеющ", "сталь", "пурпур", "крем", "кофе", "лайм", "кость", "полуночн", "сияющ",
    }







    # Мусорные слова для моделей



    BAD_MODEL_WORDS: set[str] = {



        "смартфон", "телефон", "phone", "smartphone", "ноутбук", "планшет", "телевизор",



        "наушники", "беспроводные", "беспроводной", "беспроводная", "беспроводное",
        "проводные", "проводной", "проводная", "проводное",
        "пылесос", "робот-пылесос", "робот", "роботы",
        "вертикальный", "вертикальная", "вертикальные", "вертикальное",
        "моющий", "моющая", "моющие", "моющее",
        "ручной", "ручная", "ручные",
        "портативный", "портативная", "портативные",
        "стационарный", "стационарная",
        "аккумуляторный", "аккумуляторная", "аккумуляторные",
        "циклонный", "циклонная",
        "мешковой", "безмешковый", "контейнерный",



        "холодильник", "процессор", "ядерный", "аккумулятор", "батарея",



        "пикселей", "разрешение", "память", "оперативной",



        "экран", "дисплей", "камера", "дизайн", "динамик",



        "корпус", "стекло", "зарядка", "быстрая зарядка",



        "чехол", "пленка", "плёнка", "блок питания", "оригинал", "новые", "новый",



        "стиральная машина", "стиральная", "машина", "микроволновая печь", "микроволновка",



        "электрический чайник", "чайник", "пауэрбанк",



    }







    @classmethod



    def is_wired_headphones(cls, text: str) -> bool:



        """Определяет, являются ли наушники чисто проводными (нет Bluetooth/TWS/аккумулятора)."""



        if not text:



            return False



        t = str(text).lower()



        has_wireless = bool(re.search(



            r"\b(?:беспроводн\w*|bluetooth|блютуз|tws|true\s*wireless|wireless|радиоканал|airpods|buds|freebuds|earbuds|airdots)\b",



            t,



            re.IGNORECASE,



        ))



        has_wired = bool(re.search(



            r"\b(?:проводн\w*|кабел\w*|с\s+проводом|по\s+проводу|3\.5\s*мм|3\.5mm|mini-?jack|jack\s*3\.5|штекер|проводное|проводной|wired)\b",



            t,



            re.IGNORECASE,



        ))



        return has_wired and not has_wireless







    @classmethod



    def is_wireless_headphones(cls, text: str) -> bool:



        """Определяет, являются ли наушники беспроводными (Bluetooth / TWS / радиоканал)."""



        if not text:



            return False



        t = str(text).lower()



        return bool(re.search(



            r"\b(?:беспроводн\w*|bluetooth|блютуз|tws|true\s*wireless|wireless|радиоканал|airpods|buds|freebuds|earbuds|airdots)\b",



            t,



            re.IGNORECASE,



        ))







    @classmethod



    def is_valid(cls, attr_name: str, value: str, category_key: str = "default", raw_text: str | None = None) -> bool:



        """



        Главная точка входа. Возвращает True, только если значение физически правдоподобно.



        """



        if not value or not str(value).strip():



            return False







        val_lower = str(value).lower().strip()







        if category_key == "headphones" and raw_text:



            if cls.is_wired_headphones(raw_text):



                category_key = "headphones_wired"



            elif cls.is_wireless_headphones(raw_text):



                category_key = "headphones_wireless"







        # 1. Проверка на соответствие белому списку атрибутов категории датасета



        if category_key and category_key != "default" and category_key in cls.ALLOWED_ATTRS_BY_CATEGORY:



            if attr_name not in cls.ALLOWED_ATTRS_BY_CATEGORY[category_key]:



                return False







        # 2. Проверка на несовместимость категории и атрибута



        forbidden = cls.FORBIDDEN_ATTRS_BY_CATEGORY.get(category_key, set())



        if attr_name in forbidden:



            return False







        # 2. Батарея (Battery)



        if attr_name == "battery":



            # Кросс-загрязнение: батарея не может содержать Гц, дюймы, память или ватты



            if any(u in val_lower for u in ["гц", "hz", "дюйм", '"', "гб", "gb", "тб", "ватт", "вт", "w"]):



                return False



            m = re.search(r"(\d+)", val_lower.replace(" ", ""))



            if not m:



                return False



            val_mah = int(m.group(1))







            # Физические диапазоны по категориям



            if category_key == "smartphones":



                # Смартфон: от 800 мАч до 25000 мАч (включая защищенные Oukitel, Blackview)
                return 800 <= val_mah <= 25000



            elif category_key == "tablets":



                return 1000 <= val_mah <= 20000



            elif category_key == "smart_watches":



                return 100 <= val_mah <= 1200



            elif category_key == "headphones_wired":



                return False



            elif category_key in ("headphones", "headphones_wireless"):



                return 25 <= val_mah <= 1500



            elif category_key == "vacuum_cleaners":



                return 1000 <= val_mah <= 15000



            elif category_key == "powerbanks":



                return 1000 <= val_mah <= 80000



            else:



                return 300 <= val_mah <= 80000







        # 3. Экран (Screen Diagonal)



        if attr_name == "screen_diagonal":



            # Не может содержать память, батарею, частоту или ватты



            if any(u in val_lower for u in ["гб", "gb", "тб", "tb", "мач", "mah", "гц", "hz", "ватт", "вт"]):



                return False



            m = re.search(r"(\d{1,3}(?:[.,]\d{1,2})?)", val_lower)



            if not m:



                return False



            diag = float(m.group(1).replace(",", "."))







            # Физические диапазоны по категориям



            if category_key == "smartphones":



                # Смартфон: от 3.5" (iPhone 4) до 8.3" (Fold / Mate X в раскрытом виде)
                return 3.5 <= diag <= 8.3



            elif category_key == "tablets":



                return 6.8 <= diag <= 16.0



            elif category_key == "laptops":



                # Ноутбук: от 11.0" до 19.0"



                return 11.0 <= diag <= 19.0



            elif category_key == "monitors":



                return 15.0 <= diag <= 65.0



            elif category_key == "smart_watches":



                return 0.9 <= diag <= 2.5



            elif category_key == "tvs":



                # Телевизор: от 20" до 120"



                return 20.0 <= diag <= 120.0



            else:



                return 0.9 <= diag <= 120.0







        # 4. Память ROM (Накопитель)



        if attr_name == "memory_rom":



            if any(u in val_lower for u in ['"', "дюйм", "мач", "mah", "гц", "hz", "ватт"]):



                return False



            m = re.search(r"(\d+(?:[.,]\d+)?)\s*(гб|gb|тб|tb)?", val_lower)



            if not m:



                return False



            num = float(m.group(1).replace(",", "."))



            unit = (m.group(2) or "гб").lower()



            val_gb = num * 1024 if "т" in unit else num







            if category_key == "smartphones" or category_key == "tablets":



                return 16 <= val_gb <= 2048



            elif category_key == "laptops":



                return 32 <= val_gb <= 8192



            elif category_key == "desktops":



                return 32 <= val_gb <= 32768



            else:



                return 8 <= val_gb <= 32768







        # 5. Память RAM (ОЗУ)



        if attr_name == "memory_ram":



            if any(u in val_lower for u in ['"', "дюйм", "мач", "mah", "гц", "hz", "ватт"]):



                return False



            m = re.search(r"(\d+(?:[.,]\d+)?)\s*(гб|gb)?", val_lower)



            if not m:



                return False



            val_ram = float(m.group(1).replace(",", "."))







            if category_key == "smartphones" or category_key == "tablets":



                return 1 <= val_ram <= 32



            elif category_key == "laptops":



                return 2 <= val_ram <= 128



            elif category_key == "desktops":



                return 2 <= val_ram <= 512



            else:



                return 1 <= val_ram <= 512







        # 6. Частота обновления (Refresh Rate)



        if attr_name == "refresh_rate":



            if any(u in val_lower for u in ["мач", "mah", "дюйм", '"', "гб", "gb", "тб"]):



                return False



            m = re.search(r"(\d{2,3})", val_lower)



            if not m:



                return False



            hz = int(m.group(1))



            return 48 <= hz <= 360







        # 7. Цвет (Color)



        if attr_name == "color":



            # Цвет не может содержать цифры (например, "15 Pro", "256GB" — это не цвет)



            if re.search(r"\d", val_lower):



                return False



            # Черный список маркетингового шума



            bad_phrases = {"красивый дизайн", "дизайн", "стильный", "корпус", "новинка", "смартфон", "телефон", "камера", "зарядка"}



            if any(bp in val_lower for bp in bad_phrases):



                return False



            # Обязан содержать корень реального цвета



            return any(cr in val_lower for cr in cls.COLOR_ROOTS)







        # 8. Модель (Model)



        if attr_name == "model":



            val_clean = val_lower.strip()
            # 1. Точное совпадение с мусорным словом ("phone", "телефон", "беспроводной", "робот" и т.д.)
            if val_clean in cls.BAD_MODEL_WORDS:
                return False
            # 2. Содержит родовые слова категорий без номера модели ("флагманский смартфон", "игровой ноутбук" и др.)
            has_model_specifier = bool(re.search(r"(?:\d|\b(?:x|xs|xr|se|gt|pro|ultra|max|plus|air|mini|fold|flip|lite|neo|prime|one|duo|fe)\b)", val_clean))
            words = [w for w in re.findall(r"\w+", val_clean) if w not in cls.BAD_MODEL_WORDS and not re.fullmatch(r"^[а-яё]{3,}(?:ый|ий|ой|ая|яя|ое|ее|ые|ие)$", w)]
            if not words and not has_model_specifier:
                return False

            # Одиночные русские прилагательные и причастия (беспроводной, моющий, вертикальный и т.д.)
            if len(val_lower.split()) == 1 and re.fullmatch(r"^[а-яё]{3,}(?:ый|ий|ой|ая|яя|ое|ее|ые|ие)$", val_lower):



                return False



            from app.extractors.normalization.dictionaries import BRANDS, COLORS



            if val_lower in BRANDS:



                return False



            if val_lower in COLORS:



                return False



            # Модель не должна состоять исключительно из чисел, единиц измерения и спецсимволов



            clean_spec = re.sub(



                r"\b(?:\d+(?:[.,]\d+)?|кг|kg|об/?мин|rpm|вт|w|л|l|гб|gb|тб|tb|мач|mah|гц|hz|см|cm|мм|mm|v|в)\b",



                "",



                val_lower,



            ).strip(" ,.-/()")



            if not clean_spec:



                return False



            # Модель не должна быть чисто служебным словом или числом без букв



            return len(val_lower) >= 2











        # 9. Процессор (CPU)



        if attr_name == "cpu":



            if val_lower in {"смартфон", "телефон", "ноутбук", "планшет", "телевизор", "экран", "дисплей", "камера", "аккумулятор", "батарея"}:



                return False



            from app.extractors.normalization.dictionaries import BRANDS, COLORS



            if val_lower in BRANDS or val_lower in COLORS:



                return False



            known_chips = {



                "intel", "core", "ryzen", "amd", "mediatek", "helio", "dimensity",



                "snapdragon", "qualcomm", "apple", "bionic", "exynos", "m1", "m2",



                "m3", "m4", "a14", "a15", "a16", "a17", "a18", "kirin", "tensor",



                "celeron", "pentium", "geforce", "radeon", "unisoc", "spreadtrum"



            }



            return any(c in val_lower for c in known_chips) or bool(re.search(r"\b(i[3579]|cpu|процессор|ядер\w*|ghz|ггц)\b", val_lower))











        # 10. Вес (Weight)



        if attr_name == "weight":



            m = re.search(r"(\d+(?:[.,]\d+)?)\s*(г|g|кг|kg)?", val_lower)



            if not m:



                return False



            val_num = float(m.group(1).replace(",", "."))
            explicit_unit = m.group(2)
            if explicit_unit:
                unit = explicit_unit.lower()
                val_g = val_num * 1000 if ("к" in unit or "k" in unit) else val_num
            else:
                if category_key in ("refrigerators", "washing_machines") and val_num < 300:
                    val_g = val_num * 1000
                elif category_key in ("vacuum_cleaners", "microwaves", "tvs", "monitors", "laptops") and val_num < 100:
                    val_g = val_num * 1000
                elif category_key == "powerbanks" and val_num < 5:
                    val_g = val_num * 1000
                elif category_key in ("smartphones", "smart_watches", "headphones", "tablets") and val_num < 1.0:
                    val_g = val_num * 1000
                else:
                    val_g = val_num







            if category_key == "smartphones":



                # Смартфон: от 100 г до 400 г



                return 100 <= val_g <= 400



            elif category_key == "laptops":



                # Ноутбук: от 700 г до 6000 г



                return 700 <= val_g <= 6000



            elif category_key == "headphones":



                return 20 <= val_g <= 600



            elif category_key == "washing_machines":



                # Стиральная машина: не менее 40 кг



                return 40000 <= val_g <= 150000



            elif category_key == "refrigerators":



                # Холодильник: не менее 30 кг



                return 30000 <= val_g <= 250000



            return 20 <= val_g <= 250000







        # 11. Тип уборки



        if attr_name == "cleaning_type":



            if not any(k in val_lower for k in ["сух", "влажн", "комбинир"]):
                return False
            if raw_text:
                raw_lower = raw_text.lower()
                # Если в значении заявлена влажная или комбинированная уборка:
                if "влажн" in val_lower or "комбинир" in val_lower:
                    is_wet_negated = bool(re.search(
                        r"(?:"
                        r"\b(?:нет|без|не\s+(?:поддержива\w*|предназначен\w*|рассчитан\w*|подходит|входит|комплект\w*)|отсутству\w*|не\s+умеет|не\s+моет)"
                        r"[^.,;!?()\n]{0,50}\b(?:насадк\w*|режим\w*|функци\w*|возможност\w*|для)?\s*(?:влажн\w*|мыть[яе]|пол\w*)\b"
                        r"|\b(?:насадк\w*|режим\w*|функци\w*|возможност\w*|для)?\s*(?:влажн\w*|мыть[яе]|полов)\b[^.,;!?()\n]{0,40}\b(?:отсутству\w*|не\s+(?:предусмотрен\w*|входит|поддержива\w*|рассчитан\w*|подходит)|нет)\b"
                        r"|\b(?:только|исключительно)\s+(?:для\s+)?сух\w*\b"
                        r"|\bсух\w*(?:\s+уборк\w*)?[^.,;!?()\n]{0,30}\b(?:а\s+не|но\s+не|без)\s+(?:для\s+)?влажн\w*\b"
                        r"|\bне\s+моет(?:\s+пол\w*)?\b"
                        r")",
                        raw_lower,
                    ))
                    if is_wet_negated:
                        return False
                # Если в значении заявлена сухая уборка:
                if "сух" in val_lower:
                    is_dry_negated = bool(re.search(
                        r"(?:"
                        r"\b(?:нет|без|не\s+(?:поддержива\w*|предназначен\w*|рассчитан\w*|подходит|входит|комплект\w*)|отсутству\w*)"
                        r"[^.,;!?()\n]{0,50}\b(?:насадк\w*|режим\w*|функци\w*|для)?\s*сух\w*\b"
                        r"|\b(?:насадк\w*|режим\w*|функци\w*|для)?\s*сух\w*\b[^.,;!?()\n]{0,40}\b(?:отсутству\w*|не\s+(?:предусмотрен\w*|входит|поддержива\w*|рассчитан\w*|подходит)|нет)\b"
                        r"|\b(?:только|исключительно)\s+(?:для\s+)?влажн\w*\b"
                        r"|\bвлажн\w*(?:\s+уборк\w*)?[^.,;!?()\n]{0,30}\b(?:а\s+не|но\s+не|без)\s+(?:для\s+)?сух\w*\b"
                        r")",
                        raw_lower,
                    ))
                    if is_dry_negated:
                        return False
            return True







        # 12. Система разморозки



        if attr_name == "defrost_system":



            return any(k in val_lower for k in ["no frost", "ноу фрост", "капельн", "ручн", "автомат"])







        # 13. Технология экрана



        if attr_name == "display_tech":



            return any(k in val_lower for k in cls.ALLOWED_DISPLAY_TECHS)







        # 14. Бренд (Brand)



        if attr_name == "brand":



            bad_brand_words = {



                "смартфон", "телефон", "ноутбук", "планшет", "телевизор", "наушники",



                "пылесос", "робот-пылесос", "холодильник", "стиральная машина", "стиральная", "машина",



                "микроволновая печь", "микроволновка", "электрический чайник", "чайник", "пауэрбанк",



                "товар", "устройство", "аксессуар", "комплект", "модель", "прибор", "техника",



                "изделие", "оборудование", "аппарат", "штука", "деталь", "запчасть",



                "экран", "дисплей", "память", "батарея",



                "аккумулятор", "чехол", "стекло", "зарядка", "оригинал", "новый", "новые", "новинка",



                "гб", "gb", "мач", "mah", "tws", "anc", "bluetooth", "блютуз", "wireless", "true", "wired", "беспроводной", "проводной",
                "напольный", "ортопедический", "неизвестно", "неизвестен", "неизвестный", "нет", "нет бренда", "без бренда", "не указан", "не указано", "отсутствует", "n/a", "#n/a", "unknown", "none", "null"
            }



            if category_key in ("smartphones", "laptops", "tablets", "tvs", "vacuum_cleaners", "refrigerators", "headphones", "desktops"):



                bad_brand_words.update({



                    "mediatek", "qualcomm", "snapdragon", "dimensity", "intel", "amd", "nvidia", "rtx", "gtx", "adreno", "mali"



                })



            return len(val_lower) >= 2 and val_lower not in bad_brand_words







        # 15. Время работы (Working Time)



        if attr_name == "working_time":



            if category_key == "headphones_wired":



                return False



            has_digits = bool(re.search(r"\d+", val_lower))



            has_time_unit = bool(re.search(r"(?:ч|час\w*|мин\w*|h|hr|m|sec|сек)\b", val_lower))



            return has_digits and has_time_unit and len(val_lower.split()) <= 4







        # 16. Разрешение экрана (Resolution)



        if attr_name == "resolution":



            # Разрешение не может быть дюймами, батареей, частотой или памятью



            if any(u in val_lower for u in ['"', "дюйм", "inch", "мач", "mah", "гц", "hz", "гб", "gb", "ватт"]):



                return False



            has_dims = bool(re.search(r"\b\d{3,4}\s*[x×*]\s*\d{3,4}\b", val_lower))



            has_named = any(k in val_lower for k in ["4k", "8k", "ultra hd", "full hd", "uhd", "fhd", "qhd", "wqhd", "hd"])



            return has_dims or has_named







        # 17. Видеокарта (GPU)



        if attr_name == "gpu":



            if any(u in val_lower for u in ["экран", "дисплей", "retina", "дюйм", '"', "мач", "mah", "гц", "hz", "гб", "gb", "тб", "no frost"]):



                return False



            known_gpus = {



                "rtx", "gtx", "geforce", "nvidia", "radeon", "amd", "intel iris", "iris xe",



                "intel uhd", "intel arc", "arc", "adreno", "mali", "apple", "m1", "m2", "m3", "m4",



                "встроенн", "интегрированн", "дискретн", "graphics", "графика"



            }



            return any(g in val_lower for g in known_gpus)







        # 18. Загрузка стиральной машины (Load Capacity)



        if attr_name == "load_capacity":



            m = re.search(r"(\d+(?:[.,]\d+)?)", val_lower)



            if not m:



                return False



            kg = float(m.group(1).replace(",", "."))



            return 2.0 <= kg <= 25.0







        # 19. Скорость отжима (Spin Speed)



        if attr_name == "spin_speed":



            m = re.search(r"(\d{3,4})", val_lower)



            if not m:



                return False



            rpm = int(m.group(1))



            return 400 <= rpm <= 2000











        # 20. Габариты (Dimensions)



        if attr_name == "dimensions":



            return bool(re.search(r"\d+(?:[.,]\d+)?\s*[xх×*]\s*\d+(?:[.,]\d+)?\s*[xх×*]\s*\d+(?:[.,]\d+)?", val_lower))







        # 21. Мощность (Power)



        if attr_name == "power":



            m = re.search(r"(\d+(?:[.,]\d+)?)", val_lower)



            if not m:



                return False



            p_val = float(m.group(1).replace(",", "."))



            if category_key == "microwaves":



                return 400 <= p_val <= 3000



            elif category_key == "kettles":



                return 400 <= p_val <= 3500



            elif category_key == "washing_machines":



                return 500 <= p_val <= 3500



            elif category_key == "tvs":



                return 10 <= p_val <= 1000



            elif category_key == "powerbanks":



                return 5 <= p_val <= 200



            elif category_key == "vacuum_cleaners":



                return 15 <= p_val <= 3500



            return 5 <= p_val <= 5000







        # 22. Тип подключения (Connection Type)



        if attr_name == "connection_type":



            return any(k in val_lower for k in ["проводн", "беспроводн", "tws", "bluetooth", "блютуз", "wired", "wireless"])







        # 23. Объем (Volume)



        if attr_name == "volume":



            if any(u in val_lower for u in ["дб", "db", "мач", "mah", "гц", "hz", "ватт", "вт"]):



                return False



            m = re.search(r"(\d+(?:[.,]\d+)?)", val_lower)



            if not m:



                return False



            v = float(m.group(1).replace(",", "."))



            if any(ml in val_lower for ml in ["мл", "ml"]):



                return 10.0 <= v <= 10000.0



            if category_key == "vacuum_cleaners":



                return 0.05 <= v <= 15.0



            elif category_key == "microwaves":



                return 10.0 <= v <= 60.0



            elif category_key == "refrigerators":



                return 20.0 <= v <= 1000.0



            elif category_key == "kettles":



                return 0.3 <= v <= 10.0



            return 0.05 <= v <= 1500.0







        # 24. Операционная система (OS)



        if attr_name == "os":



            known_os = {



                "android", "ios", "windows", "macos", "harmonyos", "tizen",



                "webos", "без ос", "linux", "dos", "hyperos", "chromeos",



                "watchos", "wearos", "rtos", "free dos", "no os", "ubuntu", "redos", "astra", "debian", "fedora"



            }



            return any(o in val_lower for o in known_os)







        # 25. Гарантия (Warranty)



        if attr_name == "warranty":



            m = re.search(r"(\d+)", val_lower)



            if m:



                w_num = int(m.group(1))



                if any(u in val_lower for u in ["мес", "month"]):



                    return 1 <= w_num <= 120



                if any(u in val_lower for u in ["год", "лет", "year"]):



                    return 1 <= w_num <= 10



            return any(u in val_lower for u in ["мес", "год", "лет", "month", "year"])







        return True







    @classmethod



    def normalize_color(cls, value: str) -> str:



        """Нормализует цвет через канонический словарь и унификацию е/ё."""



        if not value or not str(value).strip():



            return ""



        val = str(value).strip().lower().replace("ё", "е")



        try:



            from app.extractors.normalization.dictionaries import COLORS



            for c_alias, (c_canonical, _) in COLORS.items():



                if val == c_alias.lower().replace("ё", "е") or val == c_canonical.lower().replace("ё", "е"):



                    return c_canonical.lower().replace("ё", "е")



        except Exception:



            pass



        return val















    @classmethod



    def is_brand_model_compatible(cls, brand: str | None, model: str | None) -> bool:



        """



        Проверяет инвариант согласованности бренда и модели (защита от сквозного конфликта).



        Например, модель 'iPhone 15 Pro Max' недопустима для бренда 'Xiaomi' или 'Samsung'.



        """



        if not brand or not model:



            return True







        b_low = str(brand).strip().lower()



        m_low = str(model).strip().lower()







        # Asus эксклюзивные линейки



        if any(w in m_low for w in ["tuf gaming", "tuf", "rog", "zenbook", "vivobook"]):



            return b_low in {"asus", "асус"}







        # Apple эксклюзивные линейки



        if any(w in m_low for w in ["iphone", "ipad", "macbook", "airpods", "imac", "apple watch"]):



            return b_low in {"apple", "эппл", "эйпл"}







        # Samsung эксклюзивные линейки



        if (



            "galaxy" in m_low



            or "гэлакси" in m_low



            or bool(re.search(r"\b(?:galaxy|гэлакси|samsung|самсунг)\s+[szanmfe]\d{1,2}\b", m_low))



            or bool(re.search(r"\b[sz]\d{1,2}(?:\s*(?:ultra|plus|fe))\b", m_low))



        ):



            return b_low in {"samsung", "самсунг"}







        # Xiaomi / Poco / Redmi



        if any(w in m_low for w in ["poco", "redmi", "поко", "редми", "xiaomi", "сяоми", "redmibook"]):



            return b_low in {"xiaomi", "сяоми", "poco", "redmi", "поко", "редми"}







        # Google



        if "pixel" in m_low or "пиксель" in m_low:



            return b_low in {"google", "гугл"}







        # Honor



        if "honor" in m_low or "хонор" in m_low:



            return b_low in {"honor", "хонор", "huawei", "хуавей"}







        # Huawei



        if any(w in m_low for w in ["pura", "matepad", "matebook"]):



            return b_low in {"huawei", "хуавей"}







        # Lenovo



        if any(w in m_low for w in ["thinkpad", "ideapad", "legion"]):



            return b_low in {"lenovo", "леново"}







        # Acer



        if any(w in m_low for w in ["predator", "nitro", "aspire"]):



            return b_low in {"acer", "эйсер", "асер"}







        # Sony



        if any(w in m_low for w in ["xperia", "playstation", "bravia"]):



            return b_low in {"sony", "сони"}







        return True







