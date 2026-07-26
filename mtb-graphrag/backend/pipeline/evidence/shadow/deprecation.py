"""Mappa di deprecazione degli EvidenceStatement legacy.

Gli statement correnti non vengono cancellati. Restano leggibili come record
storici con un puntatore al parent che li sostituisce, e la deprecazione e'
reversibile: finche' la migrazione e' shadow, il corpus operativo continua a
usarli e questa mappa e' soltanto una descrizione di cosa succederebbe alla
promozione.

`deprecated_without_replacement` e' lo stato che conta di piu'. Due gruppi non
producono alcun claim: non e' una perdita da compensare inventando un
sostitutivo, ed e' esattamente la ragione per cui lo stato esiste separato.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.pipeline.evidence.shadow.schema import MODEL_SCHEMA_VERSION

DEPRECATION_STATES = (
    "replaced_by_atomic_claim",
    "replaced_by_aggregate_claim",
    "replaced_by_regimen_claim",
    "deprecated_without_replacement",
    "preserved_as_legacy_migrated_claim",
)

# Stati aggiunti dal modello 1.1. Il primo copre i claim non terapeutici; il
# secondo copre il caso che il modello 1.0 non sapeva esprimere: uno statement
# che non ha un sostituto ma che non puo' nemmeno restare com'e', perche' la
# fonte contraddice cio' che afferma. `preserved_as_legacy_migrated_claim` lo
# avrebbe lasciato attivo e promuovibile.
DEPRECATION_STATES_V11 = DEPRECATION_STATES + (
    "replaced_by_diagnostic_claim",
    "replaced_by_prognostic_claim",
    "promotion_blocked_pending_full_text",
)

# Stati che impediscono allo statement di essere promosso come claim.
PROMOTION_BLOCKING_STATES = (
    "deprecated_without_replacement",
    "promotion_blocked_pending_full_text",
)

CLAIM_TYPE_TO_STATE = {
    "atomic_intervention_claim": "replaced_by_atomic_claim",
    "aggregate_intervention_claim": "replaced_by_aggregate_claim",
    "regimen_claim": "replaced_by_regimen_claim",
}

CLAIM_TYPE_TO_STATE_V11 = dict(CLAIM_TYPE_TO_STATE) | {
    "diagnostic_claim": "replaced_by_diagnostic_claim",
    "prognostic_claim": "replaced_by_prognostic_claim",
}


class DeprecationError(ValueError):
    """Stato di deprecazione incoerente con i claim sostitutivi."""


@dataclass(frozen=True)
class LegacyStatementDeprecation:
    legacy_statement_id: str
    parent_id: str
    graph_evidence_id: str
    deprecation_state: str
    replacement_claim_ids: tuple[str, ...] = ()
    deprecation_reason: str = ""
    reversible: bool = True
    migration_version: str = MODEL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.deprecation_state not in DEPRECATION_STATES:
            raise DeprecationError(
                f"{self.legacy_statement_id}: stato sconosciuto "
                f"{self.deprecation_state!r}"
            )
        has_replacement = bool(self.replacement_claim_ids)
        if self.deprecation_state == "deprecated_without_replacement" and has_replacement:
            raise DeprecationError(
                f"{self.legacy_statement_id}: dichiarato senza sostituto ma ne ha "
                f"{len(self.replacement_claim_ids)}"
            )
        if self.deprecation_state.startswith("replaced_by") and not has_replacement:
            raise DeprecationError(
                f"{self.legacy_statement_id}: dichiarato sostituito ma senza claim"
            )

    @property
    def is_deprecated(self) -> bool:
        """Lo statement portato avanti come legacy migrato non e' deprecato."""
        return self.deprecation_state != "preserved_as_legacy_migrated_claim"

    def to_dict(self) -> dict[str, Any]:
        return {
            "legacy_statement_id": self.legacy_statement_id,
            "parent_id": self.parent_id,
            "graph_evidence_id": self.graph_evidence_id,
            "deprecation_state": self.deprecation_state,
            "replacement_claim_ids": list(self.replacement_claim_ids),
            "deprecation_reason": self.deprecation_reason,
            "reversible": self.reversible,
            "migration_version": self.migration_version,
            "is_deprecated": self.is_deprecated,
            "statement_still_readable": True,
        }


def state_for(claim_types: tuple[str, ...]) -> str:
    """Stato di deprecazione derivato dai tipi dei claim sostitutivi.

    Con piu' tipi diversi (evidence:11240 produce un regime e un atomico) vince
    il tipo del claim che porta il risultato principale, cioe' il primo in ordine
    canonico: la mappa serve a ritrovare i sostituti, che sono comunque tutti
    elencati in `replacement_claim_ids`.
    """
    if not claim_types:
        return "deprecated_without_replacement"
    return CLAIM_TYPE_TO_STATE[sorted(claim_types)[0]]
