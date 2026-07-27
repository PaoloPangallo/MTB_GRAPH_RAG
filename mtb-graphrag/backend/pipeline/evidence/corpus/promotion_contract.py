"""Contratto della promozione prototipale: cosa viene scritto, dove, e con quali valori.

Un solo modulo dichiara i nomi dei file, i conteggi attesi e i valori che il
registro deve portare. Gli altri moduli della promozione — generazione,
scrittura atomica, loader, rollback — li leggono da qui invece di ripeterli, in
modo che un disallineamento fra il corpus scritto e il corpus riletto sia
impossibile per costruzione e non soltanto improbabile.

Due valori meritano di essere spiegati invece che soltanto letti.

`PROMOTED_AT` e' una data di fase e non un orologio. Una promozione che
timbrasse `datetime.now()` produrrebbe un artefatto diverso a ogni esecuzione, e
il test di determinismo — che e' l'unico modo di dimostrare che il corpus deriva
dalla 1.4 e non dall'ambiente — non potrebbe esistere.

`PROMOTION_COMMIT` nomina l'endpoint di contenuto da cui il corpus e' derivato,
non il commit che lo contiene: un commit non puo' contenere il proprio hash. Il
campo dice "questo corpus e' funzione di quell'albero", che e' l'informazione
verificabile.
"""

from __future__ import annotations

from pathlib import Path

# --- versioni -----------------------------------------------------------------

REPOSITORY_VERSION = "qualified_claim_repository/1.4"
MODEL_VERSION = "qualified_claim_model/1.2"
SCHEMA_VERSION = "promoted_corpus_schema/1.0"
REGISTRY_VERSION = "prototype_corpus_registry/1.0"

SOURCE_SHADOW_VERSION = "qualified_claim_repository/1.4"
SOURCE_SHADOW_DIRNAME = "pre_promotion_required_fixes_1_4"
SOURCE_SHADOW_BASE_DIRNAME = "integrated_shadow_repository_1_3"

PHASE = "prototype-corpus-promotion/1.4"
PROMOTED_AT = "2026-07-27T00:00:00Z"
PROMOTION_COMMIT = "78647dd9566679df458bfc561b7e6412d01ae64c"

# --- stato ---------------------------------------------------------------------

PROMOTION_STATUS = "prototype_promoted"
PROTOTYPE_PROMOTED = True

# Il retriever operativo non e' collegato, e il campo non e' una nota: e' cio'
# che il loader e il rollback verificano. Un corpus promosso per il prototipo e
# un corpus in uso sono due stati diversi, e il registro deve poterli distinguere
# senza interpretare.
OPERATIONAL_RETRIEVER_BOUND = False
CLINICAL_READINESS = False
FINAL_EVALUABLE = False

# --- politica ------------------------------------------------------------------

DEFAULT_POLICY_MODE = "strict_verified"
ALLOWED_POLICY_MODES = ("strict_verified", "ontology_aware_warning", "audit_all")
UNKNOWN_POLICY_MODE_BEHAVIOR = "reject"

PROPAGATION_POLICY = "prototype_only"

# --- percorsi ------------------------------------------------------------------

PACKAGE_ROOT = Path(__file__).resolve().parent
PROMOTED_NAMESPACE = PACKAGE_ROOT / "v3"
CORPUS_DIRNAME = "qualified_claim_repository_1_4"
PROMOTED_CORPUS = PROMOTED_NAMESPACE / CORPUS_DIRNAME
REGISTRY_PATH = PROMOTED_NAMESPACE / "prototype_corpus_registry.json"

REPO_ROOT = PACKAGE_ROOT.parents[3]

# Percorso dichiarato in forma relativa, perche' gli artefatti possano citarlo
# senza incollare un path assoluto della macchina che li ha generati.
PROMOTED_CORPUS_RELPATH = (
    "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4"
)
REGISTRY_RELPATH = "backend/pipeline/evidence/corpus/v3/prototype_corpus_registry.json"

# --- contenuto -----------------------------------------------------------------

CLAIM_FILES = (
    "evidence_claims.jsonl",
    "therapeutic_claims.jsonl",
    "diagnostic_claims.jsonl",
    "prognostic_claims.jsonl",
)

CORPUS_FILES = (
    "graph_evidence_parents.jsonl",
    "evidence_claims.jsonl",
    "therapeutic_claims.jsonl",
    "diagnostic_claims.jsonl",
    "prognostic_claims.jsonl",
    "deprecated_claims.jsonl",
    "unsupported_associations.jsonl",
    "unresolved_associations.jsonl",
    "claim_replacement_lineage.jsonl",
    "terminology_registry.json",
    "disease_relation_registry.json",
    "formulation_registry.jsonl",
    "qualification_links.jsonl",
    "qualified_evidence_views.jsonl",
    "corpus_manifest.json",
    "corpus_registry_entry.json",
    "promotion_log.json",
    "rollback_metadata.json",
)

MANIFEST_FILE = "corpus_manifest.json"

# Il manifest non puo' contenere il proprio hash, e nemmeno quello dei due
# artefatti che lo citano. I tre restano fuori dall'elenco degli hash e sono
# verificati per contenuto invece che per digest.
UNHASHED_FILES = ("corpus_manifest.json", "promotion_log.json", "rollback_metadata.json")

# --- conteggi attesi ------------------------------------------------------------

EXPECTED_COUNTS = {
    "active_claims_total": 148,
    "aggregate_claims": 3,
    "atomic_claims": 140,
    "deduplications": 0,
    "deprecated_claims": 4,
    "diagnostic_claims": 2,
    "id_collisions": 0,
    "orphan_claims": 0,
    "parents": 147,
    "parents_without_claims": 3,
    "prognostic_claims": 0,
    "regimen_claims": 3,
    "therapeutic_claims": 146,
    "unresolved_associations": 6,
    "unsupported_associations": 6,
}

EXPECTED_LINK_ACTIONS = 37
EXPECTED_VIEW_ACTIONS = 4

# --- lineage da verificare esplicitamente ---------------------------------------

# Gli otto endpoint che la fase precedente ha nominato uno per uno. Sono i casi
# in cui il lookup puo' sbagliare in modo silenzioso: due sostituzioni
# diagnostiche, due canonicalizzazioni terminologiche, tre parent senza claim e
# un parent con due claim attivi.
LINEAGE_PROBE_IDS = (
    "evidence:347",
    "evidence:1846",
    "evidence:1847",
    "evidence:1851",
    "evidence:1853",
    "evidence:3811",
    "evidence:4759",
    "evidence:11240",
)

# --- terminologia congelata ------------------------------------------------------

VERIFIED_TERMINOLOGY_DECISION = "TP-BGJ398-INFIGRATINIB"
UNRESOLVED_TERMINOLOGY_DECISION = "TP-AUY922-LUMINESPIB"
UNRESOLVED_SOURCE_LITERAL = "AUY922"


class PromotionContractError(RuntimeError):
    """La promozione ha prodotto uno stato che il contratto non ammette."""


def registry_entry_fields() -> tuple[str, ...]:
    """I campi obbligatori della voce di registro, in ordine di lettura."""
    return (
        "repository_version",
        "model_version",
        "schema_version",
        "promotion_status",
        "prototype_promoted",
        "operational_retriever_bound",
        "default_policy_mode",
        "allowed_policy_modes",
        "unknown_policy_mode_behavior",
        "source_shadow_version",
        "source_shadow_sha256",
        "promoted_at",
        "promotion_commit",
        "rollback_target",
        "clinical_readiness",
        "final_evaluable",
    )


def validate_policy_mode(mode: str | None) -> str:
    """La modalita' dichiarata, oppure un errore. Mai un allargamento.

    Una modalita' assente si risolve nella default; una modalita' sconosciuta
    viene rifiutata. Le due cose non sono lo stesso caso, ed e' per questo che
    non condividono un ramo: un fallback silenzioso trasformerebbe un errore di
    configurazione in una query piu' permissiva di quella chiesta.
    """
    if mode is None:
        return DEFAULT_POLICY_MODE
    if mode not in ALLOWED_POLICY_MODES:
        raise PromotionContractError(
            f"UNKNOWN_POLICY_MODE — {mode!r} non e' fra {list(ALLOWED_POLICY_MODES)}; "
            f"il comportamento dichiarato e' {UNKNOWN_POLICY_MODE_BEHAVIOR!r}"
        )
    return mode


__all__ = [
    "ALLOWED_POLICY_MODES",
    "CLAIM_FILES",
    "CLINICAL_READINESS",
    "CORPUS_DIRNAME",
    "CORPUS_FILES",
    "DEFAULT_POLICY_MODE",
    "EXPECTED_COUNTS",
    "EXPECTED_LINK_ACTIONS",
    "EXPECTED_VIEW_ACTIONS",
    "FINAL_EVALUABLE",
    "LINEAGE_PROBE_IDS",
    "MANIFEST_FILE",
    "MODEL_VERSION",
    "OPERATIONAL_RETRIEVER_BOUND",
    "PACKAGE_ROOT",
    "PHASE",
    "PROMOTED_AT",
    "PROMOTED_CORPUS",
    "PROMOTED_CORPUS_RELPATH",
    "PROMOTED_NAMESPACE",
    "PROMOTION_COMMIT",
    "PROMOTION_STATUS",
    "PROPAGATION_POLICY",
    "PROTOTYPE_PROMOTED",
    "REGISTRY_PATH",
    "REGISTRY_RELPATH",
    "REGISTRY_VERSION",
    "REPOSITORY_VERSION",
    "REPO_ROOT",
    "SCHEMA_VERSION",
    "SOURCE_SHADOW_BASE_DIRNAME",
    "SOURCE_SHADOW_DIRNAME",
    "SOURCE_SHADOW_VERSION",
    "UNHASHED_FILES",
    "UNKNOWN_POLICY_MODE_BEHAVIOR",
    "UNRESOLVED_SOURCE_LITERAL",
    "UNRESOLVED_TERMINOLOGY_DECISION",
    "VERIFIED_TERMINOLOGY_DECISION",
    "PromotionContractError",
    "registry_entry_fields",
    "validate_policy_mode",
]
