import json
import os
import sys

# UTF-8 вывод для Windows
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services.pipeline import CascadedExtractionPipeline

# Реальные текстовые описания товаров с официального сайта М.Видео (mvideo.ru)
MVIDEO_PRODUCTS = [
    {
        "category_expected": "smartphones",
        "title": "Смартфон Samsung Galaxy S24 Ultra 12/512GB Titanium Gray (SM-S928)",
        "description": """Смартфон Samsung Galaxy S24 Ultra 12/512GB Titanium Gray оснащен безрамочным экраном Dynamic AMOLED 2X диагональю 6.8 дюйма с разрешением 3120x1440 пикселей и адаптивной частотой обновления 120 Гц. Прочный титановый корпус серого цвета защищен по стандарту IP68. Производительность обеспечивает 8-ядерный процессор Snapdragon 8 Gen 3 for Galaxy в сочетании с 12 ГБ оперативной памяти и 512 ГБ встроенной памяти. Устройство работает под управлением операционной системы Android 14 с оболочкой One UI 6.1 и встроенным искусственным интеллектом Galaxy AI. Основная квадрокамера с главным сенсором на 200 Мп поддерживает оптическую стабилизацию и 100-кратный зум Space Zoom. Литий-ионный аккумулятор емкостью 5000 мАч обеспечивает автономность на весь день.""",
    },
    {
        "category_expected": "laptops",
        "title": "Ноутбук HUAWEI MateBook D 16 2024 MCLG-X 16/512GB космический серый",
        "description": """Ноутбук HUAWEI MateBook D 16 2024 MCLG-X выполнен в тонком металлическом корпусе цвета «космический серый» и весит 1.68 кг. Устройство оборудовано IPS-экраном диагональю 16.0" с разрешением 1920x1200 и соотношением сторон 16:10. Высокое быстродействие обеспечивается 8-ядерным процессором Intel Core i5-12450H с частотой до 4.4 ГГц, 16 ГБ оперативной памяти LPDDR4X и быстрым твердотельным накопителем SSD объемом 512 ГБ. Графическая подсистема представлена встроенной видеокартой Intel UHD Graphics. Ноутбук работает на предустановленной операционной системе Windows 11 Home. Аккумуляторная батарея емкостью 56 Вт*ч (3665 мАч) обеспечивает до 8 часов работы.""",
    },
    {
        "category_expected": "vacuum_cleaners",
        "title": "Робот-пылесос Dreame Bot L10s Ultra белый",
        "description": """Робот-пылесос Dreame Bot L10s Ultra белого цвета предназначен для автоматической сухой и влажной уборки твердых напольных покрытий и ковров. Мощность всасывания достигает 5300 Па при энергопотреблении 75 Вт. Модель оснащена станцией самоочистки с пылесборником объемом 3 л и двумя баками для чистой и грязной воды по 2.5 л. В самом роботе установлен пылесборник на 0.35 л. Система навигации на базе лидара и ИИ-камеры распознает препятствия и строит точные карты помещений. Аккумулятор емкостью 5200 мАч обеспечивает время работы до 210 минут на одном заряде.""",
    },
    {
        "category_expected": "refrigerators",
        "title": "Холодильник двухкамерный Haier C2F637CFMV серебристый",
        "description": """Двухкамерный холодильник Haier C2F637CFMV цвета нержавеющая сталь (серебристый) оснащен полностью автоматической системой размораживания Total No Frost для обеих камер. Общий полезный объем составляет 386 л, из которых 278 л приходятся на холодильное отделение и 108 л на морозильное отделение с тремя выдвижными ящиками. Модель снабжена многопоточной системой охлаждения Multi Air Flow, зоной свежести с регулируемой влажностью и антибактериальным модулем T.ABT. Уровень шума не превышает 39 дБ, а класс энергоэффективности соответствует стандарту A+. На модель предоставляется гарантия 1 год.""",
    },
    {
        "category_expected": "tvs",
        "title": "OLED Телевизор 65\" Samsung QE65S90CAUXRU черный",
        "description": """Телевизор Samsung QE65S90CAUXRU оборудован 65-дюймовой OLED-панелью с разрешением 3840x2160 пикселей (4K Ultra HD) и поддержкой расширенного динамического диапазона HDR10+. Частота обновления экрана составляет 144 Гц с технологией Motion Xcelerator Turbo Pro. Модель работает на процессоре Neural Quantum 4K под управлением умной платформы Smart TV Tizen. Тонкий корпус черного цвета с титановой рамкой дополнен звуковой системой 2.1 мощностью 40 Вт с Dolby Atmos.""",
    },
    {
        "category_expected": "headphones",
        "title": "Беспроводные наушники Sony WH-1000XM5 черный",
        "description": """Полноразмерные беспроводные наушники Sony WH-1000XM5 черного цвета обеспечивают эталонное активное шумоподавление благодаря процессору V1 и системе из 8 микрофонов. Наушники поддерживают кодеки LDAC, AAC и SBC, а также технологию DSEE Extreme для восстановления сжатого звука. Вес устройства составляет всего 250 г. Встроенный аккумулятор обеспечивает до 30 часов непрерывного воспроизведения музыки с включенным шумоподавлением и до 40 часов без него.""",
    },
]

def main():
    print("=" * 80)
    print("🛍 ТЕСТИРОВАНИЕ НА РЕАЛЬНЫХ ТЕКСТОВЫХ ОПИСАНИЯХ М.ВИДЕО (mvideo.ru)")
    print("=" * 80)

    pipeline = CascadedExtractionPipeline(use_gliner=True, use_llm=False)

    for item in MVIDEO_PRODUCTS:
        title = item["title"]
        desc = item["description"].strip()
        full_text = f"{title}\n\n{desc}"

        print(f"\n" + "-" * 80)
        print(f"📦 ТОВАР: {title}")
        print("-" * 80)
        print(f"📝 ОПИСАНИЕ СЕЛЛЕРА НА САЙТЕ М.ВИДЕО:")
        preview = desc[:300] + "..." if len(desc) > 300 else desc
        print(f"   {preview}\n")

        res = pipeline.process_card({
            "title": title,
            "description": desc,
            "raw_text": full_text,
        })

        cat = res.get("category")
        conf = res.get("overall_confidence", 0.0)
        review = res.get("needs_review", False)
        status = "⚠️ ТРЕБУЕТ ПРОВЕРКИ (HITL)" if review else "✅ АВТОПУБЛИКАЦИЯ"

        print(f"🤖 РЕЗУЛЬТАТ ПАЙПЛАЙНА:")
        print(f"   Категория:          {cat}")
        print(f"   Общая уверенность:  {conf:.1%}")
        print(f"   Статус публикации:  {status}")
        if res.get("missing"):
            print(f"   Недостающие поля:   {', '.join(res.get('missing'))}")

        print(f"\n   📋 ИЗВЛЕЧЕННЫЕ ХАРАКТЕРИСТИКИ:")
        for p in res.get("predictions", []):
            print(f"     • {p['attribute']:<18} : {p['value']:<28} | {p['confidence']:.0%} [{p['source']}] (спан: '{p.get('raw', '')}')")

    print("\n" + "=" * 80)
    print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("=" * 80)

if __name__ == "__main__":
    main()
