"""Scoring deterministico e decomponibile del retriever qualificato."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .qualified_retrieval_errors import ScoringConfigurationMismatchError


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("hash", None)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    contribution: float
    category: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "contribution": self.contribution,
            "category": self.category,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RetrievalScoreBreakdown:
    components: tuple[ScoreComponent, ...]

    @property
    def total(self) -> float:
        return sum(item.contribution for item in self.components)

    @property
    def native_total(self) -> float:
        return sum(
            item.contribution for item in self.components if item.category == "native"
        )

    @property
    def qualified_total(self) -> float:
        return self.total - self.native_total

    def as_list(self) -> list[dict[str, Any]]:
        return [item.as_dict() for item in self.components]


@dataclass(frozen=True)
class ScoringConfig:
    version: str
    weights: Mapping[str, float]
    thresholds: Mapping[str, float]
    tie_break_rules: tuple[str, ...]
    hash: str
    payload: Mapping[str, Any]

    @classmethod
    def load(cls, path: str | Path) -> "ScoringConfig":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        actual = _canonical_hash(payload)
        declared = str(payload.get("hash") or "")
        if declared != actual:
            raise ScoringConfigurationMismatchError(
                f"hash scoring dichiarato {declared!r}, calcolato {actual!r}"
            )
        return cls(
            version=str(payload["version"]),
            weights={key: float(value) for key, value in payload["weights"].items()},
            thresholds={
                key: float(value) for key, value in payload["thresholds"].items()
            },
            tie_break_rules=tuple(payload["tie_break_rules"]),
            hash=actual,
            payload=payload,
        )


def component(
    config: ScoringConfig, name: str, *, category: str, reason: str, enabled: bool = True
) -> ScoreComponent:
    return ScoreComponent(
        name=name,
        contribution=config.weights[name] if enabled else 0.0,
        category=category,
        reason=reason,
    )


__all__ = [
    "ScoreComponent",
    "RetrievalScoreBreakdown",
    "ScoringConfig",
    "component",
]
