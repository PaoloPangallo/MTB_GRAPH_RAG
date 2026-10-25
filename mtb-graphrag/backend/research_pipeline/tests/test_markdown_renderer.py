from backend.research_pipeline.narrative.markdown_renderer import render_dossier_markdown
import pytest


def test_render_dossier_includes_all_branch_sections_and_provenance():
    dossier = {
        "case_summary": {"case_id": "CASE-1", "disease": "CRC", "gene": "KRAS", "variant": "G12D", "intervention": "PANITUMUMAB"},
        "paper_evidence": [{"candidate_id": "P", "relation": "resistance", "document_id": "PMID:1", "quote_valid": True, "quote": "validated quote", "quote_source_unit_id": "SU-1", "support_level": "PARTIAL_SUPPORT", "support_fields": {"gene": "SUPPORTED"}}],
        "clinical_trials": [{"candidate_id": "T", "nct_id": "NCT12345678", "title": "Trial", "conditions": ["CRC"], "interventions": [{"name": "PANITUMUMAB"}], "phase": ["PHASE2"], "status": "RECRUITING", "eligibility_status": "NOT_EVALUATED", "evidence_interpretation": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"}],
        "kg_only_relations": [{"candidate_id": "K", "subject": {"label": "KRAS"}, "relation": "gene_drug_interaction", "object": {"label": "PANITUMUMAB"}, "source_database": "MyCancerGenome", "verification_status": "KG_ONLY", "document_provenance": "NOT_AVAILABLE"}],
        "limitations": ["DOCUMENT_PROVENANCE_NOT_AVAILABLE"],
    }
    output = render_dossier_markdown(dossier, None, "STRUCTURED_DOSSIER_FALLBACK", {"status": "FAIL"})
    assert "## Evidenza dai paper" in output
    assert "## Trial clinici" in output
    assert "## Relazioni Knowledge Graph" in output
    assert "PMID:1" in output
    assert "NCT12345678" in output
    assert "NOT_EVALUATED" in output
    assert "MyCancerGenome" in output


def test_render_dossier_includes_verified_narrative_when_available():
    output = render_dossier_markdown(
        {"case_summary": {"case_id": "CASE-2"}, "paper_evidence": [], "clinical_trials": [], "kg_only_relations": [], "limitations": []},
        {"narrative_summary": "Sintesi leggibile", "candidate_narratives": [{"candidate_id": "GCA-1", "text": "Testo della candidate"}], "limitations_summary": "Limitazione", "closing_note": "Nota"},
        "VERIFIED_NARRATIVE", {"status": "PASS"},
    )
    assert "## Sintesi narrativa: fedeltà al dossier verificata" in output
    assert 'non la correttezza scientifica' in output
    assert "Sintesi leggibile" in output
    assert "Testo della candidate" in output
    assert "VERIFIED_NARRATIVE" in output


def test_paper_details_render_each_distinct_evidence_by_state_with_provenance():
    full = {"evidence_id": "E-FULL", "support_result": "FULL_SUPPORT", "paper_id": "PMID:11",
            "document_id": "PMID:11", "source_unit_id": "SU-11", "quote_valid": True,
            "quote": "The variant predicts response.", "provenance": {"source": "PubMed"}}
    partial = {"evidence_id": "E-PART", "support_result": "PARTIAL_SUPPORT", "paper_id": "PMID:12",
               "document_id": "PMID:12", "source_unit_id": "SU-12", "quote_valid": True,
               "quote": "Activity was observed in cell lines.",
               "document_verification": {"support_limitation": {"experimental_scope": {"literal_span": "in cell lines"}}}}
    contradiction = {"evidence_id": "E-CONTRA", "support_result": "CONTRADICTORY", "paper_id": "PMID:13",
                     "document_id": "PMID:13", "source_unit_id": "SU-13", "quote_valid": True,
                     "quote": "No response was observed."}
    dossier = {"paper_evidence": [{"candidate_id": "C1", "relation": "predictive", "document_id": "PMID:11",
                                   "support_level": "PARTIAL_SUPPORT", "quote_valid": False,
                                   "accepted_evidence_records": [full, partial, contradiction, dict(partial)]}],
               "clinical_trials": [], "kg_only_relations": [], "limitations": []}
    output = render_dossier_markdown(dossier)
    assert "E-FULL" in output and "FULL_SUPPORT" in output and "PMID:11" in output and "SU-11" in output
    assert "E-PART" in output and "PARTIAL_SUPPORT" in output and "in cell lines" in output
    assert "E-CONTRA" in output and "CONTRADICTORY" in output
    assert output.count("E-PART") == 1


def test_conflicting_duplicate_evidence_id_is_visible_and_not_deduplicated_silently():
    first = {"evidence_id": "E-COLLIDE", "support_result": "PARTIAL_SUPPORT", "paper_id": "PMID:1",
             "document_id": "PMID:1", "source_unit_id": "SU-1", "quote_valid": True,
             "quote": "Observed in cells."}
    second = {**first, "quote": "Observed in patients."}
    output = render_dossier_markdown({"paper_evidence": [{"candidate_id": "C", "accepted_evidence_records": [first, second]}],
                                      "clinical_trials": [], "kg_only_relations": [], "limitations": []})
    assert "Evidence ID duplicato con contenuti discordanti (E-COLLIDE)" in output
    assert "Observed in cells." in output
    assert "Observed in patients." in output


def test_distinct_quotes_from_one_source_unit_are_not_described_as_independent():
    common = {"support_result": "FULL_SUPPORT", "paper_id": "PMID:7", "document_id": "PMID:7",
              "source_unit_id": "SU-7", "quote_valid": True}
    output = render_dossier_markdown({"paper_evidence": [{"candidate_id": "C", "accepted_evidence_records": [
        {**common, "evidence_id": "E-7A", "quote": "First statement."},
        {**common, "evidence_id": "E-7B", "quote": "Second statement."},
    ]}], "clinical_trials": [], "kg_only_relations": [], "limitations": []})
    assert "stessa SourceUnit; non costituisce una conferma indipendente" in output


def test_legacy_raw_records_with_rejections_are_visible_only_as_unreconciled():
    output = render_dossier_markdown({"paper_evidence": [{
        "candidate_id": "C", "document_id": "PMID:8",
        "evidence_records": [{"evidence_id": "E-RAW", "paper_id": "PMID:8",
                              "source_unit_id": "SU-8", "support_result": "UNVERIFIABLE"}],
        "rejected_evidence": [{"evidence_id": "E-REJECT", "document_id": "PMID:9",
                               "source_unit_id": "SU-9", "reason": "QUOTE_NOT_VALID"}],
    }], "clinical_trials": [], "kg_only_relations": [], "limitations": []})
    assert "E-REJECT" in output
    assert "E-RAW" in output
    assert "Record storici non riconciliati (non ammessi)" in output
    assert "NON RICONCILIATO / NON AMMESSO" in output
    assert "##### UNVERIFIABLE" not in output


def test_legacy_raw_records_without_partition_are_not_rendered_as_admitted():
    output = render_dossier_markdown({"paper_evidence": [{
        "candidate_id": "C", "evidence_records": [{
            "evidence_id": "E-OLD", "paper_id": "PMID:10", "source_unit_id": "SU-10",
            "quote_valid": True, "quote": "Old quote", "support_result": "FULL_SUPPORT",
        }],
    }], "clinical_trials": [], "kg_only_relations": [], "limitations": []})
    assert "Record storici non riconciliati (non ammessi)" in output
    assert "E-OLD" in output and "NON RICONCILIATO / NON AMMESSO" in output
    assert "##### FULL_SUPPORT" not in output
    assert "Old quote" not in output


@pytest.mark.parametrize("accepted_records", [None, []])
def test_empty_acceptance_partition_never_falls_back_to_raw_records(accepted_records):
    output = render_dossier_markdown({"paper_evidence": [{
        "candidate_id": "C", "accepted_evidence_records": accepted_records,
        "evidence_records": [{"evidence_id": "E-RAW-EMPTY", "paper_id": "PMID:12",
                              "source_unit_id": "SU-12", "quote_valid": True,
                              "quote": "Raw support must remain unadmitted.",
                              "support_result": "FULL_SUPPORT"}],
    }], "clinical_trials": [], "kg_only_relations": [], "limitations": []})
    assert "E-RAW-EMPTY" in output
    assert "NON RICONCILIATO / NON AMMESSO" in output
    assert "##### FULL_SUPPORT" not in output
    assert "Raw support must remain unadmitted." not in output


def test_markdown_separates_scientific_state_from_verification_failure():
    output = render_dossier_markdown({"paper_evidence": [{
        "candidate_id": "C", "accepted_evidence_records": [{
            "evidence_id": "E-TECH", "paper_id": "PMID:11", "source_unit_id": "SU-11",
            "support_result": "UNVERIFIABLE", "verification_status": "TECHNICAL_ERROR",
            "final_admission": "TECHNICAL_ERROR", "verification_reason_codes": ["PROVIDER_TIMEOUT"],
        }],
    }], "clinical_trials": [], "kg_only_relations": [], "limitations": []})
    assert "##### UNVERIFIABLE" in output
    assert "**Verifica:** TECHNICAL_ERROR; motivi: PROVIDER_TIMEOUT" in output


def test_markdown_exposes_compact_document_and_unit_ids_without_changing_summary():
    output = render_dossier_markdown({
        "paper_evidence": [{"candidate_id": "P-1", "document_id": "DOC-9", "requested_document_id": "PMID:9",
                            "accepted_evidence_records": [{
                                "evidence_id": "E-9", "paper_id": "PMID:9", "document_id": "DOC-9",
                                "source_unit_id": "SU-9-2", "support_result": "PARTIAL_SUPPORT",
                                "quote_valid": True, "quote": "Observed in vitro.",
                                "document_verification": {"support_limitation": "Preclinical only"},
                                "verification_reason_codes": ["LIMITED_CONTEXT"],
                            }]}],
        "clinical_trials": [{"candidate_id": "T-1", "nct_id": "NCT00000009", "document_ids": ["DOC-NCT-9"],
                             "source_unit_ids": ["TRIAL-SU-3"], "trial_resolution_status": "AVAILABLE",
                             "provenance_status": "TRIAL_RECORD_RESOLVED"}],
    })
    assert "**PMID:** PMID:9" in output and "**Documento:** DOC-9" in output and "**SourceUnit:** SU-9-2" in output
    assert "**NCT:** NCT00000009" in output and "Documento: DOC-NCT-9" in output and "TRIAL-SU-3" in output
    assert "Preclinical only" in output and "LIMITED_CONTEXT" in output
    assert "**Stato:** PARTIAL_SUPPORT" in output


@pytest.mark.parametrize(
    "public_id,document_id,internal_id,expected_label",
    [
        ("pmid:26243863", "pmcid:PMC4527087", "live:GCA4-EVIDENCE:pmid:26243863", "**PMID:** PMID:26243863"),
        ("pmid:19223544", "pmid:19223544", "live:GCA4-KRAS:pmid:19223544", "**PMID:** PMID:19223544"),
    ],
)
def test_markdown_renders_validated_public_source_identity_separately_from_internal_id(
    public_id, document_id, internal_id, expected_label,
):
    output = render_dossier_markdown({
        "paper_evidence": [{"candidate_id": "P-1", "accepted_evidence_records": [{
            "evidence_id": "E-1", "paper_id": internal_id, "document_id": document_id,
            "public_source_identity": public_id, "source_unit_id": "SU-1",
            "support_result": "UNVERIFIABLE",
        }]}],
        "clinical_trials": [], "kg_only_relations": [], "limitations": [],
    })

    assert expected_label in output
    assert f"**Documento:** {document_id}" in output
    assert f"**PMID:** {internal_id}" not in output


def test_markdown_flags_same_source_unit_even_when_public_and_resolved_ids_differ():
    output = render_dossier_markdown({
        "paper_evidence": [{"candidate_id": "P-1", "accepted_evidence_records": [
            {"evidence_id": "E-1", "paper_id": "live:GCA4:pmid:77",
             "document_id": "pmcid:PMC77", "public_source_identity": "pmid:77",
             "source_unit_id": "SU-77-1", "support_result": "FULL_SUPPORT"},
            {"evidence_id": "E-2", "paper_id": "live:GCA4:pmid:77",
             "document_id": "pmcid:PMC77", "public_source_identity": "pmid:77",
             "source_unit_id": "SU-77-1", "support_result": "FULL_SUPPORT"},
        ]}],
        "clinical_trials": [], "kg_only_relations": [], "limitations": [],
    })

    assert output.count("stessa SourceUnit; non costituisce una conferma indipendente") == 2


def test_legacy_internal_paper_id_is_not_rendered_as_a_public_identifier():
    output = render_dossier_markdown({
        "paper_evidence": [{"candidate_id": "P-OLD", "evidence_records": [{
            "evidence_id": "E-OLD", "paper_id": "live:GCA4-EVIDENCE:pmid:26243863",
            "document_id": "doc-internal-26243863", "source_unit_id": "SU-OLD",
            "support_result": "FULL_SUPPORT",
        }]}],
        "clinical_trials": [], "kg_only_relations": [], "limitations": [],
    })

    assert "**PMID/documento:**" not in output
    assert "**Identità fonte:** non disponibile; **Documento:** doc-internal-26243863" in output
    assert "live:GCA4-EVIDENCE:pmid:26243863" not in output.split("Record storici non riconciliati (non ammessi)")[-1]
