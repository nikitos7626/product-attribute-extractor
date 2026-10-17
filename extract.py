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
) -> dict[str, Any]:
    """
    Extract attributes from text/card and return dict matching M.Video JSON schema.
    """
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
    out: CardOut = _run(card)
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

    args = parser.parse_args()

    # Determine input text
    title_text = args.title or args.text
    if not title_text:
        if not sys.stdin.isatty():
            title_text = sys.stdin.read().strip()
        else:
            parser.print_help(sys.stderr)
            sys.exit(1)

    result = extract_attributes(
        title=title_text,
        description=args.description,
        category=args.category,
    )

    if args.compact:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
