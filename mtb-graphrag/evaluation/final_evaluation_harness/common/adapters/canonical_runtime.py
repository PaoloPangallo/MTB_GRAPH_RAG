"""Adapter for the canonical EvidenceRetrievalPipeline public entry point."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RuntimeBinding:
    module: str = "backend.pipeline.evidence.retrieval.pipeline"
    entry_point: str = "EvidenceRetrievalPipeline.run"
    input_contract: str = "query plus retrieval_backend/configuration"
    output_contract: str = "RetrievalOutcome.to_dict()"


class CanonicalRuntimeAdapter:
    """Thin adapter; the delegate owns all runtime semantics."""

    binding = RuntimeBinding()

    def __init__(self, delegate: Callable[..., Any]) -> None:
        self._delegate = delegate

    @classmethod
    def from_runtime(cls, pipeline: Any) -> "CanonicalRuntimeAdapter":
        return cls(pipeline.run)

    def execute(self, query: Any, **kwargs: Any) -> Any:
        return self._delegate(query, **kwargs)
