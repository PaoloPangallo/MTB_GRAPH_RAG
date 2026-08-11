"""Canonical and Protocol-1.2 ablated quote validation delegates."""

from __future__ import annotations

from typing import Any, Callable


class QuoteValidatorAdapter:
    def __init__(self, validator: Callable[[Any], Any] | None, *, identity_semantic: bool = False) -> None:
        self._validator = validator
        self.identity_semantic = identity_semantic

    def validate(self, result: dict[str, Any]) -> Any:
        if result.get("transport") != "VALID" or result.get("schema") != "VALID":
            return result
        if self.identity_semantic:
            return {**result, "semantic_validation": "IDENTITY_ACCEPTED"} if result.get("decision") == "QUOTE" else result
        if self._validator is None:
            raise ValueError("canonical quote validator delegate is required")
        return self._validator(result)
