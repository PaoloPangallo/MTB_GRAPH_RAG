"""Adapter for the frozen deterministic SourceUnit selector."""

from __future__ import annotations

from typing import Any, Callable, Sequence


class SelectorAdapter:
    def __init__(self, delegate: Callable[..., Any], k: int) -> None:
        self._delegate = delegate
        self.k = k

    def select(self, source_units: Sequence[dict[str, Any]], *, top_k: int | None = None, **kwargs: Any) -> Any:
        """Invoke the reviewed runtime seam with an explicit deterministic K."""
        return self._delegate(source_units, top_k=self.k if top_k is None else top_k, **kwargs)
