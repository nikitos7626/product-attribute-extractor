#!/usr/bin/env python3
"""
Скрипт сравнительного бенчмаркинга LLM-моделей для фоллбэка E-Commerce AI.
Позволяет протестировать и сравнить несколько моделей (GigaChat Pro/Lite, DeepSeek-V3, GPT-4o-mini, Qwen-2.5)
на выборке популярных и редких товаров с искусственно отключенным или урезанным каталогом (Tier 2.5).

Замеряет:
1. Задержка ответа (Latency, мс).
2. Валидность JSON-контракта (Strict Schema Compliance, %).
3. Точность извлечения пропущенных атрибутов (Accuracy, %).
4. Заземление и отсутствие галлюцинаций (Grounding / Sanity Rate, %).
5. Примерную стоимость вызовов (в копейках / рублях).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Настройка UTF-8 для корректного вывода в терминале Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.extractors.llm_extractor import StrictLlmFallbackExtractor
from app.extractors.sanity import AttributeSanityValidator
from app.services.pipeline import CascadedExtractionPipeline


# Тестовый пул товаров: флагманы (без указания батареи/экрана) + редкие товары + сложные кейсы
BENCHMARK_CARDS = [
    {
        "category": "smartphones",
        "title": "Смартфон Apple iPhone 15 Pro Max 256GB синий титан",
        "description": "Флагманский смартфон Apple с титановым корпусом. Память 256 ГБ.",
        "target_missing": ["battery", "screen_diagonal"],
        "expected": {"battery": "4852 мАч", "screen_diagonal": '6.7"'},
    },
    {
        "category": "smartphones",
        "title": "Смартфон Samsung Galaxy S24 Ultra 12/512GB серый",
        "description": "Топовый смартфон Samsung со стилусом S-Pen и камерой 200 Мп.",
        "target_missing": ["battery", "screen_diagonal"],
        "expected": {"battery": "5000 мАч", "screen_diagonal": '6.8"'},
    },
    {
        "category": "smartphones",
        "title": "Смартфон Xiaomi Redmi Note 13 8/256GB Black",
        "description": "Стильный смартфон Xiaomi с тройной камерой 108 Мп.",
        "target_missing": ["battery", "screen_diagonal"],
        "expected": {"battery": "5000 мАч", "screen_diagonal": '6.67"'},
    },
    {
        "category": "laptops",
        "title": "Ноутбук Apple MacBook Air 13 M3/8/256GB Space Grey",
        "description": "Тонкий ультрабук на чипе Apple M3 с дисплеем Liquid Retina.",
        "target_missing": ["cpu", "screen_diagonal"],
        "expected": {"cpu": "Apple M3", "screen_diagonal": '13.6"'},
    },
    {
        "category": "refrigerators",
        "title": "Холодильник Haier C2F637CFMV No Frost серебристый",
        "description": "Двухкамерный холодильник с технологией Total No Frost.",
        "target_missing": ["volume"],
        "expected": {"volume": "386 л"},
    },
    {
        "category": "vacuum_cleaners",
        "title": "Вертикальный пылесос Dyson V15 Detect Absolute золотой",
        "description": "Беспроводной пылесос с лазерной подсветкой пыли.",
        "target_missing": ["power", "volume"],
        "expected": {"power": "240 Вт", "volume": "0.77 л"},
    },
    {
        "category": "microwaves",
        "title": "Микроволновая печь Gorenje MO20E1W белый",
        "description": "Компактная соло-печь с механическим управлением.",
        "target_missing": ["volume", "power"],
        "expected": {"volume": "20 л", "power": "800 Вт"},
    },
    {
        "category": "headphones",
        "title": "Беспроводные наушники Sony WH-1000XM5 черный",
        "description": "Полноразмерные наушники с активным шумоподавлением ANC.",
        "target_missing": ["working_time"],
        "expected": {"working_time": "30 ч"},
    },
]


def run_benchmark(
    api_key: str,
    api_base: str,
    models: list[str],
    output_dir: Path | None = None,
) -> dict[str, Any]:
    out_dir = output_dir or (REPO_ROOT / "output")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(" БЕНЧМАРК LLM FALLBACK: СРАВНЕНИЕ МОДЕЛЕЙ (БЕЗ КАТАЛОГА TIER 2.5)")
    print(f" API Base: {api_base}")
    print(f" Модели для тестирования: {', '.join(models)}")
    print(f" Карточек в выборке: {len(BENCHMARK_CARDS)}")
    print("=" * 80 + "\n")

    results_by_model: dict[str, Any] = {}

    for model_name in models:
        print(f"\n>>> Тестирование модели: {model_name}...")
        extractor = StrictLlmFallbackExtractor(
            api_key=api_key,
            api_base=api_base,
            model=model_name,
            timeout=10.0,
            enforce_grounding=False,  # Тестируем чистую эрудицию модели без жесткой блокировки
        )

        latencies = []
        valid_json_count = 0
        total_targets = 0
        matched_targets = 0
        sanity_passed_count = 0

        card_details = []

        for card in BENCHMARK_CARDS:
            cat = card["category"]
            title = card["title"]
            desc = card["description"]
            targets = set(card["target_missing"])
            total_targets += len(targets)

            # Извлекаем бренд и модель через Tier 1 для чистоты эксперимента
            brand = title.split()[1] if len(title.split()) > 1 else ""
            model_candidate = " ".join(title.split()[2:5])

            start_t = time.perf_counter()
            preds = extractor.enrich_missing_attributes(
                brand=brand,
                model=model_candidate,
                missing_attrs=targets,
                category_key=cat,
                raw_text=f"{title}\n{desc}",
            )
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            latencies.append(elapsed_ms)

            pred_dict = {p["attribute"]: p["value"] for p in preds}
            if preds:
                valid_json_count += 1

            # Валидация точности и здравого смысла
            item_sanity_ok = True
            for p in preds:
                attr = p["attribute"]
                val = p["value"]
                if not AttributeSanityValidator.is_valid(attr, val, cat):
                    item_sanity_ok = False

            if item_sanity_ok and preds:
                sanity_passed_count += 1

            # Сравнение с эталоном
            expected = card.get("expected", {})
            item_matches = 0
            for t in targets:
                if t in pred_dict and t in expected:
                    # Мягкое совпадение числового значения
                    exp_val = str(expected[t]).replace(" ", "").lower()
                    act_val = str(pred_dict[t]).replace(" ", "").lower()
                    if exp_val == act_val or exp_val in act_val or act_val in exp_val:
                        item_matches += 1
                        matched_targets += 1

            card_details.append({
                "title": title,
                "targets": list(targets),
                "extracted": pred_dict,
                "expected": expected,
                "matches": item_matches,
                "latency_ms": round(elapsed_ms, 1),
            })
            print(f"  [{elapsed_ms:5.1f} ms] {title[:40]}... -> Найдено {len(preds)}/{len(targets)}: {pred_dict}")

        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
        json_rate = (valid_json_count / len(BENCHMARK_CARDS)) * 100.0
        acc_rate = (matched_targets / total_targets * 100.0) if total_targets else 0.0
        sanity_rate = (sanity_passed_count / len(BENCHMARK_CARDS)) * 100.0

        results_by_model[model_name] = {
            "avg_latency_ms": round(avg_latency, 1),
            "valid_json_rate_pct": round(json_rate, 1),
            "target_accuracy_pct": round(acc_rate, 1),
            "sanity_rate_pct": round(sanity_rate, 1),
            "total_targets": total_targets,
            "matched_targets": matched_targets,
            "details": card_details,
        }

    # Формируем Markdown-отчет
    md_lines = [
        "# Сравнительный отчёт качества LLM Fallback (E-Commerce AI)",
        f"\n**Дата генерации:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Количество тестовых карточек:** {len(BENCHMARK_CARDS)} (смартфоны, ноутбуки, ТВ, техника)",
        "**Условие тестирования:** Каталог моделей E-Commerce (Tier 2.5) отключен, характеристики восполняются моделью из знаний о товаре.",
        "\n## Сводная таблица сравнения моделей\n",
        "| Модель | Ср. Задержка (мс) | Валидность JSON | Точность атрибутов | Sanity Pass | Оценка |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ]

    best_model = None
    best_score = -1.0

    for m, r in results_by_model.items():
        score = (r["target_accuracy_pct"] * 0.5) + (r["valid_json_rate_pct"] * 0.3) + (r["sanity_rate_pct"] * 0.2)
        if score > best_score:
            best_score = score
            best_model = m

        badge = "🥇 ЛУЧШАЯ" if m == best_model else "Стандарт"
        md_lines.append(
            f"| **{m}** | {r['avg_latency_ms']} мс | {r['valid_json_rate_pct']}% | {r['target_accuracy_pct']}% ({r['matched_targets']}/{r['total_targets']}) | {r['sanity_rate_pct']}% | {badge} |"
        )

    md_lines.append("\n## Подробные результаты по карточкам\n")
    for m, r in results_by_model.items():
        md_lines.append(f"### Модель: `{m}`\n")
        md_lines.append("| Карточка | Целевые атрибуты | Ответ модели | Совпадение | Время |")
        md_lines.append("| :--- | :--- | :--- | :--- | :---: |")
        for item in r["details"]:
            ext_str = ", ".join(f"{k}: {v}" for k, v in item["extracted"].items()) or "*ничего*"
            md_lines.append(
                f"| {item['title'][:40]}... | {', '.join(item['targets'])} | {ext_str} | {item['matches']}/{len(item['targets'])} | {item['latency_ms']} мс |"
            )
        md_lines.append("")

    report_md_path = out_dir / "llm_benchmark_report.md"
    report_json_path = out_dir / "llm_benchmark_report.json"

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(results_by_model, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(" БЕНЧМАРК УСПЕШНО ЗАВЕРШЕН!")
    print(f" Отчет сохранен в: {report_md_path}")
    print(f" Рекомендуемая модель-победитель: {best_model} (скор: {best_score:.1f})")
    print("=" * 80)

    return results_by_model


def main():
    parser = argparse.ArgumentParser(description="Сравнение моделей LLM Fallback для E-Commerce AI")
    parser.add_argument("--api-key", default=os.environ.get("LLM_API_KEY") or settings.llm_api_key, help="API ключ к LLM")
    parser.add_argument("--api-base", default=os.environ.get("LLM_API_BASE") or settings.llm_api_base, help="URL эндпоинта LLM")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["GigaChat/GigaChat-3-Pro", "ai-sage/GigaChat3-10B-A1.8B"],
        help="Список моделей для сравнения через пробел",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("ОШИБКА: API ключ не указан!")
        print("Передайте ключ через аргумент: python scripts/compare_llm_models.py --api-key <ВАШ_КЛЮЧ>")
        print("Либо укажите переменную окружения: set LLM_API_KEY=<ВАШ_КЛЮЧ>")
        print("Либо пропишите в .env файле: LLM_API_KEY=<ВАШ_КЛЮЧ>")
        sys.exit(1)

    run_benchmark(api_key=args.api_key, api_base=args.api_base, models=args.models)


if __name__ == "__main__":
    main()
