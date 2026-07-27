"""Applicazione della terminologia verificata ai claim tipizzati dello shadow.

La terminology closure ha deciso due cose diverse su due coppie diverse, e la
1.3 deve conservare la differenza invece di appiattirla su un'unica nozione di
"risolto":

    BGJ398 / infigratinib     verificato, globale  -> canonicalizzazione applicata
    AUY922 / luminespib       insufficiente        -> nessun mapping, resta unresolved

Applicare il primo mapping cambia una **rappresentazione canonica**, non una
proposizione. Il claim continua a dire quello che diceva: che due inibitori
somministrati insieme sopprimono la trasformazione, senza che il risultato sia
attribuibile a uno dei due. Per questo il numero di claim non cambia, l'aggregato
non si scompone, e `permits_member_specific_claims` resta falso.

Cambia pero' l'**identita'**, perche' la rappresentazione canonica e' uno dei
campi dell'hash. Il claim non viene mutato sul posto: quello vecchio viene
ritirato con la sua lineage e ne nasce uno nuovo con l'ID ricalcolato dalla
formula reale. Un aggiornamento in-place lascerebbe in giro due oggetti diversi
con lo stesso ID a seconda di quando li si e' letti.

Il letterale della fonte non viene toccato. `BGJ398` e' cio' che il testo del
2013 dice, e nessuna identificazione successiva puo' riscrivere una fonte: la
canonicalizzazione aggiunge una lettura, non sostituisce un documento.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from backend.pipeline.evidence.shadow.claims import AggregateInterventionClaim
from backend.pipeline.evidence.shadow.domain import domain_of
from backend.pipeline.evidence.shadow.identity import claim_id as compute_claim_id
from backend.pipeline.evidence.shadow.migration_v12_logic import (
    ShadowMigrationV12Result,
)
from backend.pipeline.evidence.shadow.parent import GraphEvidenceRecord
from backend.pipeline.evidence.shadow.schema import MODEL_SCHEMA_VERSION_V11

REPOSITORY_VERSION = "qualified_claim_repository/1.3"

VERSION_BUMP_REASON = (
    "verified intervention terminology update plus directional disease policy "
    "integration"
)

TERMINOLOGY_REGISTRY_VERSION = "shadow_terminology_registry/1.0"

# La decisione verificata, citata per ID e non ricostruita qui.
VERIFIED_DECISION_ID = "TP-BGJ398-INFIGRATINIB"
VERIFIED_QUEUE_ID = "TRQ-BGJ398"
VERIFIED_SOURCE_LITERAL = "BGJ398"
VERIFIED_CANONICAL_LABEL = "infigratinib"
VERIFIED_CANONICAL_ID = "TIV-INFIGRATINIB"

# La decisione che resta aperta, citata perche' resti visibile.
UNRESOLVED_DECISION_ID = "TP-AUY922-LUMINESPIB"
UNRESOLVED_QUEUE_ID = "TRQ-AUY922"
UNRESOLVED_SOURCE_LITERAL = "AUY922"
UNRESOLVED_GRAPH_TERM = "luminespib"

# I due gruppi su cui il mapping verificato ha effetto. Sono dichiarati, non
# cercati: se il repository ne contenesse un terzo la fase deve fermarsi, non
# estendere silenziosamente il perimetro di una review chiusa.
CANONICALIZED_GRAPH_EVIDENCE_IDS = ("evidence:1851", "evidence:1853")

REPLACEMENT_REASON = "CANONICAL_INTERVENTION_LABEL_UPDATED_BY_VERIFIED_TERMINOLOGY"
DEPRECATION_STATUS = "replaced_by_terminology_canonicalized_claim"

REASON_CODES = (
    "AGGREGATE_RESULT_REMAINS_NON_SEPARABLE",
    "DEVELOPMENT_CODE_VERIFIED",
    "FORMULATION_RELATION_REQUIRES_QUALIFIER",
    "GLOBAL_DRUG_IDENTITY_CONFIRMED",
    "SOURCE_LITERAL_PRESERVED",
)

UNRESOLVED_REASON_CODES = (
    "INSUFFICIENT_AUTHORITATIVE_SOURCE",
    "MAPPING_REMAINS_UNRESOLVED",
    "SOURCE_LITERAL_PRESERVED",
    "VOCABULARY_CONCEPT_ID_CONFLICT",
)

REVIEW_STATUS = "first_review_complete"
REVIEW_INDEPENDENCE = "non_independent"
PROPAGATION_POLICY = "prototype_only"


class TerminologyApplicationError(RuntimeError):
    """Il mapping verificato non coincide con il repository da aggiornare."""


def _normalized(label: str) -> str:
    return " ".join(str(label).split())


def canonical_aggregate_label(members: Iterable[str]) -> str:
    """Etichetta canonica di un insieme non separabile.

    L'ordinamento e' case-insensitive e questo rende l'etichetta — e quindi
    l'ID — indipendente dall'ordine in cui i membri sono scritti nella fonte.
    E' la stessa proprieta' che `canonical_regimen` da' ai regimi, ottenuta qui
    senza riusare quella funzione perche' un aggregato non e' un regime e le due
    identita' non devono poter convergere per caso.
    """
    normalized = [_normalized(member) for member in members]
    if not normalized or any(not member for member in normalized):
        raise TerminologyApplicationError(
            "un aggregato canonicalizzato richiede membri non vuoti"
        )
    return " + ".join(sorted(normalized, key=str.lower))


@dataclass(frozen=True)
class CanonicalizedAggregateClaim(AggregateInterventionClaim):
    """Aggregato con rappresentazione canonica e letterali di fonte distinti.

    Le due liste non sono ridondanti. `canonical_members` e' cio' su cui si
    calcola l'identita' e cio' che una query terminologicamente aggiornata
    raggiunge; `source_literal_members` e' cio' che la fonte dice e cio' che una
    query scritta con il codice di sviluppo raggiunge. Tenerle separate e' la
    sola forma in cui la canonicalizzazione resta reversibile.
    """

    canonical_members: tuple[str, ...] = ()
    source_literal_members: tuple[str, ...] = ()
    terminology_provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.canonical_members:
            raise TerminologyApplicationError(
                f"{self.claim_id}: aggregato canonicalizzato senza membri canonici"
            )
        if not self.source_literal_members:
            raise TerminologyApplicationError(
                f"{self.claim_id}: aggregato canonicalizzato senza letterali di fonte"
            )
        if len(self.canonical_members) != len(self.source_literal_members):
            raise TerminologyApplicationError(
                f"{self.claim_id}: canonici e letterali non sono in corrispondenza"
            )

    @property
    def intervention_members(self) -> tuple[str, ...]:
        """Membri raggiungibili dal match: canonici piu' letterali non coincidenti.

        Un aggregato resta raggiungibile con il nome che la fonte usa anche dopo
        essere stato canonicalizzato. Nessuno dei due insiemi promuove il claim:
        un membro raggiunto produce `aggregate_member_related`, che e' warning e
        non primario, esattamente come prima della canonicalizzazione.
        """
        return tuple(
            dict.fromkeys(
                tuple(self.canonical_members) + tuple(self.source_literal_members)
            )
        )

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload.update(
            {
                "canonical_members": list(self.canonical_members),
                "source_literal_members": list(self.source_literal_members),
                "aggregate_members_literal": list(self.source_literal_members),
                "terminology_provenance": dict(self.terminology_provenance),
                "permits_member_specific_claims": False,
            }
        )
        return payload


@dataclass(frozen=True)
class ShadowMigrationV13Result:
    """Repository 1.3: la 1.2 con la sola canonicalizzazione verificata applicata."""

    parents: tuple[GraphEvidenceRecord, ...]
    therapeutic_claims: tuple[Any, ...]
    diagnostic_claims: tuple[Any, ...]
    prognostic_claims: tuple[Any, ...]
    unsupported: tuple[Any, ...]
    unresolved: tuple[Any, ...]
    deprecations: tuple[Any, ...]
    parents_without_claims: tuple[dict[str, Any], ...]
    deprecated_diagnostic_claims: tuple[dict[str, Any], ...]
    deprecated_aggregate_claims: tuple[dict[str, Any], ...]
    diagnostic_replacement_map: tuple[dict[str, Any], ...]
    replacement_lineage: tuple[dict[str, Any], ...]
    source_review: dict[str, Any]
    schema_version: str = MODEL_SCHEMA_VERSION_V11
    repository_version: str = REPOSITORY_VERSION

    @property
    def evidence_claims(self) -> tuple[Any, ...]:
        return tuple(
            sorted(
                self.therapeutic_claims
                + self.diagnostic_claims
                + self.prognostic_claims,
                key=lambda claim: (domain_of(claim), claim.claim_type, claim.claim_id),
            )
        )

    @property
    def total_claims(self) -> int:
        return len(self.evidence_claims)


def _mapping_from_decision(decision: Mapping[str, Any]) -> dict[str, str]:
    """Estrae il mapping dalla decisione congelata, senza fidarsi dei default."""
    if decision.get("pair_id") != VERIFIED_DECISION_ID:
        raise TerminologyApplicationError(
            f"decisione inattesa: {decision.get('pair_id')!r}"
        )
    if not decision.get("is_verified") or not decision.get("is_global"):
        raise TerminologyApplicationError(
            f"{VERIFIED_DECISION_ID}: la decisione non e' verificata e globale"
        )
    if decision.get("mapping_scope") != "global":
        raise TerminologyApplicationError(
            f"{VERIFIED_DECISION_ID}: mapping scope inatteso"
        )
    if decision.get("decided_by_string_similarity"):
        raise TerminologyApplicationError(
            f"{VERIFIED_DECISION_ID}: decisione dedotta da somiglianza di stringa"
        )
    if not decision.get("circularity_control_passed"):
        raise TerminologyApplicationError(
            f"{VERIFIED_DECISION_ID}: controllo di circolarita' non superato"
        )
    if decision.get("gold_used_for_decisions"):
        raise TerminologyApplicationError(
            f"{VERIFIED_DECISION_ID}: la decisione dichiara di aver usato il gold"
        )
    source = str(decision.get("source_literal_term") or "")
    canonical = str(decision.get("canonical_label") or "")
    if source != VERIFIED_SOURCE_LITERAL or canonical != VERIFIED_CANONICAL_LABEL:
        raise TerminologyApplicationError(
            f"{VERIFIED_DECISION_ID}: coppia inattesa {source!r} -> {canonical!r}"
        )
    return {"source_literal": source, "canonical_label": canonical}


def _validate_unresolved(decision: Mapping[str, Any]) -> None:
    """AUY922 deve restare esattamente dove la review lo ha lasciato."""
    if decision.get("pair_id") != UNRESOLVED_DECISION_ID:
        raise TerminologyApplicationError(
            f"decisione unresolved inattesa: {decision.get('pair_id')!r}"
        )
    if decision.get("is_verified") or decision.get("is_global"):
        raise TerminologyApplicationError(
            f"{UNRESOLVED_DECISION_ID}: promosso a verificato fuori da una review"
        )
    if decision.get("mapping_scope") != "none":
        raise TerminologyApplicationError(
            f"{UNRESOLVED_DECISION_ID}: mapping scope non vuoto"
        )
    if decision.get("decision") != "insufficient_authoritative_evidence":
        raise TerminologyApplicationError(
            f"{UNRESOLVED_DECISION_ID}: decisione diversa da quella congelata"
        )


def _terminology_provenance(claim: AggregateInterventionClaim) -> dict[str, Any]:
    return {
        "authoritative_source": "peer_reviewed_record_plus_drug_vocabulary",
        "canonical_intervention_id": VERIFIED_CANONICAL_ID,
        "canonical_label": VERIFIED_CANONICAL_LABEL,
        "circularity_control_passed": True,
        "decided_by_string_similarity": False,
        "formulation_caveat": (
            "Il sale infigratinib fosfato ha concept id proprio e non viene fuso "
            "nella moiety."
        ),
        "mapping_scope": "global",
        "propagation_policy": PROPAGATION_POLICY,
        "queue_id": VERIFIED_QUEUE_ID,
        "reason_codes": list(REASON_CODES),
        "review_independence": REVIEW_INDEPENDENCE,
        "review_status": REVIEW_STATUS,
        "source_literal_preserved": True,
        "source_literal_term": VERIFIED_SOURCE_LITERAL,
        "superseded_claim_id": claim.claim_id,
        "terminology_decision_id": VERIFIED_DECISION_ID,
    }


def _canonicalize(claim: AggregateInterventionClaim) -> CanonicalizedAggregateClaim:
    """Sostituisce il solo letterale verificato dentro l'insieme non separabile."""
    literals = tuple(claim.aggregate_members_literal)
    if VERIFIED_SOURCE_LITERAL not in literals:
        raise TerminologyApplicationError(
            f"{claim.claim_id}: il letterale {VERIFIED_SOURCE_LITERAL} non compare "
            "fra i membri dell'aggregato"
        )
    canonical_members = tuple(
        VERIFIED_CANONICAL_LABEL if member == VERIFIED_SOURCE_LITERAL else member
        for member in literals
    )
    label = canonical_aggregate_label(canonical_members)
    provenance = dict(claim.provenance)
    provenance["terminology_canonicalization"] = _terminology_provenance(claim)
    candidate = replace(
        claim,
        aggregate_label=label,
        provenance=provenance,
    )
    new_id = compute_claim_id(
        graph_evidence_id=claim.graph_evidence_id,
        claim_type=claim.claim_type,
        canonical_intervention_or_regimen=candidate.canonical_intervention,
        biomarker=claim.biomarker,
        direction=claim.direction,
        polarity=claim.polarity,
        source_unit_id=claim.source_unit_ids[0],
    )
    return CanonicalizedAggregateClaim(
        claim_id=new_id,
        parent_id=claim.parent_id,
        graph_evidence_id=claim.graph_evidence_id,
        biomarker=claim.biomarker,
        disease_scope=claim.disease_scope,
        direction=claim.direction,
        polarity=claim.polarity,
        source_unit_ids=claim.source_unit_ids,
        locators=claim.locators,
        review_status=claim.review_status,
        provenance=provenance,
        evidence_setting=claim.evidence_setting,
        deprecated=False,
        schema_version=MODEL_SCHEMA_VERSION_V11,
        aggregate_type=claim.aggregate_type,
        aggregate_label=label,
        aggregate_members_literal=literals,
        permits_member_specific_claims=False,
        migration_origin=claim.migration_origin,
        canonical_members=canonical_members,
        source_literal_members=literals,
        terminology_provenance=_terminology_provenance(claim),
    )


def _lineage_row(
    old: AggregateInterventionClaim,
    new: CanonicalizedAggregateClaim,
) -> dict[str, Any]:
    return {
        "canonical_label_after": new.aggregate_label,
        "canonical_label_before": old.aggregate_label,
        "claim_type_after": new.claim_type,
        "claim_type_before": old.claim_type,
        "effective_repository_version": REPOSITORY_VERSION,
        "graph_evidence_id": old.graph_evidence_id,
        "new_claim_id": new.claim_id,
        "old_claim_id": old.claim_id,
        "parent_id": old.parent_id,
        "permits_member_specific_claims": False,
        "propagation_policy": PROPAGATION_POLICY,
        "reason_code": REPLACEMENT_REASON,
        "reason_codes": list(REASON_CODES),
        "reversible": True,
        "review_independence": REVIEW_INDEPENDENCE,
        "review_status": REVIEW_STATUS,
        "source_literals": list(new.source_literal_members),
        "terminology_decision_id": VERIFIED_DECISION_ID,
    }


def _deprecated_snapshot(
    old: AggregateInterventionClaim, new: CanonicalizedAggregateClaim
) -> dict[str, Any]:
    snapshot = old.to_dict()
    snapshot.update(
        {
            "deprecated": True,
            "deprecation_status": DEPRECATION_STATUS,
            "effective_repository_version": REPOSITORY_VERSION,
            "reason_code": REPLACEMENT_REASON,
            "replacement_claim_id": new.claim_id,
            "reversible": True,
            "terminology_decision_id": VERIFIED_DECISION_ID,
        }
    )
    return snapshot


def apply_verified_terminology(
    base: ShadowMigrationV12Result,
    mapping_decisions: Sequence[Mapping[str, Any]],
) -> ShadowMigrationV13Result:
    """Applica il solo mapping verificato ai due aggregate claim dichiarati."""
    by_pair = {row.get("pair_id"): row for row in mapping_decisions}
    if VERIFIED_DECISION_ID not in by_pair or UNRESOLVED_DECISION_ID not in by_pair:
        raise TerminologyApplicationError(
            "le due decisioni di terminologia attese non sono entrambe presenti"
        )
    _mapping_from_decision(by_pair[VERIFIED_DECISION_ID])
    _validate_unresolved(by_pair[UNRESOLVED_DECISION_ID])

    declared = tuple(sorted(by_pair[VERIFIED_DECISION_ID].get("affected_groups") or ()))
    if declared != CANONICALIZED_GRAPH_EVIDENCE_IDS:
        raise TerminologyApplicationError(
            f"gruppi coinvolti inattesi: {declared}"
        )

    targets = {
        claim.graph_evidence_id: claim
        for claim in base.therapeutic_claims
        if claim.claim_type == "aggregate_intervention_claim"
        and VERIFIED_SOURCE_LITERAL in tuple(claim.aggregate_members_literal)
    }
    if tuple(sorted(targets)) != CANONICALIZED_GRAPH_EVIDENCE_IDS:
        raise TerminologyApplicationError(
            f"aggregati con letterale {VERIFIED_SOURCE_LITERAL} inattesi: "
            f"{tuple(sorted(targets))}"
        )

    replacements: dict[str, CanonicalizedAggregateClaim] = {}
    deprecated: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    for graph_evidence_id in CANONICALIZED_GRAPH_EVIDENCE_IDS:
        old = targets[graph_evidence_id]
        new = _canonicalize(old)
        replacements[old.claim_id] = new
        deprecated.append(_deprecated_snapshot(old, new))
        lineage.append(_lineage_row(old, new))

    therapeutic = tuple(
        replacements.get(claim.claim_id, claim) for claim in base.therapeutic_claims
    )
    new_id_by_old = {old_id: new.claim_id for old_id, new in replacements.items()}
    parents = tuple(
        replace(
            parent,
            child_claim_ids=tuple(
                sorted(
                    new_id_by_old.get(claim_id, claim_id)
                    for claim_id in parent.child_claim_ids
                )
            ),
        )
        for parent in base.parents
    )

    active_ids = [claim.claim_id for claim in therapeutic]
    active_ids.extend(claim.claim_id for claim in base.diagnostic_claims)
    active_ids.extend(claim.claim_id for claim in base.prognostic_claims)
    if len(active_ids) != len(set(active_ids)):
        raise TerminologyApplicationError("collisione fra claim ID attivi nella 1.3")
    if set(active_ids) & set(new_id_by_old):
        raise TerminologyApplicationError(
            "un claim ritirato dalla canonicalizzazione e' ancora fra gli attivi"
        )
    if len(therapeutic) != len(base.therapeutic_claims):
        raise TerminologyApplicationError(
            "la canonicalizzazione ha cambiato il numero di proposizioni terapeutiche"
        )

    return ShadowMigrationV13Result(
        parents=parents,
        therapeutic_claims=therapeutic,
        diagnostic_claims=base.diagnostic_claims,
        prognostic_claims=base.prognostic_claims,
        unsupported=base.unsupported,
        unresolved=base.unresolved,
        deprecations=base.deprecations,
        parents_without_claims=base.parents_without_claims,
        deprecated_diagnostic_claims=base.deprecated_diagnostic_claims,
        deprecated_aggregate_claims=tuple(
            sorted(deprecated, key=lambda row: row["claim_id"])
        ),
        diagnostic_replacement_map=base.replacement_map,
        replacement_lineage=tuple(sorted(lineage, key=lambda row: row["old_claim_id"])),
        source_review=dict(base.source_review),
    )


def terminology_registry(result: ShadowMigrationV13Result) -> dict[str, Any]:
    """Stato terminologico della 1.3: cio' che e' chiuso e cio' che non lo e'.

    La coppia irrisolta e' registrata con lo stesso rilievo di quella verificata.
    Un registro che elencasse soltanto i mapping applicati lascerebbe credere che
    la coda sia vuota, e una coda che sembra vuota non viene piu' guardata.
    """
    return {
        "applied_mappings": [
            {
                "affected_claims": [
                    {
                        "graph_evidence_id": row["graph_evidence_id"],
                        "new_claim_id": row["new_claim_id"],
                        "old_claim_id": row["old_claim_id"],
                    }
                    for row in result.replacement_lineage
                ],
                "canonical_intervention_id": VERIFIED_CANONICAL_ID,
                "canonical_label": VERIFIED_CANONICAL_LABEL,
                "claims_atomized": 0,
                "confidence": "high",
                "decision": "verified_development_code_for_same_intervention",
                "is_global": True,
                "is_verified": True,
                "mapping_scope": "global",
                "propagation_policy": PROPAGATION_POLICY,
                "queue_id": VERIFIED_QUEUE_ID,
                "reason_codes": list(REASON_CODES),
                "review_independence": REVIEW_INDEPENDENCE,
                "review_status": REVIEW_STATUS,
                "source_literal_preserved": True,
                "source_literal_term": VERIFIED_SOURCE_LITERAL,
                "terminology_decision_id": VERIFIED_DECISION_ID,
            }
        ],
        "collisions": 0,
        "deduplications": 0,
        "propositions_created": 0,
        "propositions_removed": 0,
        "registry_version": TERMINOLOGY_REGISTRY_VERSION,
        "repository_version": REPOSITORY_VERSION,
        "unresolved_mappings": [
            {
                "canonical_label": "",
                "claims_materialized": 0,
                "confidence": "insufficient",
                "decision": "insufficient_authoritative_evidence",
                "exact_alias_created": False,
                "graph_term": UNRESOLVED_GRAPH_TERM,
                "is_global": False,
                "is_verified": False,
                "mapping_scope": "none",
                "propagation_policy": PROPAGATION_POLICY,
                "queue_id": UNRESOLVED_QUEUE_ID,
                "reason_codes": list(UNRESOLVED_REASON_CODES),
                "recommendation": "require_external_review",
                "review_independence": REVIEW_INDEPENDENCE,
                "review_status": REVIEW_STATUS,
                "source_literal_preserved": True,
                "source_literal_term": UNRESOLVED_SOURCE_LITERAL,
                "terminology_decision_id": UNRESOLVED_DECISION_ID,
                "unresolved_reason": (
                    "Nessuna fonte autorevole non circolare collega il letterale "
                    "della fonte al nome generico del grafo."
                ),
            }
        ],
        "queue_fully_resolved": False,
        # L'associazione irrisolta su infigratinib resta irrisolta, ma non piu'
        # per la ragione di prima. Il mapping ora e' verificato; cio' che continua
        # a impedirne la materializzazione e' la non separabilita' dell'aggregato,
        # decisa dall'adjudication e non da questa fase.
        "unresolved_associations_superseding_reason": {
            "association_ids": [
                "UNR-0735290c4b6f33a27c79",
                "UNR-45adc52a7eb9696c1aca",
            ],
            "materialized_by_this_phase": False,
            "previous_reason_code": "PENDING_ALIAS_BLOCKS_MATERIALIZATION",
            "records_modified": False,
            "superseding_reason_code": "AGGREGATE_RESULT_REMAINS_NON_SEPARABLE",
        },
    }


__all__ = [
    "CANONICALIZED_GRAPH_EVIDENCE_IDS",
    "DEPRECATION_STATUS",
    "REPLACEMENT_REASON",
    "REPOSITORY_VERSION",
    "TERMINOLOGY_REGISTRY_VERSION",
    "UNRESOLVED_DECISION_ID",
    "UNRESOLVED_SOURCE_LITERAL",
    "VERIFIED_CANONICAL_LABEL",
    "VERIFIED_DECISION_ID",
    "VERIFIED_SOURCE_LITERAL",
    "VERSION_BUMP_REASON",
    "CanonicalizedAggregateClaim",
    "ShadowMigrationV13Result",
    "TerminologyApplicationError",
    "apply_verified_terminology",
    "canonical_aggregate_label",
    "terminology_registry",
]
