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
    consensus: bool | None = None
    consensus_sources: list[str] | None = None
    confidence_reason: str | None = None
    status: str = "valid"


class CardOut(BaseModel):
    external_id: str | None = None
    category: str | None = None
    predictions: list[PredictionOut]
    missing: list[str]
    overall_confidence: float = 0.0
    needs_review: bool = False
    status: str = "approved"
    status_description: str = ""
    review_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    degraded_tiers: list[str] = Field(default_factory=list)
    taxonomy_status: str | None = None


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
