"""Trial ranking must use declared source anchors, never evaluation targets."""
from copy import deepcopy

from backend.research_pipeline.retrieval import kg_retrieval as kg


def case():
    return {"disease": {"raw_value": "Lung Cancer"},
            "biomarkers": [{"gene": "EGFR", "alteration": None, "assertion_status": "PRESENT"}]}


def trial(cid, genes=()):
    return {"candidate_id": cid, "semantic_key": cid,
            "document_identifiers": [{"nct": "NCT00000001" if cid == "z-specific" else "NCT00000002"}],
            "biomarkers": [], "disease": [], "interventions": [],
            "trial_context": {"genes": list(genes), "conditions": ["Lung Cancer"],
                              "interventions_raw": [], "interventions_normalized": [], "retrieval_only": True}}


def test_declared_trial_gene_counts_as_ranking_anchor():
    candidate = trial("z-specific", ["EGFR"])
    assert kg._match_candidate(case(), candidate)[0]
    _, features = kg._compatibility_score(case(), candidate)
    assert features["gene_exact"]


def test_source_gene_trial_ranks_before_disease_only_even_with_unfavorable_id():
    specific, broad = trial("z-specific", ["EGFR"]), trial("a-broad")
    for candidate in (specific, broad):
        assert kg._match_candidate(case(), candidate)[0]
    _, specific_features = kg._compatibility_score(case(), specific)
    _, broad_features = kg._compatibility_score(case(), broad)
    assert kg._specificity_order_key("z-specific", specific_features) < kg._specificity_order_key("a-broad", broad_features)


def test_source_gene_conflict_remains_a_hard_veto():
    candidate = trial("a-conflict", ["KRAS"])
    matched, reasons = kg._match_candidate(case(), candidate)
    assert not matched
    assert "TRIAL_SOURCE_GENE_NOT_COMPATIBLE" in reasons


def test_query_and_source_are_not_mutated_by_scoring():
    query, candidate = case(), trial("z-specific", ["EGFR"])
    before = deepcopy((query, candidate))
    kg._compatibility_score(query, candidate)
    assert (query, candidate) == before


def test_family_cap_selects_source_gene_anchor_and_uncapped_keeps_all(monkeypatch):
    candidates = {c["candidate_id"]: c for c in [trial("a-broad"), trial("z-specific", ["EGFR"])]}
    monkeypatch.setattr(kg, "load_candidates", lambda: candidates)
    monkeypatch.setattr(kg, "MAX_ASSOCIATIONS_PER_FAMILY", 1)
    bounded = kg.retrieve(case())
    assert [a["candidate_id"] for a in bounded["associations"]] == ["z-specific"]
    assert any(e["candidate_id"] == "a-broad" and "RELATION_FAMILY_CAP_EXCEEDED" in e["reason_codes"]
               for e in bounded["excluded_candidates"])
    monkeypatch.setattr(kg, "MAX_ASSOCIATIONS_PER_FAMILY", None)
    uncapped = kg.retrieve(case())
    assert {a["candidate_id"] for a in uncapped["associations"]} == set(candidates)
