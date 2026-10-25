"""Synthetic document fixtures test pipeline coherence, not clinical efficacy."""
import pytest
from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import (
    _run_orchestrated, _parser_output, _paper_candidate, _source_unit,
)


@pytest.mark.parametrize("gene,variant,disease,drug", [
    ("BRAF", "V600E", "colorectal cancer", "vemurafenib"),
    ("KRAS", "G12D", "pancreatic cancer", "trametinib"),
])
def test_case_resolution_retrieval_document_and_dossier_are_coherent(tmp_path, gene, variant, disease, drug):
    qualified = "metastatic " + disease
    raw = f"{qualified} with {gene} {variant}; current target {drug}."
    parsed = _parser_output(raw, disease=qualified, biomarkers=((gene, variant),), interventions=((drug, "TARGET"),))
    candidate = _paper_candidate(
        disease=[{"label": disease, "type": "Disease"}],
        biomarkers=[{"label": gene, "type": "Gene"},
                    {"label": variant, "type": "Variant", "gene": gene, "alteration": variant}],
        interventions=[{"label": drug, "type": "Drug"}],
    )
    quote = f"{gene} {variant} showed sensitivity to {drug} in {disease}."
    run = _run_orchestrated(tmp_path, "terminology-" + gene, raw, parsed,
                            {candidate["candidate_id"]: candidate}, [_source_unit(quote)])
    stages = {s.stage_id: s for s in run.stages}
    trace = stages["stage_4_retrieval_plan"].output_preview["entity_resolution"]
    assert trace["diseases"][0]["status"] == "RESOLVED"
    assert trace["diseases"][0]["residual_context"] == "metastatic"
    assert trace["biomarkers"][0]["variant"]["status"] == "RESOLVED"
    assert run.relation_aware_report["paper_evidence"][0]["claim"]["status"] == "FULL_SUPPORT"
