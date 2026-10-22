from __future__ import annotations







import io



import json



import logging



from pathlib import Path



from typing import Any







from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile



from starlette.concurrency import run_in_threadpool



from app.config import settings



from app.schemas import BatchOut, CardIn, CardOut, ModelRegisterIn, PredictionOut, ReviewOverrideIn, ReviewQueueResponse, ReviewQueueClearResponse, UrlExtractIn, UrlExtractOut



from app.services.brand_registry import BrandRegistry, process_file_lock



from app.services.pipeline import CascadedExtractionPipeline
from app.services.review_queue import ReviewQueueService







logger = logging.getLogger(__name__)







router = APIRouter(prefix="/api/extract", tags=["extract"])











def get_repo_root() -> Path:



    """Динамический поиск корня репозитория по маркерам .git / data / output."""



    current = Path(__file__).resolve().parent



    for p in [current] + list(current.parents):



        if (p / ".git").exists() or ((p / "data").is_dir() and (p / "output").is_dir()):



            return p



    return Path(__file__).resolve().parent.parent.parent.parent











_lazy_pipeline: CascadedExtractionPipeline | None = None











def get_pipeline(request: Request = None) -> CascadedExtractionPipeline:



    """Dependency Injection провайдер для CascadedExtractionPipeline."""



    global _lazy_pipeline



    if request is not None and hasattr(request, "app") and hasattr(request.app, "state"):



        app_pipe = getattr(request.app.state, "pipeline", None)



        if app_pipe is not None:



            return app_pipe



    if _lazy_pipeline is None:



        _lazy_pipeline = CascadedExtractionPipeline(use_gliner=True)



        if getattr(settings, "preload_models", True):



            _lazy_pipeline.warmup()



    return _lazy_pipeline











# Ленивый доступ для обратной совместимости прямого импорта extract._pipeline



def __getattr__(name: str) -> Any:



    if name == "_pipeline":



        return get_pipeline()



    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")











# --------------------------- хелперы ---------------------------







def _run(card: CardIn, pipeline: CascadedExtractionPipeline | None = None, enqueue_review: bool = True) -> CardOut:
    """Прогоняет одну карточку через каскадный пайплайн и упаковывает в CardOut."""
    import hashlib
    pipe = pipeline or get_pipeline()

    if not card.external_id:
        raw_key = card.raw_text or card.title or card.description or "card"
        card.external_id = f"card-{hashlib.md5(raw_key.encode('utf-8')).hexdigest()[:8]}"

    res = pipe.process_card({
        "external_id": card.external_id,
        "category": card.category,
        "title": card.title,
        "description": card.description,
        "raw_text": card.raw_text,
        "seller_attributes": card.seller_attributes,
    })

    card_out = CardOut(
        external_id=res.get("external_id") or card.external_id,
        category=res["category"],
        category_key=res.get("category_key"),
        subcategory=res.get("subcategory"),
        predictions=[PredictionOut(**p) for p in res["predictions"]],
        missing=res["missing"],
        overall_confidence=res["overall_confidence"],
        needs_review=res["needs_review"],
        status=res.get("status", "approved"),
        status_description=res.get("status_description", ""),
        review_reasons=res.get("review_reasons", []),
        warnings=res.get("warnings", []),
        degraded_tiers=res.get("degraded_tiers", []),
        taxonomy_status=res.get("taxonomy_status"),
    )

    if enqueue_review and card_out.needs_review:
        ReviewQueueService.get_instance().enqueue_card(card, card_out)

    return card_out





@router.post("/from-url", response_model=UrlExtractOut, response_model_exclude_none=True)

async def extract_from_url(

    body: UrlExtractIn,

    pipeline: CascadedExtractionPipeline = Depends(get_pipeline),

) -> UrlExtractOut:

    """

    Извлекает характеристики товара по внешней ссылке на страницу товара в открытом доступе

    (DNS, маркетплейсы, сайты производителей, агрегаторы электроники).

    Безопасно скачивает HTML, очищает текст и прогоняет через каскадный пайплайн ИИ.

    """

    import html

    import re

    import urllib.parse

    import httpx



    target_url = body.url.strip()

    if not target_url.startswith(("http://", "https://")):

        target_url = "https://" + target_url



    parsed = urllib.parse.urlparse(target_url)

    if not parsed.netloc or "." not in parsed.netloc:

        raise HTTPException(400, "Указан некорректный URL страницы товара (отсутствует доменное имя)")



    headers = {

        "User-Agent": (

            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "

            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        ),

        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",

        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",

    }



    try:

        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=headers) as client:

            resp = await client.get(target_url)

            resp.raise_for_status()

            raw_html = resp.text

    except Exception as e:

        logger.warning("Failed to fetch product URL %s: %s", target_url, e)

        raise HTTPException(502, f"Не удалось загрузить страницу по внешней ссылке: {e}")



    # Извлечение заголовка страницы (<title>...</title>)

    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)

    page_title = ""

    if title_match:

        page_title = html.unescape(title_match.group(1)).strip()

        page_title = re.sub(r"\s*[—–|-]\s*(купить в|интернет-магазин|каталог|dns|яндекс|мвидео).*$", "", page_title, flags=re.IGNORECASE).strip()



    # Удаление служебных тегов

    clean_html = re.sub(r"<(script|style|svg|nav|footer)[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)

    clean_text = re.sub(r"<[^>]+>", " ", clean_html)

    clean_text = html.unescape(clean_text)

    clean_text = re.sub(r"\s+", " ", clean_text).strip()



    snippet = clean_text[:400] + ("..." if len(clean_text) > 400 else "")



    card_dict = {

        "title": body.title or page_title,

        "description": clean_text[:15000],

        "category": body.category,

    }

    res = pipeline.process_card(card_dict)



    card_out = CardOut(

        external_id=res.get("external_id") or "from-url",

        category=res["category"],

        predictions=[PredictionOut(**p) for p in res["predictions"]],

        missing=res["missing"],

        overall_confidence=res["overall_confidence"],

        needs_review=res["needs_review"],

        status=res.get("status", "approved"),

        status_description=res.get("status_description", ""),

        review_reasons=res.get("review_reasons", []),

        warnings=res.get("warnings", []),

        degraded_tiers=res.get("degraded_tiers", []),

        taxonomy_status=res.get("taxonomy_status"),

    )



    if card_out.needs_review:
        ReviewQueueService.get_instance().enqueue_card(
            {
                "external_id": card_out.external_id,
                "title": page_title or body.title or "Товар из URL",
                "category": card_out.category,
                "raw_text": clean_text[:15000],
                "description": snippet,
            },
            card_out,
        )

    return UrlExtractOut(

        status="success",

        url=target_url,

        page_title=page_title,

        extracted_text_snippet=snippet,

        card_result=card_out,

    )







def _rows_from_file(filename: str, raw: bytes) -> list[dict]:



    """



    Строгая валидация и парсинг входных файлов пакетной обработки (CSV или JSON).



    Проверяет размер файла, формат, структуру объектов и лимиты элементов.



    """



    if not raw or not raw.strip():



        raise HTTPException(400, "Файл пустой или не содержит данных")







    max_bytes = getattr(settings, "max_batch_file_size_bytes", 50 * 1024 * 1024)



    if len(raw) > max_bytes:



        raise HTTPException(413, f"Размер файла ({len(raw) / (1024 * 1024):.1f} МБ) превышает лимит ({max_bytes // (1024 * 1024)} МБ)")







    name = (filename or "").lower().strip()



    if not (name.endswith(".json") or name.endswith(".csv")):



        raise HTTPException(400, "Неподдерживаемый формат файла. Допустимы только .json и .csv файлы")







    rows: list[dict] = []







    if name.endswith(".json"):



        try:



            data = json.loads(raw.decode("utf-8-sig", errors="replace"))



        except json.JSONDecodeError as e:



            raise HTTPException(400, f"Невалидный синтаксис JSON: {e}") from e







        if isinstance(data, list):



            rows = data



        elif isinstance(data, dict):



            rows = [data]



        else:



            raise HTTPException(400, f"Невалидная структура JSON: ожидается массив объектов или один объект (получен {type(data).__name__})")







        if not rows:



            raise HTTPException(400, "Файл JSON не содержит карточек (передан пустой массив)")







        for idx, item in enumerate(rows):



            if not isinstance(item, dict):



                raise HTTPException(400, f"Запись #{idx + 1} в JSON не является объектом (словарем)")







    elif name.endswith(".csv"):



        import pandas as pd



        try:



            df = pd.read_csv(io.BytesIO(raw), encoding="utf-8")



        except UnicodeDecodeError:



            try:



                df = pd.read_csv(io.BytesIO(raw), encoding="cp1251")



            except Exception as e:



                raise HTTPException(400, f"Ошибка кодировки CSV файла: {e}") from e



        except pd.errors.EmptyDataError as e:



            raise HTTPException(400, "CSV файл пустой или не содержит данных") from e



        except Exception as e:



            raise HTTPException(400, f"Ошибка разбора CSV: {e}") from e







        if df.empty:



            raise HTTPException(400, "CSV файл не содержит строк данных")







        col_names = [str(c).lower().strip() for c in df.columns]



        expected_signals = {"title", "description", "raw_text", "category", "external_id", "id", "name"}



        if not any(c in expected_signals for c in col_names):



            raise HTTPException(400, f"В CSV файле не найдены обязательные колонки товара ({expected_signals}). Найдены: {list(df.columns)}")







        df = df.where(pd.notnull(df), None)



        rows = df.to_dict(orient="records")







    max_items = getattr(settings, "max_batch_items", 10000)



    if len(rows) > max_items:



        raise HTTPException(400, f"Количество карточек ({len(rows)}) превышает установленный лимит пакета ({max_items})")







    return rows











def _process_batch_sync(rows: list[dict], pipe: CascadedExtractionPipeline) -> list[CardOut]:
    """Синхронный воркер пакетной обработки с частичной устойчивостью (Partial Batch Resilience)."""
    cards: list[CardOut] = []
    to_enqueue: list[tuple[Any, Any]] = []

    for i, row in enumerate(rows):
        sa = row.get("seller_attributes")
        if isinstance(sa, str):
            try:
                row["seller_attributes"] = json.loads(sa) if sa.strip() else {}
            except json.JSONDecodeError:
                row["seller_attributes"] = {}
        elif sa is None:
            row["seller_attributes"] = {}

        try:
            card_in = CardIn(**row)
            c_out = _run(card_in, pipeline=pipe, enqueue_review=False)
            cards.append(c_out)
            if c_out.needs_review:
                to_enqueue.append((card_in, c_out))
        except Exception as e:
            logger.warning("Batch processing item #%d failed: %s", i + 1, e)
            failed_card = CardOut(
                external_id=str(row.get("external_id") or row.get("id") or f"row-{i+1}"),
                category=str(row.get("category") or "unknown"),
                predictions=[],
                missing=[],
                overall_confidence=0.0,
                needs_review=True,
                status="failed",
                status_description=f"Ошибка обработки карточки: {e}",
                review_reasons=[f"Сбой парсинга/валидации: {e}"],
            )
            cards.append(failed_card)
            to_enqueue.append((row, failed_card))

    if to_enqueue:
        ReviewQueueService.get_instance().enqueue_batch(to_enqueue)

    return cards











def _process_export_sync(



    rows: list[dict],



    output_format: str,



    pipeline: CascadedExtractionPipeline,



) -> Any:



    """Синхронный воркер экспорта предсказаний."""



    results: list[dict] = []



    for i, row in enumerate(rows):



        sa = row.get("seller_attributes")



        if isinstance(sa, str):



            try:



                row["seller_attributes"] = json.loads(sa) if sa.strip() else {}



            except json.JSONDecodeError:



                row["seller_attributes"] = {}



        elif sa is None:



            row["seller_attributes"] = {}







        try:



            card_in = CardIn(**row)



            card_res = pipeline.process_card({



                "external_id": card_in.external_id,



                "category": card_in.category,



                "title": card_in.title,



                "description": card_in.description,



                "raw_text": card_in.raw_text,



                "seller_attributes": card_in.seller_attributes,



            })



            flat_attrs = {p["attribute"]: p["value"] for p in card_res.get("predictions", [])}







            results.append({



                "external_id": card_res.get("external_id") or f"sku-{i+1}",



                "title": row.get("title", ""),



                "category": card_res.get("category"),



                "status": card_res.get("status", "approved"),



                "status_description": card_res.get("status_description", ""),



                "review_reasons": card_res.get("review_reasons", []),



                "overall_confidence": card_res.get("overall_confidence"),



                "needs_review": card_res.get("needs_review"),



                "extracted_attributes": flat_attrs,



                "missing_required": card_res.get("missing", []),



                "detailed_predictions": card_res.get("predictions", []),



            })



        except Exception as e:



            logger.warning("Export item #%d failed: %s", i + 1, e)



            results.append({



                "external_id": str(row.get("external_id") or row.get("id") or f"sku-{i+1}"),



                "title": row.get("title", ""),



                "category": str(row.get("category") or "unknown"),



                "status": "failed",



                "status_description": f"Ошибка обработки: {e}",



                "review_reasons": [str(e)],



                "overall_confidence": 0.0,



                "needs_review": True,



                "extracted_attributes": {},



                "missing_required": [],



                "detailed_predictions": [],



            })







    if output_format.lower() == "csv":



        import pandas as pd



        from fastapi.responses import Response



        flat_rows = []



        for r in results:



            item = {



                "external_id": r["external_id"],



                "category": r["category"],



                "status": r.get("status", "approved"),



                "status_description": r.get("status_description", ""),



                "overall_confidence": r["overall_confidence"],



                "needs_review": r["needs_review"],



                "review_reasons": "; ".join(r.get("review_reasons", [])),



                "missing_required": ", ".join(r["missing_required"]),



            }



            for attr_name, val in r["extracted_attributes"].items():



                item[f"attr_{attr_name}"] = val



            flat_rows.append(item)







        df = pd.DataFrame(flat_rows)



        csv_buffer = io.StringIO()



        df.to_csv(csv_buffer, index=False, encoding="utf-8")



        return Response(



            content=csv_buffer.getvalue(),



            media_type="text/csv",



            headers={"Content-Disposition": 'attachment; filename="predictions.csv"'},



        )







    return {"total": len(results), "predictions": results}











# --------------------------- эндпоинты ---------------------------







@router.post("/brands/register")



def register_brand(alias: str, canonical: str | None = None) -> dict:



    """



    Динамическая регистрация нового бренда в каталог М.Видео на лету.



    Мгновенно добавляет в FlashText и сохраняет в brands.csv.



    """



    registry = BrandRegistry.get_instance()



    success = registry.register_brand(alias, canonical)



    canon = registry.get_canonical(alias) or (canonical or alias.strip().title())



    return {"ok": success, "brand": canon, "alias": alias.strip().lower()}











@router.post("/models/register")



def register_model(



    payload: ModelRegisterIn,



    pipeline: CascadedExtractionPipeline = Depends(get_pipeline),



) -> dict:



    """



    Динамическая регистрация и самообучение спецификаций модели по ID модели или паре бренд+модель.



    Мгновенно обновляет базу знаний CatalogEnricher и сохраняет в catalog_models_kb.json.



    """



    if not pipeline.catalog_enricher:



        return {"ok": False, "detail": "Catalog enricher is disabled"}







    success = pipeline.catalog_enricher.register_model_specs(



        brand=payload.brand,



        model=payload.model,



        specs={k: str(v) for k, v in payload.specs.items()},



        model_id=payload.model_id,



        persist=True,



    )



    return {



        "ok": success,



        "model_id": payload.model_id,



        "brand": payload.brand,



        "model": payload.model,



        "registered_attributes": list(payload.specs.keys()),



    }











@router.get("/health")



def health(pipeline: CascadedExtractionPipeline = Depends(get_pipeline)) -> dict:



    """Быстрая проверка состояния экстракторов, таксономии и пайплайна."""



    return {



        "ok": True,



        "pipeline": "CascadedExtractionPipeline",



        "tier1_regex": pipeline.regex_extractor.health(),



        "tier2_gliner": pipeline.gliner_extractor.health() if pipeline.gliner_extractor else False,



        "taxonomy": {



            "status": pipeline.taxonomy_manager.status,



            "categories_count": pipeline.taxonomy_manager.categories_count,



            "error": pipeline.taxonomy_manager.error_message,



        },



    }











@router.post("", response_model=CardOut, response_model_exclude_none=True)
@router.post("/", response_model=CardOut, response_model_exclude_none=True)



def extract_one(



    card: CardIn,



    pipeline: CascadedExtractionPipeline = Depends(get_pipeline),



) -> CardOut:



    """



    Одна карточка → список извлечённых атрибутов.



    """



    return _run(card, pipeline=pipeline)











@router.post("/batch", response_model=BatchOut, response_model_exclude_none=True)
async def extract_batch(
    request: Request,
    file: UploadFile | None = File(None),
    pipeline: CascadedExtractionPipeline = Depends(get_pipeline),
) -> BatchOut:
    """
    Пакетная обработка карточек: принимает файл (CSV/JSON через multipart)
    или прямое тело JSON {"items": [...]} / [...] с неблокирующим тредпулом.
    """
    content_type = request.headers.get("content-type", "") if request is not None else ""
    if file is not None and file.filename:
        raw_bytes = await file.read()
        rows = _rows_from_file(file.filename or "", raw_bytes)
    elif "application/json" in content_type:
        try:
            body = await request.json()
            if isinstance(body, dict):
                rows = body.get("items") or body.get("cards") or [body]
            elif isinstance(body, list):
                rows = body
            else:
                rows = []
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")
    elif file is not None:
        raw_bytes = await file.read()
        rows = _rows_from_file(file.filename or "input.json", raw_bytes)
    else:
        raise HTTPException(
            status_code=400,
            detail="Требуется файл (multipart/form-data: file) или JSON-тело (application/json: {'items': [...]})"
        )

    cards = await run_in_threadpool(_process_batch_sync, rows, pipeline)







    approved = sum(1 for c in cards if c.status == "approved" and not c.needs_review)



    needs_review = sum(1 for c in cards if c.needs_review and c.status != "failed")



    failed = sum(1 for c in cards if c.status == "failed")







    if failed == len(cards) and len(cards) > 0:



        overall_status = "failed"



    elif failed > 0:



        overall_status = "partial_failure"



    elif needs_review > 0:



        overall_status = "needs_review"



    else:



        overall_status = "approved"







    return BatchOut(



        total=len(cards),



        processed=len(cards),



        approved_count=approved,



        needs_review_count=needs_review,



        failed_count=failed,



        overall_status=overall_status,



        cards=cards,



    )











@router.get("/metrics")



def get_metrics() -> dict:



    """



    Возвращает стандартизированный отчет валидации качества (per-attribute F1, Precision, Recall, Coverage).



    Отчет сгенерирован на эталонном Gold Dataset М.Видео.



    """



    base_dir = get_repo_root()



    report_path = base_dir / "output" / "metrics_report.json"







    if report_path.exists():



        try:



            with open(report_path, "r", encoding="utf-8") as f:



                return json.load(f)



        except Exception as e:



            raise HTTPException(500, f"Ошибка чтения metrics_report.json: {e}")







    return {



        "status": "baseline",



        "benchmark_targets": {



            "category_accuracy": 1.0,



            "catalog_coverage": 1.0,



            "macro_f1": 0.9513,



            "micro_f1": 0.9503,



        },



        "message": "Для обновления запустите: python scripts/evaluate_metrics.py",



    }











@router.get("/taxonomy")



def get_taxonomy(pipeline: CascadedExtractionPipeline = Depends(get_pipeline)) -> dict:



    """



    Возвращает актуальную таксономию М.Видео: категории, обязательные поля и строгие белые списки.



    """



    from app.services.pipeline import CATEGORY_SCHEMAS



    from app.extractors.sanity import AttributeSanityValidator







    out = {}



    for cat_key, schema in CATEGORY_SCHEMAS.items():



        out[cat_key] = {



            "name_ru": schema["name_ru"],



            "required_attributes": sorted(list(schema["required_attrs"])),



            "allowed_attributes": sorted(list(AttributeSanityValidator.ALLOWED_ATTRS_BY_CATEGORY.get(cat_key, set()))),



            "gliner_labels": schema["gliner_labels"],



        }



    return {



        "status": pipeline.taxonomy_manager.status,



        "total_catalog_categories": pipeline.taxonomy_manager.categories_count,



        "taxonomy": out,



    }











@router.post("/export")



async def export_batch_predictions(



    file: UploadFile = File(...),



    output_format: str = "json",



    pipeline: CascadedExtractionPipeline = Depends(get_pipeline),



):



    """



    Пакетный экспорт стандартизированных предсказаний в формате JSON или CSV (неблокирующий тредпул).



    """



    raw_bytes = await file.read()



    rows = _rows_from_file(file.filename or "", raw_bytes)



    return await run_in_threadpool(_process_export_sync, rows, output_format, pipeline)











@router.get("/review-queue", response_model=ReviewQueueResponse)
@router.get("/review/queue", response_model=ReviewQueueResponse)
def get_review_queue(limit: int = 5) -> ReviewQueueResponse:
    """
    Возвращает список карточек из очереди ручной модерации (Human-in-the-Loop),
    помеченных флагом needs_review=True или имеющих пропущенные обязательные атрибуты.
    """
    total, items = ReviewQueueService.get_instance().get_queue(limit=limit)
    return ReviewQueueResponse(
        total_in_queue=total,
        items=items,
    )


@router.post("/review-queue/clear", response_model=ReviewQueueClearResponse)
@router.post("/review/queue/clear", response_model=ReviewQueueClearResponse)
@router.delete("/review-queue", response_model=ReviewQueueClearResponse)
@router.delete("/review/queue", response_model=ReviewQueueClearResponse)
def clear_review_queue() -> ReviewQueueClearResponse:
    """
    Очищает очередь ручной модерации (Human-in-the-Loop):
    утверждает все оставшиеся сомнительные карточки (needs_review=False)
    в output/predictions.json и синхронизирует output/predictions.csv.
    """
    res = ReviewQueueService.get_instance().clear_queue()
    return ReviewQueueClearResponse(
        status=res.get("status", "success"),
        message=res.get("message", "Очередь модерации успешно очищена"),
        cleared_count=res.get("cleared_count", 0),
        remaining_in_queue=res.get("remaining_in_queue", 0),
    )


@router.post("/review-override")
@router.post("/review/override")
@router.post("/review-queue/override")
@router.post("/review/queue/override")
def submit_review_override(body: ReviewOverrideIn) -> dict:
    """
    Применяет ручное решение модератора (Human-in-the-Loop):
    утверждает карточку, переопределяет атрибуты или отклоняет сомнительное значение.
    Обновляет output/predictions.json и output/reviewed_predictions.json.
    """
    return ReviewQueueService.get_instance().submit_override(body)