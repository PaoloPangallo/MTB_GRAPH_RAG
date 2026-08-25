"""Canonical relation-observation prompt for the paper Reader."""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "paper-context-enricher-prompt/3.0"
TRANSPORT_VERSION = "paper-context-enrichment-transport/3.0"
TOOL_NAME = "submit_paper_relation_observation"

DIRECTIONS = (
    "SUPPORTS", "DOES_NOT_SUPPORT", "SENSITIVITY_RESPONSE", "RESISTANCE",
    "REDUCED_SENSITIVITY", "ADVERSE_RESPONSE", "UNKNOWN", "NOT_APPLICABLE",
)
EVIDENCE_TYPES = (
    "PREDICTIVE", "DIAGNOSTIC", "PROGNOSTIC", "PREDISPOSING", "FUNCTIONAL",
    "ONCOGENIC", "UNKNOWN", "NOT_APPLICABLE",
)
_FIELDS = (
    "decision", "source_unit_id", "quote", "observed_disease", "observed_gene",
    "observed_alteration", "observed_drug", "observed_direction",
    "observed_evidence_type", "notes", "abstain_reason",
)
TOOL_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": list(_FIELDS),
    "properties": {
        **{name: {"type": "string"} for name in _FIELDS},
        "decision": {"type": "string", "enum": ["QUOTE", "ABSTAIN"]},
        "observed_direction": {"type": "string", "enum": list(DIRECTIONS)},
        "observed_evidence_type": {"type": "string", "enum": list(EVIDENCE_TYPES)},
    },
}
TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "Report a literal paper passage and only the relation fields observed in it.",
        "parameters": TOOL_SCHEMA,
    },
}

SYSTEM_PROMPT = """You read biomedical SOURCE UNITS and report only what they state.
Use no external knowledge. Never recommend therapy, decide eligibility, assign FULL/PARTIAL support,
or invent a source. Choose QUOTE only for one exact contiguous substring of one supplied SourceUnit;
otherwise choose ABSTAIN. Gene support is not variant support: a generic mutation statement does not
confirm a specific variant. Absence of a variant is not DOES_NOT_SUPPORT. A trial mention is not
efficacy evidence. Do not complete missing entities. Return exactly one tool call."""


def render_request(case_context: dict[str, Any], candidate: dict[str, Any], paper_id: str,
                   source_units: list[dict[str, Any]]) -> str:
    header = {
        "case_context": case_context,
        "candidate": candidate,
        "paper_id": paper_id,
        "instruction": "Describe observed fields; empty string means not observed.",
    }
    units = [
        {"source_unit_id": unit.get("source_unit_id"), "document_id": unit.get("document_id"),
         "unit_type": unit.get("unit_type"), "locator": unit.get("section"), "text": unit.get("text", "")}
        for unit in source_units
    ]
    return json.dumps({**header, "source_units": units}, ensure_ascii=False, sort_keys=True)
