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

    # ---------- Regex-паттерны ----------
    # Весь вход уже приведён к lower-case, re.IGNORECASE не нужен.

    _ROM_RE = re.compile(
        r"(?:rom|встроенн\w*\s+памят\w*|накопит\w*|storage|память\s+пользователя)?"
        r"\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(тб|tb|гб|gb)\b"
    )
    _RAM_RE = re.compile(
        r"(?:ram|озу|оператив\w*(?:(?:\s+[\w\-]+){0,7}?\s*(?:памят\w*|модул\w*|объем\w*|емкост\w*))?)\s*[:=\-—–]?\s*(?:объем\w*\s*[:=]?\s*)?(\d+(?:[.,]\d+)?)\s*(гб|gb)\b",
        re.IGNORECASE,
    )
    _RAM_RE2 = re.compile(
        r"(\d+(?:[.,]\d+)?)\s*(гб|gb)\s*(?:ram|озу|оператив\w*)\b"
    )
    _SLASH_MEM_RE = re.compile(
        r"(?<!\d)(\d{1,4})\s*(?:гб|gb)?\s*/\s*(\d{1,4})\s*(?:гб|gb)?\b",
        re.IGNORECASE,
    )

    _MODEL_PATTERNS = [
        re.compile(r"\b(iphone\s+(?:se|\d{1,2}(?:\s*(?:pro\s*max|pro|plus|mini))?))\b", re.IGNORECASE),
        re.compile(r"\b((?:galaxy|гэлакси)\s+[szanmfe]\d{1,2}[a-z]?(?:\s*(?:ultra|plus|\+|fe|pro|5g))?)\b", re.IGNORECASE),
        re.compile(r"\b([szanmfe]\d{1,2}[a-z]?(?:\s*(?:ultra|plus|\+|fe|pro|5g)))\b", re.IGNORECASE),
        re.compile(r"(?:samsung|самсунг)\s+([a-zа-я]\d{2}[a-zа-я]?(?:\s*(?:5g|5г|ultra|plus|fe))?)", re.IGNORECASE),
        re.compile(r"\b(redmi(?:\s+note)?\s+\d{1,2}[a-z]?(?:\s*(?:pro\s*\+|pro|plus|\+|s|turbo))?)\b", re.IGNORECASE),
        re.compile(r"\b(poco\s+[xfmc]\d{1,2}[a-z]?(?:\s*(?:pro|gt))?)\b", re.IGNORECASE),
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
    # Батарея: 4422 мАч, 5000 мА*ч, 5000mAh, батарея — 4422 мач
    _BATTERY_RE = re.compile(
        r"(?:батаре\w*|аккумулятор\w*|ёмкост\w*\s+батаре\w*)?\s*[:=\-—–]?\s*"
        r"(\d{3,6}(?:[.,]\d+)?)\s*(?:мА[·*.\-\s]?ч|mAh|mah)\b",
        re.IGNORECASE,
    )
    # Батарея с контекстом без обязательной единицы: аккум 5000, батарея 5000, акб 5000
    _BATTERY_CTX_RE = re.compile(
        r"(?:батаре\w*|аккумулятор\w*|аккум\w*|акб|ёмкост\w*(?:\s+батаре\w*|\s+акб|\s+аккум\w*)?)\s*[:=\-—–]?\s*"
        r"(\d{3,5})\s*(?:мА[·*.\-\s]?ч|mAh|mah)?\b",
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
        except Exception:
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
        except Exception:
            pass

    def _on_new_brand(self, alias: str, canon: str) -> None:
        """Слушатель: мгновенно обогащает FlashText при регистрации нового бренда."""
        self._brands[alias] = canon
        self._brand_kp.add_keyword(alias, canon)

    # ================== публичный API ==================

    def health(self) -> bool:
        return True

    def extract(self, card: dict, category_key: str = "default") -> list[Prediction]:
        title = (card.get("title") or "").lower()
        description = (card.get("description") or "").lower()
        seller = card.get("seller_attributes") or {}
        seller_text = " ".join(f"{k} {v}".lower() for k, v in seller.items())
        full_text = f"{title}\n{description}\n{seller_text}"

        out: list[Prediction] = []
        seen_attrs: set[str] = set()

        if (brand := self._find_brand(title, description, seller)):
            out.append(brand)
            seen_attrs.add("brand")

        if (color := self._find_color(full_text, seller)):
            out.append(color)
            seen_attrs.add("color")

        # Модель по известным флагманским паттернам
        search_model_text = f"{card.get('title') or ''} {card.get('description') or ''} {card.get('raw_text') or ''}".strip()
        for pat in self._MODEL_PATTERNS:
            if (m := pat.search(search_model_text)):
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

        for pred in self._find_numeric(full_text, title):
            if pred["attribute"] not in seen_attrs:
                out.append(pred)
                seen_attrs.add(pred["attribute"])

        # Физическая валидация здравого смысла и контекста категории
        return [
            p for p in out
            if AttributeSanityValidator.is_valid(p["attribute"], p["value"], category_key)
        ]

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

    def _find_color(self, full_text, seller):
        for k in ("color", "цвет"):
            v = seller.get(k)
            if v:
                key = str(v).lower().strip()
                canon, _prio = self._colors.get(key, (key, 0))
                return Prediction(attribute="color", value=canon,
                                  confidence=0.95, source="flashtext", raw=str(v))

        best: tuple[int, str, str] | None = None
        for pat, canon, prio, alias in self._color_patterns:
            if pat.search(full_text):
                if best is None or prio > best[0]:
                    best = (prio, canon, alias)

        if best:
            _prio, canon, alias = best
            conf = min(0.96, 0.90 + (_prio / 1000.0))
            return Prediction(attribute="color", value=canon,
                              confidence=round(conf, 2), source="flashtext", raw=alias)
        return None

    # ================== Regex-хелперы ==================

    def _find_numeric(self, text: str, title: str) -> Iterable[Prediction]:
        # --- Память через слэш (например, 8/256 или 12/512GB в названии или тексте) ---
        slash_match = self._SLASH_MEM_RE.search(title) or self._SLASH_MEM_RE.search(text)
        slash_ram = None
        slash_rom = None
        slash_span: tuple[int, int] | None = None
        if slash_match:
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
                        confidence=0.95,
                        source="regex",
                        raw=slash_match.group(0).strip(),
                    )
                    slash_rom = Prediction(
                        attribute="memory_rom",
                        value=_u.memory(str(rom_val), "ГБ"),
                        confidence=0.95,
                        source="regex",
                        raw=slash_match.group(0).strip(),
                    )
            except Exception:
                pass

        # --- RAM (перед ROM, чтобы «8 гб озу» или «оперативка 8 гб» не ушли в rom) ---
        ram_match = self._RAM_RE2.search(text) or self._RAM_RE.search(text)
        ram_span: tuple[int, int] | None = None
        if ram_match:
            ram_span = ram_match.span()
            yield Prediction(
                attribute="memory_ram",
                value=_u.memory(ram_match.group(1), ram_match.group(2)),
                confidence=self._conf(0.93, ram_match.group(0), title),
                source="regex", raw=ram_match.group(0).strip(),
            )
        elif slash_ram:
            yield slash_ram

        # --- ROM ---
        found_rom = False
        for m in self._ROM_RE.finditer(text):
            if ram_span and self._overlaps(m.span(), ram_span):
                continue
            if slash_span and self._overlaps(m.span(), slash_span):
                continue
            # отсеиваем мусор: если непосредственно перед числом идёт "озу"/"ram"/"оперативка"
            prefix_start = max(ram_span[1] if ram_span and m.start() >= ram_span[1] else 0, m.start() - 15)
            prefix = text[prefix_start:m.start()].lower()
            if re.search(r"\b(?:озу|ram|оператив\w*)\s*[:=]?\s*$", prefix):
                continue
            yield Prediction(
                attribute="memory_rom",
                value=_u.memory(m.group(1), m.group(2)),
                confidence=self._conf(0.92, m.group(0), title),
                source="regex", raw=m.group(0).strip(),
            )
            found_rom = True
            break
        if not found_rom and slash_rom:
            yield slash_rom


        # --- Экран ---
        if (m := self._SCREEN_RE.search(text)):
            try:
                num = float(m.group(1).replace(",", "."))
                if 3 <= num <= 120:
                    yield Prediction(
                        attribute="screen_diagonal",
                        value=_u.screen_diagonal(m.group(1)),
                        confidence=self._conf(0.92, m.group(0), title),
                        source="regex", raw=m.group(0).strip(),
                    )
            except ValueError:
                pass

        # --- Батарея ---
        if (m := self._BATTERY_RE.search(text)):
            yield Prediction(
                attribute="battery", value=_u.battery(m.group(1)),
                confidence=self._conf(0.90, m.group(0), title),
                source="regex", raw=m.group(0).strip(),
            )
        elif (m := self._BATTERY_CTX_RE.search(text)):
            mah = float(m.group(1).replace(",", "."))
            if 400 <= mah <= 35000:
                yield Prediction(
                    attribute="battery", value=_u.battery(m.group(1)),
                    confidence=self._conf(0.90, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )

        # --- Частота ---
        if (m := self._REFRESH_RE.search(text)):
            hz = int(m.group(1))
            if 30 <= hz <= 240:
                yield Prediction(
                    attribute="refresh_rate", value=_u.refresh_rate(m.group(1)),
                    confidence=self._conf(0.90, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )

        # --- Разрешение ---
        if (m := self._RES_RE.search(text)):
            yield Prediction(
                attribute="resolution",
                value=_u.resolution(m.group(1), m.group(2)),
                confidence=self._conf(0.90, m.group(0), title),
                source="regex", raw=m.group(0).strip(),
            )

        # --- Вес ---
        if (m := self._WEIGHT_CTX_RE.search(text)):
            yield Prediction(
                attribute="weight",
                value=_u.weight(m.group(1), m.group(2)),
                confidence=self._conf(0.93, m.group(0), title),
                source="regex", raw=m.group(0).strip(),
            )
        elif (m := self._WEIGHT_KG_RE.search(text)):
            # только "кг" — явный маркер веса
            yield Prediction(
                attribute="weight",
                value=_u.weight(m.group(1), "кг"),
                confidence=self._conf(0.89, m.group(0), title),
                source="regex", raw=m.group(0).strip(),
            )
        elif (m := self._WEIGHT_G_RE.search(text)):
            grams = float(m.group(1).replace(",", "."))
            if grams <= 2000:  # защита от мусора
                yield Prediction(
                    attribute="weight",
                    value=_u.weight(m.group(1), "г"),
                    confidence=self._conf(0.88, m.group(0), title),
                    source="regex", raw=m.group(0).strip(),
                )

        # --- Мощность ---
        if (m := self._POWER_RE.search(text)):
            yield Prediction(
                attribute="power", value=_u.power(m.group(1), m.group(2)),
                confidence=self._conf(0.90, m.group(0), title),
                source="regex", raw=m.group(0).strip(),
            )

        # --- Объём ---
        if (m := self._VOLUME_RE.search(text)):
            yield Prediction(
                attribute="volume", value=_u.volume(m.group(1), m.group(2)),
                confidence=self._conf(0.89, m.group(0), title),
                source="regex", raw=m.group(0).strip(),
            )

        # --- Гарантия ---
        if (m := self._WARRANTY_RE.search(text)):
            yield Prediction(
                attribute="warranty",
                value=_u.warranty(m.group(1), m.group(2)),
                confidence=0.92, source="regex", raw=m.group(0).strip(),
            )

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

    # ================== CPU / OS ==================

    def _find_cpu(self, text: str):
        for pat, conf in self._CPU_PATTERNS:
            if (m := pat.search(text)):
                return m, conf
        return None

    def _canon_cpu(self, raw: str) -> str:
        """'snapdragon 8 gen 3' → 'Snapdragon 8 Gen 3'."""
        raw = re.sub(r"^(?:чип|процессор|chip)\s+", "", raw.strip(), flags=re.IGNORECASE)
        out: list[str] = []
        for tok in raw.split():
            low = tok.lower()
            if low in self._CPU_CANON:
                out.append(self._CPU_CANON[low])
            elif re.fullmatch(r"m\d+", low):
                out.append("M" + low[1:])
            elif re.fullmatch(r"a\d+", low):
                out.append("A" + low[1:])
            else:
                out.append(tok)
        return " ".join(out)

    @staticmethod
    def _canon_model(val: str) -> str:
        """Нормализация написания моделей телефонов."""
        val = val.strip()
        val = re.sub(r"^[аА](?=\d)", "A", val)
        val = re.sub(r"^[сС](?=\d)", "S", val)
        val = re.sub(r"5[гГ]\b", "5G", val)
        val = re.sub(r"\b5g\b", "5G", val, flags=re.IGNORECASE)
        val = re.sub(r"\bгэлакси\b", "Galaxy", val, flags=re.IGNORECASE)
        words = val.split()
        fixed_words = []
        for w in words:
            low = w.lower()
            if low == "iphone":
                fixed_words.append("iPhone")
            elif low in {"galaxy", "redmi", "note", "edge", "xperia", "ultra", "plus", "pro", "max", "mini", "lite", "play", "neo", "turbo", "fusion"}:
                fixed_words.append(low.capitalize())
            elif low == "gt":
                fixed_words.append("GT")
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
        """Возвращает (raw_match, canonical) или None. Приоритет — самому
        длинному совпадению (chrome os раньше chrome, harmony os раньше harmony)."""
        best: tuple[int, str, str] | None = None
        for pat, canon in self._os_patterns:
            if (m := pat.search(text)):
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
        return min(0.99, base + (0.03 if raw and raw in title else 0.0))