from __future__ import annotations

import pytest

from backend.research_pipeline.orchestrator import _accepted_for_gates


@pytest.mark.parametrize("result", [
    "PARTIAL_SUPPORT",
    "CONTEXT_ONLY",
    "CONTRADICTORY",
    "UNVERIFIABLE",
])
def test_validated_quote_requires_strong_candidate_support(result: str) -> None:
    assert _accepted_for_gates(
        "ENRICHMENT_V2_ACCEPTED",
        {"result": result},
    ) is None


def test_strong_candidate_support_reaches_exact_support_gate() -> None:
    assert _accepted_for_gates(
        "ENRICHMENT_V2_ACCEPTED",
        {"result": "STRONG_SUPPORT"},
    ) == "ENRICHMENT_ACCEPTED"


def test_rejected_quote_cannot_be_saved_by_strong_support() -> None:
    assert _accepted_for_gates(
        "REJECTED_QUOTE_NOT_FOUND",
        {"result": "STRONG_SUPPORT"},
    ) is None


def test_strong_support_is_preserved_as_validation_metadata() -> None:
    support = {"result": "STRONG_SUPPORT", "fields": {"direction": "CONFIRMED"}}
    assert support["result"] == "STRONG_SUPPORT"
    assert _accepted_for_gates("ENRICHMENT_V2_ACCEPTED", support) == "ENRICHMENT_ACCEPTED"
