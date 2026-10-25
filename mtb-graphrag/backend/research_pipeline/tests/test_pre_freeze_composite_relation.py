"""A derived clinical proposition joins only source edges sharing one Evidence ID."""

from backend.research_pipeline.retrieval.composite_evidence import derive_composite_relations
from backend.research_pipeline.retrieval import kg_retrieval
from backend.research_pipeline.retrieval.kg_retrieval import load_candidates
from backend.research_pipeline.dossier.builder import build_relation_aware_report
from backend.research_pipeline.enrichment.relation_support import assess_relation_support


def test_complete_gca4_join_is_unique_traceable_and_does_not_mutate_source() -> None:
    source = load_candidates()
    original_count = len(source)
    derived, excluded = derive_composite_relations(source)
    assert original_count == 46974
    assert len(source) == original_count
    assert len(derived) == 3347
    assert excluded == []
    assert len(set(derived)) == len(derived)
    sample = next(item for item in derived.values()
                  if item["composite_lineage"]["shared_evidence_id"] == "evidence:1005")
    lineage = sample["composite_lineage"]
    assert lineage["profile_candidate_id"] in source
    assert lineage["evidence_drug_candidate_id"] in source
    assert sample["relation_origin"] == "DERIVED_COMPOSITE"
    assert sample["biomarkers"] == source[lineage["profile_candidate_id"]]["biomarkers"]
    assert sample["interventions"] == source[lineage["evidence_drug_candidate_id"]]["interventions"]
    assert set(sample["source_record_ids"]) == (
        set(source[lineage["profile_candidate_id"]]["source_record_ids"])
        | set(source[lineage["evidence_drug_candidate_id"]]["source_record_ids"])
    )


def test_runtime_retrieves_complete_proposition_not_orphan_drug_edge(monkeypatch) -> None:
    all_candidates = load_candidates()
    profile = next(item for item in all_candidates.values()
                   if item.get("semantic_key") == "EVIDENCE_STATEMENT|Evidence:1005")
    drug_edge = next(item for item in all_candidates.values()
                     if item.get("semantic_key", "").startswith("EVIDENCE_DRUG|Evidence:1005|"))
    monkeypatch.setattr(kg_retrieval, "load_candidates", lambda: {
        profile["candidate_id"]: profile,
        drug_edge["candidate_id"]: drug_edge,
    })
    case = {
        "biomarkers": [{"gene": "BRAF", "alteration": "V600E", "assertion_status": "PRESENT"}],
        "disease": {"raw_value": "Melanoma"},
        "target_intervention": {"raw_value": drug_edge["interventions"][0]["label"]},
        "query_intent": "THERAPY_EVALUATION",
    }
    result = kg_retrieval.retrieve(case)
    assert result == kg_retrieval.retrieve(case)
    composite = next(item for item in result["associations"]
                     if item["candidate"].get("relation_origin") == "DERIVED_COMPOSITE")
    assert composite["candidate"]["composite_lineage"]["profile_candidate_id"] == profile["candidate_id"]
    assert composite["candidate"]["composite_lineage"]["evidence_drug_candidate_id"] == drug_edge["candidate_id"]
    assert drug_edge["candidate_id"] not in {item["candidate_id"] for item in result["associations"]}
    assert any(item["candidate_id"] == drug_edge["candidate_id"]
               and "COMPOSED_IN_DERIVED_RELATION" in item["reason_codes"]
               for item in result["excluded_candidates"])
    claim = build_relation_aware_report({}, [composite["candidate"]])["paper_evidence"][0]["claim"]
    assert claim["relation_origin"] == "DERIVED_COMPOSITE"
    assert claim["composite_lineage"]["shared_evidence_id"] == "evidence:1005"
    assert set(claim["source_record_ids"]) == set(composite["candidate"]["source_record_ids"])


def test_real_derived_join_does_not_make_rejected_document_quote_full() -> None:
    derived, _ = derive_composite_relations(load_candidates())
    candidate = next(item for item in derived.values()
                     if item["composite_lineage"]["shared_evidence_id"] == "evidence:1005")
    drug = candidate["interventions"][0]["label"]
    quote = f"The proposition that BRAF V600E showed sensitivity to {drug} was rejected."
    observation = {
        "decision": "QUOTE",
        "observed_relation": {
            "subjects": [{"type": "ALTERATION", "surface_value": "BRAF V600E"}],
            "subject_pairings": [],
            "intervention": drug, "disease": None,
            "effect_direction": "SENSITIVITY_RESPONSE",
            "observed_stance": "SUPPORTS", "relation_scope": "SINGLE",
            "relation_assertion": "RELATION_ASSERTED",
        },
    }
    support = assess_relation_support(candidate, observation, source_unit_text=quote)
    assert support["text_assertion"] == "REJECTED_ASSERTION"
    assert support["result"] != "FULL_SUPPORT"
    record = {
        **observation, "candidate_id": candidate["candidate_id"],
        "document_id": "pmid:123", "source_unit_id": "SU-composite",
        "quote": quote, "quote_valid": True,
        "presentation_state": "VALIDATED_QUOTE",
        "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
        "candidate_support": support,
    }
    report = build_relation_aware_report(
        {"disease": "Melanoma"}, [candidate],
        {candidate["candidate_id"]: {"evidence_records": [record]}},
    )
    claim = report["paper_evidence"][0]["claim"]
    assert claim["status"] != "FULL_SUPPORT"
    assert claim["relation_origin"] == "DERIVED_COMPOSITE"
