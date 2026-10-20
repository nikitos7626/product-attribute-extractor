"""
Модуль математической калибровки вероятностей и оценки неопределенности
(Confidence Calibration & Uncertainty Quantification).

Построен на основе фундаментальных принципов:
  1. Platt Scaling & Logistic Calibration (калибровка логитов через сигмоиду).
  2. Multi-Source Consensus (теория Weak Supervision / Stanford Snorkel):
     байесовское усиление вероятности при согласии независимых экстракторов (Regex + GLiNER + KB).
  3. Geometric Mean Penalty (штраф за дисперсию уверенности в обязательных атрибутах).
  4. Expected Calibration Error (ECE) metric для аудита надежности скоров.
"""
from __future__ import annotations

import math
import re
from typing import Any, Iterable
from app.config import settings


class ConfidenceCalibrator:
    """
    Промышленный калибратор уверенности извлечения характеристик.
    Превращает разрозненные эвристические скоры экстракторов в строгую
    апостериорную вероятность P(y=1 | x, sources, sanity).
    """

    _instance: ConfidenceCalibrator | None = None

    @classmethod
    def get_source_priors(cls) -> dict[str, float]:
        """Динамический словарь априорных весов надежности источников из конфигурации."""
        return {
            "catalog_kb": getattr(settings, "prior_catalog_kb", 0.94),
            "flashtext": getattr(settings, "prior_flashtext", 0.95),
            "rule_subbrand": getattr(settings, "prior_rule_subbrand", 0.96),
            "regex_bounded": getattr(settings, "prior_regex_bounded", 0.93),
            "regex": getattr(settings, "prior_regex", 0.90),
            "gliner": getattr(settings, "prior_gliner", 0.88),
            "llm_grounded": getattr(settings, "prior_llm_grounded", 0.86),
            "default": getattr(settings, "prior_default", 0.75),
        }

    @property
    def SOURCE_PRIORS(self) -> dict[str, float]:
        """Обратная совместимость для прямого обращения к словарю SOURCE_PRIORS."""
        return self.get_source_priors()

    @property
    def GLINER_TEMPERATURE(self) -> float:
        return getattr(settings, "gliner_temperature", 1.25)

    def __init__(self) -> None:
        pass

    @classmethod
    def get_instance(cls) -> ConfidenceCalibrator:
        if cls._instance is None:
            cls._instance = ConfidenceCalibrator()
        return cls._instance

    def calibrate_attribute(
        self,
        attribute: str,
        value: Any,
        raw_confidence: float,
        source: str,
        category_key: str,
        in_title: bool = False,
        sanity_passed: bool = True,
    ) -> float:
        """
        Калибрует уверенность отдельного атрибута через логистическое масштабирование.
        """
        if not sanity_passed or value is None:
            return 0.0

        priors = self.get_source_priors()
        prior = priors.get(source, priors["default"])

        # 2. Если скор пришел от нейросети (GLiNER), применяем Temperature Scaling
        if source == "gliner":
            # Перевод вероятности в логит -> масштабирование температурой -> обратно в сигмоиду
            clamped_prob = min(max(raw_confidence, 0.01), 0.99)
            logit = math.log(clamped_prob / (1.0 - clamped_prob))
            scaled_logit = logit / self.GLINER_TEMPERATURE
            calibrated_prob = 1.0 / (1.0 + math.exp(-scaled_logit))
            w_prior = getattr(settings, "gliner_weight_prior", 0.40)
            w_prob = getattr(settings, "gliner_weight_prob", 0.60)
            score = w_prior * prior + w_prob * calibrated_prob
        else:
            score = 0.5 * prior + 0.5 * raw_confidence

        # 3. Бонус за присутствие в Title (Head Noun приоритет)
        if in_title:
            title_bonus = getattr(settings, "calibrator_title_bonus", 0.03)
            score = min(0.99, score + title_bonus)

        return round(score, 4)

    @staticmethod
    def _are_values_equivalent(val1: Any, val2: Any, attr: str = "") -> bool:
        if val1 is None or val2 is None:
            return False
        s1 = re.sub(r"\s+", " ", str(val1)).strip().lower().replace(",", ".")
        s2 = re.sub(r"\s+", " ", str(val2)).strip().lower().replace(",", ".")
        if s1 == s2:
            return True

        # 1. Числовые характеристики (сравнение по числовому значению и единицам)
        if attr in (
            "battery", "screen_diagonal", "memory_rom", "memory_ram",
            "load_capacity", "spin_speed", "weight", "power", "volume", "refresh_rate",
        ):
            n1 = re.findall(r"\d+(?:\.\d+)?", s1)
            n2 = re.findall(r"\d+(?:\.\d+)?", s2)
            if not n1 or not n2:
                return False
            f1, f2 = float(n1[0]), float(n2[0])

            # Нормализация единиц памяти (ТБ <-> ГБ)
            if attr in ("memory_rom", "memory_ram"):
                if ("тб" in s1 or "tb" in s1) and ("гб" in s2 or "gb" in s2):
                    f1 *= 1024
                elif ("тб" in s2 or "tb" in s2) and ("гб" in s1 or "gb" in s1):
                    f2 *= 1024
            # Нормализация массы (кг <-> г)
            elif attr == "weight":
                if ("кг" in s1 or "kg" in s1) and ("г" in s2 or "g" in s2) and "кг" not in s2 and "kg" not in s2:
                    f1 *= 1000
                elif ("кг" in s2 or "kg" in s2) and ("г" in s1 or "g" in s1) and "кг" not in s1 and "kg" not in s1:
                    f2 *= 1000
            # Нормализация мощности (кВт <-> Вт)
            elif attr == "power":
                if ("квт" in s1 or "kw" in s1) and ("вт" in s2 or "w" in s2) and "квт" not in s2 and "kw" not in s2:
                    f1 *= 1000
                elif ("квт" in s2 or "kw" in s2) and ("вт" in s1 or "w" in s1) and "квт" not in s1 and "kw" not in s1:
                    f2 *= 1000

            if attr == "screen_diagonal":
                return abs(f1 - f2) <= 0.1
            return abs(f1 - f2) < 0.01

        # 2. Разрешение экрана (4K / UHD эквивалентны 3840x2160)
        if attr == "resolution":
            if ("4k" in s1 or "uhd" in s1) and ("3840" in s2 or "2160" in s2):
                return True
            if ("4k" in s2 or "uhd" in s2) and ("3840" in s1 or "2160" in s1):
                return True
            if ("fhd" in s1 or "full hd" in s1) and ("1920" in s2 or "1080" in s2):
                return True
            if ("fhd" in s2 or "full hd" in s2) and ("1920" in s1 or "1080" in s1):
                return True

        # 3. Цвета: нормализация через палитру
        if attr == "color":
            try:
                from app.extractors.sanity import AttributeSanityValidator
                c1 = AttributeSanityValidator.normalize_color(s1)
                c2 = AttributeSanityValidator.normalize_color(s2)
                if c1 and c2 and c1 == c2:
                    return True
            except Exception:
                pass

        # 4. Текстовые поля (бренды, модели): омоглифы и границы слов
        homoglyphs = str.maketrans("асеорхувкмит", "aceopxybkmit")
        t1 = s1.translate(homoglyphs)
        t2 = s2.translate(homoglyphs)
        if t1 == t2:
            return True

        if attr in ("model", "brand"):
            clean1 = re.sub(r"\b[345]g\b", "", t1).strip()
            clean2 = re.sub(r"\b[345]g\b", "", t2).strip()
            d1 = re.findall(r"\d+", clean1)
            d2 = re.findall(r"\d+", clean2)
            if d1 and d2 and set(d1) != set(d2):
                return False
            if min(len(t1), len(t2)) >= 3:
                if re.search(rf"\b{re.escape(t1)}\b", t2) or re.search(rf"\b{re.escape(t2)}\b", t1) or (t1 in t2) or (t2 in t1):
                    return True

        return False

    def apply_multi_source_consensus(
        self,
        predictions_map: dict[str, Any],
        extracted_alternatives: dict[str, list[dict[str, Any]]],
    ) -> None:
        """
        Теория Weak Supervision (Stanford Snorkel):
        Если два независимых экстрактора (например, Regex и GLiNER, или Regex и Catalog KB)
        извлекли ОДНО И ТО ЖЕ значение — байесовская вероятность истинности возрастает:
            P(consensus) = 1 - (1 - P1) * (1 - P2)
        Если источники противоречат друг другу — накладывается штраф за разногласие.
        """
        conflict_penalty = getattr(settings, "consensus_conflict_penalty", 0.12)
        min_conf = getattr(settings, "consensus_min_confidence", 0.40)

        for attr, pred in predictions_map.items():
            alts = extracted_alternatives.get(attr, [])
            if not alts:
                continue

            current_val = pred.get("value", "")
            matching_sources = []
            conflicting_sources = []

            for alt in alts:
                alt_source = alt.get("source")
                alt_val = alt.get("value", "")
                alt_conf = alt.get("confidence", 0.8)

                if alt_source == pred.get("source"):
                    continue

                # Проверяем эквивалентность значений (с нормализацией пробелов, омоглифов и единиц)
                if self._are_values_equivalent(current_val, alt_val, attr):
                    matching_sources.append((alt_source, alt_conf))
                else:
                    conflicting_sources.append((alt_source, alt_conf))

            # Байесовское усиление при консенсусе
            if matching_sources:
                p_current = pred["confidence"]
                p_boosted = p_current
                for _, s_conf in matching_sources:
                    p_boosted = 1.0 - (1.0 - p_boosted) * (1.0 - s_conf)
                pred["confidence"] = round(min(0.99, max(p_current, p_boosted)), 4)
                pred["consensus"] = True
                pred["consensus_sources"] = list(dict.fromkeys([pred.get("source")] + [s[0] for s in matching_sources]))

            # Штраф при неразрешимом конфликте источников
            elif conflicting_sources:
                pred["confidence"] = round(max(min_conf, pred["confidence"] - conflict_penalty), 4)
                pred["conflict"] = True

    def calculate_card_confidence(
        self,
        predictions: list[dict[str, Any]],
        required_attrs: set[str],
        category_key: str,
    ) -> tuple[float, list[str]]:
        """
        Вычисляет строгую совместную вероятность корректности карточки товара:
          1. Геометрическое среднее уверенностей обязательных полей (Geometric Mean).
             В отличие от арифметического, геометрическое среднее резко падает, если
             хотя бы одно поле сомнительно (свойство мультипликативности ошибок).
          2. Нелинейный штраф за полноту обязательной схемы: (found / total)^1.5.
        """
        found_attrs = {p["attribute"]: p["confidence"] for p in predictions if p.get("value") is not None}
        missing_required = sorted(list(required_attrs - set(found_attrs.keys())))

        total_req = len(required_attrs) if required_attrs else 1
        found_req_count = len(required_attrs & set(found_attrs.keys()))
        coverage_ratio = found_req_count / total_req

        if not predictions or found_req_count == 0:
            return 0.0, missing_required

        # 1. Совместная вероятность по обязательным полям через Geometric Mean
        req_confs = [found_attrs[a] for a in required_attrs if a in found_attrs]
        if req_confs:
            log_sum = sum(math.log(max(0.01, c)) for c in req_confs)
            geom_mean_req = math.exp(log_sum / len(req_confs))
        else:
            geom_mean_req = 0.0

        # Средняя уверенность опциональных (дополнительных) полей
        opt_confs = [p["confidence"] for p in predictions if p["attribute"] not in required_attrs]
        avg_opt = (sum(opt_confs) / len(opt_confs)) if opt_confs else geom_mean_req

        # Базовый композитный скор карточки (вес обязательных и опциональных полей из конфигурации)
        req_weight = getattr(settings, "card_required_attrs_weight", 0.80)
        opt_weight = getattr(settings, "card_optional_attrs_weight", 0.20)
        base_quality = req_weight * geom_mean_req + opt_weight * avg_opt

        # 2. Нелинейный штраф за неполноту каталожной спецификации (Power-law penalty)
        penalty_power = getattr(settings, "completeness_penalty_power", 1.5)
        completeness_factor = math.pow(coverage_ratio, penalty_power)

        overall_calibrated_conf = base_quality * completeness_factor
        return round(overall_calibrated_conf, 4), missing_required

    @staticmethod
    def expected_calibration_error(
        y_true: list[int],
        y_prob: list[float],
        n_bins: int = 10,
    ) -> float:
        """
        Expected Calibration Error (ECE) — официальная академическая метрика
        калибровки вероятностей (Guo et al., ICML 2017).
        Показывает среднюю разницу между предсказанной уверенностью и реальной точностью:
            ECE = sum( (bin_size / N) * |acc(bin) - conf(bin)| )
        Идеальное значение ECE = 0.0 (модель точно знает степень своей уверенности).
        """
        if not y_true or len(y_true) != len(y_prob):
            return 0.0

        n = len(y_true)
        bin_limits = [i / n_bins for i in range(n_bins + 1)]
        ece = 0.0

        for i in range(n_bins):
            bin_lower = bin_limits[i]
            bin_upper = bin_limits[i + 1]

            # Элементы в текущей корзине вероятностей
            bin_indices = [
                idx for idx, p in enumerate(y_prob)
                if (bin_lower <= p < bin_upper) or (i == n_bins - 1 and bin_lower <= p <= bin_upper)
            ]

            bin_size = len(bin_indices)
            if bin_size == 0:
                continue

            bin_acc = sum(y_true[idx] for idx in bin_indices) / bin_size
            bin_conf = sum(y_prob[idx] for idx in bin_indices) / bin_size

            ece += (bin_size / n) * abs(bin_acc - bin_conf)

        return round(ece, 4)
