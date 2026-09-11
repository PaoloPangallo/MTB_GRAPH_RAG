"""Canonical relation-observation prompt for the paper Reader."""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "paper-context-enricher-prompt/3.2"
TRANSPORT_VERSION = "paper-context-enrichment-transport/3.2"
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
    "observed_evidence_type", "observed_relation", "notes", "abstain_reason",
)
TOOL_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": list(_FIELDS),
    "properties": {
        **{name: {"type": "string"} for name in _FIELDS if name != "observed_relation"},
        "observed_relation": {"type": "object", "additionalProperties": False,
            "required": ["subjects", "intervention", "effect_direction", "relation_scope", "evidence_scope", "evidence_context"],
            "properties": {
                "subjects": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                    "required": ["type", "value"], "properties": {"type": {"type": "string"}, "value": {"type": "string"}}}},
                "intervention": {"type": ["string", "null"]},
                "effect_direction": {"type": "string", "enum": list(DIRECTIONS)},
                "relation_scope": {"type": "string", "enum": ["SINGLE", "COEXPRESSION", "COMBINATION", "CONDITIONAL", "UNKNOWN"]},
                "evidence_scope": {"type": "string", "enum": list(EVIDENCE_TYPES)},
                "evidence_context": {"type": "object", "additionalProperties": False,
                    "required": ["subject_level", "claim_type"],
                    "properties": {
                        "subject_level": {"type": "string", "enum": ["INDIVIDUAL", "COHORT", "POPULATION", "CELL_MODEL", "ANIMAL_MODEL", "OTHER", "UNKNOWN"]},
                        "claim_type": {"type": "string", "enum": ["OBSERVED_RESPONSE", "PREDICTIVE_ASSOCIATION", "PROGNOSTIC_ASSOCIATION", "DIAGNOSTIC_ASSOCIATION", "FUNCTIONAL_EFFECT", "MECHANISTIC_EFFECT", "ASSOCIATION", "OTHER", "UNKNOWN"]},
                    }},
            }},
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

SYSTEM_PROMPT = """You are an evidence extractor. Read biomedical SOURCE UNITS and report only what one
supplied SourceUnit literally states that is relevant to the challenged GCA. Do not decide
FULL_SUPPORT, PARTIAL_SUPPORT, NO_SUPPORT, CONTRADICTORY, or UNVERIFIABLE: deterministic relation
support makes those decisions later. Use no external knowledge; never recommend therapy, decide
eligibility, invent a source, or complete missing entities.

Choose QUOTE whenever at least one relevant observed field is explicitly stated in a supplied
SourceUnit. The quote must be one exact contiguous substring from exactly one supplied SourceUnit.
Populate only fields observed in that quote; use empty strings for unobserved fields. Missing or
mismatched GCA fields are not a reason to ABSTAIN. This includes generic gene evidence when a
specific variant is challenged, an opposite direction, a different intervention, and disease-only
context. ABSTAIN only if no supplied SourceUnit contains any relevant statement or no literal quote
can be produced. If decision is ABSTAIN, source_unit_id, quote, and every observed field must be
empty. Gene support is not variant support: a generic mutation statement does not confirm a specific
variant. Absence of a variant is not DOES_NOT_SUPPORT. A trial mention is not efficacy evidence.

Examples: for KRAS G12D and "KRAS mutations were associated with resistance", QUOTE that sentence,
set observed_gene=KRAS and leave observed_alteration empty. For challenged sensitivity and a source
stating resistance, QUOTE and set observed_direction=RESISTANCE. Populate observed_relation with every subject that necessarily participates in the quoted proposition; use COEXPRESSION, COMBINATION, or CONDITIONAL when applicable and UNKNOWN when unclear. Populate evidence_context.subject_level and claim_type from the quote (for example, one patient with a response is INDIVIDUAL + OBSERVED_RESPONSE, not a predictive association). Do not decide whether the relation matches the GCA or whether it is FULL_SUPPORT. For challenged Drug A and a source
stating Drug B, QUOTE and set observed_drug=Drug B. For a disease-only statement, QUOTE and populate
only observed_disease. Return exactly one tool call."""


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
