"""Real GCA4 diagnostic metadata must survive the KG-only dossier projection."""

from backend.research_pipeline.dossier.builder import build_relation_aware_report
from backend.research_pipeline.retrieval.kg_retrieval import load_candidates


def test_real_diagnostic_context_preserves_device_and_associations() -> None:
    candidate = load_candidates()["GCA4-a4d422f60e6939250da27a02"]
    entry = build_relation_aware_report({}, [candidate])["kg_only_relations"][0]
    context = entry["diagnostic_context"]
    assert context["device_id"] == "cdx:ABBOTTREALTIMEI:IDH1:IVOSIDENIB"
    assert context["device_name"] == "Abbott RealTime IDH1  (Abbott Molecular, Inc.)"
    assert context["gene"] == "IDH1"
    assert context["drug"] == "Ivosidenib"
    assert context["platform_type"] == "PCR"
    assert context["specimen_types"] == "Bone marrow;Peripheral Blood"
    assert entry["verification_status"] == "KG_ONLY"
    assert entry["claim"]["source_record_ids"] == candidate["source_record_ids"]
