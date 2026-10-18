import pytest

from app.extractors.gliner_extractor import GlinerExtractor
from app.extractors.regex_extractor import RegexExtractor
from app.extractors.sanity import AttributeSanityValidator
from app.services.pipeline import CascadedExtractionPipeline, CATEGORY_SCHEMAS


def test_powerbanks_category_detection():
    pipeline = CascadedExtractionPipeline(use_gliner=False, use_llm=False)

    # 1. raw_cat matches "Внешние аккумуляторы"
    cat_key, cat_name = pipeline.detect_category({
        "category": "Внешние аккумуляторы",
        "title": "Xiaomi Mi Power Bank 3 20000",
    })
    assert cat_key == "powerbanks"
    assert cat_name == CATEGORY_SCHEMAS["powerbanks"]["name_ru"]

    # 2. raw_cat matches other keywords
    for cat_val in [
        "портативные аккумуляторы",
        "внешний аккумулятор",
        "power bank",
        "портативное зарядное",
    ]:
        k, _ = pipeline.detect_category({"category": cat_val, "title": "Baseus 10000"})
        assert k == "powerbanks", f"Failed for category={cat_val}"


def test_microwaves_category_and_sanity():
    pipeline = CascadedExtractionPipeline(use_gliner=False, use_llm=False)

    # 1. Detection via raw_cat
    k, name = pipeline.detect_category({
        "category": "Микроволновые печи",
        "title": "Gorenje MO20E1W",
    })
    assert k == "microwaves"
    assert name == "Микроволновые печи"

    # 2. Detection via title
    for title in [
        "Микроволновая печь Gorenje MO20E1W 20 л 800 Вт белый",
        "СВЧ печь Samsung MS23K3513AS",
        "Микроволновка LG MS2042DB",
    ]:
        k, _ = pipeline.detect_category({"title": title})
        assert k == "microwaves", f"Failed for title={title}"

    # 3. Sanity: Allowed attrs
    for attr, val in [
        ("brand", "Gorenje"),
        ("model", "MO20E1W"),
        ("volume", "20 л"),
        ("power", "800 Вт"),
        ("color", "белый"),
        ("weight", "15 кг"),
    ]:
        assert AttributeSanityValidator.is_valid(attr, val, "microwaves")

    # 4. Sanity: Forbidden attrs
    for forbidden_attr, val in [
        ("screen_diagonal", "6.7\""),
        ("refresh_rate", "120 Гц"),
        ("resolution", "1920x1080"),
        ("cpu", "Snapdragon 8 Gen 2"),
        ("os", "Android"),
        ("cleaning_type", "сухая"),
        ("battery", "5000 мАч"),
        ("defrost_system", "No Frost"),
    ]:
        assert not AttributeSanityValidator.is_valid(forbidden_attr, val, "microwaves")


def test_accessory_and_sanitary_leak_prevention():
    pipeline = CascadedExtractionPipeline(use_gliner=False, use_llm=False)

    # Accessories should route to default, NOT smartphones/tvs/headphones/laptops/vacuum_cleaners
    accessory_cases = [
        {"title": "Чехол для Apple iPhone 15 Pro Max прозрачный", "category": ""},
        {"title": "Чехлы силиконовые для Samsung Galaxy S24", "category": ""},
        {"title": "Защитное стекло для смартфона Xiaomi Redmi Note 13", "category": ""},
        {"title": "Защитные стекла на экран iPhone 16", "category": ""},
        {"title": "Пленка защитная для экрана Samsung Galaxy", "category": ""},
        {"title": "Пленки матовые для смартфона", "category": ""},
        {"title": "Кронштейн для телевизора 32-55 дюймов настенный", "category": "Кронштейны"},
        {"title": "Кронштейны настенные для ТВ", "category": ""},
        {"title": "Сменный фильтр для пылесоса Xiaomi Vacuum Mop", "category": "Фильтры"},
        {"title": "Фильтры HEPA для пылесосов Dyson", "category": ""},
        {"title": "Насадка турбощетка для пылесоса Philips", "category": "Насадки"},
        {"title": "Насадки для пылесоса", "category": ""},
        {"title": "Кабель USB Type-C для зарядки смартфона и ноутбука", "category": "Кабели"},
        {"title": "Адаптер питания 20W для iPhone", "category": "Адаптеры"},
        {"title": "Ремешок силиконовый для часов и браслетов", "category": "Ремешки"},
        {"title": "Смеситель для ванны с душем Grohe", "category": "Смесители"},
        {"title": "Душевой гарнитур со смесителем Hansgrohe", "category": "Душевые гарнитуры"},
        {"title": "Сантехника для ванной комнаты: смеситель и лейка", "category": "Сантехника"},
        # Multi-adjective edge cases (previously leaked due to {0,2} bound)
        {"title": "Силиконовый противоударный прозрачный чехол Apple iPhone 15 Pro Max", "category": ""},
        {"title": "Защитная гидрогелевая матовая пленка Samsung Galaxy S24 Ultra", "category": ""},
        {"title": "Настенный поворотный металлический кронштейн Samsung 55 дюймов", "category": ""},
        {"title": "Сменный моющийся круглый фильтр Xiaomi Vacuum Cleaner", "category": ""},
        # Search-spam starting with device noun followed by accessory
        {"title": "Смартфон Xiaomi Redmi Note 13 чехол противоударный", "category": ""},
        {"title": "Телевизор LG OLED кронштейн поворотный настенный", "category": ""},
        {"title": "Пылесос Dyson сменный фильтр HEPA", "category": ""},
    ]

    for card in accessory_cases:
        cat_key, _ = pipeline.detect_category(card)
        assert cat_key not in {
            "smartphones", "tvs", "headphones", "laptops", "vacuum_cleaners"
        }, f"Leaked accessory to {cat_key} for card: {card}"
        assert cat_key == "default", f"Expected default for {card}, got {cat_key}"


def test_sanitary_garnitura_not_classified_as_headphones():
    pipeline = CascadedExtractionPipeline(use_gliner=False, use_llm=False)

    # Contains "гарнитур" + sanitary markers -> MUST NOT be headphones
    cat_key, _ = pipeline.detect_category({
        "title": "Душевой гарнитур с тропическим душем",
        "category": "Душевые гарнитуры",
    })
    assert cat_key != "headphones"
    assert cat_key == "default"

    cat_key, _ = pipeline.detect_category({
        "title": "Гарнитур для ванны со смесителем",
        "category": "",
    })
    assert cat_key != "headphones"
    assert cat_key == "default"

    # Real headphones with "гарнитура" without sanitary markers -> MUST be headphones
    cat_key, _ = pipeline.detect_category({
        "title": "Беспроводная гарнитура Sony WH-1000XM5",
        "category": "Наушники и гарнитуры",
    })
    assert cat_key == "headphones"


def test_laptop_slash_memory_regex():
    ext = RegexExtractor()

    # M4/16/256GB must NOT capture 4/16 as RAM/ROM (Latin M)
    card = {
        "title": "Ноутбук Apple MacBook Pro 14 M4/16/512GB Space Black",
        "description": "",
    }
    preds = {p["attribute"]: p["value"] for p in ext.extract(card)}
    assert preds.get("memory_ram") == "16 ГБ"
    assert preds.get("memory_rom") == "512 ГБ"

    # Cyrillic М4/16/512GB must NOT capture 4/16 as RAM/ROM
    card_cyr = {
        "title": "Ноутбук Apple MacBook Pro 14 М4/16/512GB Space Black",
        "description": "",
    }
    preds_cyr = {p["attribute"]: p["value"] for p in ext.extract(card_cyr)}
    assert preds_cyr.get("memory_ram") == "16 ГБ"
    assert preds_cyr.get("memory_rom") == "512 ГБ"

    # Standard smartphone slash notation 8/256GB still works
    card_phone = {
        "title": "Смартфон Xiaomi Redmi Note 13 8/256GB Black",
        "description": "",
    }
    preds_phone = {p["attribute"]: p["value"] for p in ext.extract(card_phone)}
    assert preds_phone.get("memory_ram") == "8 ГБ"
    assert preds_phone.get("memory_rom") == "256 ГБ"


def test_smartphone_resolution_and_display_tech_unlocked():
    # Resolution and refresh rate are allowed for smartphones
    assert AttributeSanityValidator.is_valid("resolution", "2400x1080", "smartphones")
    assert AttributeSanityValidator.is_valid("resolution", "FHD+", "smartphones")
    assert AttributeSanityValidator.is_valid("refresh_rate", "120 Гц", "smartphones")
    assert AttributeSanityValidator.is_valid("refresh_rate", "90 Гц", "smartphones")

    # Display tech is allowed for TVs
    assert AttributeSanityValidator.is_valid("display_tech", "OLED", "tvs")
    assert AttributeSanityValidator.is_valid("display_tech", "QLED", "tvs")
    assert AttributeSanityValidator.is_valid("display_tech", "Triluminos", "tvs")

    # GPU is allowed for laptops and validates real GPU chips vs display screen techs
    assert AttributeSanityValidator.is_valid("gpu", "NVIDIA GeForce RTX 4060", "laptops")
    assert AttributeSanityValidator.is_valid("gpu", "Intel Iris Xe", "laptops")
    assert AttributeSanityValidator.is_valid("gpu", "AMD Radeon RX 7600M", "laptops")
    assert not AttributeSanityValidator.is_valid("gpu", "Liquid Retina", "laptops")
    assert not AttributeSanityValidator.is_valid("gpu", "OLED", "laptops")


def test_gliner_label_mapping():
    assert GlinerExtractor.LABEL_TO_ATTR.get("видеокарта") == "gpu"
    assert GlinerExtractor.LABEL_TO_ATTR.get("объем пылесборника") == "volume"
    assert GlinerExtractor.LABEL_TO_ATTR.get("объём пылесборника") == "volume"
    assert GlinerExtractor.LABEL_TO_ATTR.get("объем") == "volume"
    assert GlinerExtractor.LABEL_TO_ATTR.get("объём") == "volume"
    assert GlinerExtractor.LABEL_TO_ATTR.get("мощность") == "power"

