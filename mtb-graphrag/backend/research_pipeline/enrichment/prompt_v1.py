"""Prompt + forced-tool schema for the Paper Context Enricher.
Versioned as paper-context-enricher-prompt/1.0.

The LLM never produces enrichment_id/case_id/candidate_id/paper_id/model/
prompt_version -- those are filled in deterministically by the adapter, so
the model cannot invent identifiers. The model only reports what a supplied
passage says about a named drug."""
from __future__ import annotations

import hashlib
import json
from typing import Any

PROMPT_VERSION = "paper-context-enricher-prompt/1.0"
TOOL_NAME = "submit_paper_context_enrichment"

TOOL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["source_unit_id", "drug", "author_claim_quote", "author_context_summary", "evidence_kind", "abstain", "abstention_reason"],
    "properties": {
        "source_unit_id": {"type": ["string", "null"]},
        "drug": {"type": ["string", "null"]},
        "author_claim_quote": {"type": ["string", "null"]},
        "author_context_summary": {"type": ["string", "null"]},
        "evidence_kind": {"type": ["string", "null"], "enum": ["RESPONSE", "BENEFIT", "RESISTANCE", "DIAGNOSTIC", "MECHANISTIC", "OTHER", None]},
        "abstain": {"type": "boolean"},
        "abstention_reason": {"type": ["string", "null"]},
    },
}

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "Report what the supplied paper passages say about the named drug. Never decide clinical validity.",
        "parameters": TOOL_SCHEMA,
    },
}

SYSTEM_PROMPT = """You are a biomedical paper context enrichment component.

Your task is not to decide whether a treatment is clinically valid for the patient.

Your task is only to report what the supplied paper passage says about the specified drug in the specified disease and molecular context.

Use only the supplied SOURCE UNITS.

The CASE CONTEXT and CANDIDATE describe what the system is investigating. They are not documentary evidence and must never be quoted.

Select at most one short, continuous, literal quotation from the supplied exact_text.

The quotation must explain what the authors report about the intervention, such as response, benefit, resistance, lack of benefit, diagnostic relevance, or mechanistic rationale.

Copy the quotation exactly.

Do not:
- paraphrase the quotation;
- translate it;
- change punctuation;
- join non-contiguous passages;
- use ellipses;
- use external knowledge;
- cite the CASE CONTEXT;
- cite the CANDIDATE;
- decide DIRECT, PARTIAL, AMBIGUOUS or CONTRADICTED;
- recommend a treatment;
- assign gate, score or evidence level.

After selecting the quotation, write a maximum two-sentence summary that only explains the meaning of that quotation.

If no supplied passage contains a defensible statement about the drug in the requested context, return abstain=true.

Call submit_paper_context_enrichment exactly once, even when abstaining."""

TASK_PROMPT = """Report which SOURCE UNIT (by source_unit_id) the quotation comes from. If abstaining, leave source_unit_id, drug, author_claim_quote, author_context_summary and evidence_kind null, set abstain=true, and give a short abstention_reason."""


def prompt_hash() -> str:
    payload = {"version": PROMPT_VERSION, "system": SYSTEM_PROMPT, "task": TASK_PROMPT, "schema": TOOL_SCHEMA}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _format_source_unit(unit: dict[str, Any]) -> str:
    locator = {k: unit.get(k) for k in ("section", "subsection", "paragraph_index", "sentence_index") if unit.get(k) is not None}
    return f"--- SOURCE UNIT START ---\nsource_unit_id: {unit['source_unit_id']}\nlocator: {json.dumps(locator, ensure_ascii=False)}\nexact_text:\n<<<\n{unit.get('text', '')}\n>>>\n--- SOURCE UNIT END ---"


def render_request(case_context: dict[str, Any], candidate_summary: dict[str, Any], drug: str, source_units: list[dict[str, Any]]) -> str:
    header = {
        "note": "CASE CONTEXT and CANDIDATE below are the system's own working hypothesis, not documentary evidence -- never quote them.",
        "case_context": {"disease": case_context.get("disease"), "biomarkers": case_context.get("biomarkers"), "query_intent": case_context.get("query_intent")},
        "candidate": candidate_summary,
        "requested_drug": drug,
    }
    blocks = "\n".join(_format_source_unit(unit) for unit in source_units)
    return json.dumps(header, ensure_ascii=False, sort_keys=True) + "\n" + blocks


def tool_argument_errors(arguments: Any) -> list[str]:
    if not isinstance(arguments, dict):
        return ["ARGUMENTS_NOT_OBJECT"]
    expected = set(TOOL_SCHEMA["properties"])
    if set(arguments) != expected:
        return [f"TOP_LEVEL_KEYS:{sorted(set(arguments) ^ expected)}"]
    errors: list[str] = []
    if not isinstance(arguments["abstain"], bool):
        errors.append("ABSTAIN_NOT_BOOLEAN")
    if arguments["evidence_kind"] is not None and arguments["evidence_kind"] not in ("RESPONSE", "BENEFIT", "RESISTANCE", "DIAGNOSTIC", "MECHANISTIC", "OTHER"):
        errors.append("EVIDENCE_KIND_INVALID")
    if arguments["abstain"]:
        if any(arguments[key] is not None for key in ("source_unit_id", "drug", "author_claim_quote", "author_context_summary", "evidence_kind")):
            errors.append("ABSTAIN_TRUE_BUT_FIELDS_POPULATED")
    else:
        if not arguments.get("author_claim_quote"):
            errors.append("NON_ABSTAIN_REQUIRES_QUOTE")
        if not arguments.get("source_unit_id"):
            errors.append("NON_ABSTAIN_REQUIRES_SOURCE_UNIT_ID")
    return errors
