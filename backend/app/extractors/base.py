from __future__ import annotations

from typing import Any, Protocol, TypedDict, runtime_checkable

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired


class Prediction(TypedDict):
    attribute: str
    value: str
    confidence: float
    source: str
    raw: NotRequired[str]
    grounded: NotRequired[bool]


@runtime_checkable
class BaseExtractor(Protocol):
    name: str
    version: str

    def health(self) -> bool: ...
    def extract(self, card: dict[str, Any], **kwargs: Any) -> list[Prediction]: ...
    def get_info(self) -> dict[str, Any]: ...


@runtime_checkable
class KnowledgeBaseInterface(Protocol):
    version: str

    def get(self, key: str) -> dict[str, Any] | None: ...
    def size(self) -> int: ...
    def reload(self) -> bool: ...


@runtime_checkable
class LlmFallbackInterface(Protocol):
    name: str
    version: str

    def health(self) -> bool: ...
    def get_info(self) -> dict[str, Any]: ...
    def enrich_missing_attributes(
        self,
        brand: str,
        model: str,
        missing_attrs: set[str],
        category_key: str,
        raw_text: str = "",
    ) -> list[Prediction]: ...