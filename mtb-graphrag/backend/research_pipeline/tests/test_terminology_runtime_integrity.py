from pathlib import Path
import pytest
from backend.research_pipeline.documents.trial_context import TrialContextIndex
from backend.research_pipeline.terminology.loader import get_registry


def test_runtime_uses_reviewed_identifier_release_without_label_collision(monkeypatch):
    monkeypatch.delenv("RESEARCH_PIPELINE_TERMINOLOGY_MANIFEST", raising=False)
    registry = get_registry()
    assert registry.version == "terminology/1.2"
    result = registry.resolve("DISEASE", "Mantle Cell Lymphoma")
    assert result.status == "RESOLVED"
    assert result.concept_ids == ("DOID:0050746",)
    assert any(m.get("subject") == "DOID:50746" and m.get("object") == "DOID:0050746"
               and m.get("predicate") == "SOURCE_IDENTIFIER_RECONCILIATION"
               for m in registry.mappings)


def test_unreferenced_dna_coordinate_does_not_gain_protein_identity():
    registry = get_registry()
    result = registry.resolve("VARIANT", "c.1799T>A", gene_id="NCBIGene:673")
    assert result.status == "UNMAPPED"
    assert "REFERENCE_REQUIRED" in result.reasons
    assert registry.resolve("VARIANT", "NM_004333.4:c.1799T>A", gene_id="NCBIGene:673").concept_ids == ("CIViCVariant:12",)


def test_trial_file_hashes_are_computed_once_per_source(tmp_path, monkeypatch):
    filename = tmp_path / "edges_trial_gene.csv"
    filename.write_text("nct_id,gene_symbol\nNCT00000001,BRAF\nNCT00000002,EGFR\n", encoding="utf-8")
    original = Path.read_bytes
    reads = []
    def counted(path):
        reads.append(path)
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", counted)
    index = TrialContextIndex.from_directory(tmp_path)
    assert len(reads) == 1
    assert index.lookup("NCT00000001").provenance["source_file_sha256"] == index.lookup("NCT00000002").provenance["source_file_sha256"]


def test_ontology_obsolete_ids_are_not_reintroduced_by_csv():
    registry = get_registry()
    assert registry.resolve("DISEASE", "DOID:6496").status == "UNMAPPED"
    assert registry.resolve("DISEASE", "Extraskeletal Myxoid Chondrosarcoma").concept_ids == ("DOID:4549",)
    assert registry.resolve("DISEASE", "DOID:715").status == "UNMAPPED"


def test_predicted_consequence_cannot_license_confirmed_quote_identity():
    registry = get_registry()
    result = registry.compare("VARIANT", "V600E", "p.(Val600Glu)", gene_id="NCBIGene:673")
    assert result["relation"] == "PREDICTION_SCOPE_MISMATCH"
    # Retrieval still links the partial concept, while carrying its epistemic scope.
    assert registry.resolve("VARIANT", "p.(Val600Glu)", gene_id="NCBIGene:673").concept_ids == ("CIViCVariant:12",)


def test_document_grounding_uses_the_observed_verified_alias():
    from backend.research_pipeline.tests.test_document_verification import _candidate, _structural
    from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import _reader_observation, _source_unit
    candidate = _candidate()
    quote = "EGFR p.Leu858Arg showed sensitivity to erlotinib in lung cancer."
    observed = _reader_observation(candidate, [_source_unit(quote)])["enrichment"]
    for subject in observed["observed_relation"]["subjects"]:
        if subject["type"] == "ALTERATION":
            subject["surface_value"] = "p.Leu858Arg"
    assert _structural(quote, candidate=candidate, observed=observed)["structural_status"] == "PASS"


def test_resolved_boolean_profiles_handle_explicit_negative_projection():
    from backend.research_pipeline.terminology.case_resolution import resolve_case
    from backend.research_pipeline.terminology.molecular import parse_profile
    from backend.research_pipeline.retrieval.kg_retrieval import _match_candidate
    registry = get_registry()
    case = resolve_case({"disease": {"raw_value": "lung cancer"},
                         "biomarkers": [{"gene": "BRAF", "alteration": "V600E", "assertion_status": "PRESENT"}],
                         "negated_biomarkers": [{"gene": "EGFR", "alteration": "L858R"}]}, registry)
    candidate = {"disease": [{"label": "lung cancer"}], "biomarkers": [
        {"type": "Variant", "gene": "BRAF", "alteration": "V600E"},
        {"type": "Variant", "gene": "EGFR", "alteration": "L858R"}], "interventions": []}
    for expression in ("BRAF V600E OR EGFR L858R", "BRAF V600E AND NOT EGFR L858R"):
        row = {**candidate, "entity_resolution": {"compound": True, "profile": parse_profile(expression, registry)}}
        assert _match_candidate(case, row)[0], expression
    row = {**candidate, "entity_resolution": {"compound": True, "profile": parse_profile("BRAF V600E AND EGFR L858R", registry)}}
    assert not _match_candidate(case, row)[0]


def test_generic_document_support_uses_verified_alias_without_losing_grounding():
    from backend.research_pipeline.tests.test_document_verification import _candidate
    from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import _reader_observation, _source_unit
    from backend.research_pipeline.enrichment.relation_support import assess_relation_support
    candidate = _candidate()
    candidate["relation_family"] = "EVIDENCE_STATEMENT"
    quote = "EGFR p.Leu858Arg showed sensitivity to erlotinib in lung cancer."
    observed = _reader_observation(candidate, [_source_unit(quote)])["enrichment"]
    for subject in observed["observed_relation"]["subjects"]:
        if subject["type"] == "ALTERATION":
            subject["surface_value"] = "p.Leu858Arg"
    observed["observed_relation"]["subject_pairings"] = [{"gene": "EGFR", "alteration": "p.Leu858Arg"}]
    assert assess_relation_support(candidate, observed, source_unit_text=quote)["result"] == "FULL_SUPPORT"


@pytest.mark.parametrize("additional", ["KRAS G12C", "EGFR p.Thr790Met"])
def test_alias_does_not_hide_additional_molecular_subjects(additional):
    from backend.research_pipeline.tests.test_document_verification import _candidate, _structural
    from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import _reader_observation, _source_unit
    candidate = _candidate()
    quote = f"EGFR p.Leu858Arg and {additional} showed sensitivity to erlotinib in lung cancer."
    observed = _reader_observation(candidate, [_source_unit(quote)])["enrichment"]
    for subject in observed["observed_relation"]["subjects"]:
        if subject["type"] == "ALTERATION":
            subject["surface_value"] = "p.Leu858Arg"
    result = _structural(quote, candidate=candidate, observed=observed)
    assert result["structural_status"] == "UNRESOLVED"
    assert "ADDITIONAL_VARIANT_IN_PROPOSITION" in result["structural_reason_codes"]
    from backend.research_pipeline.enrichment.relation_support import assess_relation_support
    assert assess_relation_support(candidate, observed, source_unit_text=quote)["result"] != "FULL_SUPPORT"
