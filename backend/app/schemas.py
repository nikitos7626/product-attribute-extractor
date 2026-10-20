from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CardIn(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, extra="ignore")

    external_id: str | None = None
    category: str | None = None
    title: str = ""
    description: str = ""
    raw_text: str | None = None
    seller_attributes: dict = Field(default_factory=dict)

    @field_validator("title", "description", mode="before")
    @classmethod
    def default_string(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("seller_attributes", mode="before")
    @classmethod
    def default_seller_attributes(cls, v: Any) -> dict:
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        return {}


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
