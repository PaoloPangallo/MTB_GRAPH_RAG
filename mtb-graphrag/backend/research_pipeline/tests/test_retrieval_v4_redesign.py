from __future__ import annotations

from backend.research_pipeline import data_access
from backend.research_pipeline.retrieval import kg_retrieval as kr


def _candidate(*, gene=None, variant=None, alteration_type=None, drug=None,
               disease=None, nct=None, diagnostic=None, diagnostic_gene=None):
    biomarkers = []
    if gene:
        biomarkers.append({"type": "Gene", "label": gene})
    if variant:
        biomarkers.append({
            "type": "Variant", "label": variant, "gene": gene,
            "alteration_type": alteration_type,
        })
    row = {
        "candidate_id": "GCA4-TEST",
        "relation_family": "GENE_DRUG",
        "semantic_key": "TEST|semantic",
        "biomarkers": biomarkers,
        "interventions": ([{"type": "Drug", "label": drug}] if drug else []),
        "disease": ([{"type": "Disease", "label": disease}] if disease else []),
        "document_identifiers": ([{"nct": nct}] if nct else []),
    }
    if diagnostic:
        row["companion_diagnostic"] = {
            "name": diagnostic,
            "identifier": diagnostic,
            "associated_gene": diagnostic_gene or gene,
            "associated_drug": drug,
        }
    return row


def _case(*, gene=None, alteration=None, alteration_type=None, drug=None,
          disease=None, diseases=None, assertion_status="PRESENT", nct=None,
          diagnostic=None, diagnostic_gene=None):
    return {
        "disease": {"raw_value": disease} if disease else None,
        "diseases": ([{"value": {"raw_value": value}, "assertion_status": "PRESENT", "clinical_role": "PRIMARY"}
                      for value in (diseases or [])]),
        "biomarkers": ([{
            "gene": gene, "alteration": alteration,
            "alteration_type": alteration_type,
            "assertion_status": assertion_status,
        }] if gene or alteration else []),
        "target_interventions": ([{"raw_value": drug}] if drug else []),
        "trial_mentions": ([{"nct_id": nct}] if nct else []),
        "companion_diagnostic_mentions": ([{
            "name": diagnostic, "identifier": diagnostic,
            "associated_gene": diagnostic_gene or gene,
            "associated_drug": drug,
        }] if diagnostic else []),
    }


def test_negative_only_case_fails_closed():
    matched, reasons = kr._match_candidate(
        _case(gene="KRAS", alteration="G12D", assertion_status="NEGATED"),
        _candidate(gene="KRAS"),
    )
    assert matched is False
    assert "NO_POSITIVE_ANCHOR" in reasons


def test_molecular_identifiers_use_exact_boundaries():
    assert kr._molecular_term_matches("ALK", "AL") is False
    assert kr._molecular_term_matches("EGFR", "EGFR2") is False
    assert kr._molecular_term_matches("EGFR", "EGFR") is True


def test_variant_specificity_does_not_match_different_variant():
    case = _case(gene="KRAS", alteration="G12C", alteration_type="MUTATION", disease="Colorectal Cancer")
    candidate = _candidate(gene="KRAS", variant="G13D", alteration_type="MUTATION", disease="Colorectal Cancer")
    assert kr._match_candidate(case, candidate)[0] is False


def test_alteration_type_mismatch_is_rejected():
    case = _case(gene="HER2", alteration="HER2", alteration_type="AMPLIFICATION")
    candidate = _candidate(gene="HER2", variant="HER2", alteration_type="MUTATION")
    assert kr._match_candidate(case, candidate)[0] is False


def test_multiple_diseases_use_any_active_context():
    case = _case(disease="Lung cancer", diseases=["Lung cancer", "Melanoma"])
    candidate = _candidate(disease="Melanoma")
    assert kr._match_candidate(case, candidate)[0] is True


def test_nct_is_exact_when_explicit():
    case = _case(gene="EGFR", nct="NCT01234567")
    same = _candidate(gene="EGFR", nct="NCT01234567")
    other = _candidate(gene="EGFR", nct="NCT99999999")
    assert kr._match_candidate(case, same)[0] is True
    assert kr._match_candidate(case, other)[0] is False


def test_explicit_companion_diagnostic_restricts_candidate():
    case = _case(gene="ERBB2", drug="trastuzumab", diagnostic="Diagnostic A", diagnostic_gene="ERBB2")
    same = _candidate(gene="ERBB2", drug="trastuzumab", diagnostic="Diagnostic A", diagnostic_gene="ERBB2")
    other = _candidate(gene="ERBB2", drug="trastuzumab", diagnostic="Diagnostic B", diagnostic_gene="ERBB2")
    assert kr._match_candidate(case, same)[0] is True
    assert kr._match_candidate(case, other)[0] is False


def test_semantic_grouping_preserves_all_candidate_ids():
    rows = [
        {"candidate_id": "a", "semantic_key": "same", "relation_family": "GENE_DRUG"},
        {"candidate_id": "b", "semantic_key": "same", "relation_family": "GENE_DRUG"},
        {"candidate_id": "c", "semantic_key": "other", "relation_family": "GENE_DRUG"},
    ]
    groups = kr._group_matched_records(rows)
    assert [group["candidate_group_candidate_ids"] for group in groups] == [["a", "b"], ["c"]]


def test_runtime_remains_v4():
    assert data_access.GRAPH_CANDIDATE_REPOSITORY_VERSION == "4.0"


def test_molecular_profile_adapter_preserves_variant_level():
    raw = {
        "materializer_version": "gca-materializer/4.0",
        "subject": {"id": "MolecularProfile:1", "label": "KRAS G13D", "type": "MolecularProfile"},
        "object": {},
        "context": {},
        "source_properties": {"profile": {"name": "KRAS G13D"}},
    }
    adapted = data_access.adapt_candidate_for_runtime(raw)
    assert adapted["biomarkers"] == [{
        "id": "MolecularProfile:1",
        "label": "KRAS G13D",
        "type": "Variant",
        "gene": "KRAS",
        "alteration": "G13D",
        "specificity_level": "VARIANT",
        "alteration_type": "UNKNOWN",
    }]


def test_all_v4_families_are_searchable_from_v4_candidates():
    rows = list(kr.load_candidates().values())
    families = {row["relation_family"]: row for row in rows}
    assert set(families) == {
        "EVIDENCE_STATEMENT", "EVIDENCE_DRUG", "GENE_DRUG", "TRIAL_DRUG",
        "TRIAL_GENE", "DRUG_COMPANION_DIAGNOSTIC", "COMPANION_DIAGNOSTIC_GENE",
    }
    for row in families.values():
        candidate = dict(row)
        candidate["source_properties"] = None
        biomarker = next(iter(candidate.get("biomarkers") or []), None)
        intervention = next(iter(candidate.get("interventions") or []), None)
        disease = next(iter(candidate.get("disease") or []), None)
        case = {
            "disease": {"raw_value": disease["label"]} if disease else None,
            "biomarkers": ([{"gene": biomarker.get("gene"),
                              "alteration": biomarker.get("alteration") or biomarker.get("label"),
                              "assertion_status": "PRESENT"}]
                            if biomarker else []),
            "target_interventions": ([{"raw_value": intervention["label"]}] if intervention else []),
        }
        # A source label is not necessarily an unambiguous query identity:
        # cross-namespace drug collisions must abstain rather than pick one ID.
        from backend.research_pipeline.terminology.loader import get_registry
        ambiguity = intervention and get_registry().resolve("INTERVENTION", intervention["label"]).status == "AMBIGUOUS"
        from backend.research_pipeline.terminology.case_resolution import disease_context
        ambiguity = ambiguity or (disease and disease_context(disease["label"], get_registry())["status"] == "AMBIGUOUS")
        assert kr._match_candidate(case, candidate)[0] is (not bool(ambiguity)), row["relation_family"]
