import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.stdout.reconfigure(encoding='utf-8')

from app.services.pipeline import CascadedExtractionPipeline

pipeline = CascadedExtractionPipeline(use_gliner=False, use_llm=False)

test_cards = [
    {"category": "Планшеты", "title": "Планшет Apple iPad Air 11 (2024) Wi-Fi 128GB Space Gray"},
    {"category": "Стиральные машины", "title": "Стиральная машина узкая Haier HW60-BP10929A загрузка 6 кг отжим 1000 об/мин белый"},
    {"category": "Системные блоки", "title": "Системный блок игровой Thunderobot Alpha Core i5-13400F 16GB 512GB SSD RTX 4060"},
    {"category": "Мониторы", "title": "Монитор игровой Xiaomi Curved Gaming Monitor 30\" 2560x1080 200Hz"},
    {"category": "Электрические чайники", "title": "Электрический чайник Tefal Glass KI740B30 1.7 л 2200 Вт серебристый"},
    {"category": "Смарт-часы", "title": "Смарт-часы Apple Watch Series 9 45mm Midnight"},
    {"category": "Матрасы", "title": "Матрас ортопедический Askona 160x200"},
    {"category": "Смесители", "title": "Смеситель для раковины Grohe Eurosmart хром"},
    {"category": "Чехлы для смартфонов", "title": "Чехол для смартфона Apple iPhone 15 силиконовый черный"},
]

print(f"{'Входная категория':25} | {'Категория сервиса':32} | {'Ключевые извлеченные атрибуты'}")
print("-" * 95)

for card in test_cards:
    res = pipeline.process_card(card)
    attrs = [f"{p['attribute']}='{p['value']}'" for p in res['predictions'][:4]]
    attrs_str = ", ".join(attrs) if attrs else "нет атрибутов"
    print(f"{card['category']:25} | {res['category']:32} | {attrs_str}")
