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
