"""
Интерактивный инструмент ручной модерации характеристик (Human-in-the-Loop Review Queue).
Позволяет контент-менеджерам и модераторам быстро проверять карточки,
помеченные флагом needs_review=True, редактировать значения и утверждать результат.

Использование:
  python scripts/review_queue.py --summary
  python scripts/review_queue.py --input output/predictions.json --output output/reviewed_predictions.json
  python scripts/review_queue.py --auto-approve-conf 0.92
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def print_summary(items: list[dict[str, Any]]) -> None:
    """Выводит аналитическую сводку по очереди ручной модерации."""
    total = len(items)
    needs_review = [it for it in items if it.get("needs_review") is True]
    approved_auto = total - len(needs_review)

    categories: dict[str, int] = {}
    missing_counter: dict[str, int] = {}

    for it in needs_review:
        cat = it.get("category") or "Не определена"
        categories[cat] = categories.get(cat, 0) + 1
        for m in it.get("missing_required", []):
            missing_counter[m] = missing_counter.get(m, 0) + 1

    print("=" * 70)
    print("📊 СВОДКА ОЧЕРЕДИ МОДЕРАЦИИ (HITL REVIEW QUEUE SUMMARY)")
    print("=" * 70)
    print(f"Всего карточек в файле:          {total}")
    print(f"Автоматически подтверждено:      {approved_auto} ({approved_auto / total * 100:.1f}%)" if total else 0)
    print(f"Требуют ручной проверки:         {len(needs_review)} ({len(needs_review) / total * 100:.1f}%)" if total else 0)
    print("-" * 70)
    print("Распределение карточек на проверку по категориям:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  • {cat:<30}: {count} шт.")
    if missing_counter:
        print("-" * 70)
        print("Топ недостающих обязательных полей:")
        for attr, count in sorted(missing_counter.items(), key=lambda x: -x[1])[:10]:
            print(f"  • {attr:<25}: {count} раз")
    print("=" * 70 + "\n")


def run_interactive_queue(
    input_path: str,
    output_path: str,
    auto_approve_conf: float | None = None,
    flagged_only_path: str | None = None,
) -> None:
    """Запускает интерактивную сессию проверки или автоматический фильтр."""
    if not os.path.exists(input_path):
        print(f"❌ Ошибка: файл {input_path} не найден.")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items: list[dict[str, Any]] = data.get("items", []) if isinstance(data, dict) else data

    if flagged_only_path:
        flagged = [it for it in items if it.get("needs_review") is True]
        os.makedirs(os.path.dirname(os.path.abspath(flagged_only_path)), exist_ok=True)
        with open(flagged_only_path, "w", encoding="utf-8") as f:
            json.dump({"total_flagged": len(flagged), "items": flagged}, f, ensure_ascii=False, indent=2)
        print(f"✅ Сохранено {len(flagged)} карточек на модерацию в: {flagged_only_path}")
        return

    # Авто-подтверждение по порогу, если запрошено
    if auto_approve_conf is not None:
        auto_count = 0
        for it in items:
            conf = it.get("overall_confidence", 0.0)
            missing = it.get("missing_required", [])
            if it.get("needs_review") and conf >= auto_approve_conf and not missing:
                it["needs_review"] = False
                it["reviewed"] = True
                it["review_status"] = "auto_approved_by_confidence"
                auto_count += 1
        print(f"⚡ Автоматически подтверждено {auto_count} карточек с уверенностью >= {auto_approve_conf}")

    queue = [it for it in items if it.get("needs_review") is True]
    if not queue:
        print("🎉 В очереди нет карточек, требующих ручной модерации!")
        return

    print_summary(items)
    print(f"▶ Начинаем интерактивную проверку ({len(queue)} карточек).")
    print("Команды: [A]pprove (утвердить) | [E]dit (изменить поле) | [S]kip (пропустить) | [Q]uit (сохранить и выйти)\n")

    reviewed_count = 0

    for idx, card in enumerate(queue, 1):
        ext_id = card.get("external_id")
        title = card.get("title")
        cat = card.get("category")
        conf = card.get("overall_confidence")
        missing = card.get("missing_required", [])
        extracted = card.get("extracted_attributes", {})

        print("=" * 70)
        print(f"Карточка {idx}/{len(queue)} | ID: {ext_id} | Категория: {cat} | Уверенность: {conf:.2f}")
        print(f"Название: {title}")
        print("-" * 70)
        print("Извлеченные атрибуты:")
        for attr, val in sorted(extracted.items()):
            print(f"  • {attr:<20}: {val}")
        if missing:
            print(f"⚠️ Недостающие обязательные поля: {', '.join(missing)}")
        print("-" * 70)

        while True:
            try:
                choice = input("Действие [A/e/s/q]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "q"

            if choice in ("a", ""):
                card["needs_review"] = False
                card["reviewed"] = True
                card["review_timestamp"] = datetime.datetime.now().isoformat()
                card["review_status"] = "manually_approved"
                reviewed_count += 1
                print("  ✓ Карточка утверждена.\n")
                break
            elif choice == "e":
                attr_to_edit = input("  Введите название атрибута: ").strip()
                if attr_to_edit:
                    new_val = input(f"  Введите новое значение для '{attr_to_edit}': ").strip()
                    if new_val:
                        card["extracted_attributes"][attr_to_edit] = new_val
                        if attr_to_edit in card.get("missing_required", []):
                            card["missing_required"].remove(attr_to_edit)
                        card["needs_review"] = False
                        card["reviewed"] = True
                        card["review_timestamp"] = datetime.datetime.now().isoformat()
                        card["review_status"] = "edited_and_approved"
                        reviewed_count += 1
                        print(f"  ✓ Атрибут '{attr_to_edit}' обновлен на '{new_val}'. Карточка утверждена.\n")
                        break
            elif choice == "s":
                print("  ↷ Карточка пропущена.\n")
                break
            elif choice == "q":
                print("\n💾 Сохранение результатов модерации...")
                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "metadata": {
                                "timestamp": datetime.datetime.now().isoformat(),
                                "total_items": len(items),
                                "reviewed_in_session": reviewed_count,
                            },
                            "items": items,
                        },
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )
                print(f"✅ Сохранено в {output_path}. Завершение работы.")
                return
            else:
                print("Неизвестная команда. Введите 'a' (утвердить), 'e' (изменить), 's' (пропустить) или 'q' (выйти).")

    # Сохранение после прохода всех карточек
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "total_items": len(items),
                    "reviewed_in_session": reviewed_count,
                },
                "items": items,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"✅ Все карточки обработаны! Результат сохранен в: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Интерактивная очередь ручной проверки характеристик (HITL Review Queue)")
    parser.add_argument("--input", default=os.path.join(BASE_DIR, "output", "predictions.json"), help="Путь к файлу предсказаний")
    parser.add_argument("--output", default=os.path.join(BASE_DIR, "output", "reviewed_predictions.json"), help="Путь для сохранения проверенных данных")
    parser.add_argument("--summary", action="store_true", help="Вывести только аналитическую сводку по очереди")
    parser.add_argument("--flagged-only", help="Экспортировать только требующие проверки карточки в отдельный файл")
    parser.add_argument("--auto-approve-conf", type=float, help="Порог уверенности для пакетного авто-подтверждения (например 0.90)")

    args = parser.parse_args()

    if args.summary:
        if not os.path.exists(args.input):
            print(f"❌ Файл {args.input} не найден.")
            sys.exit(1)
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items", []) if isinstance(data, dict) else data
        print_summary(items)
    else:
        run_interactive_queue(
            input_path=args.input,
            output_path=args.output,
            auto_approve_conf=args.auto_approve_conf,
            flagged_only_path=args.flagged_only,
        )


if __name__ == "__main__":
    main()
