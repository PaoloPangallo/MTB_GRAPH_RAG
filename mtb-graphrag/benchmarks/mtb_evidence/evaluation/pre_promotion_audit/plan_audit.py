"""Coerenza del piano di rigenerazione dei link e delle view.

Le 37 azioni di link e le 4 di view non sono state eseguite. L'audit verifica
che *se venissero eseguite* non lascerebbero il corpus in uno stato incoerente:
nessun link verso un claim ritirato, nessun duplicato, nessuna view orfana,
nessun oggetto tipizzato appiattito.

Le 4 azioni di view meritano una spiegazione, perche' il numero sembra sbagliato
finche' non si guarda che cosa fanno. Due sono rigenerazioni vere, dei due claim
diagnostici il cui scope e' stato ristretto. Le altre due **non rigenerano
niente**: verificano che le view operative non nominino ne' il vecchio ne' il
nuovo ID dei due claim terminologici. Le view operative sono infatti indicizzate
per legacy statement, non per claim ID, quindi i due claim canonicalizzati non
vi compaiono — e il modo di dimostrarlo e' contare le occorrenze, non assumerle.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

RETIRE_ACTIONS = ("retire_statement_link", "retire_claim_link")
CREATE_ACTIONS = ("create_claim_link",)

REGENERATE_VIEW = "regenerate_diagnostic_view"
VERIFY_VIEW = "verify_no_view_references_replaced_claim"

TERMINOLOGY_REASON = "CANONICAL_INTERVENTION_LABEL_UPDATED_BY_VERIFIED_TERMINOLOGY"

EXPECTED_LINK_ACTIONS = 37
EXPECTED_VIEW_ACTIONS = 4
EXPECTED_TERMINOLOGY_RETIRE = 2
EXPECTED_TERMINOLOGY_CREATE = 2

# Un piano che appiattisse un aggregato o un regime su un intervento singolo
# rifarebbe, al momento della scrittura, l'errore che il modello tipizzato
# esiste per eliminare. I due flag sono verificati riga per riga.
FLATTENING_FLAGS = ("atomization_performed", "clinical_qualifiers_invented")

# Il piano e' stato scritto in tre fasi e ne porta tre schemi. Le differenze
# sono reali e vanno nominate invece che appianate leggendo solo i campi comuni:
#
#   1.0  create   `locator_count` intero, nessun array `locators`
#   1.2  create   array `locators`, `source_unit_id` **al singolare**
#   1.3  create   entrambi, piu' `source_unit_ids` al plurale
#   1.0  retire   ne' locator ne' source unit: ritira un link a uno statement
#
# Chi eseguira' il piano dovra' gestire tutte e tre le forme, e `source_unit_id`
# contro `source_unit_ids` e' esattamente la differenza che un esecutore
# distratto perde in silenzio.
LOCATOR_EXEMPT_ACTIONS = ("retire_statement_link",)


def declared_source_units(action: Mapping[str, Any]) -> list[str]:
    """Source unit dichiarate dall'azione, in qualunque delle due forme."""
    plural = tuple(action.get("source_unit_ids") or ())
    singular = action.get("source_unit_id")
    return sorted({str(item) for item in plural} | ({str(singular)} if singular else set()))


def declared_locators(action: Mapping[str, Any]) -> int | None:
    """Numero di locator dichiarati, o `None` se l'azione non ne dichiara.

    Le due forme non vengono sommate: quando entrambe sono presenti devono
    coincidere, ed e' quella coincidenza che il campo `locator_forms_agree`
    verifica.
    """
    array = action.get("locators")
    count = action.get("locator_count")
    if array is None and count is None:
        return None
    if array is None:
        return int(count)
    return len(array)


def _row_schema(action: Mapping[str, Any]) -> str:
    if action["action"] in LOCATOR_EXEMPT_ACTIONS:
        return "statement_link_retirement"
    has_array = action.get("locators") is not None
    has_count = action.get("locator_count") is not None
    if has_array and has_count:
        return "locator_array_and_count"
    if has_array:
        return "locator_array_only"
    if has_count:
        return "locator_count_only"
    return "no_locator_declaration"


def link_rows(repository: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Una riga per azione di link, con il verdetto su ciascun invariante."""
    active = {claim["claim_id"]: claim for claim in repository["claims"]}
    retired = {row["claim_id"] for row in repository["deprecated"]}
    rows: list[dict[str, Any]] = []
    for action in repository["link_plan"]:
        claim_id = action.get("claim_id")
        target = active.get(claim_id or "")
        creates = action["action"] in CREATE_ACTIONS
        units = declared_source_units(action)
        locators = declared_locators(action)
        array = action.get("locators")
        count = action.get("locator_count")
        rows.append(
            {
                "action": action["action"],
                "claim_id": claim_id,
                "claim_type": action.get("claim_type"),
                "executed": bool(action.get("executed")),
                "flattening_flags_set": sorted(
                    flag for flag in FLATTENING_FLAGS if action.get(flag)
                ),
                "graph_evidence_id": action.get("graph_evidence_id"),
                "locator_evidence_present": bool(locators)
                or action["action"] in LOCATOR_EXEMPT_ACTIONS,
                "locator_forms_agree": (
                    len(array) == int(count) if array is not None and count is not None else True
                ),
                "locators_declared": locators,
                "plan_id": action["plan_id"],
                "reason_code": action.get("reason_code"),
                "replaces_claim_id": action.get("replaces_claim_id"),
                "row_schema": _row_schema(action),
                "source_unit_ids": units,
                "source_units_match_claim": (units == sorted(target.get("source_unit_ids") or ()))
                if creates and target is not None
                else None,
                "targets_active_claim": bool(target) if creates else None,
                "targets_retired_claim": bool(claim_id and claim_id in retired),
                "terminology_decision_id": action.get("terminology_decision_id"),
            }
        )
    return sorted(rows, key=lambda row: row["plan_id"])


def link_reconciliation(repository: Mapping[str, Any]) -> dict[str, Any]:
    """Le 37 azioni, spiegate per gruppo invece che contate in blocco."""
    plan = repository["link_plan"]
    by_action = Counter(row["action"] for row in plan)
    terminology = [row for row in plan if row.get("reason_code") == TERMINOLOGY_REASON]
    diagnostic = [
        row
        for row in plan
        if row.get("reason_code")
        in (
            "SOURCE_POPULATION_REQUIRES_NARROWER_DISEASE_SCOPE",
            "DISEASE_SCOPE_BROADER_THAN_SOURCE_POPULATION",
        )
    ]
    carried = [
        row
        for row in plan
        if row.get("reason_code") is None
    ]
    return {
        "actions_by_type": dict(sorted(by_action.items())),
        "carried_from_earlier_phases": len(carried),
        "diagnostic_scope_actions": len(diagnostic),
        "diagnostic_scope_create": sum(
            1 for row in diagnostic if row["action"] in CREATE_ACTIONS
        ),
        "diagnostic_scope_retire": sum(
            1 for row in diagnostic if row["action"] in RETIRE_ACTIONS
        ),
        # I tre record senza sostituto compaiono nel piano: il loro link allo
        # statement legacy va ritirato. Cio' che non hanno e' una creazione, ed
        # e' quella asimmetria — ritiro senza creazione — che va nominata,
        # perche' e' l'unica forma in cui un record esce dal corpus senza che
        # nulla lo sostituisca.
        "records_retired_without_creation": sorted(
            {
                row["graph_evidence_id"]
                for row in plan
                if row["action"] in RETIRE_ACTIONS
            }
            - {
                row["graph_evidence_id"]
                for row in plan
                if row["action"] in CREATE_ACTIONS
            }
        ),
        "terminology_actions": len(terminology),
        "terminology_create": sum(
            1 for row in terminology if row["action"] in CREATE_ACTIONS
        ),
        "terminology_retire": sum(
            1 for row in terminology if row["action"] in RETIRE_ACTIONS
        ),
        "total_actions": len(plan),
        "totals_reconcile": len(terminology) + len(diagnostic) + len(carried)
        == len(plan),
    }


def link_audit(repository: Mapping[str, Any]) -> dict[str, Any]:
    rows = link_rows(repository)
    reconciliation = link_reconciliation(repository)

    plan_ids = [row["plan_id"] for row in rows]
    duplicates = sorted({pid for pid in plan_ids if plan_ids.count(pid) > 1})
    creates_towards_retired = sorted(
        row["plan_id"]
        for row in rows
        if row["action"] in CREATE_ACTIONS and row["targets_retired_claim"]
    )
    creates_towards_missing = sorted(
        row["plan_id"]
        for row in rows
        if row["action"] in CREATE_ACTIONS and row["targets_active_claim"] is False
    )
    executed = sorted(row["plan_id"] for row in rows if row["executed"])
    flattening = sorted(
        row["plan_id"] for row in rows if row["flattening_flags_set"]
    )
    locator_form_conflicts = sorted(
        row["plan_id"] for row in rows if not row["locator_forms_agree"]
    )
    locator_absent = sorted(
        row["plan_id"] for row in rows if not row["locator_evidence_present"]
    )
    source_unit_mismatch = sorted(
        row["plan_id"] for row in rows if row["source_units_match_claim"] is False
    )
    schemas = Counter(row["row_schema"] for row in rows)
    return {
        "actions_executed": executed,
        "creates_towards_missing_claim": creates_towards_missing,
        "creates_towards_retired_claim": creates_towards_retired,
        "duplicate_plan_ids": duplicates,
        "expected_total_actions": EXPECTED_LINK_ACTIONS,
        "flattening_flags_set": flattening,
        "locator_form_conflicts": locator_form_conflicts,
        "qualification_link_plan_consistent": bool(
            not duplicates
            and not creates_towards_retired
            and not creates_towards_missing
            and not executed
            and not flattening
            and not locator_form_conflicts
            and not locator_absent
            and not source_unit_mismatch
            and reconciliation["total_actions"] == EXPECTED_LINK_ACTIONS
            and reconciliation["totals_reconcile"]
            and reconciliation["terminology_retire"] == EXPECTED_TERMINOLOGY_RETIRE
            and reconciliation["terminology_create"] == EXPECTED_TERMINOLOGY_CREATE
        ),
        "reconciliation": reconciliation,
        "row_schemas": dict(sorted(schemas.items())),
        "row_schemas_heterogeneous": len(schemas) > 1,
        "rows_without_locator_evidence": locator_absent,
        "source_unit_field_forms": sorted(
            {
                "source_unit_id"
                if action.get("source_unit_id")
                else "source_unit_ids"
                if action.get("source_unit_ids")
                else "none"
                for action in repository["link_plan"]
            }
        ),
        "source_unit_mismatches": source_unit_mismatch,
    }


def view_audit(repository: Mapping[str, Any]) -> dict[str, Any]:
    """Le 4 azioni di view, distinte per cio' che fanno davvero."""
    plan = repository["view_plan"]
    active = {claim["claim_id"] for claim in repository["claims"]}
    retired = {row["claim_id"] for row in repository["deprecated"]}

    regenerate = [row for row in plan if row["action"] == REGENERATE_VIEW]
    verify = [row for row in plan if row["action"] == VERIFY_VIEW]

    orphans = sorted(
        row["plan_id"]
        for row in regenerate
        if row["claim_id"] not in active
    )
    towards_retired = sorted(
        row["plan_id"] for row in regenerate if row["claim_id"] in retired
    )
    executed = sorted(row["plan_id"] for row in plan if row.get("executed"))
    flattened = sorted(
        row["plan_id"]
        for row in plan
        if row.get("cross_domain_ranking") or row.get("therapy_score_present")
    )
    verified_absent = all(
        row.get("old_claim_id_occurrences_in_views") == 0
        and row.get("new_claim_id_occurrences_in_views") == 0
        for row in verify
    )
    plan_ids = [row["plan_id"] for row in plan]
    duplicates = sorted({pid for pid in plan_ids if plan_ids.count(pid) > 1})

    return {
        "action_breakdown": {
            "regenerate_diagnostic_view": len(regenerate),
            "verify_no_view_references_replaced_claim": len(verify),
        },
        "actions_executed": executed,
        "duplicate_plan_ids": duplicates,
        "expected_total_actions": EXPECTED_VIEW_ACTIONS,
        "flattened_domain_or_score": flattened,
        "operational_views_keyed_by_legacy_statement": all(
            row.get("reason_code")
            == "OPERATIONAL_VIEWS_ARE_KEYED_BY_LEGACY_STATEMENT_NOT_BY_CLAIM_ID"
            for row in verify
        ),
        "orphan_views": orphans,
        "qualified_view_plan_consistent": bool(
            not orphans
            and not towards_retired
            and not executed
            and not flattened
            and not duplicates
            and len(plan) == EXPECTED_VIEW_ACTIONS
            and verified_absent
        ),
        "regenerated_claims_are_active": not orphans,
        "terminology_claims_absent_from_operational_views": verified_absent,
        "total_actions": len(plan),
        "views_towards_retired_claim": towards_retired,
        "why_four_actions": (
            "Due rigenerazioni diagnostiche, portate dalla 1.2, per i claim il "
            "cui disease scope e' stato ristretto. Due verifiche, non "
            "rigenerazioni, per i claim terminologici: le view operative sono "
            "indicizzate per legacy statement e non per claim ID, quindi ne il "
            "vecchio ne il nuovo ID vi compaiono, e le due azioni contano le "
            "occorrenze invece di assumerne l'assenza."
        ),
    }


def audit(repository: Mapping[str, Any]) -> dict[str, Any]:
    return {"links": link_audit(repository), "views": view_audit(repository)}


def statements_without_replacement(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Statement ritirati senza una creazione corrispondente sullo stesso record."""
    created = {
        row["graph_evidence_id"] for row in rows if row["action"] in CREATE_ACTIONS
    }
    return sorted(
        {
            row["graph_evidence_id"]
            for row in rows
            if row["action"] in RETIRE_ACTIONS and row["graph_evidence_id"] not in created
        }
    )


__all__ = [
    "EXPECTED_LINK_ACTIONS",
    "EXPECTED_VIEW_ACTIONS",
    "audit",
    "link_audit",
    "link_reconciliation",
    "link_rows",
    "statements_without_replacement",
    "view_audit",
]
