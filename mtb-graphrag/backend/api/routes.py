"""
API Routes — /analyze, /enrich, /judge, /zeroshot.
"""

from __future__ import annotations

from fastapi import APIRouter
from langchain_core.messages import HumanMessage, SystemMessage

from backend.api.schemas import MTBRequest, ReportResponse, JudgeRequest, JudgeResponse
from backend.pipeline.state import MTBState
from backend.pipeline.graph import run_pipeline
from backend.pipeline.agents.oncokb_enricher import oncokb_enricher
from backend.pipeline.agents.judge import llm_as_judge
from backend.pipeline.helpers import make_pmids_clickable
from backend.pipeline.llm import llm
from backend.evaluation.run_zeroshot import SYNTHESIZER_SYSTEM, build_zeroshot_context
from backend.evaluation.compute_metrics import extract_pmids_from_report
from backend.api.subgraph import extract_subgraph, build_zeroshot_subgraph

router = APIRouter()


@router.get("/subgraph")
def subgraph(
    gene: str = "",
    variant: str = "",
    tumor_type: str = "",
    alteration_type: str = "point_mutation",
    mode: str = "graphrag",
    cited_pmids: str = "",
):
    """Restituisce il sotto-grafo del Knowledge Graph attivato per il caso clinico.
    
    In mode='zeroshot' restituisce un grafo sintetico che evidenzia l'allucinazione.
    """
    if "MSI" in variant.upper() or "TMB" in variant.upper():
        alteration_type = "biomarker"

    if mode == "zeroshot":
        pmids = [int(p.strip()) for p in cited_pmids.split(",") if p.strip().isdigit()]
        return build_zeroshot_subgraph(pmids)
    
    return extract_subgraph(gene, variant, tumor_type, alteration_type)


@router.post("/analyze", response_model=ReportResponse)
def analyze(req: MTBRequest) -> ReportResponse:
    """Esegue la pipeline completa su un caso MTB."""
    alt_type = req.alteration_type
    if "MSI" in req.variant.upper() or "TMB" in req.variant.upper():
        alt_type = "biomarker"

    state: MTBState = {
        "gene":               req.gene or "",
        "variant":            req.variant,
        "tumor_type":         req.tumor_type,
        "alteration_type":    alt_type,
        "therapy_line":       req.therapy_line,
        "enrich_with_oncokb": req.enrich_with_oncokb,
        "driver_variant":     req.driver_variant or "",
        # placeholder — sovrascritti dagli agenti
        "complexity":         "low",
        "variant_data":       {},
        "drug_candidates":    [],
        "trial_candidates":   [],
        "resistance_data":    [],
        "oncokb_enrichment":  [],
        "report":             "",
        "cited_pmids":        [],
        "escat_tier":         "",
    }

    final = run_pipeline(state)
    report_clickable = make_pmids_clickable(final["report"])

    return ReportResponse(
        complexity=final["complexity"],
        escat_tier=final["escat_tier"],
        report=report_clickable,
        cited_pmids=final["cited_pmids"],
        drug_candidates=final["drug_candidates"],
        resistance_data=final["resistance_data"],
        trial_candidates=final.get("trial_candidates", []),
        oncokb_enrichment=None, # Inizialmente non arricchito
    )


@router.post("/enrich", response_model=ReportResponse)
def enrich(req: MTBRequest) -> ReportResponse:
    """Richiama solo l'OncoKB Enricher su uno stato esistente."""
    alt_type = req.alteration_type
    if "MSI" in req.variant.upper() or "TMB" in req.variant.upper():
        alt_type = "biomarker"

    state: MTBState = {
        "gene":               req.gene or "",
        "variant":            req.variant,
        "tumor_type":         req.tumor_type,
        "alteration_type":    alt_type,
        "therapy_line":       req.therapy_line,
        "enrich_with_oncokb": True,  # forzato
        "driver_variant":     req.driver_variant or "",
        "complexity":         "low",
        "variant_data":       {},
        "drug_candidates":    [],
        "trial_candidates":   [],
        "resistance_data":    [],
        "oncokb_enrichment":  [],
        "report":             req.report or "",
        "cited_pmids":        [],
        "escat_tier":         "",
    }

    final = oncokb_enricher(state)
    report_clickable = make_pmids_clickable(final.get("report", ""))

    return ReportResponse(
        complexity=final.get("complexity", ""),
        escat_tier=final.get("escat_tier", ""),
        report=report_clickable,
        cited_pmids=final.get("cited_pmids", []),
        drug_candidates=final.get("drug_candidates", []),
        resistance_data=final.get("resistance_data", []),
        trial_candidates=final.get("trial_candidates", []),
        oncokb_enrichment=final.get("oncokb_enrichment", []),
    )


@router.post("/zeroshot", response_model=ReportResponse)
def zeroshot(req: MTBRequest) -> ReportResponse:
    """Esegue la generazione zero-shot (senza Knowledge Graph) su un caso MTB."""
    gene = req.gene or ""
    variant = req.variant
    tumor_type = req.tumor_type
    alteration_type = req.alteration_type
    if "MSI" in variant.upper() or "TMB" in variant.upper():
        alteration_type = "biomarker"
    therapy_line = req.therapy_line or "first-line"
    
    # Costruisci il contesto zero-shot
    context = build_zeroshot_context(
        gene, variant, tumor_type, alteration_type, therapy_line
    )
    
    # Invoca l'LLM direttamente
    response = llm.invoke([
        SystemMessage(content=SYNTHESIZER_SYSTEM),
        HumanMessage(content=context),
    ])
    
    report = response.content
    
    # Estrai i PMID citati dallo zero-shot
    cited_pmids = list(extract_pmids_from_report(report))
    
    # Rendi i PMID cliccabili
    report_clickable = make_pmids_clickable(report)
    
    return ReportResponse(
        complexity="zero-shot",
        escat_tier="N/A",
        report=report_clickable,
        cited_pmids=cited_pmids,
        drug_candidates=[],
        resistance_data=[],
        trial_candidates=[],
        oncokb_enrichment=None
    )


@router.post("/judge", response_model=JudgeResponse)
def judge(req: JudgeRequest) -> JudgeResponse:
    """Valuta un report MTB con LLM-as-judge."""
    case_info = {
        "gene": req.gene,
        "variant": req.variant,
        "tumor_type": req.tumor_type,
    }
    result = llm_as_judge(req.report, case_info)
    return JudgeResponse(**result)

