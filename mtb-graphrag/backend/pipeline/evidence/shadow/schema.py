"""Versioni di schema del percorso shadow.

Sono deliberatamente distinte da quelle operative. `qualification_corpus/2.0` e
gli `EvidenceStatement` in `evidence_repository/1.0` restano quelli che sono: il
percorso shadow non ne cambia il fingerprint, e finche' `MIGRATION_STATUS` vale
`shadow_not_promoted` nessun consumatore operativo deve leggere da qui.
"""

from __future__ import annotations

MODEL_SCHEMA_VERSION = "qualified_claim_model/1.0"
SHADOW_REPOSITORY_VERSION = "qualified_claim_repository/1.0"
MIGRATION_STATUS = "shadow_not_promoted"

# Versioni operative che questa fase non tocca. Sono qui per essere asserite, non
# per essere usate: se una di queste cambiasse, la migrazione shadow avrebbe
# invaso il corpus operativo.
OPERATIONAL_CORPUS_VERSION = "qualification_corpus/2.0"
OPERATIONAL_REPOSITORY_VERSION = "evidence_repository/1.0"

PARENT_KIND = "graph_evidence_record"

CLAIM_TYPES = (
    "atomic_intervention_claim",
    "aggregate_intervention_claim",
    "regimen_claim",
)

ASSOCIATION_KINDS = (
    "unsupported_association",
    "unresolved_association",
)

# Gli oggetti che il repository shadow puo' contenere. Il parent e le due
# associazioni ci sono, ma nessuno dei tre e' un claim.
RETRIEVABLE_OBJECT_KINDS = (PARENT_KIND,) + CLAIM_TYPES + ASSOCIATION_KINDS

AGGREGATE_TYPES = (
    "intervention_class",
    "non_separable_intervention_set",
    "panel",
    "other",
)

# `aggregate_kind` come lo scrive l'adjudication, mappato sul vocabolario del
# modello. La mappa e' esplicita perche' un aggregato di classe e un insieme non
# separabile si comportano diversamente al gate.
AGGREGATE_KIND_TO_TYPE = {
    "drug_class": "intervention_class",
    "non_separable_set": "non_separable_intervention_set",
    "panel": "panel",
}

DIRECTIONS = ("sensitivity", "resistance", "reduced_sensitivity", "unknown")
POLARITIES = ("supports", "does_not_support", "conflicting", "unknown")

# Origine della migrazione, per distinguere i claim nati dalla revisione da
# quelli che portano avanti uno statement V2 senza nuove decisioni semantiche.
MIGRATION_ORIGIN_ADJUDICATED = "adjudicated_review"
MIGRATION_ORIGIN_LEGACY = "legacy_single_statement"

MIGRATION_ORIGINS = (MIGRATION_ORIGIN_ADJUDICATED, MIGRATION_ORIGIN_LEGACY)
