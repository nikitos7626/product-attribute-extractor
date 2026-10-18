import sys
import os

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.pipeline import CascadedExtractionPipeline

pipeline = CascadedExtractionPipeline(use_gliner=True, use_catalog_enricher=True, use_llm=False)

cards = [
    {
        "title": "Беспроводные наушники Moondrop Space Travel TWS 13mm Bluetooth 5.3 черный",
        "description": "Стильные полностью беспроводные наушники с активным шумоподавлением ANC до 35 дБ. Большие 13-мм титановые динамики. Время работы до 12 часов с зарядным кейсом. Сенсорное управление, прозрачный режим.",
    },
    {
        "title": "Мини-ПК Geekom Mini IT13 Core i9-13900H 32GB/1TB SSD Windows 11 Pro серый",
        "description": "Компактный системный блок для работы и игр. Процессор Intel Core i9 13-го поколения, 32 ГБ оперативной памяти DDR4, быстрый накопитель 1 ТБ M.2 PCIe NVMe. Поддержка Wi-Fi 6E и двух экранов 8K.",
    },
    {
        "title": "Внешний аккумулятор Cuktech 10 Power Bank PB100P 10000mAh 100W серый",
        "description": "Портативный аккумулятор высокой мощности 100 Вт с цифровым TFT-дисплеем. Емкость 10000 мАч, поддержка протоколов PD 3.0 и PPS. Компактный корпус, вес всего 287 г.",
    }
]

print("=" * 80)
print("🔍 ТЕСТИРОВАНИЕ НА ТОВАРАХ, КОТОРЫХ НЕТ В КАТАЛОГЕ М.ВИДЕО И НЕТ В СЛОВАРЕ БРЕНДОВ")
print("=" * 80)

for i, c in enumerate(cards, 1):
    res = pipeline.process_card(c)
    print(f"\n[ТОВАР #{i}] {c['title']}")
    print(f"  📁 Категория:         {res.get('category')}")
    print(f"  ⭐ Общая уверенность: {round(res.get('overall_confidence', 0), 4)}")
    print(f"  👀 needs_review:      {res.get('needs_review')}")
    print("  📋 Извлечённые атрибуты:")
    for p in res.get("predictions", []):
        attr = p["attribute"]
        val = p["value"]
        conf = round(p["confidence"], 2)
        src = p.get("source")
        print(f"     • {attr:<16} : {val:<25} | conf={conf:<4} | source={src}")
print("\n" + "=" * 80)
