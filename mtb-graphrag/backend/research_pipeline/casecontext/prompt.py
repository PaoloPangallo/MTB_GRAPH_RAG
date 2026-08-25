"""Prompt and tool schema for the canonical minimal CaseContext Parser."""
from __future__ import annotations

import hashlib
import json
from typing import Any

PROMPT_VERSION = "casecontext-parser-prompt/3.0"
TOOL_NAME = "submit_case_context"

_VALUE_SCHEMA = {
    "type": ["object", "null"],
    "additionalProperties": False,
    "required": ["raw_value", "quote"],
    "properties": {
        "raw_value": {"type": ["string", "null"]},
        "quote": {"type": ["string", "null"]},
    },
}

_NON_NULL_VALUE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["raw_value", "quote"],
    "properties": {
        "raw_value": {"type": "string"},
        "quote": {"type": "string"},
    },
}

_BIOMARKER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["gene", "alteration"],
    "properties": {
        "gene": _VALUE_SCHEMA,
        "alteration": _VALUE_SCHEMA,
    },
}

CASECONTEXT_TOOL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["disease", "biomarkers", "previous_interventions", "target_intervention", "query_intent"],
    "properties": {
        "disease": _VALUE_SCHEMA,
        "biomarkers": {"type": "array", "items": _BIOMARKER_SCHEMA},
        "previous_interventions": {"type": "array", "items": _NON_NULL_VALUE_SCHEMA},
        "target_intervention": {"anyOf": [_NON_NULL_VALUE_SCHEMA, {"type": "null"}]},
        "query_intent": {
            "type": ["string", "null"],
            "enum": ["THERAPY_EVALUATION", "THERAPY_DISCOVERY", None],
        },
        "ambiguities": {"type": "array", "items": {"type": "string"}},
    },
}

CASECONTEXT_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "Submit literal case-context mentions extracted only from the supplied clinical text.",
        "parameters": CASECONTEXT_TOOL_SCHEMA,
    },
}

SYSTEM_PROMPT = """You extract structured facts from the supplied clinical text. Do not infer facts that are not explicitly written and do not use external knowledge. Never invent disease, gene, alteration, drug, treatment status, or clinical status. Preserve specificity: a gene is not a specific variant, and KRAS is not KRAS G12D. Distinguish previous treatment from a treatment currently being evaluated. If a value is absent, return null or an empty list. If wording is ambiguous, add a short ambiguity flag instead of completing it by intuition. Do not propose or recommend therapy. Every populated clinical value must include one literal contiguous quote from the input. Return only JSON through submit_case_context exactly once."""

TASK_PROMPT = """Populate only the tool schema. Disease, gene, alteration, previous interventions and target intervention must be copied from the text, never inferred. Use query_intent only when the question is explicit. Use ambiguities for unresolved wording. Do not produce prose or recommendations."""


def prompt_hash() -> str:
    payload = {"version": PROMPT_VERSION, "system": SYSTEM_PROMPT, "task": TASK_PROMPT, "schema": CASECONTEXT_TOOL_SCHEMA}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def render_request(case_id: str, clinical_text: str) -> str:
    header = json.dumps({"case_id": case_id}, ensure_ascii=False, sort_keys=True)
    return f"{header}\n--- CLINICAL TEXT START ---\n<<<\n{clinical_text}\n>>>\n--- CLINICAL TEXT END ---"


def _value_errors(value: Any, label: str, *, nullable: bool, required_strings: bool) -> list[str]:
    if value is None and nullable:
        return []
    if not isinstance(value, dict):
        return [f"{label}_NOT_OBJECT"]
    errors = []
    if set(value) != {"raw_value", "quote"}:
        errors.append(f"{label}_KEYS_INVALID")
        return errors
    for key in ("raw_value", "quote"):
        if not isinstance(value[key], str):
            errors.append(f"{label}_{key.upper()}_REQUIRED_STRING" if required_strings else f"{label}_{key.upper()}_INVALID")
    return errors


def tool_argument_errors(arguments: Any) -> list[str]:
    if not isinstance(arguments, dict):
        return ["ARGUMENTS_NOT_OBJECT"]
    expected = set(CASECONTEXT_TOOL_SCHEMA["properties"])
    required = set(CASECONTEXT_TOOL_SCHEMA["required"])
    if not required <= set(arguments) or not set(arguments) <= expected:
        return [f"TOP_LEVEL_KEYS:{sorted(set(arguments) ^ expected)}"]

    errors = _value_errors(arguments["disease"], "DISEASE", nullable=True, required_strings=False)
    biomarkers = arguments["biomarkers"]
    if not isinstance(biomarkers, list):
        errors.append("BIOMARKERS_NOT_LIST")
    else:
        for index, biomarker in enumerate(biomarkers):
            if not isinstance(biomarker, dict) or set(biomarker) != {"gene", "alteration"}:
                errors.append(f"BIOMARKER_{index}_SHAPE_INVALID")
                continue
            errors.extend(_value_errors(biomarker["gene"], f"BIOMARKER_{index}_GENE", nullable=True, required_strings=False))
            errors.extend(_value_errors(biomarker["alteration"], f"BIOMARKER_{index}_ALTERATION", nullable=True, required_strings=False))

    previous = arguments["previous_interventions"]
    if not isinstance(previous, list):
        errors.append("PREVIOUS_INTERVENTIONS_NOT_LIST")
    else:
        for index, item in enumerate(previous):
            errors.extend(_value_errors(item, f"PREVIOUS_INTERVENTION_{index}", nullable=False, required_strings=True))

    errors.extend(_value_errors(arguments["target_intervention"], "TARGET_INTERVENTION", nullable=True, required_strings=True))
    if arguments["query_intent"] not in {None, "THERAPY_EVALUATION", "THERAPY_DISCOVERY"}:
        errors.append("QUERY_INTENT_INVALID")
    if "ambiguities" in arguments and (
        not isinstance(arguments["ambiguities"], list)
        or any(not isinstance(item, str) for item in arguments["ambiguities"])
    ):
        errors.append("AMBIGUITIES_INVALID")
    return errors
