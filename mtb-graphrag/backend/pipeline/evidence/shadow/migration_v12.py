"""API pubblica dell'aggiornamento shadow 1.2."""

from backend.pipeline.evidence.shadow.migration_v12_logic import (
    CURRENT_DISEASE_SCOPE,
    DEPRECATION_REASON,
    DEPRECATION_STATUS,
    MigrationV12Error,
    NARROWED_DISEASE_SCOPE,
    REPOSITORY_VERSION,
    REQUIRED_GRAPH_EVIDENCE_IDS,
    SCOPE_NARROWING_REASON,
    SOURCE_UNIT_ID,
    ShadowMigrationV12Result,
    narrow_reviewed_diagnostic_claims,
)

__all__ = [
    "CURRENT_DISEASE_SCOPE",
    "DEPRECATION_REASON",
    "DEPRECATION_STATUS",
    "MigrationV12Error",
    "NARROWED_DISEASE_SCOPE",
    "REPOSITORY_VERSION",
    "REQUIRED_GRAPH_EVIDENCE_IDS",
    "SCOPE_NARROWING_REASON",
    "SOURCE_UNIT_ID",
    "ShadowMigrationV12Result",
    "narrow_reviewed_diagnostic_claims",
]
