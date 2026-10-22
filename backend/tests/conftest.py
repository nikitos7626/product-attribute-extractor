import sys
from pathlib import Path

# Обеспечиваем доступность как backend/app, так и корневых модулей (extract.py)
BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]

for p in (str(BACKEND_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest


@pytest.fixture(scope="session", autouse=True)
def preserve_tracked_files():
    """Сохраняет исходные файлы артефактов и баз знаний, предотвращая загрязнение git working tree при тестах."""
    preds_p = REPO_ROOT / "output" / "predictions.json"
    rev_p = REPO_ROOT / "output" / "reviewed_predictions.json"
    queue_p = REPO_ROOT / "output" / "review_queue.json"
    kb_p = REPO_ROOT / "backend" / "data" / "dictionaries" / "catalog_models_kb.json"

    orig_preds = preds_p.read_bytes() if preds_p.exists() else None
    orig_rev = rev_p.read_bytes() if rev_p.exists() else None
    orig_queue = queue_p.read_bytes() if queue_p.exists() else None
    orig_kb = kb_p.read_bytes() if kb_p.exists() else None

    yield

    if orig_preds is not None:
        preds_p.write_bytes(orig_preds)
    elif preds_p.exists():
        preds_p.unlink()

    if orig_rev is not None:
        rev_p.write_bytes(orig_rev)
    elif rev_p.exists():
        rev_p.unlink()

    if orig_queue is not None:
        queue_p.write_bytes(orig_queue)
    elif queue_p.exists():
        queue_p.unlink()

    if orig_kb is not None:
        kb_p.write_bytes(orig_kb)
    elif kb_p.exists():
        kb_p.unlink()
