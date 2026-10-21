"""
Скрипт расчёта качества извлечения характеристик (Evaluation & Benchmark).
Рассчитывает per-attribute Precision, Recall, F1, Coverage обязательных полей,
общую Accuracy и latency на эталонном gold-сете.
Результаты сохраняются в output/metrics_report.json и output/metrics_report.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from typing import Any

# Добавляем backend в sys.path
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


def _values_match(pred: str, target: str, attr: str) -> bool:
    """Нечёткое сравнение для текстовых атрибутов (модель, CPU) и точное для единиц."""
    p = str(pred).lower().strip().replace(",", ".")
    t = str(target).lower().strip().replace(",", ".")
    if p == t:
        return True
    if attr in ("model", "cpu", "cleaning_type"):
        # Частичное вхождение (например 'Snapdragon 8 Gen 3 for Galaxy' vs 'Snapdragon 8 Gen 3')
        return p in t or t in p
    if attr == "color":
        return p == t or (p == "черный" and t == "чёрный") or (p == "чёрный" and t == "черный")
    if attr == "screen_diagonal":
        p_num = re.sub(r'[^\d.]', '', p)
        t_num = re.sub(r'[^\d.]', '', t)
        if p_num and t_num:
            return abs(float(p_num) - float(t_num)) < 0.15
    if attr == "working_time":
        p_num = re.sub(r'[^\d]', '', p)
        t_num = re.sub(r'[^\d]', '', t)
        return p_num == t_num and p_num != ""
    return False


def run_evaluation(dataset_path: str, output_dir: str = "output", fast_mode: bool = False) -> dict[str, Any]:
    from app.services.pipeline import CascadedExtractionPipeline

    os.makedirs(output_dir, exist_ok=True)

    with open(dataset_path, "r", encoding="utf-8") as f:
        gold_cards = json.load(f)

    pipeline = CascadedExtractionPipeline(fast_mode=fast_mode, use_gliner=not fast_mode)

    per_attr_stats = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "total_target": 0, "total_pred": 0})
    category_matches = 0
    total_cards = len(gold_cards)
    fully_covered_cards = 0
    total_time_ms = 0.0

    print(f"\n🚀 Запуск оценки пайплайна на {total_cards} эталонных карточках ({dataset_path})...\n")

    for item in gold_cards:
        c_in = {
            "external_id": item.get("id"),
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "seller_attributes": item.get("seller_attributes", {}),
        }
        gt = item.get("ground_truth", {})
        gt_category = gt.get("category")

        t0 = time.perf_counter()
        res = pipeline.process_card(c_in)
        latency = (time.perf_counter() - t0) * 1000.0
        total_time_ms += latency

        pred_cat = res.get("category")
        if pred_cat and gt_category and pred_cat.lower() == gt_category.lower():
            category_matches += 1

        preds_dict = {p["attribute"]: p["value"] for p in res.get("predictions", [])}

        if not res.get("needs_review") and len(res.get("missing", [])) == 0:
            fully_covered_cards += 1

        gt_attrs = {k: v for k, v in gt.items() if k != "category"}
        all_attrs = set(gt_attrs.keys()) | set(preds_dict.keys())

        for attr in all_attrs:
            in_gt = attr in gt_attrs
            in_pred = attr in preds_dict

            if in_gt:
                per_attr_stats[attr]["total_target"] += 1
            if in_pred:
                per_attr_stats[attr]["total_pred"] += 1

            if in_gt and in_pred:
                if _values_match(preds_dict[attr], gt_attrs[attr], attr):
                    per_attr_stats[attr]["tp"] += 1
                else:
                    per_attr_stats[attr]["fp"] += 1
                    per_attr_stats[attr]["fn"] += 1
            elif in_pred and not in_gt:
                per_attr_stats[attr]["fp"] += 1
            elif in_gt and not in_pred:
                per_attr_stats[attr]["fn"] += 1

    # Расчет итоговых метрик
    attr_metrics = {}
    total_tp, total_fp, total_fn = 0, 0, 0
    f1_list = []

    for attr, s in sorted(per_attr_stats.items()):
        tp, fp, fn = s["tp"], s["fp"], s["fn"]
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        attr_metrics[attr] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "support": s["total_target"],
        }
        total_tp += tp
        total_fp += fp
        total_fn += fn
        if s["total_target"] > 0:
            f1_list.append(f1)

    macro_f1 = sum(f1_list) / len(f1_list) if f1_list else 0.0
    micro_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    micro_rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    micro_f1 = (2 * micro_prec * micro_rec) / (micro_prec + micro_rec) if (micro_prec + micro_rec) > 0 else 0.0

    cat_acc = category_matches / total_cards if total_cards > 0 else 0.0
    coverage = fully_covered_cards / total_cards if total_cards > 0 else 0.0
    avg_latency_ms = total_time_ms / total_cards if total_cards > 0 else 0.0

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_cards": total_cards,
        "category_accuracy": round(cat_acc, 4),
        "overall_coverage": round(coverage, 4),
        "avg_latency_ms": round(avg_latency_ms, 2),
        "macro_f1": round(macro_f1, 4),
        "micro_f1": round(micro_f1, 4),
        "per_attribute_metrics": attr_metrics,
    }

    # 1. Сохранение JSON
    json_path = os.path.join(output_dir, "metrics_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 2. Сохранение Markdown
    md_path = os.path.join(output_dir, "metrics_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# 📊 Отчёт по качеству извлечения атрибутов М.Видео\n\n")
        f.write(f"- **Дата формирования:** {report['timestamp']}\n")
        f.write(f"- **Всего эталонных карточек:** {total_cards}\n")
        f.write(f"- **Точность классификации категорий:** {cat_acc * 100:.1f}%\n")
        f.write(f"- **Покрытие обязательных полей (Full Coverage):** {coverage * 100:.1f}%\n")
        f.write(f"- **Macro-F1 (среднее по атрибутам):** **{macro_f1:.4f}**\n")
        f.write(f"- **Micro-F1:** **{micro_f1:.4f}**\n")
        f.write(f"- **Средняя скорость обработки:** {avg_latency_ms:.1f} мс/карточка\n\n")
        f.write("## 📋 Per-Attribute Метрики (Precision, Recall, F1)\n\n")
        f.write("| Атрибут | Precision | Recall | F1-Score | Поддержка (Support) |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: |\n")
        for attr, m in attr_metrics.items():
            f.write(f"| `{attr}` | {m['precision']:.3f} | {m['recall']:.3f} | **{m['f1_score']:.3f}** | {m['support']} |\n")

    # 3. Красивый вывод в консоль
    print("=" * 75)
    print("📊 ИТОГОВЫЙ ОТЧЁТ КАЧЕСТВА ИЗВЛЕЧЕНИЯ ХАРАКТЕРИСТИК (М.ВИДЕО)")
    print("=" * 75)
    print(f"Точность категорий (Accuracy):   {cat_acc * 100:.1f}%")
    print(f"Покрытие (Catalog Coverage):     {coverage * 100:.1f}%")
    print(f"Macro-F1 (по всем полям):        {macro_f1:.4f}")
    print(f"Micro-F1 (глобальный):           {micro_f1:.4f}")
    print(f"Средняя скорость:                {avg_latency_ms:.1f} мс / карточка")
    print("-" * 75)
    print(f"{'Атрибут':<20} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10} | {'Support':<8}")
    print("-" * 75)
    for attr, m in attr_metrics.items():
        print(f"{attr:<20} | {m['precision']:<10.3f} | {m['recall']:<10.3f} | {m['f1_score']:<10.3f} | {m['support']:<8}")
    print("=" * 75)
    print(f"💾 Отчёты успешно сохранены:")
    print(f"   • {json_path}")
    print(f"   • {md_path}\n")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Расчет метрик извлечения атрибутов М.Видео")
    parser.add_argument("--dataset", default=os.path.join(BASE_DIR, "data", "gold_dataset.json"), help="Путь к gold датасету")
    parser.add_argument("--output-dir", default=os.path.join(BASE_DIR, "output"), help="Каталог сохранения отчётов")
    parser.add_argument("--fast", "--offline", dest="fast_mode", action="store_true", help="Быстрый/автономный режим оценки без загрузки тяжелых ML-моделей")
    args = parser.parse_args()

    run_evaluation(dataset_path=args.dataset, output_dir=args.output_dir, fast_mode=args.fast_mode)
