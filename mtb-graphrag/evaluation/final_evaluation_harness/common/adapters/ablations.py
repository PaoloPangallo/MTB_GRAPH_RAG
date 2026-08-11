"""Harness-side wiring for the four frozen ablations."""

from __future__ import annotations

from typing import Any, Callable


def pre_retrieval_authority_bypass(parser_output: Any, retrieval: Callable[[Any], Any]) -> Any:
    """Pass parser output directly to existing retrieval (stages 3 and 3b skipped)."""
    return retrieval(parser_output)


def selector_replacement(source_units: Any, strategy: Callable[..., Any], k: int) -> Any:
    return strategy(source_units, k=k)


def quote_validator_bypass(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("transport") != "VALID" or result.get("schema") != "VALID":
        return result
    if result.get("decision") == "QUOTE":
        return {**result, "semantic_validation": "IDENTITY_ACCEPTED"}
    return result


def narrative_verifier_bypass(narrative: dict[str, Any]) -> dict[str, Any]:
    if narrative.get("transport") != "VALID":
        return narrative
    return {**narrative, "presentation": "PRESENTED_IN_OFFLINE_ABLATION"}
