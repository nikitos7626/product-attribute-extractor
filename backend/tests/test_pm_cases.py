import pytest
from app.services.pipeline import CascadedExtractionPipeline
from scripts.pm_cases import cases


@pytest.fixture(scope="module")
def pipeline():
    return CascadedExtractionPipeline(use_gliner=True)


def test_pm_case_1_galaxy_s24(pipeline):
    c = cases[0]
    res = pipeline.process_card({"title": c["title"], "description": c["desc"]})
    assert res["category"] == "Смартфоны"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds["brand"] == "Samsung"
    assert "Galaxy S24 Ultra" in preds["model"]
    assert preds["memory_rom"] == "256 ГБ"
    assert preds["battery"] == "5000 мАч"
    assert preds["color"] == "фиолетовый"
    assert res["needs_review"] is False


def test_pm_case_2_iphone_15_pro_max(pipeline):
    c = cases[1]
    res = pipeline.process_card({"title": c["title"], "description": c["desc"]})
    assert res["category"] == "Смартфоны"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds["brand"] == "Apple"
    assert preds["model"] == "iPhone 15 Pro Max"
    assert preds["memory_rom"] == "512 ГБ"
    assert preds["cpu"] == "A17 Pro"
    # Батарея автоматически дозаполнена из каталога М.Видео (catalog_kb)
    assert "battery" in preds
    assert res["needs_review"] is False


def test_pm_case_3_redmi_note_13_pro(pipeline):
    c = cases[2]
    res = pipeline.process_card({"title": c["title"], "description": c["desc"]})
    assert res["category"] == "Смартфоны"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds["brand"] == "Xiaomi"
    assert preds["model"] == "Redmi Note 13 Pro"
    assert preds["memory_ram"] == "8 ГБ"
    assert preds["memory_rom"] == "256 ГБ"
    assert res["needs_review"] is False


def test_pm_case_4_realme_gt_6t(pipeline):
    c = cases[3]
    res = pipeline.process_card({"title": c["title"], "description": c["desc"]})
    assert res["category"] == "Смартфоны"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds["brand"] == "Realme"
    assert preds["model"] == "GT 6T"
    assert preds["memory_ram"] == "12 ГБ"
    assert preds["memory_rom"] == "256 ГБ"
    assert preds["cpu"] == "Snapdragon 7+ Gen 3"
    assert preds["color"] == "золотой"
    assert res["needs_review"] is False


def test_pm_case_5_samsung_a54(pipeline):
    c = cases[4]
    res = pipeline.process_card({"title": c["title"], "description": c["desc"]})
    assert res["category"] == "Смартфоны"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds["brand"] == "Samsung"
    assert "A54" in preds["model"]
    assert preds["battery"] == "5000 мАч"
    assert preds["color"] == "синий"
    # 5g must NOT be confused with 5g weight
    assert preds.get("weight") != "5 г"
    assert res["needs_review"] is False


def test_pm_case_6_motorola_edge_50(pipeline):
    c = cases[5]
    res = pipeline.process_card({"title": c["title"], "description": c["desc"]})
    assert res["category"] == "Смартфоны"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds["brand"] == "Motorola"
    assert preds["model"] == "Edge 50"
    assert preds["memory_ram"] == "8 ГБ"
    assert preds["memory_rom"] == "256 ГБ"
    assert preds["color"] == "зелёный"
    assert res["needs_review"] is False


def test_pm_case_7_infinix_hot_40(pipeline):
    c = cases[6]
    res = pipeline.process_card({"title": c["title"], "description": c["desc"]})
    assert res["category"] == "Смартфоны"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds["brand"] == "Infinix"
    assert "HOT 40" in preds["model"]
    # Fluff "красивый дизайн" must not be parsed as color
    assert "color" not in preds
    # Батарея, экран и память подтянуты из каталога, остался только отсутствующий цвет
    assert "battery" in preds
    assert "screen_diagonal" in preds
    assert "color" in res["missing"]
    assert res["needs_review"] is True


def test_pm_case_8_huawei_p60_pro(pipeline):
    c = cases[7]
    res = pipeline.process_card({"title": c["title"], "description": c["desc"]})
    # Must not be classified as TVs despite OLED mention
    assert res["category"] == "Смартфоны"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds["brand"] == "Huawei"
    assert preds["model"] == "P60 Pro"
    assert preds["model"] != "экран"
    assert preds["memory_rom"] == "256 ГБ"
    assert preds["battery"] == "4815 мАч"
    assert preds["color"] == "чёрный"
    assert res["needs_review"] is False


def test_pm_case_9_sony_xperia_1_vi(pipeline):
    c = cases[8]
    res = pipeline.process_card({"title": c["title"], "description": c["desc"]})
    # Must not be classified as TVs despite 4K OLED mention
    assert res["category"] == "Смартфоны"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds["brand"] == "Sony"
    assert preds["model"] == "Xperia 1 VI"
    assert preds["memory_ram"] == "12 ГБ"
    assert preds["memory_rom"] == "256 ГБ"
    assert preds["cpu"] == "Snapdragon 8 Gen 3"
    assert preds["battery"] == "5000 мАч"
    assert preds["color"] == "чёрный"
    assert res["needs_review"] is False


def test_pm_case_10_powerbank_20000mah(pipeline):
    text = (
        "Внешний аккумулятор Xiaomi Mi Power Bank 3 20000 mAh Fast Charge. "
        "Емкость 20000 мАч, максимальная мощность зарядки 18 Вт, цвет черный. "
        "Оснащен разъемами USB-A и USB-C."
    )
    res = pipeline.process_card({"raw_text": text})
    assert res["category"] == "Внешние аккумуляторы (Power Bank)"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds["brand"] == "Xiaomi"
    assert preds["battery"] == "20000 мАч"
    assert preds["color"] == "чёрный"
    assert preds["power"] == "18 Вт"
    assert "Mi Power Bank" in preds["model"]
    # Powerbank must NOT have screen or ROM
    assert "screen_diagonal" not in preds
    assert "memory_rom" not in preds
    assert res["needs_review"] is False


def test_pm_case_11_tv_strict_attributes_no_os(pipeline):
    text = (
        "Телевизор LG OLED evo OLED55C4RLA с диагональю 55 дюймов и разрешением 3840x2160 пикселей 4K. "
        "Частота обновления экрана составляет 120 Гц. Операционная система webOS 24. "
        "Мощность акустической системы 40 Вт. Цвет: черный."
    )
    res = pipeline.process_card({"raw_text": text})
    assert res["category"] == "Телевизоры"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds["brand"] == "LG"
    assert preds["screen_diagonal"] == '55,0"'
    assert preds["resolution"] == "3840×2160"
    assert preds["refresh_rate"] == "120 Гц"
    assert preds["power"] == "40 Вт"
    assert preds["color"] == "чёрный"
    # os не входит в схему датасета для ТВ и должна быть строго отфильтрована!
    assert "os" not in preds
    assert res["needs_review"] is False


