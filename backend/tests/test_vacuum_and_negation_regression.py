import pytest
from app.extractors.regex_extractor import RegexExtractor
from app.extractors.sanity import AttributeSanityValidator
from app.services.pipeline import CascadedExtractionPipeline


def test_user_screenshot_dyson_v11_exact_card():
    """
    Регрессионный тест на карточку из пользовательского скриншота:
    'Пылесос Dyson V11, беспроводной, серый. Мощность всасывания 185 Ватт.
     Время работы до 60 минут. Вес 3.1 кг. В комплекте нет насадки для влажной уборки, только для сухой.'
    """
    card = {
        "title": "Пылесос Dyson V11, беспроводной, серый. Мощность всасывания 185 Ватт. Время работы до 60 минут. Вес 3.1 кг. В комплекте нет насадки для влажной уборки, только для сухой.",
        "description": "",
    }

    # Проверяем сквозной пайплайн
    pipe = CascadedExtractionPipeline(use_gliner=True, use_catalog_enricher=True, use_llm=False)
    res = pipe.process_card(card)
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}

    # 1. Модель обязана быть V11, а НЕ 'беспроводной'
    assert preds.get("model") == "V11", f"Expected model V11, got {preds.get('model')}"

    # 2. Тип уборки обязан быть 'сухая' из-за отрицания насадки для влажной уборки
    assert preds.get("cleaning_type") == "сухая", f"Expected cleaning_type 'сухая', got {preds.get('cleaning_type')}"

    # 3. Остальные характеристики
    assert preds.get("brand") == "Dyson"
    assert preds.get("color") == "серый"
    assert preds.get("weight") in ("3.1 кг", "3,1 кг")
    assert preds.get("power") == "185 Вт"
    assert preds.get("working_time") == "60 мин"


def test_bad_model_words_rejects_generic_product_types():
    """
    Проверяет, что generic слова ('беспроводной', 'вертикальный', 'робот', 'моющий' и т.д.)
    ни при каких обстоятельствах не могут быть приняты за модель.
    """
    bad_words = [
        "беспроводной",
        "беспроводная",
        "беспроводные",
        "проводной",
        "проводная",
        "вертикальный",
        "вертикальная",
        "робот",
        "моющий",
        "моющая",
        "ручной",
        "ручная",
        "портативный",
        "аккумуляторный",
        "циклонный",
        "тихий",
        "мощный",
    ]
    for w in bad_words:
        assert not AttributeSanityValidator.is_valid("model", w, "vacuum_cleaners"), f"Word '{w}' should be rejected as model"
        assert not AttributeSanityValidator.is_valid("model", w.capitalize(), "vacuum_cleaners")


def test_dyson_model_regex_extraction():
    """
    Проверяет извлечение моделей Dyson и пылесосов в RegexExtractor (Tier 1).
    """
    extractor = RegexExtractor()

    test_cases = [
        ("Пылесос Dyson V11 беспроводной", "V11"),
        ("Пылесос Dyson V12 Detect Slim Extra", "V12 Detect Slim Extra"),
        ("Пылесос Dyson V15 Detect Absolute", "V15 Detect Absolute"),
        ("Беспроводной пылесос Dyson V8 Absolute", "V8 Absolute"),
        ("Пылесос Dyson V10 Fluffy", "V10 Fluffy"),
        ("Пылесос Dyson Gen5detect Absolute", "Gen5detect Absolute"),
        ("Пылесос Dyson Omni-glide", "Omni-glide"),
        ("Пылесос Dreame V11 Pro", "V11 Pro"),
        ("Робот-пылесос Roborock S8 Pro Ultra", "S8 Pro Ultra"),
    ]

    for title, expected_model in test_cases:
        preds = extractor.extract({"title": title}, category_key="vacuum_cleaners")
        model_pred = next((p for p in preds if p["attribute"] == "model"), None)
        assert model_pred is not None, f"Failed to extract model for '{title}'"
        assert expected_model.lower() in model_pred["value"].lower(), f"For '{title}', expected '{expected_model}', got '{model_pred['value']}'"


@pytest.mark.parametrize(
    "text,expected_cleaning_type",
    [
        ("В комплекте нет насадки для влажной уборки, только для сухой.", "сухая"),
        ("Пылесос не поддерживает влажную уборку.", "сухая"),
        ("Пылесос без влажной уборки, мощность 200 Вт.", "сухая"),
        ("Только для сухой уборки напольных покрытий.", "сухая"),
        ("Исключительно для сухой чистки.", "сухая"),
        ("Отсутствует функция влажной уборки.", "сухая"),
        ("Пылесос не моет полы.", "сухая"),
        ("Сухая и влажная уборка пола.", "сухая и влажная"),
        ("Подходит для сухой/влажной уборки.", "сухая и влажная"),
        ("Влажная и сухая уборка 2 в 1.", "сухая и влажная"),
        ("Комбинированная уборка квартиры.", "сухая и влажная"),
        ("В комплекте нет насадки для сухой уборки, только для влажной.", "влажная"),
        ("Исключительно для влажной уборки.", "влажная"),
        ("Сухая и влажная уборка, однако насадка для влажной уборки отсутствует.", "сухая"),
    ],
)
def test_cleaning_type_negation_and_combinations(text: str, expected_cleaning_type: str):
    extractor = RegexExtractor()
    card = {"title": "Пылесос", "description": text}
    pred = extractor._find_cleaning_type(text, title="Пылесос")
    assert pred is not None, f"Expected cleaning_type for '{text}'"
    assert pred["value"] == expected_cleaning_type, f"For '{text}', expected '{expected_cleaning_type}', got '{pred['value']}'"


def test_sanity_validator_blocks_negated_cleaning_type():
    """
    Проверяет, что Sanity Validator блокирует галлюцинированный тип уборки при отрицании.
    """
    negated_wet_text = "В комплекте нет насадки для влажной уборки, только для сухой."
    # 'влажная' и 'сухая и влажная' должны быть отсечены
    assert not AttributeSanityValidator.is_valid("cleaning_type", "влажная", "vacuum_cleaners", raw_text=negated_wet_text)
    assert not AttributeSanityValidator.is_valid("cleaning_type", "сухая и влажная", "vacuum_cleaners", raw_text=negated_wet_text)
    # 'сухая' должна успешно проходить валидацию
    assert AttributeSanityValidator.is_valid("cleaning_type", "сухая", "vacuum_cleaners", raw_text=negated_wet_text)

    negated_dry_text = "Только для влажной уборки, нет насадок для сухой."
    assert not AttributeSanityValidator.is_valid("cleaning_type", "сухая", "vacuum_cleaners", raw_text=negated_dry_text)
    assert not AttributeSanityValidator.is_valid("cleaning_type", "сухая и влажная", "vacuum_cleaners", raw_text=negated_dry_text)
    assert AttributeSanityValidator.is_valid("cleaning_type", "влажная", "vacuum_cleaners", raw_text=negated_dry_text)


def test_nothing_phone_4a_model_and_category():
    """
    Проверяет карточку Nothing Phone (4a):
    1. Категория должна быть 'Смартфоны' (не 'Электроника и техника')
    2. Модель должна быть 'Phone (4a)', а не просто 'Phone'
    3. Бренд должен быть 'Nothing'
    4. Так как цвет/батарея не указаны, карточка должна требовать ручной проверки (needs_review=True)
    """
    card = {"title": "Nothing Phone (4a)", "description": ""}
    pipe = CascadedExtractionPipeline(use_gliner=True, use_catalog_enricher=True, use_llm=False)
    res = pipe.process_card(card)

    assert res.get("category_key") == "smartphones", f"Expected category smartphones, got {res.get('category_key')}"
    preds = {p["attribute"]: p["value"] for p in res.get("predictions", [])}

    assert preds.get("brand") == "Nothing", f"Expected brand Nothing, got {preds.get('brand')}"
    assert preds.get("model") == "Phone (4a)", f"Expected model 'Phone (4a)', got {preds.get('model')}"
    assert res.get("needs_review") is True, "Card must require review due to missing required fields"
    assert "color" in res.get("missing", []), "Expected 'color' in missing fields"
