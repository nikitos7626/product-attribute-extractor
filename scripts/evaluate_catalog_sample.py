import argparse
import json
import random
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.stdout.reconfigure(encoding='utf-8')

from app.services.pipeline import CascadedExtractionPipeline


def normalize_val(val: str) -> str:
    if not val:
        return ""
    v = str(val).lower().strip()
    v = v.replace("ё", "е").replace("—", "-").replace("−", "-")
    v = v.replace("гб", "gb").replace("tb", "тб")
    v = v.replace(" ", "")
    return v


def main():
    parser = argparse.ArgumentParser(description="Динамическая оценка точности на случайной выборке реального каталога М.Видео")
    parser.add_argument("--category", type=str, default="smartphones", help="Категория (smartphones, laptops, tvs, tablets, monitors, desktops, headphones, refrigerators, powerbanks, all)")
    parser.add_argument("--size", type=int, default=13, help="Количество случайных карточек для теста (по умолчанию 13)")
    parser.add_argument("--seed", type=int, default=None, help="Сид рандома (для повторяемости, если не указан — случайный каждый раз)")
    args = parser.parse_args()

    pool_path = Path(__file__).parent.parent / "data" / "catalog_eval_pool.json"
    if not pool_path.is_file():
        print(f"Ошибка: файл пула {pool_path} не найден. Сначала запустите scripts/build_catalog_eval_pool.py")
        sys.exit(1)

    with open(pool_path, "r", encoding="utf-8") as f:
        pool = json.load(f)

    if args.seed is not None:
        random.seed(args.seed)

    # Выбираем товары
    sample_cards = []
    if args.category == "all":
        # Равномерно по всем категориям
        per_cat = max(1, args.size // len(pool))
        for cat_k, items in pool.items():
            sample_cards.extend(random.sample(items, min(len(items), per_cat)))
    else:
        cat_items = pool.get(args.category)
        if not cat_items:
            print(f"Категория {args.category} не найдена в пуле. Доступны: {list(pool.keys())}")
            sys.exit(1)
        sample_cards = random.sample(cat_items, min(len(cat_items), args.size))

    pipeline = CascadedExtractionPipeline(use_gliner=False, use_llm=False)

    print("=" * 85)
    print(f"🎲 СЛУЧАЙНАЯ ВЫБОРКА: {len(sample_cards)} РЕАЛЬНЫХ ТОВАРОВ ИЗ КАТАЛОГА М.ВИДЕО (категория: {args.category})")
    print("=" * 85)

    total_gt_points = 0
    total_found_points = 0
    total_exact_matches = 0

    per_attr_gt = {}
    per_attr_matches = {}

    for idx, card in enumerate(sample_cards, 1):
        name = card["title"]
        desc = card["description"]
        gt = card["params"]

        # Подаём только сырой текст названия и описания
        input_card = {
            "title": name,
            "description": desc or name,
            "category": card["category_name"]
        }
        res = pipeline.process_card(input_card)
        pred_map = {p["attribute"]: p["value"] for p in res["predictions"]}

        print(f"\n[{idx}/{len(sample_cards)}] {name[:75]}")
        for attr, true_val in gt.items():
            total_gt_points += 1
            per_attr_gt[attr] = per_attr_gt.get(attr, 0) + 1
            pred_val = pred_map.get(attr)

            if pred_val is not None:
                total_found_points += 1
                norm_true = normalize_val(true_val)
                norm_pred = normalize_val(pred_val)

                # Проверка на совпадение (полное или вхождение)
                is_match = (norm_true in norm_pred) or (norm_pred in norm_true)
                if is_match:
                    total_exact_matches += 1
                    per_attr_matches[attr] = per_attr_matches.get(attr, 0) + 1
                    status = "✅ Совпало"
                else:
                    status = "⚠️ Частично / Различие форматов"
                print(f"   • {attr:15}: истина={true_val!r:18} | система={pred_val!r:18} -> {status}")
            else:
                print(f"   • {attr:15}: истина={true_val!r:18} | система=ПРОПУСК В ТЕКСТЕ")

    print("\n" + "=" * 85)
    print("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ СЛУЧАЙНОГО СРЕЗА")
    print("=" * 85)
    recall = (total_found_points / total_gt_points * 100) if total_gt_points else 0
    precision = (total_exact_matches / total_found_points * 100) if total_found_points else 0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0

    print(f"Всего контрольных точек параметров М.Видео: {total_gt_points}")
    print(f"Извлечено системой из текста:               {total_found_points} (Полнота Recall: {recall:.1f}%)")
    print(f"Точно совпало со спецификацией каталога:     {total_exact_matches} (Точность Precision: {precision:.1f}%)")
    print(f"Реальный F1-Score на случайной выборке:      {f1:.1f}%")
    print("-" * 85)


if __name__ == "__main__":
    main()
