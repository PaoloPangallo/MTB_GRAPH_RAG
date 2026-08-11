"""Transparent timing adapter for the existing document resolver."""

from __future__ import annotations

from time import monotonic
from typing import Any, Callable


class DocumentResolverAdapter:
    def __init__(self, resolver: Callable[..., Any], network_guard: Any | None = None) -> None:
        self._resolver = resolver
        self._network_guard = network_guard

    def resolve(self, *args: Any, **kwargs: Any) -> tuple[Any, float]:
        start = monotonic()
        if self._network_guard is not None:
            assert_allowed = getattr(self._network_guard, "assert_allowed", None)
            if callable(assert_allowed):
                assert_allowed("CANONICAL_RUNTIME_POLICY")
            self._network_guard.record()
        result = self._resolver(*args, **kwargs)
        return result, (monotonic() - start) * 1000.0
