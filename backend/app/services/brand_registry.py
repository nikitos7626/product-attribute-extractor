"""
Реестр брендов с поддержкой динамической регистрации (Dynamic Brand Registry)
и валидацией канонических имен / опечаток (Fuzzy Brand Typo Matcher).

Архитектура:
1. Канонические бренды E-Commerce (4 600+ брендов из brands.csv).
2. Популярные бренды и их транслиты/опечатки (Samsung, Apple, Xiaomi, LG и т.д.).
3. Нечеткое сопоставление (Fuzzy Match / SequenceMatcher): опечатки («смасунг», «смачунг»)
   мягко нормализуются в канонический бренд («Samsung») с флагом is_fuzzy_corrected=True.
4. Новые бренды (Brand Candidates): неизвестные слова, не являющиеся опечатками,
   сохраняются как кандидаты с confidence=0.80 и needs_review=True.
"""
from __future__ import annotations

import contextlib
import difflib
import logging
import os
import re
import threading
import time
from typing import Callable

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_BRANDS_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    getattr(settings, "brands_csv_path", "data/dictionaries/brands.csv"),
)


@contextlib.contextmanager
def process_file_lock(filepath: str, timeout: float = 10.0):
    """
    Кроссплатформенная межпроцессная блокировка файла (Process-Safe File Lock).
    Использует атомарное создание .lock файла через os.O_CREAT | os.O_EXCL.
    Защищена от зависших (stale) блокировок старше 30 секунд.
    """
    lock_file = filepath + ".lock"
    start_time = time.time()
    fd = None

    while True:
        try:
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except (FileExistsError, OSError):
            # Проверяем, не является ли существующая блокировка зависшей
            try:
                if os.path.exists(lock_file):
                    lock_age = time.time() - os.path.getmtime(lock_file)
                    if lock_age > 30.0:
                        logger.warning("Cleaning up stale brand registry lock file (%s, age=%.1fs)", lock_file, lock_age)
                        try:
                            os.unlink(lock_file)
                        except OSError:
                            pass
                        continue
            except OSError:
                pass

            if time.time() - start_time >= timeout:
                logger.error("Timed out waiting for file lock on %s after %.1fs", filepath, timeout)
                raise TimeoutError(f"Timed out waiting for file lock on {filepath} after {timeout:.1f}s")
            time.sleep(0.02)

    try:
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                if os.path.exists(lock_file):
                    os.unlink(lock_file)
            except OSError:
                pass



# Топ-35 ключевых брендов каталога E-Commerce с известными транслитерациями и синонимами
POPULAR_BRANDS: dict[str, list[str]] = {
    "Samsung": [
        "samsung", "самсунг", "смасунг", "смачунг", "samsung galaxy", "гэлакси", "гелакси", "galaxy", "самсунг гэлакси"
    ],
    "Apple": [
        "apple", "эппл", "эпл", "айфон", "iphone", "apple inc", "ipad", "айпад", "macbook", "макбук"
    ],
    "Xiaomi": [
        "xiaomi", "сяоми", "ксяоми", "шаоми", "редми", "redmi", "poco", "поко", "mi"
    ],
    "Huawei": [
        "huawei", "хуавей", "хуавэй"
    ],
    "Honor": [
        "honor", "хонор"
    ],
    "Realme": [
        "realme", "реалми", "реалме"
    ],
    "Infinix": [
        "infinix", "инфиникс"
    ],
    "Tecno": [
        "tecno", "текно"
    ],
    "Sony": [
        "sony", "сони", "playstation", "плейстейшн", "сони плейстейшн"
    ],
    "LG": [
        "lg", "элджи", "лджи", "лж", "lg electronics"
    ],
    "Philips": [
        "philips", "филипс"
    ],
    "Bosch": [
        "bosch", "бош"
    ],
    "Siemens": [
        "siemens", "сименс"
    ],
    "Electrolux": [
        "electrolux", "электролюкс"
    ],
    "Indesit": [
        "indesit", "индезит"
    ],
    "Beko": [
        "beko", "беко"
    ],
    "Gorenje": [
        "gorenje", "горенье", "горени"
    ],
    "Haier": [
        "haier", "хайер", "хаер"
    ],
    "Tefal": [
        "tefal", "тефаль"
    ],
    "Redmond": [
        "redmond", "редмонд"
    ],
    "Dyson": [
        "dyson", "дайсон"
    ],
    "Dreame": [
        "dreame", "дрими"
    ],
    "Roborock": [
        "roborock", "роборок"
    ],
    "Lenovo": [
        "lenovo", "леново"
    ],
    "Asus": [
        "asus", "асус"
    ],
    "Acer": [
        "acer", "эйсер", "асер"
    ],
    "HP": [
        "hp", "эйчпи"
    ],
    "Dell": [
        "dell", "делл"
    ],
    "MSI": [
        "msi", "мси"
    ],
    "TCL": [
        "tcl", "тсл"
    ],
    "Hisense": [
        "hisense", "хайсенс"
    ],
    "Google": [
        "google", "гугл", "pixel", "пиксель"
    ],
    "OnePlus": [
        "oneplus", "ванплас"
    ],
    "Oppo": [
        "oppo", "оппо"
    ],
    "Vivo": [
        "vivo", "виво"
    ],
}


class BrandRegistry:
    """
    Синглтон-реестр брендов каталога E-Commerce с потокобезопасным кэшем в памяти (threading.RLock)
    и межпроцессной атомарной блокировкой записи в файл (Process-Safe Atomic File Lock).
    """

    _instance: BrandRegistry | None = None
    _instance_lock: threading.Lock = threading.Lock()

    def __init__(self, csv_path: str | None = None) -> None:
        self.csv_path = csv_path or DEFAULT_BRANDS_CSV
        self._lock = threading.RLock()
        self.brands: dict[str, str] = {}
        self.canonical_whitelist: set[str] = set()
        self.candidates: set[str] = set()
        self._listeners: list[Callable[[str, str], None]] = []
        self._load()

    @classmethod
    def get_instance(cls) -> BrandRegistry:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _load(self) -> None:
        """Загружает существующие бренды из CSV и предзаполняет популярные алиасы под блокировкой."""
        with self._lock:
            if not os.path.exists(self.csv_path):
                logger.warning("Brands CSV not found at %s", self.csv_path)
                return

            count = 0
            with open(self.csv_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(",", 1)
                    alias = parts[0].strip().lower()
                    canon = parts[1].strip() if len(parts) > 1 else parts[0].strip()
                    if alias and canon:
                        self.brands[alias] = canon
                        self.canonical_whitelist.add(canon)
                        count += 1

            # Обогащаем популярными алиасами и транслитами E-Commerce
            for canon, aliases in POPULAR_BRANDS.items():
                self.canonical_whitelist.add(canon)
                for a in aliases:
                    a_lower = a.lower().strip()
                    self.brands[a_lower] = canon

            logger.info("BrandRegistry loaded %d brands from %s", count, self.csv_path)

    def subscribe(self, callback: Callable[[str, str], None]) -> None:
        """Подписывает обработчик (например KeywordProcessor) на появление новых брендов."""
        with self._lock:
            self._listeners.append(callback)

    def has_brand(self, brand: str) -> bool:
        """Проверяет, зарегистрирован ли бренд."""
        if not brand:
            return False
        with self._lock:
            return brand.strip().lower() in self.brands

    def get_canonical(self, brand: str) -> str | None:
        """Возвращает каноническое имя бренда или None."""
        if not brand:
            return None
        with self._lock:
            return self.brands.get(brand.strip().lower())

    def match_or_fuzzy_brand(self, word: str) -> tuple[str, float, bool]:
        """
        Проверяет бренд:
        Возвращает кортеж: (canonical_name, confidence, is_fuzzy_or_candidate).

        1. Точное совпадение в self.brands -> (canonical, 0.95, False)
        2. Нечеткое совпадение с популярными брендами (похоже на опечатку) -> (canonical, 0.85, True)
        3. Неизвестное новое слово -> (word.title(), 0.80, True) [кандидат в бренд]
        """
        if not word or not word.strip():
            return ("", 0.0, False)

        clean = word.strip().lower()

        with self._lock:
            # 1. Точное совпадение со словарем
            if clean in self.brands:
                canon = self.brands[clean]
                return (canon, 0.95, False)

            # 2. Нечеткое сопоставление с популярными брендами (защита от опечаток селлеров)
            best_canon: str | None = None
            best_ratio: float = 0.0

            for canon, aliases in POPULAR_BRANDS.items():
                for alias in aliases:
                    # Если длины отличаются слишком сильно, пропускаем
                    if abs(len(clean) - len(alias)) > 2:
                        continue
                    ratio = difflib.SequenceMatcher(None, clean, alias).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_canon = canon

            # Порог похожести: опечатка в 1-2 символах ("смачунг" к "самсунг" = 0.86, "смасунг" = 0.86)
            if best_ratio >= 0.78 and best_canon:
                logger.info("Fuzzy matched typo '%s' -> canonical '%s' (ratio=%.2f)", word, best_canon, best_ratio)
                return (best_canon, 0.85, True)

            # 3. Новое неизвестное слово (кандидат в новый бренд)
            candidate = word.strip().title()
            self.candidates.add(candidate)
            return (candidate, 0.80, True)

    def register_brand(self, alias: str, canonical: str | None = None, persist: bool = True) -> bool:
        """
        Потокобезопасно и процессно-безопасно регистрирует новый бренд:
        - проверяет, не является ли это опечаткой существующего популярного бренда
        - добавляет в память под self._lock
        - уведомляет слушателей FlashText
        - атомарно дописывает в CSV файл с межпроцессной блокировкой и fsync (если persist=True)
        """
        if not alias or len(alias.strip()) < 2:
            return False

        clean_alias = alias.strip().lower()
        if "," in clean_alias:
            return False

        # Проверка: если пытаются зарегистрировать опечатку, автоматически мапим в канонический бренд
        fuzzy_canon, _, is_fuzzy = self.match_or_fuzzy_brand(clean_alias)
        if is_fuzzy and fuzzy_canon in POPULAR_BRANDS:
            clean_canon = fuzzy_canon
        else:
            clean_canon = canonical.strip() if canonical and canonical.strip() else alias.strip().title()

        with self._lock:
            # Если алиас уже известен с тем же значением, не дублируем
            if clean_alias in self.brands and self.brands[clean_alias] == clean_canon:
                return False

            self.brands[clean_alias] = clean_canon
            self.canonical_whitelist.add(clean_canon)
            listeners_snapshot = list(self._listeners)

        # Уведомляем подписчиков (KeywordProcessor и др.)
        for listener in listeners_snapshot:
            try:
                listener(clean_alias, clean_canon)
            except Exception as e:
                logger.error("Error in brand listener: %s", e)

        # Сохраняем на диск при persist=True с межпроцессной блокировкой
        if persist:
            try:
                csv_dir = os.path.dirname(os.path.abspath(self.csv_path))
                if csv_dir and not os.path.exists(csv_dir):
                    os.makedirs(csv_dir, exist_ok=True)

                with process_file_lock(self.csv_path, timeout=5.0):
                    # Проверяем перед дозаписью, не добавил ли уже другой процесс
                    already_present = False
                    if os.path.exists(self.csv_path):
                        with open(self.csv_path, "r", encoding="utf-8") as rf:
                            for row in rf:
                                row_parts = row.strip().split(",", 1)
                                if row_parts and row_parts[0].strip().lower() == clean_alias:
                                    already_present = True
                                    break

                    if not already_present:
                        with open(self.csv_path, "a", encoding="utf-8") as f:
                            f.write(f"{clean_alias},{clean_canon}\n")
                            f.flush()
                            try:
                                os.fsync(f.fileno())
                            except OSError:
                                pass
                logger.info("Successfully registered brand alias: %s -> %s", clean_alias, clean_canon)
            except Exception as e:
                logger.error("Failed to append brand to %s: %s", self.csv_path, e)
                return False

        return True
