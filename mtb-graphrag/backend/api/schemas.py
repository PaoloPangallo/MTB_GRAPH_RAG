"""
Pydantic I/O models — Contratto tra frontend e backend.
"""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class MTBRequest(BaseModel):
    """Input della pipeline MTB."""
    gene:               Optional[str] = None    # HUGO symbol (null per biomarker)
    variant:            str                      # protein change, Fusion, MSI-High
    tumor_type:         str                      # nome tumore o codice OncoTree
    alteration_type:    Literal[
        "point_mutation", "fusion", "cna", "itd", "atypical", "biomarker"
    ]
    therapy_line:       str = "first-line"       # first-line | second-line | later-line
    enrich_with_oncokb: bool = False             # attiva OncoKB Enricher
    report:             Optional[str] = None     # report base da arricchire
    driver_variant:     Optional[str] = None     # variante driver originale da cui si è sviluppata la resistenza




class ReportResponse(BaseModel):
    """Output della pipeline MTB."""
    complexity:         str
    escat_tier:         str
    report:             str
    cited_pmids:        list[int]
    drug_candidates:    list[dict[str, Any]]
    resistance_data:    list[dict[str, Any]]
    trial_candidates:   list[dict[str, Any]]
    oncokb_enrichment:  Optional[list[dict[str, Any]]] = None


class JudgeRequest(BaseModel):
    """Input per la valutazione LLM-as-judge."""
    report:     str
    gene:       Optional[str] = None
    variant:    str
    tumor_type: str


class JudgeResponse(BaseModel):
    """Output della valutazione LLM-as-judge."""
    completezza:         Optional[float] = None
    utilita_clinica:     Optional[float] = None
    fedelta_evidenze:    Optional[float] = None
    accuratezza_clinica: Optional[float] = None
    score_totale:        Optional[float] = None
    motivazione:         Optional[str] = None
    raw_response:        Optional[str] = None
    error:               Optional[str] = None
