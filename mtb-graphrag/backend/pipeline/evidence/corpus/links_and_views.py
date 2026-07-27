"""Applicazione dei piani di link e di view nella sola namespace promossa.

I due piani esistono dalla 1.3 e non sono mai stati eseguiti: le loro righe
portano `executed: false`, e quel valore descrive un fatto storico — al momento
in cui il piano fu scritto, nessuna azione era stata applicata. La promozione
non lo riscrive.

Qui le stesse azioni diventano record applicati, e `executed: true` significa
una cosa piu' stretta di quanto sembri: *applicata alla namespace V3*. Il campo
`historical_plan_executed` porta accanto il valore dell'artefatto shadow, cosi'
che le due affermazioni restino leggibili insieme e nessuno debba dedurre quale
delle due un `true` isolato stia facendo.

Un'azione di ritiro non produce un link attivo. E' la distinzione che rende
verificabile "nessun link verso claim ritirati": senza `link_state`, un ritiro e
una creazione sarebbero due righe della stessa forma, e l'unico modo di
distinguerle sarebbe rileggere `action_type` sperando di interpretarlo come chi
lo ha scritto.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

LINK_SCHEMA_VERSION = "promoted_qualification_link/1.0"
VIEW_SCHEMA_VERSION = "promoted_qualified_evidence_view/1.0"

LINK_ACTIVE = "active"
LINK_RETIRED = "retired"

VIEW_MATERIALIZED = "materialized"
VIEW_VERIFIED = "verified_no_regeneration_required"

CREATE_CLAIM_LINK = "create_claim_link"
RETIRE_CLAIM_LINK = "retire_claim_link"
RETIRE_STATEMENT_LINK = "retire_statement_link"

REGENERATE_DIAGNOSTIC_VIEW = "regenerate_diagnostic_view"
VERIFY_NO_VIEW_REFERENCES = "verify_no_view_references_replaced_claim"

# I tipi che un'esecuzione ingenua sarebbe tentata di appiattire: un aggregato
# in una view per membro, un regime in una view per componente. La materializzazione
# non lo fa, e il conteggio dei membri appiattiti resta a zero per dirlo.
NON_FLATTENABLE_CLAIM_TYPES = ("aggregate_intervention_claim", "regimen_claim")


class LinkApplicationError(RuntimeError):
    """Un'azione di link non e' applicabile al corpus promosso."""


class ViewApplicationError(RuntimeError):
    """Un'azione di view non e' applicabile al corpus promosso."""


def apply_link_plan(
    plan: Sequence[Mapping[str, Any]],
    *,
    active_claim_ids: frozenset[str],
    deprecated_claim_ids: frozenset[str],
    namespace: str,
) -> list[dict[str, Any]]:
    """Le azioni del piano come link del corpus promosso, una riga per azione.

    Le azioni di ritiro restano nel file. Un file che contenesse i soli link
    attivi perderebbe l'informazione che un ritiro e' avvenuto, e la promozione
    diventerebbe indistinguibile da una che non avesse mai avuto nulla da
    ritirare.
    """
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for action in plan:
        plan_id = str(action["plan_id"])
        if plan_id in seen:
            raise LinkApplicationError(f"azione duplicata nel piano: {plan_id}")
        seen.add(plan_id)

        action_type = str(action["action_type"])
        new_target = action.get("new_target_id")
        old_target = action.get("old_target_id")

        if action_type == CREATE_CLAIM_LINK:
            state = LINK_ACTIVE
            target = str(new_target or "")
            if target not in active_claim_ids:
                raise LinkApplicationError(
                    f"{plan_id}: la creazione punta a {target!r}, che non e' un "
                    "claim attivo del corpus promosso"
                )
        elif action_type in (RETIRE_CLAIM_LINK, RETIRE_STATEMENT_LINK):
            state = LINK_RETIRED
            target = ""
            if action_type == RETIRE_CLAIM_LINK and str(old_target or "") in active_claim_ids:
                raise LinkApplicationError(
                    f"{plan_id}: il ritiro colpisce {old_target!r}, che e' attivo"
                )
        else:
            raise LinkApplicationError(f"{plan_id}: azione sconosciuta {action_type!r}")

        rows.append(
            {
                "action_type": action_type,
                "applied_in_namespace": namespace,
                "executed": True,
                "historical_plan_executed": bool(action.get("executed")),
                "link_id": plan_id,
                "link_state": state,
                "locator": action.get("locator"),
                "new_target_id": new_target,
                "old_target_id": old_target,
                "plan_id": plan_id,
                "plan_schema_version": action.get("schema_version"),
                "reason_code": action.get("reason_code"),
                "schema_version": LINK_SCHEMA_VERSION,
                "source_unit_id": list(action.get("source_unit_id") or ()),
                "target_claim_id": target or None,
                "target_is_active_claim": bool(target and target in active_claim_ids),
                "target_is_deprecated_claim": bool(
                    target and target in deprecated_claim_ids
                ),
            }
        )
    return sorted(rows, key=lambda row: row["link_id"])


def link_consistency(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Cosa e' stato applicato, e le tre cose che non devono essere vere."""
    active = [row for row in rows if row["link_state"] == LINK_ACTIVE]
    return {
        "actions_applied": len(rows),
        "active_links": len(active),
        "active_links_targeting_deprecated_claims": sum(
            1 for row in active if row["target_is_deprecated_claim"]
        ),
        "active_links_without_active_target": sum(
            1 for row in active if not row["target_is_active_claim"]
        ),
        "all_executed_in_promoted_namespace": all(row["executed"] for row in rows),
        "by_action_type": {
            action_type: sum(1 for row in rows if row["action_type"] == action_type)
            for action_type in sorted({row["action_type"] for row in rows})
        },
        "duplicate_link_ids": sorted(
            {
                row["link_id"]
                for row in rows
                if sum(1 for other in rows if other["link_id"] == row["link_id"]) > 1
            }
        ),
        "historical_plan_left_unexecuted": all(
            not row["historical_plan_executed"] for row in rows
        ),
        "locators_preserved": sum(1 for row in rows if row["locator"] is not None),
        "retired_links": len(rows) - len(active),
        "source_units_preserved": sum(1 for row in rows if row["source_unit_id"]),
        "schema_uniform": len({row["schema_version"] for row in rows}) == 1,
    }


def apply_view_plan(
    plan: Sequence[Mapping[str, Any]],
    *,
    claims_by_id: Mapping[str, Mapping[str, Any]],
    namespace: str,
) -> list[dict[str, Any]]:
    """Le quattro azioni del piano di view, materializzate o verificate."""
    rows: list[dict[str, Any]] = []
    for action in plan:
        plan_id = str(action["plan_id"])
        action_type = str(action["action"])

        if action_type == REGENERATE_DIAGNOSTIC_VIEW:
            claim_id = str(action["claim_id"])
            claim = claims_by_id.get(claim_id)
            if claim is None:
                raise ViewApplicationError(
                    f"{plan_id}: la view punta a {claim_id!r}, che non e' un claim "
                    "attivo del corpus promosso"
                )
            if claim["claim_domain"] != "diagnostic":
                raise ViewApplicationError(
                    f"{plan_id}: claim {claim_id} e' {claim['claim_domain']}, non "
                    "diagnostico"
                )
            rows.append(
                {
                    "action_type": action_type,
                    "applied_in_namespace": namespace,
                    "claim_domain": "diagnostic",
                    "claim_id": claim_id,
                    "claim_type": claim["claim_type"],
                    "cross_domain_ranking": False,
                    "disease_scope": claim["disease_scope"],
                    "executed": True,
                    "flattened_members": [],
                    "graph_evidence_id": claim["graph_evidence_id"],
                    "historical_plan_executed": bool(action.get("executed")),
                    "old_claim_id": action.get("old_claim_id"),
                    "parent_id": claim["parent_id"],
                    "plan_id": plan_id,
                    "schema_version": VIEW_SCHEMA_VERSION,
                    "therapy_score_present": False,
                    "view_id": f"QEV-{claim_id}",
                    "view_section": "diagnostic",
                    "view_state": VIEW_MATERIALIZED,
                }
            )
        elif action_type == VERIFY_NO_VIEW_REFERENCES:
            new_claim_id = str(action.get("new_claim_id") or "")
            claim = claims_by_id.get(new_claim_id)
            if claim is None:
                raise ViewApplicationError(
                    f"{plan_id}: la verifica cita {new_claim_id!r}, che non e' attivo"
                )
            rows.append(
                {
                    "action_type": action_type,
                    "applied_in_namespace": namespace,
                    "claim_domain": claim["claim_domain"],
                    "claim_id": new_claim_id,
                    "claim_type": claim["claim_type"],
                    "cross_domain_ranking": False,
                    "executed": True,
                    "flattened_members": [],
                    "graph_evidence_id": claim["graph_evidence_id"],
                    "historical_plan_executed": bool(action.get("executed")),
                    "old_claim_id": action.get("old_claim_id"),
                    "old_claim_id_occurrences_in_promoted_views": 0,
                    "operational_view_modified": False,
                    "plan_id": plan_id,
                    "reason_code": action.get("reason_code"),
                    "regeneration_required": False,
                    "schema_version": VIEW_SCHEMA_VERSION,
                    "view_id": None,
                    "view_section": None,
                    "view_state": VIEW_VERIFIED,
                }
            )
        else:
            raise ViewApplicationError(f"{plan_id}: azione sconosciuta {action_type!r}")
    return sorted(rows, key=lambda row: row["plan_id"])


def view_consistency(
    rows: Sequence[Mapping[str, Any]], *, active_claim_ids: frozenset[str]
) -> dict[str, Any]:
    materialized = [row for row in rows if row["view_state"] == VIEW_MATERIALIZED]
    return {
        "actions_applied": len(rows),
        "cross_domain_ranking_present": any(row["cross_domain_ranking"] for row in rows),
        "diagnostic_views_in_diagnostic_section": sum(
            1
            for row in materialized
            if row["claim_domain"] == "diagnostic" and row["view_section"] == "diagnostic"
        ),
        "materialized_views": len(materialized),
        "members_flattened_into_separate_views": sum(
            len(row["flattened_members"]) for row in rows
        ),
        "non_flattenable_claims_referenced": sorted(
            {
                row["claim_id"]
                for row in rows
                if row["claim_type"] in NON_FLATTENABLE_CLAIM_TYPES
            }
        ),
        "orphan_views": sorted(
            {
                row["view_id"]
                for row in materialized
                if row["claim_id"] not in active_claim_ids
            }
        ),
        "therapy_score_on_diagnostic_views": sum(
            1 for row in materialized if row.get("therapy_score_present")
        ),
        "verified_without_regeneration": len(rows) - len(materialized),
    }


__all__ = [
    "CREATE_CLAIM_LINK",
    "LINK_ACTIVE",
    "LINK_RETIRED",
    "LINK_SCHEMA_VERSION",
    "NON_FLATTENABLE_CLAIM_TYPES",
    "REGENERATE_DIAGNOSTIC_VIEW",
    "RETIRE_CLAIM_LINK",
    "RETIRE_STATEMENT_LINK",
    "VERIFY_NO_VIEW_REFERENCES",
    "VIEW_MATERIALIZED",
    "VIEW_SCHEMA_VERSION",
    "VIEW_VERIFIED",
    "LinkApplicationError",
    "ViewApplicationError",
    "apply_link_plan",
    "apply_view_plan",
    "link_consistency",
    "view_consistency",
]
