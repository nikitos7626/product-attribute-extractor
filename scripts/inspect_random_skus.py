import pickle
import random
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.stdout.reconfigure(encoding='utf-8')

from app.services.pipeline import CascadedExtractionPipeline

import argparse
import os

REPO_ROOT = Path(__file__).resolve().parent.parent

parser = argparse.ArgumentParser(description="Инспекция случайных товаров из skus.pkl")
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
    print("ℹ️ Файл skus.pkl не обнаружен. Для инспекции случайных карточек используйте: python scripts/evaluate_catalog_sample.py")
    sys.exit(0)

print(f"Загрузка {skus_file} (546 тыс. товаров)...")
with open(skus_file, 'rb') as f:
    data = pickle.load(f)

categories = data['yml_catalog']['shop']['categories']['category']
cat_map = {c['@id']: c['#text'] for c in categories}
offers = data['yml_catalog']['shop']['offers']['offer']

# Initialize pipeline (fast Tier 1 + KB + GLiNER)
pipeline = CascadedExtractionPipeline(use_gliner=True, use_llm=False)

# Target categories to inspect
target_cats = [
    "Смартфоны",
    "Ноутбуки",
    "Телевизоры",
    "Холодильники",
    "Роботы-пылесосы",
    "Наушники",
    "Внешние аккумуляторы",
    "Микроволновые печи соло"
]

# Group offers by category
grouped = {c: [] for c in target_cats}
for o in offers:
    cats = o.get('categories', {})
    cid = cats.get('categoryId') if isinstance(cats, dict) else None
    cname = cat_map.get(cid, '')
    if cname in grouped:
        grouped[cname].append(o)

print("\n" + "="*80)
print("ПРОВЕРКА В РЕАЛЬНОМ ВРЕМЕНИ НА СЛУЧАЙНЫХ ТОВАРАХ ИЗ КАТАЛОГА М.ВИДЕО")
print("="*80)

random.seed(42)  # Воспроизводимый сид

for cname in target_cats:
    pool = grouped[cname]
    if not pool:
        continue
    sample = random.choice(pool)
    name = sample.get('name', '')
    desc = sample.get('description', '')
    if isinstance(desc, str) and len(desc) > 150:
        desc_short = desc[:150] + "..."
    else:
        desc_short = str(desc)

    # Raw seller params
    raw_params = []
    params = sample.get('param', [])
    if isinstance(params, dict):
        params = [params]
    for p in params:
        if isinstance(p, dict) and '@name' in p and '#text' in p:
            if not any(k in p['@name'] for k in ['бонус', 'Подборки', 'коллекция', 'Продавец']):
                raw_params.append(f"{p['@name']}: {p['#text']}")

    # Run extraction through our pipeline
    card_input = {
        "title": name,
        "description": desc or name,
        "category": cname,
        "raw_text": f"{name}\n{desc or ''}"
    }
    result = pipeline.process_card(card_input)

    print(f"\n[{cname.upper()}]")
    print(f"  Товар: {name}")
    print(f"  Параметры в каталоге М.Видео (raw): {', '.join(raw_params[:6]) if raw_params else 'нет явных параметров'}")
    print(f"  -> Извлечено системой:")
    print(f"     Категория: {result['category']} (уверенность: {result['overall_confidence']:.2f}, needs_review: {result['needs_review']})")
    for p in result['predictions']:
        print(f"     • {p['attribute']}: {p['value']} (conf: {p['confidence']:.2f}, src: {p.get('source', 'tier1')})")
    if result['missing']:
        print(f"     ⚠️ Не найдены обязательные: {result['missing']}")
