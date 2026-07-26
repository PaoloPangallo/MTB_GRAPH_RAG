"""Aggiornamento shadow 1.2 per il narrowing locale dei claim diagnostici.

La 1.2 non cambia il modello 1.1 e non introduce una gerarchia di malattia.
Autentica le due decisioni della source closure, sostituisce i claim attivi e
conserva separatamente gli snapshot ritirati e la lineage reversibile.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from backend.pipeline.evidence.shadow.domain import domain_of
from backend.pipeline.evidence.shadow.identity import non_therapeutic_claim_id
from backend.pipeline.evidence.shadow.migration_v11 import ShadowMigrationV11Result
from backend.pipeline.evidence.shadow.non_therapeutic_claims import DiagnosticClaim
from backend.pipeline.evidence.shadow.parent import GraphEvidenceRecord
from backend.pipeline.evidence.shadow.schema import MODEL_SCHEMA_VERSION_V11

REPOSITORY_VERSION = "qualified_claim_repository/1.2"
NARROWED_DISEASE_SCOPE = "Intrahepatic Cholangiocarcinoma"
CURRENT_DISEASE_SCOPE = "Cholangiocarcinoma"
SCOPE_NARROWING_REASON = "SOURCE_POPULATION_REQUIRES_NARROWER_DISEASE_SCOPE"
DEPRECATION_REASON = "DISEASE_SCOPE_BROADER_THAN_SOURCE_POPULATION"
DEPRECATION_STATUS = "replaced_by_narrowed_diagnostic_claim"
SOURCE_UNIT_ID = "PU-PMID-24122810-cohort-1"
REQUIRED_GRAPH_EVIDENCE_IDS = ("evidence:1846", "evidence:1847")


class MigrationV12Error(RuntimeError):
    """La source closure non coincide con il repository shadow da aggiornare."""


@dataclass(frozen=True)
class ShadowMigrationV12Result:
    """Repository 1.2 attivo piu' audit dei due claim sostituiti."""

    parents: tuple[GraphEvidenceRecord, ...]
    therapeutic_claims: tuple[Any, ...]
    diagnostic_claims: tuple[DiagnosticClaim, ...]
    prognostic_claims: tuple[Any, ...]
    unsupported: tuple[Any, ...]
    unresolved: tuple[Any, ...]
    deprecations: tuple[Any, ...]
    parents_without_claims: tuple[dict[str, Any], ...]
    deprecated_diagnostic_claims: tuple[dict[str, Any], ...]
    replacement_map: tuple[dict[str, Any], ...]
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
                key=lambda claim: (
                    domain_of(claim),
                    claim.claim_type,
                    claim.claim_id,
                ),
            )
        )

    @property
    def total_claims(self) -> int:
        return len(self.evidence_claims)


def _review_by_evidence(
    review_records: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    reviews = {record["graph_evidence_id"]: record for record in review_records}
    if tuple(sorted(reviews)) != REQUIRED_GRAPH_EVIDENCE_IDS:
        raise MigrationV12Error(
            f"source closure inattesa: attesi {REQUIRED_GRAPH_EVIDENCE_IDS}, "
            f"trovati {tuple(sorted(reviews))}"
        )
    for graph_evidence_id, review in sorted(reviews.items()):
        if review.get("decision") != "diagnostic_claim_requires_narrowing":
            raise MigrationV12Error(
                f"{graph_evidence_id}: decisione di narrowing assente"
            )
        narrowing = review.get("required_narrowing") or ()
        disease = [
            item
            for item in narrowing
            if item.get("field") == "disease_scope"
            and item.get("current") == CURRENT_DISEASE_SCOPE
        ]
        if len(disease) != 1 or disease[0].get("narrowed_to") != NARROWED_DISEASE_SCOPE:
            raise MigrationV12Error(
                f"{graph_evidence_id}: disease scope revisionato inatteso"
            )
    return reviews


def _validate_source_review(source_review: Mapping[str, Any]) -> None:
    expected = {
        "source_unit_id": SOURCE_UNIT_ID,
        "review_status": "first_review_complete",
        "review_independence": "non_independent",
        "propagation_policy": "prototype_only",
        "hard_filterable": False,
        "final_evaluable": False,
    }
    mismatches = {
        key: (source_review.get(key), value)
        for key, value in expected.items()
        if source_review.get(key) != value
    }
    if mismatches:
        raise MigrationV12Error(f"source review non congelata: {mismatches}")
    limitation_codes = {
        item.get("code") for item in source_review.get("limitations") or ()
    }
    required = {
        "PREVALENCE_AGGREGATE_ONLY_NOT_PARTNER_SPECIFIC",
        "CLINICAL_UTILITY_NOT_ASSERTED",
        "ABSTRACT_ONLY_NO_FULL_TEXT",
    }
    if not required <= limitation_codes:
        raise MigrationV12Error(
            f"source review priva delle limitazioni richieste: "
            f"{sorted(required - limitation_codes)}"
        )


def _replacement_claim(
    claim: DiagnosticClaim,
    review: Mapping[str, Any],
    source_review: Mapping[str, Any],
) -> DiagnosticClaim:
    claim_id = non_therapeutic_claim_id(
        graph_evidence_id=claim.graph_evidence_id,
        claim_type=claim.claim_type,
        canonical_subject=claim.canonical_subject,
        biomarker=claim.biomarker,
        disease_scope=NARROWED_DISEASE_SCOPE,
        direction_or_interpretation=claim.diagnostic_interpretation,
        polarity=claim.polarity,
        source_unit_id=SOURCE_UNIT_ID,
    )
    limitations = tuple(
        code
        for code in claim.limitation_codes
        if code != "SOURCE_UNIT_AWAITING_HUMAN_REVIEW"
    ) + ("SECOND_INDEPENDENT_REVIEW_PENDING",)
    provenance = dict(claim.provenance)
    provenance["scope_narrowing"] = {
        "old_claim_id": claim.claim_id,
        "old_disease_scope": claim.disease_scope,
        "new_disease_scope": NARROWED_DISEASE_SCOPE,
        "reason_code": SCOPE_NARROWING_REASON,
        "source_review_id": review["review_id"],
        "source_review_version": source_review["review_version"],
        "review_status": source_review["review_status"],
        "review_independence": source_review["review_independence"],
    }
    return replace(
        claim,
        claim_id=claim_id,
        disease_scope=NARROWED_DISEASE_SCOPE,
        review_status=source_review["review_status"],
        limitation_codes=limitations,
        provenance=provenance,
    )


def narrow_reviewed_diagnostic_claims(
    base: ShadowMigrationV11Result,
    review_records: Sequence[Mapping[str, Any]],
    source_review: Mapping[str, Any],
) -> ShadowMigrationV12Result:
    """Sostituisce esattamente i due claim larghi autenticati dalla closure."""
    reviews = _review_by_evidence(review_records)
    _validate_source_review(source_review)
    old_by_evidence = {
        claim.graph_evidence_id: claim for claim in base.diagnostic_claims
    }
    if tuple(sorted(old_by_evidence)) != REQUIRED_GRAPH_EVIDENCE_IDS:
        raise MigrationV12Error(
            "lo shadow 1.1 non contiene esattamente i due claim diagnostici attesi"
        )

    replacements: list[DiagnosticClaim] = []
    deprecated: list[dict[str, Any]] = []
    replacement_map: list[dict[str, Any]] = []
    new_id_by_old: dict[str, str] = {}

    for graph_evidence_id in REQUIRED_GRAPH_EVIDENCE_IDS:
        old = old_by_evidence[graph_evidence_id]
        review = reviews[graph_evidence_id]
        if (
            old.claim_id != review["claim_id"]
            or old.disease_scope != CURRENT_DISEASE_SCOPE
        ):
            raise MigrationV12Error(
                f"{graph_evidence_id}: claim 1.1 diverso da quello revisionato"
            )
        new = _replacement_claim(old, review, source_review)
        replacements.append(new)
        new_id_by_old[old.claim_id] = new.claim_id

        snapshot = old.to_dict()
        snapshot.update(
            {
                "deprecated": True,
                "deprecation_status": DEPRECATION_STATUS,
                "reason_code": DEPRECATION_REASON,
                "replacement_claim_id": new.claim_id,
                "effective_repository_version": REPOSITORY_VERSION,
                "source_review_id": review["review_id"],
                "reversible": True,
            }
        )
        deprecated.append(snapshot)
        replacement_map.append(
            {
                "legacy_or_shadow_claim_id": old.claim_id,
                "replacement_claim_id": new.claim_id,
                "parent_id": graph_evidence_id,
                "graph_parent_id": old.parent_id,
                "reason_code": DEPRECATION_REASON,
                "source_narrowing_reason_code": SCOPE_NARROWING_REASON,
                "source_review_id": review["review_id"],
                "effective_repository_version": REPOSITORY_VERSION,
                "reversible": True,
                "review_status": source_review["review_status"],
                "review_independence": source_review["review_independence"],
                "propagation_policy": source_review["propagation_policy"],
            }
        )

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

    active_ids = [claim.claim_id for claim in base.therapeutic_claims]
    active_ids.extend(claim.claim_id for claim in replacements)
    if len(active_ids) != len(set(active_ids)):
        raise MigrationV12Error("collisione fra claim ID attivi nella 1.2")
    if set(active_ids) & set(new_id_by_old):
        raise MigrationV12Error("un claim ritirato e' ancora presente fra gli attivi")

    return ShadowMigrationV12Result(
        parents=parents,
        therapeutic_claims=base.therapeutic_claims,
        diagnostic_claims=tuple(
            sorted(replacements, key=lambda claim: claim.claim_id)
        ),
        prognostic_claims=base.prognostic_claims,
        unsupported=base.unsupported,
        unresolved=base.unresolved,
        deprecations=base.deprecations,
        parents_without_claims=base.parents_without_claims,
        deprecated_diagnostic_claims=tuple(
            sorted(deprecated, key=lambda row: row["claim_id"])
        ),
        replacement_map=tuple(
            sorted(
                replacement_map,
                key=lambda row: row["legacy_or_shadow_claim_id"],
            )
        ),
        source_review=dict(source_review),
    )
