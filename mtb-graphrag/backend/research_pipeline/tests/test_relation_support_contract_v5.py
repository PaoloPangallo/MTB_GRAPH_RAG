from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.orchestrator import _accepted_for_gates


def candidate(*, disease="melanoma", gene="BRAF", alteration="V600E", drug="vemurafenib",
              predicate="associated_with_sensitivity_to"):
    return {
        "candidate_id": "GCA-T",
        "disease": ([{"type": "Disease", "label": disease}] if disease else []),
        "biomarkers": [
            *([{"type": "Gene", "label": gene}] if gene else []),
            *([{"type": "Variant", "label": alteration}] if alteration else []),
        ],
        "interventions": ([{"type": "Drug", "label": drug}] if drug else []),
        "predicate": predicate,
    }


def observation(*, gene="BRAF", alteration="V600E", drug="vemurafenib",
                direction="SENSITIVITY_RESPONSE", relation=True, decision="QUOTE",
                disease=None, stance="SUPPORTS", assertion="RELATION_ASSERTED",
                pairings=None):
    relation_value = None
    if relation:
        relation_value = {
            "subjects": [
                *([{"type": "GENE", "surface_value": gene}] if gene else []),
                *([{"type": "ALTERATION", "surface_value": alteration}] if alteration else []),
            ],
            "intervention": drug,
            "disease": disease,
            "effect_direction": direction,
            "observed_stance": stance,
            "relation_scope": "SINGLE",
            "relation_assertion": assertion,
            "subject_pairings": pairings or ([{"gene": gene, "alteration": alteration}]
                                               if gene and alteration else []),
        }
    return {"decision": decision, "observed_relation": relation_value}


def test_exact_relation_is_full_without_repeating_contextual_disease():
    result = assess_relation_support(
        candidate(), observation(disease=None),
        source_unit_text="BRAF V600E showed sensitivity to vemurafenib.",
    )
    assert result["result"] == "FULL_SUPPORT"
    assert result["predicates"]["relation_full_specificity"] is True


def test_gene_level_relation_for_variant_target_is_partial():
    result = assess_relation_support(
        candidate(), observation(alteration=None),
        source_unit_text="BRAF showed sensitivity to vemurafenib.",
    )
    assert result["result"] == "NO_SUPPORT"
    assert result["fields"]["alteration"] == "NOT_CONFIRMED"


def test_co_mentions_without_asserted_relation_are_no_support():
    observed = {
        "decision": "QUOTE", "observed_relation": None,
        "observed_gene": "BRAF", "observed_alteration": "V600E",
        "observed_drug": "vemurafenib", "observed_direction": "SENSITIVITY_RESPONSE",
    }
    assert assess_relation_support(candidate(), observed)["result"] == "NO_SUPPORT"


def test_only_gene_is_no_support():
    result = assess_relation_support(
        candidate(), observation(alteration=None, drug=None, direction=None)
    )
    assert result["result"] == "NO_SUPPORT"


def test_opposite_direction_is_contradictory():
    result = assess_relation_support(
        candidate(), observation(direction="RESISTANCE"),
        source_unit_text="BRAF V600E showed resistance to vemurafenib.",
    )
    assert result["result"] == "CONTRADICTORY"


def test_invalid_observation_is_unverifiable():
    assert assess_relation_support(candidate(), {"decision": "ABSTAIN"})["result"] == "UNVERIFIABLE"


def test_unknown_direction_is_not_contradiction():
    result = assess_relation_support(
        candidate(), observation(direction="UNKNOWN"),
        source_unit_text="BRAF V600E showed sensitivity to vemurafenib.",
    )
    assert result["result"] == "PARTIAL_SUPPORT"
    assert result["fields"]["direction"] == "NOT_CONFIRMED"


def test_does_not_support_cannot_be_full_support_or_reach_gate():
    result = assess_relation_support(
        candidate(),
        observation(stance="DOES_NOT_SUPPORT"),
        source_unit_text="BRAF V600E did not support response to vemurafenib.",
    )
    assert result["result"] in {"CONTRADICTORY", "NO_SUPPORT"}
    assert _accepted_for_gates("ENRICHMENT_V3_ACCEPTED", result) is None


def test_entity_cooccurrence_is_not_relation_support():
    result = assess_relation_support(
        candidate(),
        observation(assertion="ENTITY_CO_OCCURRENCE"),
        source_unit_text="BRAF and V600E were measured; vemurafenib was included in the panel.",
    )
    assert result["result"] in {"NO_SUPPORT", "UNVERIFIABLE"}


def test_cross_pair_is_not_full_support():
    result = assess_relation_support(
        {
            **candidate(),
            "biomarkers": [
                {"type": "Gene", "label": "EGFR"},
                {"type": "Variant", "label": "L858R"},
                {"type": "Gene", "label": "KRAS"},
                {"type": "Variant", "label": "G12C"},
            ],
        },
        observation(gene="EGFR", alteration="G12C",
                    pairings=[{"gene": "EGFR", "alteration": "G12C"}]),
        source_unit_text="EGFR G12C and KRAS L858R were evaluated with vemurafenib.",
    )
    assert result["result"] != "FULL_SUPPORT"
