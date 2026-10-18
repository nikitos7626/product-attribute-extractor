import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.services.pipeline import CascadedExtractionPipeline

pipeline = CascadedExtractionPipeline(use_gliner=True, use_llm=False)

case_1_text = """НБ ASUS TUF Gaming A15 FA507NU-LP031 (15.6" FHD IPS 144Гц, Ryzen 7 7735HS, 16ГБ DDR5, SSD 512ГБ, GeForce RTX 4050 для ноутбуков 6ГБ, Без ОС, Серый, 90NR0EB5-M002S0). Игровой ноутбук серии ASUS TUF Gaming A15 в цвете Mecha Gray создан для серьезного гейминга. В максимальных конфигурациях линейки устанавливается до 32 ГБ оперативной памяти и два твердотельных накопителя суммарным объемом до 2 ТБ. Дискретная видеокарта NVIDIA GeForce RTX 4050 с 6 ГБ видеопамяти GDDR6 и поддержкой DLSS 3 обеспечивает высокий фреймрейт. Поставляется без предустановленной операционной системы (рекомендуется установка Windows 11 Домашняя)."""

case_2_text = """Смартфон POCO X6 Pro 5G (глобальная версия, не путать с обычным Redmi Note 13 или базовым Poco X6!). Хит продаж, который по плавности работы не уступает Apple iPhone 15 Pro Max и Samsung Galaxy S24 в корпусе титановый черный! Внимание: у нас в продаже редкая старшая конфигурация — не 8/256 ГБ как у большинства продавцов, а полноценные 12 гигабайт оперативки и накопитель на полтерабайта! (также в соседнем лоте есть версия с расширением флешки до 1024 ГБ). Экран кристально чистый AMOLED, диагональ 6.67" (смотрится компактнее громоздких лопат на 6.8 дюйма, разрешение 2712x1220), честная герцовка 120 Гц — забудьте про старые дерганые матрицы на 60Hz и 90Hz! Под капотом зверский чип MediaTek Dimensity 8300-Ultra (рвет в клочья популярный Snapdragon 7s Gen 2). Цвет корпуса: сочный Желтый, задняя крышка из экокожи (в подарок идет защитный чехол темно-синий). Внутри мощный аккумулятор 5000 мАч (быстрая зарядка в комплекте, вам больше не придется таскать с собой тяжелый пауэрбанк на 10000 мА*ч!)."""

print("=== CASE 1 ===")
res1 = pipeline.process_card({"raw_text": case_1_text})
print(json.dumps(res1, ensure_ascii=False, indent=2))

print("\n=== CASE 2 ===")
res2 = pipeline.process_card({"raw_text": case_2_text})
print(json.dumps(res2, ensure_ascii=False, indent=2))
