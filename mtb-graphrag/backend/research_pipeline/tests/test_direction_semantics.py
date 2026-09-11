from backend.research_pipeline.determinism.direction_semantics import (
    compare_relation_axes, derive_expected_effect, derive_source_stance,
)
from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.determinism.gates import candidate_direction_consistency


def _candidate(predicate, *, stance="Supports", significance=None, direction=None):
    c = {"predicate": predicate, "direction": direction or stance}
    if significance is not None or stance is not None:
        c["source_properties"] = {"evidence": {
            "evidence_direction": stance, "significance": significance,
        }}
    return c


def _observed(direction, evidence_type="PREDICTIVE"):
    return {"decision": "QUOTE", "observed_direction": direction,
            "observed_evidence_type": evidence_type}


def test_has_evidence_supports_resistance_uses_effect_axis():
    c = _candidate("has_evidence_statement", significance="Resistance")
    assert derive_source_stance(c) == "SUPPORTS"
    assert derive_expected_effect(c) == "RESISTANCE"
    assert assess_relation_support(c, _observed("RESISTANCE"))["fields"]["direction"] == "CONFIRMED"


def test_has_evidence_supports_sensitivity_conflicts_with_expected_resistance():
    c = _candidate("has_evidence_statement", significance="Resistance")
    assert assess_relation_support(c, _observed("SENSITIVITY_RESPONSE"))["fields"]["direction"] == "CONTRADICTORY"


def test_missing_significance_is_conservative():
    c = _candidate("has_evidence_statement", significance=None)
    assert assess_relation_support(c, _observed("RESISTANCE"))["fields"]["direction"] == "NOT_CONFIRMED"


def test_associated_direction_comparisons():
    r = _candidate("associated_with_resistance_to", direction="Resistance")
    s = _candidate("associated_with_sensitivity_to", direction="Sensitivity/Response")
    assert assess_relation_support(r, _observed("RESISTANCE"))["fields"]["direction"] == "CONFIRMED"
    assert assess_relation_support(r, _observed("SENSITIVITY_RESPONSE"))["fields"]["direction"] == "CONTRADICTORY"
    assert assess_relation_support(s, _observed("SENSITIVITY_RESPONSE"))["fields"]["direction"] == "CONFIRMED"
    assert assess_relation_support(s, _observed("RESISTANCE"))["fields"]["direction"] == "CONTRADICTORY"


def test_nonclinical_significance_does_not_become_effect():
    c = _candidate("has_evidence_statement", significance="Poor Outcome")
    assert derive_expected_effect(c) == "UNKNOWN"
    assert assess_relation_support(c, _observed("RESISTANCE"))["fields"]["direction"] == "NOT_CONFIRMED"


def test_shared_semantics_returns_same_axis_interpretation():
    c = _candidate("has_evidence_statement", significance="Resistance")
    assert compare_relation_axes(c["predicate"], derive_source_stance(c),
                                 derive_expected_effect(c), "RESISTANCE") == "CONSISTENT"
    assert candidate_direction_consistency(c, "RESISTANCE") == "CONSISTENT"


def test_composite_observed_relation_cannot_promote_single_subject_gca():
    c = _candidate("associated_with_sensitivity_to", direction="Sensitivity/Response")
    c["biomarkers"] = [{"type": "Gene", "label": "PTEN"}]
    observed = _observed("SENSITIVITY_RESPONSE")
    observed["observed_relation"] = {
        "subjects": [{"type": "biomarker", "value": "EGFRvIII"}, {"type": "gene", "value": "PTEN"}],
        "intervention": "erlotinib", "effect_direction": "SENSITIVITY_RESPONSE",
        "relation_scope": "COEXPRESSION", "evidence_scope": "PREDICTIVE",
    }
    result = assess_relation_support(c, observed)
    assert result["result"] == "PARTIAL_SUPPORT"
    assert result["relation_composition"] == "COMPOSITE_MISMATCH"


def _with_context(observed, level, claim):
    observed["observed_relation"] = {
        "subjects": [], "intervention": None, "effect_direction": observed["observed_direction"],
        "relation_scope": "SINGLE", "evidence_scope": "PREDICTIVE",
        "evidence_context": {"subject_level": level, "claim_type": claim},
    }
    return observed


def test_individual_observed_response_cannot_fulfill_predictive_scope():
    c = _candidate("has_evidence_statement", significance="Sensitivity/Response")
    c["evidence_scope"] = "Predictive"
    result = assess_relation_support(c, _with_context(_observed("SENSITIVITY_RESPONSE"), "INDIVIDUAL", "OBSERVED_RESPONSE"))
    assert result["result"] == "PARTIAL_SUPPORT"


def test_cohort_predictive_association_remains_eligible():
    c = _candidate("has_evidence_statement", significance="Sensitivity/Response")
    c["evidence_scope"] = "Predictive"
    o = _with_context(_observed("SENSITIVITY_RESPONSE"), "COHORT", "PREDICTIVE_ASSOCIATION")
    o["observed_relation"]["subjects"] = [{"type": "gene", "value": "JAK2"}]
    c["biomarkers"] = [{"type": "Gene", "label": "JAK2"}]
    result = assess_relation_support(c, o)
    assert result["result"] in {"FULL_SUPPORT", "PARTIAL_SUPPORT"}


def test_unknown_evidence_context_is_conservative():
    c = _candidate("has_evidence_statement", significance="Sensitivity/Response")
    c["evidence_scope"] = "Predictive"
    result = assess_relation_support(c, _with_context(_observed("SENSITIVITY_RESPONSE"), "UNKNOWN", "UNKNOWN"))
    assert result["result"] == "PARTIAL_SUPPORT"
