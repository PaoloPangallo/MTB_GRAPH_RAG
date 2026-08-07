"""STAGE 9 — research-only dossier preview. Built deterministically from
already-validated data only. Gemma's output appears exclusively under
"author_context" and never overwrites claim/status/support_mask/gate/
provenance.

Ogni voce di ``author_context`` porta il **proprio** esito di validazione. Senza
di esso il dossier conservava soltanto una lista piatta di proposte del modello e
una lista separata di esiti, e un consumatore non poteva sapere quale esito
appartenesse a quale quote: la UI ricadeva su ``accepted = quote != null`` e
mostrava come citazione d'autore anche una quote rigettata.

``presentation_state`` è il vocabolario che i consumatori devono leggere. La
fonte dell'accettazione è l'esito del validatore deterministico, mai la presenza
di una stringa.
"""
from __future__ import annotations

from typing import Any

#: Stati di presentazione di un enrichment. Chiusi e mutuamente esclusivi.
VALIDATED_QUOTE = "VALIDATED_QUOTE"
REJECTED_QUOTE = "REJECTED_QUOTE"
ABSTAINED = "ABSTAINED"
PROPOSED_QUOTE_NOT_VALIDATED = "PROPOSED_QUOTE_NOT_VALIDATED"

PRESENTATION_STATES: tuple[str, ...] = (
    VALIDATED_QUOTE, REJECTED_QUOTE, ABSTAINED, PROPOSED_QUOTE_NOT_VALIDATED,
)

#: I soli stati che un consumatore può presentare come citazione degli autori.
PRESENTABLE_AS_AUTHOR_CLAIM: frozenset[str] = frozenset({VALIDATED_QUOTE})

_ACCEPTED_OUTCOMES: frozenset[str] = frozenset({
    "ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING",
    "ENRICHMENT_V2_ACCEPTED", "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY",
})

_ABSTAIN_OUTCOMES: frozenset[str] = frozenset({
    "ENRICHMENT_ABSTAINED", "ENRICHMENT_V2_ABSTAINED",
    "ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS",
})


def presentation_state(outcome: str | None, *, has_quote: bool) -> str:
    """Stato di presentazione, derivato **solo** dall'esito del validatore.

    Un esito assente non è un'accettazione: una proposta non validata resta
    ``PROPOSED_QUOTE_NOT_VALIDATED`` e non è presentabile.
    """
    if outcome in _ACCEPTED_OUTCOMES:
        return VALIDATED_QUOTE
    if outcome in _ABSTAIN_OUTCOMES:
        return ABSTAINED
    if outcome:
        return REJECTED_QUOTE
    return PROPOSED_QUOTE_NOT_VALIDATED


def annotate_enrichment(
    enrichment: dict[str, Any],
    *,
    paper_id: str | None,
    validation: dict[str, Any] | None,
    accepted_for_gates: bool,
) -> dict[str, Any]:
    """Copia dell'enrichment con il proprio esito di validazione allegato.

    Non muta l'originale e non rimuove nulla: la proposta del modello resta
    integralmente ispezionabile per audit, ma smette di essere indistinguibile
    da una citazione validata.
    """
    outcome = (validation or {}).get("outcome")
    has_quote = bool((enrichment or {}).get("author_claim_quote"))
    return {
        **(enrichment or {}),
        "paper_id": paper_id,
        "validation_outcome": outcome,
        "validation_reason_codes": list((validation or {}).get("reason_codes") or []),
        "presentation_state": presentation_state(outcome, has_quote=has_quote),
        "accepted_for_gates": bool(accepted_for_gates),
    }


def build_dossier_preview(case_id: str, case_context: dict[str, Any], verification_summary: dict[str, Any], candidate_therapies: list[dict[str, Any]], limitations: list[str]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "case_context": case_context,
        "case_context_verification": verification_summary,
        "candidate_therapies": candidate_therapies,
        "limitations": limitations,
        "provenance": {
            "dossier_kind": "research_only_end_to_end_pilot_preview",
            "dossier_version": "end-to-end-pilot-dossier/1.0",
            "gemma_role": "paper_context_enricher_only",
            "gemma_never_decides": ["support_status", "direction", "contradiction", "gate", "score", "bucket"],
            "not_wired_to_production_runtime": True,
        },
    }


def build_candidate_therapy_entry(candidate: dict[str, Any], graph_relation: str, document_support: dict[str, Any], enrichments: list[dict[str, Any]], validation_results: list[dict[str, Any]], evaluation: dict[str, Any]) -> dict[str, Any]:
    interventions = [i.get("label") for i in candidate.get("interventions") or [] if i.get("label")]
    return {
        "candidate_id": candidate["candidate_id"],
        "drug": interventions[0] if interventions else None,
        "graph_relation": graph_relation,
        "document_support": document_support,
        "author_context": enrichments,
        "validation_results": validation_results,
        "gate_results": {"bucket": evaluation["gate_bucket"], "support_mask": evaluation["support_mask"]},
        "status": evaluation["status"],
        "warnings": evaluation["warnings"],
    }
