import json

from backend.research_pipeline.determinism.direction_semantics import compare_relation_axes
from backend.research_pipeline.enrichment.canonical_normalizer import entity_relation, normalize_anchor, subject_level_consistency
from backend.research_pipeline.enrichment.prompt_v3 import PROMPT_VERSION, TRANSPORT_VERSION
from backend.research_pipeline.enrichment.enricher_v3 import _transport


def test_punctuation_variant_normalizes_without_collapsing_distinct_variant():
    assert entity_relation("PIK3CA) E545K", "PIK3CA E545K") == "IDENTICAL"
    assert entity_relation("F877L", "F876L") == "DIFFERENT"


def test_identity_categories_are_oriented_candidate_to_source():
    assert entity_relation("BRCA1", "BRCA1/2") == "SOURCE_BROADER"
    assert entity_relation("BRCA1/2", "BRCA1") == "SOURCE_NARROWER"


def test_subject_level_unresolved_is_not_inconsistent():
    assert subject_level_consistency("COHORT", "KRAS mutations correlate with response.") == "UNRESOLVED"
    assert subject_level_consistency("COHORT", "A cell line was treated.") == "INCONSISTENT"


def test_typed_anchor_keeps_surface_and_adds_canonical_value():
    anchor = normalize_anchor({"type": "ALTERATION", "surface_value": "PIK3CA) E545K", "linked_gene": "PIK3CA"})
    assert anchor == {"type": "ALTERATION", "surface_value": "PIK3CA) E545K", "canonical_value": "pik3ca e545k", "linked_gene": "PIK3CA"}


def test_explicit_stance_never_becomes_a_clinical_effect():
    assert compare_relation_axes("has_evidence_statement", "SUPPORTS", "RESISTANCE", "RESISTANCE", "SUPPORTS") == "CONSISTENT"
    assert compare_relation_axes("has_evidence_statement", "SUPPORTS", "RESISTANCE", "SENSITIVITY_RESPONSE", "SUPPORTS") == "CONFLICTING"
    assert compare_relation_axes("has_evidence_statement", "SUPPORTS", "UNKNOWN", "UNKNOWN", "DOES_NOT_SUPPORT") == "CONFLICTING"


def test_v4_versions_are_explicit():
    assert PROMPT_VERSION == "paper-context-enricher-prompt/4.1"
    assert TRANSPORT_VERSION == "paper-context-enrichment-transport/4.1"


def _args(decision, **overrides):
    args = {
        "decision": decision, "source_unit_id": None, "quote": None,
        "observed_relation": None, "notes": None, "abstain_reason": None,
    }
    args.update(overrides)
    return args


def test_transport_accepts_quote_with_canonical_relation_and_null_abstain_reason():
    relation = {"disease": None, "subjects": [], "intervention": None,
                "observed_stance": "SUPPORTS", "effect_direction": "UNKNOWN",
                "relation_scope": "SINGLE", "evidence_scope": "UNKNOWN",
                "evidence_context": {"subject_level": "UNKNOWN", "claim_type": "UNKNOWN"}}
    outcome, parsed, reasons = _transport(200, {"choices": [{"message": {"tool_calls": [{
        "function": {"name": "submit_paper_relation_observation", "arguments": json.dumps(_args(
            "QUOTE", source_unit_id="SU-1", quote="literal", observed_relation=relation))}}]}}]}, None)
    assert outcome == "V3_TRANSPORT_VALID"
    assert parsed["observed_relation"]["subjects"] == []
    assert reasons == []


def test_transport_accepts_abstain_with_null_payload_and_reason():
    outcome, parsed, reasons = _transport(200, {"choices": [{"message": {"tool_calls": [{
        "function": {"name": "submit_paper_relation_observation", "arguments": json.dumps(
            _args("ABSTAIN", abstain_reason="NO_RELEVANT_EVIDENCE"))}}]}}]}, None)
    assert outcome == "V3_TRANSPORT_VALID"
    assert parsed["observed_relation"] is None
    assert reasons == []


def test_transport_rejects_crossed_quote_and_abstain_fields():
    outcome, _, reasons = _transport(200, {"choices": [{"message": {"tool_calls": [{
        "function": {"name": "submit_paper_relation_observation", "arguments": json.dumps(
            _args("QUOTE", source_unit_id="SU-1", quote="literal", abstain_reason="OTHER"))}}]}}]}, None)
    assert outcome == "INVALID_TOOL_ARGUMENTS"
    assert reasons == ["OBSERVED_RELATION_REQUIRED_FOR_QUOTE"]


def test_transport_accepts_legacy_wire_anchor_spelling_as_compatibility():
    relation = {"disease": None, "subjects": [{"type": "gene_variant", "value": "PIK3CA E545K"}],
                "intervention": None, "observed_stance": "SUPPORTS", "effect_direction": "UNKNOWN",
                "relation_scope": "SINGLE", "evidence_scope": "UNKNOWN",
                "evidence_context": {"subject_level": "UNKNOWN", "claim_type": "UNKNOWN"}}
    outcome, parsed, _ = _transport(200, {"choices": [{"message": {"tool_calls": [{
        "function": {"name": "submit_paper_relation_observation", "arguments": json.dumps(_args(
            "QUOTE", source_unit_id="SU-1", quote="literal", observed_relation=relation))}}]}}]}, None)
    assert outcome == "V3_TRANSPORT_VALID"
    assert parsed["observed_relation"]["subjects"][0]["type"] == "ALTERATION"
    assert parsed["observed_relation"]["subjects"][0]["surface_value"] == "PIK3CA E545K"
