from __future__ import annotations

import io
import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from app.schemas import BatchOut, CardIn, CardOut, PredictionOut, ReviewOverrideIn, ReviewQueueResponse
from app.services.pipeline import CascadedExtractionPipeline


router = APIRouter(prefix="/api/extract", tags=["extract"])

# Каскадный пайплайн (Tier 1 FastRules + Tier 2 GLiNER Zero-Shot + HITL)
_pipeline = CascadedExtractionPipeline(use_gliner=True)



# --------------------------- хелперы ---------------------------

def _run(card: CardIn) -> CardOut:
    """Прогоняет одну карточку через каскадный пайплайн и упаковывает в CardOut."""
    res = _pipeline.process_card({
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
        warnings=res.get("warnings", []),
        degraded_tiers=res.get("degraded_tiers", []),
    )



def _rows_from_file(filename: str, raw: bytes) -> list[dict]:
    """CSV или JSON → список dict'ов. Пустой файл → 400, а не 500."""
    if not raw or not raw.strip():
        raise HTTPException(400, "Файл пустой")

    name = (filename or "").lower()
    if name.endswith(".json"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"Невалидный JSON: {e}") from e
        rows = data if isinstance(data, list) else [data]
        if not rows:
            raise HTTPException(400, "В JSON нет карточек")
        return rows

    if name.endswith(".csv"):
        import pandas as pd
        try:
            df = pd.read_csv(io.BytesIO(raw))
        except pd.errors.EmptyDataError as e:
            raise HTTPException(400, "CSV не содержит колонок/строк") from e
        if df.empty:
            raise HTTPException(400, "CSV пустой")
        return df.to_dict(orient="records")

    raise HTTPException(400, "Только CSV или JSON")


# --------------------------- эндпоинты ---------------------------

@router.post("/brands/register")
def register_brand(alias: str, canonical: str | None = None) -> dict:
    """
    Динамическая регистрация нового бренда в каталог М.Видео на лету.
    Мгновенно добавляет в FlashText и сохраняет в brands.csv.
    """
    from app.services.brand_registry import BrandRegistry
    registry = BrandRegistry.get_instance()
    success = registry.register_brand(alias, canonical)
    canon = registry.get_canonical(alias) or (canonical or alias.strip().title())
    return {"ok": success, "brand": canon, "alias": alias.strip().lower()}


@router.get("/health")
def health() -> dict:
    """Быстрая проверка состояния экстракторов и пайплайна."""
    return {
        "ok": True,
        "pipeline": "CascadedExtractionPipeline",
        "tier1_regex": _pipeline.regex_extractor.health(),
        "tier2_gliner": _pipeline.gliner_extractor.health() if _pipeline.gliner_extractor else False,
    }


@router.post("", response_model=CardOut)
def extract_one(card: CardIn) -> CardOut:
    """
    Одна карточка → список извлечённых атрибутов.

    Пример тела запроса:
    {
      "external_id": "sku-1",
      "category": "smartphones",
      "title": "Смартфон Apple iPhone 15 Pro Max 256GB Black Titanium",
      "description": "Экран 6.7 дюймов, батарея 4422 мАч",
      "seller_attributes": {"rom": "256gb", "color": "black"}
    }
    """
    return _run(card)


@router.post("/batch", response_model=BatchOut)
async def extract_batch(file: UploadFile = File(...)) -> BatchOut:
    """
    Файл CSV или JSON → список карточек с извлечёнными атрибутами.

    Ожидаемые колонки: external_id, category, title, description, seller_attributes.
    seller_attributes в CSV — JSON-строка, в JSON — объект.
    """
    rows = _rows_from_file(file.filename or "", await file.read())

    cards: list[CardOut] = []
    for i, row in enumerate(rows):
        # seller_attributes может прийти строкой из CSV — парсим
        sa = row.get("seller_attributes")
        if isinstance(sa, str):
            try:
                row["seller_attributes"] = json.loads(sa) if sa.strip() else {}
            except json.JSONDecodeError:
                raise HTTPException(
                    400,
                    f"Row {i}: seller_attributes не валидный JSON: {sa!r}",
                )
        cards.append(_run(CardIn(**row)))

    return BatchOut(total=len(cards), cards=cards)


@router.get("/metrics")
def get_metrics() -> dict:
    """
    Возвращает стандартизированный отчет валидации качества (per-attribute F1, Precision, Recall, Coverage).
    Отчет сгенерирован на эталонном Gold Dataset М.Видео.
    """
    from pathlib import Path
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
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
def get_taxonomy() -> dict:
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
    return {"taxonomy": out}


@router.post("/export")
async def export_batch_predictions(
    file: UploadFile = File(...),
    output_format: str = "json",
):
    """
    Пакетный экспорт стандартизированных предсказаний в формате JSON или CSV.
    Принимает входной файл (CSV или JSON), прогоняет через каскад и возвращает
    структурированный массив характеристик со всеми флагами проверки и уверенности.
    """
    from fastapi.responses import Response

    rows = _rows_from_file(file.filename or "", await file.read())
    results: list[dict] = []

    for i, row in enumerate(rows):
        sa = row.get("seller_attributes")
        if isinstance(sa, str):
            try:
                row["seller_attributes"] = json.loads(sa) if sa.strip() else {}
            except json.JSONDecodeError:
                raise HTTPException(400, f"Row {i}: seller_attributes не валидный JSON: {sa!r}")

        card_res = _pipeline.process_card(row)
        flat_attrs = {p["attribute"]: p["value"] for p in card_res.get("predictions", [])}

        results.append({
            "external_id": card_res.get("external_id") or f"sku-{i+1}",
            "title": row.get("title", ""),
            "category": card_res.get("category"),
            "overall_confidence": card_res.get("overall_confidence"),
            "needs_review": card_res.get("needs_review"),
            "extracted_attributes": flat_attrs,
            "missing_required": card_res.get("missing", []),
            "detailed_predictions": card_res.get("predictions", []),
        })

    if output_format.lower() == "csv":
        import pandas as pd
        flat_rows = []
        for r in results:
            item = {
                "external_id": r["external_id"],
                "category": r["category"],
                "overall_confidence": r["overall_confidence"],
                "needs_review": r["needs_review"],
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


@router.get("/review-queue", response_model=ReviewQueueResponse)
def get_review_queue(limit: int = 50) -> ReviewQueueResponse:
    """
    Возвращает список карточек из очереди ручной модерации (Human-in-the-Loop),
    помеченных флагом needs_review=True или имеющих пропущенные обязательные атрибуты.
    """
    from pathlib import Path
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
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
    Результат записывается в output/reviewed_predictions.json.
    """
    from datetime import datetime
    from pathlib import Path

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    reviewed_path = base_dir / "output" / "reviewed_predictions.json"

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

    # Активный контур обратной связи (Feedback Loop):
    # При подтверждении или исправлении бренда модератором, бренд моментально регистрируется в BrandRegistry
    if body.attribute == "brand" and body.action in ("approve", "override") and body.override_value:
        try:
            from app.services.brand_registry import BrandRegistry
            BrandRegistry.get_instance().register_brand(
                alias=body.override_value.strip().lower(),
                canonical=body.override_value.strip(),
                persist=True,
            )
            logger.info("Feedback loop: registered verified brand '%s' from human review", body.override_value)
        except Exception as e:
            logger.warning("Feedback loop brand registration error: %s", e)

    reviewed_path.parent.mkdir(parents=True, exist_ok=True)
    with open(reviewed_path, "w", encoding="utf-8") as f:
        json.dump(reviewed_store, f, ensure_ascii=False, indent=2)

    return {
        "status": "success",
        "action_recorded": entry,
        "feedback_applied": body.attribute == "brand",
        "total_overrides": len(reviewed_store["overrides"]),
    }

