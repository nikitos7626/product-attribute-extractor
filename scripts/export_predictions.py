"""
Скрипт стандартизованного экспорта предсказаний (Batch Prediction Export).
Принимает входной файл (CSV или JSON), прогоняет через каскадный пайплайн
и сохраняет стандартизованные файлы предсказаний:
  • output/predictions.json
  • output/predictions.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def export_predictions(
    input_path: str,
    output_json_path: str | None = "output/predictions.json",
    output_csv_path: str | None = "output/predictions.csv",
    use_gliner: bool = True,
    use_llm: bool = False,
) -> list[dict[str, Any]]:
    from app.services.pipeline import CascadedExtractionPipeline

    if output_json_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
    if output_csv_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_csv_path)), exist_ok=True)

    # 1. Чтение входных данных
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Файл {input_path} не найден.")

    cards_in: list[dict[str, Any]] = []
    if input_path.lower().endswith(".json"):
        with open(input_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            cards_in = raw if isinstance(raw, list) else [raw]
    elif input_path.lower().endswith(".csv"):
        import pandas as pd
        df = pd.read_csv(input_path)
        cards_in = df.to_dict(orient="records")
    else:
        raise ValueError("Поддерживаются только форматы .json и .csv")

    print(f"\n🚀 Запуск пакетного экспорта предсказаний для {len(cards_in)} карточек...")
    print(f"📥 Источник: {input_path}")
    print(f"⚙️ Режим: GLiNER={use_gliner}, CatalogKB=True, LLM={use_llm}")

    pipeline = CascadedExtractionPipeline(use_gliner=use_gliner, use_llm=use_llm)

    results: list[dict[str, Any]] = []
    t_start = time.perf_counter()

    for idx, card in enumerate(cards_in, 1):
        ext_id = card.get("external_id") or card.get("id") or f"sku-{idx}"
        title = card.get("title") or ""
        desc = card.get("description") or ""
        raw_text = card.get("raw_text") or f"{title}\n{desc}".strip()
        seller_attrs = card.get("seller_attributes") or {}

        t0 = time.perf_counter()
        res = pipeline.process_card({
            "external_id": ext_id,
            "category": card.get("category"),
            "title": title,
            "description": desc,
            "raw_text": raw_text,
            "seller_attributes": seller_attrs,
        })
        card_latency = (time.perf_counter() - t0) * 1000.0

        flat_preds = {p["attribute"]: p["value"] for p in res.get("predictions", [])}

        item_out = {
            "external_id": ext_id,
            "title": title,
            "category": res.get("category"),
            "overall_confidence": round(res.get("overall_confidence", 0.0), 4),
            "needs_review": res.get("needs_review", False),
            "extracted_attributes": flat_preds,
            "missing_required": res.get("missing", []),
            "latency_ms": round(card_latency, 2),
            "warnings": res.get("warnings", []),
            "degraded_tiers": res.get("degraded_tiers", []),
            "detailed_predictions": res.get("predictions", []),
        }
        results.append(item_out)

    total_time_ms = (time.perf_counter() - t_start) * 1000.0
    avg_latency = total_time_ms / len(cards_in) if cards_in else 0.0

    # 2. Экспорт в JSON
    if output_json_path:
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "metadata": {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "total_cards": len(results),
                        "avg_latency_ms": round(avg_latency, 2),
                        "pipeline_version": "2.2.0",
                    },
                    "items": results,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        # Сохраняем компактный образец предсказаний для быстрого просмотра в веб-интерфейсе репозитория (< 10 КБ)
        sample_path = os.path.join(os.path.dirname(output_json_path), "sample_prediction.json")
        sample_items = results[:3]
        with open(sample_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "metadata": {
                        "description": "Компактный образец стандартизированного вывода предсказаний М.Видео AI (3 карточки)",
                        "schema_version": "2.2.0",
                        "total_samples": len(sample_items),
                    },
                    "samples": sample_items,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    # 3. Экспорт в плоский CSV (удобный для контент-менеджеров и жюри)
    if output_csv_path:
        # Собираем все уникальные атрибуты
        all_attr_names = set()
        for r in results:
            all_attr_names.update(r["extracted_attributes"].keys())
        sorted_attrs = sorted(list(all_attr_names))

        csv_columns = ["external_id", "title", "category", "overall_confidence", "needs_review", "missing_required"] + sorted_attrs

        with open(output_csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(csv_columns)
            for r in results:
                row = [
                    r["external_id"],
                    r["title"],
                    r["category"],
                    r["overall_confidence"],
                    "YES" if r["needs_review"] else "NO",
                    ";".join(r["missing_required"]),
                ]
                for attr in sorted_attrs:
                    row.append(r["extracted_attributes"].get(attr, ""))
                writer.writerow(row)

    print("=" * 70)
    print("✅ ЭКСПОРТ ПРЕДСКАЗАНИЙ УСПЕШНО ЗАВЕРШЁН")
    print("=" * 70)
    print(f"Всего обработано:    {len(results)} карточек")
    print(f"Общее время:         {total_time_ms / 1000.0:.2f} сек ({avg_latency:.1f} мс/карточка)")
    print(f"Требуют ручного ревью: {sum(1 for r in results if r['needs_review'])} из {len(results)}")
    print("-" * 70)
    print(f"📁 JSON-экспорт:     {output_json_path}")
    print(f"📁 CSV-экспорт:      {output_csv_path}")
    print("=" * 70 + "\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Экспорт предсказаний характеристик товаров М.Видео")
    parser.add_argument("--input", default=os.path.join(BASE_DIR, "data", "sample_cards.json"), help="Путь к входному JSON или CSV файлу")
    parser.add_argument("--output-json", default=os.path.join(BASE_DIR, "output", "predictions.json"), help="Путь к результирующему JSON")
    parser.add_argument("--output-csv", default=os.path.join(BASE_DIR, "output", "predictions.csv"), help="Путь к результирующему CSV")
    parser.add_argument("--format", choices=["json", "csv", "both"], default="both", help="Формат экспорта (json, csv, both)")
    parser.add_argument("--use-llm", action="store_true", default=False, help="Активировать Tier 4 LLM fallback (по умолчанию выключен для безопасного офлайн-экспорта без 429)")
    parser.add_argument("--fast", "--offline", "--no-gliner", dest="fast_mode", action="store_true", default=False, help="Быстрый/автономный режим без GLiNER и внешних зависимостей (максимальная скорость)")
    args = parser.parse_args()

    export_predictions(
        input_path=args.input,
        output_json_path=args.output_json if args.format in ("json", "both") else None,
        output_csv_path=args.output_csv if args.format in ("csv", "both") else None,
        use_gliner=not args.fast_mode,
        use_llm=args.use_llm,
    )
