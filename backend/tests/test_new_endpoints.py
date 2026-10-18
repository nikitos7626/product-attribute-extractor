import json
import io
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_api_info_endpoint():
    """Тест эндпоинта /api и /api/info."""
    for path in ("/api", "/api/info"):
        response = client.get(path)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert "endpoints" in data
        assert "extract_root" in data["endpoints"]


def test_taxonomy_endpoint():
    """Тест эндпоинта GET /api/extract/taxonomy."""
    response = client.get("/api/extract/taxonomy")
    assert response.status_code == 200
    data = response.json()
    assert "taxonomy" in data
    assert "smartphones" in data["taxonomy"]
    assert "tvs" in data["taxonomy"]
    # Проверяем, что os отсутствует в разрешенных для телевизоров
    assert "os" not in data["taxonomy"]["tvs"]["allowed_attributes"]


def test_metrics_endpoint():
    """Тест эндпоинта GET /api/extract/metrics."""
    response = client.get("/api/extract/metrics")
    assert response.status_code == 200
    data = response.json()
    assert ("macro_f1" in data) or ("benchmark_targets" in data)


def test_export_endpoint_json():
    """Тест пакетного экспорта предсказаний POST /api/extract/export (JSON)."""
    cards = [
        {
            "external_id": "test-1",
            "title": "Смартфон Apple iPhone 15 Pro 256GB синий",
            "description": "Батарея 3274 мАч, экран 6.1 дюйма",
        }
    ]
    raw_bytes = json.dumps(cards).encode("utf-8")
    files = {"file": ("cards.json", io.BytesIO(raw_bytes), "application/json")}

    response = client.post("/api/extract/export?output_format=json", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    pred = data["predictions"][0]
    assert pred["category"] == "Смартфоны"
    assert pred["extracted_attributes"]["brand"] == "Apple"
    assert pred["extracted_attributes"]["color"] == "синий"
    assert pred["extracted_attributes"]["memory_rom"] == "256 ГБ"


def test_export_endpoint_csv():
    """Тест пакетного экспорта предсказаний POST /api/extract/export (CSV)."""
    cards = [
        {
            "external_id": "test-csv",
            "title": "Холодильник LG No Frost серебристый",
            "description": "Двухкамерный холодильник с системой ноу фрост",
        }
    ]
    raw_bytes = json.dumps(cards).encode("utf-8")
    files = {"file": ("cards.json", io.BytesIO(raw_bytes), "application/json")}

    response = client.post("/api/extract/export?output_format=csv", files=files)
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    assert "external_id" in response.text
    assert "test-csv" in response.text
