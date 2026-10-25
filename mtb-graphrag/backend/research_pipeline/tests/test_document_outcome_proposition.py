"""Literal cohort outcomes are distinct from single-drug efficacy claims."""
import pytest

from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.tests.test_relation_support_contract_v5 import candidate, observation


def _case(gene="BRAF", variant="V600E", disease="colorectal cancer"):
    target = candidate(disease=disease, gene=gene, alteration=variant, drug=None)
    target["evidence_type"] = "Predictive"
    target["relation_family"] = "EVIDENCE_STATEMENT"
    observed = observation(gene=gene, alteration=variant, drug="agentone and agenttwo", disease=disease)
    observed["observed_relation"]["relation_scope"] = "COMBINATION"
    return target, observed


@pytest.mark.parametrize("gene,variant,disease", [
    ("BRAF", "V600E", "colorectal cancer"),
    ("EGFR", "L858R", "lung cancer"),
])
def test_direct_comparative_cohort_result_is_not_entity_cooccurrence(gene, variant, disease):
    target, observed = _case(gene, variant, disease)
    quote = (f"A combination of agentone and agenttwo resulted in significantly longer overall survival "
             f"and a higher response rate than standard therapy in patients with {disease} with the {gene} {variant} mutation.")
    result = assess_relation_support(target, observed, source_unit_text=quote)
    assert result["text_assertion"] == "DIRECT_ASSERTION", result
    assert result["result"] == "FULL_SUPPORT", result


def test_cohort_outcome_reuses_gene_attached_to_variant_by_source_edge():
    target, observed = _case()
    target["biomarkers"] = [{"type": "Variant", "label": "V600E", "gene": "BRAF"}]
    quote = ("A combination of agentone and agenttwo resulted in longer overall survival "
             "in patients with colorectal cancer with BRAF V600E.")
    result = assess_relation_support(target, observed, source_unit_text=quote)
    assert result["result"] == "FULL_SUPPORT", result


@pytest.mark.parametrize("prefix,suffix", [
    ("A previous study reported that ", ""),
    ("The hypothesis that ", " was rejected."),
    ("", " This conclusion was withdrawn."),
    ("", " in a fictional scenario."),
    ("", " according to a prior report."),
])
def test_comparative_outcome_does_not_escape_epistemic_scope(prefix, suffix):
    target, observed = _case()
    quote = (prefix + "a combination of agentone and agenttwo resulted in longer overall survival "
             "than standard therapy in patients with colorectal cancer with BRAF V600E." + suffix)
    assert assess_relation_support(target, observed, source_unit_text=quote)["result"] != "FULL_SUPPORT"


def test_regimen_result_does_not_support_single_drug_candidate():
    target, observed = _case()
    target["interventions"] = [{"type": "Drug", "label": "agentone"}]
    quote = "A combination of agentone and agenttwo resulted in longer overall survival in patients with colorectal cancer with BRAF V600E."
    assert assess_relation_support(target, observed, source_unit_text=quote)["result"] != "FULL_SUPPORT"


def test_unmatched_intervention_and_comparator_are_not_promoted():
    target, observed = _case()
    for quote in (
        "Standard therapy resulted in longer overall survival than agentone and agenttwo in patients with colorectal cancer with BRAF V600E.",
        "A combination of agentone and agenttwo may result in longer overall survival in patients with colorectal cancer with BRAF V600E.",
    ):
        assert assess_relation_support(target, observed, source_unit_text=quote)["result"] != "FULL_SUPPORT"


@pytest.mark.parametrize("cohort", [
    "colorectal cancer without BRAF V600E",
    "colorectal cancer lacking BRAF V600E",
    "melanoma, unlike patients with colorectal cancer with BRAF V600E",
    "colorectal cancer. BRAF V600E was not evaluated",
    "colorectal cancer excluding BRAF V600E",
    "colorectal cancer with BRAF V600E excluded",
    "colorectal cancer with wild type BRAF rather than V600E",
    "colorectal cancer compared with controls with BRAF V600E",
    "colorectal cancer relative to patients with BRAF V600E",
])
def test_outcome_requires_affirmative_anchors_in_the_same_cohort(cohort):
    target, observed = _case()
    quote = ("A combination of agentone and agenttwo resulted in longer overall survival "
             f"in patients with {cohort}.")
    assert assess_relation_support(target, observed, source_unit_text=quote)["result"] != "FULL_SUPPORT"


@pytest.mark.parametrize("connector", ["except", "but not", "excluding", "allegedly"])
def test_unknown_or_exception_connector_does_not_license_cohort_outcome(connector):
    target, observed = _case()
    quote = ("A combination of agentone and agenttwo resulted in longer overall survival "
             f"{connector} in patients with colorectal cancer with BRAF V600E.")
    assert assess_relation_support(target, observed, source_unit_text=quote)["result"] != "FULL_SUPPORT"
