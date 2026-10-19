from __future__ import annotations

from pydantic import BaseModel, Field


class CardIn(BaseModel):
    external_id: str | None = None
    category: str | None = None
    title: str = ""
    description: str = ""
    raw_text: str | None = None
    seller_attributes: dict = Field(default_factory=dict)


class PredictionOut(BaseModel):
    attribute: str
    value: str
    confidence: float
    source: str
    raw: str | None = None
    grounded: bool | None = None


class CardOut(BaseModel):
    external_id: str | None
    category: str | None
    predictions: list[PredictionOut]
    missing: list[str]
    overall_confidence: float = 0.0
    needs_review: bool = False
    warnings: list[str] = Field(default_factory=list)
    degraded_tiers: list[str] = Field(default_factory=list)


class BatchOut(BaseModel):
    total: int
    cards: list[CardOut]


class ReviewOverrideIn(BaseModel):
    external_id: str
    attribute: str
    override_value: str
    action: str = "override"  # override | approve | reject
    reviewed_by: str = "operator"


class ReviewQueueResponse(BaseModel):
    total_in_queue: int
    items: list[dict]
