"""Repository 1.4: la 1.3 con lo schema di propagazione reso obbligatorio.

La 1.4 non aggiunge, non toglie e non riscrive nessuna proposizione. Applica due
correzioni, entrambe legate a un finding dell'audit pre-promozione, ed entrambe
scelte per non toccare cio' che la revisione ha deciso:

**Propagation policy uniforme.** I tre campi obbligatori del modello 1.2 vengono
scritti su ogni claim. Per i 142 che gia' li portavano il valore resta quello
che era; per i sei che non li portavano il valore e' dichiarato dalla fase, non
dedotto dal contenuto.

**Nessun cambio di identita'.** I campi di propagazione non appartengono alla
formula del claim ID, e non vi entrano ora. Un ID che cambiasse per l'aggiunta
di un campo di governance direbbe che e' cambiata la proposizione, che non e'
vero: sarebbe una regressione travestita da correzione.

Il gate di formulazione e' una decisione di *retrieval*, non di contenuto. Nessun
claim viene modificato perche' la sua forma e' cambiata di comportamento al
gate, e la 1.4 lo registra: gli ID restano tutti quelli della 1.3.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from backend.pipeline.evidence.shadow import propagation as PROP
from backend.pipeline.evidence.shadow.formulation import (
    CONTRACT_VERSION as FORMULATION_CONTRACT_VERSION,
)

REPOSITORY_VERSION = "qualified_claim_repository/1.4"
SUPERSEDES = "qualified_claim_repository/1.3"

VERSION_BUMP_REASON = (
    "mandatory propagation policy schema plus explicit active moiety, salt and "
    "formulation contract"
)

MIGRATION_STATUS = "shadow_not_promoted"

# I due finding dell'audit pre-promozione che questa fase chiude, citati per ID
# perche' la correzione resti collegata a cio' che l'ha richiesta.
RESOLVED_FINDINGS = (
    "PROPAGATION_POLICY_MISSING_ON_NON_ATOMIC_CLAIMS",
    "SALT_FORM_TABLE_CONTRADICTS_FORMULATION_CAVEAT",
    "UNKNOWN_MODE_REJECTION_NOT_DECLARED",
    "LINK_PLAN_SCHEMA_HETEROGENEOUS",
)


class MigrationV14Error(RuntimeError):
    """La 1.4 ha incontrato uno stato che la 1.3 non dovrebbe poter produrre."""


@dataclass(frozen=True)
class PropagationChange:
    """Che cosa e' cambiato su un singolo claim, e che cosa no."""

    claim_id: str
    claim_type: str
    graph_evidence_id: str
    fields_added: tuple[str, ...]
    fields_already_present: tuple[str, ...]
    values: dict[str, Any]
    claim_id_changed: bool = False

    def as_row(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_id_changed": self.claim_id_changed,
            "claim_type": self.claim_type,
            "fields_added": list(self.fields_added),
            "fields_already_present": list(self.fields_already_present),
            "graph_evidence_id": self.graph_evidence_id,
            "values": dict(self.values),
        }


def upgrade_claim(record: Mapping[str, Any]) -> tuple[dict[str, Any], PropagationChange]:
    """Un claim 1.3 nella forma 1.4, con i campi di propagazione espliciti.

    I valori gia' presenti non vengono sovrascritti. La fase dichiara cio' che
    manca; non ridecide cio' che una revisione precedente ha stabilito.
    """
    claim_type = str(record.get("claim_type") or "")
    declared = PROP.propagation_fields_for(claim_type)

    added: list[str] = []
    present: list[str] = []
    values: dict[str, Any] = {}
    for field, default in sorted(declared.items()):
        if record.get(field) is None:
            added.append(field)
            values[field] = default
        else:
            present.append(field)
            values[field] = record[field]

    upgraded = dict(record) | values
    upgraded["schema_version"] = PROP.MODEL_SCHEMA_VERSION_V12
    upgraded["repository_version"] = REPOSITORY_VERSION

    # Il claim ID non entra in gioco: i campi appena scritti non appartengono
    # alla formula di identita', e questa riga lo rende una verifica invece che
    # una promessa.
    if upgraded["claim_id"] != record["claim_id"]:
        raise MigrationV14Error(
            f"{record['claim_id']}: l'aggiornamento di schema ha cambiato l'ID"
        )

    PROP.validate_record(upgraded)
    return upgraded, PropagationChange(
        claim_id=str(record["claim_id"]),
        claim_type=claim_type,
        graph_evidence_id=str(record.get("graph_evidence_id") or ""),
        fields_added=tuple(added),
        fields_already_present=tuple(present),
        values=values,
    )


def upgrade_claims(
    records: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[PropagationChange]]:
    upgraded: list[dict[str, Any]] = []
    changes: list[PropagationChange] = []
    for record in records:
        claim, change = upgrade_claim(record)
        upgraded.append(claim)
        changes.append(change)

    ids = [claim["claim_id"] for claim in upgraded]
    if len(ids) != len(set(ids)):
        raise MigrationV14Error("collisione fra claim ID nella 1.4")
    if sorted(ids) != sorted(record["claim_id"] for record in records):
        raise MigrationV14Error("l'insieme dei claim ID e' cambiato nella 1.4")
    return upgraded, changes


def propagation_matrix(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Matrice completa: un claim per riga, tutti i campi di governance."""
    rows: list[dict[str, Any]] = []
    for record in records:
        row = {
            "claim_id": record["claim_id"],
            "claim_type": record["claim_type"],
            "final_evaluable": record["final_evaluable"],
            "graph_evidence_id": record["graph_evidence_id"],
            "hard_filterable": record["hard_filterable"],
            "propagation_policy": record["propagation_policy"],
        }
        if record["claim_type"] in PROP.NON_ATOMIC_CLAIM_TYPES:
            row["member_propagation_allowed"] = record[PROP.MEMBER_PROPAGATION_FIELD]
        if record["claim_type"] == "aggregate_intervention_claim":
            row["permits_member_specific_claims"] = record[
                "permits_member_specific_claims"
            ]
        if record["claim_type"] == "regimen_claim":
            row["result_applies_to_combination"] = record[
                "result_applies_to_combination"
            ]
        rows.append(row)
    return sorted(rows, key=lambda row: row["claim_id"])


def aggregate_audit(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """I tre aggregati, con la propagazione ai membri esplicitamente negata."""
    return sorted(
        (
            {
                "aggregate_label": record.get("aggregate_label"),
                "aggregate_type": record.get("aggregate_type"),
                "claim_id": record["claim_id"],
                "final_evaluable": record["final_evaluable"],
                "graph_evidence_id": record["graph_evidence_id"],
                "hard_filterable": record["hard_filterable"],
                "member_propagation_allowed": record[PROP.MEMBER_PROPAGATION_FIELD],
                "members": list(record.get("aggregate_members_literal") or ()),
                "members_inheriting_the_result": [],
                "parent_id": record["parent_id"],
                "permits_member_specific_claims": record[
                    "permits_member_specific_claims"
                ],
                "propagation_policy": record["propagation_policy"],
                "reason_code": PROP.AGGREGATE_RESULT_NOT_SEPARABLE_BY_MEMBER,
            }
            for record in records
            if record["claim_type"] == "aggregate_intervention_claim"
        ),
        key=lambda row: row["claim_id"],
    )


def regimen_audit(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """I tre regimi, con la propagazione ai componenti esplicitamente negata."""
    return sorted(
        (
            {
                "claim_id": record["claim_id"],
                "components": list(record.get("regimen_components") or ()),
                "components_inheriting_the_result": [],
                "final_evaluable": record["final_evaluable"],
                "graph_evidence_id": record["graph_evidence_id"],
                "hard_filterable": record["hard_filterable"],
                "member_propagation_allowed": record[PROP.MEMBER_PROPAGATION_FIELD],
                "parent_id": record["parent_id"],
                "propagation_policy": record["propagation_policy"],
                "reason_code": PROP.COMPONENT_PROPAGATION_FORBIDDEN,
                "result_applies_to_combination": record[
                    "result_applies_to_combination"
                ],
            }
            for record in records
            if record["claim_type"] == "regimen_claim"
        ),
        key=lambda row: row["claim_id"],
    )


def version_lineage() -> dict[str, Any]:
    return {
        "current": REPOSITORY_VERSION,
        "migration_status": MIGRATION_STATUS,
        "model_schema": PROP.MODEL_SCHEMA_VERSION_V12,
        "resolved_audit_findings": list(RESOLVED_FINDINGS),
        "supersedes": SUPERSEDES,
        "version_bump_reason": VERSION_BUMP_REASON,
        "versions": [
            {
                "added": "modello tipizzato, parent di provenienza, tre tipi di claim",
                "model_schema": "qualified_claim_model/1.0",
                "repository_version": "qualified_claim_repository/1.0",
            },
            {
                "added": "domini diagnostico e prognostico",
                "model_schema": "qualified_claim_model/1.1",
                "repository_version": "qualified_claim_repository/1.1",
            },
            {
                "added": "restringimento del disease scope diagnostico",
                "model_schema": "qualified_claim_model/1.1",
                "repository_version": "qualified_claim_repository/1.2",
            },
            {
                "added": "terminologia verificata e gate direzionale di malattia",
                "model_schema": "qualified_claim_model/1.1",
                "repository_version": "qualified_claim_repository/1.3",
            },
            {
                "added": (
                    "propagation policy obbligatoria e contratto di forma "
                    "dell'intervento"
                ),
                "formulation_contract": FORMULATION_CONTRACT_VERSION,
                "model_schema": PROP.MODEL_SCHEMA_VERSION_V12,
                "repository_version": REPOSITORY_VERSION,
            },
        ],
    }


__all__ = [
    "MIGRATION_STATUS",
    "REPOSITORY_VERSION",
    "RESOLVED_FINDINGS",
    "SUPERSEDES",
    "VERSION_BUMP_REASON",
    "MigrationV14Error",
    "PropagationChange",
    "aggregate_audit",
    "propagation_matrix",
    "regimen_audit",
    "upgrade_claim",
    "upgrade_claims",
    "version_lineage",
]
