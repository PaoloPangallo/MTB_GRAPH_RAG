"""Prompt + forced-tool schema for the CaseContext Parser. Versioned as
casecontext-parser-prompt/1.0. The parser receives only free clinical text --
never the structured record it was derived from, never KG results."""
from __future__ import annotations

import hashlib
import json
from typing import Any

PROMPT_VERSION = "casecontext-parser-prompt/1.0"
TOOL_NAME = "submit_case_context"

_SPAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["quote", "start_offset", "end_offset"],
    "properties": {
        "quote": {"type": "string"},
        "start_offset": {"type": ["integer", "null"]},
        "end_offset": {"type": ["integer", "null"]},
    },
}

_FIELD_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["raw_value", "normalized_value", "source_spans"],
    "properties": {
        "raw_value": {"type": ["string", "null"]},
        "normalized_value": {"type": ["string", "null"]},
        "source_spans": {"type": "array", "items": _SPAN_SCHEMA},
    },
}

_BIOMARKER_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["gene", "alteration", "raw_value", "normalized_value", "source_spans"],
    "properties": {
        "gene": {"type": ["string", "null"]},
        "alteration": {"type": ["string", "null"]},
        "raw_value": {"type": "string"},
        "normalized_value": {"type": "string"},
        "source_spans": {"type": "array", "items": _SPAN_SCHEMA},
    },
}

CASECONTEXT_TOOL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["case_id", "disease", "biomarkers", "previous_interventions", "target_intervention", "query_intent", "clinical_question", "uncertainties"],
    "properties": {
        "case_id": {"type": "string"},
        "disease": _FIELD_SCHEMA,
        "biomarkers": {"type": "array", "items": _BIOMARKER_SCHEMA},
        "previous_interventions": {"type": "array", "items": _FIELD_SCHEMA},
        "target_intervention": {"type": ["object", "null"], "additionalProperties": False, "properties": _FIELD_SCHEMA["properties"]},
        "query_intent": {"type": "string", "enum": ["THERAPY_EVALUATION", "THERAPY_DISCOVERY"]},
        "clinical_question": {"type": "string"},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
    },
}

CASECONTEXT_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "Submit one structured CaseContext extracted only from the supplied free clinical text.",
        "parameters": CASECONTEXT_TOOL_SCHEMA,
    },
}

SYSTEM_PROMPT = """You are a clinical case context extraction component. Read only the supplied free clinical text. Do not use external knowledge, do not query any database, do not know or guess what the correct or expected answer is. Extract disease, biomarkers (gene + alteration), any previous interventions, and -- only if the text names a specific drug the clinician wants evaluated -- a target intervention. If the text asks a discovery-style question ("what therapy options exist") without naming a specific drug, target_intervention must be null and query_intent must be THERAPY_DISCOVERY; do not invent a drug name to fill it. If the text names a specific drug to evaluate, query_intent must be THERAPY_EVALUATION. Every non-null field must carry at least one literal, contiguous, exact quotation from the supplied text as a source_spans entry (copy the quote exactly; do not paraphrase or translate). Do not add a drug, gene, alteration, or disease that is not literally present in the text. Do not invent molecular variants. Do not produce clinical recommendations. Record anything unclear or ambiguous in uncertainties. Call submit_case_context exactly once."""

TASK_PROMPT = """Populate every required field of the tool call strictly from the supplied text. Leave a field null (with an empty source_spans list) only when the text truly does not mention it. Do not guess a case_id beyond the one supplied in the input."""


def prompt_hash() -> str:
    payload = {"version": PROMPT_VERSION, "system": SYSTEM_PROMPT, "task": TASK_PROMPT, "schema": CASECONTEXT_TOOL_SCHEMA}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def render_request(case_id: str, clinical_text: str) -> str:
    header = json.dumps({"case_id": case_id}, ensure_ascii=False, sort_keys=True)
    return f"{header}\n--- CLINICAL TEXT START ---\n<<<\n{clinical_text}\n>>>\n--- CLINICAL TEXT END ---"


def tool_argument_errors(arguments: Any) -> list[str]:
    from ..models import case_context_schema_errors
    if not isinstance(arguments, dict):
        return ["ARGUMENTS_NOT_OBJECT"]
    expected = set(CASECONTEXT_TOOL_SCHEMA["properties"])
    if set(arguments) != expected:
        return [f"TOP_LEVEL_KEYS:{sorted(set(arguments) ^ expected)}"]
    return case_context_schema_errors(arguments)
