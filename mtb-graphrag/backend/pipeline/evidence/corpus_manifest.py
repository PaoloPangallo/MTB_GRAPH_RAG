"""Manifest e freeze del qualification corpus.

Il valore di un freeze sta interamente in cio' che **impedisce**. Un manifest che
si lasciasse impostare a `frozen` su richiesta certificherebbe soltanto che
qualcuno ha scritto la parola: qui `freeze_status` e' calcolato dai fatti, e le
guardie sono la parte importante del modulo.

Le ragioni del blocco vengono restituite tutte insieme e non alla prima: un
corpus bloccato per sei motivi diversi va sistemato una volta, non sei.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

MANIFEST_VERSION = "qualification_corpus_manifest/1.0"

DRAFT = "draft"
FIRST_REVIEW_COMPLETE = "first_review_complete"
AWAITING_SECOND_REVIEW = "awaiting_second_review"
ADJUDICATED = "adjudicated"
FROZEN = "frozen"
BLOCKED = "blocked"

FREEZE_STATUSES = (
    DRAFT,
    FIRST_REVIEW_COMPLETE,
    AWAITING_SECOND_REVIEW,
    ADJUDICATED,
    FROZEN,
    BLOCKED,
)


def content_hash(payload: Any) -> str:
    """SHA-256 della forma canonica: stabile fra esecuzioni e piattaforme."""
    from benchmarks.mtb_evidence.pilot.audit_lib.serialize import canonical_json

    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass
class FreezeEvaluation:
    """Esito delle guardie di freeze, con tutti i motivi del blocco."""

    status: str
    blockers: tuple[str, ...] = ()

    @property
    def is_frozen(self) -> bool:
        return self.status == FROZEN

    def as_dict(self) -> dict[str, Any]:
        return {"freeze_status": self.status, "blockers": list(self.blockers)}


def evaluate_freeze(
    *,
    units: Sequence[Any],
    gold_records: Sequence[Any],
    required_second_reviews: int,
    unresolved_sources: int,
    snapshot_fingerprint: str,
    expected_snapshot_fingerprint: str,
    statement_repository_hash: str,
    expected_statement_repository_hash: str,
) -> FreezeEvaluation:
    """Decide `freeze_status` dai fatti, non dall'intenzione."""
    from .profile_unit import MACHINE_EXTRACTED, UNREVIEWED
    from .qualification_gold import GOLD_DISAGREEMENT

    blockers: list[str] = []

    missing_provenance = [
        unit.profile_unit_id for unit in units if not unit.provenance_complete()
    ]
    if missing_provenance:
        blockers.append(
            f"{len(missing_provenance)} unita' con dimensioni note prive di provenance"
        )

    # Un profilo «senza fonte» e' un profilo che afferma qualcosa di clinico senza
    # che nessuno abbia letto nulla. E' la condizione che rende un corpus inutile
    # e pericoloso allo stesso tempo, perche' resta formalmente valido.
    sourceless = [
        unit.profile_unit_id
        for unit in units
        if unit.known_dimensions()
        and unit.extraction_status == UNREVIEWED
        and not unit.source_spans
        and not any(item.source_locator for item in unit.provenance)
    ]
    if sourceless:
        blockers.append(f"{len(sourceless)} unita' con valori clinici e nessuna fonte dichiarata")

    if unresolved_sources:
        blockers.append(f"{unresolved_sources} fonti con identificatore non risolto")

    second_reviews = sum(1 for record in gold_records if record.has_two_real_reviews)
    if second_reviews < required_second_reviews:
        blockers.append(
            f"seconda revisione mancante su {required_second_reviews - second_reviews} "
            f"coppie su {required_second_reviews} richieste"
        )

    disagreements = [
        record.gold_link_id
        for record in gold_records
        if record.state == GOLD_DISAGREEMENT
    ]
    if disagreements:
        blockers.append(f"{len(disagreements)} disagreement non adjudicati")

    if expected_snapshot_fingerprint and snapshot_fingerprint != expected_snapshot_fingerprint:
        blockers.append("snapshot_fingerprint diverso da quello atteso")
    if (
        expected_statement_repository_hash
        and statement_repository_hash != expected_statement_repository_hash
    ):
        blockers.append("statement_repository_hash diverso da quello atteso")

    if blockers:
        # Distinzione voluta: «bloccato» descrive un corpus che ha un difetto,
        # «in attesa di seconda revisione» descrive un corpus sano ma incompleto.
        # Confonderli farebbe sembrare rotto un lavoro semplicemente non finito.
        only_missing_reviews = all(
            blocker.startswith("seconda revisione mancante") for blocker in blockers
        )
        status = AWAITING_SECOND_REVIEW if only_missing_reviews else BLOCKED
        return FreezeEvaluation(status=status, blockers=tuple(blockers))

    if not gold_records:
        return FreezeEvaluation(status=DRAFT, blockers=("nessun record di gold prodotto",))
    return FreezeEvaluation(status=FROZEN)


@dataclass
class QualificationCorpusManifest:
    """Fotografia verificabile del corpus."""

    corpus_version: str
    source_inventory_hash: str
    qualification_scope_hash: str
    statement_repository_hash: str
    source_profiles_hash: str
    profile_units_hash: str
    link_gold_hash: str
    linker_version: str
    schema_versions: Mapping[str, str]
    snapshot_fingerprint: str
    source_count: int = 0
    scoped_source_count: int = 0
    profile_unit_count: int = 0
    reviewed_count: int = 0
    machine_extracted_count: int = 0
    provisional_count: int = 0
    frozen_count: int = 0
    unresolved_count: int = 0
    evaluated_link_count: int = 0
    not_evaluated_link_count: int = 0
    created_at: str = ""
    freeze_status: str = DRAFT
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.freeze_status not in FREEZE_STATUSES:
            raise ValueError(
                f"freeze_status non ammesso: {self.freeze_status!r}. Ammessi: {list(FREEZE_STATUSES)}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "corpus_version": self.corpus_version,
            "manifest_version": MANIFEST_VERSION,
            "source_inventory_hash": self.source_inventory_hash,
            "qualification_scope_hash": self.qualification_scope_hash,
            "statement_repository_hash": self.statement_repository_hash,
            "source_profiles_hash": self.source_profiles_hash,
            "profile_units_hash": self.profile_units_hash,
            "link_gold_hash": self.link_gold_hash,
            "linker_version": self.linker_version,
            "schema_versions": dict(self.schema_versions),
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "source_count": self.source_count,
            "scoped_source_count": self.scoped_source_count,
            "profile_unit_count": self.profile_unit_count,
            "reviewed_count": self.reviewed_count,
            "machine_extracted_count": self.machine_extracted_count,
            "provisional_count": self.provisional_count,
            "frozen_count": self.frozen_count,
            "unresolved_count": self.unresolved_count,
            "evaluated_link_count": self.evaluated_link_count,
            "not_evaluated_link_count": self.not_evaluated_link_count,
            "created_at": self.created_at,
            "freeze_status": self.freeze_status,
            "blockers": list(self.blockers),
        }


__all__ = [
    "MANIFEST_VERSION",
    "FREEZE_STATUSES",
    "DRAFT",
    "FIRST_REVIEW_COMPLETE",
    "AWAITING_SECOND_REVIEW",
    "ADJUDICATED",
    "FROZEN",
    "BLOCKED",
    "content_hash",
    "FreezeEvaluation",
    "evaluate_freeze",
    "QualificationCorpusManifest",
]
