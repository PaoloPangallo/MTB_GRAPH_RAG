"""Contratto di ingresso del retriever qualificato.

La query porta due tipi di campo che non vanno confusi.

I **vincoli nativi** — malattia, biomarcatore, intervento, direzione, polarita',
scope — descrivono proprieta' che vengono dal grafo congelato. Possono generare i
candidati e possono escluderli, perche' escludere su di essi non e' una
scommessa: sono gli stessi campi su cui il retrieval V2 gia' filtra.

Il **contesto clinico** — stadio, setting, linea di terapia, terapie precedenti,
popolazione, stato di resezione — descrive il paziente. Sulla fonte, gli stessi
campi arrivano da una revisione che nessuno ha confermato in modo indipendente,
e per questo qui possono soltanto spostare un punteggio o accendere un warning.
Usarli per escludere significherebbe far sparire una evidenza sulla base di un
valore che una sola persona ha letto una volta sola.

Il modello del caso pilota (`mtb_evidence_gold_pilot_v1.jsonl`) ha gia' gene,
variante, malattia e contesto richiesto: `from_pilot_case` lo converte invece di
introdurre un secondo modello che possa divergere dal primo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ._normalize import normalize_drug, normalize_text
from .qualified_retrieval_errors import (
    InvalidQueryError,
    UnknownRetrievalModeError,
)

QUERY_VERSION = "qualified_retrieval_query/1.0"

# --- modalita' ----------------------------------------------------------------
MODE_V2_COMPATIBILITY = "v2_compatibility"
MODE_NATIVE_ONLY = "native_only"
MODE_QUALIFIED_SOFT = "qualified_soft"
MODE_AUDIT_ALL = "audit_all"

RETRIEVAL_MODES = (
    MODE_V2_COMPATIBILITY,
    MODE_NATIVE_ONLY,
    MODE_QUALIFIED_SOFT,
    MODE_AUDIT_ALL,
)

# Le modalita' in cui i qualificatori source-derived toccano il punteggio. Le
# altre due esistono per misurare la differenza: se `native_only` e
# `qualified_soft` dessero lo stesso ranking, i qualificatori non starebbero
# contribuendo nulla, e sarebbe un risultato da sapere.
QUALIFIER_AWARE_MODES = (MODE_QUALIFIED_SOFT, MODE_AUDIT_ALL)

# --- granularita' del match biomarcatore -------------------------------------
# Non sono fallback. La modalita' deriva dai campi richiesti: appena la query
# porta una alterazione, il confronto deve soddisfare gene E alterazione.
BIOMARKER_MATCH_GENE_LEVEL = "gene_level"
BIOMARKER_MATCH_ALTERATION_SPECIFIC = "alteration_specific"
BIOMARKER_MATCH_MODES = (
    BIOMARKER_MATCH_GENE_LEVEL,
    BIOMARKER_MATCH_ALTERATION_SPECIFIC,
)

# --- direzioni e polarita' ----------------------------------------------------
DIRECTION_SENSITIVITY = "sensitivity"
DIRECTION_RESISTANCE = "resistance"
DIRECTION_DIAGNOSTIC = "diagnostic"
DIRECTION_PROGNOSTIC = "prognostic"

DIRECTIONS = (
    DIRECTION_SENSITIVITY,
    DIRECTION_RESISTANCE,
    DIRECTION_DIAGNOSTIC,
    DIRECTION_PROGNOSTIC,
)

POLARITY_SUPPORTS = "supports"
POLARITY_DOES_NOT_SUPPORT = "does_not_support"
POLARITIES = (POLARITY_SUPPORTS, POLARITY_DOES_NOT_SUPPORT)

# --- contesto dell'evidenza ---------------------------------------------------
CONTEXT_CLINICAL = "clinical"
CONTEXT_PRECLINICAL = "preclinical"
CONTEXT_BOTH = "both"
EVIDENCE_CONTEXTS = (CONTEXT_CLINICAL, CONTEXT_PRECLINICAL, CONTEXT_BOTH)

# Contesto clinico della query: influenza punteggio e warning, mai l'esclusione.
CLINICAL_CONTEXT_FIELDS = (
    "stage",
    "setting",
    "therapy_line",
    "prior_therapies",
    "population",
    "resection_status",
)

DEFAULT_TOP_K = 20
MAX_TOP_K = 500


@dataclass(frozen=True)
class QueryBiomarker:
    """Un biomarcatore della query, nelle forme in cui puo' essere confrontato."""

    gene: str = ""
    alteration: str = ""
    normalized: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.gene or self.alteration or self.normalized)

    def match_keys(self) -> tuple[str, ...]:
        """Le chiavi con cui cercare, dalla piu' specifica alla piu' larga."""
        keys = [
            normalize_text(self.normalized),
            normalize_text(self.alteration),
            normalize_text(self.gene),
        ]
        return tuple(key for key in keys if key)

    @property
    def has_alteration_constraint(self) -> bool:
        """True quando la query richiede piu' del solo gene."""
        if normalize_text(self.alteration):
            return True
        normalized = normalize_text(self.normalized)
        return bool(normalized and normalized != normalize_text(self.gene))

    def as_dict(self) -> dict[str, Any]:
        return {
            "gene": self.gene,
            "alteration": self.alteration,
            "normalized": self.normalized,
        }


@dataclass(frozen=True)
class QualifiedRetrievalQuery:
    """Che cosa si sta cercando, e con quale autorita' si puo' escludere."""

    query_id: str
    biomarkers: tuple[QueryBiomarker, ...] = ()
    disease: str = ""
    disease_aliases: tuple[str, ...] = ()
    case_id: str = ""
    interventions: tuple[str, ...] = ()
    directions: tuple[str, ...] = ()
    assertion_polarities: tuple[str, ...] = ()
    evidence_scopes: tuple[str, ...] = ()
    preferred_evidence_context: str = CONTEXT_BOTH
    clinical_context: Mapping[str, Any] = field(default_factory=dict)
    top_k: int = DEFAULT_TOP_K
    mode: str = MODE_QUALIFIED_SOFT
    corpus_fingerprint: str = ""

    # -- interrogazione --------------------------------------------------------

    @property
    def uses_qualifiers(self) -> bool:
        return self.mode in QUALIFIER_AWARE_MODES

    @property
    def normalized_disease(self) -> str:
        return normalize_text(self.disease)

    def disease_keys(self) -> tuple[str, ...]:
        keys = [normalize_text(self.disease)]
        keys.extend(normalize_text(alias) for alias in self.disease_aliases)
        return tuple(sorted({key for key in keys if key}))

    def intervention_keys(self) -> tuple[str, ...]:
        return tuple(
            sorted({normalize_drug(item) for item in self.interventions if normalize_drug(item)})
        )

    def biomarker_keys(self) -> tuple[str, ...]:
        return tuple(
            sorted({key for marker in self.biomarkers for key in marker.match_keys()})
        )

    @property
    def biomarker_match_mode(self) -> str:
        """Granularita'' nativa, senza fallback automatico."""
        if any(marker.has_alteration_constraint for marker in self.biomarkers):
            return BIOMARKER_MATCH_ALTERATION_SPECIFIC
        return BIOMARKER_MATCH_GENE_LEVEL

    def clinical_context_value(self, dimension: str) -> Any:
        return self.clinical_context.get(dimension)

    def as_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "case_id": self.case_id,
            "query_version": QUERY_VERSION,
            "disease": self.disease,
            "disease_aliases": list(self.disease_aliases),
            "biomarkers": [marker.as_dict() for marker in self.biomarkers],
            "interventions": list(self.interventions),
            "directions": list(self.directions),
            "assertion_polarities": list(self.assertion_polarities),
            "evidence_scopes": list(self.evidence_scopes),
            "preferred_evidence_context": self.preferred_evidence_context,
            "clinical_context": dict(self.clinical_context),
            "top_k": self.top_k,
            "mode": self.mode,
            "corpus_fingerprint": self.corpus_fingerprint,
        }


def validate_query(query: QualifiedRetrievalQuery) -> list[str]:
    """Tutti i problemi della query, non solo il primo.

    Restituirli insieme evita il ciclo «correggi, riprova, scopri il prossimo»,
    che su una query con quattro campi sbagliati costa quattro esecuzioni.
    """
    problems: list[str] = []

    if not str(query.query_id or "").strip():
        problems.append("query_id mancante: il risultato non sarebbe tracciabile")

    markers = [marker for marker in query.biomarkers if not marker.is_empty]
    if not markers:
        problems.append(
            "nessun biomarcatore: la generazione dei candidati parte dal "
            "biomarcatore e senza di esso restituirebbe l'intero repository"
        )
    if not str(query.disease or "").strip():
        problems.append(
            "disease mancante: e' un vincolo nativo e senza di essa non e' "
            "possibile distinguere un match dalla sua assenza"
        )

    for marker in markers:
        if not marker.match_keys():
            problems.append(
                f"biomarcatore non normalizzabile: {marker.as_dict()!r}"
            )

    for direction in query.directions:
        if normalize_text(direction) not in DIRECTIONS:
            problems.append(f"direzione non ammessa: {direction!r}")
    for polarity in query.assertion_polarities:
        if normalize_text(polarity) not in POLARITIES:
            problems.append(f"assertion polarity non ammessa: {polarity!r}")
    if query.preferred_evidence_context not in EVIDENCE_CONTEXTS:
        problems.append(
            f"preferred_evidence_context non ammesso: {query.preferred_evidence_context!r}"
        )

    unknown_context = sorted(set(query.clinical_context) - set(CLINICAL_CONTEXT_FIELDS))
    if unknown_context:
        problems.append(f"campi di contesto clinico non riconosciuti: {unknown_context}")

    if not isinstance(query.top_k, int) or isinstance(query.top_k, bool):
        problems.append(f"top_k non e' un intero: {query.top_k!r}")
    elif query.top_k < 1 or query.top_k > MAX_TOP_K:
        problems.append(f"top_k fuori intervallo [1, {MAX_TOP_K}]: {query.top_k}")

    if query.mode not in RETRIEVAL_MODES:
        problems.append(
            f"modalita' sconosciuta: {query.mode!r}. Ammesse: {list(RETRIEVAL_MODES)}"
        )

    return problems


def require_valid(query: QualifiedRetrievalQuery) -> QualifiedRetrievalQuery:
    """La query, oppure un errore che elenca tutto cio' che non va."""
    if query.mode not in RETRIEVAL_MODES:
        raise UnknownRetrievalModeError(
            f"modalita' sconosciuta: {query.mode!r}. Ammesse: {list(RETRIEVAL_MODES)}"
        )
    problems = validate_query(query)
    if problems:
        raise InvalidQueryError("; ".join(problems))
    return query


def build_query(payload: Mapping[str, Any]) -> QualifiedRetrievalQuery:
    """Costruisce una query da un dizionario, senza inventare valori."""
    markers = tuple(
        QueryBiomarker(
            gene=str(item.get("gene") or ""),
            alteration=str(item.get("alteration") or ""),
            normalized=str(item.get("normalized") or ""),
        )
        for item in payload.get("biomarkers") or []
    )
    return QualifiedRetrievalQuery(
        query_id=str(payload.get("query_id") or ""),
        case_id=str(payload.get("case_id") or ""),
        biomarkers=markers,
        disease=str(payload.get("disease") or ""),
        disease_aliases=tuple(payload.get("disease_aliases") or ()),
        interventions=tuple(payload.get("interventions") or ()),
        directions=tuple(payload.get("directions") or ()),
        assertion_polarities=tuple(payload.get("assertion_polarities") or ()),
        evidence_scopes=tuple(payload.get("evidence_scopes") or ()),
        preferred_evidence_context=str(
            payload.get("preferred_evidence_context") or CONTEXT_BOTH
        ),
        clinical_context=dict(payload.get("clinical_context") or {}),
        top_k=int(payload.get("top_k", DEFAULT_TOP_K)),
        mode=str(payload.get("mode") or MODE_QUALIFIED_SOFT),
        corpus_fingerprint=str(payload.get("corpus_fingerprint") or ""),
    )


def from_pilot_case(
    case: Mapping[str, Any],
    *,
    mode: str = MODE_QUALIFIED_SOFT,
    top_k: int = DEFAULT_TOP_K,
    corpus_fingerprint: str = "",
) -> QualifiedRetrievalQuery:
    """Converte un caso del pilota congelato in una query.

    Il caso pilota e' gia' un modello strutturato e revisionato: gene, variante,
    malattia e contesto richiesto ci sono. Introdurre un secondo modello
    significherebbe avere due definizioni dello stesso caso che possono
    divergere senza che nulla lo segnali.

    `required_context` resta una stringa: e' prosa scritta per un lettore umano, e
    trasformarla in campi strutturati richiederebbe di interpretarla. Viaggia come
    contesto dichiarato e produce warning, mai esclusioni.
    """
    gene = str(case.get("gene") or "")
    variant = str(case.get("variant") or "")
    marker = QueryBiomarker(
        gene=gene,
        alteration=variant,
        normalized=f"{gene} {variant}".strip() if gene and variant else gene or variant,
    )
    context: dict[str, Any] = {}
    required = str(case.get("required_context") or "").strip()
    if required:
        context["setting"] = required
    return QualifiedRetrievalQuery(
        query_id=f"Q-{case.get('case_id')}",
        case_id=str(case.get("case_id") or ""),
        biomarkers=(marker,),
        disease=str(case.get("disease") or ""),
        clinical_context=context,
        preferred_evidence_context=CONTEXT_BOTH,
        top_k=top_k,
        mode=mode,
        corpus_fingerprint=corpus_fingerprint,
    )


__all__ = [
    "QUERY_VERSION",
    "MODE_V2_COMPATIBILITY",
    "MODE_NATIVE_ONLY",
    "MODE_QUALIFIED_SOFT",
    "MODE_AUDIT_ALL",
    "RETRIEVAL_MODES",
    "QUALIFIER_AWARE_MODES",
    "BIOMARKER_MATCH_GENE_LEVEL",
    "BIOMARKER_MATCH_ALTERATION_SPECIFIC",
    "BIOMARKER_MATCH_MODES",
    "DIRECTIONS",
    "POLARITIES",
    "EVIDENCE_CONTEXTS",
    "CONTEXT_CLINICAL",
    "CONTEXT_PRECLINICAL",
    "CONTEXT_BOTH",
    "CLINICAL_CONTEXT_FIELDS",
    "DEFAULT_TOP_K",
    "MAX_TOP_K",
    "QueryBiomarker",
    "QualifiedRetrievalQuery",
    "validate_query",
    "require_valid",
    "build_query",
    "from_pilot_case",
]
