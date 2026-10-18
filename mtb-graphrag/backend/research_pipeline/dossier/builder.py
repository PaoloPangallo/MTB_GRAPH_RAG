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

import hashlib
import json
from copy import deepcopy
from typing import Any

from backend.research_pipeline.documents.authorized_cache import expand_identifier

from backend.research_pipeline.retrieval.relation_family import (
    CLINICAL_TRIAL,
    INVALID_PROVENANCE,
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

_SUPPORT_LEVELS = ("FULL_SUPPORT", "PARTIAL_SUPPORT", "NO_SUPPORT", "CONTRADICTORY",
                   "UNVERIFIABLE", "INSUFFICIENT_INFORMATION")


def _stable_id(prefix: str, payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}-{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:24]}"


def evidence_id(record: dict[str, Any]) -> str:
    """Return a deterministic evidence identity without using runtime order."""
    existing = record.get("evidence_id")
    if existing:
        return str(existing)
    return _stable_id("EVIDENCE", {
        "candidate_id": record.get("candidate_id"),
        "document_id": record.get("document_id") or record.get("paper_id"),
        "source_unit_id": record.get("source_unit_id"),
        "quote": record.get("quote") or record.get("author_claim_quote"),
    })


def is_aggregation_eligible(record: dict[str, Any]) -> tuple[bool, str | None]:
    """Fail-closed predicate for evidence entering support aggregation.

    PARTIAL/CONTRADICTORY are still verified evidence even when the gate does
    not admit them as primary support; they must remain available to preserve
    conflicts. A rejected record can never contribute merely because it carries
    stale ``candidate_support`` metadata.
    """
    outcome = record.get("validation_outcome")
    if outcome not in _ACCEPTED_OUTCOMES:
        return False, "VALIDATION_NOT_ACCEPTED"
    if record.get("quote_valid") is not True:
        return False, "QUOTE_NOT_VALID"
    if record.get("presentation_state") not in (None, VALIDATED_QUOTE):
        return False, "PRESENTATION_NOT_VALIDATED"
    support = record.get("candidate_support") or {}
    level = support.get("result") or record.get("support_level")
    if record.get("relation_family") == "EVIDENCE_DRUG" and level in {
        "FULL_SUPPORT", "PARTIAL_SUPPORT", "CONTRADICTORY",
    }:
        from ..enrichment.document_verification import admit
        from ..enrichment.semantic_contract import POLICY_VERSION

        verification = record.get("document_verification") or {}
        expected_alignment = "OPPOSITE" if level == "CONTRADICTORY" else "SAME"
        expected_admission = {
            "FULL_SUPPORT": "DOCUMENT_SUPPORTED",
            "PARTIAL_SUPPORT": "PARTIALLY_SUPPORTED",
            "CONTRADICTORY": "REJECTED",
        }[level]
        if (verification.get("structural_status") != "PASS"
                or verification.get("relation_alignment") != expected_alignment
                or verification.get("assertion_scope") != "DIRECT_ASSERTION"
                or verification.get("final_admission") != expected_admission
                or verification.get("admission_policy_version") != POLICY_VERSION
                or admit(verification, verification.get("semantic_assessment"))[
                    "final_admission"] != expected_admission):
            return False, "DOCUMENT_VERIFICATION_NOT_ADMITTED"
    if level not in _SUPPORT_LEVELS:
        return False, "SUPPORT_STATE_INVALID"
    if record.get("accepted_for_gates") is False and level == "FULL_SUPPORT":
        return False, "FULL_SUPPORT_NOT_ADMITTED_BY_GATE"
    if record.get("source_unit_id") in (None, ""):
        return False, "SOURCE_UNIT_ID_MISSING"
    if (record.get("document_id") or record.get("paper_id")) in (None, ""):
        return False, "DOCUMENT_ID_MISSING"
    return True, None


def _rejection_record(record: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id(record),
        "candidate_id": record.get("candidate_id"),
        "document_id": record.get("document_id") or record.get("paper_id"),
        "source_unit_id": record.get("source_unit_id"),
        "validation_outcome": record.get("validation_outcome"),
        "quote_valid": record.get("quote_valid"),
        "reader_attempt_status": record.get("reader_attempt_status"),
        "transport_result": record.get("transport_result"),
        "transport_reason_codes": record.get("transport_reason_codes") or [],
        "validation_reason_codes": record.get("validation_reason_codes") or [],
        "rejection_reason": reason,
        "candidate_support": record.get("candidate_support"),
    }


def aggregate_evidence_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive a fail-closed summary while preserving rejected audit records."""
    normalized = [dict(item) for item in records if isinstance(item, dict)]
    eligible, rejected = [], []
    for item in normalized:
        allowed, reason = is_aggregation_eligible(item)
        if allowed:
            item["evidence_id"] = evidence_id(item)
            eligible.append(item)
        else:
            rejected.append(_rejection_record(item, reason or "NOT_ELIGIBLE"))
    levels = [str((item.get("candidate_support") or {}).get("result") or item.get("support_level") or "UNVERIFIABLE")
              for item in eligible]
    has_full = "FULL_SUPPORT" in levels
    has_contradiction = "CONTRADICTORY" in levels
    if has_full and has_contradiction:
        summary = "PARTIAL_SUPPORT"
    elif has_full:
        summary = "FULL_SUPPORT"
    elif has_contradiction:
        summary = "CONTRADICTORY"
    elif "PARTIAL_SUPPORT" in levels:
        summary = "PARTIAL_SUPPORT"
    elif "NO_SUPPORT" in levels:
        summary = "NO_SUPPORT"
    elif "INSUFFICIENT_INFORMATION" in levels:
        summary = "INSUFFICIENT_INFORMATION"
    else:
        summary = "UNVERIFIABLE"
    def ids(level: str) -> list[str]:
        return sorted(evidence_id(item) for item in eligible
                      if str((item.get("candidate_support") or {}).get("result") or item.get("support_level")) == level)

    source_unit_groups: dict[tuple[str, str], list[str]] = {}
    for item in eligible:
        source_key = (str(item.get("document_id") or item.get("paper_id") or ""),
                      str(item.get("source_unit_id") or ""))
        source_unit_groups.setdefault(source_key, []).append(evidence_id(item))
    same_source_unit_ids = sorted({identity for ids_for_source in source_unit_groups.values()
                                   if len(ids_for_source) > 1 for identity in ids_for_source})
    composition = {
        "record_count": len(eligible),
        "unique_publication_count": len({str(item.get("document_id") or item.get("paper_id"))
                                         for item in eligible}),
        "counts_by_support_result": {level: levels.count(level) for level in _SUPPORT_LEVELS},
        "mixed_support": len(set(levels)) > 1,
        "partial_support_origin": (
            "MIXED_FULL_AND_CONTRADICTORY" if has_full and has_contradiction
            else "RESTRICTED_EVIDENCE" if summary == "PARTIAL_SUPPORT" else None),
    }

    return {
        "support_level": summary,
        "evidence_composition": composition,
        "contradiction_present": has_contradiction,
        "evidence_count": len(eligible),
        "distinct_source_unit_count": len(source_unit_groups),
        "same_source_unit_evidence_ids": same_source_unit_ids,
        "accepted_evidence_ids": sorted(evidence_id(item) for item in eligible),
        "full_evidence_ids": ids("FULL_SUPPORT"),
        "partial_evidence_ids": ids("PARTIAL_SUPPORT"),
        "contradicting_evidence_ids": ids("CONTRADICTORY"),
        "no_support_evidence_ids": ids("NO_SUPPORT"),
        "unverifiable_evidence_ids": ids("UNVERIFIABLE"),
        "insufficient_information_evidence_ids": ids("INSUFFICIENT_INFORMATION"),
        "structurally_blocked_evidence_ids": sorted(evidence_id(item) for item in eligible
            if str((item.get("document_verification") or {}).get("verification_status") or "").startswith("STRUCTURAL_")),
        "technical_error_evidence_ids": sorted(evidence_id(item) for item in eligible
            if ((item.get("document_verification") or {}).get("verification_status") == "TECHNICAL_ERROR")),
        "rejected_evidence": sorted(rejected, key=lambda item: item["evidence_id"]),
        "evidence_records": sorted(eligible, key=lambda item: (
            str(item.get("paper_id") or item.get("document_id") or ""),
            str(item.get("source_unit_id") or ""),
        )),
    }

_ACCEPTED_OUTCOMES: frozenset[str] = frozenset({
    "ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING",
    "ENRICHMENT_V2_ACCEPTED", "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY",
    "ENRICHMENT_V3_ACCEPTED",
})

_ABSTAIN_OUTCOMES: frozenset[str] = frozenset({
    "ENRICHMENT_ABSTAINED", "ENRICHMENT_V2_ABSTAINED",
    "ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS",
    "ENRICHMENT_V3_ABSTAINED",
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
    source_unit_text: str | None = None,
) -> dict[str, Any]:
    """Copia dell'enrichment con il proprio esito di validazione allegato.

    Non muta l'originale e non rimuove nulla: la proposta del modello resta
    integralmente ispezionabile per audit, ma smette di essere indistinguibile
    da una citazione validata.
    """
    outcome = (validation or {}).get("outcome")
    has_quote = bool(
        (enrichment or {}).get("quote") or (enrichment or {}).get("author_claim_quote")
    )
    annotated = {
        **(enrichment or {}),
        "paper_id": paper_id,
        "validation_outcome": outcome,
        "validation_reason_codes": list((validation or {}).get("reason_codes") or []),
        "presentation_state": presentation_state(outcome, has_quote=has_quote),
        "accepted_for_gates": bool(accepted_for_gates),
    }
    if outcome in _ACCEPTED_OUTCOMES and isinstance(source_unit_text, str):
        annotated["source_unit_text"] = source_unit_text
    return annotated


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
    for raw_identifier in candidate.get("document_identifiers") or []:
        for identifier in expand_identifier(raw_identifier):
            for kind in preferred:
                if identifier.get(kind):
                    return f"{kind}:{identifier[kind]}"
    return None


def _candidate_result(results: Any, candidate_id: str) -> dict[str, Any]:
    if isinstance(results, dict):
        value = results.get(candidate_id)
        return value if isinstance(value, dict) else {}
    return {}


def _candidate_pairings(candidate: dict[str, Any]) -> list[dict[str, str]]:
    biomarkers = candidate.get("biomarkers") or []
    genes = [str(item.get("label")) for item in biomarkers
             if str(item.get("type") or "").casefold() == "gene" and item.get("label")]
    pairings = []
    for item in biomarkers:
        if str(item.get("type") or "").casefold() in {"variant", "alteration"} and item.get("label"):
            linked = item.get("linked_gene")
            if linked:
                pairings.append({"gene": str(linked), "alteration": str(item["label"])})
    if not pairings and len(genes) == 1:
        variants = [str(item.get("label")) for item in biomarkers
                    if str(item.get("type") or "").casefold() in {"variant", "alteration"} and item.get("label")]
        if len(variants) == 1:
            pairings.append({"gene": genes[0], "alteration": variants[0]})
    return sorted(pairings, key=lambda item: (item["gene"].casefold(), item["alteration"].casefold()))


def _claim_specificity(candidate: dict[str, Any]) -> str:
    types = {str(item.get("type") or "").casefold() for item in candidate.get("biomarkers") or []}
    if "variant" in types:
        return "VARIANT_LEVEL"
    if "alteration" in types:
        return "GENERIC_OR_ALTERATION_LEVEL"
    if "gene" in types:
        return "GENE_LEVEL"
    return "UNKNOWN"


def _claim_object(candidate: dict[str, Any], family: str, aggregation: dict[str, Any],
                  accepted_records: list[dict[str, Any]], rejected_records: list[dict[str, Any]]) -> dict[str, Any]:
    source_record_ids = sorted({str(value) for value in candidate.get("source_record_ids") or [] if value})
    source_datasets = sorted({str(value) for value in candidate.get("source_datasets") or [] if value})
    document_ids = sorted({str(item.get("document_id") or item.get("paper_id"))
                           for item in accepted_records if item.get("document_id") or item.get("paper_id")})
    source_unit_ids = sorted({str(item.get("source_unit_id")) for item in accepted_records if item.get("source_unit_id")})
    quotes = sorted({str(item.get("quote") or item.get("author_claim_quote"))
                     for item in accepted_records if item.get("quote") or item.get("author_claim_quote")})
    pairings = _candidate_pairings(candidate)
    caveats, uncertainty, conflicts = set(), set(), set()
    for item in accepted_records:
        relation = item.get("observed_relation") or {}
        pairings.extend(relation.get("subject_pairings") or [])
        caveats.update(str(value) for value in relation.get("caveats") or [] if value)
        if relation.get("uncertainty"):
            uncertainty.add(str(relation["uncertainty"]))
        conflicts.update(str(value) for value in relation.get("conflict_markers") or [] if value)
    pairing_map = {(str(item.get("gene")), str(item.get("alteration"))): {
        "gene": str(item.get("gene")), "alteration": str(item.get("alteration"))
    } for item in pairings if isinstance(item, dict) and item.get("gene") and item.get("alteration")}
    semantic_key = candidate.get("semantic_key")
    claim_id = _stable_id("CLAIM", {
        "candidate_id": candidate.get("candidate_id"), "family": family,
        "semantic_key": semantic_key, "subject": candidate.get("subject"),
        "predicate": candidate.get("predicate"), "object": candidate.get("object"),
        "disease": candidate.get("disease") or [], "direction": candidate.get("direction"),
    })
    evidence_ids = [evidence_id(item) for item in accepted_records]
    representative = None
    for level in (aggregation.get("support_level"), "FULL_SUPPORT", "PARTIAL_SUPPORT",
                  "CONTRADICTORY", "NO_SUPPORT", "INSUFFICIENT_INFORMATION", "UNVERIFIABLE"):
        representative = next((item for item in accepted_records
                               if str((item.get("candidate_support") or {}).get("result") or item.get("support_level")) == level), None)
        if representative:
            break
    return {
        "claim_id": claim_id,
        "candidate_id": candidate.get("candidate_id"),
        "candidate_group_candidate_ids": sorted(candidate.get("candidate_group_candidate_ids") or [candidate.get("candidate_id")]),
        "member_semantic_identities": sorted(candidate.get("member_semantic_identities") or [candidate.get("semantic_key") or candidate.get("candidate_id")]),
        "group_graph_paths": candidate.get("group_graph_paths") or [],
        "relation_family": family,
        "relation_origin": candidate.get("relation_origin"),
        "composite_lineage": candidate.get("composite_lineage"),
        "subject": candidate.get("subject"),
        "object": candidate.get("object"),
        "relation": candidate.get("predicate"),
        "disease_context": _labels(candidate.get("disease")),
        "direction": candidate.get("direction"),
        "evidence_type": candidate.get("evidence_scope") or candidate.get("diagnostic_scope"),
        "specificity": _claim_specificity(candidate),
        "gene_variant_pairings": sorted(pairing_map.values(), key=lambda item: (item["gene"], item["alteration"])),
        "status": aggregation.get("support_level"),
        "evidence_composition": aggregation.get("evidence_composition", {}),
        "representative_evidence_id": evidence_id(representative) if representative else None,
        "supporting_evidence_ids": aggregation.get("full_evidence_ids", []),
        "partial_evidence_ids": aggregation.get("partial_evidence_ids", []),
        "contradicting_evidence_ids": aggregation.get("contradicting_evidence_ids", []),
        "no_support_evidence_ids": aggregation.get("no_support_evidence_ids", []),
        "unverifiable_evidence_ids": aggregation.get("unverifiable_evidence_ids", []),
        "insufficient_information_evidence_ids": aggregation.get("insufficient_information_evidence_ids", []),
        "structurally_blocked_evidence_ids": aggregation.get("structurally_blocked_evidence_ids", []),
        "technical_error_evidence_ids": aggregation.get("technical_error_evidence_ids", []),
        "evidence_assessments": [{
            "evidence_id": evidence_id(item),
            "paper_id": item.get("paper_id") or item.get("document_id"),
            "document_id": item.get("document_id") or item.get("paper_id"),
            "source_unit_id": item.get("source_unit_id"),
            "quote_valid": item.get("quote_valid") is True,
            "quote": (item.get("quote") or item.get("author_claim_quote")
                      if item.get("quote_valid") is True else None),
            "support_result": (item.get("candidate_support") or {}).get("result"),
            "verification_status": (item.get("document_verification") or {}).get("verification_status"),
            "support_limitation": (item.get("document_verification") or {}).get("support_limitation"),
            "study_context": (item.get("document_verification") or {}).get("study_context"),
            "applicability_to_case": (item.get("document_verification") or {}).get("applicability_to_case"),
            "reason_codes": (item.get("document_verification") or {}).get("admission_reason_codes") or [],
        } for item in accepted_records],
        "rejected_evidence_ids": sorted(item["evidence_id"] for item in rejected_records),
        "source_record_ids": source_record_ids,
        "source_datasets": source_datasets,
        "semantic_key": semantic_key,
        "graph_path": candidate.get("graph_path") or [],
        "node_ids": candidate.get("node_ids") or [],
        "edge_ids": candidate.get("edge_ids") or [],
        "materialization_rule": candidate.get("materialization_rule") or candidate.get("materialization_rule_id"),
        "document_ids": document_ids,
        "source_unit_ids": source_unit_ids,
        "quotes": quotes,
        "caveats": sorted(caveats),
        "uncertainty": sorted(uncertainty),
        "conflict_markers": sorted(conflicts),
        "contradiction_present": bool(aggregation.get("contradiction_present")),
    }


def _paper_result_fields(result: dict[str, Any]) -> dict[str, Any]:
    """Project existing paper-pipeline records without recomputing them."""
    enrichment = result.get("enrichment") or {}
    validation = result.get("validation") or {}
    support = result.get("candidate_support") or {}
    selected = result.get("selected_source_units") or []
    rejected_quotes = []
    proposed_quote = enrichment.get("author_claim_quote") or enrichment.get("quote")
    if proposed_quote and result.get("quote_valid") is False:
        rejected_quotes.append({
            "quote": proposed_quote,
            "source_unit_id": enrichment.get("source_unit_id"),
            "paper_id": result.get("document_id") or enrichment.get("paper_id"),
        })
    evidence_records = []
    for record in result.get("evidence_records") or []:
        if not isinstance(record, dict):
            continue
        item = dict(record)
        item["evidence_id"] = evidence_id(item)
        valid = item.get("quote_valid") is True or item.get("presentation_state") == VALIDATED_QUOTE
        if not valid:
            item.pop("quote", None)
            item.pop("author_claim_quote", None)
        evidence_records.append(item)
    evidence_records.sort(key=lambda item: (
        str(item.get("paper_id") or item.get("document_id") or ""),
        str(item.get("source_unit_id") or ""),
        str(item.get("validation_outcome") or ""),
    ))
    aggregation = aggregate_evidence_records(evidence_records) if evidence_records else {
        "support_level": "UNVERIFIABLE", "evidence_records": [],
        "rejected_evidence": [], "accepted_evidence_ids": [],
        "full_evidence_ids": [], "partial_evidence_ids": [],
        "contradicting_evidence_ids": [], "contradiction_present": False,
        "no_support_evidence_ids": [], "unverifiable_evidence_ids": [],
        "insufficient_information_evidence_ids": [],
        "structurally_blocked_evidence_ids": [], "technical_error_evidence_ids": [],
    }
    accepted_records = aggregation.get("evidence_records") or []
    rejected_records = aggregation.get("rejected_evidence") or []
    if accepted_records:
        enrichment = accepted_records[0]
        support = enrichment.get("candidate_support") or support
        selected = sorted({str(item.get("source_unit_id")) for item in accepted_records if item.get("source_unit_id")})
    validation_outcome = str(validation.get("outcome") or "")
    quote_is_valid = (
        enrichment.get("quote_valid") is True if accepted_records else
        (result.get("quote_valid") is True
         or str(result.get("quote_validation") or validation.get("outcome") or "").upper() in {"VALIDATED", "QUOTE_VALIDATED"}
         or (validation_outcome.startswith("ENRICHMENT_") and validation_outcome.endswith("ACCEPTED")))
    )
    authorized_quote = enrichment.get("quote") or enrichment.get("author_claim_quote") if accepted_records else None
    if not quote_is_valid:
        authorized_quote = None
    return {
        "pmcid": result.get("pmcid"),
        "source_bibliography": deepcopy(result.get('source_bibliography') or []),
        "document_type": result.get("document_type"),
        "document_source": result.get("document_source"),
        "document_resolution_status": result.get("document_resolution_status") or "UNAVAILABLE",
        "selected_source_units": selected,
        "selected_source_unit_ids": result.get("selected_source_unit_ids") or selected,
        "reader_status": enrichment.get("decision") or result.get("reader_status"),
        "reader_attempts": list(result.get("reader_attempts") or []),
        "reader_decision": enrichment.get("decision") or result.get("reader_decision"),
        "quote": authorized_quote,
        "quote_source_unit_id": enrichment.get("source_unit_id") if accepted_records else result.get("quote_source_unit_id"),
        "representative_document_id": (
            enrichment.get("document_id") or enrichment.get("paper_id") if accepted_records else None
        ),
        "source_unit_text": enrichment.get("source_unit_text"),
        "quote_valid": quote_is_valid,
        "quote_validation": enrichment.get("validation_outcome") if accepted_records else result.get("quote_validation") or validation.get("outcome"),
        "support_fields": result.get("support_fields") or support.get("fields"),
        "support_level": aggregation.get("support_level") or result.get("support_level") or support.get("result"),
        "evidence_composition": aggregation.get("evidence_composition", {}),
        "reason": result.get("reason") or support.get("reason"),
        "support_reason": result.get("support_reason") or result.get("reason") or support.get("reason"),
        # Canonical metadata needed by the narrative verifier to detect a
        # rejected quote without consulting the legacy dossier preview.
        "rejected_quotes": rejected_quotes,
        "audit_only": {"rejected_quotes": rejected_quotes},
        "evidence_records": evidence_records,
        "accepted_evidence_records": accepted_records,
        "rejected_evidence": rejected_records,
        "accepted_evidence_ids": aggregation.get("accepted_evidence_ids", []),
        "full_evidence_ids": aggregation.get("full_evidence_ids", []),
        "partial_evidence_ids": aggregation.get("partial_evidence_ids", []),
        "contradicting_evidence_ids": aggregation.get("contradicting_evidence_ids", []),
        "no_support_evidence_ids": aggregation.get("no_support_evidence_ids", []),
        "unverifiable_evidence_ids": aggregation.get("unverifiable_evidence_ids", []),
        "insufficient_information_evidence_ids": aggregation.get("insufficient_information_evidence_ids", []),
        "structurally_blocked_evidence_ids": aggregation.get("structurally_blocked_evidence_ids", []),
        "technical_error_evidence_ids": aggregation.get("technical_error_evidence_ids", []),
        "contradiction_present": aggregation.get("contradiction_present", False),
        "distinct_source_unit_count": aggregation.get("distinct_source_unit_count", 0),
        "same_source_unit_evidence_ids": aggregation.get("same_source_unit_evidence_ids", []),
    }


def _case_summary(case_context: dict[str, Any]) -> dict[str, Any]:
    biomarkers = case_context.get("biomarkers") or []
    first = biomarkers[0] if biomarkers else {}
    result = {
        "case_id": case_context.get("case_id"),
        "disease": _scalar(case_context.get("disease")),
        "gene": _scalar(first.get("gene")),
        "variant": _scalar(first.get("alteration")),
        "intervention": _scalar(case_context.get("target_intervention")),
        "intent": case_context.get("query_intent"),
    }
    molecular = []
    for item in (case_context.get('entity_resolution') or {}).get('biomarkers') or []:
        observation = item.get('observation') or {}
        if observation.get('fusion_partners'):
            fusion = observation.get('fusion') or {}
            molecular.append({'gene': observation.get('raw_gene'), 'alteration': observation.get('raw_alteration'),
                'fusion_partners': list(observation['fusion_partners']), 'fusion_status': fusion.get('status') or 'UNMAPPED',
                'fusion_concept_ids': fusion.get('concept_ids') or [], 'reason_codes': fusion.get('reasons') or []})
    if molecular:
        result['molecular_resolution'] = molecular
    return result


def _trial_result_fields(result: dict[str, Any]) -> dict[str, Any]:
    availability = str(result.get("availability") or "").upper()
    resolution_status = result.get("trial_resolution_status")
    if not resolution_status:
        if availability == "METADATA_ONLY":
            resolution_status = "AVAILABLE" if result.get("local_cache_path") else "RESOLUTION_FAILED"
        elif availability:
            resolution_status = availability
        else:
            resolution_status = "AVAILABLE" if result else "UNAVAILABLE"
    return {
        "reader_attempts": list(result.get("reader_attempts") or []),
        "declared_nct_id": result.get("declared_nct_id"),
        "resolved_nct_id": result.get("resolved_nct_id"),
        "title": result.get("title"),
        "status": result.get("status") or result.get("overall_status") or result.get("recruitment_status"),
        "phase": result.get("phase") or result.get("phases"),
        "conditions": result.get("conditions") or [],
        "interventions": result.get("interventions") or [],
        "arm_groups": result.get("arm_groups") or [],
        "arm_group_status": result.get("arm_group_status") or "NOT_RECORDED",
        "trial_structure_provenance": result.get("trial_structure_provenance"),
        "biomarker_gene": result.get("biomarker_gene"),
        "source": result.get("source") or "ClinicalTrials.gov",
        "provenance_status": result.get("provenance_status") or (
            "TRIAL_RECORD_RESOLVED" if resolution_status == "AVAILABLE" else
            "TRIAL_RECORD_UNAVAILABLE" if resolution_status == "UNAVAILABLE" else
            f"TRIAL_{resolution_status}"
        ),
        "eligibility_status": result.get("eligibility_status") or "NOT_EVALUATED",
        "trial_resolution_status": resolution_status,
    }


def build_relation_aware_report(
    case_context: dict[str, Any],
    candidates: list[dict[str, Any]],
    paper_results: Any = None,
    trial_results: Any = None,
    *,
    run_status: str = "COMPLETED",
    retrieval_summary: dict[str, Any] | None = None,
    extra_limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Project GCA candidates into a deterministic, provenance-aware report.

    This function is intentionally a projection only: it performs no retrieval,
    document resolution, enrichment, LLM call, or network access.
    """
    paper_evidence: list[dict[str, Any]] = []
    clinical_trials: list[dict[str, Any]] = []
    kg_only_relations: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    limitations: set[str] = set(extra_limitations or [])
    candidate_ids: list[str] = []

    for candidate in sorted(candidates, key=lambda item: str(item.get("candidate_id", ""))):
        candidate_id = candidate["candidate_id"]
        family = classify_relation_family(candidate)
        if family == INVALID_PROVENANCE:
            limitations.add(f"INVALID_PROVENANCE:{candidate_id}")
            continue
        candidate_ids.append(candidate_id)
        graph_provenance = {
            "node_ids": candidate.get("node_ids") or [],
            "edge_ids": candidate.get("edge_ids") or [],
            "graph_path": candidate.get("graph_path") or [],
            "materialization_rule_id": candidate.get("materialization_rule_id"),
        }
        common = {
            "candidate_id": candidate_id,
            "relation_family": family,
            "subject": candidate.get("subject"),
            "relation": candidate.get("predicate"),
            "object": candidate.get("object"),
            "disease_context": _labels(candidate.get("disease")),
            "direction": candidate.get("direction"),
            "evidence_type": candidate.get("evidence_scope") or candidate.get("diagnostic_scope"),
            "graph_provenance": graph_provenance,
        }
        if family == PAPER_EVIDENCE:
            result = _candidate_result(paper_results, candidate_id)
            paper_fields = _paper_result_fields(result)
            aggregation_view = {
                "support_level": paper_fields.get("support_level") or "UNVERIFIABLE",
                "full_evidence_ids": paper_fields.get("full_evidence_ids", []),
                "partial_evidence_ids": paper_fields.get("partial_evidence_ids", []),
                "contradicting_evidence_ids": paper_fields.get("contradicting_evidence_ids", []),
                "no_support_evidence_ids": paper_fields.get("no_support_evidence_ids", []),
                "unverifiable_evidence_ids": paper_fields.get("unverifiable_evidence_ids", []),
                "insufficient_information_evidence_ids": paper_fields.get("insufficient_information_evidence_ids", []),
                "structurally_blocked_evidence_ids": paper_fields.get("structurally_blocked_evidence_ids", []),
                "technical_error_evidence_ids": paper_fields.get("technical_error_evidence_ids", []),
                "contradiction_present": paper_fields.get("contradiction_present", False),
                "distinct_source_unit_count": paper_fields.get("distinct_source_unit_count", 0),
                "same_source_unit_evidence_ids": paper_fields.get("same_source_unit_evidence_ids", []),
            }
            claim = _claim_object(
                candidate, family, aggregation_view,
                paper_fields.get("accepted_evidence_records", []),
                paper_fields.get("rejected_evidence", []),
            )
            declared_document_id = _document_id(candidate)
            resolved_document_id = (
                paper_fields.get("representative_document_id") or result.get("document_id")
            ) if result else None
            paper_evidence.append({
                **common,
                "evidence_type": candidate.get("evidence_scope") or candidate.get("source_properties", {}).get("evidence", {}).get("evidence_type"),
                "document_id": resolved_document_id,
                "declared_source_identity": declared_document_id,
                "resolved_source_identity": resolved_document_id,
                "requested_document_id": result.get("requested_document_id") or declared_document_id,
                "source_type": candidate.get("source_properties", {}).get("evidence", {}).get("source_type"),
                "claim_id": claim["claim_id"],
                "claim": claim,
                "representative_evidence_id": claim.get("representative_evidence_id"),
                **paper_fields,
                "support_status": result.get("support_status") or ("NOT_EVALUATED" if not result else None),
            })
            claims.append(claim)
            if not result:
                limitations.add("PAPER_SUPPORT_NOT_EVALUATED")
            elif paper_fields["support_level"] == "PARTIAL_SUPPORT":
                limitations.add("CANDIDATE_PARTIALLY_SUPPORTED")
            if result and paper_fields["document_resolution_status"] in {
                "UNAVAILABLE", "DOCUMENT_UNAVAILABLE"
            }:
                limitations.add("DOCUMENT_UNAVAILABLE")
            if paper_fields["reader_status"] == "ABSTAIN":
                limitations.add("READER_ABSTAINED")
            if (paper_fields["quote_valid"] is False
                    and paper_fields["reader_status"] != "ABSTAIN"
                    and paper_fields["reader_decision"] != "ABSTAIN"):
                limitations.add("QUOTE_INVALID")
        elif family == CLINICAL_TRIAL:
            result = _candidate_result(trial_results, candidate_id)
            trial_fields = _trial_result_fields(result)
            nct_id = next((item.get("nct") for item in candidate.get("document_identifiers") or [] if item.get("nct")), None)
            trial_claim = {
                "claim_id": _stable_id("CLAIM", {"candidate_id": candidate_id, "family": family,
                                                 "semantic_key": candidate.get("semantic_key"),
                                                 "nct_id": nct_id}),
                "candidate_id": candidate_id,
                "relation_family": family,
                "relation": candidate.get("predicate"),
                "status": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
                "supporting_evidence_ids": [], "partial_evidence_ids": [],
                "contradicting_evidence_ids": [], "rejected_evidence_ids": [],
                "source_record_ids": sorted(candidate.get("source_record_ids") or []),
                "source_datasets": sorted(candidate.get("source_datasets") or []),
                "semantic_key": candidate.get("semantic_key"),
                "graph_path": candidate.get("graph_path") or [],
                "node_ids": candidate.get("node_ids") or [],
                "edge_ids": candidate.get("edge_ids") or [],
                "materialization_rule": candidate.get("materialization_rule") or candidate.get("materialization_rule_id"),
                "document_ids": [nct_id] if nct_id else [], "source_unit_ids": [], "quotes": [],
                "caveats": [], "uncertainty": [], "conflict_markers": [],
                "specificity": _claim_specificity(candidate),
                "gene_variant_pairings": _candidate_pairings(candidate),
            }
            clinical_trials.append({
                **common,
                "nct_id": nct_id,
                "declared_source_identity": nct_id,
                "resolved_source_identity": trial_fields.get("resolved_nct_id"),
                **trial_fields,
                "interventions": trial_fields["interventions"] or _labels(candidate.get("interventions")),
                "biomarker_gene": trial_fields["biomarker_gene"] or _labels(candidate.get("biomarkers")),
                "evidence_interpretation": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
                "claim_id": trial_claim["claim_id"],
                "claim": trial_claim,
            })
            claims.append(trial_claim)
            limitations.add("TRIAL_ASSOCIATION_IS_NOT_EFFICACY_EVIDENCE")
            if (
                trial_fields["trial_resolution_status"] == "UNAVAILABLE"
                or trial_fields["provenance_status"] not in {"TRIAL_RECORD_RESOLVED", "RESOLVED"}
            ):
                limitations.add("TRIAL_RECORD_UNAVAILABLE")
        else:
            properties = candidate.get("source_properties") or {}
            diagnostic = properties.get("device") or properties.get("diagnostic") or {}
            diagnostic_adapter = candidate.get("companion_diagnostic") or {}
            diagnostic_context = {
                key: value for key, value in {
                    "device_id": diagnostic.get("device_id") or diagnostic_adapter.get("identifier"),
                    "device_name": diagnostic.get("device_name") or diagnostic_adapter.get("name"),
                    "drug": diagnostic.get("drug") or diagnostic_adapter.get("associated_drug"),
                    "gene": diagnostic.get("gene") or diagnostic_adapter.get("associated_gene"),
                    "platform_type": diagnostic.get("platform_type") or diagnostic_adapter.get("platform"),
                    "specimen_types": diagnostic.get("specimen_types") or diagnostic_adapter.get("specimen"),
                }.items() if value not in (None, "")
            }
            source_database = (
                properties.get("evidence", {}).get("source_type")
                or properties.get("interaction", {}).get("source_db")
                or properties.get("diagnostic", {}).get("source_db")
                or "KG"
            )
            kg_claim = {
                "claim_id": _stable_id("CLAIM", {"candidate_id": candidate_id, "family": family,
                                                 "semantic_key": candidate.get("semantic_key"),
                                                 "subject": candidate.get("subject"),
                                                 "predicate": candidate.get("predicate"),
                                                 "object": candidate.get("object")}),
                "candidate_id": candidate_id,
                "candidate_group_candidate_ids": sorted(candidate.get("candidate_group_candidate_ids") or [candidate_id]),
                "member_semantic_identities": sorted(candidate.get("member_semantic_identities") or [candidate.get("semantic_key") or candidate_id]),
                "group_graph_paths": candidate.get("group_graph_paths") or [],
                "relation_family": family,
                "relation": candidate.get("predicate"),
                "status": "KG_ONLY",
                "supporting_evidence_ids": [], "partial_evidence_ids": [],
                "contradicting_evidence_ids": [], "rejected_evidence_ids": [],
                "source_record_ids": sorted(candidate.get("source_record_ids") or []),
                "source_datasets": sorted(candidate.get("source_datasets") or []),
                "semantic_key": candidate.get("semantic_key"),
                "graph_path": candidate.get("graph_path") or [],
                "node_ids": candidate.get("node_ids") or [],
                "edge_ids": candidate.get("edge_ids") or [],
                "materialization_rule": candidate.get("materialization_rule") or candidate.get("materialization_rule_id"),
                "document_ids": [], "source_unit_ids": [], "quotes": [],
                "caveats": [], "uncertainty": [], "conflict_markers": [],
                "specificity": _claim_specificity(candidate),
                "gene_variant_pairings": _candidate_pairings(candidate),
            }
            kg_only_relations.append({
                **common,
                "document_id": None,
                "graph_provenance": graph_provenance,
                "source_database": source_database,
                "verification_status": "KG_ONLY",
                "document_provenance": "NOT_AVAILABLE",
                "diagnostic_scope": candidate.get("diagnostic_scope"),
                "diagnostic_context": diagnostic_context,
                "claim_id": kg_claim["claim_id"],
                "claim": kg_claim,
            })
            claims.append(kg_claim)
            limitations.add("DOCUMENT_PROVENANCE_NOT_AVAILABLE")

    accepted_ids = {
        evidence_id(record)
        for entry in paper_evidence
        for record in entry.get("accepted_evidence_records") or []
    }
    rejected_ids = {
        str(record.get("evidence_id"))
        for entry in paper_evidence
        for record in entry.get("rejected_evidence") or []
        if record.get("evidence_id")
    }
    dossier_record_ids = {
        evidence_id(record)
        for entry in paper_evidence
        for record in entry.get("evidence_records") or []
    }
    accounted_ids = accepted_ids | rejected_ids
    reconciliation = {
        "accepted_input_records": len(accepted_ids),
        "rejected_input_records": len(rejected_ids),
        "dossier_accepted_records": len(accepted_ids & dossier_record_ids),
        "dossier_rejected_records": len(rejected_ids & dossier_record_ids),
        "missing_accepted_records": len(accepted_ids - dossier_record_ids),
        "unsupported_dossier_records": len(dossier_record_ids - accounted_ids),
        "unaccounted_records": len(dossier_record_ids - accounted_ids),
    }
    report = {
        "run_status": run_status,
        "case_summary": _case_summary(case_context),
        "retrieval_summary": {
            "total_candidates": len(candidate_ids),
            "paper_candidates": len(paper_evidence),
            "trial_candidates": len(clinical_trials),
            "kg_only_candidates": len(kg_only_relations),
            **(retrieval_summary or {}),
        },
        "paper_evidence": paper_evidence,
        "clinical_trials": clinical_trials,
        "kg_only_relations": kg_only_relations,
        "claims": sorted(claims, key=lambda item: str(item.get("claim_id") or "")),
        "aggregation_reconciliation": reconciliation,
        "limitations": sorted(limitations),
        "provenance_summary": {
            "candidate_ids": sorted(candidate_ids),
            "paper_document_ids": sorted(
                entry["document_id"] for entry in paper_evidence if entry.get("document_id")
            ),
            "trial_ids": sorted(
                entry["nct_id"] for entry in clinical_trials if entry.get("nct_id")
            ),
            "graph_only_candidate_ids": sorted(
                entry["candidate_id"] for entry in kg_only_relations
            ),
        },
    }

    from .observations import project_documentary_findings
    return project_documentary_findings(report)
