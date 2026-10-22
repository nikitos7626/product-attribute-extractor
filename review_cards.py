#!/usr/bin/env python3
"""
Интерактивный модуль ручной валидации карточек товара (Human-in-the-Loop).
Делегирует исполнение в production-ready модуль scripts.review_queue.

Использование:
  python review_cards.py --summary
  python review_cards.py --input output/predictions.json --output output/reviewed_predictions.json
"""
import sys
from pathlib import Path

# Ensure repo root is in sys.path
_repo_root = Path(__file__).resolve().parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.review_queue import main, print_summary, run_interactive_queue

if __name__ == "__main__":
    main()
