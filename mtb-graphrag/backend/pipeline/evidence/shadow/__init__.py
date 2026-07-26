"""Modello tipizzato parent/claim in modalita' shadow.

Questo package convive con la pipeline operativa senza toccarla. Nessun modulo
operativo lo importa: `v2_adapter`, `repository`, `qualified_retriever` e
`qualified_retrieval_scoring` restano quelli di prima e continuano a produrre gli
stessi output. Qui vive la rappresentazione verso cui il corpus migrera', ma il
corpus operativo non e' ancora promosso.

La distinzione portante e' fra *contenitore di provenienza* e *claim*. Il record
V2 non e' una proposizione terapeutica: e' una riga di grafo con dentro piu'
interventi. Promuoverne il primo a intervento dello statement — quello che fa
l'adapter operativo — e' cio' che ha prodotto i claim non sostenuti trovati
dall'adjudication. Nel modello shadow quel record diventa un
`GraphEvidenceRecord`, che non afferma nulla, e i claim nascono soltanto dove la
revisione documentale li sostiene.
"""

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
    DEPRECATION_STATES,
    LegacyStatementDeprecation,
)
from backend.pipeline.evidence.shadow.identity import (
    CLAIM_ID_FORMULA_VERSION,
    association_id,
    canonical_regimen,
    claim_id,
    claim_identity_payload,
    parent_id,
)
from backend.pipeline.evidence.shadow.parent import GraphEvidenceRecord
from backend.pipeline.evidence.shadow.schema import (
    CLAIM_TYPES,
    MIGRATION_STATUS,
    MODEL_SCHEMA_VERSION,
    SHADOW_REPOSITORY_VERSION,
)

__all__ = [
    "AggregateInterventionClaim",
    "AtomicInterventionClaim",
    "CLAIM_ID_FORMULA_VERSION",
    "CLAIM_TYPES",
    "DEPRECATION_STATES",
    "GraphEvidenceRecord",
    "LegacyStatementDeprecation",
    "MIGRATION_STATUS",
    "MODEL_SCHEMA_VERSION",
    "RegimenClaim",
    "SHADOW_REPOSITORY_VERSION",
    "TypedClaim",
    "UnresolvedAssociation",
    "UnsupportedAssociation",
    "association_id",
    "canonical_regimen",
    "claim_id",
    "claim_identity_payload",
    "parent_id",
]
