"""Runtime-only joins of GCA4 evidence-profile and evidence-drug source edges.

These are derived propositions, not additional raw source units. A join is
permitted only on one shared Evidence ID with identical disease, direction and
document identifiers. Both original candidate identities remain traceable.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping


def _family(candidate: dict[str, Any]) -> str:
    return str(candidate.get("semantic_key") or "").split("|", 1)[0]


def _union(first: dict[str, Any], second: dict[str, Any], field: str) -> list[str]:
    return sorted({str(value) for candidate in (first, second)
                   for value in candidate.get(field) or [] if value})


def derive_composite_relations(
    source_candidates: Mapping[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    """Join GCA4 source candidates without changing their semantic accounting."""
    profiles: dict[str, list[dict[str, Any]]] = {}
    for candidate in source_candidates.values():
        if _family(candidate) != "EVIDENCE_STATEMENT":
            continue
        for evidence_id in candidate.get("evidence_record_ids") or []:
            profiles.setdefault(str(evidence_id), []).append(candidate)

    derived: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, str]] = []
    for drug_edge in sorted(source_candidates.values(), key=lambda row: row["candidate_id"]):
        if _family(drug_edge) != "EVIDENCE_DRUG":
            continue
        evidence_ids = [str(value) for value in drug_edge.get("evidence_record_ids") or []]
        profile_rows = profiles.get(evidence_ids[0], []) if len(evidence_ids) == 1 else []
        reason = None
        if len(evidence_ids) != 1 or len(profile_rows) != 1:
            reason = "COMPOSITE_JOIN_NOT_UNIQUE"
        else:
            profile = profile_rows[0]
            if profile.get("disease") != drug_edge.get("disease"):
                reason = "COMPOSITE_DISEASE_MISMATCH"
            elif profile.get("direction") != drug_edge.get("direction"):
                reason = "COMPOSITE_DIRECTION_MISMATCH"
            elif profile.get("document_identifiers") != drug_edge.get("document_identifiers"):
                reason = "COMPOSITE_DOCUMENT_MISMATCH"
        if reason:
            excluded.append({"candidate_id": drug_edge["candidate_id"], "reason": reason})
            continue

        profile = profile_rows[0]
        identity = f"{profile['candidate_id']}|{drug_edge['candidate_id']}|{evidence_ids[0]}"
        candidate_id = "GCA4-DERIVED-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        if candidate_id in derived:
            excluded.append({"candidate_id": drug_edge["candidate_id"], "reason": "COMPOSITE_ID_COLLISION"})
            continue
        composed = dict(drug_edge)
        composed.update({
            "candidate_id": candidate_id,
            "semantic_key": f"COMPOSITE_EVIDENCE_RELATION|{evidence_ids[0]}|{drug_edge['candidate_id']}",
            "relation_origin": "DERIVED_COMPOSITE",
            "candidate_version": "runtime-derived/1.0",
            "materialization_rule": "runtime/composite_evidence_join/1.0",
            "materialization_rule_id": "runtime/composite_evidence_join/1.0",
            "subject": profile.get("subject"),
            "biomarkers": list(profile.get("biomarkers") or []),
            "entity_resolution": profile.get("entity_resolution"),
            "source_record_ids": _union(profile, drug_edge, "source_record_ids"),
            "source_datasets": _union(profile, drug_edge, "source_datasets"),
            "edge_ids": _union(profile, drug_edge, "edge_ids"),
            "node_ids": _union(profile, drug_edge, "node_ids"),
            "graph_path": list(profile.get("graph_path") or []) + [str((drug_edge.get("object") or {}).get("id") or "")],
            "source_properties": {
                **(drug_edge.get("source_properties") or {}),
                "profile": (profile.get("source_properties") or {}).get("profile") or {},
            },
            "composite_lineage": {
                "profile_candidate_id": profile["candidate_id"],
                "evidence_drug_candidate_id": drug_edge["candidate_id"],
                "shared_evidence_id": evidence_ids[0],
                "profile_semantic_key": profile.get("semantic_key"),
                "evidence_drug_semantic_key": drug_edge.get("semantic_key"),
                "profile_graph_path": profile.get("graph_path") or [],
                "evidence_drug_graph_path": drug_edge.get("graph_path") or [],
            },
        })
        derived[candidate_id] = composed
    return derived, excluded
