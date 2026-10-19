import json
import pickle
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

import argparse
import os

REPO_ROOT = Path(__file__).resolve().parent.parent

parser = argparse.ArgumentParser(description="Создание пула валидации из skus.pkl")
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
    print("ℹ️ Файл skus.pkl не обнаружен. Пул валидации уже предсобран в data/catalog_eval_pool.json.")
    print("  Для повторной генерации укажите путь: python scripts/build_catalog_eval_pool.py --skus-path /path/to/skus.pkl")
    sys.exit(0)

print(f"Загрузка {skus_file} для создания пула валидации...")
with open(skus_file, 'rb') as f:
    data = pickle.load(f)

categories = data['yml_catalog']['shop']['categories']['category']
cat_map = {c['@id']: c['#text'] for c in categories}
offers = data['yml_catalog']['shop']['offers']['offer']

# Маппинг категорий каталога на ключи пайплайна
TARGET_CATS = {
    "Смартфоны": "smartphones",
    "Ноутбуки": "laptops",
    "Телевизоры": "tvs",
    "Холодильники": "refrigerators",
    "Роботы-пылесосы": "vacuum_cleaners",
    "Наушники": "headphones",
    "Внешние аккумуляторы": "powerbanks",
    "Микроволновые печи соло": "microwaves",
    "Планшеты": "tablets",
    "Стиральные машины": "washing_machines",
    "Мониторы": "monitors",
    "Системные блоки": "desktops",
    "Смарт-часы": "smart_watches",
    "Электрические чайники": "kettles",
}

# Маппинг тегов param М.Видео на наши атрибуты
PARAM_NAME_MAP = {
    "встроенная память": "memory_rom",
    "встроенная память (rom)": "memory_rom",
    "объём встроенной памяти": "memory_rom",
    "объём ssd": "memory_rom",
    "объем ssd": "memory_rom",
    "жесткий диск (hdd)": "memory_rom",
    "оперативная память": "memory_ram",
    "оперативная память (ram)": "memory_ram",
    "объем оперативной памяти": "memory_ram",
    "цвет": "color",
    "емкость аккумулятора": "battery",
    "диагональ экрана": "screen_diagonal",
    "диагональ": "screen_diagonal",
    "разрешение экрана": "resolution",
    "частота обновления экрана": "refresh_rate",
    "тип процессора": "cpu",
    "производитель процессора": "cpu_brand",
    "видеокарта": "gpu",
    "тип уборки": "cleaning_type",
    "размораживание холодильной камеры": "defrost_system",
    "система no frost": "defrost_system",
    "максимальная загрузка": "load_capacity",
    "скорость отжима": "spin_speed",
    "объем": "volume",
    "мощность": "power",
    "тип подключения": "connection_type",
}

pool = defaultdict(list)

for o in offers:
    cats = o.get('categories', {})
    cid = cats.get('categoryId') if isinstance(cats, dict) else None
    cname = cat_map.get(cid, '')
    if cname not in TARGET_CATS:
        continue
    
    cat_key = TARGET_CATS[cname]
    params = o.get('param', [])
    if isinstance(params, dict):
        params = [params]
        
    ground_truth = {}
    for p in params:
        if isinstance(p, dict) and '@name' in p and '#text' in p:
            k = p['@name'].strip().lower()
            if k in PARAM_NAME_MAP:
                ground_truth[PARAM_NAME_MAP[k]] = str(p['#text']).strip()
                
    if len(ground_truth) >= 2 and o.get('name'):
        pool[cat_key].append({
            "id": o.get('@id'),
            "category_name": cname,
            "category_key": cat_key,
            "title": o.get('name', ''),
            "description": o.get('description', ''),
            "vendor": o.get('vendor', ''),
            "model": o.get('model', ''),
            "params": ground_truth
        })

print("\nСобрано карточек в пул по категориям:")
total_items = 0
final_pool = {}
for cat_key, items in pool.items():
    # Сохраняем до 80 карточек на категорию для быстрого доступа
    random.seed(42)
    selected = random.sample(items, min(len(items), 80))
    final_pool[cat_key] = selected
    total_items += len(selected)
    print(f"  • {cat_key:18}: {len(selected):>3} шт. (из {len(items):,} доступных)")

out_file = REPO_ROOT / "data" / "catalog_eval_pool.json"
out_file.parent.mkdir(parents=True, exist_ok=True)
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(final_pool, f, ensure_ascii=False, indent=2)

print(f"\nУспешно сохранён пул из {total_items:,} реальных товаров М.Видео в {out_file}")
