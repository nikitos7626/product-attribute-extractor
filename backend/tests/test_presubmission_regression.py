import pytest
from app.extractors.regex_extractor import RegexExtractor
from app.extractors.sanity import AttributeSanityValidator
from app.services.pipeline import CascadedExtractionPipeline


def test_laptop_bag_classified_as_default_not_laptop():
    pipeline = CascadedExtractionPipeline(use_gliner=False, use_llm=False)
    
    test_cases = [
        {"title": "Сумка для ноутбука Lenovo Casual Toploader T210 15.6'' Черная"},
        {"title": "Сумки для ноутбуков RivaCase 15.6 дюймов полиэстер"},
        {"title": "Чехол-сумка для MacBook Air 13 синий", "category": "Сумки и чехлы"},
        {"title": "Рюкзак для ноутбука Xiaomi Urban Backpack 15.6"},
        {"title": "Рюкзак Xiaomi Commuter темно-синий"},
    ]
    for case in test_cases:
        cat_key, _ = pipeline.detect_category(case)
        assert cat_key != "laptops", f"Failed: {case['title']} was classified as 'laptops'!"
        assert cat_key != "smartphones", f"Failed: {case['title']} was classified as 'smartphones'!"
        assert cat_key == "default", f"Expected 'default', got '{cat_key}' for {case['title']}"


def test_cyrillic_words_do_not_extract_brand_tka():
    ext = RegexExtractor()
    
    words_ending_in_tka = [
        "щетка",
        "щётка",
        "турбощетка",
        "салфетка",
        "решетка",
        "розетка",
        "плитка",
        "пылесос с турбощеткой для ковров",
        "электрическая зубная щетка",
    ]
    for word in words_ending_in_tka:
        hits = ext._brand_kp.extract_keywords(word)
        assert "ТКА" not in hits, f"Hallucinated brand 'ТКА' from word '{word}'! Hits: {hits}"

    # Standalone 'ТКА' brand should still be extracted
    valid_tka_text = "Прибор комбинированный ТКА-ПКМ люксметр"
    tka_hits = ext._brand_kp.extract_keywords(valid_tka_text)
    assert "ТКА" in tka_hits, f"Failed to extract standalone brand 'ТКА' from '{valid_tka_text}'"


def test_raw_numeric_weights_category_aware_heuristics():
    # 1.51 without units for laptop -> interpreted as 1.51 kg (1510 g) -> valid
    assert AttributeSanityValidator.is_valid("weight", "1.51", "laptops")
    assert AttributeSanityValidator.is_valid("weight", "2.1", "laptops")
    assert AttributeSanityValidator.is_valid("weight", "1.51 кг", "laptops")
    assert AttributeSanityValidator.is_valid("weight", "1510 г", "laptops")
    assert not AttributeSanityValidator.is_valid("weight", "0.05", "laptops")  # 50g is too small

    # 67 without units for refrigerator -> interpreted as 67 kg (67000 g) -> valid
    assert AttributeSanityValidator.is_valid("weight", "67", "refrigerators")
    assert AttributeSanityValidator.is_valid("weight", "82.5", "refrigerators")
    assert AttributeSanityValidator.is_valid("weight", "67 кг", "refrigerators")
    assert not AttributeSanityValidator.is_valid("weight", "5", "refrigerators")  # 5kg is too small

    # Washing machines
    assert AttributeSanityValidator.is_valid("weight", "55", "washing_machines")

    # Powerbanks
    assert AttributeSanityValidator.is_valid("weight", "0.4", "powerbanks")
    assert AttributeSanityValidator.is_valid("weight", "400 г", "powerbanks")

    # Vacuum cleaners (3.5 kg -> 3500 g)
    assert AttributeSanityValidator.is_valid("weight", "3.5", "vacuum_cleaners")
    assert AttributeSanityValidator.is_valid("weight", "3.5 кг", "vacuum_cleaners")

    # Microwaves (12 kg -> 12000 g)
    assert AttributeSanityValidator.is_valid("weight", "12", "microwaves")
    assert AttributeSanityValidator.is_valid("weight", "12 кг", "microwaves")

    # Smartphones (0.198 kg -> 198 g; or 198 g directly)
    assert AttributeSanityValidator.is_valid("weight", "0.198", "smartphones")
    assert AttributeSanityValidator.is_valid("weight", "198", "smartphones")
    assert AttributeSanityValidator.is_valid("weight", "198 г", "smartphones")


def test_foldable_smartphones_screen_diagonal_and_rugged_batteries():
    # Foldables: 8.0" screen diagonal (Mate X, Galaxy Fold)
    assert AttributeSanityValidator.is_valid("screen_diagonal", "8.0", "smartphones")
    assert AttributeSanityValidator.is_valid("screen_diagonal", "8.0\"", "smartphones")
    assert AttributeSanityValidator.is_valid("screen_diagonal", "8.3 дюйм", "smartphones")
    assert AttributeSanityValidator.is_valid("screen_diagonal", "6.7 дюймов", "smartphones")
    assert not AttributeSanityValidator.is_valid("screen_diagonal", "8.5", "smartphones")
    assert not AttributeSanityValidator.is_valid("screen_diagonal", "2.0", "smartphones")

    # Rugged high-capacity smartphones (Oukitel, Blackview 15000-22000 mAh)
    assert AttributeSanityValidator.is_valid("battery", "15000 мАч", "smartphones")
    assert AttributeSanityValidator.is_valid("battery", "22000 mAh", "smartphones")
    assert AttributeSanityValidator.is_valid("battery", "25000", "smartphones")
    assert AttributeSanityValidator.is_valid("battery", "5000 мАч", "smartphones")
    assert not AttributeSanityValidator.is_valid("battery", "28000 мАч", "smartphones")
    assert not AttributeSanityValidator.is_valid("battery", "500 мАч", "smartphones")


def test_extended_color_roots_validation():
    valid_colors = [
        "нержавеющая сталь",
        "сталь",
        "пурпурный",
        "кремовый",
        "кофейный",
        "лайм",
        "слоновая кость",
        "полуночный черный",
        "сияющая звезда",
    ]
    for c in valid_colors:
        assert AttributeSanityValidator.is_valid("color", c, "default"), f"Color '{c}' failed validation"


def test_dirty_brand_tokens_rejected_and_absent_from_brands_csv():
    # Placeholder tokens and unit abbreviations must be rejected by validator
    dirty_tokens = [
        "нет бренда",
        "без бренда",
        "не указан",
        "не указано",
        "отсутствует",
        "нет",
        "n/a",
        "#n/a",
        "wireless",
        "tws",
        "gb",
        "напольный",
        "ортопедический",
    ]
    for token in dirty_tokens:
        assert not AttributeSanityValidator.is_valid("brand", token), f"Token '{token}' was unexpectedly accepted as brand!"

    # Verify brands.csv does not contain these non-brand entries
    from app.services.brand_registry import DEFAULT_BRANDS_CSV
    with open(DEFAULT_BRANDS_CSV, encoding="utf-8") as f:
        content = f.read().lower()
        for token in ["нет бренда,нет бренда", "без бренда,без бренда", "нет,нет", "#n/a,#n/a", "wireless,wireless", "tws,tws", "gb,gb"]:
            assert token not in content, f"Dirty token '{token}' found in brands.csv!"
