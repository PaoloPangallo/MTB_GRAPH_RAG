"""GraphEvidenceRecord: il contenitore di provenienza.

Non e' un claim, e questo non e' un dettaglio di nomenclatura. Il record V2
porta piu' interventi; l'adapter operativo ne promuove il primo a intervento
dello statement, e cosi' facendo afferma qualcosa che la fonte non dice — in
evidence:275 afferma erlotinib mentre la fonte nomina solo `EGFR-TKI`, in
evidence:1851 e evidence:1853 afferma infigratinib mentre la fonte usa solo
BGJ398, in evidence:4759 lega L858R/ex19del a un esito misurato sulle mutazioni
non comuni.

Il parent risolve il problema togliendo l'affermazione invece di sceglierla
meglio: conserva tutti gli interventi V2 come letterali, senza privilegiarne
nessuno, e lascia che i claim nascano dove la revisione li sostiene. Un parent
con zero claim e' un esito legittimo, non una perdita da compensare.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow.schema import MODEL_SCHEMA_VERSION, PARENT_KIND


class ParentSemanticsError(ValueError):
    """Il parent e' stato usato come se fosse un claim."""


# Usi vietati, come li elenca il contratto. Non sono commenti: `check_use`
# solleva, cosi' un uso sbagliato fallisce dove avviene invece di propagarsi in
# una metrica.
FORBIDDEN_USES = (
    "claim_level_candidate_ranking",
    "therapy_score_assignment",
    "therapy_level_metrics",
    "primary_therapeutic_evidence_result",
)

ALLOWED_USES = (
    "graph_lineage",
    "source_resolution",
    "raw_record_inspection",
    "adapter_provenance",
    "audit_trail",
)

PARENT_REASON_CODE = "PARENT_PROVENANCE_CONTAINER_NOT_CLAIM"


@dataclass(frozen=True)
class GraphEvidenceRecord:
    """Provenienza di un graph evidence ID. Nessuna terapia, nessun punteggio."""

    parent_id: str
    graph_evidence_id: str
    source_ids: tuple[str, ...] = ()
    source_record_ids: tuple[str, ...] = ()
    raw_v2_records: tuple[dict[str, Any], ...] = ()
    biomarker_context: str | None = None
    disease_context: str | None = None
    # Tutti gli interventi nominati dal record V2, nell'ordine canonico e senza
    # che nessuno sia marcato come principale. E' il punto in cui il modello si
    # rifiuta di scegliere.
    original_intervention_associations: tuple[str, ...] = ()
    adapter_lineage: tuple[str, ...] = ()
    review_status: str = "not_reviewed"
    deprecated_statement_ids: tuple[str, ...] = ()
    child_claim_ids: tuple[str, ...] = ()
    unsupported_association_ids: tuple[str, ...] = ()
    unresolved_association_ids: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = MODEL_SCHEMA_VERSION

    # --- invarianti ----------------------------------------------------------

    kind: str = PARENT_KIND

    @property
    def is_claim(self) -> bool:
        return False

    @property
    def has_primary_therapy(self) -> bool:
        """Un contenitore non porta una terapia primaria, mai."""
        return False

    @property
    def receives_therapy_score(self) -> bool:
        return False

    @property
    def enters_claim_level_ranking(self) -> bool:
        return False

    @property
    def counted_in_claim_level_metrics(self) -> bool:
        return False

    @property
    def claim_count(self) -> int:
        return len(self.child_claim_ids)

    def check_use(self, use: str) -> None:
        """Solleva se il parent viene impiegato in un uso vietato dal contratto."""
        if use in FORBIDDEN_USES:
            raise ParentSemanticsError(
                f"{self.graph_evidence_id}: uso vietato del contenitore di "
                f"provenienza ({use}); {PARENT_REASON_CODE}"
            )
        if use not in ALLOWED_USES:
            raise ParentSemanticsError(
                f"{self.graph_evidence_id}: uso non dichiarato dal contratto ({use})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_id": self.parent_id,
            "graph_evidence_id": self.graph_evidence_id,
            "kind": self.kind,
            "is_claim": False,
            "source_ids": list(self.source_ids),
            "source_record_ids": list(self.source_record_ids),
            "raw_v2_records": [dict(record) for record in self.raw_v2_records],
            "biomarker_context": self.biomarker_context,
            "disease_context": self.disease_context,
            "original_intervention_associations": list(
                self.original_intervention_associations
            ),
            "adapter_lineage": list(self.adapter_lineage),
            "review_status": self.review_status,
            "deprecated_statement_ids": list(self.deprecated_statement_ids),
            "child_claim_ids": list(self.child_claim_ids),
            "unsupported_association_ids": list(self.unsupported_association_ids),
            "unresolved_association_ids": list(self.unresolved_association_ids),
            "provenance": dict(self.provenance),
            "schema_version": self.schema_version,
        }
