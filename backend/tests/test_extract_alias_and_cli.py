import subprocess
import sys
import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_extract_alias_endpoint():
    """Тест эндпоинта-алиаса POST /extract (для автоматических тестеров)."""
    payload = {
        "title": "Смартфон Apple iPhone 15 Pro Max 256GB синий титан",
        "description": "Флагманский смартфон"
    }
    response = client.post("/extract", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "Смартфоны"
    assert any(p["attribute"] == "brand" and p["value"] == "Apple" for p in data["predictions"])


def test_root_content_negotiation_json():
    """Тест GET / с Accept: application/json."""
    response = client.get("/", headers={"Accept": "application/json"})
    assert response.status_code == 200
    data = response.json()
    assert "endpoints" in data
    assert data["endpoints"]["extract"] == "POST /api/extract"
    assert data["endpoints"]["extract_alias"] == "POST /extract"


def test_extract_cli_module_import():
    """Тест функции extract_attributes из extract.py."""
    from extract import extract_attributes
    res = extract_attributes("Смартфон Samsung S24 256GB")
    assert res["category"] == "Смартфоны"
    assert any(p["attribute"] == "brand" and p["value"] == "Samsung" for p in res["predictions"])


def test_brand_typo_fuzzy_normalization_samsung():
    """Тест нечеткой канонизации опечаток и сохранения модели Galaxy S24 Ultra."""
    from extract import extract_attributes
    res = extract_attributes("смачунг гэлакси S24 Ultra 256gb фиолетовый")
    assert res["category"] == "Смартфоны"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds.get("brand") == "Samsung"
    assert "S24 Ultra" in preds.get("model", "")


def test_brand_candidate_unknown_preserved():
    """Тест сохранения нового неизвестного бренда как кандидата на модерацию."""
    from extract import extract_attributes
    res = extract_attributes("Смартфон CoolNewTech UltraPhone 256GB синий")
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds.get("brand") == "Coolnewtech"
    # Новый бренд требует подтверждения оператором
    assert res["needs_review"] is True


def test_smartphone_with_bundled_headphones_not_misclassified():
    """Регрессионный тест: смартфон с комплектными наушниками не должен определяться как Наушники."""
    from extract import extract_attributes
    text = (
        "Смартфон Apple iPhone 16 Pro - это современное устройство. "
        "Конфигурация памяти составляет 256 ГБ. Экран 6.3 дюйма, 2622x1206 пикселей, 120 Гц. "
        "Аккумулятор емкостью 3355 мА⋅ч. Время заряда составляет 30 минут. "
        "Корпус смартфона выполнен из титана. В комплекте идут кабель USB C, документация и наушники."
    )
    res = extract_attributes(text)
    assert res["category"] == "Смартфоны"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds.get("brand") == "Apple"
    assert "iPhone 16 Pro" in preds.get("model", "")
    assert preds.get("memory_rom") == "256 ГБ"
    assert preds.get("battery") == "3355 мАч"
    assert preds.get("color") == "титановый"
    # Комплектные наушники и время зарядки не должны порождать атрибут "время работы" для наушников
    assert "working_time" not in preds
    assert res["needs_review"] is False


def test_headphones_for_smartphone_classified_as_headphones():
    """Тест: наушники с предлогом совместимости 'для смартфона' определяются как Наушники."""
    from extract import extract_attributes
    res = extract_attributes("Беспроводные TWS наушники для смартфона Apple iPhone белые")
    assert res["category"] == "Наушники"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds.get("color") == "белый"


def test_vacuum_with_smartphone_app_control_classified_as_vacuum():
    """Тест: робот-пылесос с фразой 'управление со смартфона' определяется как Пылесосы."""
    from extract import extract_attributes
    res = extract_attributes("Робот-пылесос Xiaomi Robot Vacuum E10 белый с управлением со смартфона")
    assert res["category"] == "Пылесосы"
    preds = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert preds.get("brand") == "Xiaomi"

