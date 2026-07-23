"""Revisione documentale delle fonti che mescolano clinico e preclinico.

L'audit strutturale ha classificato tre fonti `clinical_preclinical_split_required`
leggendo i **segnali** della fonte. Un segnale dice che la fonte contiene una
componente clinica e una preclinica; non dice quali statement appartengano
all'una e quali all'altra. Infatti l'audit ha lasciato tutti e sette gli statement
delle tre fonti in `candidate_ambiguous`.

Questo modulo porta il vocabolario della fase che scioglie quell'ambiguita'
leggendo le fonti primarie. Il tetto di cio' che puo' produrre e'
`source_checked_review_proposal`: una proposta verificata sulla fonte, non una
revisione. La differenza non e' formale — una proposta che si dichiarasse
revisione trasformerebbe l'estrazione automatica in gold, che e' esattamente la
circolarita' che il corpus esiste per evitare.

Il numero di unita' deve emergere dalla fonte. L'audit ne ha proposte due per
fonte per simmetria strutturale; la verifica documentale puo' confermarle,
correggerle, aumentarle o ridurle, e gli stati esistono per dirlo.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

REVIEW_VERSION = "clinical_preclinical_review/1.0"

# --- perimetro ----------------------------------------------------------------
# Le tre fonti che l'audit ha classificato clinical_preclinical_split_required.
# Dichiarate esplicitamente perche' il controllo possa confrontare l'insieme
# derivato con quello atteso invece di fidarsi di un conteggio.
TARGET_STRUCTURE_STATE = "clinical_preclinical_split_required"

EXPECTED_SOURCES = (
    "PU-PMID-22235099-cohort-1",
    "PU-PMID-23344087-cohort-1",
    "PU-PMID-31358542-cohort-1",
)


class ScopeMismatch(RuntimeError):
    """Il perimetro derivato non coincide con quello dichiarato."""


def derive_scope(classifications: Sequence[Mapping[str, Any]]) -> list[str]:
    """Le unita' del perimetro, derivate dal criterio e non dal conteggio."""
    return sorted(
        str(row["profile_unit_id"])
        for row in classifications
        if row.get("structure_state") == TARGET_STRUCTURE_STATE
    )


def check_scope(derived: Sequence[str]) -> None:
    """Fallisce su qualunque divergenza dall'insieme dichiarato."""
    derived_set = set(derived)
    expected_set = set(EXPECTED_SOURCES)
    missing = expected_set - derived_set
    extra = derived_set - expected_set
    if missing or extra:
        raise ScopeMismatch(
            f"perimetro divergente. Mancanti: {sorted(missing)}. In piu': {sorted(extra)}. "
            "Il perimetro segue la classificazione dell'audit: aggiornare EXPECTED_SOURCES "
            "solo dopo aver capito perche' l'insieme e' cambiato."
        )


# --- decisione strutturale (una sola per fonte) -------------------------------
AUDIT_SPLIT_CONFIRMED = "audit_split_confirmed"
AUDIT_SPLIT_CONFIRMED_MORE = "audit_split_confirmed_with_more_units"
AUDIT_SPLIT_CONFIRMED_FEWER = "audit_split_confirmed_with_fewer_units"
AUDIT_SPLIT_CORRECTED = "audit_split_corrected"
AUDIT_SPLIT_PARTIALLY_SUPPORTED = "audit_split_partially_supported"
AUDIT_SPLIT_NOT_SUPPORTED = "audit_split_not_supported"
INSUFFICIENT_SOURCE_INFORMATION = "insufficient_source_information"
REQUIRES_CLINICAL_REVIEW = "requires_clinical_review"

STRUCTURAL_DECISIONS = (
    AUDIT_SPLIT_CONFIRMED,
    AUDIT_SPLIT_CONFIRMED_MORE,
    AUDIT_SPLIT_CONFIRMED_FEWER,
    AUDIT_SPLIT_CORRECTED,
    AUDIT_SPLIT_PARTIALLY_SUPPORTED,
    AUDIT_SPLIT_NOT_SUPPORTED,
    INSUFFICIENT_SOURCE_INFORMATION,
    REQUIRES_CLINICAL_REVIEW,
)

# Decisioni che confermano lo split dell'audit, in una qualche misura. Servono
# alle metriche descrittive del detector: un confirmed_with_more_units resta una
# conferma del segnale, anche se corregge il numero di unita'.
CONFIRMING_DECISIONS = (
    AUDIT_SPLIT_CONFIRMED,
    AUDIT_SPLIT_CONFIRMED_MORE,
    AUDIT_SPLIT_CONFIRMED_FEWER,
    AUDIT_SPLIT_CORRECTED,
)

# --- tipi di supporto dello statement -----------------------------------------
DIRECT_CLINICAL_SUPPORT = "direct_clinical_support"
DIRECT_PRECLINICAL_SUPPORT = "direct_preclinical_support"
CLINICAL_WITH_PRECLINICAL_VALIDATION = "clinical_observation_with_preclinical_validation"
CLINICAL_CONTEXT_ONLY = "clinical_context_only"
PRECLINICAL_CONTEXT_ONLY = "preclinical_context_only"
INDIRECT_SUPPORT = "indirect_support"
NOT_DETERMINABLE = "not_determinable"
UNSUPPORTED_BY_ACCESSIBLE_SOURCE = "unsupported_by_accessible_source"

SUPPORT_TYPES = (
    DIRECT_CLINICAL_SUPPORT,
    DIRECT_PRECLINICAL_SUPPORT,
    CLINICAL_WITH_PRECLINICAL_VALIDATION,
    CLINICAL_CONTEXT_ONLY,
    PRECLINICAL_CONTEXT_ONLY,
    INDIRECT_SUPPORT,
    NOT_DETERMINABLE,
    UNSUPPORTED_BY_ACCESSIBLE_SOURCE,
)

CANDIDATE_VALID = "candidate_valid"
CANDIDATE_PARTIAL = "candidate_partial"
CANDIDATE_AMBIGUOUS = "candidate_ambiguous"
CANDIDATE_CONFLICTING = "candidate_conflicting"
CANDIDATE_INVALID = "candidate_invalid"
CANDIDATE_NOT_DETERMINABLE = "candidate_not_determinable"

CANDIDATE_LINK_STATES = (
    CANDIDATE_VALID,
    CANDIDATE_PARTIAL,
    CANDIDATE_AMBIGUOUS,
    CANDIDATE_CONFLICTING,
    CANDIDATE_INVALID,
    CANDIDATE_NOT_DETERMINABLE,
)

# --- normalizzazione terminologica --------------------------------------------
MAPPING_EXACT = "exact"
MAPPING_VERIFIED_SYNONYM = "verified_synonym"
MAPPING_VERIFIED_DEVELOPMENT_CODE = "verified_development_code"
MAPPING_REQUIRES_VERIFICATION = "requires_terminology_verification"
MAPPING_AMBIGUOUS = "ambiguous_mapping"
MAPPING_REJECTED = "mapping_rejected"

TERMINOLOGY_STATES = (
    MAPPING_EXACT,
    MAPPING_VERIFIED_SYNONYM,
    MAPPING_VERIFIED_DEVELOPMENT_CODE,
    MAPPING_REQUIRES_VERIFICATION,
    MAPPING_AMBIGUOUS,
    MAPPING_REJECTED,
)

# --- locator ------------------------------------------------------------------
MATCH_EXACT = "exact"
MATCH_INLINE_REFERENCE = "inline_reference"
MATCH_INTERPOLATED = "interpolated"
MATCH_NORMALIZED_LABEL = "normalized_label"
MATCH_SECTION_LEVEL = "section_level"
MATCH_TABLE_LEVEL = "table_level"
MATCH_FIGURE_LEVEL = "figure_level"
MATCH_NOT_VERIFIED = "not_verified"

LOCATOR_MATCH_TYPES = (
    MATCH_EXACT,
    MATCH_INLINE_REFERENCE,
    MATCH_INTERPOLATED,
    MATCH_NORMALIZED_LABEL,
    MATCH_SECTION_LEVEL,
    MATCH_TABLE_LEVEL,
    MATCH_FIGURE_LEVEL,
    MATCH_NOT_VERIFIED,
)

# Match che valgono come verifica sulla fonte. `not_verified` ovviamente no; i
# livelli di sezione, tabella e figura si': dicono dove sta il reperto anche
# quando la stringa esatta non e' riproducibile.
VERIFIED_MATCH_TYPES = frozenset(
    {
        MATCH_EXACT,
        MATCH_INLINE_REFERENCE,
        MATCH_INTERPOLATED,
        MATCH_NORMALIZED_LABEL,
        MATCH_SECTION_LEVEL,
        MATCH_TABLE_LEVEL,
        MATCH_FIGURE_LEVEL,
    }
)

# --- stati della proposta -----------------------------------------------------
# Il tetto della fase. Separato dagli stati di revisione umana: nessun percorso
# automatico deve poter promuovere una proposta a revisione.
SOURCE_CHECKED_REVIEW_PROPOSAL = "source_checked_review_proposal"
SPLIT_REVIEW_PROPOSED = "split_review_proposed"

# --- packet di approvazione ---------------------------------------------------
APPROVE = "approve"
APPROVE_WITH_CORRECTIONS = "approve_with_corrections"
REJECT = "reject"
DEFER_TO_CLINICAL_REVIEWER = "defer_to_clinical_reviewer"
INSUFFICIENT_INFORMATION = "insufficient_information"

AUTHOR_DECISIONS = (
    APPROVE,
    APPROVE_WITH_CORRECTIONS,
    REJECT,
    DEFER_TO_CLINICAL_REVIEWER,
    INSUFFICIENT_INFORMATION,
)

FIELD_DECISIONS = (
    "confirmed",
    "corrected",
    "unknown",
    "not_applicable",
    "not_separable",
    "requires_clinical_review",
)

_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Testo confrontabile: spazi collassati, minuscolo."""
    return _WHITESPACE.sub(" ", str(text or "")).strip().casefold()


def span_hash(text: str) -> str:
    """Impronta di uno span citato.

    Permette di dimostrare che un estratto viene davvero dal documento di cui si
    dichiara l'hash, senza conservare il documento.
    """
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LocatorCheck:
    """Esito della ricerca di un locator nel documento.

    `max_gap` e' registrato perche' un match interpolato con distanza grande e un
    match esatto non sono la stessa prova, e chi rilegge deve poterli distinguere
    senza rieseguire la ricerca.
    """

    locator_id: str
    query: str
    match_type: str
    verified: bool
    char_offset: int | None = None
    max_gap: int = 0
    section_label: str = ""
    span_hash: str = ""
    excerpt: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "locator_id": self.locator_id,
            "query": self.query,
            "match_type": self.match_type,
            "verified": self.verified,
            "char_offset": self.char_offset,
            "max_gap": self.max_gap,
            "section_label": self.section_label,
            "span_hash": self.span_hash,
            "excerpt": self.excerpt,
            "note": self.note,
        }


def validate_proposal_states(record: Mapping[str, Any]) -> list[str]:
    """Gli stati che una proposta di questa fase non puo' superare.

    Restituisce i problemi trovati invece di sollevare: chi chiama vuole
    l'elenco completo, non il primo errore.
    """
    problems: list[str] = []
    if record.get("review_status") != SOURCE_CHECKED_REVIEW_PROPOSAL:
        problems.append(
            f"review_status deve essere {SOURCE_CHECKED_REVIEW_PROPOSAL}, "
            f"trovato {record.get('review_status')!r}"
        )
    for flag in ("human_reviewed", "first_review_complete", "is_evaluable", "is_propagatable"):
        if record.get(flag) is not False:
            problems.append(f"{flag} deve essere false, trovato {record.get(flag)!r}")
    for flag in ("requires_author_approval", "requires_second_independent_review"):
        if record.get(flag) is not True:
            problems.append(f"{flag} deve essere true, trovato {record.get(flag)!r}")
    return problems
