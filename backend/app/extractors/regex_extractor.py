from __future__ import annotations

import re
from typing import Iterable

from flashtext import KeywordProcessor

from app.extractors.base import Prediction
from app.extractors.normalization.dictionaries import BRANDS, COLORS
from app.extractors.normalization.units import UnitNormalizer
from app.extractors.sanity import AttributeSanityValidator

_u = UnitNormalizer()


class RegexExtractor:
    """
    Tier 1: FlashText + Regex.

    Атрибуты:
      • brand             — FlashText (словарь брендов)
      • color             — FlashText (словарь цветов с приоритетами)
      • memory_rom        — Regex + UnitNormalizer
      • memory_ram        — Regex + UnitNormalizer
      • screen_diagonal   — Regex + UnitNormalizer
      • battery           — Regex + UnitNormalizer
      • refresh_rate      — Regex + UnitNormalizer
      • resolution        — Regex
      • cpu               — Regex (паттерны) + канонизация
      • os                — Regex (словарь)
      • weight            — Regex + UnitNormalizer
      • power             — Regex + UnitNormalizer
      • volume            — Regex + UnitNormalizer
      • warranty          — Regex + UnitNormalizer
    """

    name = "regex"
    version = "1.2.0"

    # ---------- Guard-паттерны (контекстные фильтры отрицаний, сравнений и лимитов) ----------
    _NEGATION_PREFIX_RE = re.compile(
        r"\b(?:не|нет|вместо|нежели|чем|кроме|не\s+путать\s+с|забудьте\s+про|без|в\s+отличие\s+от|отличие\s+от|отличн\w*\s+от|компактнее\w*|меньше\w*|не\s+прид[её]тся)\s+[^.,!;()]{0,45}$",
        re.IGNORECASE,
    )
    _NEGATION_SUFFIX_RE = re.compile(
        r"^\s*(?:не\s+поддержива\w*|не\s+установлен\w*|не\s+входит\s+в|отсутству\w*|нет\b)",
        re.IGNORECASE,
    )
    _UPGRADE_LIMIT_RE = re.compile(
        r"\b(?:до|максимальн\w*|расширен\w*|поддержк\w*|слот\w*|карт\w*\s+памят\w*|флешк\w*|micro\s*sd|microsd|суммарн\w*(?:\s+\w+)?\s+до|вплоть\s+до)\s+[^.,!;()]{0,35}$",
        re.IGNORECASE,
    )
    _COMPETITOR_PREFIX_RE = re.compile(
        r"\b(?:не\s+уступает|лучше(?:\s+чем)?|в\s+отличие\s+от|рвет\s+в\s+клочья|убийца|против|сравним\w*\s+с|аналог\w*|не\s+путать\s+с)\s+[^.,!;()]{0,45}$",
        re.IGNORECASE,
    )
    _ACCESSORY_PREFIX_RE = re.compile(
        r"\b(?:чех(?:ол|ла|ле|лом)|стекл(?:о|а|ом|е)|пл[её]нк\w*|ремеш(?:ок|ка|ком)|футляр\w*|насадк\w*|кабел\w*|адаптер\w*|в\s+подарок|подарочн\w*|пауэрбанк\w*|павербанк\w*|повербанк\w*|power\s*bank\w*|внешн\w*\s+аккумулятор\w*)\s+(?:на\s+)?[^.,!;()]{0,35}$",
        re.IGNORECASE,
    )
    _RECOMMENDATION_PREFIX_RE = re.compile(
        r"\b(?:рекомендуется|рекомендован\w*|совместим\w*|поддерживает|возможн\w*\s+установк\w*|опциональн\w*)\s+[^.,!;()]{0,35}$",
        re.IGNORECASE,
    )

    # ---------- Regex-паттерны характеристик ----------

    _ROM_RE = re.compile(
        r"(?:rom|встроенн\w*\s+памят\w*|накопит\w*|storage|память\s+пользователя|ssd|hdd|emmc|ufs(?:\s*\d\.\d)?)?"
        r"\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(тб|tb|гб|gb|терабайт\w*|гигабайт\w*)\b",
        re.IGNORECASE,
    )
    _ROM_WORD_RE = re.compile(
        r"(?:накопит\w*|памят\w*|диск\w*|хранилищ\w*|объем\w*|емкост\w*)?\s*(?:на\s+)?(полтерабайта|терабайт\w*|полтора\s+терабайта|два\s+терабайта)\b",
        re.IGNORECASE,
    )
    _ROM_WORD_MAP: dict[str, str] = {
        "полтерабайта": "512 ГБ",
        "терабайт": "1 ТБ",
        "терабайта": "1 ТБ",
        "терабайтов": "1 ТБ",
        "полтора терабайта": "1.5 ТБ",
        "два терабайта": "2 ТБ",
    }
    _RAM_DDR_RE = re.compile(
        r"\b(\d{1,3})\s*(?:гб|gb)?\s*(?:ddr[345][x]?|lpddr[45][x]?)\b",
        re.IGNORECASE,
    )
    _RAM_RE = re.compile(
        r"(?:ram|озу|оператив\w*(?:(?:\s+[\w\-]+){0,7}?\s*(?:памят\w*|модул\w*|объем\w*|емкост\w*))?)\s*[:=\-—–]?\s*(?:объем\w*\s*[:=]?\s*)?(\d+(?:[.,]\d+)?)\s*(гб|gb|гигабайт\w*)\b",
        re.IGNORECASE,
    )
    _RAM_RE2 = re.compile(
        r"(\d+(?:[.,]\d+)?)\s*(?:гб|gb|гигабайт\w*)\s*(?:ram|озу|оператив\w*)\b",
        re.IGNORECASE,
    )
    _SLASH_MEM_RE = re.compile(
        r"(?<![a-zA-Zа-яА-ЯёЁ0-9])(\d{1,4})\s*(?:гб|gb)?\s*/\s*(\d{1,4})\s*(?:гб|gb)?\b",
        re.IGNORECASE,
    )
    _LOAD_CAPACITY_RE = re.compile(
        r"(?:загрузк\w*|максимальн\w*\s+загрузк\w*|вместимост\w*)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:кг|kg)\b",
        re.IGNORECASE,
    )
    _SPIN_SPEED_RE = re.compile(
        r"(?:скорост\w*\s+отжим\w*|отжим\w*)\s*[:=]?\s*(\d{3,4})\s*(?:об/?мин|rpm)\b",
        re.IGNORECASE,
    )

    # Контекстные маркеры цвета и материала (full_text уже в lower)
    _COLOR_PREFIX_RE = re.compile(
        r"(?:(?:в|во)\s+)?(?:цвет[еа]?|оттенк[еа]|color)(?:\s+корпуса)?\s*[:=-]?\s*(?:(?:сочный|яркий|глубокий|матовый|глянцевый|темный|тёмный|светлый)\s+)?$",
        re.IGNORECASE,
    )
    _COLOR_SUFFIX_RE = re.compile(
        r"^\s*(?:цвета|цвете|оттенка|color)\b",
        re.IGNORECASE,
    )
    _MATERIAL_PREFIX_RE = re.compile(
        r"(?:(?:сделан|выполнен|изготовлен)\s+(?:полностью\s+)?из|корпус(?:\s+устройства)?\s+из|материал(?:\s+корпуса)?\s*[:=-]?\s*(?:из)?)\s*$",
        re.IGNORECASE,
    )

    _GPU_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\b((?:nvidia\s+)?geforce\s+rtx\s+\d{4}(?:\s*(?:ti|super))?(?:\s+для\s+ноутбуков)?(?:\s+\d+\s*(?:гб|gb))?)\b", re.IGNORECASE),
        re.compile(r"\b((?:nvidia\s+)?geforce\s+gtx\s+\d{3,4}(?:\s*(?:ti|super))?)\b", re.IGNORECASE),
        re.compile(r"\b(rtx\s+\d{4}(?:\s*(?:ti|super))?)\b", re.IGNORECASE),
        re.compile(r"\b(radeon\s+rx\s+\d{4}\s*[a-z]*)\b", re.IGNORECASE),
        re.compile(r"\b(intel\s+(?:iris\s+xe|arc\s+[a-z]\d{3}|uhd\s+graphics))\b", re.IGNORECASE),
        re.compile(r"\b(apple\s+m\d+\s+(?:pro|max|ultra)\s+gpu)\b", re.IGNORECASE),
    ]

    _MODEL_PATTERNS = [
        re.compile(r"\b(iphone\s+(?:se|\d{1,2}(?:\s*(?:pro\s*max|pro|plus|mini))?))\b", re.IGNORECASE),
        re.compile(r"\b((?:galaxy|гэлакси)\s+[szanmfe]\d{1,2}[a-z]?(?:\s*(?:ultra|plus|\+|fe|pro|5g))?)\b", re.IGNORECASE),
        re.compile(r"\b([szanmfe]\d{1,2}[a-z]?(?:\s*(?:ultra|plus|\+|fe|pro|5g)))\b", re.IGNORECASE),
        re.compile(r"(?:samsung|самсунг)\s+([a-zа-я]\d{2}[a-zа-я]?(?:\s*(?:5g|5г|ultra|plus|fe))?)", re.IGNORECASE),
        re.compile(r"\b(redmi(?:\s+note)?\s+\d{1,2}[a-z]?(?:\s*(?:pro\s*\+|pro|plus|\+|s|turbo))?)\b", re.IGNORECASE),
        re.compile(r"\b(poco\s+[xfmc]\d{1,2}[a-z]?(?:\s*(?:pro|gt))?(?:\s*5g)?)\b", re.IGNORECASE),
        re.compile(r"\b(tuf\s+gaming\s+[a-z]\d{2}(?:\s+[a-z0-9\-]+)?)\b", re.IGNORECASE),
        re.compile(r"\b(rog\s+(?:strix|zephyrus)\s+[a-z]\d{2}(?:\s+[a-z0-9\-]+)?)\b", re.IGNORECASE),
        re.compile(r"\b(zenbook(?:\s+(?:pro|duo|flip|s))?\s+\d{2}[a-z]?(?:\s+[a-z0-9\-]+)?)\b", re.IGNORECASE),
        re.compile(r"\b(vivobook(?:\s+(?:pro|s|flip))?\s+\d{2}[a-z]?(?:\s+[a-z0-9\-]+)?)\b", re.IGNORECASE),
        re.compile(r"\b(thinkpad\s+[a-z]\d{2}[a-z]?(?:\s+gen\s+\d+)?)\b", re.IGNORECASE),
        re.compile(r"\b(ideapad(?:\s+(?:gaming|slim|pro|flex))?\s+\d{1,2}[a-z]?(?:\s+[a-z0-9\-]+)?)\b", re.IGNORECASE),
        re.compile(r"\b(legion\s+(?:pro\s+)?\d{1,2}[a-z]?(?:\s+[a-z0-9\-]+)?)\b", re.IGNORECASE),
        re.compile(r"\b(nitro\s+\d{1,2}(?:\s+[a-z0-9\-]+)?)\b", re.IGNORECASE),
        re.compile(r"\b(aspire\s+\d{1,2}(?:\s+[a-z0-9\-]+)?)\b", re.IGNORECASE),
        re.compile(r"\b(macbook\s+(?:air|pro)(?:\s+\d{1,2}(?:[.,]\d)?)?)\b", re.IGNORECASE),
        re.compile(r"\b(gt\s+(?:neo\s*)?\d+[a-z]?(?:\s*(?:pro|ultra|explorer))?)\b", re.IGNORECASE),
        re.compile(r"\b(edge\s+\d{1,2}[a-z]?(?:\s*(?:pro|plus|fusion|ultra|neo))?)\b", re.IGNORECASE),
        re.compile(r"\b(xperia\s+(?:\d{1,2}|[ivx]+)(?:\s+[ivx\d]+)?(?:\s*(?:pro|plus))?)\b", re.IGNORECASE),
        re.compile(r"\b(p\d{2}(?:\s*(?:pro\s*\+|pro|art|pocket))?)\b", re.IGNORECASE),
        re.compile(r"\b(pura\s+\d{2}(?:\s*(?:pro\s*\+|pro|ultra))?)\b", re.IGNORECASE),
        re.compile(r"\b(mate\s+\d{2}(?:\s*(?:pro\s*\+|pro|rs|x\d?))?)\b", re.IGNORECASE),
        re.compile(r"\b(nova\s+\d{1,2}[a-z]?(?:\s*(?:pro|se|i|y))?)\b", re.IGNORECASE),
        re.compile(r"\b((?:hot|нот|note|zero|smart|смарт)\s+\d{1,2}[a-z]?(?:\s*(?:pro|play|vip|plus|про|плюс))?)\b", re.IGNORECASE),
        re.compile(r"\b(oneplus\s+(?:\d{1,2}[a-z]?|nord(?:\s+(?:ce|\d+|n\d+))?)(?:\s*(?:pro|r|open))?)\b", re.IGNORECASE),
        re.compile(r"\b(pixel\s+\d{1,2}[a-z]?(?:\s*(?:pro(?:\s*xl)?|a))?)\b", re.IGNORECASE),
    ]
    # Экран: 6.7", 6.7 дюйма, 6,7 ″, 6,4-дюймовым, диагональ — 50 дюймов
    _SCREEN_RE = re.compile(
        r"(?:диагонал\w*|экран\w*)?\s*[:=\-—–]?\s*"
        r"(\d+(?:[.,]\d+)?)\s*[-–—]?\s*(?:\"|″|”|дюйм\w*|inch(?:es)?\b)",
        re.IGNORECASE,
    )
    # Батарея: 4422 мАч, 5000 мА*ч, 5000mAh, 3355 мА⋅ч, батарея — 4422 мач
    _BATTERY_RE = re.compile(
        r"(?:батаре\w*|аккумулятор\w*|ёмкост\w*\s+батаре\w*)?\s*[:=\-—–]?\s*"
        r"(\d{3,6}(?:[.,]\d+)?)\s*(?:мА[·⋅•*.\-\s]?ч|mAh|mah)\b",
        re.IGNORECASE,
    )
    # Батарея с контекстом без обязательной единицы: аккум 5000, батарея 5000, акб 5000
    _BATTERY_CTX_RE = re.compile(
        r"(?:батаре\w*|аккумулятор\w*|аккум\w*|акб|ёмкост\w*(?:\s+батаре\w*|\s+акб|\s+аккум\w*)?)\s*[:=\-—–]?\s*"
        r"(\d{3,5})\s*(?:мА[·⋅•*.\-\s]?ч|mAh|mah)?\b",
        re.IGNORECASE,
    )
    _REFRESH_RE = re.compile(r"(\d{2,4})\s*(?:гц|hz)\b")
    _RES_RE = re.compile(r"\b(\d{3,4})\s*[x×]\s*(\d{3,4})\b")


    # --- новые ---

    # Вес с контекстом (вес/масса/weight)
    _WEIGHT_CTX_RE = re.compile(
        r"(?:вес\w*|масс\w*|weight)\s*[:=]?\s*"
        r"(\d+(?:[.,]\d+)?)\s*"
        r"(кг|kg|килограмм\w*|гр|грамм\w*|gr|г|g)\b"
    )
    # Вес без контекста — только килограммы (явный маркер массы)
    _WEIGHT_KG_RE = re.compile(
        r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:кг|kg|килограмм\w*)\b"
    )
    # Вес без контекста — граммы (только явные обозначения граммов, защита от 5g/4g)
    _WEIGHT_G_RE = re.compile(
        r"(?<!\d)(?<![2-5])(\d{1,4}(?:[.,]\d+)?)\s*(?:гр|грамм\w*|gr|г)\b"
    )

    # Мощность: 1500 Вт, 1.5 кВт, 500w
    _POWER_RE = re.compile(
        r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(квт|kw|вт|w|ватт\w*)\b"
    )

    # Объём: 1.7 л, 500 мл, 2l
    _VOLUME_RE = re.compile(
        r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(мл|ml|л|l|литр\w*)\b"
    )

    # Гарантия: только с ключевым словом, иначе "12 месяцев" — что угодно
    _WARRANTY_RE = re.compile(
        r"(?:гаранти\w*|warranty)\s*[:=]?\s*"
        r"(\d+)\s*(мес\w*|month\w*|год\w*|лет|года|year\w*)"
    )

    # CPU-паттерны: (regex, base_confidence). Идём по порядку,
    # берём первое совпадение. Специфичные — выше.
    _CPU_PATTERNS: list[tuple[re.Pattern[str], float]] = [
        (re.compile(r"\bsnapdragon\s+\d+\+?(?:\s+gen\s+\d+)?(?:\s+(?:plus|\+|ultra|pro))?\b"), 0.94),
        (re.compile(r"\bmediatek\s+dimensity\s+\d+\b"), 0.94),
        (re.compile(r"\bdimensity\s+\d+\b"), 0.90),
        (re.compile(r"\bexynos\s+\d+\b"), 0.93),
        (re.compile(r"\bkirin\s+\d+\b"), 0.93),
        (re.compile(r"\b(?:apple\s+|чип\s+|процессор\s+|chip\s+)a\d{1,2}(?:\s*(?:pro|bionic|max))?\b"), 0.95),
        (re.compile(r"\ba\d{1,2}\s+(?:pro|bionic|max)\b"), 0.94),
        (re.compile(r"\bapple\s+m\d+(?:\s+(?:pro|max|ultra))?\b"), 0.95),
        (re.compile(r"\bm\d+\s+(?:pro|max|ultra)\b"), 0.90),
        (re.compile(r"\bintel\s+core\s+i[3579](?:-\d+\w*)?\b"), 0.95),
        (re.compile(r"\bcore\s+i[3579](?:-\d+\w*)?\b"), 0.90),
        (re.compile(r"\bryzen\s+\d+(?:\s+\w+)?\b"), 0.92),
        (re.compile(r"\bceleron\s+\w+\b"), 0.89),
        (re.compile(r"\bpentium\s+\w+\b"), 0.89),
    ]

    # Словарь канонизации токенов CPU
    _CPU_CANON = {
        "snapdragon": "Snapdragon",
        "mediatek": "MediaTek",
        "dimensity": "Dimensity",
        "exynos": "Exynos",
        "kirin": "Kirin",
        "apple": "Apple",
        "intel": "Intel",
        "core": "Core",
        "ryzen": "Ryzen",
        "celeron": "Celeron",
        "pentium": "Pentium",
        "bionic": "Bionic",
        "gen": "Gen",
        "pro": "Pro",
        "max": "Max",
        "ultra": "Ultra",
    }

    # Операционные системы. Ключи — lower.
    _OS_MAP: dict[str, str] = {
        "без ос": "Без ОС",
        "без операционной системы": "Без ОС",
        "без предустановленной операционной системы": "Без ОС",
        "no os": "Без ОС",
        "without os": "Без ОС",
        "freedos": "FreeDOS",
        "free dos": "FreeDOS",
        "dos": "DOS",
        "не установлена": "Без ОС",
        "android": "Android",
        "андроид": "Android",
        "ios": "iOS",
        "иос": "iOS",
        "ipados": "iPadOS",
        "windows": "Windows",
        "виндовс": "Windows",
        "macos": "macOS",
        "макос": "macOS",
        "linux": "Linux",
        "линукс": "Linux",
        "harmonyos": "HarmonyOS",
        "harmony os": "HarmonyOS",
        "tizen": "Tizen",
        "webos": "webOS",
        "chromeos": "ChromeOS",
        "chrome os": "ChromeOS",
        "ubuntu": "Ubuntu",
        "redos": "RedOS",
        "astra linux": "Astra Linux",
    }

    # ---------- Конструктор ----------

    def __init__(
        self,
        brands: dict[str, str] | None = None,
        colors: dict[str, tuple[str, int]] | None = None,
    ):
        try:
            from app.services.brand_registry import BrandRegistry
            registry_brands = BrandRegistry.get_instance().brands
        except Exception as e:
            logger.debug("BrandRegistry not available during RegexExtractor init: %s", e)
            registry_brands = None

        self._brands: dict[str, str] = brands or registry_brands or BRANDS
        self._colors: dict[str, tuple[str, int]] = colors or COLORS

        self._brand_kp = KeywordProcessor(case_sensitive=False)
        for alias, canon in self._brands.items():
            self._brand_kp.add_keyword(alias, canon)

        # Предкомпилированные паттерны для цветов (границы без \b,
        # чтобы работало с кириллицей)
        self._color_patterns: list[tuple[re.Pattern[str], str, int, str]] = []
        for alias, (canon, prio) in self._colors.items():
            pat = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)")
            self._color_patterns.append((pat, canon, prio, alias))

        # Предкомпилированные паттерны для ОС
        self._os_patterns: list[tuple[re.Pattern[str], str]] = [
            (re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)"), canon)
            for alias, canon in self._OS_MAP.items()
        ]

        # Подписка на динамическое пополнение брендов на лету
        try:
            from app.services.brand_registry import BrandRegistry
            BrandRegistry.get_instance().subscribe(self._on_new_brand)
        except Exception as e:
            logger.debug("Could not subscribe to BrandRegistry: %s", e)


    def _on_new_brand(self, alias: str, canon: str) -> None:
        """Слушатель: мгновенно обогащает FlashText при регистрации нового бренда."""
        self._brands[alias] = canon
        self._brand_kp.add_keyword(alias, canon)

    # ================== публичный API ==================

    def health(self) -> bool:
        return True

    def get_info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "brands_count": len(self._brands),
            "colors_count": len(self._colors),
            "status": "ready",
        }

    def _is_negated_or_filtered(
        self,
        text: str,
        start_pos: int,
        end_pos: int | None = None,
        check_upgrade: bool = False,
        check_accessory: bool = False,
        check_recommendation: bool = False,
    ) -> bool:
        """
        Проверяет контекст перед вхождением и после него на наличие отрицаний, сравнений с конкурентами,
        лимитов апгрейда (до N ГБ), аксессуаров и рекомендаций ОС.

        Правило изоляции: контекстное окно не пересекает границы скобок '(', ')', '[', ']',
        а также знаков препинания (., !, ?, ;, :) справа и слева от найденного значения,
        чтобы комментарии в скобках или соседние предложения не отменяли валидные характеристики.
        """
        raw_prefix = text[max(0, start_pos - 60):start_pos].lower()
        prefix_parts = re.split(r"[()[\]{}.,!;?]", raw_prefix)
        prefix = prefix_parts[-1] if prefix_parts else raw_prefix

        if self._NEGATION_PREFIX_RE.search(prefix):
            return True
        if self._COMPETITOR_PREFIX_RE.search(prefix):
            return True
        if check_upgrade and self._UPGRADE_LIMIT_RE.search(prefix):
            return True
        if check_accessory and self._ACCESSORY_PREFIX_RE.search(prefix):
            return True
        if check_recommendation and self._RECOMMENDATION_PREFIX_RE.search(prefix):
            return True

        if end_pos is not None:
            raw_suffix = text[end_pos:min(len(text), end_pos + 45)].lower()
            suffix_parts = re.split(r"[()[\]{}.,!;?]", raw_suffix)
            suffix = suffix_parts[0].strip() if suffix_parts else ""
            if suffix and self._NEGATION_SUFFIX_RE.search(suffix):
                return True

        return False

    def extract(self, card: dict, category_key: str = "default") -> list[Prediction]:
        title = (card.get("title") or "").strip()
        description = (card.get("description") or "").strip()
        title_lower = title.lower()
        desc_lower = description.lower()
        seller = card.get("seller_attributes") or {}
        seller_text = " ".join(f"{k} {v}".lower() for k, v in seller.items())
        full_text = f"{title_lower}\n{desc_lower}\n{seller_text}"

        out: list[Prediction] = []
        seen_attrs: set[str] = set()

        if (brand := self._find_brand(title_lower, desc_lower, seller)):
            out.append(brand)
            seen_attrs.add("brand")

        if (color := self._find_color(full_text, seller, title=title_lower)):
            out.append(color)
            seen_attrs.add("color")

        # 1. Поиск модели СТРОГО в названии товара (Title First)
        if title:
            for pat in self._MODEL_PATTERNS:
                for m in pat.finditer(title):
                    if not self._is_negated_or_filtered(title, m.start()):
                        val = self._canon_model(m.group(1).strip())
                        out.append(Prediction(
                            attribute="model",
                            value=val,
                            confidence=0.96,
                            source="regex",
                            raw=m.group(0).strip(),
                        ))
                        seen_attrs.add("model")
                        break
                if "model" in seen_attrs:
                    break

        # 2. Если модель не найдена в названии — ищем в описании с защитой от конкурентов
        if "model" not in seen_attrs and description:
            for pat in self._MODEL_PATTERNS:
                for m in pat.finditer(description):
                    if not self._is_negated_or_filtered(description, m.start()):
                        val = self._canon_model(m.group(1).strip())
                        out.append(Prediction(
                            attribute="model",
                            value=val,
                            confidence=0.90,
                            source="regex",
                            raw=m.group(0).strip(),
                        ))
                        seen_attrs.add("model")
                        break
                if "model" in seen_attrs:
                    break

        # 3. Приоритетное извлечение спецификаций из заголовка (Title First)
        if title_lower:
            for pred in self._find_numeric(title_lower, title_lower, category_key=category_key, is_title=True):
                if pred["attribute"] not in seen_attrs:
                    out.append(pred)
                    seen_attrs.add(pred["attribute"])

        # 4. Добор недостающих характеристик из полного текста
        for pred in self._find_numeric(full_text, title_lower, category_key=category_key, is_title=False):
            if pred["attribute"] not in seen_attrs:
                out.append(pred)
                seen_attrs.add(pred["attribute"])

        # Физическая валидация здравого смысла и контекста категории
        valid_out: list[Prediction] = []
        for p in out:
            if AttributeSanityValidator.is_valid(p["attribute"], p["value"], category_key):
                if "grounded" not in p:
                    p["grounded"] = True
                p["confidence"] = round(p["confidence"], 4)
                valid_out.append(p)
        return valid_out

    # ================== FlashText-хелперы ==================

    def _find_brand(self, title, description, seller):
        for k in ("brand", "бренд", "производитель", "vendor"):
            v = seller.get(k)
            if not v:
                continue
            key = str(v).lower().strip()
            canon = self._brands.get(key, str(v))
            return Prediction(attribute="brand", value=canon,
                              confidence=0.98, source="flashtext", raw=str(v))

        hits_title = self._brand_kp.extract_keywords(title)
        hits_desc = self._brand_kp.extract_keywords(description)
        hits = hits_title or hits_desc
        if hits:
            canon = hits[0]
            conf = 0.95 if hits_title else 0.88
            return Prediction(attribute="brand", value=canon,
                              confidence=conf, source="flashtext", raw=canon)
        return None

    def _find_color(self, full_text: str, seller: dict, title: str = "") -> Prediction | None:
        for k in ("color", "цвет"):
            v = seller.get(k)
            if v:
                key = str(v).lower().strip()
                canon, _prio = self._colors.get(key, (key, 0))
                return Prediction(attribute="color", value=canon,
                                  confidence=0.95, source="flashtext", raw=str(v))

        # 1. Поиск цвета СТРОГО в заголовке товара (Title First)
        if title:
            best_title: tuple[int, str, str] | None = None
            for pat, canon, prio, alias in self._color_patterns:
                for m in pat.finditer(title):
                    start, end = m.span()
                    if self._is_negated_or_filtered(title, start, check_accessory=True):
                        continue
                    prefix = title[max(0, start - 30):start]
                    suffix = title[end:min(len(title), end + 30)]
                    effective_prio = prio + 200
                    if self._COLOR_PREFIX_RE.search(prefix) or self._COLOR_SUFFIX_RE.search(suffix):
                        effective_prio += 500
                    if self._MATERIAL_PREFIX_RE.search(prefix):
                        effective_prio -= 300
                    if effective_prio > 0:
                        if best_title is None or effective_prio > best_title[0]:
                            best_title = (effective_prio, canon, alias)
            if best_title:
                _prio, canon, alias = best_title
                conf = min(0.96, 0.90 + (_prio / 1000.0))
                return Prediction(attribute="color", value=canon,
                                  confidence=round(conf, 4), source="flashtext", raw=alias)

        # 2. Поиск цвета в полном тексте (с жесткой защитой от чехлов, подарков и конкурентов)
        best: tuple[int, str, str] | None = None
        for pat, canon, prio, alias in self._color_patterns:
            for m in pat.finditer(full_text):
                start, end = m.span()
                if self._is_negated_or_filtered(full_text, start, check_accessory=True):
                    continue

                prefix = full_text[max(0, start - 40):start]
                suffix = full_text[end:min(len(full_text), end + 40)]

                effective_prio = prio

                # Явный контекст цвета ("в черном цвете", "цвет: черный", "цвет корпуса: сочный желтый")
                if self._COLOR_PREFIX_RE.search(prefix) or self._COLOR_SUFFIX_RE.search(suffix):
                    effective_prio += 500

                # Контекст материала корпуса
                if self._MATERIAL_PREFIX_RE.search(prefix):
                    effective_prio -= 300

                if effective_prio > 0:
                    if best is None or effective_prio > best[0]:
                        best = (effective_prio, canon, alias)

        if best:
            _prio, canon, alias = best
            conf = min(0.96, 0.90 + (_prio / 1000.0))
            return Prediction(attribute="color", value=canon,
                              confidence=round(conf, 4), source="flashtext", raw=alias)
        return None


    # ================== Regex-хелперы ==================

    def _find_numeric(self, text: str, title: str, category_key: str = "default", is_title: bool = False) -> Iterable[Prediction]:
        # --- Память через слэш (например, 8/256 или 12/512GB в названии или тексте) ---
        slash_match = self._SLASH_MEM_RE.search(text)
        slash_ram = None
        slash_rom = None
        slash_span: tuple[int, int] | None = None
        if slash_match and not self._is_negated_or_filtered(text, slash_match.start(), check_upgrade=True):
            try:
                v1 = int(slash_match.group(1))
                v2 = int(slash_match.group(2))
                ram_val = min(v1, v2)
                rom_val = max(v1, v2)
                if ram_val in (3, 4, 6, 8, 12, 16, 24, 32, 48, 64) and rom_val in (16, 32, 64, 128, 256, 512, 1024, 2048):
                    slash_span = slash_match.span()
                    slash_ram = Prediction(
                        attribute="memory_ram",
                        value=_u.memory(str(ram_val), "ГБ"),
                        confidence=self._conf(0.95, slash_match.group(0), title),
                        source="regex",
                        raw=slash_match.group(0).strip(),
                    )
                    slash_rom = Prediction(
                        attribute="memory_rom",
                        value=_u.memory(str(rom_val), "ГБ"),
                        confidence=self._conf(0.95, slash_match.group(0), title),
                        source="regex",
                        raw=slash_match.group(0).strip(),
                    )
            except (ValueError, TypeError, IndexError) as e:
                logger.debug("Slash memory parsing error: %s", e)

        # --- RAM (перед ROM, чтобы «8 гб озу», «16гб ddr5» или «12 гигабайт оперативки» не ушли в rom) ---
        ram_pred = None
        ram_span: tuple[int, int] | None = None

        # 1. RAM со стандартом памяти (16ГБ DDR5, 8GB LPDDR4X)
        for m in self._RAM_DDR_RE.finditer(text):
            if not self._is_negated_or_filtered(text, m.start(), check_upgrade=True):
                ram_span = m.span()
                ram_pred = Prediction(
                    attribute="memory_ram",
                    value=_u.memory(m.group(1), "ГБ"),
                    confidence=self._conf(0.96, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )
                break

        # 2. RAM с суффиксом (12 гигабайт оперативки, 16 gb ram)
        if not ram_pred:
            for m in self._RAM_RE2.finditer(text):
                if not self._is_negated_or_filtered(text, m.start(), check_upgrade=True):
                    ram_span = m.span()
                    ram_pred = Prediction(
                        attribute="memory_ram",
                        value=_u.memory(m.group(1), "ГБ"),
                        confidence=self._conf(0.94, m.group(0), title),
                        source="regex", raw=m.group(0).strip(),
                    )
                    break

        # 3. RAM с префиксом (ОЗУ 16 ГБ, оперативная память: 8 гб)
        if not ram_pred:
            for m in self._RAM_RE.finditer(text):
                if not self._is_negated_or_filtered(text, m.start(), check_upgrade=True):
                    ram_span = m.span()
                    ram_pred = Prediction(
                        attribute="memory_ram",
                        value=_u.memory(m.group(1), m.group(2) if "т" in m.group(2).lower() else "ГБ"),
                        confidence=self._conf(0.93, m.group(0), title),
                        source="regex", raw=m.group(0).strip(),
                    )
                    break

        if ram_pred:
            yield ram_pred
        elif slash_ram:
            yield slash_ram

        # --- ROM (Встроенная память / SSD / Накопитель) ---
        found_rom = False

        # 1. Словесные накопители («полтерабайта», «терабайт», «полтора терабайта»)
        for m in self._ROM_WORD_RE.finditer(text):
            if self._is_negated_or_filtered(text, m.start(), check_upgrade=True):
                continue
            w_key = m.group(1).lower().strip()
            canon_val = None
            for wk, cv in self._ROM_WORD_MAP.items():
                if wk in w_key:
                    canon_val = cv
                    break
            if canon_val:
                yield Prediction(
                    attribute="memory_rom",
                    value=canon_val,
                    confidence=self._conf(0.94, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )
                found_rom = True
                break

        # 2. Числовые накопители (SSD 512ГБ, ROM 256GB, 128 ГБ)
        if not found_rom:
            for m in self._ROM_RE.finditer(text):
                if ram_span and self._overlaps(m.span(), ram_span):
                    continue
                if slash_span and self._overlaps(m.span(), slash_span):
                    continue
                if self._is_negated_or_filtered(text, m.start(), check_upgrade=True):
                    continue
                prefix_start = max(ram_span[1] if ram_span and m.start() >= ram_span[1] else 0, m.start() - 20)
                prefix = text[prefix_start:m.start()].lower()
                suffix = text[m.end():min(len(text), m.end() + 15)].lower()

                # Отсеиваем RAM (если ddr или ram непосредственно перед/после числа)
                if re.search(r"\b(?:озу|ram|оператив\w*)\s*[:=]?\s*$", prefix):
                    continue
                if re.search(r"^\s*(?:ddr\d|lpddr\d|ram|озу|оператив\w*)", suffix):
                    continue

                val = _u.memory(m.group(1), m.group(2))
                # Проверка здравого смысла: если категория известна и значение невалидно, ищем дальше
                if category_key and not AttributeSanityValidator.is_valid("memory_rom", val, category_key):
                    continue

                yield Prediction(
                    attribute="memory_rom",
                    value=val,
                    confidence=self._conf(0.92, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )
                found_rom = True
                break

        if not found_rom and slash_rom:
            yield slash_rom

        # --- Экран ---
        for m in self._SCREEN_RE.finditer(text):
            if self._is_negated_or_filtered(text, m.start()):
                continue
            try:
                num = float(m.group(1).replace(",", "."))
                if 3 <= num <= 120:
                    yield Prediction(
                        attribute="screen_diagonal",
                        value=_u.screen_diagonal(m.group(1)),
                        confidence=self._conf(0.92, m.group(0), title),
                        source="regex", raw=m.group(0).strip(),
                    )
                    break
            except ValueError:
                pass

        # --- Батарея ---
        found_battery = False
        check_battery_acc = (category_key != "powerbanks")
        for m in self._BATTERY_RE.finditer(text):
            if not self._is_negated_or_filtered(text, m.start(), end_pos=m.end(), check_accessory=check_battery_acc):
                yield Prediction(
                    attribute="battery", value=_u.battery(m.group(1)),
                    confidence=self._conf(0.90, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )
                found_battery = True
                break

        if not found_battery:
            for m in self._BATTERY_CTX_RE.finditer(text):
                if not self._is_negated_or_filtered(text, m.start(), end_pos=m.end(), check_accessory=check_battery_acc):
                    mah = float(m.group(1).replace(",", "."))
                    if 400 <= mah <= 35000:
                        yield Prediction(
                            attribute="battery", value=_u.battery(m.group(1)),
                            confidence=self._conf(0.90, m.group(0), title),
                            source="regex", raw=m.group(0).strip(),
                        )
                        break

        # --- Частота ---
        for m in self._REFRESH_RE.finditer(text):
            if self._is_negated_or_filtered(text, m.start()):
                continue
            hz = int(m.group(1))
            if 30 <= hz <= 360:
                yield Prediction(
                    attribute="refresh_rate", value=_u.refresh_rate(m.group(1)),
                    confidence=self._conf(0.90, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )
                break

        # --- Разрешение ---
        found_res = False
        for m in self._RES_RE.finditer(text):
            if self._is_negated_or_filtered(text, m.start()):
                continue
            yield Prediction(
                attribute="resolution",
                value=_u.resolution(m.group(1), m.group(2)),
                confidence=self._conf(0.90, m.group(0), title),
                source="regex", raw=m.group(0).strip(),
            )
            found_res = True
            break

        if not found_res:
            for m in re.finditer(r"\b(?:4k|4к|ultra\s*hd|uhd)\b", text, flags=re.IGNORECASE):
                if not self._is_negated_or_filtered(text, m.start()):
                    yield Prediction(
                        attribute="resolution",
                        value="3840×2160",
                        confidence=self._conf(0.91, m.group(0), title),
                        source="regex", raw=m.group(0).strip(),
                    )
                    found_res = True
                    break

        if not found_res:
            for m in re.finditer(r"\b(?:8k|8к)\b", text, flags=re.IGNORECASE):
                if not self._is_negated_or_filtered(text, m.start()):
                    yield Prediction(
                        attribute="resolution",
                        value="7680×4320",
                        confidence=self._conf(0.91, m.group(0), title),
                        source="regex", raw=m.group(0).strip(),
                    )
                    found_res = True
                    break

        if not found_res:
            for m in re.finditer(r"\b(?:full\s*hd|fhd)\b", text, flags=re.IGNORECASE):
                if not self._is_negated_or_filtered(text, m.start()):
                    yield Prediction(
                        attribute="resolution",
                        value="1920×1080",
                        confidence=self._conf(0.90, m.group(0), title),
                        source="regex", raw=m.group(0).strip(),
                    )
                    found_res = True
                    break

        # --- Видеокарта (GPU) для ноутбуков и ПК ---
        for pat in self._GPU_PATTERNS:
            for m in pat.finditer(text):
                if not self._is_negated_or_filtered(text, m.start()):
                    val = self._canon_gpu(m.group(1).strip())
                    yield Prediction(
                        attribute="gpu",
                        value=val,
                        confidence=self._conf(0.95, m.group(0), title),
                        source="regex", raw=m.group(0).strip(),
                    )
                    break
            else:
                continue
            break

        # --- Вес ---
        found_weight = False
        for m in self._WEIGHT_CTX_RE.finditer(text):
            if not self._is_negated_or_filtered(text, m.start()):
                yield Prediction(
                    attribute="weight",
                    value=_u.weight(m.group(1), m.group(2)),
                    confidence=self._conf(0.93, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )
                found_weight = True
                break

        if not found_weight:
            for m in self._WEIGHT_KG_RE.finditer(text):
                if not self._is_negated_or_filtered(text, m.start()):
                    yield Prediction(
                        attribute="weight",
                        value=_u.weight(m.group(1), "кг"),
                        confidence=self._conf(0.89, m.group(0), title),
                        source="regex", raw=m.group(0).strip(),
                    )
                    found_weight = True
                    break

        if not found_weight:
            for m in self._WEIGHT_G_RE.finditer(text):
                if not self._is_negated_or_filtered(text, m.start()):
                    grams = float(m.group(1).replace(",", "."))
                    if grams <= 2000:
                        yield Prediction(
                            attribute="weight",
                            value=_u.weight(m.group(1), "г"),
                            confidence=self._conf(0.88, m.group(0), title),
                            source="regex", raw=m.group(0).strip(),
                        )
                        break

        # --- Мощность ---
        for m in self._POWER_RE.finditer(text):
            if not self._is_negated_or_filtered(text, m.start()):
                yield Prediction(
                    attribute="power", value=_u.power(m.group(1), m.group(2)),
                    confidence=self._conf(0.90, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )
                break

        # --- Объём ---
        for m in self._VOLUME_RE.finditer(text):
            if not self._is_negated_or_filtered(text, m.start()):
                yield Prediction(
                    attribute="volume", value=_u.volume(m.group(1), m.group(2)),
                    confidence=self._conf(0.89, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )
                break

        # --- Гарантия ---
        for m in self._WARRANTY_RE.finditer(text):
            if not self._is_negated_or_filtered(text, m.start()):
                yield Prediction(
                    attribute="warranty",
                    value=_u.warranty(m.group(1), m.group(2)),
                    confidence=0.92, source="regex", raw=m.group(0).strip(),
                )
                break

        # --- CPU ---
        if (m := self._find_cpu(text)):
            raw_match, base_conf = m
            yield Prediction(
                attribute="cpu",
                value=self._canon_cpu(raw_match.group(0)),
                confidence=self._conf(base_conf, raw_match.group(0), title),
                source="regex", raw=raw_match.group(0).strip(),
            )

        # --- OS ---
        if (m := self._find_os(text)):
            raw_text, canon = m
            yield Prediction(
                attribute="os", value=canon,
                confidence=0.92, source="regex", raw=raw_text,
            )

        # --- Загрузка стиральной машины ---
        for m in self._LOAD_CAPACITY_RE.finditer(text):
            if not self._is_negated_or_filtered(text, m.start()):
                yield Prediction(
                    attribute="load_capacity",
                    value=f"{float(m.group(1).replace(',', '.')):.1f} кг".replace(".0", ""),
                    confidence=self._conf(0.92, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )
                break

        # --- Скорость отжима ---
        for m in self._SPIN_SPEED_RE.finditer(text):
            if not self._is_negated_or_filtered(text, m.start()):
                yield Prediction(
                    attribute="spin_speed",
                    value=f"{m.group(1)} об/мин",
                    confidence=self._conf(0.92, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )
                break

    # ================== CPU / OS / GPU ==================

    def _find_cpu(self, text: str):
        for pat, conf in self._CPU_PATTERNS:
            for m in pat.finditer(text):
                if not self._is_negated_or_filtered(text, m.start()):
                    return m, conf
        return None

    def _canon_cpu(self, raw: str) -> str:
        """'snapdragon 8 gen 3' → 'Snapdragon 8 Gen 3', 'ryzen 7 7735hs' → 'Ryzen 7 7735HS', 'i7-12700h' → 'i7-12700H'."""
        raw = re.sub(r"^(?:чип|процессор|chip)\s+", "", raw.strip(), flags=re.IGNORECASE)

        def _format_token_part(part: str) -> str:
            low = part.lower()
            if low in self._CPU_CANON:
                return self._CPU_CANON[low]
            if re.fullmatch(r"m\d+", low):
                return "M" + low[1:]
            if re.fullmatch(r"a\d+", low):
                return "A" + low[1:]
            if re.fullmatch(r"i[3579]", low):
                return "i" + low[1:]
            m_suf = re.match(r"^(\d+)([a-zA-Z]{1,3})$", low)
            if m_suf:
                return f"{m_suf.group(1)}{m_suf.group(2).upper()}"
            if part.isalpha():
                return part.capitalize()
            return part

        out: list[str] = []
        for tok in raw.split():
            low = tok.lower()
            if low in self._CPU_CANON:
                out.append(self._CPU_CANON[low])
            elif "-" in tok:
                sub_parts = tok.split("-")
                out.append("-".join(_format_token_part(p) for p in sub_parts))
            else:
                out.append(_format_token_part(tok))
        return " ".join(out)

    @staticmethod
    def _canon_gpu(val: str) -> str:
        clean = re.sub(r"\s+для\s+ноутбуков.*$", "", val, flags=re.IGNORECASE).strip()
        clean = re.sub(r"\s+\d+\s*(?:гб|gb).*$", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"\bgeforce\b", "GeForce", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\brtx\b", "RTX", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bgtx\b", "GTX", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bnvidia\b", "NVIDIA", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bradeon\b", "Radeon", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\brx\b", "RX", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bti\b", "Ti", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\bsuper\b", "Super", clean, flags=re.IGNORECASE)
        return clean

    @staticmethod
    def _canon_model(val: str) -> str:
        """Нормализация написания моделей телефонов и ноутбуков."""
        val = val.strip()
        val = re.sub(r"^[аА](?=\d)", "A", val)
        val = re.sub(r"^[сС](?=\d)", "S", val)
        val = re.sub(r"5[гГ]\b", "5G", val)
        val = re.sub(r"\b5g\b", "5G", val, flags=re.IGNORECASE)
        val = re.sub(r"\bгэлакси\b", "Galaxy", val, flags=re.IGNORECASE)
        val = re.sub(r"\btuf\s+gaming\b", "TUF Gaming", val, flags=re.IGNORECASE)
        val = re.sub(r"\brog\b", "ROG", val, flags=re.IGNORECASE)
        words = val.split()
        fixed_words = []
        for w in words:
            low = w.lower()
            if low == "iphone":
                fixed_words.append("iPhone")
            elif low in {"galaxy", "redmi", "note", "edge", "xperia", "ultra", "plus", "pro", "max", "mini", "lite", "play", "neo", "turbo", "fusion", "gaming", "strix", "zephyrus", "zenbook", "vivobook", "macbook", "air", "thinkpad", "ideapad", "legion", "nitro", "aspire", "victus", "omen"}:
                fixed_words.append(low.capitalize())
            elif low in {"gt", "tuf", "rog"}:
                fixed_words.append(low.upper())
            elif low in {"vi", "iv", "v", "ii", "iii"}:
                fixed_words.append(low.upper())
            elif re.match(r"^[a-z]\d{1,2}[a-z]?$", low):
                fixed_words.append(low.upper())
            elif low in {"нот", "хот"}:
                fixed_words.append("HOT")
            else:
                fixed_words.append(w)
        return " ".join(fixed_words)

    def _find_os(self, text: str):
        """Возвращает (raw_match, canonical) или None."""
        # 1. Эксплицитное отсутствие ОС в тексте (наивысший приоритет)
        if re.search(r"\b(?:без\s+(?:предустановленной\s+)?(?:операционной\s+)?системы|без\s+ос|no\s+os|without\s+os|freedos|free\s*dos)\b", text, re.I):
            return "Без ОС", "Без ОС"

        best: tuple[int, str, str] | None = None
        for pat, canon in self._os_patterns:
            for m in pat.finditer(text):
                if self._is_negated_or_filtered(text, m.start(), check_recommendation=True):
                    continue
                length = m.end() - m.start()
                if best is None or length > best[0]:
                    best = (length, m.group(0), canon)
        if best:
            return best[1], best[2]
        return None

    # ================== утилиты ==================

    @staticmethod
    def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
        return not (a[1] <= b[0] or b[1] <= a[0])

    @staticmethod
    def _conf(base: float, raw: str, title: str) -> float:
        return round(min(0.99, base + (0.03 if raw and raw in title else 0.0)), 4)