from __future__ import annotations

from copy import deepcopy
from typing import Any


def _module(
    module_name: str,
    module_version: str,
    maturity: str,
    execution_mode: str,
    status: str,
    data_scope: str,
    limitations: list[str],
    *,
    available: bool | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "module_name": module_name,
        "module_version": module_version,
        "maturity": maturity,
        "execution_mode": execution_mode,
        "status": status,
        "data_scope": data_scope,
        "limitations": list(limitations),
    }
    if available is not None:
        value["available"] = available
    return value


def build_module_status() -> dict[str, dict[str, Any]]:
    """Return the explicit maturity/execution contract for every module."""

    return deepcopy(
        {
            "v3_core": _module(
                "V3 core",
                "v3-core/1.0",
                "PRODUCTION",
                "ACTIVE",
                "EXECUTED",
                "frozen deterministic V3 result supplied to the adapter",
                ["The shadow contract does not invoke or recalculate the runtime."],
            ),
            "provenance_audit": _module(
                "Provenance audit",
                "qualified-claim-provenance/1.4",
                "FROZEN_EXPERIMENT",
                "OFFLINE",
                "PARTIALLY_AVAILABLE",
                "local qualified claim and parent records",
                ["Parent publication availability is not claim-level verification."],
            ),
            "document_support": _module(
                "Document support pilot",
                "pmid-pilot/1.0",
                "FROZEN_EXPERIMENT",
                "OFFLINE",
                "PARTIALLY_AVAILABLE",
                "local PMID pilot alignments when present",
                ["Unexecuted analysis is reported as NOT_ASSESSED."],
            ),
            "ontology": _module(
                "Ontology alignment MVP",
                "ontology-shadow-mvp/1.0",
                "RESEARCH_DRAFT",
                "SHADOW",
                "SHADOW",
                "local normalization and ontology registry",
                ["Matches are evidence only and cannot alter V3 compatibility."],
            ),
            "companion_diagnostic": _module(
                "Companion diagnostic context",
                "companion-diagnostic/0.1",
                "DISCOVERY_ONLY",
                "OFFLINE",
                "STRUCTURAL_DATA_ONLY",
                "graph diagnostic records without qualified claim promotion",
                ["Disease context, provenance, and regulatory status may be unavailable."],
            ),
            "escat": _module(
                "ESCAT clinical actionability",
                "escat-shadow/1.0",
                "RESEARCH_DRAFT",
                "SHADOW",
                "NOT_ASSESSED",
                "existing EscatAssessmentRecord values only",
                ["Ruleset is not clinically validated and no tier is assigned automatically."],
                available=False,
            ),
        }
    )
