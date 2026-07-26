"""Adapter shadow: dai record V2 al modello tipizzato parent/claim.

E' un adapter nuovo, non una modifica di `v2_adapter`. L'adapter operativo resta
quello che e' e continua a produrre gli stessi `EvidenceStatement`: la migrazione
shadow gli cammina accanto senza toccarlo.

La differenza sta in un punto solo, ed e' il punto che conta. L'adapter operativo
raggruppa le righe V2 per graph evidence ID e, sui campi multi-valore, tiene il
primo valore: `merge_duplicate_records.scalar_single_value_selection`. Cosi'
`evidence:229` diventa uno statement su erlotinib e gefitinib sparisce. Qui il
raggruppamento resta identico, ma non produce una scelta: produce un
`GraphEvidenceRecord` che conserva tutti gli interventi come letterali e non
afferma nessuna terapia.

I claim arrivano da altrove. Per i 13 gruppi adjudicati arrivano
dall'adjudication congelata, applicata alla lettera. Per gli altri record
l'adapter porta avanti il claim corrente senza migliorarlo ne' peggiorarlo:
stesso intervento, stesso review status, stessa propagation policy, nessuna
source unit nuova, `documentary_revalidation_completed` a falso perche' nessuna
revisione documentale e' avvenuta.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow.associations import (
    UnresolvedAssociation,
    UnsupportedAssociation,
)
from backend.pipeline.evidence.shadow.claims import (
    AggregateInterventionClaim,
    AtomicInterventionClaim,
    RegimenClaim,
    TypedClaim,
)
from backend.pipeline.evidence.shadow.deprecation import (
    LegacyStatementDeprecation,
    state_for,
)
from backend.pipeline.evidence.shadow.identity import (
    association_id,
    canonical_regimen,
    claim_id,
    parent_id,
)
from backend.pipeline.evidence.shadow.parent import GraphEvidenceRecord
from backend.pipeline.evidence.shadow.schema import (
    AGGREGATE_KIND_TO_TYPE,
    MIGRATION_ORIGIN_ADJUDICATED,
    MIGRATION_ORIGIN_LEGACY,
    MODEL_SCHEMA_VERSION,
)

SHADOW_ADAPTER_VERSION = "v2_to_typed_claim_shadow_adapter/1.0"

# Le direzioni che il modello di claim conosce. `diagnostic` e `prognostic` non
# ci sono: non sono direzioni terapeutiche, e un record che le porta non afferma
# un effetto di un intervento su un biomarcatore.
THERAPEUTIC_DIRECTIONS = ("sensitivity", "resistance", "reduced_sensitivity")

# Token di identita' per i claim legacy. Non e' una source unit documentale e non
# pretende di esserlo: la revisione che le produce non e' avvenuta su questi
# record. Serve a rendere l'ID deterministico senza inventare un'unita' di fonte
# che non esiste, ed e' riconoscibile come tale a vista.
LEGACY_SOURCE_UNIT_PREFIX = "LEGACY-NO-REVIEWED-SOURCE-UNIT:"

BLOCKER_NON_THERAPEUTIC = "NON_THERAPEUTIC_RECORD_NO_INTERVENTION_CLAIM_TYPE"
BLOCKER_NO_INTERVENTION = "LEGACY_STATEMENT_WITHOUT_INTERVENTION"


class ShadowAdapterError(RuntimeError):
    """La migrazione shadow ha incontrato uno stato che non sa rappresentare."""


@dataclass(frozen=True)
class MigrationBlocker:
    """Un record che non si migra senza una nuova decisione semantica."""

    graph_evidence_id: str
    parent_id: str
    legacy_statement_id: str | None
    blocker_code: str
    detail: str
    blocks_promotion: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_evidence_id": self.graph_evidence_id,
            "parent_id": self.parent_id,
            "legacy_statement_id": self.legacy_statement_id,
            "blocker_code": self.blocker_code,
            "detail": self.detail,
            "blocks_promotion": self.blocks_promotion,
            "migration_version": MODEL_SCHEMA_VERSION,
        }


@dataclass(frozen=True)
class ShadowMigrationResult:
    parents: tuple[GraphEvidenceRecord, ...] = ()
    claims: tuple[TypedClaim, ...] = ()
    unsupported: tuple[UnsupportedAssociation, ...] = ()
    unresolved: tuple[UnresolvedAssociation, ...] = ()
    deprecations: tuple[LegacyStatementDeprecation, ...] = ()
    blockers: tuple[MigrationBlocker, ...] = ()
    v2_row_count: int = 0
    adjudicated_graph_evidence_ids: tuple[str, ...] = ()

    def claims_of_type(self, claim_type: str) -> tuple[TypedClaim, ...]:
        return tuple(c for c in self.claims if c.claim_type == claim_type)

    def claims_by_origin(self, origin: str) -> tuple[TypedClaim, ...]:
        return tuple(c for c in self.claims if c.migration_origin == origin)


# --- normalizzazione ----------------------------------------------------------


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _statement_graph_evidence_id(statement: Mapping[str, Any]) -> str:
    ids = statement.get("provenance", {}).get("graph_record_ids") or ()
    if not ids:
        raise ShadowAdapterError(
            f"{statement.get('evidence_statement_id')}: statement senza graph record id"
        )
    return ids[0]


# --- parent -------------------------------------------------------------------


def build_parent(
    graph_evidence_id: str,
    v2_rows: Sequence[Mapping[str, Any]],
    statement: Mapping[str, Any] | None,
) -> GraphEvidenceRecord:
    """Un contenitore per graph evidence ID, con tutti gli interventi V2 dentro.

    Le righe entrano ordinate per `record_index` perche' il risultato non dipenda
    dall'ordine di lettura del file. Gli interventi sono deduplicati conservando
    il primo ordine di apparizione, e le righe senza intervento non contribuiscono
    un letterale vuoto.
    """
    ordered = sorted(v2_rows, key=lambda row: (row.get("record_index", 0), row.get("lineage_id", "")))
    interventions: list[str] = []
    for row in ordered:
        literal = _text(row.get("adapter_input_intervention_normalized"))
        if literal and literal not in interventions:
            interventions.append(literal)

    provenance: dict[str, Any] = {
        "graph_record_ids": [graph_evidence_id],
        "adapter_version": SHADOW_ADAPTER_VERSION,
        "origin": "frozen_kg",
    }
    if statement is not None:
        source_provenance = statement.get("provenance", {})
        provenance["snapshot_fingerprint"] = source_provenance.get("snapshot_fingerprint")
        provenance["operational_extraction_action_id"] = source_provenance.get(
            "extraction_action_id"
        )

    source_ids = sorted(
        {
            _text(ref.get("source_id"))
            for ref in (statement or {}).get("source_references", ())
            if _text(ref.get("source_id"))
        }
    )

    return GraphEvidenceRecord(
        parent_id=parent_id(graph_evidence_id),
        graph_evidence_id=graph_evidence_id,
        source_ids=tuple(source_ids),
        source_record_ids=tuple(row.get("lineage_id", "") for row in ordered),
        raw_v2_records=tuple(dict(row) for row in ordered),
        biomarker_context=_text((statement or {}).get("biomarker", {}).get("label")) or None,
        disease_context=_text((statement or {}).get("disease", {}).get("label")) or None,
        original_intervention_associations=tuple(interventions),
        adapter_lineage=(SHADOW_ADAPTER_VERSION,),
        # Nessuna revisione umana e' avvenuta sul contenitore in quanto tale.
        review_status="not_reviewed",
        provenance=provenance,
    )


# --- claim adjudicati ---------------------------------------------------------


def _locators(record: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    locator = record.get("locator")
    if not locator:
        return ()
    if isinstance(locator, str):
        return ({"text": locator, "source_id": record.get("source_id")},)
    return (dict(locator),)


def build_adjudicated_claim(
    record: Mapping[str, Any], parent: GraphEvidenceRecord
) -> TypedClaim:
    """Materializza un claim approvato, senza reinterpretare la decisione."""
    claim_type = record["claim_type"]
    source_units = (record["source_unit_id"],) + tuple(record.get("supporting_units") or ())
    provenance = {
        "graph_record_ids": [parent.graph_evidence_id],
        "snapshot_fingerprint": parent.provenance.get("snapshot_fingerprint"),
        "adapter_version": SHADOW_ADAPTER_VERSION,
        "adjudication_version": record.get("adjudication_version"),
        "adjudicator_role": record.get("adjudicator_role"),
        "adjudication_independence": record.get("adjudication_independence"),
        "claim_ref": record.get("claim_ref"),
        "source_id": record.get("source_id"),
        "source_literal_terms": list(record.get("source_literal_terms") or ()),
        "result_summary": record.get("result_summary"),
        "residual_risk": record.get("residual_risk"),
        "gold_used_for_decisions": record.get("gold_used_for_decisions", False),
    }
    common = {
        "parent_id": parent.parent_id,
        "graph_evidence_id": parent.graph_evidence_id,
        "biomarker": record["biomarker"],
        "disease_scope": record["disease_scope"],
        "direction": record["direction"],
        "polarity": record["polarity"],
        "source_unit_ids": source_units,
        "locators": _locators(record),
        "review_status": "adjudicated",
        "provenance": provenance,
        "evidence_setting": record.get("evidence_setting"),
    }

    if claim_type == "regimen_claim":
        components = tuple(record["regimen_components"])
        identity = canonical_regimen(components)
    elif claim_type == "aggregate_intervention_claim":
        identity = record["canonical_intervention_or_regimen"]
    else:
        identity = record["canonical_intervention_or_regimen"]

    new_id = claim_id(
        graph_evidence_id=parent.graph_evidence_id,
        claim_type=claim_type,
        canonical_intervention_or_regimen=identity,
        biomarker=record["biomarker"],
        direction=record["direction"],
        polarity=record["polarity"],
        source_unit_id=record["source_unit_id"],
    )
    # L'adjudication ha gia' emesso l'ID. Ricalcolarlo e confrontarlo e' il modo
    # di accorgersi subito se la formula qui divergesse da quella congelata.
    if record.get("claim_id") and record["claim_id"] != new_id:
        raise ShadowAdapterError(
            f"{record.get('claim_ref')}: claim_id ricalcolato {new_id} diverso da "
            f"quello congelato {record['claim_id']}"
        )

    if claim_type == "regimen_claim":
        return RegimenClaim(
            claim_id=new_id,
            regimen_components=tuple(record["regimen_components"]),
            migration_origin=MIGRATION_ORIGIN_ADJUDICATED,
            **common,
        )
    if claim_type == "aggregate_intervention_claim":
        kind = record.get("aggregate_kind", "other")
        return AggregateInterventionClaim(
            claim_id=new_id,
            aggregate_type=AGGREGATE_KIND_TO_TYPE.get(kind, "other"),
            aggregate_label=record["aggregate_members"][0],
            aggregate_members_literal=tuple(record.get("source_literal_terms") or ()),
            permits_member_specific_claims=False,
            migration_origin=MIGRATION_ORIGIN_ADJUDICATED,
            **common,
        )
    return AtomicInterventionClaim(
        claim_id=new_id,
        intervention=record["intervention"],
        migration_origin=MIGRATION_ORIGIN_ADJUDICATED,
        documentary_revalidation_completed=True,
        propagation_policy=record.get("propagation_policy", "prototype_only"),
        **common,
    )


def build_association(
    record: Mapping[str, Any], parent: GraphEvidenceRecord, kind: str
) -> UnsupportedAssociation | UnresolvedAssociation:
    new_id = association_id(
        kind=kind,
        graph_evidence_id=parent.graph_evidence_id,
        intervention_literal=record["intervention"],
        biomarker=record["biomarker"],
        source_unit_id=record["source_unit_id"],
    )
    common = {
        "association_id": new_id,
        "parent_id": parent.parent_id,
        "graph_evidence_id": parent.graph_evidence_id,
        "intervention_literal": record["intervention"],
        "biomarker": record["biomarker"],
        "source_unit_ids": (record["source_unit_id"],),
        "locators": _locators(record),
        "review_status": "adjudicated",
        "provenance": {
            "graph_record_ids": [parent.graph_evidence_id],
            "adjudication_id": record.get("adjudication_id"),
            "adjudication_version": record.get("adjudication_version"),
            "rationale": record.get("rationale"),
            "source_id": record.get("source_id"),
            "is_parent_intervention": record.get("is_parent_intervention"),
        },
    }
    if kind == "unsupported_association":
        return UnsupportedAssociation(
            reason_codes=tuple(record.get("reason_codes") or ()), **common
        )
    return UnresolvedAssociation(
        unresolved_reason_codes=tuple(record.get("reason_codes") or ()),
        terminology_status=record.get("first_review_classification"),
        **common,
    )


# --- claim legacy -------------------------------------------------------------


def build_legacy_claim(
    statement: Mapping[str, Any], parent: GraphEvidenceRecord
) -> AtomicInterventionClaim | None:
    """Porta avanti lo statement corrente come claim legacy migrato.

    Non migliora e non peggiora il supporto: nessuna source unit nuova, nessuna
    revisione promossa da automatica a umana, nessun claim dichiarato definitivo.
    Restituisce `None` quando lo statement non porta un intervento, perche' i tre
    tipi di claim sono tutti tipi di intervento e non ce n'e' uno che possa
    ospitare un record prognostico o diagnostico.
    """
    intervention = _text((statement.get("intervention") or {}).get("label"))
    if not intervention:
        return None

    statement_id = statement["evidence_statement_id"]
    biomarker = _text(statement.get("biomarker", {}).get("label"))
    disease = _text(statement.get("disease", {}).get("label")) or "unknown"
    direction = statement.get("direction") or "unknown"
    polarity = statement.get("assertion_polarity") or "unknown"
    source_unit_token = LEGACY_SOURCE_UNIT_PREFIX + statement_id

    new_id = claim_id(
        graph_evidence_id=parent.graph_evidence_id,
        claim_type="atomic_intervention_claim",
        canonical_intervention_or_regimen=intervention.lower(),
        biomarker=biomarker,
        direction=direction,
        polarity=polarity,
        source_unit_id=source_unit_token,
    )
    return AtomicInterventionClaim(
        claim_id=new_id,
        parent_id=parent.parent_id,
        graph_evidence_id=parent.graph_evidence_id,
        intervention=intervention,
        biomarker=biomarker,
        disease_scope=disease,
        direction=direction,
        polarity=polarity,
        # Nessuna unita' di fonte revisionata esiste per questi record.
        source_unit_ids=(),
        locators=(),
        review_status=statement.get("review_status", "pending_verification"),
        propagation_policy="prototype_only",
        legacy_statement_ids=(statement_id,),
        migration_origin=MIGRATION_ORIGIN_LEGACY,
        documentary_revalidation_completed=False,
        evidence_setting=None,
        provenance={
            "graph_record_ids": [parent.graph_evidence_id],
            "snapshot_fingerprint": statement.get("provenance", {}).get(
                "snapshot_fingerprint"
            ),
            "operational_extraction_action_id": statement.get("provenance", {}).get(
                "extraction_action_id"
            ),
            "adapter_version": SHADOW_ADAPTER_VERSION,
            "legacy_statement_id": statement_id,
            "identity_source_unit_token": source_unit_token,
            "documentary_review_performed": False,
        },
    )
