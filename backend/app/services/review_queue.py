"""
E-Commerce AI — Сервис очереди ручной модерации Human-in-the-Loop (ReviewQueueService).
Обеспечивает централизованное управление карточками, требующими проверки оператором:
1. Автоматическое добавление сомнительных карточек из одиночного (single) и пакетного (batch) извлечения.
2. Синхронизация с файловым хранилищем (output/predictions.json) с межпроцессной блокировкой.
3. Поддержка операторских действий: одобрение, отклонение, редактирование атрибутов.
4. Обратная связь (Feedback Loop) в реестр брендов и базу знаний характеристик (Catalog KB).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from app.services.brand_registry import BrandRegistry, process_file_lock

logger = logging.getLogger(__name__)


def get_repo_root() -> Path:
    """Динамический поиск корня репозитория по маркерам .git / data / output."""
    current = Path(__file__).resolve().parent
    for p in [current] + list(current.parents):
        if (p / ".git").exists() or ((p / "data").is_dir() and (p / "output").is_dir()):
            return p
    return Path(__file__).resolve().parent.parent.parent.parent


def is_needs_review(it: dict[str, Any]) -> bool:
    """Проверяет флаг ручной модерации с поддержкой bool, str и int форматов."""
    val = it.get("needs_review")
    if val is True:
        return True
    if isinstance(val, str) and val.strip().lower() in ("true", "yes", "1"):
        return True
    if isinstance(val, (int, float)) and val == 1:
        return True
    return False


class ReviewQueueService:
    """
    Потокобезопасный и межпроцессный сервис управления очередью ручной модерации (HITL).
    """

    _instance: ReviewQueueService | None = None
    _singleton_lock = threading.Lock()

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or get_repo_root()
        self.output_dir = self.base_dir / "output"
        self.queue_path = self.output_dir / "review_queue.json"
        self.preds_path = self.output_dir / "predictions.json"
        self.reviewed_path = self.output_dir / "reviewed_predictions.json"
        self.csv_path = self.output_dir / "predictions.csv"
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls, base_dir: Path | None = None) -> ReviewQueueService:
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls(base_dir=base_dir)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Сброс экземпляра синглтона (используется в тестах и при перезапуске)."""
        with cls._singleton_lock:
            cls._instance = None

    def _ensure_output_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _extract_item_dict(self, card: Any, result: Any) -> dict[str, Any]:
        """Формирует нормализованный словарь карточки для очереди модерации."""
        # 1. Извлечение полей входной карточки
        if hasattr(card, "model_dump"):
            card_dict = card.model_dump()
        elif hasattr(card, "dict"):
            card_dict = card.dict()
        elif isinstance(card, dict):
            card_dict = card
        else:
            card_dict = {}

        # 2. Извлечение полей результата
        if hasattr(result, "model_dump"):
            res_dict = result.model_dump()
        elif hasattr(result, "dict"):
            res_dict = result.dict()
        elif isinstance(result, dict):
            res_dict = result
        else:
            res_dict = {}

        raw_text = card_dict.get("raw_text") or card_dict.get("description") or card_dict.get("title") or ""
        title = card_dict.get("title") or ""
        if not title and raw_text:
            title = raw_text.split("\n")[0][:120].strip()

        ext_id = card_dict.get("external_id") or res_dict.get("external_id")
        if not ext_id:
            raw_key = raw_text or title or str(uuid.uuid4())
            ext_id = f"card-{hashlib.md5(raw_key.encode('utf-8')).hexdigest()[:8]}"
            if hasattr(card, "external_id") and not getattr(card, "external_id", None):
                card.external_id = ext_id
            if hasattr(result, "external_id") and not getattr(result, "external_id", None):
                result.external_id = ext_id

        preds = res_dict.get("predictions") or []
        detailed_preds = []
        flat_attrs: dict[str, Any] = {}
        for p in preds:
            if hasattr(p, "model_dump"):
                p_dict = p.model_dump()
            elif isinstance(p, dict):
                p_dict = p
            else:
                continue
            detailed_preds.append(p_dict)
            attr_name = p_dict.get("attribute")
            if attr_name and "value" in p_dict:
                flat_attrs[attr_name] = p_dict["value"]

        category = res_dict.get("category") or card_dict.get("category") or "Электроника"
        overall_conf = float(res_dict.get("overall_confidence", 0.0))
        status = res_dict.get("status", "needs_review")
        status_desc = res_dict.get("status_description", "")
        review_reasons = list(res_dict.get("review_reasons", []))
        warnings = list(res_dict.get("warnings", []))
        degraded = list(res_dict.get("degraded_tiers", []))
        missing = list(res_dict.get("missing", []))

        return {
            "external_id": str(ext_id),
            "title": title or "Товар",
            "category": category,
            "raw_text": raw_text,
            "description": card_dict.get("description", ""),
            "overall_confidence": round(overall_conf, 4),
            "needs_review": True,
            "status": status if status != "approved" else "needs_review",
            "status_description": status_desc,
            "review_reasons": review_reasons,
            "warnings": warnings,
            "degraded_tiers": degraded,
            "extracted_attributes": flat_attrs,
            "missing_required": missing,
            "detailed_predictions": detailed_preds,
            "enqueued_at": datetime.datetime.now().isoformat(),
        }

    def enqueue_card(self, card: Any, result: Any) -> dict[str, Any] | None:
        """
        Добавляет одну карточку с флагом needs_review=True в очередь ручной проверки (output/predictions.json).
        Если карточка с таким external_id уже существует, обновляет её на первом месте (top of queue).
        """
        needs_review = (
            getattr(result, "needs_review", None)
            if hasattr(result, "needs_review")
            else (result.get("needs_review") if isinstance(result, dict) else False)
        )
        if not needs_review:
            return None

        item_dict = self._extract_item_dict(card, result)
        self._ensure_output_dir()
        lock_file = str(self.queue_path)

        with self._lock:
            with process_file_lock(lock_file):
                queue_data: dict[str, Any] = {"metadata": {}, "items": []}
                if self.queue_path.exists():
                    try:
                        with open(self.queue_path, "r", encoding="utf-8") as f:
                            loaded = json.load(f)
                            if isinstance(loaded, dict):
                                preds_data = loaded
                            elif isinstance(loaded, list):
                                preds_data = {"metadata": {}, "items": loaded}
                    except Exception as e:
                        logger.warning("Failed to parse existing %s: %s", self.preds_path, e)

                items: list[dict[str, Any]] = preds_data.get("items", [])
                ext_id = item_dict["external_id"]

                # Проверяем наличие карточки с таким же ID
                existing_idx = -1
                for idx, it in enumerate(items):
                    if str(it.get("external_id")) == str(ext_id):
                        existing_idx = idx
                        break

                if existing_idx >= 0:
                    items.pop(existing_idx)
                items.insert(0, item_dict)

                preds_data["items"] = items
                preds_data.setdefault("metadata", {})
                preds_data["metadata"]["last_updated"] = datetime.datetime.now().isoformat()
                preds_data["metadata"]["total_needs_review"] = sum(
                    1 for it in items if it.get("needs_review") is True
                )
                preds_data["metadata"]["total_cards"] = len(items)

                tmp_file = self.queue_path.with_suffix(".tmp")
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(preds_data, f, ensure_ascii=False, indent=2)
                tmp_file.replace(self.queue_path)
                logger.info("Enqueued card '%s' into review queue (total_flagged=%d)", ext_id, preds_data["metadata"]["total_needs_review"])

        return item_dict

    def enqueue_batch(self, items_pairs: list[tuple[Any, Any]]) -> int:
        """
        Пакетное добавление карточек в очередь модерации за один атомарный файловый IO.
        """
        flagged_items = []
        for card, res in items_pairs:
            needs_review = (
                getattr(res, "needs_review", None)
                if hasattr(res, "needs_review")
                else (res.get("needs_review") if isinstance(res, dict) else False)
            )
            if needs_review:
                flagged_items.append(self._extract_item_dict(card, res))

        if not flagged_items:
            return 0

        self._ensure_output_dir()
        lock_file = str(self.queue_path)

        with self._lock:
            with process_file_lock(lock_file):
                queue_data: dict[str, Any] = {"metadata": {}, "items": []}
                if self.queue_path.exists():
                    try:
                        with open(self.queue_path, "r", encoding="utf-8") as f:
                            loaded = json.load(f)
                            if isinstance(loaded, dict):
                                preds_data = loaded
                            elif isinstance(loaded, list):
                                preds_data = {"metadata": {}, "items": loaded}
                    except Exception as e:
                        logger.warning("Failed to parse existing %s: %s", self.preds_path, e)

                items: list[dict[str, Any]] = preds_data.get("items", [])
                existing_map = {str(it.get("external_id")): idx for idx, it in enumerate(items)}

                for new_item in reversed(flagged_items):
                    ext_id = str(new_item["external_id"])
                    if ext_id in existing_map:
                        idx = existing_map[ext_id]
                        items[idx] = new_item
                    else:
                        items.insert(0, new_item)

                preds_data["items"] = items
                preds_data.setdefault("metadata", {})
                preds_data["metadata"]["last_updated"] = datetime.datetime.now().isoformat()
                preds_data["metadata"]["total_needs_review"] = sum(
                    1 for it in items if it.get("needs_review") is True
                )
                preds_data["metadata"]["total_cards"] = len(items)

                tmp_file = self.queue_path.with_suffix(".tmp")
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(preds_data, f, ensure_ascii=False, indent=2)
                tmp_file.replace(self.queue_path)

        return len(flagged_items)

    def get_queue(self, limit: int = 5, offset: int = 0) -> tuple[int, list[dict[str, Any]]]:
        """
        Возвращает количество карточек в очереди ручной модерации и срез элементов.
        """
        if not self.queue_path.exists():
            return 0, []

        try:
            with open(self.queue_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items", []) if isinstance(data, dict) else data
        except Exception as e:
            logger.error("Error reading %s: %s", self.queue_path, e)
            return 0, []

        flagged = [it for it in items if is_needs_review(it)]
        return len(flagged), flagged[offset : offset + limit]

    def clear_queue(self) -> dict[str, Any]:
        """
        Очищает очередь ручной модерации, утверждая оставшиеся сомнительные карточки.
        """
        cleared_count = 0
        lock_file = str(self.queue_path)

        with self._lock:
            with process_file_lock(lock_file):
                if self.queue_path.exists():
                    try:
                        with open(self.queue_path, "r", encoding="utf-8") as f:
                            preds_data = json.load(f)
                        is_dict = isinstance(preds_data, dict)
                        items_list = preds_data.get("items", []) if is_dict else preds_data

                        for it in items_list:
                            if is_needs_review(it):
                                cleared_count += 1
                                it["needs_review"] = False
                                if not it.get("status") or it.get("status") in ("pending", "needs_review"):
                                    it["status"] = "approved_by_operator"

                        if is_dict:
                            preds_data.setdefault("metadata", {})
                            preds_data["metadata"]["total_needs_review"] = 0
                            preds_data["metadata"]["last_updated"] = datetime.datetime.now().isoformat()

                        tmp_preds = self.queue_path.with_suffix(".tmp")
                        with open(tmp_preds, "w", encoding="utf-8") as f:
                            json.dump(preds_data, f, ensure_ascii=False, indent=2)
                        tmp_preds.replace(self.queue_path)
                    except Exception as e:
                        logger.error("Failed to clear review queue in %s: %s", self.queue_path, e)



        return {
            "status": "success",
            "message": "Очередь модерации успешно очищена",
            "cleared_count": cleared_count,
            "remaining_in_queue": 0,
        }

    def submit_override(self, body: Any) -> dict[str, Any]:
        """
        Применяет ручное решение модератора (утверждение, отклонение, оверрайд атрибутов).
        """
        lock_file = str(self.reviewed_path)
        timestamp = datetime.datetime.now().isoformat()

        with self._lock:
            with process_file_lock(lock_file):
                reviewed_store: dict[str, Any] = {
                    "metadata": {"last_updated": timestamp},
                    "overrides": {},
                }
                if self.reviewed_path.exists():
                    try:
                        with open(self.reviewed_path, "r", encoding="utf-8") as f:
                            reviewed_store = json.load(f)
                    except Exception as e:
                        logger.warning("Failed to load %s: %s", self.reviewed_path, e)

                if "overrides" not in reviewed_store:
                    reviewed_store["overrides"] = {}

                # 1. Сохранение оверрайдов
                if getattr(body, "attributes", None):
                    for attr, val in body.attributes.items():
                        key = f"{body.external_id}:{attr}"
                        reviewed_store["overrides"][key] = {
                            "external_id": body.external_id,
                            "attribute": attr,
                            "override_value": str(val),
                            "action": body.action,
                            "reviewed_by": body.reviewed_by,
                            "timestamp": timestamp,
                        }
                        if attr == "brand" and body.action in ("approve", "override") and val:
                            try:
                                BrandRegistry.get_instance().register_brand(
                                    alias=str(val).strip().lower(),
                                    canonical=str(val).strip(),
                                    persist=True,
                                )
                            except Exception as e:
                                logger.warning("Brand feedback loop error: %s", e)
                else:
                    attr_name = getattr(body, "attribute", None) or "all"
                    key = f"{body.external_id}:{attr_name}"
                    reviewed_store["overrides"][key] = {
                        "external_id": body.external_id,
                        "attribute": attr_name,
                        "override_value": getattr(body, "override_value", "") or "",
                        "action": body.action,
                        "reviewed_by": body.reviewed_by,
                        "timestamp": timestamp,
                    }
                    if attr_name == "brand" and body.action in ("approve", "override") and getattr(body, "override_value", None):
                        try:
                            BrandRegistry.get_instance().register_brand(
                                alias=body.override_value.strip().lower(),
                                canonical=body.override_value.strip(),
                                persist=True,
                            )
                        except Exception as e:
                            logger.warning("Brand feedback loop error: %s", e)

                reviewed_store["metadata"]["last_updated"] = timestamp
                reviewed_store["metadata"]["total_overrides"] = len(reviewed_store["overrides"])

                self.output_dir.mkdir(parents=True, exist_ok=True)
                tmp_rev = self.reviewed_path.with_suffix(".tmp")
                with open(tmp_rev, "w", encoding="utf-8") as f:
                    json.dump(reviewed_store, f, ensure_ascii=False, indent=2)
                tmp_rev.replace(self.reviewed_path)

                                # 2. Обновление статуса карточки в review_queue.json
                if self.queue_path.exists():
                    try:
                        with process_file_lock(str(self.queue_path)):
                            with open(self.queue_path, "r", encoding="utf-8") as qf:
                                q_data = json.load(qf)
                        q_items = q_data.get("items", []) if isinstance(q_data, dict) else q_data
                        for it in q_items:
                            if str(it.get("external_id")) == str(body.external_id):
                                it["needs_review"] = False
                                it["status"] = "approved_by_operator" if body.action in ("approve", "override") else "rejected_by_operator"
                                if getattr(body, "attributes", None):
                                    it["extracted_attributes"] = dict(body.attributes)
                                break
                        if isinstance(q_data, dict):
                            q_data.setdefault("metadata", {})
                            q_data["metadata"]["total_needs_review"] = sum(1 for it in q_items if it.get("needs_review") is True)
                            q_data["metadata"]["last_updated"] = timestamp
                        tmp_q = self.queue_path.with_suffix(".tmp")
                        with open(tmp_q, "w", encoding="utf-8") as qf:
                            json.dump(q_data, qf, ensure_ascii=False, indent=2)
                        tmp_q.replace(self.queue_path)
                    except Exception as e:
                        logger.warning("Could not update %s for external_id %s: %s", self.queue_path, body.external_id, e)

                # 2b. Обновление статуса карточки в output/predictions.json
                target_brand = ""
                target_model = ""
                target_title = ""
                if getattr(body, "attributes", None):
                    target_brand = str(body.attributes.get("brand") or "").strip()
                    target_model = str(body.attributes.get("model") or "").strip()

                auto_resolved_ids: list[str] = []

                if self.preds_path.exists():
                    try:
                        with process_file_lock(str(self.preds_path)):
                            with open(self.preds_path, "r", encoding="utf-8") as pf:
                                preds_data = json.load(pf)
                        is_dict = isinstance(preds_data, dict)
                        items_list = preds_data.get("items", []) if is_dict else preds_data

                        for it in items_list:
                            if str(it.get("external_id")) == str(body.external_id):
                                target_title = str(it.get("title") or "")
                                if not target_brand:
                                    target_brand = str(it.get("extracted_attributes", {}).get("brand") or "").strip()
                                if not target_model:
                                    target_model = str(it.get("extracted_attributes", {}).get("model") or "").strip()

                                it["needs_review"] = False
                                if body.action in ("approve", "override"):
                                    it["status"] = "approved_by_operator"
                                    if getattr(body, "attributes", None):
                                        it["extracted_attributes"] = dict(body.attributes)
                                        existing_preds = {
                                            p["attribute"]: p
                                            for p in it.get("detailed_predictions", [])
                                            if "attribute" in p
                                        }
                                        new_preds = []
                                        for a, v in body.attributes.items():
                                            if a in existing_preds:
                                                p = existing_preds[a]
                                                p["value"] = v
                                                p["status"] = "human_verified"
                                                p["confidence"] = 1.0
                                                p["tier"] = "Verified"
                                                new_preds.append(p)
                                            else:
                                                new_preds.append({
                                                    "attribute": a,
                                                    "value": v,
                                                    "confidence": 1.0,
                                                    "source": "operator",
                                                    "tier": "Verified",
                                                    "status": "human_verified",
                                                })
                                        it["detailed_predictions"] = new_preds
                                        it["missing_required"] = [
                                            m
                                            for m in it.get("missing_required", [])
                                            if m not in body.attributes or not body.attributes[m]
                                        ]
                                elif body.action == "reject":
                                    it["status"] = "rejected_by_operator"
                                break

                        # Автоматическая дедупликация идентичных товаров в очереди
                        if body.action in ("approve", "override") and (target_model or target_title):
                            for other_it in items_list:
                                other_id = str(other_it.get("external_id"))
                                if other_id == str(body.external_id) or not other_it.get("needs_review"):
                                    continue

                                other_attrs = other_it.get("extracted_attributes", {})
                                other_brand = str(other_attrs.get("brand") or "").strip().lower()
                                other_model = str(other_attrs.get("model") or "").strip().lower()
                                other_title = str(other_it.get("title") or "").strip().lower()

                                is_dup = False
                                if (
                                    target_brand
                                    and target_model
                                    and other_brand == target_brand.lower()
                                    and other_model == target_model.lower()
                                ):
                                    is_dup = True
                                elif target_title and other_title and other_title == target_title.lower():
                                    is_dup = True

                                if is_dup:
                                    other_it["needs_review"] = False
                                    other_it["status"] = "auto_approved_by_duplicate_consensus"
                                    if getattr(body, "attributes", None):
                                        other_it["extracted_attributes"].update(body.attributes)
                                        other_it["missing_required"] = [
                                            m
                                            for m in other_it.get("missing_required", [])
                                            if m not in body.attributes or not body.attributes[m]
                                        ]
                                    auto_resolved_ids.append(other_id)

                        if is_dict:
                            preds_data.setdefault("metadata", {})
                            preds_data["metadata"]["total_needs_review"] = sum(
                                1 for it in items_list if it.get("needs_review") is True
                            )
                            preds_data["metadata"]["last_updated"] = timestamp

                        tmp_preds = self.preds_path.with_suffix(".tmp")
                        with open(tmp_preds, "w", encoding="utf-8") as pf:
                            json.dump(preds_data, pf, ensure_ascii=False, indent=2)
                        tmp_preds.replace(self.preds_path)
                    except Exception as e:
                        logger.warning("Could not update predictions.json for external_id %s: %s", body.external_id, e)

                if self.csv_path.exists():
                    try:
                        with process_file_lock(str(self.csv_path), timeout=5.0):
                            import pandas as pd
                            df = pd.read_csv(self.csv_path)
                            if "external_id" in df.columns and "needs_review" in df.columns:
                                mask = df["external_id"].astype(str) == str(body.external_id)
                                if mask.any():
                                    df.loc[mask, "needs_review"] = "NO"
                                    if getattr(body, "attributes", None):
                                        for a, v in body.attributes.items():
                                            if a in df.columns:
                                                df.loc[mask, a] = str(v)
                                    tmp_csv = self.csv_path.with_suffix(".tmp")
                                    df.to_csv(tmp_csv, index=False, encoding="utf-8-sig")
                                    tmp_csv.replace(self.csv_path)
                    except Exception as e:
                        logger.warning("Could not sync predictions.csv during override: %s", e)

                # 3. Регистрация в Catalog KB
                if body.action in ("approve", "override") and target_brand and target_model:
                    try:
                        from app.services.catalog_enricher import CatalogEnricher
                        specs = getattr(body, "attributes", None) or {}
                        specs_clean = {
                            k: str(v).strip()
                            for k, v in specs.items()
                            if k not in ("brand", "model") and v
                        }
                        if specs_clean:
                            CatalogEnricher.get_instance().register_model_specs(
                                brand=target_brand,
                                model=target_model,
                                specs=specs_clean,
                                persist=True,
                            )
                    except Exception as e:
                        logger.warning("Catalog KB feedback loop error: %s", e)

        entry = {
            "external_id": body.external_id,
            "attribute": getattr(body, "attribute", None) or "all",
            "override_value": getattr(body, "override_value", None) or (str(body.attributes) if getattr(body, "attributes", None) else ""),
            "action": body.action,
            "reviewed_by": body.reviewed_by,
            "timestamp": timestamp,
        }

        return {
            "status": "success",
            "message": f"Решение модератора для '{body.external_id}' успешно сохранено",
            "action_recorded": entry,
            "auto_resolved_duplicates": auto_resolved_ids,
        }