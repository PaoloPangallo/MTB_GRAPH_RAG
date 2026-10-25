from backend.research_pipeline.retrieval import kg_retrieval as kr


def case(*, disease=None, gene="KRAS", alteration="G12D", drug="panitumumab"):
    return {
        "disease": {"normalized_value": disease} if disease else None,
        "biomarkers": [{"gene": gene, "alteration": alteration}] if gene or alteration else [],
        "target_intervention": {"normalized_value": drug} if drug else None,
        "query_intent": "THERAPY_EVALUATION",
    }


def candidate(cid, *, disease=None, gene="KRAS", alteration="G12D", drug="panitumumab"):
    biomarkers = []
    if gene:
        biomarkers.append({"type": "Gene", "label": gene})
    if alteration:
        biomarkers.append({"type": "Variant", "label": alteration, "gene": gene})
    return {
        "candidate_id": cid,
        "disease": ([{"type": "Disease", "label": disease}] if disease else []),
        "biomarkers": biomarkers,
        "interventions": ([{"type": "Drug", "label": drug}] if drug else []),
        "document_identifiers": [{"pmid": cid[-1] + "001"}],
    }


def test_exact_gene_variant_matches():
    assert kr._match_candidate(case(), candidate("GCA-1"))[0] is True


def test_same_alteration_wrong_explicit_gene_is_excluded():
    assert kr._match_candidate(case(gene="EGFR"), candidate("GCA-1"))[0] is False


def test_gene_level_candidate_survives_variant_specific_query():
    assert kr._match_candidate(case(), candidate("GCA-1", alteration=None))[0] is True


def test_missing_disease_does_not_exclude_candidate():
    assert kr._match_candidate(case(disease=None), candidate("GCA-1", disease=None))[0] is True


def test_multiple_compatible_candidates_are_returned(monkeypatch):
    corpus = {"GCA-1": candidate("GCA-1"), "GCA-2": candidate("GCA-2", alteration=None)}
    monkeypatch.setattr(kr, "load_candidates", lambda: corpus)
    result = kr._retrieve(case(), use_frozen_bundles=False)
    assert [x["candidate_id"] for x in result["associations"]] == ["GCA-1", "GCA-2"]


def test_exact_intervention_is_ranked_before_less_specific_trials_then_cap_applies(monkeypatch):
    monkeypatch.setattr(kr, "MAX_ASSOCIATIONS_PER_FAMILY", 3)
    def trial(cid, nct, drug=None):
        value = candidate(cid, disease=None, gene="ERBB2", alteration=None, drug=drug)
        value["predicate"] = "trial_association"
        value["subject"] = {"type": "ClinicalTrial", "label": nct}
        value["document_identifiers"] = [{"nct": nct}]
        return value

    corpus = {
        "GCA-A": trial("GCA-A", "NCT00000001"),
        "GCA-B": trial("GCA-B", "NCT00000002"),
        "GCA-C": trial("GCA-C", "NCT00000003"),
        "GCA-Z": trial("GCA-Z", "NCT00000004", "trastuzumab"),
    }
    monkeypatch.setattr(kr, "load_candidates", lambda: corpus)
    result = kr._retrieve(case(disease=None, gene="ERBB2", alteration=None, drug="trastuzumab"), use_frozen_bundles=False)
    selected = [item["candidate_id"] for item in result["associations"]]
    assert selected[0] == "GCA-Z"
    assert len(selected) == kr.MAX_ASSOCIATIONS_PER_FAMILY
    assert len(result["excluded_candidates"]) == 1
