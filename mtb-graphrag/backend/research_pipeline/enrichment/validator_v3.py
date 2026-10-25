"""Structural/provenance validation for Paper Reader 4.0."""

from __future__ import annotations
from .observation_checks import assess_observation

from typing import Any
import re

from .canonical_normalizer import normalized_phrase_in, subject_level_consistency
from .prompt_v3 import RELATION_ASSERTIONS
from .observation_scope import MOLECULAR_COMPOSITIONS, INTERVENTION_COMPOSITIONS, intervention_composition_conflict

VALIDATOR_VERSION = "paper-validator/4.3"


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
    if enrichment.get("candidate_id") and enrichment.get("candidate_id") != candidate.get("candidate_id"):
        return {"outcome": "QUOTE_INVALID", "reason_codes": ["CANDIDATE_ID_MISMATCH"]}
    if enrichment.get("paper_id") and enrichment.get("paper_id") not in {
        paper_bundle.get("document_id"), paper_bundle.get("bundle_id"),
    }:
        return {"outcome": "QUOTE_INVALID", "reason_codes": ["PAPER_ID_MISMATCH"]}
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
    identity_grounding = None
    relation = enrichment.get("observed_relation")
    observation_checks = assess_observation(quote, relation if isinstance(relation, dict) else enrichment)
    if observation_checks['status'] != 'PASS':
        return {'outcome': 'QUOTE_INVALID', 'reason_codes': observation_checks['reason_codes'],
                'quote_valid': True, 'observation_checks': observation_checks}
    if relation is not None:
        if not isinstance(relation, dict) or not isinstance(relation.get("subjects"), list):
            return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_RELATION_SHAPE_INVALID"]}
        if relation.get("observed_stance") not in {"SUPPORTS", "DOES_NOT_SUPPORT", "UNKNOWN", "NOT_APPLICABLE"}:
            return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_RELATION_STANCE_INVALID"]}
        if relation.get("relation_assertion") not in set(RELATION_ASSERTIONS):
            return {"outcome": "QUOTE_INVALID", "reason_codes": ["RELATION_ASSERTION_INVALID"]}
        if relation.get("relation_scope") not in MOLECULAR_COMPOSITIONS:
            return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_RELATION_SCOPE_INVALID"]}
        context = relation.get("evidence_context")
        if context is not None:
            levels = {"INDIVIDUAL", "COHORT", "POPULATION", "CELL_MODEL", "ANIMAL_MODEL", "OTHER", "UNKNOWN"}
            claims = {"OBSERVED_RESPONSE", "PREDICTIVE_ASSOCIATION", "PROGNOSTIC_ASSOCIATION", "DIAGNOSTIC_ASSOCIATION", "FUNCTIONAL_EFFECT", "MECHANISTIC_EFFECT", "ASSOCIATION", "OTHER", "UNKNOWN"}
            if not isinstance(context, dict) or context.get("subject_level") not in levels or context.get("claim_type") not in claims:
                return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_EVIDENCE_CONTEXT_INVALID"]}
            consistency = subject_level_consistency(context["subject_level"], quote)
            if consistency == "INCONSISTENT":
                return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_SUBJECT_LEVEL_NOT_GROUNDED"]}
        for subject in relation["subjects"]:
            surface = subject.get("surface_value") or subject.get("value") if isinstance(subject, dict) else ""
            if not isinstance(subject, dict) or subject.get("type") not in {"GENE", "ALTERATION", "BIOMARKER", "OTHER", "gene", "alteration", "biomarker", "other"} or not surface:
                return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_RELATION_SUBJECT_INVALID"]}
            if not normalized_phrase_in(surface, quote):
                return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_RELATION_SUBJECT_NOT_GROUNDED"]}
        pairings = relation.get("subject_pairings") or []
        for pairing in pairings:
            if not normalized_phrase_in(pairing.get("gene"), quote) or not normalized_phrase_in(pairing.get("alteration"), quote):
                return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_PAIRING_NOT_GROUNDED"]}
        intervention = relation.get("intervention")
        if relation.get("molecular_composition", "UNKNOWN") not in MOLECULAR_COMPOSITIONS:
            return {"outcome": "QUOTE_INVALID", "reason_codes": ["MOLECULAR_COMPOSITION_INVALID"]}
        composition = relation.get("intervention_composition", "UNKNOWN")
        if composition not in INTERVENTION_COMPOSITIONS:
            return {"outcome": "QUOTE_INVALID", "reason_codes": ["INTERVENTION_COMPOSITION_INVALID"]}
        if intervention_composition_conflict(composition, str(intervention or "")):
            return {"outcome": "QUOTE_INVALID", "reason_codes": ["INTERVENTION_SCOPE_CONTRADICTS_LITERAL_REGIMEN"]}
        if intervention and not normalized_phrase_in(intervention, quote):
            return {"outcome": "QUOTE_INVALID", "reason_codes": ["OBSERVED_RELATION_INTERVENTION_NOT_GROUNDED"]}
        for field in ("nct_id", "trial_name", "trial_phase", "trial_status", "trial_condition"):
            value = relation.get("trial_context", {}).get(field)
            if value and not normalized_phrase_in(value, quote):
                # The selected registry document authenticates its own identity;
                # clinical facts still require literal support in the quote.
                if (field == "nct_id" and re.fullmatch(r"NCT\d{8}", str(value))
                        and expected_document == f"nct:{value}"
                        and unit.get("document_id") == expected_document):
                    identity_grounding = {"nct_id": value, "basis": "SOURCE_DOCUMENT_ID",
                                          "document_id": expected_document}
                    continue
                return {"outcome": "QUOTE_INVALID", "reason_codes": [f"TRIAL_{field.upper()}_NOT_GROUNDED"]}
        for field, value in (relation.get("companion_diagnostic") or {}).items():
            if value and not normalized_phrase_in(value, quote):
                return {"outcome": "QUOTE_INVALID", "reason_codes": [f"COMPANION_{field.upper()}_NOT_GROUNDED"]}
    return {"outcome": "ENRICHMENT_V3_ACCEPTED", "reason_codes": [], "quote_valid": True,
            **({"trial_identity_grounding": identity_grounding} if identity_grounding else {})}
