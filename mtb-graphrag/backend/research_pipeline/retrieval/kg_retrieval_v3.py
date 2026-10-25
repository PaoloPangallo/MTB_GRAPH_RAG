"""Retrieval su ``graph_candidate_repository/3.0``.

Differenze rispetto al retrieval v2, tutte conseguenza del contratto v3:

* la query usa **solo i campi verificati dal gate**: menzioni negate, rifiutate
  per tipo o contenute in istruzioni di controllo non entrano;
* l'alterazione è confrontata con l'AST, non con una stringa: ``A AND B``
  richiede entrambi i termini;
* l'intervento tiene conto della struttura: un regime irrisolto non produce un
  match esatto;
* la polarità della fonte determina il **ramo**, non l'esclusione: una candidate
  ``DOES_NOT_SUPPORT`` è conservata nel ramo negativo invece di sparire.

Nessun LLM è coinvolto.
"""

from __future__ import annotations

from typing import Any

from .admission import (
    BRANCH_POSITIVE, CandidateRuntimeAdmission, evaluate_candidate, split_branches,
)
from .repository_v3 import load_v3_candidates

RETRIEVAL_V3_VERSION = "kg-retrieval/3.0"

MAX_ASSOCIATIONS_PER_CASE = 3
MAX_AUDIT_ASSOCIATIONS_PER_CASE = 3


def _norm(value: Any) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _disease_compatible(candidate: dict[str, Any], disease: str | None) -> bool:
    if not disease:
        return False
    case_value = _norm(disease)
    for entry in candidate.get("disease") or []:
        label = _norm(entry.get("label"))
        if label and (case_value in label or label in case_value):
            return True
    return False


def _gene_compatible(candidate: dict[str, Any], genes: list[str]) -> bool:
    if not genes:
        return False
    labels = {_norm(b.get("label")) for b in candidate.get("biomarkers") or [] if b.get("label")}
    terms = {_norm(g) for g in genes if g}
    for term in terms:
        for label in labels:
            if not term or not label:
                continue
            if term in label or label in term:
                return True
            shared = ({t for t in term.split() if len(t) > 2}
                      & {t for t in label.split() if len(t) > 2})
            if shared:
                return True
    return False


def retrieve(
    verified_fields: dict[str, Any],
    query_intent: str | None,
    bundles_by_candidate: dict[str, list[dict]] | None = None,
) -> dict[str, Any]:
    """Retrieval deterministico su v3, a partire dai campi **verificati**."""
    candidates = load_v3_candidates()
    bundles_by_candidate = bundles_by_candidate or {}

    # Come in v2, il retrieval resta ristretto alle candidate per cui esiste un
    # EvidenceBundle già in cache: nessun documento nuovo viene mai richiesto.
    scope = sorted(cid for cid in candidates if cid in bundles_by_candidate) \
        if bundles_by_candidate else sorted(candidates)

    admissions: list[CandidateRuntimeAdmission] = []
    structurally_excluded: list[dict[str, Any]] = []

    disease = verified_fields.get("disease")
    genes = verified_fields.get("genes") or []

    for candidate_id in scope:
        candidate = candidates[candidate_id]
        if not _disease_compatible(candidate, disease):
            structurally_excluded.append({
                "candidate_id": candidate_id, "reason_codes": ["DISEASE_NOT_COMPATIBLE"]})
            continue
        if not _gene_compatible(candidate, genes):
            structurally_excluded.append({
                "candidate_id": candidate_id, "reason_codes": ["BIOMARKER_GENE_NOT_COMPATIBLE"]})
            continue
        admissions.append(evaluate_candidate(candidate, verified_fields, query_intent))

    branches = split_branches(admissions)
    positive = [a for a in admissions if a.is_positive]
    audit_only = [a for a in admissions if a.is_audit_only and not a.is_positive]
    rejected = [a for a in admissions if a.is_rejected]

    def _association(admission: CandidateRuntimeAdmission) -> dict[str, Any]:
        candidate = candidates[admission.candidate_id]
        bundles = sorted(bundles_by_candidate.get(admission.candidate_id, []),
                         key=lambda b: b["bundle_id"])
        return {
            "candidate_id": admission.candidate_id,
            "candidate": candidate,
            "admission": admission.to_dict(),
            "available_bundles": [
                {"bundle_id": b["bundle_id"], "document_id": b["document_id"],
                 "bundle_type": b.get("bundle_type"),
                 "source_unit_ids": b.get("source_unit_ids", [])[:4]}
                for b in bundles
            ],
        }

    associations = [_association(a) for a in positive[:MAX_ASSOCIATIONS_PER_CASE]]
    audit_associations = [_association(a) for a in audit_only[:MAX_AUDIT_ASSOCIATIONS_PER_CASE]]

    return {
        "repository_version": "3.0",
        "retrieval_version": RETRIEVAL_V3_VERSION,
        "query_intent": query_intent,
        "query_fields": {
            "disease": disease, "genes": genes,
            "alterations": verified_fields.get("alterations") or [],
            "target_intervention": verified_fields.get("target_intervention"),
        },
        "associations": associations,
        "audit_only_associations": audit_associations,
        "excluded_candidates": structurally_excluded + [
            {"candidate_id": a.candidate_id, "reason_codes": a.reason_codes}
            for a in rejected
        ],
        "branches": branches,
        "counts": {
            "considered": len(scope),
            "structurally_excluded": len(structurally_excluded),
            "evaluated": len(admissions),
            "positive": len(positive),
            "audit_only": len(audit_only),
            "rejected": len(rejected),
        },
        "no_match": len(associations) == 0,
    }
