from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool
from app.config import settings
from app.schemas import BatchOut, CardIn, CardOut, PredictionOut, ReviewOverrideIn, ReviewQueueResponse
from app.services.brand_registry import BrandRegistry, process_file_lock
from app.services.pipeline import CascadedExtractionPipeline

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
    return _lazy_pipeline


# Ленивый доступ для обратной совместимости прямого импорта extract._pipeline
def __getattr__(name: str) -> Any:
    if name == "_pipeline":
        return get_pipeline()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# --------------------------- хелперы ---------------------------

def _run(card: CardIn, pipeline: CascadedExtractionPipeline | None = None) -> CardOut:
    """Прогоняет одну карточку через каскадный пайплайн и упаковывает в CardOut."""
    pipe = pipeline or get_pipeline()
    res = pipe.process_card({
        "external_id": card.external_id,
        "category": card.category,
        "title": card.title,
        "description": card.description,
        "raw_text": card.raw_text,
        "seller_attributes": card.seller_attributes,
    })
    return CardOut(
        external_id=res["external_id"],
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
            cards.append(_run(card_in, pipeline=pipe))
        except Exception as e:
            logger.warning("Batch processing item #%d failed: %s", i + 1, e)
            cards.append(CardOut(
                external_id=str(row.get("external_id") or row.get("id") or f"row-{i+1}"),
                category=str(row.get("category") or "unknown"),
                predictions=[],
                missing=[],
                overall_confidence=0.0,
                needs_review=True,
                status="failed",
                status_description=f"Ошибка обработки карточки: {e}",
                review_reasons=[f"Сбой парсинга/валидации: {e}"],
            ))
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


@router.post("", response_model=CardOut)
def extract_one(
    card: CardIn,
    pipeline: CascadedExtractionPipeline = Depends(get_pipeline),
) -> CardOut:
    """
    Одна карточка → список извлечённых атрибутов.
    """
    return _run(card, pipeline=pipeline)


@router.post("/batch", response_model=BatchOut)
async def extract_batch(
    file: UploadFile = File(...),
    pipeline: CascadedExtractionPipeline = Depends(get_pipeline),
) -> BatchOut:
    """
    Файл CSV или JSON → список карточек с извлечёнными атрибутами (неблокирующий тредпул).
    """
    raw_bytes = await file.read()
    rows = _rows_from_file(file.filename or "", raw_bytes)
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
def get_review_queue(limit: int = 50) -> ReviewQueueResponse:
    """
    Возвращает список карточек из очереди ручной модерации (Human-in-the-Loop),
    помеченных флагом needs_review=True или имеющих пропущенные обязательные атрибуты.
    """
    base_dir = get_repo_root()
    preds_path = base_dir / "output" / "predictions.json"

    if not preds_path.exists():
        return ReviewQueueResponse(total_in_queue=0, items=[])

    try:
        with open(preds_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items", []) if isinstance(data, dict) else data
    except Exception as e:
        raise HTTPException(500, f"Ошибка чтения очереди модерации: {e}")

    flagged = [it for it in items if it.get("needs_review") is True]
    return ReviewQueueResponse(
        total_in_queue=len(flagged),
        items=flagged[:limit],
    )


@router.post("/review-override")
def submit_review_override(body: ReviewOverrideIn) -> dict:
    """
    Применяет ручное решение модератора (Human-in-the-Loop):
    утверждает карточку, переопределяет ошибочный атрибут или отклоняет сомнительное значение.
    Результат записывается в output/reviewed_predictions.json с потокобезопасной блокировкой.
    """
    from datetime import datetime

    base_dir = get_repo_root()
    reviewed_path = base_dir / "output" / "reviewed_predictions.json"
    lock_file = str(reviewed_path)

    with process_file_lock(lock_file):
        reviewed_store: dict = {"metadata": {"last_updated": datetime.now().isoformat()}, "overrides": {}}
        if reviewed_path.exists():
            try:
                with open(reviewed_path, "r", encoding="utf-8") as f:
                    reviewed_store = json.load(f)
            except Exception as e:
                logger.warning("Failed to load existing reviewed predictions from %s: %s", reviewed_path, e)

        if "overrides" not in reviewed_store:
            reviewed_store["overrides"] = {}

        entry = {
            "external_id": body.external_id,
            "attribute": body.attribute,
            "override_value": body.override_value,
            "action": body.action,
            "reviewed_by": body.reviewed_by,
            "timestamp": datetime.now().isoformat(),
        }
        key = f"{body.external_id}:{body.attribute}"
        reviewed_store["overrides"][key] = entry
        reviewed_store["metadata"]["last_updated"] = datetime.now().isoformat()
        reviewed_store["metadata"]["total_overrides"] = len(reviewed_store["overrides"])

        if body.attribute == "brand" and body.action in ("approve", "override") and body.override_value:
            try:
                BrandRegistry.get_instance().register_brand(
                    alias=body.override_value.strip().lower(),
                    canonical=body.override_value.strip(),
                    persist=True,
                )
                logger.info("Feedback loop: registered verified brand '%s' from human review", body.override_value)
            except Exception as e:
                logger.warning("Feedback loop brand registration error: %s", e)

        reviewed_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = reviewed_path.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(reviewed_store, f, ensure_ascii=False, indent=2)
        tmp_file.replace(reviewed_path)

    return {
        "status": "success",
        "action_recorded": entry,
        "feedback_applied": body.attribute == "brand",
        "total_overrides": len(reviewed_store["overrides"]),
    }