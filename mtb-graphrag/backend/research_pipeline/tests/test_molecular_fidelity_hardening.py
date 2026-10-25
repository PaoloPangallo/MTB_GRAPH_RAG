"""Software policy regressions using pinned source concepts, not clinical labels."""
from copy import deepcopy

import pytest

from backend.research_pipeline.terminology import molecular
from backend.research_pipeline.terminology.case_resolution import resolve_case
from backend.research_pipeline.terminology.loader import get_registry
from backend.research_pipeline.retrieval import kg_retrieval as kr
from backend.research_pipeline import data_access


def fusion_case(partners="BCR::ABL1", status="PRESENT"):
    return {"biomarkers": [{"gene": partners, "alteration": "Fusion",
                            "assertion_status": status,
                            "source_spans": [{"quote": partners, "start_offset": 4,
                                              "end_offset": 4 + len(partners)}]}]}


def test_typed_fusion_observation_preserves_partners_spans_and_source_link():
    item = fusion_case()["biomarkers"][0]
    observation = molecular.molecular_observation(item, get_registry())
    assert isinstance(observation, molecular.MolecularObservation)
    assert observation.fusion_partners == ("BCR", "ABL1")
    assert observation.source_spans[0].quote == "BCR::ABL1"
    assert observation.fusion.status == "RESOLVED"
    assert observation.fusion.concept_ids == ("CIViCVariant:1",)
    assert observation.fusion.terms[0].domain == "PROFILE"
    assert molecular.molecular_observation(fusion_case("EGFR::UNKNOWN")["biomarkers"][0], get_registry()).fusion.status == "UNMAPPED"


def test_fusion_compound_is_source_linked_and_requires_both_components():
    registry = get_registry()
    profile = molecular.parse_profile("BCR::ABL1 Fusion AND ABL1 T315I", registry)
    assert profile["status"] == "RESOLVED"
    case = fusion_case()
    case["biomarkers"].append({"gene": "ABL1", "alteration": "T315I", "assertion_status": "PRESENT"})
    row = {"candidate_id": "fusion", "biomarkers": [], "document_identifiers": [{"pmid": "123"}],
           "entity_resolution": {"compound": True, "profile": profile}}
    assert kr._match_candidate(case, row)[0]
    assert not kr._match_candidate(fusion_case(), row)[0]
    case["biomarkers"][0]["assertion_status"] = "NEGATED"
    assert not kr._match_candidate(case, row)[0]


@pytest.mark.parametrize("partners", ["BCR::JAK2", "ABL1::BCR", "EGFR::RAD51"])
def test_fusion_partner_mismatch_does_not_license_same_fusion_id(partners):
    profile = molecular.parse_profile("BCR::ABL1 Fusion", get_registry())
    assert profile["status"] == "RESOLVED"
    resolved = resolve_case(fusion_case(partners), get_registry())
    observations = [x["observation"] for x in resolved["entity_resolution"]["biomarkers"]]
    assert molecular.evaluate_profile(profile["ast"], observations) == "UNKNOWN"


def test_fusion_resolution_is_additive_and_keeps_raw_contract():
    case = fusion_case("EGFR::RAD51")
    before = deepcopy(case)
    resolved = resolve_case(case, get_registry())
    assert case == before and resolved["biomarkers"] == before["biomarkers"]
    record = resolved["entity_resolution"]["biomarkers"][0]
    assert record["gene"]["status"] == "UNMAPPED"
    assert record["variant"]["status"] == "UNMAPPED"
    assert record["observation"]["fusion"]["status"] == "RESOLVED"


def test_unknown_qualifier_is_not_lost_during_gene_alias_matching():
    query = [{"gene": "HER2", "alteration": "expression", "alteration_type": "EXPRESSION"}]
    candidate = [{"gene": "ERBB2", "alteration": "expression", "alteration_type": "AMPLIFICATION"}]
    assert not kr._molecular_compatible(query, candidate)[0]


@pytest.mark.parametrize("updates", [{"alteration_type": "EXPRESSION"},
                                    {"alteration_type": "FUSION", "alteration": "amplification"},
                                    {"gene": "KRAS", "alteration": "EGFR::RAD51 Fusion"}])
def test_conflicting_fusion_qualifiers_do_not_resolve(updates):
    item = {**fusion_case()["biomarkers"][0], **updates}
    observation = molecular.molecular_observation(item, get_registry())
    assert observation.fusion is None or observation.fusion.status != "RESOLVED"


def test_generic_fusion_and_partner_gene_do_not_satisfy_source_fusion():
    profile = molecular.parse_profile("EGFR::RAD51 Fusion", get_registry())
    case = {"biomarkers": [{"gene": "EGFR", "alteration": "Fusion", "assertion_status": "PRESENT"}]}
    resolved = resolve_case(case, get_registry())
    observations = [x["observation"] for x in resolved["entity_resolution"]["biomarkers"]]
    assert molecular.evaluate_profile(profile["ast"], observations) == "UNKNOWN"


@pytest.mark.parametrize("qualifier", ["FUSION", "EXPRESSION", "AMPLIFICATION", "DELETION"])
def test_compound_point_variants_reject_conflicting_qualifiers(qualifier):
    profile = molecular.parse_profile("BRAF V600E AND EGFR L858R", get_registry())
    candidate = {"candidate_id": "qualified-profile", "biomarkers": [],
                 "document_identifiers": [{"pmid": "123"}],
                 "entity_resolution": {"compound": True, "profile": profile}}
    case = {"biomarkers": [
        {"gene": "BRAF", "alteration": "V600E", "alteration_type": qualifier, "assertion_status": "PRESENT"},
        {"gene": "EGFR", "alteration": "L858R", "alteration_type": "MUTATION", "assertion_status": "PRESENT"},
    ]}
    before = deepcopy(case)
    assert not kr._match_candidate(case, candidate)[0]
    assert case == before
    case["biomarkers"][0]["alteration_type"] = "MUTATION"
    assert kr._match_candidate(case, candidate)[0]


def test_conflicting_qualifier_cannot_satisfy_negated_profile():
    profile = molecular.parse_profile("NOT BRAF V600E", get_registry())
    case = {"negated_biomarkers": [{"gene": "BRAF", "alteration": "V600E", "alteration_type": "EXPRESSION"}]}
    resolved = resolve_case(case, get_registry())
    observation = resolved["entity_resolution"]["negated_biomarkers"][0]["observation"]
    assert molecular.evaluate_profile(profile["ast"], [observation]) == "UNKNOWN"


def test_index_does_not_drop_unknown_gene_alternative(monkeypatch):
    row = {"candidate_id": "mixed", "document_identifiers": [{"pmid": "123"}],
           "biomarkers": [{"type": "Gene", "label": "EGFR"}, {"type": "Gene", "label": "LOCAL-X"}]}
    corpus = {"mixed": row}
    monkeypatch.setattr(kr, "load_candidates", lambda: corpus)
    case = {"biomarkers": [{"gene": "LOCAL-X"}]}
    assert kr.retrieve(case)["associations"] == kr.retrieve_exhaustive(case)["associations"]
    assert kr.retrieve(case)["associations"]


def test_retrieval_summary_has_family_accounting_and_snapshot(monkeypatch):
    corpus = {"x": {"candidate_id": "x", "document_identifiers": [{"pmid": "123"}],
                    "biomarkers": [{"type": "Gene", "label": "EGFR"}]}}
    monkeypatch.setattr(kr, "load_candidates", lambda: corpus)
    result = kr.retrieve({"biomarkers": [{"gene": "EGFR"}]})
    summary = result["retrieval_summary"]
    family = result["associations"][0]["relation_family"]
    assert summary["family_accounting"][family] == {"eligible": 1, "matched": 1, "selected": 1, "capped": 0,
                                                     "excluded_reasons": {}}
    assert summary["corpus_snapshot"]["repository_version"] == "4.0"
    assert summary["corpus_snapshot"]["candidate_sha256"]


def test_source_supported_fusions_retrieve_from_pinned_overlay(monkeypatch):
    source = kr.load_candidates()
    wanted = {"BCR::ABL1 Fusion AND ABL1 T315I", "EGFR::RAD51 Fusion"}
    corpus = {cid: row for cid, row in source.items()
              if ((row.get("source_properties") or {}).get("profile") or {}).get("name") in wanted}
    assert corpus
    monkeypatch.setattr(kr, "load_candidates", lambda: corpus)
    for partners in ("BCR::ABL1", "EGFR::RAD51"):
        case = fusion_case(partners)
        case["diseases"] = [{"raw_value": x["label"], "assertion_status": "PRESENT"}
                            for row in corpus.values() for x in row.get("disease") or []]
        if partners == "BCR::ABL1":
            case["biomarkers"].append({"gene": "ABL1", "alteration": "T315I", "assertion_status": "PRESENT"})
        indexed, exhaustive = kr.retrieve(case), kr.retrieve_exhaustive(case)
        assert indexed["associations"] == exhaustive["associations"]
        assert indexed["associations"]
        for association in indexed["associations"]:
            name = association["candidate"]["source_properties"]["profile"]["name"]
            assert name.startswith(partners + " Fusion")


def test_index_preserves_not_profile_and_literal_alternatives(monkeypatch):
    row = {"candidate_id": "not", "document_identifiers": [{"pmid": "123"}],
           "biomarkers": [{"type": "Variant", "gene": "KRAS", "alteration": "G12D"}],
           "entity_resolution": {"compound": True, "profile": molecular.parse_profile("NOT KRAS G12D", get_registry())}}
    corpus = {"not": row}
    monkeypatch.setattr(kr, "load_candidates", lambda: corpus)
    case = {"biomarkers": [{"gene": "EGFR", "assertion_status": "PRESENT"}],
            "negated_biomarkers": [{"gene": "KRAS", "alteration": "G12D"}]}
    indexed, exhaustive = kr.retrieve(case), kr.retrieve_exhaustive(case)
    assert indexed["associations"] == exhaustive["associations"]
    assert indexed["associations"]


def test_runtime_index_and_compositions_are_reused_for_same_corpus():
    source = {"x": {"candidate_id": "x", "semantic_key": "GENE_DRUG|x",
                    "biomarkers": [{"type": "Gene", "label": "EGFR"}]}}
    first = kr._composed_candidates(source)
    second = kr._composed_candidates(source)
    assert first[0] is second[0]
    prepared, index = kr._prepared_and_indexed(first[0], get_registry())
    assert index["by_gene"]["NCBIGene:1956"] == frozenset({"x"})
    assert kr._prepared_and_indexed(second[0], get_registry())[0] is prepared


def test_runtime_snapshot_is_immutable_and_includes_ontology_sources():
    from dataclasses import FrozenInstanceError

    snapshot = data_access.runtime_corpus_snapshot()
    assert data_access.runtime_corpus_snapshot() is snapshot
    assert "snapshot:doid.obo" in snapshot.to_dict()["source_manifest"]
    with pytest.raises(FrozenInstanceError):
        snapshot.repository_version = "invented"
    description = snapshot.to_dict()
    description["source_manifest"].clear()
    assert snapshot.source_manifest


@pytest.mark.parametrize("case_id", [
    "CASE-1-therapy-evaluation-strong-match", "CASE-2-therapy-discovery",
    "CASE-3-partial-incomplete-context", "CASE-4-contradicted-or-resistance",
    "CASE-5-casecontext-mismatch-no-match",
])
def test_indexed_and_exhaustive_parity_across_recorded_case_fixtures(case_id):
    from backend.research_pipeline.replay import _parser_outputs_by_case

    case = _parser_outputs_by_case()[case_id]["case_context_raw"]
    indexed, exhaustive = kr.retrieve(case), kr.retrieve_exhaustive(case)
    assert indexed["associations"] == exhaustive["associations"]
    assert indexed["no_match"] == exhaustive["no_match"]
    assert {x["candidate_id"] for x in indexed["excluded_candidates"]} == {
        x["candidate_id"] for x in exhaustive["excluded_candidates"]}
    for family, counts in indexed["retrieval_summary"]["family_accounting"].items():
        expected = exhaustive["retrieval_summary"]["family_accounting"][family]
        assert {k: counts[k] for k in ("eligible", "matched", "selected", "capped")} == {
            k: expected[k] for k in ("eligible", "matched", "selected", "capped")}
