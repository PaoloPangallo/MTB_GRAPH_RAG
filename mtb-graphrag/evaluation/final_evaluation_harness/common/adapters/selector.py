"""Adapter for the frozen deterministic SourceUnit selector."""

from __future__ import annotations

from typing import Any, Callable, Sequence


class SelectorAdapter:
    def __init__(self, delegate: Callable[..., Any], k: int) -> None:
        self._delegate = delegate
        self.k = k

    def select(self, source_units: Sequence[dict[str, Any]], **kwargs: Any) -> Any:
        return self._delegate(source_units, k=self.k, **kwargs)
