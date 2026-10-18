import pytest

from app.extractors.regex_extractor import RegexExtractor


@pytest.fixture
def ext():
    return RegexExtractor()


def _get(preds, attr):
    return next((p for p in preds if p["attribute"] == attr), None)


# ---------- ROM ----------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("256 ГБ", "256 ГБ"),
        ("256GB", "256 ГБ"),
        ("1 ТБ", "1 ТБ"),
        ("1024 ГБ", "1 ТБ"),
        ("512 гб", "512 ГБ"),
    ],
)
def test_rom(ext, raw, expected):
    p = _get(ext.extract({"title": f"Смартфон {raw}", "description": ""}),
             "memory_rom")
    assert p and p["value"] == expected


# ---------- Экран ----------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ('6.7"', '6,7"'),
        ("6.7 дюймов", '6,7"'),
        ("6,7 дюйма", '6,7"'),
    ],
)
def test_screen(ext, raw, expected):
    p = _get(ext.extract({"title": f"Экран {raw}", "description": ""}),
             "screen_diagonal")
    assert p and p["value"] == expected


# ---------- RAM vs ROM ----------

@pytest.mark.parametrize(
    "text,ram,rom",
    [
        ("Ноутбук 16 ГБ ОЗУ 512 ГБ SSD",  "16 ГБ", "512 ГБ"),
        ("Ноутбук ОЗУ 32 ГБ / SSD 1 ТБ",  "32 ГБ", "1 ТБ"),
        ("Смартфон 8 ГБ RAM 128 ГБ ROM",  "8 ГБ",  "128 ГБ"),
        ("iPhone 256 ГБ",                 None,    "256 ГБ"),
    ],
)
def test_ram_rom_disambiguation(ext, text, ram, rom):
    preds = ext.extract({"title": text, "description": ""})
    got_ram = _get(preds, "memory_ram")
    got_rom = _get(preds, "memory_rom")
    assert (got_ram["value"] if got_ram else None) == ram
    assert (got_rom["value"] if got_rom else None) == rom

# ---------- Новые атрибуты ----------

@pytest.mark.parametrize("text,expected", [
    ("Смартфон 250 г", "250 г"),
    ("Наушники 250 грамм", "250 г"),
    ("Ноутбук вес 2.5 кг", "2,5 кг"),
    ("Пылесос вес: 1.5 kg", "1,5 кг"),
    ("Телевизор 15 кг", "15 кг"),
    ("Планшет 1500 г", "1,5 кг"),
])
def test_weight(ext, text, expected):
    p = _get(ext.extract({"title": text, "description": ""}), "weight")
    assert p and p["value"] == expected


@pytest.mark.parametrize("text,expected", [
    ("Пылесос 1500 Вт", "1500 Вт"),
    ("Чайник 1.5 кВт", "1500 Вт"),
    ("Микроволновка 800 w", "800 Вт"),
])
def test_power(ext, text, expected):
    p = _get(ext.extract({"title": text, "description": ""}), "power")
    assert p and p["value"] == expected


@pytest.mark.parametrize("text,expected", [
    ("Чайник 1.7 л", "1,7 л"),
    ("Кувшин 500 мл", "500 мл"),
    ("Кастрюля 3 литра", "3 л"),
    ("Бутылка 2000 мл", "2 л"),
])
def test_volume(ext, text, expected):
    p = _get(ext.extract({"title": text, "description": ""}), "volume")
    assert p and p["value"] == expected


@pytest.mark.parametrize("text,expected", [
    ("Гарантия 12 мес", "12 мес"),
    ("Гарантия: 24 месяца", "24 мес"),
    ("Гарантия 1 год", "12 мес"),
    ("Гарантия 2 года", "24 мес"),
    ("Warranty 1 year", "12 мес"),
])
def test_warranty(ext, text, expected):
    p = _get(ext.extract({"title": text, "description": ""}), "warranty")
    assert p and p["value"] == expected


@pytest.mark.parametrize("text,expected", [
    ("Смартфон Snapdragon 8 Gen 3", "Snapdragon 8 Gen 3"),
    ("Ноутбук Intel Core i7-12700H", "Intel Core i7-12700H"),
    ("Ноутбук Apple M3 Pro", "Apple M3 Pro"),
    ("Ноутбук Ryzen 7 5800H", "Ryzen 7 5800H"),
    ("MediaTek Dimensity 9200", "MediaTek Dimensity 9200"),
    ("Exynos 2200", "Exynos 2200"),
])
def test_cpu(ext, text, expected):
    p = _get(ext.extract({"title": text, "description": ""}), "cpu")
    assert p and p["value"] == expected


@pytest.mark.parametrize("text,expected", [
    ("Смартфон на Android 14", "Android"),
    ("iPhone под управлением iOS", "iOS"),
    ("Ноутбук Windows 11", "Windows"),
    ("MacBook macOS Sonoma", "macOS"),
    ("ПК Linux Ubuntu", "Ubuntu"),         # длинное совпадение выигрывает
    ("Сервер под управлением Linux", "Linux"),
])
def test_os(ext, text, expected):
    p = _get(ext.extract({"title": text, "description": ""}), "os")
    assert p and p["value"] == expected


def test_weight_no_false_positive_from_gb(ext):
    """'16 ГБ ОЗУ' не должно стать весом 16 г."""
    preds = ext.extract({"title": "Ноутбук 16 ГБ ОЗУ 512 ГБ SSD",
                         "description": ""})
    assert _get(preds, "weight") is None
    assert _get(preds, "memory_ram")["value"] == "16 ГБ"


def test_warranty_requires_keyword(ext):
    """'12 месяцев' без слова 'гарантия' — не warranty."""
    preds = ext.extract({"title": "Ноутбук со скидкой 12 месяцев",
                         "description": ""})
    assert _get(preds, "warranty") is None

@pytest.mark.parametrize("text,expected", [
    ("Ноутбук ChromeOS", "ChromeOS"),
    ("Ноутбук Chrome OS", "ChromeOS"),
    ("Смартфон HarmonyOS", "HarmonyOS"),
    ("Смартфон Harmony OS", "HarmonyOS"),
])
def test_os_longest_match_wins(ext, text, expected):
    p = _get(ext.extract({"title": text, "description": ""}), "os")
    assert p and p["value"] == expected

# ---------- Прочее ----------

def test_brand_from_seller_overrides_text(ext):
    preds = ext.extract({
        "title": "Смартфон Samsung Galaxy",
        "description": "",
        "seller_attributes": {"brand": "Apple"},
    })
    assert _get(preds, "brand")["value"] == "Apple"


def test_no_hallucination(ext):
    preds = ext.extract({"title": "Наушники беспроводные", "description": ""})
    assert _get(preds, "memory_rom") is None
    assert _get(preds, "screen_diagonal") is None


# ---------- Цвет vs Материал и склонения ----------

def test_color_in_color_phrase_wins_over_chassis_material(ext):
    """'в черном цвете' должно побеждать 'выполнен из титана'."""
    text = (
        "Смартфон Apple iPhone 16 Pro 128 ГБ в черном цвете. "
        "Корпус смартфона выполнен из титана и стекла."
    )
    preds = ext.extract({"title": "Apple iPhone 16 Pro", "description": text})
    color = _get(preds, "color")
    assert color is not None
    assert color["value"] == "чёрный"


def test_material_titanium_not_recognized_as_color_alone(ext):
    """'выполнен из титана' не должен ошибочно давать цвет титановый при отсутствии цвета."""
    text = (
        "Смартфон Apple iPhone 16 Pro. Корпус смартфона выполнен из титана. "
        "В комплекте кабель USB-C и наушники."
    )
    preds = ext.extract({"title": "Apple iPhone 16 Pro", "description": text})
    color = _get(preds, "color")
    assert color is None


@pytest.mark.parametrize("desc,expected", [
    ("Модель представлена в белом цвете", "белый"),
    ("Доступен в синем цвете", "синий"),
    ("В серебристом исполнении", "серебристый"),
    ("В золотом корпусе", "золотой"),
    ("В зеленом цвете", "зелёный"),
    ("В фиолетовом цвете", "фиолетовый"),
    ("Apple iPhone 16 Pro Desert Titanium", "золотой"),
    ("Apple iPhone 16 Pro Black Titanium", "чёрный"),
])
def test_color_declensions_and_compounds(ext, desc, expected):
    preds = ext.extract({"title": desc, "description": ""})
    color = _get(preds, "color")
    assert color is not None
    assert color["value"] == expected