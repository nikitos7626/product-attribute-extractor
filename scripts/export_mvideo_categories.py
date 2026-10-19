import json
import pickle
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

import argparse
import os

REPO_ROOT = Path(__file__).resolve().parent.parent

parser = argparse.ArgumentParser(description="Экспорт категорий М.Видео из skus.pkl")
parser.add_argument("--skus-path", type=str, default=None, help="Путь к файлу skus.pkl")
args = parser.parse_args()

skus_candidates = [
    Path(args.skus_path) if args.skus_path else None,
    Path(os.environ["SKUS_PATH"]) if "SKUS_PATH" in os.environ else None,
    REPO_ROOT / "data" / "skus.pkl",
    Path("skus.pkl"),
]
skus_file = next((p for p in skus_candidates if p and p.is_file()), None)

if not skus_file:
    print("ℹ️ Файл skus.pkl не обнаружен. Категории уже экспортированы в backend/data/dictionaries/mvideo_categories.json.")
    sys.exit(0)

print(f"Extracting full M.Video category tree from {skus_file}...")
with open(skus_file, 'rb') as f:
    data = pickle.load(f)

categories = data['yml_catalog']['shop']['categories']['category']
print(f"Total category definitions: {len(categories):,}")

# Structure:
# id_to_name: {id: name}
# id_to_parent: {id: parent_id}
# all_categories: list of unique clean names
id_to_name = {}
id_to_parent = {}
unique_names = set()

for c in categories:
    cid = str(c.get('@id', '')).strip()
    name = str(c.get('#text', '')).strip()
    pid = str(c.get('@parentId', '')).strip()
    if cid and name:
        id_to_name[cid] = name
        unique_names.add(name)
        if pid:
            id_to_parent[cid] = pid

out_path = REPO_ROOT / 'backend' / 'data' / 'dictionaries' / 'mvideo_categories.json'
out_path.parent.mkdir(parents=True, exist_ok=True)

with open(out_path, 'w', encoding='utf-8') as f:
    json.dump({
        "total_categories": len(unique_names),
        "id_to_name": id_to_name,
        "id_to_parent": id_to_parent,
        "all_names": sorted(list(unique_names))
    }, f, ensure_ascii=False, indent=2)

print(f"Successfully saved {len(unique_names):,} unique categories to {out_path}")
