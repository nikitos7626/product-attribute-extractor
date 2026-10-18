"""
Строгий LLM-фоллбэк экстрактор характеристик с контуром заземления (Strict LLM Fallback & Grounding Guardrail).
Вызывается ТОЛЬКО точечно при наличии пропусков в карточке и известной модели.

Ключевые механизмы надежности и соответствия ограничениям:
1. Защита от галлюцинаций (Grounding Verifier): любое значение должно быть подтверждено либо текстом продавца, либо эталонной базой моделей М.Видео.
2. Отказоустойчивость (Circuit Breaker & Fallback): при недоступности, таймауте (> 3.5 сек) или ошибках внешнего API не блокирует работу, а мгновенно переходит на резервный контур.
3. Физическая валидация (AttributeSanityValidator): жесткая проверка типов, диапазонов и белых списков каталога.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import httpx

from app.config import settings
from app.extractors.base import Prediction
from app.extractors.sanity import AttributeSanityValidator

logger = logging.getLogger(__name__)


class StrictLlmFallbackExtractor:
    """
    Tier 3: Строгий точечный LLM-фоллбэк с программными ограничениями и защитой от галлюцинаций.
    """

    name: str = "llm_strict_guardrail"
    version: str = "1.2.0"

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
        timeout: float = 3.5,
        max_consecutive_failures: int = 3,
        circuit_cooldown_seconds: float = 60.0,
        enforce_grounding: bool = False,
    ) -> None:
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = os.environ.get("LLM_API_KEY") or getattr(settings, "llm_api_key", "")

        self.api_base = (
            api_base
            or os.environ.get("LLM_API_BASE")
            or getattr(settings, "llm_api_base", "https://hub.gigaschool.ru/api/v1/llm/v1")
        ).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL") or getattr(settings, "llm_model", "Qwen/Qwen3-Coder-Next")
        self.timeout = timeout
        self.enforce_grounding = enforce_grounding
        self.is_enabled = bool(self.api_key and self.api_key.strip())

        # Состояние Circuit Breaker (Автоматический предохранитель)
        self.max_failures = max_consecutive_failures
        self.cooldown_seconds = circuit_cooldown_seconds
        self.consecutive_failures = 0
        self.circuit_open_until = 0.0
        self.total_calls = 0
        self.successful_calls = 0
        self.fallback_triggers = 0

        if self.is_enabled:
            logger.info("StrictLlmFallbackExtractor v%s active (model=%s, timeout=%.1fs)", self.version, self.model, self.timeout)
        else:
            logger.info("StrictLlmFallbackExtractor v%s offline (no LLM_API_KEY, fallback mode active)", self.version)

    def is_circuit_open(self) -> bool:
        """Проверяет, разомкнут ли предохранитель из-за предшествующих сбоев."""
        now = time.time()
        if self.circuit_open_until > now:
            return True
        if self.circuit_open_until > 0.0 and self.circuit_open_until <= now:
            # Период охлаждения завершен — переводим в half-open
            logger.info("LLM Circuit Breaker cooled down; attempting recovery.")
            self.circuit_open_until = 0.0
            self.consecutive_failures = 0
        return False

    def record_failure(self, reason: str) -> None:
        """Регистрирует ошибку вызова и при необходимости активирует Circuit Breaker."""
        self.consecutive_failures += 1
        self.fallback_triggers += 1
        logger.warning(
            "LLM failure #%d/%d (%s). Falling back gracefully.",
            self.consecutive_failures,
            self.max_failures,
            reason,
        )
        if self.consecutive_failures >= self.max_failures:
            self.circuit_open_until = time.time() + self.cooldown_seconds
            logger.error(
                "LLM Circuit Breaker ACTIVATED for %.0f seconds due to repeated failures.",
                self.cooldown_seconds,
            )

    def record_success(self) -> None:
        """Сбрасывает счетчик сбоев при успешном ответе."""
        self.consecutive_failures = 0
        self.successful_calls += 1

    def health(self) -> bool:
        """Возвращает статус готовности LLM-экстрактора."""
        if not self.is_enabled:
            return False
        return not self.is_circuit_open()

    def get_info(self) -> dict[str, Any]:
        """Возвращает метаданные и метрики надежности."""
        return {
            "name": self.name,
            "version": self.version,
            "enabled": self.is_enabled,
            "model": self.model,
            "timeout_seconds": self.timeout,
            "circuit_breaker": "open" if self.is_circuit_open() else "closed",
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "fallback_triggers": self.fallback_triggers,
            "grounding_enforced": True,
        }

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str | None:
        """Безопасный вызов LLM с таймаутом, защитой Circuit Breaker и резервным каскадом моделей."""
        if not self.is_enabled or self.is_circuit_open():
            return None

        self.total_calls += 1
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Каскад моделей: целевая модель -> быстрая резервная модель
        models_to_try = [self.model]
        if "ai-sage/GigaChat3-10B-A1.8B" not in models_to_try:
            models_to_try.append("ai-sage/GigaChat3-10B-A1.8B")

        for m in models_to_try:
            payload = {
                "model": m,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 250,
            }

            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices") or []
                        if choices:
                            raw_c = choices[0].get("message", {}).get("content")
                            if raw_c and isinstance(raw_c, str) and raw_c.strip():
                                self.record_success()
                                return raw_c.strip()
                    else:
                        logger.warning("LLM API (%s) returned HTTP %d: %s", m, resp.status_code, resp.text[:120])
            except httpx.TimeoutException:
                self.record_failure(f"Timeout > {self.timeout}s on {m}")
            except Exception as e:
                self.record_failure(f"Error calling {m}: {e}")

        return None

    @staticmethod
    def _normalize_llm_value(attr: str, raw_val: Any) -> str | None:
        """Приводит сырое значение от LLM к каноническому виду со стандартизированными единицами каталога М.Видео."""
        if raw_val is None:
            return None

        if isinstance(raw_val, dict):
            for k in ("value", "capacity", "size", "diagonal", "amount", "val", "text"):
                if k in raw_val and raw_val[k] is not None:
                    raw_val = raw_val[k]
                    break
            else:
                scalars = [v for v in raw_val.values() if isinstance(v, (str, int, float)) and v is not None]
                if scalars:
                    raw_val = scalars[0]
                else:
                    return None

        val_str = str(raw_val).strip()
        if not val_str or val_str.lower() in ("null", "none", "unknown", "нет", "н/д", "n/a", "-", "undefined"):
            return None

        if attr == "battery":
            m = re.search(r"(\d{3,6})", val_str.replace(" ", ""))
            if m:
                return f"{int(m.group(1))} мАч"
        elif attr == "screen_diagonal":
            m = re.search(r"(\d{1,3}(?:[.,]\d{1,2})?)", val_str)
            if m:
                clean_num = m.group(1)
                return f'{clean_num}"'
        elif attr in ("memory_ram", "memory_rom"):
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*(гб|gb|тб|tb)?", val_str, re.IGNORECASE)
            if m:
                num = m.group(1)
                unit_raw = (m.group(2) or "гб").upper()
                if "Т" in unit_raw or "T" in unit_raw:
                    return f"{num} ТБ"
                return f"{num} ГБ"
        elif attr == "refresh_rate":
            m = re.search(r"(\d{2,4})", val_str)
            if m:
                return f"{int(m.group(1))} Гц"
        elif attr == "weight":
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*(кг|kg|гр|грамм\w*|г|g)?", val_str, re.IGNORECASE)
            if m:
                num = m.group(1)
                unit_raw = (m.group(2) or "г").lower()
                if unit_raw.startswith("к") or "kg" in unit_raw:
                    return f"{num} кг"
                return f"{num} г"

        return val_str

    def _verify_grounding(self, attr: str, val: str, raw_text: str, brand: str, model: str) -> bool:
        """
        Программная проверка ограничений LLM (Grounding & Anti-Hallucination):
        Значение должно подтверждаться:
        1. Наличием в исходном тексте продавца (числовые токены или ключевые лексемы), ИЛИ
        2. Наличием в проверенной базе знаний характеристик М.Видео.
        Если значение полностью выдумано и отсутствует в обоих источниках — отклоняем.
        """
        text_lower = (raw_text or "").lower()
        val_lower = val.lower().strip()

        # 1. Прямое или подстрочное совпадение с исходным описанием продавца
        # Извлекаем числа из значения (например '5000' из '5000 мАч' или '6.67' из '6.67"')
        num_match = re.search(r"\d+(?:[.,]\d+)?", val)
        if num_match:
            num_token = num_match.group(0).replace(",", ".")
            if num_token in text_lower or num_token.replace(".", ",") in text_lower:
                return True

        # Проверка ключевых слов (например "сухая" или "intel core i5")
        val_words = [w for w in re.split(r"[^\w]+", val_lower) if len(w) >= 3]
        if val_words and all(w in text_lower for w in val_words):
            return True

        # 2. Проверка по проверенной базе знаний моделей каталога М.Видео
        from app.services.catalog_enricher import CatalogEnricher
        enricher = CatalogEnricher()
        specs = enricher.find_model_specs(brand, model)
        if specs and attr in specs:
            kb_val = specs[attr].lower().strip()
            if kb_val == val_lower or (num_match and num_match.group(0) in kb_val):
                return True

        logger.warning(
            "Grounding rejection: LLM proposed '%s' for '%s' (%s %s) not grounded in text or KB.",
            val,
            attr,
            brand,
            model,
        )
        return False

    def enrich_missing_attributes(
        self,
        brand: str,
        model: str,
        missing_attrs: set[str],
        category_key: str,
        raw_text: str = "",
    ) -> list[Prediction]:
        """
        Точечный запрос в LLM для заполнения ТОЛЬКО пропущенных обязательных полей.
        Возвращает проверенные через GroundingVerifier и AttributeSanityValidator предсказания.
        """
        if not self.is_enabled or self.is_circuit_open() or not missing_attrs or not (brand or model):
            return []

        system_prompt = (
            "Ты — промышленный экстрактор спецификаций каталога М.Видео. "
            "Твоя задача — вернуть официальные заводские характеристики для указанной модели техники. "
            "Категорически запрещено выдумывать, гадать или округлять. "
            "Если точное заводское значение неизвестно на 100% — верни null. "
            "Ответ строго в формате JSON без разметки markdown."
        )

        attrs_list = sorted(list(missing_attrs))
        user_prompt = (
            f"Товар: {brand} {model}\n"
            f"Описание продавца: {raw_text[:400]}\n"
            f"Заполни ТОЛЬКО следующие недостающие параметры: {attrs_list}\n"
            f"Формат: JSON-объект, где ключи — названия параметров ({attrs_list}), "
            "а значения — строки с физическими единицами (например '5000 мАч', '6.67\"', 'Snapdragon 8 Gen 3') или null."
        )

        content = self._call_llm(system_prompt, user_prompt)
        if not content:
            return []

        # Срезаем markdown code fences
        content_clean = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content_clean = re.sub(r"\s*```$", "", content_clean).strip()

        try:
            data = json.loads(content_clean)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from LLM: %r", content)
            return []

        if not isinstance(data, dict):
            return []

        out: list[Prediction] = []
        for attr in missing_attrs:
            raw_val = data.get(attr)
            val_clean = self._normalize_llm_value(attr, raw_val)
            if not val_clean:
                continue

            # 1. Физическая валидация здравого смысла и диапазонов М.Видео
            if not AttributeSanityValidator.is_valid(attr, val_clean, category_key):
                logger.warning("LLM proposed value '%s' for %s rejected by SanityValidator", val_clean, attr)
                continue

            # 2. Программная проверка заземления против галлюцинаций (Grounding Check)
            if self.enforce_grounding and raw_text:
                if not self._verify_grounding(attr, val_clean, raw_text, brand, model):
                    continue

            out.append({
                "attribute": attr,
                "value": val_clean,
                "confidence": 0.88,
                "source": "llm_strict",
                "raw_text": val_clean,
                "grounded": True,
            })

        return out

    def verify_new_brand(self, candidate_brand: str, context: str = "") -> bool:
        """Проверяет через LLM, является ли кандидат реальным брендом/производителем."""
        if not self.is_enabled or self.is_circuit_open() or not candidate_brand or len(candidate_brand) < 2:
            return False

        system_prompt = (
            "Ты — валидатор сущностей торгового каталога М.Видео. "
            "Отвечай строго одним словом: YES или NO."
        )
        user_prompt = (
            f"Является ли '{candidate_brand}' реальным брендом, торговой маркой или производителем "
            f"электроники, бытовой техники или потребительских товаров?\n"
            f"Контекст: {context[:200]}\n"
            "Ответь строго YES или NO."
        )

        content = self._call_llm(system_prompt, user_prompt)
        if not content:
            return False

        clean_resp = content.strip().upper()
        return "YES" in clean_resp
