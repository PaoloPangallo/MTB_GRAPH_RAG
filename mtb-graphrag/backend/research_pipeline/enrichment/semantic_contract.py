"""Typed semantic judgments and literal anchoring, not a truth oracle."""

from typing import Any

from jsonschema import Draft7Validator

POLICY_VERSION = "evidence-drug-semantic-admission/2.1"
_ENUMS = {
    "relation_alignment": ["SAME", "OPPOSITE", "NO_SUPPORT", "INSUFFICIENT", "AMBIGUOUS"],
    "assertion_scope": ["DIRECT_ASSERTION", "REPORTED_PRIOR_WORK", "HYPOTHETICAL",
                        "REJECTED_ASSERTION", "UNCERTAIN_ASSERTION", "QUESTIONED_ASSERTION", "UNKNOWN"],
    "evidence_role": ["OBSERVED_RESULT", "STUDY_DESIGN", "ELIGIBILITY", "BACKGROUND", "UNKNOWN"],
    "molecular_scope": ["SAME", "NARROWER", "BROADER", "DIFFERENT", "UNKNOWN"],
    "population_scope": ["SAME", "NARROWER", "BROADER", "DIFFERENT", "UNKNOWN"],
    "intervention_scope": ["SAME", "COMBINATION", "DIFFERENT", "UNKNOWN"],
    "inference": ["DIRECT", "INVERSE", "INDIRECT", "UNKNOWN"],
    "certainty": ["ESTABLISHED", "UNCERTAIN", "UNKNOWN"],
}
SPAN_FIELDS = ("decisive_text", "result_span", "molecular_span", "population_span", "intervention_span")
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": [*_ENUMS, "reason", *SPAN_FIELDS],
    "properties": {**{key: {"enum": values} for key, values in _ENUMS.items()},
                   "reason": {"type": "string", "minLength": 1},
                   **{key: {"type": "string"} for key in SPAN_FIELDS}},
}
ASSESSMENT_FIELDS: tuple[str, ...] = tuple(OUTPUT_SCHEMA["required"])
_VALIDATOR = Draft7Validator(OUTPUT_SCHEMA)


def assessment_payload(output: Any) -> Any:
    """Strip caller metadata only; unknown tool fields must remain invalid."""
    if not isinstance(output, dict):
        return output
    return {key: value for key, value in output.items()
            if key not in {"model", "prompt_version", "transport_result", "transport_reason_codes", "operational_metrics"}}


def validate_assessment(output: Any, gep: dict[str, Any]) -> dict[str, Any]:
    if list(_VALIDATOR.iter_errors(output)):
        raise ValueError("SEMANTIC_OUTPUT_SCHEMA_INVALID")
    source = gep.get("required_context") if isinstance(gep, dict) else None
    if not isinstance(source, str):
        raise ValueError("SEMANTIC_CONTEXT_MISSING")
    for field in SPAN_FIELDS:
        span = output[field]
        if span and (not span.strip() or span not in source):
            raise ValueError(f"SEMANTIC_{field.upper()}_NOT_LITERAL")
    required = []
    if output["relation_alignment"] in {"SAME", "OPPOSITE", "NO_SUPPORT"}:
        required.append("decisive_text")
    if output["evidence_role"] == "OBSERVED_RESULT":
        required.append("result_span")
    for dimension, field in (("molecular_scope", "molecular_span"),
                             ("population_scope", "population_span"),
                             ("intervention_scope", "intervention_span")):
        if output[dimension] in {"SAME", "NARROWER"}:
            required.append(field)
    if any(not output[field].strip() for field in required):
        raise ValueError("SEMANTIC_REQUIRED_SPAN_MISSING")
    return dict(output)


def admission_blockers(output: Any, gep: dict[str, Any]) -> list[str]:
    """Positive, null and contrary judgments require comparable direct results."""
    try:
        output = validate_assessment(output, gep)
    except ValueError as error:
        return [str(error)]
    required = {"assertion_scope": "DIRECT_ASSERTION", "evidence_role": "OBSERVED_RESULT",
                "molecular_scope": "SAME", "population_scope": "SAME",
                "intervention_scope": "SAME", "inference": "DIRECT", "certainty": "ESTABLISHED"}
    return [f"SEMANTIC_{key.upper()}_{output[key]}" for key, value in required.items()
            if output[key] != value]


def partial_admission_blockers(output: Any, gep: dict[str, Any]) -> list[str]:
    """Allow limited support only for a direct observed relation in a narrower context."""
    try:
        output = validate_assessment(output, gep)
    except ValueError as error:
        return [str(error)]
    allowed = {
        "relation_alignment": "SAME", "assertion_scope": "DIRECT_ASSERTION",
        "evidence_role": "OBSERVED_RESULT", "intervention_scope": "SAME",
        "inference": "DIRECT", "certainty": "ESTABLISHED",
    }
    blockers = [f"SEMANTIC_{key.upper()}_{output[key]}" for key, value in allowed.items()
                if output[key] != value]
    for key in ("molecular_scope", "population_scope"):
        if output[key] not in {"SAME", "NARROWER"}:
            blockers.append(f"SEMANTIC_{key.upper()}_{output[key]}")
    if not any(output[key] == "NARROWER" for key in ("molecular_scope", "population_scope")):
        blockers.append("SEMANTIC_NO_IDENTIFIED_LIMITATION")
    return blockers


def unresolved_assessment(reason: str) -> dict[str, Any]:
    return {**{key: "UNKNOWN" for key in _ENUMS}, "relation_alignment": "AMBIGUOUS",
            "reason": reason, **{key: "" for key in SPAN_FIELDS}}
