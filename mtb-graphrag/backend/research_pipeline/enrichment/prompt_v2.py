"""Prompt + minimal all-string tool schema for Paper Context Enricher v2.0.
Versioned paper-context-enricher-prompt/2.0, transport
paper-context-enrichment-transport/2.0. Independent of v1.0/v1.1
(paper_context_enricher_prompt.py / paper_context_enricher_prompt_v1_1.py),
neither of which is modified here. Gemma makes exactly one choice --
QUOTE or ABSTAIN -- and never classifies evidence_kind or produces any
metadata (those are always added locally, see paper_context_enricher_v2.py).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

PROMPT_VERSION = "paper-context-enricher-prompt/2.0"
TRANSPORT_VERSION = "paper-context-enrichment-transport/2.0"
TOOL_NAME = "submit_paper_context_enrichment_v2"
DECISIONS = ("QUOTE", "ABSTAIN")

# All five fields are plain strings -- no null, no nested objects, no union types,
# no evidence_kind, no model-produced identifiers/offsets/hashes.
TOOL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["decision", "source_unit_id", "author_claim_quote", "author_context_summary", "abstention_reason"],
    "properties": {
        "decision": {"type": "string", "enum": list(DECISIONS)},
        "source_unit_id": {"type": "string"},
        "author_claim_quote": {"type": "string"},
        "author_context_summary": {"type": "string"},
        "abstention_reason": {"type": "string"},
    },
}

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "Choose QUOTE (cite one literal passage about the requested drug) or ABSTAIN. Never classify or decide clinical validity.",
        "parameters": TOOL_SCHEMA,
    },
}

SYSTEM_PROMPT = """You are a biomedical paper quotation extraction component.

Your task is only to choose between:

QUOTE
or
ABSTAIN.

Use only the supplied SOURCE UNITS.

The CASE CONTEXT and CANDIDATE explain what the system is investigating. They are not documentary evidence and must never be quoted.

Choose QUOTE when at least one supplied SOURCE UNIT contains a passage in which the paper authors report an observation, result, conclusion, resistance finding, lack of benefit, clinical association, diagnostic relevance, or mechanistic rationale concerning the specified intervention.

The selected quotation does not need to repeat the disease, biomarker and intervention in the same sentence when the surrounding supplied SOURCE UNITS from the same paper clearly establish that context.

When decision=QUOTE:

- copy exactly one short, continuous quotation;
- copy the exact source_unit_id containing it;
- do not paraphrase;
- do not translate;
- do not change punctuation or capitalization;
- do not combine separate fragments;
- do not add ellipses;
- author_context_summary may contain zero, one or two short sentences;
- the summary must explain only what the quote reports;
- an empty summary is allowed.

Choose ABSTAIN only when none of the supplied SOURCE UNITS contains a defensible passage concerning the specified intervention.

Do not abstain merely because:

- the finding is negative;
- the finding reports resistance;
- the finding contradicts the candidate;
- the result is uncertain;
- the quotation does not repeat every CaseContext field;
- the summary would be empty.

Do not:

- use external knowledge;
- quote the CASE CONTEXT;
- quote the CANDIDATE;
- classify the evidence;
- assign an evidence kind;
- decide DIRECT, PARTIAL, AMBIGUOUS or CONTRADICTED;
- recommend a treatment;
- assign a gate, score or evidence level.

Call submit_paper_context_enrichment_v2 exactly once.

Return no prose outside the tool call."""


def prompt_hash() -> str:
    payload = {"version": PROMPT_VERSION, "transport": TRANSPORT_VERSION, "system": SYSTEM_PROMPT, "schema": TOOL_SCHEMA}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _format_source_unit(unit: dict[str, Any]) -> str:
    locator = {k: unit.get(k) for k in ("section", "subsection", "paragraph_index", "sentence_index") if unit.get(k) is not None}
    return f"--- SOURCE UNIT START ---\nsource_unit_id: {unit['source_unit_id']}\nunit_type: {unit.get('unit_type')}\nlocator: {json.dumps(locator, ensure_ascii=False)}\nexact_text:\n<<<\n{unit.get('text', '')}\n>>>\n--- SOURCE UNIT END ---"


def render_request(case_context: dict[str, Any], candidate_summary: dict[str, Any], drug: str, paper_id: str, source_units: list[dict[str, Any]]) -> str:
    # Deliberately excludes: expected status, baseline, validator result, whether the
    # case is DIRECT/PARTIAL/CONTRADICTED, or any expected quotation (section 7).
    header = {
        "note": "CASE CONTEXT and CANDIDATE below are the system's own working hypothesis, not documentary evidence -- never quote them.",
        "case_context": {"disease": case_context.get("disease"), "biomarkers": case_context.get("biomarkers")},
        "candidate_intervention": drug,
        "paper_id": paper_id,
        "instruction": "Return QUOTE or ABSTAIN. For QUOTE, copy a literal substring from exact_text and give its exact source_unit_id. Do not produce an evidence_kind. Do not produce text outside the tool call.",
    }
    blocks = "\n".join(_format_source_unit(unit) for unit in source_units)
    return json.dumps(header, ensure_ascii=False, sort_keys=True) + "\n" + blocks
