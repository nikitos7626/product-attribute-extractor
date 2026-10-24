# backend/scripts/interactive.py
"""
Интерактивный режим для ручного тестирования извлечения характеристик.

Запуск:
    cd backend
    python -m scripts.interactive
"""
from __future__ import annotations

import json
import os
import sys

# Настройка кодировки для корректного вывода в Windows консоли
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Добавляем путь к backend, если запускается напрямую
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.services.pipeline import CascadedExtractionPipeline

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def print_banner():
    banner_text = (
        "╔══════════════════════════════════════════════════════════════════╗\n"
        "║     E-COMMERCE AI · ИНТЕРАКТИВНЫЙ РЕЖИМ ИЗВЛЕЧЕНИЯ АТРИБУТОВ        ║\n"
        "║     Каскадный пайплайн: Tier 1 (Правила) + Tier 2 (GLiNER)       ║\n"
        "╚══════════════════════════════════════════════════════════════════╝"
    )
    if HAS_RICH:
        console.print(Panel(banner_text, style="bold cyan", expand=False))
    else:
        print(banner_text)
    print("💡 Введите текст карточки товара. Для выхода наберите 'exit' или 'q'.\n")


def format_output(res: dict):
    overall_conf = res.get("overall_confidence", 0.0)
    needs_review = res.get("needs_review", False)
    missing = res.get("missing", [])
    predictions = res.get("predictions", [])

    status_icon = "⚠️ ТРЕБУЕТ ПРОВЕРКИ (HITL)" if needs_review else "✅ ОПУБЛИКОВАНО В КАТАЛОГ"
    status_style = "bold yellow" if needs_review else "bold green"

    if HAS_RICH:
        # Таблица извлеченных характеристик
        table = Table(title="📦 Извлеченные характеристики", show_header=True, header_style="bold magenta")
        table.add_column("Атрибут", style="cyan", width=20)
        table.add_column("Каноническое значение", style="bold white", width=25)
        table.add_column("Уверенность", justify="center", width=12)
        table.add_column("Источник", style="dim", width=12)
        table.add_column("Сырой текст (спан)", style="italic", width=22)

        for p in predictions:
            conf_color = "green" if p["confidence"] >= 0.85 else ("yellow" if p["confidence"] >= 0.70 else "red")
            table.add_row(
                p["attribute"],
                str(p["value"]),
                f"[{conf_color}]{p['confidence']:.2f}[/{conf_color}]",
                p["source"],
                p.get("raw") or "—",
            )

        console.print(table)

        # Информационная сводка
        summary = (
            f"• Статус карточки: [{status_style}]{status_icon}[/{status_style}]\n"
            f"• Общая уверенность: [bold cyan]{overall_conf * 100:.1f}%[/bold cyan]\n"
            f"• Незаполненные обязательные поля: {', '.join(missing) if missing else '[green]Все закрыты (100%)[/green]'}"
        )
        console.print(Panel(summary, title="📊 Итог валидации", expand=False))

        # Сырой JSON
        json_str = json.dumps(res, ensure_ascii=False, indent=2)
        console.print("\n📄 [bold]Финальный JSON для каталога / API:[/bold]")
        console.print(Syntax(json_str, "json", theme="monokai", word_wrap=True))
    else:
        print("\n" + "=" * 50)
        print(f"Статус: {status_icon}")
        print(f"Общая уверенность: {overall_conf:.2f}")
        print(f"Пропущенные поля: {missing or 'Все закрыты'}")
        print("=" * 50)
        print("\nФинальный JSON:")
        print(json.dumps(res, ensure_ascii=False, indent=2))
        print("=" * 50)


def main():
    print_banner()
    print("⏳ Инициализация каскадного пайплайна (загрузка моделей)...")
    pipeline = CascadedExtractionPipeline(use_gliner=True)
    print("✅ Пайплайн готов к работе!\n")

    while True:
        try:
            print("-" * 65)
            title = input("📝 Название товара (Title) [или вставьте весь текст сюда]: ").strip()
            if title.lower() in ("exit", "q", "quit", "выход"):
                print("Выход из интерактивного режима. Удачи!")
                break

            if not title:
                print("⚠️ Текст не может быть пустым. Попробуйте еще раз.")
                continue

            desc = input("📄 Описание (Description) [Enter, если нет]: ").strip()
            if desc.lower() in ("exit", "q", "quit", "выход"):
                print("Выход из интерактивного режима. Удачи!")
                break

            card = {
                "id": "manual-input",
                "title": title,
                "description": desc,
            }

            print("\n⚙️ Обработка карточки...")
            res = pipeline.process_card(card)
            format_output(res)
            print("\n")

        except (KeyboardInterrupt, EOFError):
            print("\nЗавершение работы.")
            break


if __name__ == "__main__":
    main()
