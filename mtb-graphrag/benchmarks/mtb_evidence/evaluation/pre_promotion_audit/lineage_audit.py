"""Lineage delle sostituzioni e stato dei claim ritirati.

Due sostituzioni diverse convivono nella 1.3 e vanno tenute distinte, perche'
sbagliano in modi diversi se vengono confuse:

**Terminologia** (evidence:1851, evidence:1853). Cambia la rappresentazione
canonica e quindi l'ID. Non cambia la proposizione: l'aggregato resta non
separabile e il numero di claim non si muove. Il letterale della fonte resta.

**Restringimento di scope** (evidence:1846, evidence:1847). Cambia il disease
scope e quindi l'ID. Cambia cio' che il claim afferma — dice meno di prima — ed
e' esattamente per questo che il vecchio va ritirato e non aggiornato.

Tre parent non hanno nessun sostituto (evidence:347, evidence:3811,
evidence:4759). Non e' una lacuna della lineage: e' una decisione presa nelle
fasi precedenti, e un audit che li trattasse come righe mancanti chiederebbe di
inventare i claim che quelle fasi hanno rifiutato di creare.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

TERMINOLOGY_ORIGIN = "terminology_canonicalization"
SCOPE_NARROWING_ORIGIN = "diagnostic_disease_scope_narrowing"

TERMINOLOGY_RECORDS = ("evidence:1851", "evidence:1853")
SCOPE_NARROWING_RECORDS = ("evidence:1846", "evidence:1847")
RECORDS_WITHOUT_REPLACEMENT = ("evidence:347", "evidence:3811", "evidence:4759")

TERMINOLOGY_REASON = "CANONICAL_INTERVENTION_LABEL_UPDATED_BY_VERIFIED_TERMINOLOGY"

# Cio' che una riga di lineage deve portare perche' la sostituzione sia
# reversibile da chi non era presente quando e' stata decisa.
REQUIRED_LINEAGE_FIELDS = (
    "effective_repository_version",
    "graph_evidence_id",
    "new_claim_id",
    "old_claim_id",
    "parent_id",
    "reason_code",
    "reversible",
    "review_status",
)

VERIFIED_SOURCE_LITERAL = "BGJ398"
VERIFIED_CANONICAL_LABEL = "infigratinib"


def _deprecation_rows(repository: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["claim_id"]: row for row in repository["deprecated"]}


def terminology_rows(repository: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Righe di lineage della canonicalizzazione, con i controlli semantici."""
    retired = _deprecation_rows(repository)
    active = {claim["claim_id"]: claim for claim in repository["claims"]}
    rows: list[dict[str, Any]] = []
    for row in repository["lineage"]:
        old = retired.get(row["old_claim_id"], {})
        new = active.get(row["new_claim_id"], {})
        literals = list(new.get("source_literal_members") or old.get("aggregate_members_literal") or ())
        rows.append(
            {
                "aggregate_semantics_unchanged": bool(
                    old.get("claim_type") == new.get("claim_type")
                    and old.get("biomarker") == new.get("biomarker")
                    and old.get("disease_scope") == new.get("disease_scope")
                    and old.get("direction") == new.get("direction")
                    and old.get("polarity") == new.get("polarity")
                    and new.get("permits_member_specific_claims") is False
                ),
                "canonical_label_after": row.get("canonical_label_after"),
                "canonical_label_before": row.get("canonical_label_before"),
                "canonical_label_uses_verified_term": VERIFIED_CANONICAL_LABEL
                in str(row.get("canonical_label_after") or ""),
                "decision_source": row.get("terminology_decision_id"),
                "graph_evidence_id": row["graph_evidence_id"],
                "lineage_kind": TERMINOLOGY_ORIGIN,
                "missing_fields": sorted(
                    field for field in REQUIRED_LINEAGE_FIELDS if not row.get(field)
                ),
                "new_claim_id": row["new_claim_id"],
                "new_claim_is_active": row["new_claim_id"] in active,
                "old_claim_id": row["old_claim_id"],
                "old_claim_is_retired": row["old_claim_id"] in retired,
                "parent_id": row["parent_id"],
                "reason_code": row.get("reason_code"),
                "repository_version": row.get("effective_repository_version"),
                "reversible": bool(row.get("reversible")),
                "source_literal_preserved": VERIFIED_SOURCE_LITERAL in literals,
                "source_literals": sorted(literals),
            }
        )
    return sorted(rows, key=lambda row: row["old_claim_id"])


def scope_narrowing_rows(repository: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Sostituzioni diagnostiche, ricostruite dal piano di view e dai ritirati.

    La 1.3 non riemette la mappa di sostituzione diagnostica: la porta dalla 1.2
    dentro il piano di rigenerazione delle view. Ricostruirla da li' e' cio' che
    rende la lineage completa senza rileggere la 1.2, che questa fase non tocca.
    """
    retired = _deprecation_rows(repository)
    active = {claim["claim_id"]: claim for claim in repository["claims"]}
    rows: list[dict[str, Any]] = []
    for action in repository["view_plan"]:
        if action["action"] != "regenerate_diagnostic_view":
            continue
        old_id = action["old_claim_id"]
        new_id = action["claim_id"]
        old = retired.get(old_id, {})
        new = active.get(new_id, {})
        rows.append(
            {
                "decision_source": (new.get("provenance") or {})
                .get("scope_narrowing", {})
                .get("source_review_id"),
                "disease_scope_after": new.get("disease_scope"),
                "disease_scope_before": old.get("disease_scope"),
                "graph_evidence_id": action["graph_evidence_id"],
                "lineage_kind": SCOPE_NARROWING_ORIGIN,
                "narrowed_not_broadened": str(old.get("disease_scope") or "")
                in str(new.get("disease_scope") or "")
                or str(new.get("disease_scope") or "").endswith(
                    str(old.get("disease_scope") or "")
                ),
                "new_claim_id": new_id,
                "new_claim_is_active": new_id in active,
                "old_claim_id": old_id,
                "old_claim_is_retired": old_id in retired,
                "parent_id": action["parent_id"],
                "reason_code": (new.get("provenance") or {})
                .get("scope_narrowing", {})
                .get("reason_code"),
                "repository_version": old.get("effective_repository_version")
                or action.get("carried_from_repository_version"),
                "reversible": bool(old),
            }
        )
    return sorted(rows, key=lambda row: row["old_claim_id"])


def no_replacement_rows(repository: Mapping[str, Any]) -> list[dict[str, Any]]:
    """I tre parent senza sostituto, dichiarati invece che dedotti da un'assenza."""
    by_record = {
        parent["graph_evidence_id"]: parent for parent in repository["parents"]
    }
    rows = []
    for record in RECORDS_WITHOUT_REPLACEMENT:
        parent = by_record.get(record, {})
        rows.append(
            {
                "active_claims": len(parent.get("child_claim_ids") or ()),
                "graph_evidence_id": record,
                "lineage_kind": "no_replacement",
                "parent_id": parent.get("parent_id"),
                "parent_present": bool(parent),
                "provenance_retained": bool(parent.get("provenance")),
                "reason": "nessuna fase ha materializzato un claim da questo record",
                "unresolved_association_ids": sorted(
                    parent.get("unresolved_association_ids") or ()
                ),
                "unsupported_association_ids": sorted(
                    parent.get("unsupported_association_ids") or ()
                ),
            }
        )
    return rows


def lineage_rows(repository: Mapping[str, Any]) -> list[dict[str, Any]]:
    return (
        terminology_rows(repository)
        + scope_narrowing_rows(repository)
        + no_replacement_rows(repository)
    )


def _retired_never_rankable(
    repository: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Nessun ritirato puo' essere primario o eleggibile al ranking finale.

    Il controllo qui e' documentale — i ritirati portano `deprecated: true` e non
    compaiono fra gli attivi. La verifica comportamentale, cioe' che il gate li
    tenga fuori dal bucket primario anche con tutti gli assi exact, sta
    nell'audit dei gate: sono due affermazioni diverse e nessuna delle due
    sostituisce l'altra.
    """
    retired = repository["deprecated"]
    active_ids = {claim["claim_id"] for claim in repository["claims"]}
    return {
        "all_retired_flagged_deprecated": all(
            row.get("deprecated") is True for row in retired
        ),
        "retired_claims": len(retired),
        "retired_present_in_active_set": sorted(
            row["claim_id"] for row in retired if row["claim_id"] in active_ids
        ),
        "retired_with_replacement": sorted(
            row["claim_id"] for row in retired if row.get("replacement_claim_id")
        ),
        "retired_without_replacement": sorted(
            row["claim_id"] for row in retired if not row.get("replacement_claim_id")
        ),
    }


def audit(repository: Mapping[str, Any]) -> dict[str, Any]:
    terminology = terminology_rows(repository)
    narrowing = scope_narrowing_rows(repository)
    absent = no_replacement_rows(repository)
    rows = terminology + narrowing

    incomplete = [row for row in terminology if row["missing_fields"]]
    broken = [
        row
        for row in rows
        if not (row["old_claim_is_retired"] and row["new_claim_is_active"])
    ]
    irreversible = [row for row in rows if not row["reversible"]]

    return {
        "graph_records_covered": sorted(
            {row["graph_evidence_id"] for row in rows}
            | {row["graph_evidence_id"] for row in absent}
        ),
        "lineage_complete": bool(
            not incomplete
            and not broken
            and not irreversible
            and sorted(row["graph_evidence_id"] for row in terminology)
            == sorted(TERMINOLOGY_RECORDS)
            and sorted(row["graph_evidence_id"] for row in narrowing)
            == sorted(SCOPE_NARROWING_RECORDS)
            and all(row["parent_present"] for row in absent)
        ),
        "records_without_replacement": [
            row["graph_evidence_id"] for row in absent
        ],
        "records_without_replacement_all_present": all(
            row["parent_present"] for row in absent
        ),
        "replacements_broken": [row["old_claim_id"] for row in broken],
        "replacements_irreversible": [row["old_claim_id"] for row in irreversible],
        "replacements_with_missing_fields": [
            {"missing": row["missing_fields"], "old_claim_id": row["old_claim_id"]}
            for row in incomplete
        ],
        "retired_claim_status": _retired_never_rankable(repository, rows),
        "scope_narrowing": {
            "expected_records": sorted(SCOPE_NARROWING_RECORDS),
            "narrowed_not_broadened": all(row["narrowed_not_broadened"] for row in narrowing),
            "observed_records": sorted(row["graph_evidence_id"] for row in narrowing),
            "replacements": len(narrowing),
        },
        "terminology": {
            "aggregate_semantics_unchanged": all(
                row["aggregate_semantics_unchanged"] for row in terminology
            ),
            "canonical_label_uses_verified_term": all(
                row["canonical_label_uses_verified_term"] for row in terminology
            ),
            "expected_records": sorted(TERMINOLOGY_RECORDS),
            "observed_records": sorted(row["graph_evidence_id"] for row in terminology),
            "reason_code_uniform": {row["reason_code"] for row in terminology}
            == {TERMINOLOGY_REASON},
            "replacements": len(terminology),
            "source_literal_preserved": all(
                row["source_literal_preserved"] for row in terminology
            ),
        },
    }


__all__ = [
    "RECORDS_WITHOUT_REPLACEMENT",
    "REQUIRED_LINEAGE_FIELDS",
    "SCOPE_NARROWING_RECORDS",
    "TERMINOLOGY_RECORDS",
    "audit",
    "lineage_rows",
    "no_replacement_rows",
    "scope_narrowing_rows",
    "terminology_rows",
]
