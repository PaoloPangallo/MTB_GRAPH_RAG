import json
from pathlib import Path

import pytest

from backend.research_pipeline.retrieval import kg_retrieval
from backend.research_pipeline.retrieval.relation_family import (
    CLINICAL_TRIAL,
    KG_ONLY,
    INVALID_PROVENANCE,
    PAPER_EVIDENCE,
    classify_relation_family,
)


CORPUS = (
    Path(__file__).resolve().parents[3]
    / "benchmarks/mtb_evidence/document_grounded_claims/"
    "graph_candidate_repository/2.0/candidates.jsonl"
)


def _real_examples() -> dict[str, dict]:
    wanted = {
        ("has_evidence_statement", "pmid"): "paper_statement",
        ("associated_with_sensitivity_to", "pmid"): "paper_drug",
        ("trial_association", "nct", "drug"): "trial_drug",
        ("trial_association", "nct", "gene"): "trial_gene",
        ("gene_drug_interaction", "none"): "kg_drug",
        ("has_companion_diagnostic", "none"): "kg_diagnostic",
    }
    found: dict[str, dict] = {}
    with CORPUS.open(encoding="utf-8") as handle:
        for line in handle:
            candidate = json.loads(line)
            identifiers = candidate.get("document_identifiers") or []
            kinds = {key for item in identifiers for key in ("pmid", "nct") if item.get(key)}
            if candidate.get("predicate") == "trial_association" and "nct" in kinds:
                kind = "gene" if candidate.get("biomarkers") else "drug" if candidate.get("interventions") else "other"
                key = (candidate.get("predicate"), "nct", kind)
            else:
                key = (candidate.get("predicate"), next(iter(kinds), "none"))
            name = wanted.get(key)
            if name and name not in found:
                found[name] = candidate
            if len(found) == len(wanted):
                break
    return found


@pytest.fixture(scope="module")
def real_examples():
    examples = _real_examples()
    assert set(examples) == {
        "paper_statement", "paper_drug", "trial_drug", "trial_gene", "kg_drug", "kg_diagnostic"
    }
    return examples


def test_real_evidence_statement_is_paper(real_examples):
    assert classify_relation_family(real_examples["paper_statement"]) == PAPER_EVIDENCE


def test_real_evidence_to_drug_is_paper(real_examples):
    assert classify_relation_family(real_examples["paper_drug"]) == PAPER_EVIDENCE


def test_real_trial_drug_is_clinical_trial(real_examples):
    assert classify_relation_family(real_examples["trial_drug"]) == CLINICAL_TRIAL
    assert real_examples["trial_drug"]["document_identifiers"][0]["nct"].startswith("NCT")


def test_real_trial_gene_or_trial_association_is_clinical_trial(real_examples):
    assert classify_relation_family(real_examples["trial_gene"]) == CLINICAL_TRIAL


def test_real_gene_drug_interaction_is_kg_only(real_examples):
    assert classify_relation_family(real_examples["kg_drug"]) == KG_ONLY


def test_real_companion_diagnostic_is_kg_only(real_examples):
    assert classify_relation_family(real_examples["kg_diagnostic"]) == KG_ONLY


@pytest.mark.parametrize("candidate", [{}, {"document_identifiers": None}, {"document_identifiers": []}])
def test_missing_document_identifiers_are_kg_only(candidate):
    assert classify_relation_family(candidate) == KG_ONLY


def test_source_type_does_not_create_document_provenance():
    assert classify_relation_family({"source_type": "PubMed"}) == KG_ONLY


def test_pmid_and_nct_are_rejected_explicitly():
    assert classify_relation_family(
        {"document_identifiers": [{"pmid": "1", "nct": "NCT1"}]}
    ) == INVALID_PROVENANCE


def test_live_retrieval_admits_real_kg_only_without_identifier(monkeypatch, real_examples):
    target = real_examples["kg_drug"]
    unrelated = real_examples["kg_diagnostic"]
    monkeypatch.setattr(kg_retrieval, "load_candidates", lambda: {
        target["candidate_id"]: target,
        unrelated["candidate_id"]: unrelated,
    })

    def match(case_context, candidate):
        return (candidate["candidate_id"] == target["candidate_id"], ["MATCH"])

    monkeypatch.setattr(kg_retrieval, "_match_candidate", match)
    result = kg_retrieval.retrieve({"query_intent": "THERAPY_DISCOVERY"})

    assert [item["candidate_id"] for item in result["associations"]] == [target["candidate_id"]]
    assert result["associations"][0]["candidate"] ["document_identifiers"] == []
    assert classify_relation_family(result["associations"][0]["candidate"]) == KG_ONLY
    assert unrelated["candidate_id"] in {item["candidate_id"] for item in result["excluded_candidates"]}


def test_live_retrieval_admits_real_trial_without_calling_provider(monkeypatch, real_examples):
    target = real_examples["trial_drug"]
    monkeypatch.setattr(kg_retrieval, "load_candidates", lambda: {target["candidate_id"]: target})
    monkeypatch.setattr(kg_retrieval, "_match_candidate", lambda *_: (True, ["MATCH"]))

    result = kg_retrieval.retrieve({"query_intent": "THERAPY_DISCOVERY"})

    assert result["associations"][0]["candidate_id"] == target["candidate_id"]
    assert classify_relation_family(result["associations"][0]["candidate"]) == CLINICAL_TRIAL


def _case(*, gene=None, alteration=None, intervention=None, disease="colorectal cancer"):
    return {
        "disease": {"normalized_value": disease},
        "biomarkers": ([{
            "gene": gene,
            "alteration": alteration,
            "normalized_value": " ".join(value for value in (gene, alteration) if value),
        }] if gene or alteration else []),
        "target_intervention": ({"normalized_value": intervention} if intervention else None),
        "query_intent": None,
    }


def _candidate(*, gene=None, alteration=None, intervention=None, disease="Colorectal Cancer"):
    biomarkers = []
    if gene:
        biomarkers.append({"label": gene, "type": "Gene"})
    if alteration:
        biomarkers.append({"label": alteration, "type": "Variant"})
    return {
        "candidate_id": "synthetic",
        "disease": ([{"label": disease}] if disease else []),
        "biomarkers": biomarkers,
        "interventions": ([{"label": intervention, "type": "Drug"}] if intervention else []),
        "document_identifiers": [],
    }


def test_disease_match_does_not_override_unrelated_explicit_gene():
    matched, _ = kg_retrieval._match_candidate(
        _case(gene="ZZTK9", alteration="P44R"), _candidate(gene="KRAS", alteration="G12D")
    )
    assert matched is False


def test_different_gene_cannot_match_generic_candidate_alteration():
    matched, _ = kg_retrieval._match_candidate(
        _case(gene="ZZTK9", alteration="P44R alteration"),
        _candidate(gene="TP53", alteration="ALTERATION"),
    )
    assert matched is False


def test_same_gene_is_relevant_even_when_candidate_has_no_explicit_alteration():
    matched, _ = kg_retrieval._match_candidate(
        _case(gene="KRAS", alteration="G12D"), _candidate(gene="KRAS")
    )
    assert matched is True


def test_same_gene_with_conflicting_alteration_is_rejected_without_other_anchor():
    matched, _ = kg_retrieval._match_candidate(
        _case(gene="KRAS", alteration="G12D"), _candidate(gene="KRAS", alteration="G13D")
    )
    assert matched is False


def test_intervention_match_does_not_override_explicit_molecular_conflict():
    matched, reasons = kg_retrieval._match_candidate(
        _case(gene="ZZTK9", alteration="P44R", intervention="panitumumab"),
        _candidate(gene="KRAS", intervention="panitumumab"),
    )
    assert matched is False
    assert "BIOMARKER_NOT_COMPATIBLE" in reasons


def test_real_trial_drug_is_reachable_by_intervention(real_examples):
    matched, _ = kg_retrieval._match_candidate(
        _case(intervention="EMB-01", disease="metastatic gastrointestinal carcinoid tumor"), real_examples["trial_drug"]
    )
    assert matched is True


def test_real_trial_gene_is_reachable_by_gene(real_examples):
    candidate = real_examples["trial_gene"]
    gene = next(item["label"] for item in candidate["biomarkers"] if item.get("type") == "Gene")
    matched, _ = kg_retrieval._match_candidate(
        _case(gene=gene, disease="metastatic gastrointestinal carcinoid tumor"), candidate
    )
    assert matched is True


def test_real_kg_only_gene_drug_is_reachable_by_gene_or_drug(real_examples):
    candidate = real_examples["kg_drug"]
    gene = candidate["biomarkers"][0]["label"]
    matched_by_gene, _ = kg_retrieval._match_candidate(_case(gene=gene), candidate)
    drug = candidate["interventions"][0]["label"]
    matched_by_drug, _ = kg_retrieval._match_candidate(_case(intervention=drug), candidate)
    assert matched_by_gene is True
    assert matched_by_drug is True
