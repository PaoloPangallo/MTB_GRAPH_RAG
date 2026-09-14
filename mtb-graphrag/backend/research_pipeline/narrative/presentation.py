"""Assemble the narrative presentation from canonical facts and verified prose."""

from __future__ import annotations

from typing import Any

from ..dossier.builder import PRESENTABLE_AS_AUTHOR_CLAIM
from .input_projection import NARRATIVE_CRITICAL_WARNINGS

PRESENTATION_CONTRACT_VERSION = "narrative-presentation/2.2"
DOCUMENTARY_EVIDENCE_AVAILABLE = "DOCUMENTARY_EVIDENCE_AVAILABLE"
NO_VALIDATED_DOCUMENTARY_EVIDENCE = "NO_VALIDATED_DOCUMENTARY_EVIDENCE"
SOURCE_DOES_NOT_SUPPORT = "SOURCE_DOES_NOT_SUPPORT"
CONTRADICTORY_DOCUMENTARY_EVIDENCE = "CONTRADICTORY_DOCUMENTARY_EVIDENCE"
AMBIGUOUS_DOCUMENTARY_STATE = "AMBIGUOUS_DOCUMENTARY_STATE"

DOCUMENTARY_STATE_LABELS = {
    DOCUMENTARY_EVIDENCE_AVAILABLE: "Documentazione validata disponibile",
    NO_VALIDATED_DOCUMENTARY_EVIDENCE: "Nessun supporto documentale validato",
    SOURCE_DOES_NOT_SUPPORT: "La fonte non supporta la relazione",
    CONTRADICTORY_DOCUMENTARY_EVIDENCE: "Evidenza documentale contraddittoria",
    AMBIGUOUS_DOCUMENTARY_STATE: "Stato documentale non conclusivo",
}


def documentary_state_label(state: str) -> str:
    """Human-facing wording that does not imply positive clinical support."""
    return DOCUMENTARY_STATE_LABELS.get(state, state)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _label(value: Any) -> str | None:
    if isinstance(value, dict):
        return _text(value.get("label") or value.get("name")) or None
    if isinstance(value, str):
        return _text(value) or None
    return None


def _validated_sources(entry: dict[str, Any]) -> list[dict[str, Any]]:
    selected = {
        value for value in ((entry.get("document_support") or {}).get("selected_papers") or [])
        if isinstance(value, str) and value
    }
    validated: dict[str, list[dict[str, Any]]] = {paper_id: [] for paper_id in selected}
    for context in entry.get("author_context") or []:
        if context.get("presentation_state") not in PRESENTABLE_AS_AUTHOR_CLAIM:
            continue
        paper_id = _text(context.get("paper_id"))
        quote = _text(context.get("author_claim_quote"))
        if paper_id in selected and quote:
            validated[paper_id].append({
                "paper_id": paper_id,
                "source_unit_id": _text(context.get("source_unit_id")),
                "quote_available": True,
                "validated_quote": quote,
                "source_unit_text": _text(context.get("source_unit_text")) or None,
            })
    sources: list[dict[str, Any]] = []
    for paper_id in sorted(selected):
        sources.extend(validated[paper_id] or [{
            "paper_id": paper_id,
            "source_unit_id": "",
            "quote_available": False,
            "validated_quote": None,
            "source_unit_text": None,
        }])
    return sources


def _documentary_state(entry: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    direction = _text(((entry.get("gate_results") or {}).get("support_mask") or {}).get("direction"))
    if direction == "CONTRADICTED":
        return CONTRADICTORY_DOCUMENTARY_EVIDENCE
    if direction == "SOURCE_DOES_NOT_SUPPORT":
        return SOURCE_DOES_NOT_SUPPORT
    if direction in {"UNRELATED_EVIDENCE", "NEUTRAL", "UNVERIFIABLE"}:
        return AMBIGUOUS_DOCUMENTARY_STATE
    if any(source["quote_available"] for source in sources):
        return DOCUMENTARY_EVIDENCE_AVAILABLE
    if direction == "NO_DOCUMENT_SIGNAL" or "NO_VALIDATED_ENRICHMENT_AVAILABLE" in (entry.get("warnings") or []):
        return NO_VALIDATED_DOCUMENTARY_EVIDENCE
    return AMBIGUOUS_DOCUMENTARY_STATE


def _critical_notices(entry: dict[str, Any]) -> list[str]:
    warnings = [value for value in entry.get("warnings") or [] if isinstance(value, str)]
    notices = [value for value in warnings if value in NARRATIVE_CRITICAL_WARNINGS]
    for context in entry.get("author_context") or []:
        if context.get("presentation_state") == "ABSTAINED":
            reason = _text(context.get("abstention_reason"))
            if reason:
                notices.append(f"ABSTENTION: {reason}")
    return notices


def _relation_sources(entry: dict[str, Any], branch: str) -> list[dict[str, Any]]:
    if branch == "PAPER":
        paper_id = _text(entry.get("document_id"))
        if not paper_id:
            return []
        quote_available = entry.get("quote_valid") is True and bool(_text(entry.get("quote")))
        return [{
            "paper_id": paper_id,
            "source_unit_id": _text(entry.get("quote_source_unit_id")) if quote_available else "",
            "quote_available": quote_available,
            "validated_quote": _text(entry.get("quote")) if quote_available else None,
            "source_unit_text": _text(entry.get("source_unit_text")) or None
            if quote_available else None,
        }]
    if branch == "TRIAL":
        nct_id = _text(entry.get("nct_id"))
        return ([{"paper_id": nct_id, "source_unit_id": "", "quote_available": False,
                  "validated_quote": None, "source_unit_text": None}] if nct_id else [])
    source_database = _text(entry.get("source_database"))
    return ([{"paper_id": source_database, "source_unit_id": "", "quote_available": False,
              "validated_quote": None, "source_unit_text": None}] if source_database else [])


def _relation_documentary_state(
    entry: dict[str, Any], branch: str, sources: list[dict[str, Any]],
) -> str:
    if branch == "KG_ONLY":
        return NO_VALIDATED_DOCUMENTARY_EVIDENCE
    if branch == "TRIAL":
        return (
            DOCUMENTARY_EVIDENCE_AVAILABLE
            if _text(entry.get("trial_resolution_status")) == "RESOLVED"
            else NO_VALIDATED_DOCUMENTARY_EVIDENCE
        )
    support_level = _text(entry.get("support_level"))
    direction = _text((entry.get("support_fields") or {}).get("direction"))
    if support_level == "CONTRADICTORY" or direction == "CONTRADICTED":
        return CONTRADICTORY_DOCUMENTARY_EVIDENCE
    if support_level == "NO_SUPPORT" or direction == "SOURCE_DOES_NOT_SUPPORT":
        return SOURCE_DOES_NOT_SUPPORT
    if support_level in {"UNVERIFIABLE", "CONTEXT_ONLY"} or direction in {
        "UNRELATED_EVIDENCE", "NEUTRAL", "UNVERIFIABLE",
    }:
        return AMBIGUOUS_DOCUMENTARY_STATE
    if any(source["quote_available"] for source in sources):
        return DOCUMENTARY_EVIDENCE_AVAILABLE
    return NO_VALIDATED_DOCUMENTARY_EVIDENCE


def _relation_candidates(canonical_dossier: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        *(("PAPER", entry) for entry in canonical_dossier.get("paper_evidence") or []),
        *(("TRIAL", entry) for entry in canonical_dossier.get("clinical_trials") or []),
        *(("KG_ONLY", entry) for entry in canonical_dossier.get("kg_only_relations") or []),
    ]


def build_narrative_presentation(
    canonical_dossier: dict[str, Any],
    narrative: dict[str, Any] | None,
    verification: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a fresh view model; attach generated prose only after PASS."""
    verified = bool(verification and verification.get("status") == "PASS" and narrative)
    explanations = ({
        item.get("candidate_id"): item.get("text")
        for item in ((narrative or {}).get("candidate_narratives") or [])
        if isinstance(item, dict) and isinstance(item.get("candidate_id"), str)
    } if verified else {})
    candidates = []
    relation_entries = _relation_candidates(canonical_dossier)
    if relation_entries:
        for branch, entry in relation_entries:
            candidate_id = _text(entry.get("candidate_id"))
            sources = _relation_sources(entry, branch)
            status = (
                _text(entry.get("support_level") or entry.get("support_status"))
                if branch == "PAPER" else
                _text(entry.get("trial_resolution_status") or entry.get("provenance_status"))
                if branch == "TRIAL" else
                _text(entry.get("verification_status"))
            )
            notices = (
                ["TRIAL_ASSOCIATION_IS_NOT_EFFICACY_EVIDENCE"]
                if branch == "TRIAL" else
                ["DOCUMENT_PROVENANCE_NOT_AVAILABLE"] if branch == "KG_ONLY" else []
            )
            candidates.append({
                "candidate_id": candidate_id,
                "intervention": _label(entry.get("object")),
                "graph_relation": _text(entry.get("relation")),
                "canonical_status": status or "NOT_EVALUATED",
                "support_direction": _text(
                    (entry.get("support_fields") or {}).get("direction")
                    or entry.get("direction")
                ),
                "documentary_support_state": _relation_documentary_state(entry, branch, sources),
                "sources": sources,
                "critical_notices": notices,
                "generated_explanation": explanations.get(candidate_id),
            })
    else:
        for entry in canonical_dossier.get("candidate_therapies") or []:
            mask = (entry.get("gate_results") or {}).get("support_mask") or {}
            sources = _validated_sources(entry)
            candidate_id = _text(entry.get("candidate_id"))
            candidates.append({
                "candidate_id": candidate_id,
                "intervention": entry.get("drug"),
                "graph_relation": _text(entry.get("graph_relation")),
                "canonical_status": _text(entry.get("status")),
                "support_direction": _text(mask.get("direction")),
                "documentary_support_state": _documentary_state(entry, sources),
                "sources": sources,
                "critical_notices": _critical_notices(entry),
                "generated_explanation": explanations.get(candidate_id),
            })
    return {
        "contract_version": PRESENTATION_CONTRACT_VERSION,
        "presentation_mode": "VERIFIED_NARRATIVE" if verified else "STRUCTURED_DOSSIER_FALLBACK",
        "summary": (narrative or {}).get("narrative_summary") if verified else None,
        "candidates": candidates,
        "canonical_limitations": [x for x in canonical_dossier.get("limitations") or [] if isinstance(x, str)],
        "limitations_explanation": (narrative or {}).get("limitations_summary") if verified else None,
        "closing_note": (narrative or {}).get("closing_note") if verified else None,
        "verification": {
            "status": (verification or {}).get("status"),
            "reason_codes": list((verification or {}).get("reason_codes") or []),
            "verifier_version": (verification or {}).get("verifier_version"),
            "narrative_hash": (verification or {}).get("narrative_hash"),
            "input_hash": (verification or {}).get("input_hash"),
        },
    }
