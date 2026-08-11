"""Delegate adapter for the frozen Gemma provider configuration."""

from __future__ import annotations

from typing import Any, Callable


class GemmaAdapter:
    def __init__(self, provider: Callable[..., Any], configuration: dict[str, Any], on_call: Callable[[str], None] | None = None) -> None:
        self._provider = provider
        self.configuration = dict(configuration)
        self._on_call = on_call

    def call(self, prompt: Any, **kwargs: Any) -> Any:
        if self._on_call:
            self._on_call("gemma")
        return self._provider(prompt, configuration=self.configuration, **kwargs)
