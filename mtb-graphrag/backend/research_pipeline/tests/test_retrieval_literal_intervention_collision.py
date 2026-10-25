"""Same literal drug name may have distinct source IDs, without merging them."""
from backend.research_pipeline.retrieval import kg_retrieval as kg
from backend.research_pipeline.terminology import matching
from backend.research_pipeline.terminology.models import SourceRef, Term
from backend.research_pipeline.terminology.registry import Registry


def registry(*, alias_collision=False):
    source = SourceRef("fixture", "1", "a" * 64, "row:1")
    return Registry([
        Term("INTERVENTION", "rxcui:1", "DRUG A", "PREFERRED", source),
        Term("INTERVENTION", "ncit:C1", "DRUG A", "EXACT" if alias_collision else "PREFERRED", source),
        Term("INTERVENTION", "rxcui:2", "DRUG B", "PREFERRED", source),
    ], "fixture/1")


def test_identical_preferred_drug_names_remain_retrievable_without_merging_concepts():
    reg = registry()
    token = matching.active_registry.set(reg)
    try:
        assert reg.resolve("INTERVENTION", "DRUG A").status == "AMBIGUOUS"
        assert not matching.identity("INTERVENTION", "DRUG A", "DRUG A")
        assert kg._intervention_matches("DRUG A", "drug a")
        assert not kg._intervention_matches("DRUG A", "DRUG B")
        assert reg.resolve("INTERVENTION", "DRUG A").status == "AMBIGUOUS"
    finally:
        matching.active_registry.reset(token)


def test_an_ambiguous_alias_does_not_receive_the_preferred_literal_fallback():
    token = matching.active_registry.set(registry(alias_collision=True))
    try:
        assert not kg._intervention_matches("DRUG A", "DRUG A")
    finally:
        matching.active_registry.reset(token)


def test_literal_collision_is_explicit_in_candidate_retrieval_reasons():
    token = matching.active_registry.set(registry())
    try:
        context = {"query_intent": "THERAPY_EVALUATION", "target_intervention": {"raw_value": "DRUG A"}}
        candidate = {"candidate_id": "C", "biomarkers": [], "disease": [],
                     "interventions": [{"label": "DRUG A"}], "document_identifiers": []}
        matched, reasons = kg._match_candidate(context, candidate)
        assert matched
        assert "INTERVENTION_LITERAL_IDENTITY_AMBIGUOUS_CONCEPT" in reasons
    finally:
        matching.active_registry.reset(token)


def test_trial_uses_same_literal_policy_and_preserves_raw_regimen_precedence():
    token = matching.active_registry.set(registry())
    try:
        assert kg._trial_intervention_matches("DRUG A", {"interventions_raw": ["DRUG A"]})
        assert not kg._trial_intervention_matches("DRUG A", {
            "interventions_raw": ["DRUG A plus DRUG B"], "interventions_normalized": ["DRUG A"],
        })
    finally:
        matching.active_registry.reset(token)


def test_gene_alias_collision_stays_excluded_with_actionable_reason():
    source = SourceRef("fixture", "1", "a" * 64, "row:1")
    reg = Registry([
        Term("GENE", "NCBIGene:1", "AR", "PREFERRED", source),
        Term("GENE", "NCBIGene:2", "AR", "EXACT", source),
    ], "fixture/1")
    token = matching.active_registry.set(reg)
    try:
        context = {"biomarkers": [{"gene": "AR", "alteration": None, "assertion_status": "PRESENT"}]}
        candidate = {"candidate_id": "C", "biomarkers": [{"type": "Gene", "label": "AR"}],
                     "disease": [], "interventions": [], "document_identifiers": []}
        matched, reasons = kg._match_candidate(context, candidate)
        assert not matched
        assert "GENE_IDENTITY_AMBIGUOUS" in reasons
        assert reg.resolve("GENE", "AR").status == "AMBIGUOUS"
    finally:
        matching.active_registry.reset(token)
