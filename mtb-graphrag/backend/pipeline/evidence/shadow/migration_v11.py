"""Migrazione shadow 1.1: aggiunge i domini diagnostico e prognostico.

Riusa la migrazione 1.0 senza modificarla e vi aggiunge tre cose: i claim
diagnostici approvati dall'audit, la revisione dello stato di deprecazione dei
loro statement legacy, e la risoluzione di `evidence:347`.

`evidence:347` e' il caso che il modello 1.0 non sapeva rappresentare. Il suo
statement operativo afferma una direzione prognostica che la fonte contraddice —
la fonte e' un'analisi dell'effetto di cetuximab, non uno studio prognostico — e
nel piano 1.0 restava `preserved_as_legacy_migrated_claim`, cioe' attivo,
promuovibile e senza alcuna traccia del problema. Non ha un sostituto, quindi
`deprecated_without_replacement` direbbe una cosa vera ma incompleta: farebbe
sembrare chiusa una questione che e' aperta. Lo stato
`promotion_blocked_pending_full_text` dice le due cose insieme — non promuovere,
e perche'.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from backend.pipeline.evidence.shadow.deprecation import (
    CLAIM_TYPE_TO_STATE_V11,
    DEPRECATION_STATES_V11,
    PROMOTION_BLOCKING_STATES,
    LegacyStatementDeprecation,
)
from backend.pipeline.evidence.shadow.domain import (
    DOMAIN_DIAGNOSTIC,
    DOMAIN_PROGNOSTIC,
    DOMAIN_THERAPEUTIC,
    domain_of,
)
from backend.pipeline.evidence.shadow.identity import non_therapeutic_claim_id
from backend.pipeline.evidence.shadow.non_therapeutic_claims import (
    DiagnosticClaim,
    PrognosticClaim,
)
from backend.pipeline.evidence.shadow.parent import GraphEvidenceRecord
from backend.pipeline.evidence.shadow.schema import (
    MODEL_SCHEMA_VERSION_V11,
    SHADOW_REPOSITORY_VERSION_V11,
)
from backend.pipeline.evidence.shadow.shadow_adapter import ShadowMigrationResult

MIGRATION_VERSION = "v2_to_typed_claim_shadow_adapter/1.1"

# Il record che resta senza claim per contraddizione documentale, e i codici che
# lo dicono. Non e' una lista di eccezioni: e' l'esito di un audit, e i codici
# sono quelli che l'audit ha emesso.
NO_CLAIM_REASON = "SOURCE_CONTRADICTS_GRAPH_PROGNOSTIC_DIRECTION"
UNRESOLVED_REASON = "FULL_TEXT_REQUIRED_FOR_PREDICTIVE_SCOPE"

PROMOTION_BLOCKED_STATE = "promotion_blocked_pending_full_text"


class MigrationV11Error(RuntimeError):
    """La migrazione 1.1 ha incontrato uno stato che non sa rappresentare."""


@dataclass(frozen=True)
class ShadowMigrationV11Result:
    parents: tuple[GraphEvidenceRecord, ...] = ()
    therapeutic_claims: tuple[Any, ...] = ()
    diagnostic_claims: tuple[DiagnosticClaim, ...] = ()
    prognostic_claims: tuple[PrognosticClaim, ...] = ()
    unsupported: tuple[Any, ...] = ()
    unresolved: tuple[Any, ...] = ()
    deprecations: tuple[LegacyStatementDeprecation, ...] = ()
    parents_without_claims: tuple[dict[str, Any], ...] = ()
    schema_version: str = MODEL_SCHEMA_VERSION_V11
    repository_version: str = SHADOW_REPOSITORY_VERSION_V11

    @property
    def evidence_claims(self) -> tuple[Any, ...]:
        """Tutti gli EvidenceClaim, in ordine canonico per dominio e ID."""
        return tuple(
            sorted(
                self.therapeutic_claims + self.diagnostic_claims + self.prognostic_claims,
                key=lambda c: (domain_of(c), c.claim_type, c.claim_id),
            )
        )

    @property
    def total_claims(self) -> int:
        return len(self.evidence_claims)


def build_diagnostic_claim(
    record: Mapping[str, Any], parent: GraphEvidenceRecord
) -> DiagnosticClaim:
    """Materializza un claim diagnostico dall'audit, senza aggiungere nulla."""
    subject = record["diagnostic_subject"]
    canonical = " ".join(subject.split()).lower()
    interpretation = record["diagnostic_interpretation"]
    source_unit = record["profile_unit_id"]

    claim_id = non_therapeutic_claim_id(
        graph_evidence_id=record["graph_evidence_id"],
        claim_type="diagnostic_claim",
        canonical_subject=canonical,
        biomarker=record["biomarker"],
        disease_scope=record["disease"],
        direction_or_interpretation=interpretation,
        polarity=record["assertion_polarity"],
        source_unit_id=source_unit,
    )

    limitations: list[str] = []
    if not record.get("prevalence_attributable_to_specific_fusion", True):
        limitations.append("PREVALENCE_AGGREGATE_ONLY_NOT_PARTNER_SPECIFIC")
    if not record.get("clinical_validation_asserted", False):
        limitations.append("CLINICAL_UTILITY_NOT_ASSERTED")
    if record.get("abstract_available") and not record.get("full_text_used", False):
        limitations.append("ABSTRACT_ONLY_NO_FULL_TEXT")
    if not record.get("profile_unit_is_evaluable", False):
        limitations.append("SOURCE_UNIT_AWAITING_HUMAN_REVIEW")

    return DiagnosticClaim(
        claim_id=claim_id,
        parent_id=parent.parent_id,
        graph_evidence_id=record["graph_evidence_id"],
        biomarker=record["biomarker"],
        disease_scope=record["disease"],
        direction=record["graph_direction"],
        polarity=record["assertion_polarity"],
        source_unit_ids=(source_unit,),
        locators=tuple(dict(x) for x in record["locators"]),
        qualification_link_ids=(),
        # Lo stato di revisione e' quello che c'era: l'audit e' documentale, non
        # ha promosso nessuna revisione umana della fonte primaria.
        review_status=record["review_status"],
        propagation_policy="prototype_only",
        legacy_statement_ids=(record["legacy_statement_id"],),
        deprecated=False,
        diagnostic_subject=subject,
        diagnostic_interpretation=interpretation,
        assay_or_method=record.get("assay_or_method"),
        population_or_sample_scope=record.get("population_or_sample_scope"),
        clinical_validation_asserted=False,
        prevalence_attributable_to_subject=bool(
            record.get("prevalence_attributable_to_specific_fusion", False)
        ),
        limitation_codes=tuple(limitations),
        hard_filterable=False,
        final_evaluable=False,
        provenance={
            "graph_record_ids": [record["graph_evidence_id"]],
            "snapshot_fingerprint": parent.provenance.get("snapshot_fingerprint"),
            "adapter_version": MIGRATION_VERSION,
            "audit_id": record["audit_id"],
            "source_id": record["source_id"],
            "source_title": record.get("source_title"),
            "verbatim_probes": list(record.get("verbatim_probes") or ()),
            "documentary_role": record.get("documentary_role"),
            "reason_codes": list(record.get("reason_codes") or ()),
            "gold_used": False,
        },
    )


def _parent_without_claim_record(
    parent: GraphEvidenceRecord,
    audit: Mapping[str, Any] | None,
    deprecation: LegacyStatementDeprecation | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "graph_evidence_id": parent.graph_evidence_id,
        "parent_id": parent.parent_id,
        "claim_count": 0,
        "unsupported_association_ids": list(parent.unsupported_association_ids),
        "unresolved_association_ids": list(parent.unresolved_association_ids),
        "legacy_statement_ids": [deprecation.legacy_statement_id] if deprecation else [],
        "legacy_deprecation_state": deprecation.deprecation_state if deprecation else None,
        "promotion_blocked": bool(
            deprecation and deprecation.deprecation_state in PROMOTION_BLOCKING_STATES
        ),
        "provenance": dict(parent.provenance),
        "schema_version": MODEL_SCHEMA_VERSION_V11,
    }
    if audit is not None:
        payload.update(
            {
                "no_claim_reason": NO_CLAIM_REASON,
                "unresolved_reason": UNRESOLVED_REASON,
                "source_id": audit["source_id"],
                "audit_id": audit["audit_id"],
                "audit_verdict": audit["verdict"],
                "audit_status": "audited_no_claim",
                "requires_full_text": bool(audit.get("requires_full_text")),
            }
        )
    else:
        payload.update(
            {
                "no_claim_reason": "ADJUDICATED_NO_POSITIVE_CLAIM",
                "unresolved_reason": None,
                "audit_status": "adjudicated_no_claim",
                "requires_full_text": False,
            }
        )
    return payload


def upgrade(
    base: ShadowMigrationResult,
    audit_records: Sequence[Mapping[str, Any]],
) -> ShadowMigrationV11Result:
    """Porta il risultato 1.0 al modello 1.1 senza rigenerarlo."""
    audit_by_ge = {r["graph_evidence_id"]: r for r in audit_records}
    parents_by_ge = {p.graph_evidence_id: p for p in base.parents}
    deprecation_by_ge = {d.graph_evidence_id: d for d in base.deprecations}

    diagnostic: list[DiagnosticClaim] = []
    prognostic: list[PrognosticClaim] = []

    for graph_evidence_id in sorted(audit_by_ge):
        record = audit_by_ge[graph_evidence_id]
        parent = parents_by_ge.get(graph_evidence_id)
        if parent is None:
            raise MigrationV11Error(f"{graph_evidence_id}: audit senza parent")
        if record["verdict"] == "diagnostic_claim_supported":
            diagnostic.append(build_diagnostic_claim(record, parent))
        elif record["verdict"] == "prognostic_claim_supported":
            raise MigrationV11Error(
                f"{graph_evidence_id}: claim prognostico approvato ma questa fase non "
                "ne materializza nessuno; serve una decisione esplicita"
            )
        # Ogni altro verdetto non produce claim, ed e' un esito legittimo.

    claims_by_ge: dict[str, list[Any]] = {}
    for claim in diagnostic + prognostic:
        claims_by_ge.setdefault(claim.graph_evidence_id, []).append(claim)

    # --- deprecazioni riviste ------------------------------------------------
    deprecations: list[LegacyStatementDeprecation] = []
    for deprecation in base.deprecations:
        graph_evidence_id = deprecation.graph_evidence_id
        new_claims = claims_by_ge.get(graph_evidence_id, [])
        audit = audit_by_ge.get(graph_evidence_id)

        if new_claims:
            state = CLAIM_TYPE_TO_STATE_V11[sorted(c.claim_type for c in new_claims)[0]]
            deprecations.append(
                replace(
                    deprecation,
                    deprecation_state=state,
                    replacement_claim_ids=tuple(sorted(c.claim_id for c in new_claims)),
                    deprecation_reason=(
                        "Lo statement e' sostituito da un claim tipizzato nel dominio "
                        "che lo descrive: il record non era senza contenuto, era senza "
                        "un tipo che potesse ospitarlo."
                    ),
                    migration_version=MODEL_SCHEMA_VERSION_V11,
                )
            )
            continue

        if audit is not None and audit["verdict"] == "non_therapeutic_claim_unresolved":
            deprecations.append(
                replace(
                    deprecation,
                    deprecation_state=PROMOTION_BLOCKED_STATE,
                    replacement_claim_ids=(),
                    deprecation_reason=(
                        f"{NO_CLAIM_REASON}: la fonte {audit['source_id']} misura "
                        "l'effetto di un trattamento e non riporta alcun esito "
                        "prognostico per il biomarcatore. Lo statement non ha un "
                        "sostituto e non puo' restare promuovibile come claim "
                        f"prognostico. {UNRESOLVED_REASON}."
                    ),
                    migration_version=MODEL_SCHEMA_VERSION_V11,
                )
            )
            continue

        deprecations.append(replace(deprecation, migration_version=MODEL_SCHEMA_VERSION_V11))

    # --- parent aggiornati ---------------------------------------------------
    parents: list[GraphEvidenceRecord] = []
    for parent in base.parents:
        new_claims = claims_by_ge.get(parent.graph_evidence_id, [])
        if new_claims:
            parent = replace(
                parent,
                child_claim_ids=tuple(parent.child_claim_ids)
                + tuple(sorted(c.claim_id for c in new_claims)),
                deprecated_statement_ids=tuple(
                    d.legacy_statement_id
                    for d in deprecations
                    if d.graph_evidence_id == parent.graph_evidence_id
                ),
            )
        parents.append(parent)

    deprecation_by_ge = {d.graph_evidence_id: d for d in deprecations}
    without_claims = tuple(
        _parent_without_claim_record(
            parent,
            audit_by_ge.get(parent.graph_evidence_id),
            deprecation_by_ge.get(parent.graph_evidence_id),
        )
        for parent in parents
        if not parent.child_claim_ids
    )

    _check_no_id_collisions(
        [c.claim_id for c in base.claims], diagnostic, prognostic, parents
    )

    return ShadowMigrationV11Result(
        parents=tuple(parents),
        therapeutic_claims=base.claims,
        diagnostic_claims=tuple(sorted(diagnostic, key=lambda c: c.claim_id)),
        prognostic_claims=tuple(sorted(prognostic, key=lambda c: c.claim_id)),
        unsupported=base.unsupported,
        unresolved=base.unresolved,
        deprecations=tuple(sorted(deprecations, key=lambda d: d.legacy_statement_id)),
        parents_without_claims=without_claims,
    )


def _check_no_id_collisions(
    therapeutic_ids: Sequence[str],
    diagnostic: Sequence[DiagnosticClaim],
    prognostic: Sequence[PrognosticClaim],
    parents: Sequence[GraphEvidenceRecord],
) -> None:
    seen: dict[str, str] = {i: "therapeutic" for i in therapeutic_ids}
    for group, label in ((diagnostic, "diagnostic"), (prognostic, "prognostic")):
        for claim in group:
            if claim.claim_id in seen:
                raise MigrationV11Error(
                    f"collisione di ID {claim.claim_id}: {seen[claim.claim_id]} e {label}"
                )
            seen[claim.claim_id] = label
    for parent in parents:
        if parent.parent_id in seen:
            raise MigrationV11Error(
                f"collisione di ID {parent.parent_id}: {seen[parent.parent_id]} e parent"
            )
