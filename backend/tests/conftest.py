import sys
from pathlib import Path

# Обеспечиваем доступность как backend/app, так и корневых модулей (extract.py)
BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]

for p in (str(BACKEND_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)