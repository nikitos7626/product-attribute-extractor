import pickle
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')

print("Loading skus.pkl...")
with open(r'c:\Users\nikit\Downloads\cu_ws\skus.pkl', 'rb') as f:
    data = pickle.load(f)

categories = data['yml_catalog']['shop']['categories']['category']
cat_map = {c['@id']: c['#text'] for c in categories}
offers = data['yml_catalog']['shop']['offers']['offer']

print(f"Total offers in dataset: {len(offers):,}")
print(f"Total category definitions: {len(categories):,}")

# 1. Count offers per category
cat_counts = Counter()
cat_offers = defaultdict(list)

for o in offers:
    cats = o.get('categories', {})
    cid = cats.get('categoryId') if isinstance(cats, dict) else None
    cname = cat_map.get(cid, 'Unknown')
    cat_counts[cname] += 1
    if len(cat_offers[cname]) < 50:
        cat_offers[cname].append(o)

print("\n" + "="*80)
print("1. TOP TARGET CATEGORIES IN skus.pkl (Электроника и бытовая техника)")
print("="*80)

# Filter targets related to consumer tech / electronics
target_keywords = [
    "смартфон", "ноутбук", "телевизор", "холодильник", 
    "пылесос", "наушник", "аккумулятор", "микроволнов",
    "планшет", "стиральн", "посудомоечн", "монитор", "видеокарт", "процессор"
]

matched_cats = {}
for cname, count in cat_counts.most_common():
    lower = cname.lower()
    for kw in target_keywords:
        if kw in lower:
            matched_cats[cname] = (count, kw)
            break

for cname, (count, kw) in sorted(matched_cats.items(), key=lambda x: -x[1][0])[:35]:
    print(f"  [{count:>6,} шт.] {cname}")

print("\n" + "="*80)
print("2. REAL PARAMETERS IN skus.pkl FOR OUR 8 TARGET CATEGORIES")
print("="*80)

def analyze_category_params(cat_name):
    param_counter = Counter()
    sample_offers = cat_offers.get(cat_name, [])
    for o in sample_offers:
        params = o.get('param', [])
        if isinstance(params, dict):
            params = [params]
        for p in params:
            if isinstance(p, dict) and '@name' in p:
                param_counter[p['@name']] += 1
    return param_counter

key_mvideo_categories = [
    "Смартфоны",
    "Ноутбуки",
    "Телевизоры",
    "Холодильники",
    "Роботы-пылесосы",
    "Наушники",
    "Внешние аккумуляторы",
    "Микроволновые печи"
]

for cat in key_mvideo_categories:
    params = analyze_category_params(cat)
    top_p = [f"{p} ({cnt})" for p, cnt in params.most_common(8)]
    print(f"\nКатегория: «{cat}» ({cat_counts.get(cat, 0):,} офферов в каталоге)")
    print(f"  Топ параметров в каталоге М.Видео:")
    if top_p:
        for p_str in top_p:
            print(f"    - {p_str}")
    else:
        print("    (Параметры отсутствуют или лежат в описании)")
