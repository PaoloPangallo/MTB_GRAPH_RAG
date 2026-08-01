"""
API Routes — /analyze, /enrich, /judge, /zeroshot.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage

from backend.api.schemas import (
    MTBRequest,
    ReportResponse,
    JudgeRequest,
    JudgeResponse,
    ArchitectureComparisonRequest,
    ArchitectureComparisonResponse,
)
from backend.api.v3_schemas import V3RetrieveRequest, V3RetrieveResponse
from backend.api.v3_presentation import present_retrieval_outcome
from backend.comparison.service import compare_architectures
from backend.pipeline.state import MTBState
from backend.pipeline.evidence.retrieval.pipeline import EvidenceRetrievalPipeline
from backend.pipeline.graph import run_pipeline
from backend.pipeline.agents.oncokb_enricher import oncokb_enricher
from backend.pipeline.agents.judge import llm_as_judge
from backend.pipeline.helpers import make_pmids_clickable
from backend.pipeline.llm import llm
from backend.evaluation.run_zeroshot import SYNTHESIZER_SYSTEM, build_zeroshot_context
from backend.evaluation.compute_metrics import extract_pmids_from_report, extract_escat_tier
from backend.api.subgraph import extract_subgraph, build_zeroshot_subgraph


router = APIRouter()


@router.post("/compare-architectures", response_model=ArchitectureComparisonResponse)
def architecture_comparison(req: ArchitectureComparisonRequest) -> ArchitectureComparisonResponse:
    """Esegue le due architetture GraphRAG verificabili sullo stesso caso.

    Restituisce esattamente due run:

    - ``deterministic`` — GraphRAG deterministico verificabile: piano fisso e
      traversal tipizzato;
    - ``agentic`` — Agentic GraphRAG verificabile: planner adattivo in ciclo
      plan-act-observe.

    Le due differiscono **soltanto** nella strategia di raccolta e attraversano
    lo stesso strato di controllo (ledger append-only, vista canonica
    ricostruita per replay, proiezione pertinente, verifica strutturale,
    verifica claim-fonte, applicabilita', riparazione bounded, dossier). Il
    confronto misura quindi orchestrazione deterministica contro orchestrazione
    agentica a strato di controllo invariato.

    ``execution_mode`` non identifica un'architettura: sceglie soltanto se
    usare le dipendenze reali (``live``) o fixture e client scriptati
    (``demo``). La forma della risposta e' identica nei due casi.

    Prototipo di ricerca: il dossier e' un artefatto destinato alla revisione
    del Molecular Tumor Board, non una raccomandazione terapeutica.
    """
    return compare_architectures(req)


@router.get("/agent-runs/{run_id}")
def agent_run_events(run_id: str) -> dict:
    """Espone un singolo ledger tramite UUID, senza consentire ricerca o modifica."""
    from uuid import UUID

    from backend.pipeline.agentic.ledger import EventLedger

    try:
        UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="run_id non valido") from exc

    ledger = EventLedger()
    events = ledger.events(run_id)
    if not events:
        raise HTTPException(status_code=404, detail="esecuzione non trovata")
    public_events = [
        {key: value for key, value in event.items() if key != "payload_json"}
        for event in events
    ]
    return {
        "run_id": run_id,
        "append_only": True,
        "hash_chain_valid": ledger.verify_chain(run_id),
        "events": public_events,
    }


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


def extract_drugs_from_report(report_text: str) -> list[dict]:
    from backend.evaluation.drug_aliases import DRUG_ALIASES
    found_drugs = []
    text_lower = report_text.lower()
    detected = set()
    for alias, generic in DRUG_ALIASES.items():
        if alias in text_lower or generic in text_lower:
            detected.add(generic)
            
    for drug in sorted(list(detected)):
        found_drugs.append({
            "drug_name": drug.capitalize(),
            "approved": True,
            "evidence_level": "N/D",
            "companion_diagnostic": None
        })
    return found_drugs


@router.post("/websearch", response_model=ReportResponse)
def websearch(req: MTBRequest) -> ReportResponse:
    """Esegue la condizione websearch (PubMed search + LLM zero-shot)."""
    from backend.evaluation.ablation_websearch import run_websearch

    gene = req.gene or ""
    variant = req.variant
    tumor_type = req.tumor_type
    alteration_type = req.alteration_type
    if "MSI" in variant.upper() or "TMB" in variant.upper():
        alteration_type = "biomarker"
    therapy_line = req.therapy_line or "first-line"
    
    report = run_websearch(
        gene, variant, tumor_type, alteration_type, therapy_line
    )
    
    # Estrai i PMID citati
    cited_pmids = list(extract_pmids_from_report(report))
    
    # Rendi i PMID cliccabili
    report_clickable = make_pmids_clickable(report)
    
    # Estrai ESCAT tier
    escat_tier = extract_escat_tier(report) or "N/D"
    
    # Estrai farmaci raccomandati
    drug_candidates = extract_drugs_from_report(report)
    
    return ReportResponse(
        complexity="websearch",
        escat_tier=escat_tier,
        report=report_clickable,
        cited_pmids=cited_pmids,
        drug_candidates=drug_candidates,
        resistance_data=[],
        trial_candidates=[],
        oncokb_enrichment=None
    )


@router.post("/rag", response_model=ReportResponse)
def rag(req: MTBRequest) -> ReportResponse:
    """Esegue la condizione rag_testuale (RAG su chunk KG + LLM)."""
    from backend.evaluation.ablation_rag import run_rag_testuale

    gene = req.gene or ""
    variant = req.variant
    tumor_type = req.tumor_type
    alteration_type = req.alteration_type
    if "MSI" in variant.upper() or "TMB" in variant.upper():
        alteration_type = "biomarker"
    therapy_line = req.therapy_line or "first-line"
    
    report = run_rag_testuale(
        gene, variant, tumor_type, alteration_type, therapy_line
    )
    
    # Estrai i PMID citati
    cited_pmids = list(extract_pmids_from_report(report))
    
    # Rendi i PMID cliccabili
    report_clickable = make_pmids_clickable(report)
    
    # Estrai ESCAT tier
    escat_tier = extract_escat_tier(report) or "N/D"
    
    # Estrai farmaci raccomandati
    drug_candidates = extract_drugs_from_report(report)
    
    return ReportResponse(
        complexity="rag_testuale",
        escat_tier=escat_tier,
        report=report_clickable,
        cited_pmids=cited_pmids,
        drug_candidates=drug_candidates,
        resistance_data=[],
        trial_candidates=[],
        oncokb_enrichment=None
    )


@router.post("/v3/retrieve", response_model=V3RetrieveResponse)
def v3_retrieve(req: V3RetrieveRequest) -> V3RetrieveResponse:
    """Esegue esclusivamente il retriever V3 strutturale, senza planner o LLM."""
    pipeline = EvidenceRetrievalPipeline.from_config(
        {
            "retrieval_backend": "qualified_claim_v3",
            "qualified_claim_policy_mode": req.policy_mode,
        }
    )
    outcome = pipeline.run(
        req.to_query(), retrieval_backend="qualified_claim_v3"
    )
    return V3RetrieveResponse.model_validate(present_retrieval_outcome(outcome))


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
