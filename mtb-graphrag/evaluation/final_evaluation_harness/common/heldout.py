"""Inference/evaluation separation for held-out cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InferenceCase:
    case_id: str
    case_payload: dict[str, Any]


def load_case_only(case: dict[str, Any]) -> InferenceCase:
    if "gold" in case or "expected" in case:
        raise ValueError("gold is inaccessible during held-out inference")
    return InferenceCase(case["case_id"], dict(case))


def join_gold_after_inference(raw: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    return {"raw": raw, "gold": gold}
