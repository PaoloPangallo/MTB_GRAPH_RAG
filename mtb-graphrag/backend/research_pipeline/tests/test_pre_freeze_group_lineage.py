"""One semantic claim must retain every matched GCA4 source member."""

from backend.research_pipeline.dossier.builder import build_relation_aware_report
from backend.research_pipeline.retrieval.kg_retrieval import load_candidates, retrieve


def test_real_brca1_rucaparib_group_preserves_both_source_rows() -> None:
    ids = {"GCA4-0227ddcb67f86282af04c54b", "GCA4-03ffb663a43e047759d99310"}
    case = {
        "biomarkers": [{"gene": "BRCA1", "assertion_status": "PRESENT"}],
        "target_intervention": {"raw_value": "RUCAPARIB"},
        "query_intent": "THERAPY_EVALUATION",
    }
    association = next(item for item in retrieve(case)["associations"]
                       if ids <= set(item["candidate_group_candidate_ids"]))
    assert len(association["candidate_group_candidate_ids"]) >= 2
    members = load_candidates()
    expected_rows = {row for candidate_id in ids for row in members[candidate_id]["source_record_ids"]}
    expected_edges = {edge for candidate_id in ids for edge in members[candidate_id]["edge_ids"]}
    claim = build_relation_aware_report({}, [association["candidate"]])["kg_only_relations"][0]["claim"]
    assert ids <= set(claim["candidate_group_candidate_ids"])
    assert expected_rows <= set(claim["source_record_ids"])
    assert expected_edges <= set(claim["edge_ids"])
    assert len({claim["claim_id"]}) == 1
