"""Deterministic retrieval: verified CaseContext -> GraphCandidateAssertion
matches -> documents -> SourceUnit. No LLM involved anywhere in this module.

The "KG" queried here is the already-materialized, static
`GraphCandidateAssertion` repository (benchmarks/mtb_evidence/
document_grounded_claims/graph_candidate_repository/2.0/candidates.jsonl) --
see docs/end_to_end_pipeline_pilot/current_component_audit.md for why a live
Neo4j query was out of scope for this research-only pilot. Retrieval is
additionally restricted to candidates that already have at least one of the
25 frozen, already-cached EvidenceBundle (benchmarks/mtb_evidence/
document_grounded_claims/evidence_bundle/evidence_bundles.jsonl) so that no
new document is ever fetched.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from backend.research_pipeline.data_access import candidates_path, evidence_bundles_path
from backend.research_pipeline.documents.authorized_cache import expand_identifier

# I percorsi arrivano da ``data_access``, non da ``Path(__file__).parents[n]``:
# la profondità di questo file è cambiata con la promozione, e un percorso
# derivato dalla posizione del sorgente si sarebbe rotto in silenzio.

MAX_ASSOCIATIONS_PER_CASE = 3
MAX_DOCUMENTS_PER_ASSOCIATION = 2
MAX_SOURCE_UNITS_PER_DOCUMENT = 4


def _live_provenance_bundles(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Build document descriptors from GCA provenance, never from gold units."""
    descriptors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in candidate.get("document_identifiers") or []:
        for identifier in expand_identifier(raw):
            kind_value = next(
                ((kind, str(identifier.get(kind)).strip()) for kind in ("pmid", "pmcid", "nct", "doi", "url")
                 if identifier.get(kind)),
                None,
            )
            if kind_value is None:
                continue
            kind, value = kind_value
            normalized = value.upper() if kind in {"pmid", "pmcid", "nct"} else value.lower()
            document_id = f"{kind}:{normalized}"
            if document_id in seen:
                continue
            seen.add(document_id)
            descriptors.append({
                "bundle_id": f"live:{candidate['candidate_id']}:{document_id}",
                "document_id": document_id,
                "provenance_identifier": {kind: normalized},
                "bundle_type": "PROVENANCE_DOCUMENT",
                "source_unit_ids": [],
            })
    return descriptors


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _labels(items: list[dict]) -> set[str]:
    return {_norm(item.get("label")) for item in items if item.get("label")}


def _term_matches(term: str, label: str) -> bool:
    """Substring match, or a shared meaningful token (>2 chars) -- covers common clinical
    abbreviation overlap such as case term "microsatellite instability (msi)" against
    candidate label "msi high" without a hardcoded synonym table."""
    if not term or not label:
        return False
    if term in label or label in term:
        return True
    shared = {token for token in term.split() if len(token) > 2} & {token for token in label.split() if len(token) > 2}
    return bool(shared)


@lru_cache(maxsize=1)
def load_candidates() -> dict[str, dict]:
    # ``candidates.jsonl`` pesa 72,5 MB e il dataset è congelato: rileggerlo a
    # ogni run costava ~3 s per chiamata e rendeva l'endpoint inutilizzabile.
    # La cache è invalidabile con ``load_candidates.cache_clear()`` nei test che
    # cambiano ``RESEARCH_PIPELINE_DATA_ROOT``.
    return {row["candidate_id"]: row for row in (json.loads(line) for line in candidates_path().read_text(encoding="utf-8").splitlines() if line.strip())}


@lru_cache(maxsize=1)
def load_bundles_by_candidate() -> dict[str, list[dict]]:
    by_candidate: dict[str, list[dict]] = {}
    for line in evidence_bundles_path().read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        by_candidate.setdefault(row["candidate_id"], []).append(row)
    return by_candidate


def _match_candidate(case_context: dict[str, Any], candidate: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    case_disease = _norm((case_context.get("disease") or {}).get("normalized_value") or (case_context.get("disease") or {}).get("raw_value"))
    candidate_disease = _labels(candidate.get("disease") or [])
    disease_ok = bool(case_disease) and any(case_disease in cd or cd in case_disease for cd in candidate_disease)
    if not disease_ok:
        reasons.append("DISEASE_NOT_COMPATIBLE")

    # Use every textual field the parser populated for each biomarker (gene, normalized
    # value, raw value), not just the gene symbol alone: for pan-genomic category
    # biomarkers without a true gene (e.g. "MSI-High"), the parser sometimes puts a
    # descriptive word in `gene` (observed: "microsatellite") that alone loses the
    # abbreviation/qualifier ("MSI"/"High") carried by normalized_value -- matching
    # against the union of fields is more robust than trusting a single field.
    case_biomarker_terms = {
        _norm(value)
        for b in (case_context.get("biomarkers") or [])
        for value in (b.get("gene"), b.get("normalized_value"), b.get("raw_value"))
        if value
    }
    candidate_biomarker_labels = _labels(candidate.get("biomarkers") or [])
    gene_ok = bool(case_biomarker_terms) and any(any(_term_matches(term, label) for label in candidate_biomarker_labels) for term in case_biomarker_terms)
    if not gene_ok:
        reasons.append("BIOMARKER_GENE_NOT_COMPATIBLE")

    intent = case_context.get("query_intent")
    intervention_ok = True
    if intent == "THERAPY_EVALUATION":
        target = case_context.get("target_intervention") or {}
        target_value = _norm(target.get("normalized_value") or target.get("raw_value"))
        candidate_interventions = _labels(candidate.get("interventions") or [])
        intervention_ok = bool(target_value) and any(target_value in label or label in target_value for label in candidate_interventions)
        if not intervention_ok:
            reasons.append("TARGET_INTERVENTION_NOT_COMPATIBLE")

    ok = disease_ok and gene_ok and intervention_ok
    if ok:
        reasons = ["DISEASE_COMPATIBLE", "BIOMARKER_COMPATIBLE"] + (["INTERVENTION_COMPATIBLE"] if intent == "THERAPY_EVALUATION" else ["DISCOVERY_NO_INTERVENTION_FILTER"])
    return ok, reasons


def retrieve(case_context: dict[str, Any], *, document_mode: str = "REPLAY") -> dict[str, Any]:
    candidates = load_candidates()
    bundles_by_candidate = load_bundles_by_candidate()
    if document_mode not in {"LIVE", "REPLAY"}:
        raise ValueError(f"unsupported document mode: {document_mode!r}")
    authorized_candidate_ids = sorted(
        cid for cid, candidate in candidates.items()
        if (document_mode == "LIVE" and candidate.get("document_identifiers"))
        or (document_mode == "REPLAY" and cid in bundles_by_candidate)
    )

    matched: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for candidate_id in authorized_candidate_ids:
        candidate = candidates[candidate_id]
        ok, reasons = _match_candidate(case_context, candidate)
        record = {"candidate_id": candidate_id, "reason_codes": reasons}
        if ok:
            matched.append(record)
        else:
            excluded.append(record)

    accepted = matched[:MAX_ASSOCIATIONS_PER_CASE]
    capped_out = [{"candidate_id": item["candidate_id"], "reason_codes": ["MAX_ASSOCIATIONS_PER_CASE_EXCEEDED"]} for item in matched[MAX_ASSOCIATIONS_PER_CASE:]]

    associations = []
    for item in accepted:
        candidate_id = item["candidate_id"]
        candidate = candidates[candidate_id]
        bundles = (
            _live_provenance_bundles(candidate)
            if document_mode == "LIVE"
            else sorted(bundles_by_candidate.get(candidate_id, []), key=lambda b: b["bundle_id"])
        )
        associations.append({
            "candidate_id": candidate_id, "candidate": candidate, "match_reason_codes": item["reason_codes"],
            "available_bundles": [{"bundle_id": b["bundle_id"], "document_id": b["document_id"], "bundle_type": b.get("bundle_type"), "source_unit_ids": b.get("source_unit_ids", [])[:MAX_SOURCE_UNITS_PER_DOCUMENT], **({"provenance_identifier": b["provenance_identifier"]} if document_mode == "LIVE" else {})} for b in bundles],
        })

    return {
        "query_intent": case_context.get("query_intent"),
        "associations": associations,
        "excluded_candidates": excluded + capped_out,
        "no_match": len(associations) == 0,
    }
