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


def test_review_queue_and_override_endpoints():
    """Тест интерактивных эндпоинтов модерации HITL (GET /review-queue, POST /review-override)."""
    # 1. Запрос очереди
    resp_q = client.get("/api/extract/review-queue?limit=10")
    assert resp_q.status_code == 200
    data_q = resp_q.json()
    assert "total_in_queue" in data_q
    assert isinstance(data_q["items"], list)

    # 2. Отправка ручного переопределения модератором
    override_payload = {
        "external_id": "test-override-sku",
        "attribute": "color",
        "override_value": "титановый серый",
        "action": "override",
        "reviewed_by": "qa_operator",
    }
    resp_ov = client.post("/api/extract/review-override", json=override_payload)
    assert resp_ov.status_code == 200
    data_ov = resp_ov.json()
    assert data_ov["status"] == "success"
    assert data_ov["action_recorded"]["override_value"] == "титановый серый"
    assert data_ov["action_recorded"]["reviewed_by"] == "qa_operator"


def test_api_key_auth_protection():
    """Тест защищенного режима авторизации: блокировка без ключа и пропуск с валидным ключом."""
    from app.config import settings

    # Временно активируем защиту API-ключом
    original_key = settings.api_key
    try:
        settings.api_key = "secret-test-token"

        # Запрос без ключа -> 401 Unauthorized
        card = {"title": "Смартфон Apple iPhone 15 128GB"}
        resp_unauth = client.post("/api/extract", json=card)
        assert resp_unauth.status_code == 401
        assert "Unauthorized" in resp_unauth.json()["detail"]

        # Запрос с неправильным ключом -> 401
        resp_bad = client.post("/api/extract", json=card, headers={"X-API-Key": "wrong-token"})
        assert resp_bad.status_code == 401

        # Запрос с валидным ключом через X-API-Key -> 200 OK
        resp_ok = client.post("/api/extract", json=card, headers={"X-API-Key": "secret-test-token"})
        assert resp_ok.status_code == 200
        assert resp_ok.json()["category"] == "Смартфоны"

        # Запрос с валидным Bearer-токеном -> 200 OK
        resp_bearer = client.post("/api/extract", json=card, headers={"Authorization": "Bearer secret-test-token"})
        assert resp_bearer.status_code == 200

        # Публичные эндпоинты (/health, /api/info, /docs) доступны без ключа
        assert client.get("/health").status_code == 200
        assert client.get("/api/info").status_code == 200

    finally:
        # Восстанавливаем открытый режим по умолчанию
        settings.api_key = original_key


def test_modular_frontend_serving():
    """Тест отдачи модульного веб-интерфейса и статических ассетов."""
    resp_root = client.get('/', headers={'Accept': 'text/html'})
    assert resp_root.status_code == 200
    assert '<!DOCTYPE html>' in resp_root.text
    assert '/static/js/app.js' in resp_root.text
    assert '/static/css/style.css' in resp_root.text

    assert client.get('/static/js/app.js').status_code == 200
    assert client.get('/static/js/api.js').status_code == 200
    assert client.get('/static/js/presets.js').status_code == 200
    assert client.get('/static/js/render.js').status_code == 200
    assert client.get('/static/css/style.css').status_code == 200
