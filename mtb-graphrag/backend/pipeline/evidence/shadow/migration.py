"""Orchestrazione della migrazione shadow.

Il risultato deve essere deterministico: due generazioni producono gli stessi
byte, e invertire l'ordine dei file di ingresso non cambia nulla. Per questo ogni
raggruppamento e' ordinato esplicitamente e nessun risultato dipende dall'ordine
di iterazione di un dizionario o dall'ordine di lettura di un file.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from backend.pipeline.evidence.shadow.associations import (
    UnresolvedAssociation,
    UnsupportedAssociation,
)
from backend.pipeline.evidence.shadow.claims import TypedClaim
from backend.pipeline.evidence.shadow.deprecation import (
    LegacyStatementDeprecation,
    state_for,
)
from backend.pipeline.evidence.shadow.parent import GraphEvidenceRecord
from backend.pipeline.evidence.shadow.shadow_adapter import (
    BLOCKER_NON_THERAPEUTIC,
    MigrationBlocker,
    ShadowAdapterError,
    ShadowMigrationResult,
    THERAPEUTIC_DIRECTIONS,
    _statement_graph_evidence_id,
    build_adjudicated_claim,
    build_association,
    build_legacy_claim,
    build_parent,
)
from backend.pipeline.evidence.shadow.schema import MODEL_SCHEMA_VERSION

DEPRECATION_REASONS = {
    "replaced_by_atomic_claim": "Lo statement scalare e' sostituito da claim atomici approvati dall'adjudication.",
    "replaced_by_aggregate_claim": "Lo statement scalare e' sostituito da un claim aggregato: la fonte nomina la classe, non il singolo farmaco.",
    "replaced_by_regimen_claim": "Lo statement scalare e' sostituito da un claim di regime: il risultato appartiene alla combinazione.",
    "deprecated_without_replacement": "L'adjudication non ha approvato alcun claim per questo gruppo: le associazioni restano auditabili e nessun sostituto viene inventato.",
    "preserved_as_legacy_migrated_claim": "Record non adjudicato: il claim corrente e' portato avanti senza nuove decisioni semantiche.",
}


def migrate(
    *,
    v2_rows: Sequence[Mapping[str, Any]],
    statements: Sequence[Mapping[str, Any]],
    approved_claims: Sequence[Mapping[str, Any]],
    unsupported_records: Sequence[Mapping[str, Any]],
    unresolved_records: Sequence[Mapping[str, Any]],
    adjudicated_graph_evidence_ids: Sequence[str],
) -> ShadowMigrationResult:
    """Costruisce il repository shadow completo a partire dagli input congelati."""
    adjudicated = frozenset(adjudicated_graph_evidence_ids)

    rows_by_ge: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in v2_rows:
        rows_by_ge[row["graph_evidence_id"]].append(row)

    statement_by_ge: dict[str, Mapping[str, Any]] = {}
    for statement in statements:
        ge = _statement_graph_evidence_id(statement)
        if ge in statement_by_ge:
            raise ShadowAdapterError(f"{ge}: piu' di uno statement operativo")
        statement_by_ge[ge] = statement

    claims_by_ge: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in approved_claims:
        claims_by_ge[record["graph_evidence_parent"]].append(record)

    unsupported_by_ge: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in unsupported_records:
        unsupported_by_ge[record["graph_evidence_id"]].append(record)

    unresolved_by_ge: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in unresolved_records:
        unresolved_by_ge[record["graph_evidence_id"]].append(record)

    parents: list[GraphEvidenceRecord] = []
    claims: list[TypedClaim] = []
    unsupported: list[UnsupportedAssociation] = []
    unresolved: list[UnresolvedAssociation] = []
    deprecations: list[LegacyStatementDeprecation] = []
    blockers: list[MigrationBlocker] = []

    # L'ordine di uscita e' l'ordine canonico dei graph evidence ID, non quello
    # di ingresso: e' cio' che rende la generazione byte-identica fra run.
    for graph_evidence_id in sorted(rows_by_ge):
        statement = statement_by_ge.get(graph_evidence_id)
        parent = build_parent(graph_evidence_id, rows_by_ge[graph_evidence_id], statement)

        group_claims: list[TypedClaim] = []
        group_unsupported: list[UnsupportedAssociation] = []
        group_unresolved: list[UnresolvedAssociation] = []

        if graph_evidence_id in adjudicated:
            for record in sorted(
                claims_by_ge[graph_evidence_id], key=lambda r: r["claim_id"]
            ):
                group_claims.append(build_adjudicated_claim(record, parent))
            for record in sorted(
                unsupported_by_ge[graph_evidence_id],
                key=lambda r: (r["intervention"], r["source_unit_id"]),
            ):
                group_unsupported.append(
                    build_association(record, parent, "unsupported_association")
                )
            for record in sorted(
                unresolved_by_ge[graph_evidence_id],
                key=lambda r: (r["intervention"], r["source_unit_id"]),
            ):
                group_unresolved.append(
                    build_association(record, parent, "unresolved_association")
                )
        elif statement is not None:
            legacy = build_legacy_claim(statement, parent)
            if legacy is not None:
                group_claims.append(legacy)
            else:
                blockers.append(
                    MigrationBlocker(
                        graph_evidence_id=graph_evidence_id,
                        parent_id=parent.parent_id,
                        legacy_statement_id=statement["evidence_statement_id"],
                        blocker_code=BLOCKER_NON_THERAPEUTIC,
                        detail=(
                            "Lo statement non porta un intervento e la sua direzione "
                            f"({statement.get('direction')}) non e' terapeutica: nessuno dei tre "
                            "tipi di claim puo' ospitarlo. Il parent resta senza claim invece "
                            "che con un claim inventato."
                        ),
                        # Non blocca la promozione: e' un record che non ha mai
                        # affermato una terapia, non un record perso.
                        blocks_promotion=False,
                    )
                )

        parent = _attach_children(parent, group_claims, group_unsupported, group_unresolved, statement)
        parents.append(parent)
        claims.extend(group_claims)
        unsupported.extend(group_unsupported)
        unresolved.extend(group_unresolved)

        if statement is not None:
            deprecations.append(
                _deprecation_for(statement, parent, group_claims, graph_evidence_id in adjudicated)
            )

    _check_no_id_collisions(claims, unsupported, unresolved, parents)

    return ShadowMigrationResult(
        parents=tuple(parents),
        claims=tuple(claims),
        unsupported=tuple(unsupported),
        unresolved=tuple(unresolved),
        deprecations=tuple(deprecations),
        blockers=tuple(blockers),
        v2_row_count=len(v2_rows),
        adjudicated_graph_evidence_ids=tuple(sorted(adjudicated)),
    )


def _attach_children(
    parent: GraphEvidenceRecord,
    claims: Sequence[TypedClaim],
    unsupported: Sequence[UnsupportedAssociation],
    unresolved: Sequence[UnresolvedAssociation],
    statement: Mapping[str, Any] | None,
) -> GraphEvidenceRecord:
    """Ricostruisce il parent con i riferimenti ai figli. Nessuna mutazione."""
    from dataclasses import replace

    deprecated_ids: tuple[str, ...] = ()
    if statement is not None and claims and any(
        c.migration_origin == "adjudicated_review" for c in claims
    ):
        deprecated_ids = (statement["evidence_statement_id"],)
    elif statement is not None and not claims and (unsupported or unresolved):
        deprecated_ids = (statement["evidence_statement_id"],)

    return replace(
        parent,
        child_claim_ids=tuple(c.claim_id for c in claims),
        unsupported_association_ids=tuple(a.association_id for a in unsupported),
        unresolved_association_ids=tuple(a.association_id for a in unresolved),
        deprecated_statement_ids=deprecated_ids,
    )


def _deprecation_for(
    statement: Mapping[str, Any],
    parent: GraphEvidenceRecord,
    claims: Sequence[TypedClaim],
    adjudicated: bool,
) -> LegacyStatementDeprecation:
    statement_id = statement["evidence_statement_id"]
    if not adjudicated:
        # Il record non adjudicato non viene deprecato: il claim corrente e'
        # portato avanti, o — per i record non terapeutici — semplicemente resta
        # senza claim, e in nessuno dei due casi lo statement perde validita'.
        reason = DEPRECATION_REASONS["preserved_as_legacy_migrated_claim"]
        if not claims:
            reason = (
                "Record non adjudicato e non terapeutico: nessun tipo di claim di "
                "intervento lo rappresenta. Lo statement resta valido e leggibile."
            )
        return LegacyStatementDeprecation(
            legacy_statement_id=statement_id,
            parent_id=parent.parent_id,
            graph_evidence_id=parent.graph_evidence_id,
            deprecation_state="preserved_as_legacy_migrated_claim",
            replacement_claim_ids=tuple(c.claim_id for c in claims),
            deprecation_reason=reason,
        )

    state = state_for(tuple(c.claim_type for c in claims))
    return LegacyStatementDeprecation(
        legacy_statement_id=statement_id,
        parent_id=parent.parent_id,
        graph_evidence_id=parent.graph_evidence_id,
        deprecation_state=state,
        replacement_claim_ids=tuple(c.claim_id for c in claims),
        deprecation_reason=DEPRECATION_REASONS[state],
    )


def _check_no_id_collisions(
    claims: Sequence[TypedClaim],
    unsupported: Sequence[UnsupportedAssociation],
    unresolved: Sequence[UnresolvedAssociation],
    parents: Sequence[GraphEvidenceRecord],
) -> None:
    """Nessun ID puo' ripetersi, nemmeno fra tipi diversi."""
    seen: dict[str, str] = {}
    for group, label in (
        ([c.claim_id for c in claims], "claim"),
        ([a.association_id for a in unsupported], "unsupported"),
        ([a.association_id for a in unresolved], "unresolved"),
        ([p.parent_id for p in parents], "parent"),
    ):
        for identifier in group:
            if identifier in seen:
                raise ShadowAdapterError(
                    f"collisione di ID {identifier}: {seen[identifier]} e {label}"
                )
            seen[identifier] = label
