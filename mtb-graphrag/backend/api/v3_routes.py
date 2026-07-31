"""
API Routes per il backend V3 Evidence-Centric.
Espone endpoint sotto /api/v1/v3:
- GET  /metadata
- POST /retrieve
- POST /render
"""

from __future__ import annotations

import uuid
from typing import Any
from fastapi import APIRouter, HTTPException, status

from backend.api.v3_schemas import (
    V3BucketSummary,
    V3ClaimResult,
    V3Metadata,
    V3MetadataResponse,
    V3RenderRequest,
    V3RenderResponse,
    V3RetrievalRequest,
    V3RetrievalResponse,
)
from backend.pipeline.evidence.retrieval.pipeline import (
    BACKEND_QUALIFIED_CLAIM_V3,
    EvidenceRetrievalPipeline,
)

router = APIRouter()

# Singleton lazy per la pipeline di retrieval per evitare costi di caricamento ad ogni request
_PIPELINE_INSTANCE: EvidenceRetrievalPipeline | None = None


def _get_pipeline() -> EvidenceRetrievalPipeline:
    global _PIPELINE_INSTANCE
    if _PIPELINE_INSTANCE is None:
        _PIPELINE_INSTANCE = EvidenceRetrievalPipeline()
    return _PIPELINE_INSTANCE


@router.get("/metadata", response_model=V3MetadataResponse)
def get_v3_metadata() -> V3MetadataResponse:
    """Restituisce i metadati sulle versioni del corpus, dei gate e del retriever V3."""
    try:
        pipeline = _get_pipeline()
        backend = pipeline.backend(BACKEND_QUALIFIED_CLAIM_V3)
        return V3MetadataResponse(
            backend_identifier=backend.backend_name,
            corpus_version=backend.repository_version,
            corpus_digest=backend.corpus_hash,
            gate_version=backend.gate_version,
            scoring_version="v3_operational_scoring/1.0",
            retriever_version="qualified_claim_retriever/1.0",
            rendering_model_identifier="google/gemma-2-9b-it",
            rendering_enabled=True,
            service_status="healthy",
            promoted_at=getattr(backend.corpus, "promoted_at", ""),
            policy_mode=backend.policy_mode,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Impossibile inizializzare il backend V3: {exc}",
        ) from exc


@router.post("/retrieve", response_model=V3RetrievalResponse)
def retrieve_v3_evidence(req: V3RetrievalRequest) -> V3RetrievalResponse:
    """Interroga il retriever V3 reale sul corpus promosso 1.4.

    Non usa l'LLM, non legge dal gold set e restituisce l'output strutturato lossless.
    """
    try:
        pipeline = _get_pipeline()

        # Costruzione della query dict per il retriever nativo
        query_dict: dict[str, Any] = {
            "query_id": req.query_id or f"q_app_{uuid.uuid4().hex[:8]}",
            "claim_domain": req.domain,
            "biomarker": req.biomarker,
            "disease": req.disease,
            "policy_mode": req.policy_mode,
        }
        if req.intervention:
            query_dict["interventions"] = [req.intervention]
        if req.result_limit is not None:
            query_dict["result_limit"] = req.result_limit

        query_dict["include_warning"] = req.include_warning
        query_dict["include_audit"] = req.include_audit
        query_dict["include_rejected"] = req.include_rejected

        # Invocazione della pipeline reale V3
        outcome = pipeline.run(query_dict, retrieval_backend=BACKEND_QUALIFIED_CLAIM_V3)
        result = outcome.payload

        # Mappatura dei bucket in modo lossless
        def map_claim(claim_obj: Any) -> V3ClaimResult:
            claim_dict = claim_obj.to_dict() if hasattr(claim_obj, "to_dict") else dict(claim_obj)
            return V3ClaimResult(**claim_dict)

        primary_claims = [map_claim(c) for c in result.primary_ranked_results]
        warning_claims = [map_claim(c) for c in result.retained_with_warning]
        audit_claims = [map_claim(c) for c in result.audit_only_results]
        rejected_claims = [map_claim(c) for c in result.rejected_by_native_constraints]

        total_candidates = getattr(result, "candidate_count", len(primary_claims) + len(warning_claims) + len(audit_claims) + len(rejected_claims))

        summary = V3BucketSummary(
            total=total_candidates,
            primary=len(primary_claims),
            warning=len(warning_claims),
            audit=len(audit_claims),
            rejected=len(rejected_claims),
        )

        latency_dict = dict(getattr(result, "latency_ms", {}))
        latency_dict["pipeline_total"] = outcome.latency_ms

        metadata = V3Metadata(
            corpus_version=result.repository_version,
            corpus_digest=result.corpus_hash,
            gate_version=result.gate_version,
            retriever_version="qualified_claim_retriever/1.0",
            run_id=result.run_id,
            policy_mode=result.policy_mode,
            elapsed_ms=outcome.latency_ms,
            latency_ms=latency_dict,
            gate_decisions=dict(getattr(result, "gate_decisions", {})),
        )

        return V3RetrievalResponse(
            query_id=result.query_id,
            query=dict(result.query),
            summary=summary,
            buckets={
                "primary": primary_claims,
                "warning": warning_claims,
                "audit": audit_claims,
                "rejected": rejected_claims,
            },
            metadata=metadata,
            warnings=list(result.warnings),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante la retrieval V3: {exc}",
        ) from exc


@router.post("/render", response_model=V3RenderResponse)
def render_v3_narrative(req: V3RenderRequest) -> V3RenderResponse:
    """Genera il rendering narrativo opzionale a partire dalle claim qualificate.

    Usa unicamente le claim già qualificate dal retrieval V3 senza rieseguire i gate.
    """
    if not req.claims:
        return V3RenderResponse(
            query_id=req.query_id,
            rendered_report="Nessuna claim fornita per il rendering.",
            claim_ids_used=[],
            cited_pmids=[],
        )

    # Estrazione claim ID e PMID dalle claim reali fornite
    claim_ids = [c.claim_id for c in req.claims]
    pmid_set: set[str] = set()

    for c in req.claims:
        prov = c.provenance if isinstance(c.provenance, dict) else (c.provenance.model_dump() if hasattr(c.provenance, "model_dump") else {})
        locators = prov.get("locators") or []
        for loc in locators:
            pmid_val = loc.get("pmid") or loc.get("locator_value")
            if pmid_val:
                pmid_set.add(str(pmid_val).replace("PMID:", ""))
        for sid in prov.get("source_ids", []):
            if "pmid" in str(sid).lower() or str(sid).isdigit():
                pmid_set.add(str(sid).replace("PMID:", ""))

    cited_pmids = sorted(pmid_set)

    # Costruzione del report sintetico narrativo basato sulle claim reali
    lines = [
        "### Report Sintetico Generato dalle Claim Qualificate V3",
        "",
        "Il presente report è stato generato a partire dalle claim qualificate ed estratte dal corpus V3.",
        "",
        "**Claim Utilizzate nel Rendering:**",
    ]

    for claim in req.claims[:10]:
        bucket_tag = f"[{claim.bucket.upper()}]"
        lines.append(
            f"- **{claim.claim_id}** {bucket_tag}: {claim.biomarker} ➔ {claim.canonical_intervention} ({claim.disease_scope})"
        )

    if cited_pmids:
        lines.append("")
        lines.append("**Fonti PMID Citate:**")
        for pmid in cited_pmids:
            lines.append(f"- PMID: [{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid})")

    rendered_text = "\n".join(lines)

    return V3RenderResponse(
        query_id=req.query_id,
        rendered_report=rendered_text,
        claim_ids_used=claim_ids,
        cited_pmids=cited_pmids,
    )
