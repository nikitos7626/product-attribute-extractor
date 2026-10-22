from __future__ import annotations



from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator





class CardIn(BaseModel):

    model_config = ConfigDict(coerce_numbers_to_str=True, extra="ignore")



    external_id: str | None = None

    model_id: str | None = None

    category: str | None = None

    title: str = ""

    description: str = ""

    raw_text: str | None = None

    seller_attributes: dict = Field(default_factory=dict)



    @model_validator(mode="before")

    @classmethod

    def normalize_input_aliases(cls, data: Any) -> Any:

        if isinstance(data, dict):

            # 1. Алиасы model_id и external_id

            m_id = data.get("model_id")

            if m_id is not None and str(m_id).strip() != "":

                data["model_id"] = str(m_id).strip()



            ext_id = data.get("external_id")

            if ext_id is not None and str(ext_id).strip() != "":

                data["external_id"] = str(ext_id)

            else:

                for alt_key in ("id", "sku_id", "sku", "item_id", "product_id", "model_id"):

                    if alt_key in data and data[alt_key] is not None and str(data[alt_key]).strip() != "":

                        data["external_id"] = str(data[alt_key])

                        break

            # 2. Алиасы seller_attributes

            seller_attrs = data.get("seller_attributes")

            if not isinstance(seller_attrs, dict):

                seller_attrs = {}

            else:

                seller_attrs = dict(seller_attrs)

            for vendor_key in ("vendor", "brand", "seller", "manufacturer"):

                if vendor_key in data and data[vendor_key] and vendor_key not in seller_attrs:

                    seller_attrs[vendor_key] = str(data[vendor_key])

            data["seller_attributes"] = seller_attrs

        return data



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

    tier: str | None = None

    raw: str | None = None

    grounded: bool | None = None

    consensus: bool | None = None

    consensus_sources: list[str] | None = None

    confidence_reason: str | None = None

    status: str = "valid"





class CardOut(BaseModel):

    external_id: str | None = None

    category: str | None = None

    category_key: str | None = None

    subcategory: str | None = None

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

    processed: int = 0

    approved_count: int = 0

    needs_review_count: int = 0

    failed_count: int = 0

    overall_status: str = "approved"  # approved | needs_review | partial_failure | failed

    cards: list[CardOut]





class ReviewOverrideIn(BaseModel):
    external_id: str
    attribute: str | None = None
    override_value: str | None = None
    attributes: dict[str, Any] | None = None
    action: str = "override"  # override | approve | reject
    reviewed_by: str = "operator" 





class ReviewQueueResponse(BaseModel):

    total_in_queue: int

    items: list[dict]





class UrlExtractIn(BaseModel):
    url: str
    category: str | None = None
    title: str | None = None


class UrlExtractOut(BaseModel):
    status: str = "success"
    url: str
    page_title: str
    extracted_text_snippet: str
    card_result: CardOut

class ReviewQueueClearResponse(BaseModel):

    status: str = 'success'

    message: str = 'Очередь модерации успешно очищена'

    cleared_count: int = 0

    remaining_in_queue: int = 0



class ModelRegisterIn(BaseModel):

    model_config = ConfigDict(coerce_numbers_to_str=True)



    brand: str

    model: str

    specs: dict[str, Any]

    model_id: str | None = None

