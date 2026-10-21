#!/usr/bin/env python3
"""
CLI & Python entry point for M.Video Product Attribute Extraction Pipeline.
Allows automated evaluators, reviewers, and scripts to extract attributes
and receive clean JSON directly.

Usage examples:
    # 1. Direct text via argument:
    python extract.py "Смартфон Apple iPhone 15 Pro Max 256GB синий титан"

    # 2. Structured title + description:
    python extract.py --title "Смартфон Xiaomi Redmi Note 13" --description "Память 8/256 ГБ, цвет черный, 5000 мАч"

    # 3. Via standard input (stdin / pipe):
    echo "Холодильник LG No Frost серебристый" | python extract.py

    # 4. In Python code:
    from extract import extract_attributes
    result = extract_attributes("Смартфон Samsung Galaxy S24 256GB")
"""

import argparse
import json
import os
import sys
import warnings
from typing import Any, Optional

# Disable Hugging Face download progress bar in stdout
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Ensure UTF-8 output on all operating systems (Windows, Linux, macOS)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Suppress PyTorch warnings for clean CLI output
warnings.filterwarnings("ignore")

# Ensure backend modules can be imported from any working directory
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

try:
    from app.schemas import CardIn, CardOut
    from app.routers.extract import _run
except ImportError as e:
    sys.stderr.write(f"Error importing backend dependencies: {e}\n")
    sys.stderr.write("Make sure you installed backend/requirements.txt\n")
    sys.exit(1)


def extract_attributes(
    text: str = "",
    title: str = "",
    description: str = "",
    seller_attributes: Optional[dict[str, Any]] = None,
    category: Optional[str] = None,
    external_id: Optional[str] = None,
    fast_mode: bool = False,
) -> dict[str, Any]:
    """
    Extract attributes from text/card and return dict matching M.Video JSON schema.
    """
    from app.services.pipeline import CascadedExtractionPipeline
    pipe = CascadedExtractionPipeline(fast_mode=True) if fast_mode else None

    raw_text_val = text if text and not (title and description) else None
    final_title = title or (text if not description else "")
    card = CardIn(
        external_id=external_id,
        category=category,
        title=final_title,
        description=description,
        raw_text=raw_text_val,
        seller_attributes=seller_attributes or {},
    )
    out: CardOut = _run(card, pipeline=pipe)
    return out.model_dump()


def main():
    parser = argparse.ArgumentParser(
        description="M.Video Product Attribute Extraction CLI - Outputs structured JSON"
    )
    parser.add_argument(
        "text",
        nargs="?",
        default=None,
        help="Raw product text or title (e.g. 'Смартфон Apple iPhone 15 Pro Max 256GB')"
    )
    parser.add_argument("--title", "-t", default=None, help="Product title")
    parser.add_argument("--description", "-d", default="", help="Product description")
    parser.add_argument("--category", "-c", default=None, help="Explicit category if known")
    parser.add_argument("--compact", action="store_true", help="Output compact single-line JSON")
    parser.add_argument("--interactive-review", action="store_true", help="Включить интерактивный режим модерации (Human-in-the-Loop) при флаге needs_review")
    parser.add_argument("--fast", "--offline", dest="fast_mode", action="store_true", help="Быстрый автономный режим без загрузки тяжелых ML-моделей (только детерминированные правила Tier 1 и KB)")

    args = parser.parse_args()

    # Determine input text
    title_text = args.title or args.text
    if not title_text:
        if not sys.stdin.isatty():
            title_text = sys.stdin.read().strip()
        else:
            parser.print_help(sys.stderr)
            sys.exit(1)

    if not args.fast_mode and sys.stderr.isatty():
        sys.stderr.write("⚙️ Запуск гибридного пайплайна (для мгновенного offline/fast режима укажите флаг --fast)...\n")

    result = extract_attributes(
        title=title_text,
        description=args.description,
        category=args.category,
        fast_mode=args.fast_mode,
    )

    if args.interactive_review and result.get("needs_review"):
        print("\n" + "=" * 60)
        print("⚠️ КАРТОЧКА ПОМЕЧЕНА ДЛЯ ПРОВЕРКИ (needs_review=True)")
        print(f"Категория: {result.get('category')}, Уверенность: {result.get('overall_confidence')}")
        if result.get("missing"):
            print(f"Недостающие обязательные поля: {', '.join(result['missing'])}")
        print("=" * 60)
        try:
            choice = input("Действие [A]pprove / [E]dit / [S]kip: ").strip().lower()
            if choice in ("a", ""):
                result["needs_review"] = False
                result["reviewed"] = True
                result["review_status"] = "manually_approved"
                print("✓ Карточка утверждена оператором.")
            elif choice == "e":
                attr = input("Введите название атрибута для изменения: ").strip()
                val = input(f"Введите новое значение для '{attr}': ").strip()
                if attr and val:
                    found = False
                    for p in result.get("predictions", []):
                        if p.get("attribute") == attr:
                            p["value"] = val
                            p["confidence"] = 1.0
                            found = True
                            break
                    if not found:
                        result["predictions"].append({
                            "attribute": attr,
                            "value": val,
                            "confidence": 1.0,
                            "source": "manual_review",
                            "grounded": True,
                        })
                    result["needs_review"] = False
                    result["reviewed"] = True
                    result["review_status"] = "edited_and_approved"
                    print(f"✓ Атрибут '{attr}' обновлен. Карточка утверждена.")
        except (EOFError, KeyboardInterrupt):
            pass

    if args.compact:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))



if __name__ == "__main__":
    main()
