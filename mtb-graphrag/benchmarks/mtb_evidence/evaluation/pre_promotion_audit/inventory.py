"""Inventario e riconciliazione parent/claim, derivati dai file.

Il manifest della 1.3 dichiara i propri conteggi. Questo modulo li ricalcola dai
JSONL e li mette accanto ai dichiarati: se coincidono e' un fatto verificato, se
divergono e' un finding. Un audit che si limitasse a rileggere il manifest
verificherebbe soltanto che il manifest e' uguale a se stesso.

La riconciliazione e' per parent, non per claim, perche' il parent e' l'unita'
che sopravvive a ogni sostituzione: un claim ritirato cambia ID, il contenitore
di provenienza no.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

# Conteggi attesi dalla fase 1.3. Sono scritti qui per essere *confrontati* con
# quelli derivati, non per essere copiati dentro l'output.
EXPECTED_COUNTS = {
    "active_claims_total": 148,
    "aggregate_claims": 3,
    "atomic_claims": 140,
    "diagnostic_claims": 2,
    "parents": 147,
    "parents_without_claims": 3,
    "prognostic_claims": 0,
    "regimen_claims": 3,
    "therapeutic_claims": 146,
    "unresolved_associations": 6,
    "unsupported_associations": 6,
}

# I tre parent che nessuna fase ha sostituito. Sono nominati perche' restino
# nominati: un parent senza claim che diventasse anonimo tornerebbe a sembrare
# una perdita di dati invece di una decisione.
PARENTS_WITHOUT_CLAIMS = ("evidence:347", "evidence:3811", "evidence:4759")


def derived_counts(repository: Mapping[str, Any]) -> dict[str, Any]:
    """Conteggi ricalcolati dai file della 1.3."""
    claims = repository["claims"]
    parents = repository["parents"]
    by_type = Counter(claim["claim_type"] for claim in claims)
    by_domain = Counter(claim["claim_domain"] for claim in claims)
    return {
        "active_claims_total": len(claims),
        "aggregate_claims": by_type["aggregate_intervention_claim"],
        "atomic_claims": by_type["atomic_intervention_claim"],
        "by_claim_type": dict(sorted(by_type.items())),
        "by_claim_domain": dict(sorted(by_domain.items())),
        "deprecated_claims": len(repository["deprecated"]),
        "diagnostic_claims": by_domain["diagnostic"],
        "parents": len(parents),
        "parents_without_claims": sum(
            1 for parent in parents if not parent.get("child_claim_ids")
        ),
        "prognostic_claims": by_domain["prognostic"],
        "regimen_claims": by_type["regimen_claim"],
        "replacement_lineage_rows": len(repository["lineage"]),
        "therapeutic_claims": by_domain["therapeutic"],
        "unresolved_associations": len(repository["unresolved"]),
        "unsupported_associations": len(repository["unsupported"]),
    }


def _split_files_agree(repository: Mapping[str, Any]) -> dict[str, Any]:
    """I file per dominio devono partizionare esattamente `evidence_claims`."""
    union = (
        {claim["claim_id"] for claim in repository["therapeutic"]}
        | {claim["claim_id"] for claim in repository["diagnostic"]}
        | {claim["claim_id"] for claim in repository["prognostic"]}
    )
    active = {claim["claim_id"] for claim in repository["claims"]}
    overlaps = (
        {claim["claim_id"] for claim in repository["therapeutic"]}
        & {claim["claim_id"] for claim in repository["diagnostic"]}
    )
    return {
        "domain_files_partition_active_claims": union == active and not overlaps,
        "in_domain_files_not_in_active": sorted(union - active),
        "in_active_not_in_domain_files": sorted(active - union),
        "overlapping_between_domain_files": sorted(overlaps),
    }


def structural_integrity(repository: Mapping[str, Any]) -> dict[str, Any]:
    """Le quattro rotture possibili del grafo parent/claim, cercate una a una."""
    claims = repository["claims"]
    parents = repository["parents"]
    parent_ids = {parent["parent_id"] for parent in parents}
    claim_ids = {claim["claim_id"] for claim in claims}
    children_by_parent = {
        parent["parent_id"]: set(parent.get("child_claim_ids") or ())
        for parent in parents
    }
    deprecated_ids = {row["claim_id"] for row in repository["deprecated"]}

    orphans = sorted(
        claim["claim_id"] for claim in claims if claim["parent_id"] not in parent_ids
    )
    dangling = sorted(
        f"{parent['graph_evidence_id']}->{child}"
        for parent in parents
        for child in (parent.get("child_claim_ids") or ())
        if child not in claim_ids
    )
    unlisted = sorted(
        claim["claim_id"]
        for claim in claims
        if claim["claim_id"] not in children_by_parent.get(claim["parent_id"], set())
    )
    deprecated_still_active = sorted(deprecated_ids & claim_ids)
    flagged_deprecated = sorted(
        claim["claim_id"] for claim in claims if claim.get("deprecated")
    )
    return {
        "claims_flagged_deprecated_inside_active_set": flagged_deprecated,
        "claims_not_listed_by_their_parent": unlisted,
        "dangling_child_references": dangling,
        "deprecated_claims_present_in_active_set": deprecated_still_active,
        "no_orphan_claims": not orphans,
        "orphan_claims": orphans,
        "parent_child_graph_consistent": not (orphans or dangling or unlisted),
    }


def reconciliation_rows(repository: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Una riga per parent: attivi, ritirati, non sostenuti, irrisolti, legacy."""
    claims_by_parent: dict[str, list[dict[str, Any]]] = {}
    for claim in repository["claims"]:
        claims_by_parent.setdefault(claim["parent_id"], []).append(claim)

    deprecated_by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in repository["deprecated"]:
        deprecated_by_parent.setdefault(row["parent_id"], []).append(row)

    unsupported_by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in repository["unsupported"]:
        unsupported_by_parent.setdefault(row["parent_id"], []).append(row)

    unresolved_by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in repository["unresolved"]:
        unresolved_by_parent.setdefault(row["parent_id"], []).append(row)

    replacement_by_old = {
        row["old_claim_id"]: row["new_claim_id"] for row in repository["lineage"]
    }

    rows: list[dict[str, Any]] = []
    for parent in repository["parents"]:
        parent_id = parent["parent_id"]
        active = sorted(
            claim["claim_id"] for claim in claims_by_parent.get(parent_id, ())
        )
        retired = sorted(
            row["claim_id"] for row in deprecated_by_parent.get(parent_id, ())
        )
        legacy = sorted(
            {
                statement
                for claim in claims_by_parent.get(parent_id, ())
                for statement in (claim.get("legacy_statement_ids") or ())
            }
            | set(parent.get("deprecated_statement_ids") or ())
        )
        rows.append(
            {
                "active_claim_ids": active,
                "active_claims": len(active),
                "declared_child_claim_ids": sorted(parent.get("child_claim_ids") or ()),
                "child_list_matches_active_claims": sorted(
                    parent.get("child_claim_ids") or ()
                )
                == active,
                "graph_evidence_id": parent["graph_evidence_id"],
                "has_no_active_claim": not active,
                "legacy_statement_lineage": legacy,
                "parent_id": parent_id,
                "replacements_from_this_parent": sorted(
                    f"{old}->{new}"
                    for old, new in replacement_by_old.items()
                    if old in retired
                ),
                "retired_claim_ids": retired,
                "retired_claims": len(retired),
                "source_ids": sorted(parent.get("source_ids") or ()),
                "unresolved_association_ids": sorted(
                    row["association_id"] for row in unresolved_by_parent.get(parent_id, ())
                ),
                "unsupported_association_ids": sorted(
                    row["association_id"]
                    for row in unsupported_by_parent.get(parent_id, ())
                ),
            }
        )
    return sorted(rows, key=lambda row: row["graph_evidence_id"])


def audit(repository: Mapping[str, Any]) -> dict[str, Any]:
    """Inventario completo: derivato, dichiarato e differenza fra i due."""
    derived = derived_counts(repository)
    declared = dict(repository["manifest"]["counts"])
    comparable = {
        key: value for key, value in derived.items() if key in EXPECTED_COUNTS
    }
    mismatches = {
        key: {"declared": EXPECTED_COUNTS[key], "derived": value}
        for key, value in comparable.items()
        if value != EXPECTED_COUNTS[key]
    }
    manifest_mismatches = {
        key: {"manifest": declared[key], "derived": derived[key]}
        for key in sorted(set(declared) & set(derived))
        if declared[key] != derived[key]
    }
    parents_without = sorted(
        parent["graph_evidence_id"]
        for parent in repository["parents"]
        if not parent.get("child_claim_ids")
    )
    integrity = structural_integrity(repository)
    return {
        "audit_derived_counts": derived,
        "counts_match_expected": not mismatches,
        "counts_match_manifest": not manifest_mismatches,
        "count_mismatches_vs_expected": mismatches,
        "count_mismatches_vs_manifest": manifest_mismatches,
        "declared_manifest_counts": declared,
        "domain_file_partition": _split_files_agree(repository),
        "expected_counts": dict(EXPECTED_COUNTS),
        "inventory_consistent": bool(
            not mismatches
            and not manifest_mismatches
            and integrity["parent_child_graph_consistent"]
            and not integrity["deprecated_claims_present_in_active_set"]
            and not integrity["claims_flagged_deprecated_inside_active_set"]
            and parents_without == sorted(PARENTS_WITHOUT_CLAIMS)
            and _split_files_agree(repository)["domain_files_partition_active_claims"]
        ),
        "parents_without_claims_expected": sorted(PARENTS_WITHOUT_CLAIMS),
        "parents_without_claims_observed": parents_without,
        "parents_without_claims_match": parents_without
        == sorted(PARENTS_WITHOUT_CLAIMS),
        "structural_integrity": integrity,
    }


def reconciliation_totals(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Somma delle righe di riconciliazione, per chiudere il conto."""
    return {
        "active_claims": sum(row["active_claims"] for row in rows),
        "parents": len(rows),
        "parents_without_active_claim": sum(
            1 for row in rows if row["has_no_active_claim"]
        ),
        "retired_claims": sum(row["retired_claims"] for row in rows),
        "unresolved_associations": sum(
            len(row["unresolved_association_ids"]) for row in rows
        ),
        "unsupported_associations": sum(
            len(row["unsupported_association_ids"]) for row in rows
        ),
    }


__all__ = [
    "EXPECTED_COUNTS",
    "PARENTS_WITHOUT_CLAIMS",
    "audit",
    "derived_counts",
    "reconciliation_rows",
    "reconciliation_totals",
    "structural_integrity",
]
