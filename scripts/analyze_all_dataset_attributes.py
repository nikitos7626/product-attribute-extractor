import pickle
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')

print("Загрузка skus.pkl...")
with open(r'c:\Users\nikit\Downloads\cu_ws\skus.pkl', 'rb') as f:
    data = pickle.load(f)

categories = data['yml_catalog']['shop']['categories']['category']
cat_map = {c['@id']: c['#text'] for c in categories}
offers = data['yml_catalog']['shop']['offers']['offer']

print(f"Всего товаров в датасете: {len(offers):,}")

# Статистика по категориям:
# - total_offers
# - offers_with_params
# - unique_param_names
cat_total = Counter()
cat_with_params = Counter()
cat_param_names = defaultdict(Counter)

# Игнорируем маркетинговые параметры ("бонусы", "акции", "подборки", "продавец")
MARKETING_PARAMS = {
    'потратить бонусы', 'подборки', 'топ коллекция', 'акции', 'продавец', 
    'состояние', 'быстрая доставка', 'гарантия'
}

for o in offers:
    cats = o.get('categories', {})
    cid = cats.get('categoryId') if isinstance(cats, dict) else None
    cname = cat_map.get(cid, 'Неизвестно')
    cat_total[cname] += 1
    
    params = o.get('param', [])
    if isinstance(params, dict):
        params = [params]
    
    tech_params = []
    for p in params:
        if isinstance(p, dict) and '@name' in p:
            pname = p['@name'].strip()
            if pname.lower() not in MARKETING_PARAMS:
                tech_params.append(pname)
                cat_param_names[cname][pname] += 1
                
    if tech_params:
        cat_with_params[cname] += 1

print("\n" + "="*85)
print("ТОП КАТЕГОРИЙ В ДАТАСЕТЕ С НАИБОЛЬШИМ ЧИСЛОМ ТЕХНИЧЕСКИХ ХАРАКТЕРИСТИК (СПЕЦИФИКАЦИЙ)")
print("="*85)
print(f"{'Категория':35} | {'Товаров':>8} | {'С параметрами':>13} | {'Уникальных параметров':>22}")
print("-" * 85)

# Сортируем категории по количеству офферов с заполненными параметрами
sorted_cats = sorted(cat_with_params.items(), key=lambda x: -x[1])

for cname, with_p in sorted_cats[:40]:
    total = cat_total[cname]
    num_unique_params = len(cat_param_names[cname])
    pct = (with_p / total * 100) if total else 0
    print(f"{cname[:35]:35} | {total:>8,} | {with_p:>7,} ({pct:4.1f}%) | {num_unique_params:>22}")

print("\n" + "="*85)
print("ДЕТАЛИЗАЦИЯ: КАКИЕ ИМЕННО АТРИБУТЫ ОПИСАНЫ В ТОПОВЫХ КАТЕГОРИЯХ")
print("="*85)

for cname, _ in sorted_cats[:15]:
    top_attrs = [f"{p} ({cnt:,})" for p, cnt in cat_param_names[cname].most_common(7)]
    print(f"\n[{cname}] (Всего товаров: {cat_total[cname]:,})")
    print(f"  Ключевые атрибуты: {', '.join(top_attrs)}")
