import json

from backend.research_pipeline.determinism.direction_semantics import compare_relation_axes
from backend.research_pipeline.enrichment.canonical_normalizer import entity_relation, normalize_anchor, subject_level_consistency
from backend.research_pipeline.enrichment.prompt_v3 import PROMPT_VERSION, TOOL_SCHEMA, TRANSPORT_VERSION
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
    assert PROMPT_VERSION == "paper-context-enricher-prompt/4.5"
    assert TRANSPORT_VERSION == "paper-context-enrichment-transport/4.5"


def _args(decision, **overrides):
    args = {"decision": decision, "source_unit_id": None, "quote": None,
            "disease": None, "intervention": None,
            "subject_1_type": None, "subject_1_value": None, "subject_1_linked_gene": None,
            "subject_2_type": None, "subject_2_value": None, "subject_2_linked_gene": None,
            "subject_3_type": None, "subject_3_value": None, "subject_3_linked_gene": None,
            "subject_4_type": None, "subject_4_value": None, "subject_4_linked_gene": None,
            "observed_stance": None, "effect_direction": None, "relation_scope": None,
            "subject_level": None, "claim_type": None, "notes": None, "abstain_reason": None}
    args.update(overrides)
    return args


def _call(args):
    return _transport(200, {"choices": [{"message": {"tool_calls": [{
        "function": {"name": "submit_paper_relation_observation", "arguments": json.dumps(args)}}]}}]}, None)


def _complete_quote(**overrides):
    args = _args("QUOTE", source_unit_id="SU-1", quote="literal",
                 observed_stance="SUPPORTS", effect_direction="RESISTANCE",
                 relation_scope="SINGLE", subject_level="COHORT",
                 claim_type="PREDICTIVE_ASSOCIATION")
    args.update(overrides)
    return args


def test_flat_minimal_quote_builds_unknown_canonical_relation():
    outcome, parsed, reasons = _call(_args("QUOTE", source_unit_id="SU-X", quote="literal"))
    assert outcome == "V3_TRANSPORT_VALID"
    assert reasons == []
    assert {key: parsed["observed_relation"][key] for key in (
        "disease", "subjects", "intervention", "observed_stance", "effect_direction",
        "relation_scope", "evidence_context")
    } == {
        "disease": None, "subjects": [], "intervention": None,
        "observed_stance": "UNKNOWN", "effect_direction": "UNKNOWN",
        "relation_scope": "UNKNOWN",
        "evidence_context": {"subject_level": "UNKNOWN", "claim_type": "UNKNOWN"},
    }


def test_flat_complete_quote_preserves_two_subjects_in_order():
    args = _complete_quote(subject_1_type="ALTERATION", subject_1_value="EGFRvIII",
                           subject_2_type="GENE", subject_2_value="PTEN",
                           effect_direction="SENSITIVITY_RESPONSE", relation_scope="COEXPRESSION",
                           subject_level="CELL_MODEL", claim_type="FUNCTIONAL_EFFECT")
    outcome, parsed, reasons = _call(args)
    assert outcome == "V3_TRANSPORT_VALID"
    assert reasons == []
    assert parsed["observed_relation"]["subjects"] == [
        {"type": "ALTERATION", "surface_value": "EGFRvIII", "canonical_value": "egfrviii"},
        {"type": "GENE", "surface_value": "PTEN", "canonical_value": "pten"},
    ]
    assert parsed["observed_relation"]["relation_scope"] == "COEXPRESSION"


def test_flat_four_subject_slots_are_supported():
    args = _complete_quote()
    for i in range(1, 5):
        args[f"subject_{i}_type"] = "BIOMARKER"
        args[f"subject_{i}_value"] = f"B{i}"
    outcome, parsed, _ = _call(args)
    assert outcome == "V3_TRANSPORT_VALID"
    assert len(parsed["observed_relation"]["subjects"]) == 4


def test_subject_slot_requires_type_and_value_as_pair():
    outcome, _, reasons = _call(_args("QUOTE", source_unit_id="SU-1", quote="literal", subject_1_type="GENE"))
    assert outcome == "INVALID_TOOL_ARGUMENTS"
    assert "SUBJECT_SLOT_INVALID" in reasons


def test_subject_slot_rejects_whitespace_only_values():
    outcome, _, reasons = _call(_args("QUOTE", source_unit_id="SU-1", quote="literal",
                                      subject_1_type="GENE", subject_1_value="   "))
    assert outcome == "INVALID_TOOL_ARGUMENTS"
    assert "SUBJECT_SLOT_INVALID" in reasons


def test_transport_accepts_valid_abstain_with_reason():
    outcome, parsed, reasons = _call(_args("ABSTAIN", abstain_reason="NO_RELEVANT_EVIDENCE"))
    assert outcome == "V3_TRANSPORT_VALID"
    assert parsed["observed_relation"] is None
    assert reasons == []


def test_transport_fills_omitted_optional_fields_for_abstain():
    outcome, parsed, reasons = _call({"decision": "ABSTAIN", "abstain_reason": "NO_RELEVANT_EVIDENCE"})
    assert outcome == "V3_TRANSPORT_VALID"
    assert parsed["quote"] is None
    assert parsed["source_unit_id"] is None
    assert parsed["observed_relation"] is None
    assert reasons == []


def test_transport_rejects_wrong_semantic_axes_and_field_names():
    for overrides in ({"relation_scope": "PREDICTIVE"}, {"effect_direction": "SUPPORTS"},
                      {"observed_stance": "RESISTANCE"}, {"claim_type": "PREDICTIVE"},
                      {"gene": "KRAS"}, {"clinical_effect": "RESISTANCE"}, {"subject": "KRAS"}):
        outcome, _, reasons = _call(_complete_quote(**overrides))
        assert outcome == "INVALID_TOOL_ARGUMENTS"
        assert "NESTED_SCHEMA_VALIDATION_FAILED" in reasons


def test_transport_rejects_nested_observed_relation_wire_object():
    outcome, _, reasons = _call(_args("QUOTE", source_unit_id="SU-1", quote="literal", observed_relation={}))
    assert outcome == "INVALID_TOOL_ARGUMENTS"
    assert "NESTED_SCHEMA_VALIDATION_FAILED" in reasons


def test_transport_rejects_missing_quote_source_unit():
    outcome, _, reasons = _call(_args("QUOTE", quote="literal"))
    assert outcome == "INVALID_TOOL_ARGUMENTS"
    assert "QUOTE_FIELDS_REQUIRED_FOR_QUOTE" in reasons


def test_transport_rejects_crossed_quote_and_abstain_fields():
    outcome, _, reasons = _call(_args("QUOTE", source_unit_id="SU-1", quote="literal", abstain_reason="OTHER"))
    assert outcome == "INVALID_TOOL_ARGUMENTS"
    assert "ABSTAIN_REASON_PRESENT_DESPITE_QUOTE" in reasons
    outcome, _, reasons = _call(_args("ABSTAIN", abstain_reason="OTHER", quote="literal"))
    assert outcome == "INVALID_TOOL_ARGUMENTS"
    assert "ABSTAIN_FIELDS_PRESENT" in reasons


def test_transport_rejects_invalid_abstain_reason_and_decision():
    outcome, _, reasons = _call(_args("ABSTAIN", abstain_reason="unknown reason"))
    assert outcome == "INVALID_TOOL_ARGUMENTS"
    assert "NESTED_SCHEMA_VALIDATION_FAILED" in reasons
    outcome, _, reasons = _call(_args("SUPPORTS"))
    assert outcome == "INVALID_TOOL_ARGUMENTS"
    assert "NESTED_SCHEMA_VALIDATION_FAILED" in reasons


def test_legacy_fields_are_not_visible_in_tool_schema():
    forbidden = {"observed_relation", "evidence_context", "evidence_scope", "observed_gene", "observed_alteration",
                 "observed_drug", "observed_direction", "observed_evidence_type"}
    assert forbidden.isdisjoint(TOOL_SCHEMA["properties"])


def test_transport_derives_legacy_fields_after_valid_canonical_relation():
    outcome, parsed, reasons = _call(_complete_quote())
    assert outcome == "V3_TRANSPORT_VALID"
    assert reasons == []
    assert parsed["observed_gene"] == ""
    assert parsed["observed_direction"] == "RESISTANCE"
    assert parsed["observed_evidence_type"] == "PREDICTIVE"
