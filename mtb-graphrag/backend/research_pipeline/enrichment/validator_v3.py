"""Literal and provenance validation for Paper Reader 3.0."""

from __future__ import annotations

from typing import Any


def validate_enrichment_v3(transport_result: str, enrichment: dict[str, Any] | None, *,
                           candidate: dict[str, Any], paper_bundle: dict[str, Any],
                           source_units_by_id: dict[str, dict[str, Any]], **_: Any) -> dict[str, Any]:
    if transport_result != "V3_TRANSPORT_VALID" or enrichment is None:
        return {"outcome": "REJECTED_TRANSPORT", "reason_codes": [transport_result]}
    if enrichment.get("decision") == "ABSTAIN":
        populated = [name for name in ("source_unit_id", "quote") if enrichment.get(name)]
        return {
            "outcome": "ENRICHMENT_V3_ABSTAINED" if not populated else "QUOTE_INVALID",
            "reason_codes": [] if not populated else ["FIELDS_POPULATED_DESPITE_ABSTAIN"],
        }
    unit_id = enrichment.get("source_unit_id")
    quote = str(enrichment.get("quote") or "")
    allowed = paper_bundle.get("resolved_source_unit_ids") or paper_bundle.get("source_unit_ids") or []
    unit = source_units_by_id.get(str(unit_id))
    expected_document = paper_bundle.get("document_id")
    if not unit or unit_id not in allowed:
        return {"outcome": "QUOTE_INVALID", "reason_codes": ["SOURCE_UNIT_NOT_IN_SELECTED_DOCUMENT"]}
    if expected_document and unit.get("document_id") not in {None, expected_document}:
        return {"outcome": "QUOTE_INVALID", "reason_codes": ["DOCUMENT_PROVENANCE_MISMATCH"]}
    if not quote or quote not in str(unit.get("text") or ""):
        return {"outcome": "QUOTE_INVALID", "reason_codes": ["QUOTE_NOT_LITERAL_IN_SOURCE_UNIT"]}
    relation = enrichment.get("observed_relation")
    if relation is not None:
        if not isinstance(relation, dict) or not isinstance(relation.get("subjects"), list):
            return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_RELATION_SHAPE_INVALID"]}
        if relation.get("relation_scope") not in {"SINGLE", "COEXPRESSION", "COMBINATION", "CONDITIONAL", "UNKNOWN"}:
            return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_RELATION_SCOPE_INVALID"]}
        context = relation.get("evidence_context")
        if context is not None:
            levels = {"INDIVIDUAL", "COHORT", "POPULATION", "CELL_MODEL", "ANIMAL_MODEL", "OTHER", "UNKNOWN"}
            claims = {"OBSERVED_RESPONSE", "PREDICTIVE_ASSOCIATION", "PROGNOSTIC_ASSOCIATION", "DIAGNOSTIC_ASSOCIATION", "FUNCTIONAL_EFFECT", "MECHANISTIC_EFFECT", "ASSOCIATION", "OTHER", "UNKNOWN"}
            if not isinstance(context, dict) or context.get("subject_level") not in levels or context.get("claim_type") not in claims:
                return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_EVIDENCE_CONTEXT_INVALID"]}
            lowered = quote.casefold()
            if context["subject_level"] == "INDIVIDUAL" and "one patient" not in lowered and "single patient" not in lowered:
                return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_SUBJECT_LEVEL_NOT_GROUNDED"]}
            if context["subject_level"] == "COHORT" and "cohort" not in lowered and "patients" not in lowered:
                return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_SUBJECT_LEVEL_NOT_GROUNDED"]}
        for subject in relation["subjects"]:
            if not isinstance(subject, dict) or not subject.get("type") or not subject.get("value"):
                return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_RELATION_SUBJECT_INVALID"]}
            if str(subject["value"]).casefold() not in quote.casefold():
                return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_RELATION_SUBJECT_NOT_GROUNDED"]}
        intervention = relation.get("intervention")
        if intervention and str(intervention).casefold() not in quote.casefold():
            return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_RELATION_INTERVENTION_NOT_GROUNDED"]}
    return {"outcome": "ENRICHMENT_V3_ACCEPTED", "reason_codes": [], "quote_valid": True}
