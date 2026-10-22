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

def test_clear_review_queue_endpoint():
    """Тест эндпоинта массовой очистки очереди модерации (POST /review-queue/clear и DELETE /review-queue)."""
    # Вызов очистки
    resp_clear = client.post("/api/extract/review-queue/clear")
    assert resp_clear.status_code == 200
    data_clear = resp_clear.json()
    assert data_clear["status"] == "success"
    assert "cleared_count" in data_clear
    assert data_clear["remaining_in_queue"] == 0

    # Проверка, что после очистки очередь возвращает 0 элементов
    resp_q = client.get("/api/extract/review-queue")
    assert resp_q.status_code == 200
    assert resp_q.json()["total_in_queue"] == 0
    assert len(resp_q.json()["items"]) == 0

    # Проверка метода DELETE
    resp_del = client.delete("/api/extract/review-queue")
    assert resp_del.status_code == 200
    assert resp_del.json()["status"] == "success"
    assert resp_del.json()["remaining_in_queue"] == 0


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
    assert 'js/app.js' in resp_root.text
    assert 'css/style.css' in resp_root.text

    assert client.get('/static/js/app.js').status_code == 200
    assert client.get('/static/js/api.js').status_code == 200
    assert client.get('/static/js/presets.js').status_code == 200
    assert client.get('/static/js/render.js').status_code == 200
    assert client.get('/static/css/style.css').status_code == 200


def test_catalog_enricher_robust_degradation():
    """Тест исключения silent-failure в CatalogEnricher: фиксация статуса деградации и предупреждений."""
    from app.services.catalog_enricher import CatalogEnricher
    from app.services.pipeline import CascadedExtractionPipeline

    # 1. Создание экземпляра с несуществующим файлом
    broken_enricher = CatalogEnricher(kb_path="definitely_non_existent_kb_file.json")
    assert broken_enricher.status == "degraded"
    assert "не найден" in broken_enricher.error_message
    assert broken_enricher.get_info()["status"] == "degraded"

    # 2. Вызов enrich не падает молча, а возвращает пустой список с логированием
    preds = broken_enricher.enrich(
        brand="Apple",
        model="iPhone 15",
        missing_attrs={"color", "memory_rom"},
        category_key="smartphones",
    )
    assert preds == []

    # 3. Интеграция в пайплайн: явное добавление в degraded_tiers и warnings
    p = CascadedExtractionPipeline(use_gliner=False, use_llm=False)
    p.catalog_enricher = broken_enricher
    res = p.process_card({"title": "Смартфон Apple iPhone 15"})
    assert "tier2_5_catalog_kb" in res["degraded_tiers"]
    assert any("деградированном режиме" in w for w in res["warnings"])


def test_universal_seller_attributes_handling():
    """Тест универсальной обработки атрибутов продавца (seller_attributes) для всех категорий."""
    from app.services.pipeline import CascadedExtractionPipeline

    pipeline = CascadedExtractionPipeline(use_gliner=False, use_llm=False)
    card = {
        "title": "Холодильник Haier",
        "category": "refrigerators",
        "seller_attributes": {
            "цвет": "серебристый",
            "объем": "346 л",
            "система_размораживания": "No Frost",
        },
    }
    res = pipeline.process_card(card)
    attrs = {p["attribute"]: p["value"] for p in res["predictions"]}
    assert attrs.get("color") == "серебристый"
    assert attrs.get("volume") == "346 л"
    assert attrs.get("defrost_system") == "No Frost"


def test_extract_from_url_endpoint():
    """Тест эндпоинта извлечения характеристик по внешней веб-ссылке (POST /api/extract/from-url)."""
    # 1. Некорректный URL -> 400 Bad Request
    resp_bad = client.post("/api/extract/from-url", json={"url": "not-a-valid-url"})
    assert resp_bad.status_code == 400

    # 2. Недоступный хост -> 502 Bad Gateway с пояснением ошибки
    resp_unreach = client.post("/api/extract/from-url", json={"url": "https://non-existent-domain-123456789.org/test"})
    assert resp_unreach.status_code == 502
    assert "Не удалось загрузить" in resp_unreach.json()["detail"]



def test_single_card_enqueues_to_review_queue_and_moderation_e2e():
    """Тест автоматического добавления сомнительной карточки (needs_review=True) в очередь модерации."""
    # 1. Очищаем очередь для чистоты теста
    client.post("/api/extract/review-queue/clear")
    q_initial = client.get("/api/extract/review/queue").json()
    assert q_initial["total_in_queue"] == 0

    # 2. Одиночное извлечение карточки Lenovo с низкой уверенностью (needs_review=True)
    card_payload = {
        "raw_text": (
            'Ноутбук Lenovo IdeaPad 3 Gen7 82RK003TRU оборудован шестиядерным процессором Intel Core i3 1215U 1.2 ГГц. '
            'Конфигурацией устройства предусмотрено наличие экрана разрешением 1920х1080 пикселей и диагональю 15,6". '
            'Частота обновления экрана составляет 60 Гц. Оперативный модуль для хранения данных обладает объемом 8 ГБ, '
            'объем жесткого диска — 512 ГБ.'
        )
    }
    resp = client.post("/extract", json=card_payload)
    assert resp.status_code == 200
    card_data = resp.json()
    assert card_data["needs_review"] is True
    ext_id = card_data["external_id"]
    assert ext_id is not None

    # 3. Проверяем, что карточка мгновенно появилась в очереди модерации по обоим путям
    for endpoint in ["/api/extract/review/queue", "/api/extract/review-queue", "/review/queue", "/review-queue"]:
        resp_q = client.get(endpoint)
        assert resp_q.status_code == 200
        q_data = resp_q.json()
        assert q_data["total_in_queue"] >= 1
        item_ids = [it["external_id"] for it in q_data["items"]]
        assert ext_id in item_ids
        target_item = next(it for it in q_data["items"] if it["external_id"] == ext_id)
        assert target_item["needs_review"] is True
        assert len(target_item["review_reasons"]) > 0
        assert "Lenovo" in target_item["title"] or "Lenovo" in target_item["raw_text"]
        assert isinstance(target_item["extracted_attributes"], dict)
        assert isinstance(target_item["detailed_predictions"], list)

    # 4. Проверяем ручное одобрение карточки модератором
    override_payload = {
        "external_id": ext_id,
        "action": "approve",
        "reviewed_by": "test_moderator",
        "attributes": {
            "brand": "Lenovo",
            "model": "IdeaPad 3",
            "cpu": "Intel Core i3 1215U",
        },
    }
    resp_approve = client.post("/api/extract/review-override", json=override_payload)
    assert resp_approve.status_code == 200
    assert resp_approve.json()["status"] == "success"

    # 5. Проверяем, что после утверждения карточка исчезла из очереди модерации
    resp_q_after = client.get("/api/extract/review/queue")
    assert resp_q_after.status_code == 200
    remaining_ids = [it["external_id"] for it in resp_q_after.json()["items"]]
    assert ext_id not in remaining_ids
