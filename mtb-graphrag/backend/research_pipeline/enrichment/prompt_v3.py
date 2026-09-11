"""Canonical relation-observation prompt for the paper Reader."""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "paper-context-enricher-prompt/4.8"
TRANSPORT_VERSION = "paper-context-enrichment-transport/4.5"
TOOL_NAME = "submit_paper_relation_observation"

STANCES = ("SUPPORTS", "DOES_NOT_SUPPORT", "UNKNOWN", "NOT_APPLICABLE")
EFFECT_DIRECTIONS = (
    "SENSITIVITY_RESPONSE", "RESISTANCE", "REDUCED_SENSITIVITY",
    "ADVERSE_RESPONSE", "UNKNOWN", "NOT_APPLICABLE",
)
EVIDENCE_TYPES = (
    "PREDICTIVE", "DIAGNOSTIC", "PROGNOSTIC", "PREDISPOSING", "FUNCTIONAL",
    "ONCOGENIC", "UNKNOWN", "NOT_APPLICABLE",
)
RELATION_SCOPES = ("SINGLE", "COEXPRESSION", "COMBINATION", "CONDITIONAL", "UNKNOWN")
SUBJECT_LEVELS = ("INDIVIDUAL", "COHORT", "POPULATION", "CELL_MODEL", "ANIMAL_MODEL", "OTHER", "UNKNOWN")
CLAIM_TYPES = (
    "OBSERVED_RESPONSE", "PREDICTIVE_ASSOCIATION", "PROGNOSTIC_ASSOCIATION",
    "DIAGNOSTIC_ASSOCIATION", "FUNCTIONAL_EFFECT", "MECHANISTIC_EFFECT",
    "ASSOCIATION", "OTHER", "UNKNOWN",
)
ABSTAIN_REASONS = (
    "NO_RELEVANT_EVIDENCE", "INSUFFICIENT_RELATION", "MISSING_REQUIRED_ANCHOR",
    "AMBIGUOUS_EVIDENCE", "COMPOSITION_UNCLEAR", "EVIDENCE_CONTEXT_UNCLEAR", "OTHER",
)
SUBJECT_TYPES = ("GENE", "ALTERATION", "BIOMARKER", "OTHER")
TOP_LEVEL_FIELDS = (
    "decision", "source_unit_id", "quote", "disease", "intervention", "observed_stance",
    "effect_direction", "relation_scope", "subject_level", "claim_type", "notes", "abstain_reason",
)
TOOL_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["decision"],
    "properties": {
        "decision": {"type": "string", "enum": ["QUOTE", "ABSTAIN"]},
        "source_unit_id": {"type": ["string", "null"]},
        "quote": {"type": ["string", "null"]},
        "disease": {"type": ["string", "null"]},
        "intervention": {"type": ["string", "null"]},
        **{f"subject_{i}_type": {"type": ["string", "null"], "enum": [*SUBJECT_TYPES, None]} for i in range(1, 5)},
        **{f"subject_{i}_value": {"type": ["string", "null"]} for i in range(1, 5)},
        **{f"subject_{i}_linked_gene": {"type": ["string", "null"]} for i in range(1, 5)},
        "observed_stance": {"type": ["string", "null"], "enum": [*STANCES, None]},
        "effect_direction": {"type": ["string", "null"], "enum": [*EFFECT_DIRECTIONS, None]},
        "relation_scope": {"type": ["string", "null"], "enum": [*RELATION_SCOPES, None]},
        "subject_level": {"type": ["string", "null"], "enum": [*SUBJECT_LEVELS, None]},
        "claim_type": {"type": ["string", "null"], "enum": [*CLAIM_TYPES, None]},
        "notes": {"type": ["string", "null"]},
        "abstain_reason": {"type": ["string", "null"], "enum": [*ABSTAIN_REASONS, None]},
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

SYSTEM_PROMPT = """You extract structured facts from exactly one quoted biomedical SourceUnit.
Do not decide whether the challenged GCA is supported, and never decide FULL_SUPPORT,
PARTIAL_SUPPORT, CONTRADICTORY, or UNVERIFIABLE. Use no external knowledge, do not invent
missing entities, and use exactly the flat tool fields provided.

Choose QUOTE when one supplied SourceUnit contains a relevant literal statement. Choose ABSTAIN
only when no relevant literal statement can be quoted. For QUOTE provide source_unit_id and an exact
contiguous quote. Use subject_1 through subject_4 for molecular participants explicitly present in
the quoted relation; each used slot needs both type and value, and participants must not be collapsed.
Use null or omit absent entity fields and UNKNOWN (or omit) for uncertain semantic enums.

observed_stance asks only whether the source supports the proposition: SUPPORTS, DOES_NOT_SUPPORT,
UNKNOWN, NOT_APPLICABLE. effect_direction asks only for the explicit therapeutic effect:
SENSITIVITY_RESPONSE, RESISTANCE, REDUCED_SENSITIVITY, ADVERSE_RESPONSE, UNKNOWN, NOT_APPLICABLE.
relation_scope asks only how participants are composed: SINGLE, COEXPRESSION, COMBINATION, CONDITIONAL,
UNKNOWN. claim_type asks what kind of claim is expressed: OBSERVED_RESPONSE, PREDICTIVE_ASSOCIATION,
PROGNOSTIC_ASSOCIATION, DIAGNOSTIC_ASSOCIATION, FUNCTIONAL_EFFECT, MECHANISTIC_EFFECT, ASSOCIATION,
OTHER, UNKNOWN. Never use a value from one enum in another; uncertain values must be UNKNOWN.
subject_level is INDIVIDUAL, COHORT, POPULATION, CELL_MODEL, ANIMAL_MODEL, OTHER, or UNKNOWN.
For ABSTAIN set abstain_reason to exactly one allowed enum and leave quote/source_unit_id null.

Molecular subject granularity:
- Preserve explicitly stated genes and alterations as separate subjects.
- If an alteration is explicitly linked to a gene in the source, use linked_gene.
- If linked_gene is populated from an explicitly named gene, emit that same gene as a separate GENE subject when a slot is available; linked_gene does not replace the GENE subject.
- Do not infer gene-alteration links from external knowledge.
- Do not collapse "GENE + alteration" into one ALTERATION subject when both are explicitly identifiable.
- If the text does not support a safe separation, preserve the observed surface form conservatively.
- For subject_value, extract the smallest textual span that identifies the molecular entity or alteration while preserving its meaning. Do not include surrounding explanatory words when they are not part of the entity identity.
Examples: "XYZ1 R123Q mutation" -> GENE XYZ1 plus ALTERATION R123Q linked_gene XYZ1;
"Loss of ABC2" -> GENE ABC2 plus ALTERATION loss linked_gene ABC2;
"DEF3 amplification" -> GENE DEF3 plus ALTERATION amplification linked_gene DEF3.

Atomic alteration value:
- When the SourceUnit explicitly contains a minimal textual span identifying the alteration, use that span as subject_value.
- Do not include an explicitly represented gene name inside ALTERATION when that gene is already a separate GENE subject.
- Preserve longer expressions only when the longer expression itself is the molecular alteration being stated.
- For "internal tandem duplication (ITD) of XYZ1", use ALTERATION "ITD" only when ITD is explicitly present; otherwise do not invent ITD.
- Do not use regex or mechanical splitting; if no safe atomic span is explicit, preserve the broader observed form.

Examples:
A: "In a cohort of patients, variant V was associated with improved response to drug X." →
QUOTE, subject_1_type=ALTERATION, subject_1_value="variant V", intervention="drug X",
observed_stance=SUPPORTS, effect_direction=SENSITIVITY_RESPONSE, relation_scope=SINGLE,
subject_level=COHORT, claim_type=PREDICTIVE_ASSOCIATION.
B: "One patient carrying variant V achieved a complete response to drug X." →
subject_level=INDIVIDUAL, claim_type=OBSERVED_RESPONSE, effect_direction=SENSITIVITY_RESPONSE.
Do not label this PREDICTIVE_ASSOCIATION solely because a response occurred.
C: "Coexpression of GENE_A and GENE_B sensitized cells to drug X." →
subject_1_type=GENE, subject_1_value="GENE_A", subject_2_type=GENE,
subject_2_value="GENE_B", intervention="drug X", relation_scope=COEXPRESSION,
subject_level=CELL_MODEL, claim_type=FUNCTIONAL_EFFECT, effect_direction=SENSITIVITY_RESPONSE.
D: no relevant relation → decision=ABSTAIN, abstain_reason=NO_RELEVANT_EVIDENCE.
Return exactly one tool call."""


def render_request(case_context: dict[str, Any], candidate: dict[str, Any], paper_id: str,
                   source_units: list[dict[str, Any]]) -> str:
    header = {
        "case_context": case_context,
        "candidate": candidate,
        "paper_id": paper_id,
        "instruction": (
            "Extract one flat paper observation using only the tool fields. Quote exactly one supplied "
            "SourceUnit. Omit or use null for absent entity fields and use UNKNOWN for uncertain "
            "semantic enums."
        ),
    }
    units = [
        {"source_unit_id": unit.get("source_unit_id"), "document_id": unit.get("document_id"),
         "unit_type": unit.get("unit_type"), "locator": unit.get("section"), "text": unit.get("text", "")}
        for unit in source_units
    ]
    return json.dumps({**header, "source_units": units}, ensure_ascii=False, sort_keys=True)
