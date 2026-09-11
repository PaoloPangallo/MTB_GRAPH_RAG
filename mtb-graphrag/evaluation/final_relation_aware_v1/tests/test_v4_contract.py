from backend.research_pipeline.determinism.direction_semantics import compare_relation_axes
from backend.research_pipeline.enrichment.canonical_normalizer import entity_relation, normalize_anchor, subject_level_consistency
from backend.research_pipeline.enrichment.prompt_v3 import PROMPT_VERSION, TRANSPORT_VERSION


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
    assert PROMPT_VERSION == "paper-context-enricher-prompt/4.0"
    assert TRANSPORT_VERSION == "paper-context-enrichment-transport/4.0"
