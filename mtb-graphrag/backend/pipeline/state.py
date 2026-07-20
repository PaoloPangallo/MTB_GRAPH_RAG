"""
MTBState — Stato condiviso della pipeline agentica GraphRAG MTB.
Ogni agente riceve MTBState in input e restituisce MTBState in output.
"""

from __future__ import annotations

from typing import Any, Literal
from typing_extensions import TypedDict, NotRequired


AlterationType = Literal[
    "point_mutation", "fusion", "cna", "itd", "atypical", "biomarker"
]


class MTBState(TypedDict):
    # Input clinico
    gene:               str                    # HUGO symbol (null per biomarker)
    variant:            str                    # protein change, Fusion, MSI-High
    tumor_type:         str                    # nome tumore o codice OncoTree
    alteration_type:    AlterationType         # determina logica di query e endpoint OncoKB
    therapy_line:       str                    # first-line | second-line | later-line
    enrich_with_oncokb: bool                   # attiva OncoKB Enricher (human-in-the-loop)
    driver_variant:     NotRequired[str]       # variante driver da cui si è sviluppata la resistenza
    disease_stage:      NotRequired[str]
    disease_setting:    NotRequired[str]
    prior_therapies:    NotRequired[list[str]]
    prior_response:     NotRequired[str]
    ecog_status:        NotRequired[int]
    cns_metastases:     NotRequired[bool]
    co_alterations:     NotRequired[list[str]]
    jurisdiction:       NotRequired[str]
    mtb_goal:           NotRequired[str]

    # Routing
    complexity:         Literal["low", "moderate", "high"]

    # Output intermedi
    variant_data:       dict[str, Any]         # evidenze A/B + ESCAT tier
    drug_candidates:    list[dict[str, Any]]   # drug + companion diagnostic
    trial_candidates:   list[dict[str, Any]]   # trial clinici eleggibili
    resistance_data:    list[dict[str, Any]]   # evidenze di resistenza + pubblicazioni
    oncokb_enrichment:  list[dict[str, Any]]   # trattamenti OncoKB live (solo se Enricher attivo)

    # Output finale
    report:                 str
    cited_pmids:            list[int]
    escat_tier:             str
    pmid_rimossi_dal_testo: NotRequired[list[int]]
