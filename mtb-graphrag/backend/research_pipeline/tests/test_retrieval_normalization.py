import copy

import pytest

from backend.research_pipeline.retrieval import kg_retrieval as kr


def query(disease="metastatic colorectal cancer", alteration="V600E mutation"):
    return {"disease": disease, "biomarkers": [{"gene": "BRAF", "alteration": alteration}],
            "query_intent": "THERAPY_DISCOVERY"}


def candidate(disease="Colorectal Cancer", alteration="V600E"):
    return {"candidate_id": "normalization-test", "disease": [{"label": disease}],
            "biomarkers": [{"type": "Variant", "gene": "BRAF", "alteration": alteration}],
            "document_identifiers": [{"pmid": "27325282"}], "interventions": []}


@pytest.mark.parametrize("alteration", ["V600E mutation", "p.V600E", "p.(Val600Glu)", "Val600Glu", "v600e"])
def test_equivalent_protein_notations_enter_paper(alteration):
    assert kr._match_candidate(query(alteration=alteration), candidate())[0]


@pytest.mark.parametrize("disease", ["metastatic colorectal cancer", "advanced colorectal cancer",
                                      "recurrent colorectal cancer", "locally advanced colorectal cancer"])
def test_qualified_case_can_retrieve_unspecified_disease(disease):
    assert kr._match_candidate(query(disease, "V600E"), candidate())[0]


@pytest.mark.parametrize("q,c", [("colorectal cancer", "metastatic colorectal cancer"),
                                 ("metastatic colorectal cancer", "recurrent colorectal cancer"),
                                 ("small cell lung cancer", "non-small cell lung cancer"),
                                 ("colorectal cancer", "colorectal adenocarcinoma")])
def test_specific_disease_constraints_are_not_invented(q, c):
    assert not kr._match_candidate(query(q, "V600E"), candidate(c))[0]


@pytest.mark.parametrize("alteration", ["V600K", "V600", "V600E AND EZH2 Y646F", "c.1799T>A", "V600E deletion",
                                      "p.(Val600Glu", "Val600Glu)", "(V600E", "V600E)"])
def test_different_or_ambiguous_variants_remain_excluded(alteration):
    assert not kr._match_candidate(query("colorectal cancer", alteration), candidate())[0]


@pytest.mark.parametrize("q,c", [("c.1799T>A", "c.1799T=A"), ("V600E?", "V600E"),
                                 ("V600E+K601E", "V600E/K601E")])
def test_unknown_notation_preserves_meaningful_symbols(q, c):
    assert not kr._match_candidate(query("colorectal cancer", q), candidate(alteration=c))[0]


def test_equivalent_notation_is_used_in_ranking():
    _, features = kr._compatibility_score(query(alteration="p.Val600Glu"), candidate())
    assert features["alteration_exact"]
    assert not features["disease_exact"]
    assert features["disease_scope_compatible"]


@pytest.mark.parametrize("gene,raw,canonical,disease", [
    ("EGFR", "p.Leu858Arg mutation", "L858R", "non-small cell lung cancer"),
    ("KRAS", "p.Gly12Asp", "G12D", "pancreatic cancer"),
    ("PIK3CA", "His1047Arg mutation", "H1047R", "breast cancer"),
])
def test_normalization_is_shared_across_genes_and_diseases(gene, raw, canonical, disease):
    q, c = query("metastatic " + disease, raw), candidate(disease, canonical)
    q["biomarkers"][0]["gene"] = gene
    c["biomarkers"][0]["gene"] = gene
    assert kr._match_candidate(q, c)[0]
    c["biomarkers"][0]["gene"] = "OTHER"
    assert not kr._match_candidate(q, c)[0]


def test_normalized_negated_variant_still_vetoes_retrieval():
    q = query("colorectal cancer", "V600E")
    q["negated_biomarkers"] = [{"gene": "BRAF", "alteration": "p.Val600Glu"}]
    assert not kr._match_candidate(q, candidate())[0]


def test_normalization_trace_preserves_input_and_corpus(monkeypatch):
    q, c = query(), candidate()
    originals = copy.deepcopy((q, c))
    monkeypatch.setattr(kr, "load_candidates", lambda: {c["candidate_id"]: c})
    result = kr._retrieve(q, use_frozen_bundles=False)
    assert len(result["associations"]) == 1
    trace = result["associations"][0]["retrieval_trace"]["normalization"]
    assert trace["version"]
    assert trace["query_diseases"][0]["concept_ids"] == ("DOID:9256",)
    assert trace["query_diseases"][0]["residual_context"] == "metastatic"
    assert trace["query_biomarkers"][0]["variant"]["concept_ids"] == ("CIViCVariant:12",)
    assert (q, c) == originals
