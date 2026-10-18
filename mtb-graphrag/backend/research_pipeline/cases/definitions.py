"""5 synthetic clinical vignettes, deterministically authored from real
GraphCandidateAssertion/EvidenceBundle records already frozen in this
repository, so the expected outcome is known in advance without inventing
any clinical association. The parser NEVER receives `source_record` -- only
`clinical_text`. No real patient data is used anywhere.
"""
from __future__ import annotations

CASES = [
    {
        "case_id": "CASE-1-therapy-evaluation-strong-match",
        "clinical_text": (
            "A patient with metastatic colorectal cancer has been found to carry a "
            "KRAS G12D mutation on molecular testing of the tumor. The treating "
            "oncologist is evaluating whether panitumumab would be an appropriate "
            "therapy for this patient."
        ),
        "source_record": {"candidate_id": "GCA-008ae3aad1a64c118318ef79", "bundle_id": "EB-b4c48ba003913f278ff182a6", "baseline_support_status": "DIRECT"},
        "fields_used": ["disease=Colorectal Cancer", "biomarker=KRAS G12D", "target_intervention=panitumumab"],
        "fields_omitted": [],
        "fields_perturbed": [],
        "expected_query_intent": "THERAPY_EVALUATION",
        "expected_result": "Strong structural match; candidate found; document is the DIRECT baseline (KRAS G12D confers resistance to panitumumab); Gemma enrichment, if accepted, should report resistance, not benefit; deterministic status should not become a positive claim.",
    },
    {
        "case_id": "CASE-2-therapy-discovery",
        "clinical_text": (
            "A patient with metastatic colorectal cancer has a BRAF V600E mutation "
            "identified on tumor genomic profiling. Which therapeutic options are "
            "associated with this molecular alteration in this disease context?"
        ),
        "source_record": {"candidate_id": "GCA-0031c17c5ff5ae29ff221b1e", "bundle_ids": ["EB-479f55c21cac935ef1313755", "EB-278efe96eecccc226c82aa2d"], "baseline_support_status": "AMBIGUOUS"},
        "fields_used": ["disease=Colorectal Cancer", "biomarker=BRAF V600E"],
        "fields_omitted": ["target_intervention (encorafenib) deliberately not named in the text"],
        "fields_perturbed": [],
        "expected_query_intent": "THERAPY_DISCOVERY",
        "expected_result": "target_intervention must be null; retrieval should discover ENCORAFENIB from the KG without the drug ever appearing in the clinical text; Gemma reads only the retrieved candidate's papers, not a free choice of drug.",
    },
    {
        "case_id": "CASE-3-partial-incomplete-context",
        "clinical_text": (
            "A patient with colorectal cancer has tumor testing showing microsatellite "
            "instability (MSI), with the specific degree not yet reported. The patient has "
            "previously received fluoropyrimidine-based chemotherapy. The clinical team is "
            "evaluating nivolumab as a subsequent treatment option."
        ),
        "source_record": {"candidate_id": "GCA-02861e174359dd9f4f53df9b", "bundle_id": "EB-b6dc7db903abe794a5b18eae", "baseline_support_status": "PARTIAL"},
        "fields_used": ["disease=Colorectal Cancer (kept general)", "biomarker=microsatellite instability / MSI (subtype MSI-High omitted)", "previous_intervention=fluoropyrimidine-based chemotherapy", "target_intervention=nivolumab"],
        "fields_omitted": ["exact MSI-High degree/subtype label"],
        "fields_perturbed": ["biomarker made less specific than the candidate's own label"],
        "expected_query_intent": "THERAPY_EVALUATION",
        "expected_result": "Partial/uncertain biomarker match expected (verifier may flag UNCERTAIN due to normalized-value divergence); no improper promotion to DIRECT; warning expected in the dossier.",
    },
    {
        "case_id": "CASE-4-contradicted-or-resistance",
        "clinical_text": (
            "A patient with lung squamous cell carcinoma has FGFR1 amplification "
            "detected by next-generation sequencing. The oncology team is evaluating "
            "infigratinib for this patient and would like to understand what the "
            "available literature reports."
        ),
        "source_record": {"candidate_id": "GCA-0062c0237b990701837a1cc4", "bundle_id": "EB-6a291f12975b20b79e1c3dd7", "baseline_support_status": "CONTRADICTED"},
        "fields_used": ["disease=Lung Squamous Cell Carcinoma", "biomarker=FGFR1 Amplification", "target_intervention=infigratinib"],
        "fields_omitted": [],
        "fields_perturbed": [],
        "expected_query_intent": "THERAPY_EVALUATION",
        "expected_result": "The candidate asserts Sensitivity/Response, but the underlying document does not clearly support infigratinib specifically for this exact histology (baseline CONTRADICTED). Gemma must report what the authors actually say without converting it into a benefit claim; the deterministic pipeline must not classify this as DIRECT/positive.",
    },
    {
        "case_id": "CASE-5-casecontext-mismatch-no-match",
        "clinical_text": (
            "A patient with colorectal cancer underwent an exploratory research "
            "genomic panel that identified a ZZTK9 P44R alteration of uncertain "
            "clinical significance. The team asks whether panitumumab could be "
            "considered for this patient."
        ),
        "source_record": None,
        "fields_used": ["disease=Colorectal Cancer (real)", "biomarker=ZZTK9 P44R (fabricated, not in the repository)", "target_intervention=panitumumab (real drug)"],
        "fields_omitted": [],
        "fields_perturbed": ["gene name ZZTK9 is fabricated and does not exist in graph_candidate_repository/2.0/candidates.jsonl"],
        "expected_query_intent": "THERAPY_EVALUATION",
        "expected_result": "The CaseContext Match Verifier should find MATCH for the fabricated biomarker (it is genuinely, literally present in the text -- the parser extracted faithfully). Retrieval must find zero compatible candidates (the gene does not exist in the KG) and return NO_MATCH before Gemma is ever called; no artificial evidence may be constructed.",
    },
]
