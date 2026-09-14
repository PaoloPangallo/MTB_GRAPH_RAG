from backend.research_pipeline.narrative.markdown_renderer import render_dossier_markdown


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
    assert "## Sintesi narrativa verificata" in output
    assert "Sintesi leggibile" in output
    assert "Testo della candidate" in output
    assert "VERIFIED_NARRATIVE" in output
