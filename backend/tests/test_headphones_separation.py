"""
Тесты разделения наушников на проводные и беспроводные (Headphone Subtype Specialization).
Проверяют:
1. У проводных наушников принципиально нет аккумулятора и времени автономной работы (working_time).
2. Защиту от ложного извлечения working_time из маркетингового шума/доставки у проводных наушников.
3. Извлечение типа подключения (connection_type: "проводные" vs "беспроводные").
4. Извлечение времени автономной работы у беспроводных и TWS наушников.
5. Правила AttributeSanityValidator для подтипов headphones_wired и headphones_wireless.
"""
import pytest
from app.extractors.sanity import AttributeSanityValidator
from app.services.pipeline import CascadedExtractionPipeline


@pytest.fixture(scope="module")
def pipeline():
    return CascadedExtractionPipeline(use_gliner=False, use_llm=False)


def test_wired_headphones_no_working_time_and_connection_type(pipeline):
    """
    Проводные наушники:
    - connection_type == 'проводные'
    - working_time ОТСУТСТВУЕТ (даже при наличии в описании 'доставка за 24 часа')
    - working_time НЕ попадает в missing
    - subcategory == 'wired'
    """
    card = {
        "id": "test-wired-01",
        "title": "Наушники проводные JBL C100SI 3.5 мм черный",
        "category": "Наушники",
        "description": "Проводные внутриканальные наушники с разъемом mini-jack 3.5 мм. Чистый звук, гарантия 12 месяцев, доставка за 24 часа.",
    }
    res = pipeline.process_card(card)
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}

    assert res["category"] == "Наушники"
    assert res["subcategory"] == "wired"
    assert preds.get("brand") == "JBL"
    assert preds.get("color") in ("черный", "чёрный")
    assert preds.get("connection_type") == "проводные"

    # Критическое требование: у проводных наушников НЕТ атрибута working_time!
    assert "working_time" not in preds, f"Working time unexpectedly extracted for wired headphones: {preds.get('working_time')}"
    assert "battery" not in preds, f"Battery unexpectedly extracted for wired headphones: {preds.get('battery')}"
    assert "working_time" not in res["missing"], "working_time must not be in missing for wired headphones"


def test_wired_headphones_in_ear_sennheiser(pipeline):
    """Проводные наушники-вкладыши с кабелем без слова 'проводные' в названии."""
    card = {
        "id": "test-wired-02",
        "title": "Наушники-вкладыши Sennheiser IE 40 PRO Transparent",
        "category": "Наушники",
        "description": "Профессиональные мониторные наушники со съемным кабелем 1.3 м и штекером 3.5 мм. Вес 18 г.",
    }
    res = pipeline.process_card(card)
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}

    assert res["category"] == "Наушники"
    assert res["subcategory"] == "wired"
    assert preds.get("brand") == "Sennheiser"
    assert preds.get("connection_type") == "проводные"
    assert "working_time" not in preds
    assert "working_time" not in res["missing"]


def test_wireless_headphones_has_working_time(pipeline):
    """
    Беспроводные наушники:
    - connection_type == 'беспроводные'
    - working_time извлекается
    - subcategory == 'wireless'
    """
    card = {
        "id": "test-wireless-01",
        "title": "Беспроводные наушники Sony WH-1000XM5 серебристый",
        "category": "Наушники",
        "description": "Полноразмерные Bluetooth наушники с активным шумоподавлением. Время автономной работы до 30 часов. Вес 250 г.",
    }
    res = pipeline.process_card(card)
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}

    assert res["category"] == "Наушники"
    assert res["subcategory"] == "wireless"
    assert preds.get("brand") == "Sony"
    assert preds.get("color") == "серебристый"
    assert preds.get("connection_type") == "беспроводные"
    assert preds.get("working_time") == "30 ч"
    assert preds.get("weight") == "250 г"


def test_tws_airpods_wireless(pipeline):
    """TWS гарнитура Apple AirPods: определяется как беспроводные."""
    card = {
        "id": "test-tws-01",
        "title": "Наушники True Wireless Apple AirPods Pro 2 White",
        "category": "Наушники",
        "description": "TWS наушники с чипом H2. До 6 часов воспроизведения на одном заряде.",
    }
    res = pipeline.process_card(card)
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}

    assert res["category"] == "Наушники"
    assert res["subcategory"] == "wireless"
    assert preds.get("brand") == "Apple"
    assert preds.get("connection_type") == "беспроводные"
    assert preds.get("working_time") == "6 ч"


def test_hybrid_bluetooth_with_optional_cable_is_wireless(pipeline):
    """
    Гибридные наушники: есть Bluetooth И провод 3.5 мм в комплекте.
    Поскольку есть Bluetooth и аккумулятор, это беспроводные наушники с working_time!
    """
    card = {
        "id": "test-hybrid-01",
        "title": "Наушники накладные Bluetooth JBL Tune 520BT Blue",
        "category": "Наушники",
        "description": "Беспроводная гарнитура с возможностью подключения через кабель 3.5 мм. Работает до 57 часов.",
    }
    res = pipeline.process_card(card)
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}

    assert res["category"] == "Наушники"
    assert res["subcategory"] == "wireless"
    assert preds.get("connection_type") == "беспроводные"
    assert preds.get("working_time") == "57 ч"


def test_sanity_validator_headphones_subtypes():
    """Проверка правил физического здравого смысла в AttributeSanityValidator."""
    # 1. Проводные наушники: working_time и battery категорически запрещены
    assert AttributeSanityValidator.is_valid("working_time", "30 ч", "headphones_wired") is False
    assert AttributeSanityValidator.is_valid("battery", "500 мАч", "headphones_wired") is False

    # 2. Беспроводные наушники: working_time и battery разрешены
    assert AttributeSanityValidator.is_valid("working_time", "30 ч", "headphones_wireless") is True
    assert AttributeSanityValidator.is_valid("battery", "500 мАч", "headphones_wireless") is True

    # 3. Базовая категория headphones: по умолчанию валидно (обратная совместимость)
    assert AttributeSanityValidator.is_valid("working_time", "30 ч", "headphones") is True

    # 4. Базовая категория headphones + контекст текста:
    wired_text = "Наушники проводные JBL C100SI 3.5 мм кабель"
    wireless_text = "Беспроводные наушники Sony WH-1000XM5 Bluetooth"

    assert AttributeSanityValidator.is_valid("working_time", "30 ч", "headphones", raw_text=wired_text) is False
    assert AttributeSanityValidator.is_valid("battery", "500 мАч", "headphones", raw_text=wired_text) is False
    assert AttributeSanityValidator.is_valid("working_time", "30 ч", "headphones", raw_text=wireless_text) is True

    # 5. Тип подключения (connection_type)
    assert AttributeSanityValidator.is_valid("connection_type", "проводные", "headphones") is True
    assert AttributeSanityValidator.is_valid("connection_type", "беспроводные", "headphones") is True
    assert AttributeSanityValidator.is_valid("connection_type", "мусорное значение", "headphones") is False

    # 6. Хелперы детекции
    assert AttributeSanityValidator.is_wired_headphones(wired_text) is True
    assert AttributeSanityValidator.is_wired_headphones(wireless_text) is False
    assert AttributeSanityValidator.is_wireless_headphones(wireless_text) is True
    assert AttributeSanityValidator.is_wireless_headphones("Bluetooth гарнитура с кабелем 3.5мм") is True
    assert AttributeSanityValidator.is_wired_headphones("Bluetooth гарнитура с кабелем 3.5мм") is False
