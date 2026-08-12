"""Delegate adapter for the frozen Gemma provider configuration."""

from __future__ import annotations

from typing import Any, Callable


class GemmaAdapter:
    def __init__(self, provider: Callable[..., Any], configuration: dict[str, Any], on_call: Callable[[str], None] | None = None, model_guard: Any | None = None) -> None:
        self._provider = provider
        self.configuration = dict(configuration)
        self._on_call = on_call
        self._model_guard = model_guard

    def call(self, *args: Any, **kwargs: Any) -> Any:
        if self._model_guard is not None:
            assert_allowed = getattr(self._model_guard, "assert_allowed", None)
            if callable(assert_allowed):
                try:
                    assert_allowed("REQUIRED", role="gemma")
                except TypeError:
                    assert_allowed("REQUIRED")
        if self._on_call:
            self._on_call("gemma")
        return self._provider(*args, configuration=self.configuration, **kwargs)
