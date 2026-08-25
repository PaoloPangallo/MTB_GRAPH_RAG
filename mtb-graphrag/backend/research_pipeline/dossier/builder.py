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

from backend.research_pipeline.retrieval.relation_family import (
    CLINICAL_TRIAL,
    KG_ONLY,
    PAPER_EVIDENCE,
    classify_relation_family,
)

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


def _scalar(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("normalized_value") or value.get("raw_value") or value.get("label")
    return value


def _labels(entries: list[dict[str, Any]] | None) -> list[str]:
    return [str(item["label"]) for item in entries or [] if item.get("label")]


def _document_id(candidate: dict[str, Any], preferred: tuple[str, ...] = ("pmid", "pmcid", "nct", "doi", "url")) -> str | None:
    for identifier in candidate.get("document_identifiers") or []:
        for kind in preferred:
            if identifier.get(kind):
                return f"{kind}:{identifier[kind]}"
    return None


def _candidate_result(results: Any, candidate_id: str) -> dict[str, Any]:
    if isinstance(results, dict):
        value = results.get(candidate_id)
        return value if isinstance(value, dict) else {}
    return {}


def _paper_result_fields(result: dict[str, Any]) -> dict[str, Any]:
    """Project existing paper-pipeline records without recomputing them."""
    enrichment = result.get("enrichment") or {}
    validation = result.get("validation") or {}
    support = result.get("candidate_support") or {}
    selected = result.get("selected_source_units") or []
    return {
        "document_source": result.get("document_source"),
        "document_resolution_status": result.get("document_resolution_status"),
        "selected_source_units": selected,
        "reader_status": enrichment.get("decision") or result.get("reader_status"),
        "quote": result.get("quote") or enrichment.get("author_claim_quote"),
        "quote_validation": result.get("quote_validation") or validation.get("outcome"),
        "support_fields": result.get("support_fields") or support.get("fields"),
        "support_level": result.get("support_level") or support.get("result"),
        "reason": result.get("reason") or support.get("reason"),
    }


def _case_summary(case_context: dict[str, Any]) -> dict[str, Any]:
    biomarkers = case_context.get("biomarkers") or []
    first = biomarkers[0] if biomarkers else {}
    return {
        "case_id": case_context.get("case_id"),
        "disease": _scalar(case_context.get("disease")),
        "gene": _scalar(first.get("gene")),
        "variant": _scalar(first.get("alteration")),
        "intervention": _scalar(case_context.get("target_intervention")),
        "intent": case_context.get("query_intent"),
    }


def _trial_result_fields(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": result.get("title"),
        "status": result.get("status") or result.get("overall_status") or result.get("recruitment_status"),
        "phase": result.get("phase") or result.get("phases"),
        "conditions": result.get("conditions") or [],
        "interventions": result.get("interventions") or [],
        "biomarker_gene": result.get("biomarker_gene"),
        "source": result.get("source") or "ClinicalTrials.gov",
        "provenance_status": result.get("provenance_status") or (
            "TRIAL_RECORD_RESOLVED" if result else "NOT_EVALUATED"
        ),
        "eligibility_status": result.get("eligibility_status") or "NOT_EVALUATED",
    }


def build_relation_aware_report(
    case_context: dict[str, Any],
    candidates: list[dict[str, Any]],
    paper_results: Any = None,
    trial_results: Any = None,
) -> dict[str, Any]:
    """Project GCA candidates into a deterministic, provenance-aware report.

    This function is intentionally a projection only: it performs no retrieval,
    document resolution, enrichment, LLM call, or network access.
    """
    paper_evidence: list[dict[str, Any]] = []
    clinical_trials: list[dict[str, Any]] = []
    kg_only_relations: list[dict[str, Any]] = []
    limitations: set[str] = set()

    for candidate in sorted(candidates, key=lambda item: str(item.get("candidate_id", ""))):
        candidate_id = candidate["candidate_id"]
        family = classify_relation_family(candidate)
        common = {
            "candidate_id": candidate_id,
            "relation_family": family,
            "subject": candidate.get("subject"),
            "relation": candidate.get("predicate"),
            "object": candidate.get("object"),
            "disease_context": _labels(candidate.get("disease")),
            "direction": candidate.get("direction"),
        }
        if family == PAPER_EVIDENCE:
            result = _candidate_result(paper_results, candidate_id)
            paper_fields = _paper_result_fields(result)
            paper_evidence.append({
                **common,
                "evidence_type": candidate.get("evidence_scope") or candidate.get("source_properties", {}).get("evidence", {}).get("evidence_type"),
                "document_id": _document_id(candidate),
                "source_type": candidate.get("source_properties", {}).get("evidence", {}).get("source_type"),
                **paper_fields,
                "support_status": result.get("support_status") or ("NOT_EVALUATED" if not result else None),
            })
            if not result:
                limitations.add("PAPER_SUPPORT_NOT_EVALUATED")
        elif family == CLINICAL_TRIAL:
            result = _candidate_result(trial_results, candidate_id)
            trial_fields = _trial_result_fields(result)
            nct_id = next((item.get("nct") for item in candidate.get("document_identifiers") or [] if item.get("nct")), None)
            clinical_trials.append({
                **common,
                "nct_id": nct_id,
                **trial_fields,
                "interventions": trial_fields["interventions"] or _labels(candidate.get("interventions")),
                "biomarker_gene": trial_fields["biomarker_gene"] or _labels(candidate.get("biomarkers")),
                "evidence_interpretation": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
            })
            limitations.add("TRIAL_ASSOCIATION_IS_NOT_EFFICACY_EVIDENCE")
        else:
            kg_only_relations.append({
                **common,
                "document_id": None,
                "graph_provenance": candidate.get("source_properties") or candidate.get("materialization_rule_id"),
                "source_database": candidate.get("source_properties", {}).get("evidence", {}).get("source_type") or "KG",
                "verification_status": "KG_ONLY",
                "document_provenance": "NOT_AVAILABLE",
            })
            limitations.add("DOCUMENT_PROVENANCE_NOT_AVAILABLE")

    return {
        "case_summary": _case_summary(case_context),
        "paper_evidence": paper_evidence,
        "clinical_trials": clinical_trials,
        "kg_only_relations": kg_only_relations,
        "limitations": sorted(limitations),
    }
