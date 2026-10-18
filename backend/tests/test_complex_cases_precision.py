import pytest
from app.extractors.regex_extractor import RegexExtractor
from app.extractors.sanity import AttributeSanityValidator
from app.services.pipeline import CascadedExtractionPipeline


def test_brand_model_compatibility():
    assert AttributeSanityValidator.is_brand_model_compatible("Apple", "iPhone 15 Pro Max") is True
    assert AttributeSanityValidator.is_brand_model_compatible("Xiaomi", "iPhone 15 Pro Max") is False
    assert AttributeSanityValidator.is_brand_model_compatible("Samsung", "Galaxy S24 Ultra") is True
    assert AttributeSanityValidator.is_brand_model_compatible("Xiaomi", "Galaxy S24") is False
    assert AttributeSanityValidator.is_brand_model_compatible("Xiaomi", "POCO X6 Pro 5G") is True
    assert AttributeSanityValidator.is_brand_model_compatible("Xiaomi", "Redmi Note 13") is True
    assert AttributeSanityValidator.is_brand_model_compatible("Asus", "TUF Gaming A15") is True
    assert AttributeSanityValidator.is_brand_model_compatible("Samsung", "TUF Gaming A15") is False
    assert AttributeSanityValidator.is_brand_model_compatible("Google", "Pixel 8 Pro") is True


def test_case_1_laptop_asus_tuf_gaming():
    pipeline = CascadedExtractionPipeline(use_gliner=False, use_llm=False)
    raw_text = (
        'НБ ASUS TUF Gaming A15 FA507NU-LP031 (15.6" FHD IPS 144Гц, Ryzen 7 7735HS, '
        '16ГБ DDR5, SSD 512ГБ, GeForce RTX 4050 для ноутбуков 6ГБ, Без ОС, Серый, 90NR0EB5-M002S0). '
        'Игровой ноутбук серии ASUS TUF Gaming A15 в цвете Mecha Gray создан для серьезного гейминга. '
        'В максимальных конфигурациях линейки устанавливается до 32 ГБ оперативной памяти и два '
        'твердотельных накопителя суммарным объемом до 2 ТБ. Дискретная видеокарта NVIDIA GeForce RTX 4050 '
        'с 6 ГБ видеопамяти GDDR6 и поддержкой DLSS 3 обеспечивает высокий фреймрейт. Поставляется без '
        'предустановленной операционной системы (рекомендуется установка Windows 11 Домашняя).'
    )
    result = pipeline.process_card({"raw_text": raw_text})
    preds = {p["attribute"]: p["value"] for p in result["predictions"]}

    assert result["category"] == "Ноутбуки"
    assert preds["brand"] == "Asus"
    assert preds["color"] == "серый"
    assert "TUF Gaming" in preds["model"]
    # 1. Извлечена реальная комплектация 16 ГБ, а не лимит апгрейда 32 ГБ
    assert preds["memory_ram"] == "16 ГБ"
    # 2. Извлечен реальный накопитель 512 ГБ, а не лимит 2 ТБ
    assert preds["memory_rom"] == "512 ГБ"
    # 3. Суффикс CPU в верхнем регистре (7735HS, а не 7735hs)
    assert preds["cpu"] == "Ryzen 7 7735HS"
    # 4. ОС "Без ОС", а не рекомендованная Windows
    assert preds["os"] == "Без ОС"
    # 5. Экран и видеокарта
    assert preds["screen_diagonal"] == '15,6"'
    assert "RTX 4050" in preds["gpu"]

    # Проверка чистоты округления float confidence
    for p in result["predictions"]:
        conf_str = str(p["confidence"])
        decimals = len(conf_str.split(".")[1]) if "." in conf_str else 0
        assert decimals <= 4, f"Float rounding artifact found: {p['confidence']}"


def test_case_2_smartphone_poco_x6_pro():
    pipeline = CascadedExtractionPipeline(use_gliner=False, use_llm=False)
    raw_text = (
        'Смартфон POCO X6 Pro 5G (глобальная версия, не путать с обычным Redmi Note 13 или базовым Poco X6!). '
        'Хит продаж, который по плавности работы не уступает Apple iPhone 15 Pro Max и Samsung Galaxy S24 '
        'в корпусе титановый черный! Внимание: у нас в продаже редкая старшая конфигурация — не 8/256 ГБ как у '
        'большинства продавцов, а полноценные 12 гигабайт оперативки и накопитель на полтерабайта! '
        '(также в соседнем лоте есть версия с расширением флешки до 1024 ГБ). Экран кристально чистый AMOLED, '
        'диагональ 6.67" (смотрится компактнее громоздких лопат на 6.8 дюйма, разрешение 2712x1220), '
        'честная герцовка 120 Гц — забудьте про старые дерганые матрицы на 60Hz и 90Hz! Под капотом зверский чип '
        'MediaTek Dimensity 8300-Ultra (рвет в клочья популярный Snapdragon 7s Gen 2). Цвет корпуса: сочный Желтый, '
        'задняя крышка из экокожи (в подарок идет защитный чехол темно-синий). Внутри мощный аккумулятор 5000 мАч '
        '(быстрая зарядка в комплекте, вам больше не придется таскать с собой тяжелый пауэрбанк на 10000 мА*ч!).'
    )
    result = pipeline.process_card({"raw_text": raw_text})
    preds = {p["attribute"]: p["value"] for p in result["predictions"]}

    assert result["category"] == "Смартфоны"
    assert preds["brand"] == "Xiaomi"
    # 1. Модель POCO X6 Pro 5G, а не упомянутый в сравнении iPhone 15 Pro Max
    assert preds["model"] == "POCO X6 Pro 5G"
    # 2. Цвет устройства "жёлтый", а не конкурента "черный" и не чехла "синий"
    assert preds["color"] in ("жёлтый", "желтый")
    # 3. RAM 12 ГБ (не отрицаемые 8 ГБ)
    assert preds["memory_ram"] == "12 ГБ"
    # 4. ROM 512 ГБ (из "полтерабайта", а не 256 ГБ и не флешка 1024 ГБ)
    assert preds["memory_rom"] == "512 ГБ"
    # 5. Экран 6.67" (а не 6.8")
    assert preds["screen_diagonal"] == '6,67"'
    # 6. Герцовка 120 Гц (а не отвергнутые 60Hz и 90Hz)
    assert preds["refresh_rate"] == "120 Гц"
    # 7. Разрешение экрана
    assert preds["resolution"] == "2712×1220"
    # 8. Процессор Dimensity 8300 (а не Snapdragon 7s Gen 2)
    assert "Dimensity" in preds["cpu"]
    assert "Snapdragon" not in preds["cpu"]
    # 9. Батарея 5000 мАч из regex (а не пауэрбанк 10000 мАч и не 5100 мАч из каталога)
    battery_pred = next(p for p in result["predictions"] if p["attribute"] == "battery")
    assert battery_pred["value"] == "5000 мАч"
    assert battery_pred["source"] == "regex"
    assert "5000" in battery_pred["raw"]


def test_guard_filters_standalone():
    extractor = RegexExtractor()
    # Отрицание
    assert extractor._is_negated_or_filtered("не 8/256 ГБ", 3) is True
    assert extractor._is_negated_or_filtered("не путать с обычным Redmi", 18) is True
    # Апгрейд
    assert extractor._is_negated_or_filtered("устанавливается до 32 ГБ", 19, check_upgrade=True) is True
    assert extractor._is_negated_or_filtered("суммарным объемом до 2 ТБ", 21, check_upgrade=True) is True
    assert extractor._is_negated_or_filtered("с расширением флешки до 1024 ГБ", 24, check_upgrade=True) is True
    # Аксессуары
    assert extractor._is_negated_or_filtered("защитный чехол темно-синий", 15, check_accessory=True) is True
    # Рекомендации ОС
    assert extractor._is_negated_or_filtered("рекомендуется установка Windows 11", 24, check_recommendation=True) is True
    # Изоляция контекстного окна (скобки и знаки препинания не отменяют валидную батарею)
    t_bat = "мощный аккумулятор 5000 мАч (быстрая зарядка в комплекте, вам больше не придется таскать с собой тяжелый пауэрбанк на 10000 мА*ч!)"
    idx_5000 = t_bat.find("5000")
    idx_10000 = t_bat.find("10000")
    assert extractor._is_negated_or_filtered(t_bat, idx_5000, end_pos=idx_5000 + 8, check_accessory=True) is False
    assert extractor._is_negated_or_filtered(t_bat, idx_10000, end_pos=idx_10000 + 10, check_accessory=True) is True


def test_catalog_kb_unified_raw_key():
    from app.services.catalog_enricher import CatalogEnricher
    enricher = CatalogEnricher()
    res = enricher.enrich("Samsung", "Galaxy S22", {"battery", "screen_diagonal"}, "smartphones")
    assert len(res) > 0
    for p in res:
        assert "raw" in p
        assert "raw_text" not in p
        assert p["raw"] == p["value"]
        assert p["source"] == "catalog_kb"
