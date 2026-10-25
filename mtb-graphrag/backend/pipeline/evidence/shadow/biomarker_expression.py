"""Semantica booleana delle espressioni di biomarcatore.

Il gate 1.0 confronta il biomarcatore della query con quello del claim per
uguaglianza di stringa normalizzata. Su un corpus in cui 64 claim su 148 portano
un'espressione booleana — `EGFR L858R OR EGFR Exon 19 Deletion`,
`EML4::ALK Fusion AND ALK C1156Y` — quel confronto non distingue la congiunzione
dalla disgiunzione: le tratta come due stringhe opache, identiche nel modo in cui
falliscono. Un claim disgiuntivo che *contiene* il letterale chiesto viene
respinto per la stessa ragione per cui viene respinto un claim congiuntivo di cui
la query soddisfa un solo membro, e le due ragioni non sono la stessa ragione.

Questo modulo dà all'asse un vocabolario. Tre scelte meritano di essere lette
come scelte.

**L'identita' di un'espressione e' la coppia (operatore, insieme di termini), mai
la stringa.** `A OR B` e `B OR A` sono la stessa domanda scritta in due ordini, e
`A OR B OR A` non e' una domanda diversa da `A OR B`. Normalizzazione,
deduplicazione e ordinamento vengono prima di ogni confronto, e il confronto e'
fra insiemi. Un'espressione che dopo la deduplicazione ha un termine solo *e'* un
termine solo, qualunque operatore la legasse.

**Il confronto fra termini resta uguaglianza esatta.** Nessun wildcard, nessuna
somiglianza, nessuna normalizzazione semantica dei partner di fusione. E' cio'
che tiene `FGFR2::v Fusion` e `FGFR2::? Fusion` — dove `v` e `?` sono i segnaposto
che la fonte usa per un partner non identificato — lontani da
`FGFR2::BICC1 Fusion`. Trattare quei segnaposto come jolly farebbe corrispondere
una fusione nota a una fusione ignota, che e' esattamente l'affermazione che la
fonte si e' astenuta dal fare.

**Cio' che il parser non sa leggere finisce in audit, non fra i respinti.**
Un'espressione mista (`A AND B OR C`), annidata o con parentesi non e' un
mismatch: e' una domanda a cui questo modulo non risponde. Dichiararla
`incompatible` significherebbe affermare che il claim non c'entra, che e'
un'affermazione; `unresolved_boolean_expression` dice che la relazione non e'
stata decisa, e la lascia recuperabile in audit. Il corpus promosso non ne
contiene nessuna — il ramo esiste per non essere sorpreso dalla prima che
arrivera'.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

CONTRACT_VERSION = "biomarker-boolean-semantics/1.0"

# --- operatori ----------------------------------------------------------------

OP_EMPTY = "empty"
OP_SINGLE = "single"
OP_OR = "or"
OP_AND = "and"
OP_UNRESOLVED = "unresolved"

OPERATORS = (OP_EMPTY, OP_SINGLE, OP_OR, OP_AND, OP_UNRESOLVED)

# --- match type ---------------------------------------------------------------

MATCH_NOT_CONSTRAINED = "not_constrained"
MATCH_EXACT = "exact"
MATCH_EXACT_BOOLEAN_SET = "exact_boolean_set"
MATCH_DISJUNCT_MEMBER = "disjunct_member"
MATCH_CONJUNCTION_SATISFIED = "conjunction_satisfied"
MATCH_CONJUNCTION_PARTIAL = "conjunction_partially_satisfied"
MATCH_UNRESOLVED = "unresolved_boolean_expression"
MATCH_INCOMPATIBLE = "incompatible"

MATCH_TYPES = (
    MATCH_NOT_CONSTRAINED,
    MATCH_EXACT,
    MATCH_EXACT_BOOLEAN_SET,
    MATCH_DISJUNCT_MEMBER,
    MATCH_CONJUNCTION_SATISFIED,
    MATCH_CONJUNCTION_PARTIAL,
    MATCH_UNRESOLVED,
    MATCH_INCOMPATIBLE,
)

# I match type che consentono al claim di restare candidato primario sull'asse.
COMPATIBLE_MATCH_TYPES = frozenset(
    {
        MATCH_NOT_CONSTRAINED,
        MATCH_EXACT,
        MATCH_EXACT_BOOLEAN_SET,
        MATCH_DISJUNCT_MEMBER,
        MATCH_CONJUNCTION_SATISFIED,
    }
)

# I match type in cui la query raggiunge il claim per una relazione booleana e non
# per il letterale: il gate 1.1 va interrogato con l'espressione del claim, non
# con quella della query, altrimenti risponderebbe alla domanda sbagliata.
#
# `exact_boolean_set` e' in questo insieme e non fra le identita' letterali, ed e'
# una distinzione che costa un bug se la si sbaglia: `A AND B` e `B AND A` sono
# la stessa espressione per questo modulo ma due stringhe diverse per il gate
# 1.1, e dichiarare la coppia compatibile senza sostituire lascerebbe il gate a
# valle a respingerla sull'ordine delle parole. La compatibilita' dichiarata
# dev'essere anche la compatibilita' esercitata.
SUBSTITUTING_MATCH_TYPES = frozenset(
    {
        MATCH_EXACT_BOOLEAN_SET,
        MATCH_DISJUNCT_MEMBER,
        MATCH_CONJUNCTION_SATISFIED,
    }
)

# --- reason code --------------------------------------------------------------

BIOMARKER_NOT_CONSTRAINED = "BIOMARKER_NOT_CONSTRAINED"
BIOMARKER_EXACT_LITERAL = "BIOMARKER_EXACT_LITERAL_MATCH"
BIOMARKER_EXACT_SET = "BIOMARKER_EXACT_BOOLEAN_SET_MATCH"
BIOMARKER_DISJUNCT_MEMBER = "BIOMARKER_QUERY_SATISFIES_ONE_DISJUNCT"
BIOMARKER_CONJUNCTION_SATISFIED = "BIOMARKER_QUERY_SATISFIES_EVERY_CONJUNCT"
BIOMARKER_CONJUNCTION_PARTIAL = "BIOMARKER_CONJUNCTION_ONLY_PARTIALLY_SATISFIED"
BIOMARKER_EXPRESSION_UNRESOLVED = "BIOMARKER_BOOLEAN_EXPRESSION_NOT_INTERPRETABLE"
NATIVE_BIOMARKER_MISMATCH = "NATIVE_BIOMARKER_MISMATCH"

# --- bucket dell'asse ---------------------------------------------------------
#
# I nomi sono quelli del gate 1.0 e vengono ripetuti qui invece di essere
# importati: questo modulo non dipende da nessun gate, ed e' cio' che gli
# permette di essere interrogato da solo in un test.

PRIMARY_BUCKET = "primary_ranked_results"
AUDIT_BUCKET = "audit_only_results"
REJECTED_BUCKET = "rejected_by_native_constraints"

_AXIS_BUCKET = {
    MATCH_NOT_CONSTRAINED: PRIMARY_BUCKET,
    MATCH_EXACT: PRIMARY_BUCKET,
    MATCH_EXACT_BOOLEAN_SET: PRIMARY_BUCKET,
    MATCH_DISJUNCT_MEMBER: PRIMARY_BUCKET,
    MATCH_CONJUNCTION_SATISFIED: PRIMARY_BUCKET,
    MATCH_CONJUNCTION_PARTIAL: REJECTED_BUCKET,
    MATCH_UNRESOLVED: AUDIT_BUCKET,
    MATCH_INCOMPATIBLE: REJECTED_BUCKET,
}

_REASON_CODES = {
    MATCH_NOT_CONSTRAINED: (BIOMARKER_NOT_CONSTRAINED,),
    MATCH_EXACT: (BIOMARKER_EXACT_LITERAL,),
    MATCH_EXACT_BOOLEAN_SET: (BIOMARKER_EXACT_SET,),
    MATCH_DISJUNCT_MEMBER: (BIOMARKER_DISJUNCT_MEMBER,),
    MATCH_CONJUNCTION_SATISFIED: (BIOMARKER_CONJUNCTION_SATISFIED,),
    MATCH_CONJUNCTION_PARTIAL: (
        BIOMARKER_CONJUNCTION_PARTIAL,
        NATIVE_BIOMARKER_MISMATCH,
    ),
    MATCH_UNRESOLVED: (BIOMARKER_EXPRESSION_UNRESOLVED,),
    MATCH_INCOMPATIBLE: (NATIVE_BIOMARKER_MISMATCH,),
}

# I caratteri che segnalano una struttura che questo parser non legge. Non
# vengono ignorati e non vengono rimossi: la loro presenza *e'* l'esito.
_STRUCTURE_CHARS = ("(", ")", "[", "]")

_OR_SEPARATOR = " or "
_AND_SEPARATOR = " and "


def normalize(value: Any) -> str:
    """Spazi collassati e minuscole.

    Identica alla `normalize` del contratto congelato, ridefinita qui perche'
    importarla creerebbe un ciclo: e' il contratto a dipendere da questo modulo,
    non il contrario.
    """
    return " ".join(str(value or "").split()).lower()


@dataclass(frozen=True)
class BiomarkerExpression:
    """Un'espressione di biomarcatore in forma canonica.

    `terms` e' gia' deduplicato e ordinato. `literal` conserva la forma
    normalizzata di partenza, perche' un artefatto che riportasse soltanto la
    forma canonica non permetterebbe piu' di risalire a cio' che la fonte scrive.
    """

    operator: str
    terms: tuple[str, ...]
    literal: str

    @property
    def term_set(self) -> frozenset[str]:
        return frozenset(self.terms)

    @property
    def is_interpretable(self) -> bool:
        return self.operator != OP_UNRESOLVED

    @property
    def is_empty(self) -> bool:
        return self.operator == OP_EMPTY

    def to_dict(self) -> dict[str, Any]:
        return {
            "literal": self.literal,
            "operator": self.operator,
            "terms": list(self.terms),
        }


@dataclass(frozen=True)
class BiomarkerMatch:
    """Esito del confronto fra l'espressione della query e quella del claim."""

    match_type: str
    compatible: bool
    axis_bucket: str
    substitutes: bool
    query_expression: BiomarkerExpression
    claim_expression: BiomarkerExpression
    reason_codes: tuple[str, ...] = ()

    @property
    def is_unresolved(self) -> bool:
        return self.match_type == MATCH_UNRESOLVED

    def to_dict(self) -> dict[str, Any]:
        """Il vocabolario che il gate 1.0 si aspetta, piu' cio' che aggiunge.

        `match_type` e `compatible` sono le chiavi che il gate integrato legge
        gia'; le altre dicono *quale* relazione booleana ha deciso, che il gate
        1.0 non era in grado di distinguere.
        """
        return {
            "axis_bucket": self.axis_bucket,
            "claim_expression": self.claim_expression.to_dict(),
            "compatible": self.compatible,
            "contract_version": CONTRACT_VERSION,
            "match_type": self.match_type,
            "query_expression": self.query_expression.to_dict(),
            "reason_codes": list(self.reason_codes),
            "substitution_applied": self.substitutes,
        }


_OPERATOR_WORDS = ("or", "and")


def _is_malformed(term: str) -> bool:
    """Un termine che porta ancora un operatore non e' un termine.

    Un operatore doppio (`A OR OR B`) non produce un termine vuoto: lo split
    consuma il primo separatore e lascia `or b`, che passerebbe per il nome di un
    biomarcatore. Accettarlo significherebbe confrontare `or b` con i letterali
    del corpus e concludere che non corrisponde a niente — una risposta
    plausibile alla domanda sbagliata.
    """
    if not term:
        return True
    if term in _OPERATOR_WORDS:
        return True
    first, _, _ = term.partition(" ")
    *_, last = term.rpartition(" ")
    return first in _OPERATOR_WORDS or last in _OPERATOR_WORDS


def _split_terms(text: str, separator: str) -> tuple[str, ...]:
    """Termini deduplicati e ordinati. Un termine malformato rende l'espressione illeggibile."""
    parts = [part.strip() for part in text.split(separator)]
    if any(_is_malformed(part) for part in parts):
        return ()
    return tuple(sorted(set(parts)))


def canonical(value: Any) -> BiomarkerExpression:
    """Forma canonica di un'espressione: normalizza, deduplica, ordina.

    L'ordine dei passi non e' indifferente. La deduplicazione avviene *dopo* la
    normalizzazione — altrimenti `EGFR L858R` e `egfr  l858r` resterebbero due
    termini — e *prima* del conteggio, perche' e' quel conteggio a decidere se
    l'espressione sia ancora booleana: `A OR A` e' `A`.
    """
    literal = normalize(value)
    if not literal:
        return BiomarkerExpression(OP_EMPTY, (), "")

    if any(char in literal for char in _STRUCTURE_CHARS):
        return BiomarkerExpression(OP_UNRESOLVED, (), literal)

    has_or = _OR_SEPARATOR in literal
    has_and = _AND_SEPARATOR in literal
    if has_or and has_and:
        # Senza parentesi la precedenza fra i due operatori non e' scritta da
        # nessuna parte, e sceglierne una sarebbe interpretare la fonte.
        return BiomarkerExpression(OP_UNRESOLVED, (), literal)

    if not has_or and not has_and:
        # Un operatore in testa o in coda non produce un separatore — non ha
        # spazi da entrambi i lati — e l'espressione sembrerebbe un termine solo
        # con un pezzo di sintassi attaccato.
        if _is_malformed(literal):
            return BiomarkerExpression(OP_UNRESOLVED, (), literal)
        return BiomarkerExpression(OP_SINGLE, (literal,), literal)

    separator = _OR_SEPARATOR if has_or else _AND_SEPARATOR
    terms = _split_terms(literal, separator)
    if not terms:
        return BiomarkerExpression(OP_UNRESOLVED, (), literal)
    if len(terms) == 1:
        # `A OR A`, `A AND A`: l'operatore non lega piu' niente.
        return BiomarkerExpression(OP_SINGLE, terms, literal)
    return BiomarkerExpression(OP_OR if has_or else OP_AND, terms, literal)


def _verdict(
    match_type: str,
    query: BiomarkerExpression,
    claim: BiomarkerExpression,
) -> BiomarkerMatch:
    return BiomarkerMatch(
        match_type=match_type,
        compatible=match_type in COMPATIBLE_MATCH_TYPES,
        axis_bucket=_AXIS_BUCKET[match_type],
        substitutes=match_type in SUBSTITUTING_MATCH_TYPES,
        query_expression=query,
        claim_expression=claim,
        reason_codes=_REASON_CODES[match_type],
    )


def match(query_value: Any, claim_value: Any) -> BiomarkerMatch:
    """Relazione booleana fra il biomarcatore chiesto e quello del claim.

    La tabella e' esplicita e non ha un ramo permissivo di chiusura: tutto cio'
    che non e' riconosciuto e' `incompatible`, e tutto cio' che non e' leggibile
    e' `unresolved_boolean_expression`. Le due cose sono diverse e restano
    distinte fino all'artefatto.
    """
    query = canonical(query_value)
    claim = canonical(claim_value)

    # Una domanda che non nomina un biomarcatore non vincola l'asse. Vale prima
    # di ogni altra cosa, anche prima dell'illeggibilita' del claim: un asse che
    # la query non usa non puo' mandare niente in audit.
    if query.is_empty:
        return _verdict(MATCH_NOT_CONSTRAINED, query, claim)

    if not query.is_interpretable or not claim.is_interpretable:
        return _verdict(MATCH_UNRESOLVED, query, claim)

    if claim.is_empty:
        return _verdict(MATCH_INCOMPATIBLE, query, claim)

    if query.literal == claim.literal:
        return _verdict(MATCH_EXACT, query, claim)

    if query.operator == claim.operator and query.term_set == claim.term_set:
        # Stesso operatore, stessi termini, ordine o duplicati diversi.
        return _verdict(MATCH_EXACT_BOOLEAN_SET, query, claim)

    # Una query disgiuntiva chiede l'insieme, non uno dei suoi membri: sostenere
    # che raggiunga un claim piu' stretto significherebbe decidere quale disgiunto
    # il paziente porta, che la domanda non dice.
    if query.operator == OP_OR:
        return _verdict(MATCH_INCOMPATIBLE, query, claim)

    wanted = query.term_set

    if claim.operator == OP_OR:
        if wanted & claim.term_set:
            return _verdict(MATCH_DISJUNCT_MEMBER, query, claim)
        return _verdict(MATCH_INCOMPATIBLE, query, claim)

    required = claim.term_set
    if required <= wanted:
        return _verdict(MATCH_CONJUNCTION_SATISFIED, query, claim)
    if required & wanted:
        return _verdict(MATCH_CONJUNCTION_PARTIAL, query, claim)
    return _verdict(MATCH_INCOMPATIBLE, query, claim)


def boolean_semantics_contract() -> dict[str, Any]:
    """Descrizione serializzabile della semantica, per gli artefatti di fase."""
    return {
        "canonicalization_steps": [
            "normalizzazione: spazi collassati, minuscole",
            "split sull'operatore, uno solo per espressione",
            "deduplicazione dei termini",
            "ordinamento dei termini",
            "identita' = (operatore, insieme dei termini), mai la stringa",
        ],
        "compatible_match_types": sorted(COMPATIBLE_MATCH_TYPES),
        "contract_version": CONTRACT_VERSION,
        "degenerate_single_term_collapses_operator": True,
        "match_type_axis_bucket": dict(sorted(_AXIS_BUCKET.items())),
        "match_type_reason_codes": {
            name: list(codes) for name, codes in sorted(_REASON_CODES.items())
        },
        "match_types": list(MATCH_TYPES),
        "operators": list(OPERATORS),
        "placeholders_are_never_wildcards": [
            "il confronto fra termini e' uguaglianza esatta normalizzata",
            "FGFR2::v Fusion e FGFR2::? Fusion non raggiungono FGFR2::BICC1 Fusion",
        ],
        "query_disjunction_requires_set_equality": True,
        "substituting_match_types": sorted(SUBSTITUTING_MATCH_TYPES),
        "unresolved_expressions_go_to_audit_never_rejected": True,
        "unresolved_when": [
            "operatori misti nella stessa espressione, senza parentesi che ne fissino la precedenza",
            "parentesi o parentesi quadre, che indicano un annidamento non letto",
            "un termine vuoto fra due separatori",
        ],
    }


def describe(query_value: Any, claim_value: Any) -> dict[str, Any]:
    """Riga di audit per una singola coppia query/claim."""
    verdict = match(query_value, claim_value)
    return {
        "axis_bucket": verdict.axis_bucket,
        "claim_expression": verdict.claim_expression.to_dict(),
        "compatible": verdict.compatible,
        "match_type": verdict.match_type,
        "query_expression": verdict.query_expression.to_dict(),
        "reason_codes": list(verdict.reason_codes),
        "substitution_applied": verdict.substitutes,
    }


def substitution_record(
    query_value: Any, claim_value: Any, verdict: BiomarkerMatch | None = None
) -> dict[str, str]:
    """Che cosa e' stato passato al gate 1.1, e perche'.

    La sostituzione dell'espressione e' l'unico punto in cui questo modulo
    modifica cio' che un altro gate vede. Registrarla per esteso e' cio' che la
    rende una scelta dichiarata invece che un effetto collaterale.
    """
    decided = verdict if verdict is not None else match(query_value, claim_value)
    original = normalize(query_value)
    claim_literal = normalize(claim_value)
    substituted = decided.substitutes
    return {
        "claim_biomarker_expression": claim_literal,
        "effective_biomarker_passed_to_v11": claim_literal if substituted else original,
        "original_query_biomarker": original,
        "substitution_reason": decided.match_type if substituted else "none",
    }


def as_gate_axis(verdict: BiomarkerMatch) -> Mapping[str, Any]:
    """L'asse nel formato che il gate integrato pubblica."""
    return verdict.to_dict()


__all__ = [
    "AUDIT_BUCKET",
    "COMPATIBLE_MATCH_TYPES",
    "CONTRACT_VERSION",
    "MATCH_CONJUNCTION_PARTIAL",
    "MATCH_CONJUNCTION_SATISFIED",
    "MATCH_DISJUNCT_MEMBER",
    "MATCH_EXACT",
    "MATCH_EXACT_BOOLEAN_SET",
    "MATCH_INCOMPATIBLE",
    "MATCH_NOT_CONSTRAINED",
    "MATCH_TYPES",
    "MATCH_UNRESOLVED",
    "OPERATORS",
    "OP_AND",
    "OP_EMPTY",
    "OP_OR",
    "OP_SINGLE",
    "OP_UNRESOLVED",
    "PRIMARY_BUCKET",
    "REJECTED_BUCKET",
    "SUBSTITUTING_MATCH_TYPES",
    "BiomarkerExpression",
    "BiomarkerMatch",
    "as_gate_axis",
    "boolean_semantics_contract",
    "canonical",
    "describe",
    "match",
    "normalize",
    "substitution_record",
]
