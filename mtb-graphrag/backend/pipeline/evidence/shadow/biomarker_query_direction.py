"""Semantica direzionale delle query congiuntive.

Il gate 1.2 ha insegnato all'asse del biomarcatore a leggere gli operatori, e
nel farlo ha adottato una regola sola per le congiunzioni: se i termini del
claim sono contenuti in quelli della query, la query soddisfa il claim. E' vera
come implicazione logica e sbagliata come affermazione clinica, ed e' la
differenza che questo modulo scrive.

Una query `EGFR L858R AND EGFR T790M` descrive un paziente co-alterato. Un claim
su `EGFR L858R` da solo e' stato misurato su una popolazione che quella
co-alterazione non aveva, e il suo risultato non e' separabile: non si sa quanto
di quell'effetto sopravviva in presenza della seconda alterazione. Concedergli il
bucket primario significherebbe attribuire al paziente co-alterato un risultato
ottenuto altrove. Respingerlo perderebbe l'unica evidenza disponibile. Warning e'
l'unico posto in cui entrambe le cose restano vere — ed e' lo stesso argomento
con cui il gate 1.1 tratta il sale verificato della moiety.

La direzione conta, e conta in tutti e due i versi.

    query piu' specifica del claim   -> warning, mai primary
    claim piu' specifico della query -> rejected

Il secondo verso non e' simmetrico al primo. Un claim che chiede
`A AND B AND C` parla di una popolazione che la query non descrive: il paziente
non ha la terza alterazione, e il claim non lo riguarda. Non e' evidenza
indebolita, e' evidenza su un altro caso.

Il modulo non tocca le query che non sono congiuntive. Una query a termine
singolo e una query disgiuntiva continuano a essere decise dal gate 1.2 parola
per parola: `evidence:11219` resta raggiunto dal suo disgiunto, `evidence:11598`
e `evidence:11599` restano respinti dalla congiunzione soddisfatta a meta'. La
correzione e' circoscritta al verso che il 1.2 aveva collassato.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.pipeline.evidence.shadow import biomarker_expression as BIO

CONTRACT_VERSION = "biomarker-directional-semantics/1.0"

# La modalita' in cui il punteggio qualificato non sopravvive al warning. Nelle
# altre il warning resta ordinabile dentro il proprio bucket.
STRICT_POLICY_MODE = "strict_verified"

# --- match type -------------------------------------------------------------
#
# I primi due sono quelli del 1.2, ripresi senza cambiarne il nome: un match type
# che cambiasse significato fra due gate renderebbe illeggibili gli artefatti
# della fase precedente.

MATCH_NOT_CONSTRAINED = BIO.MATCH_NOT_CONSTRAINED
MATCH_EXACT = BIO.MATCH_EXACT
MATCH_EXACT_BOOLEAN_SET = BIO.MATCH_EXACT_BOOLEAN_SET
MATCH_DISJUNCT_MEMBER = BIO.MATCH_DISJUNCT_MEMBER
MATCH_CONJUNCTION_PARTIAL = BIO.MATCH_CONJUNCTION_PARTIAL
MATCH_UNRESOLVED = BIO.MATCH_UNRESOLVED
MATCH_INCOMPATIBLE = BIO.MATCH_INCOMPATIBLE

# I quattro che il 1.3 aggiunge, tutti e quattro per query congiuntive.
MATCH_QUERY_MORE_SPECIFIC = "query_more_specific_than_claim"
MATCH_CLAIM_REQUIRES_ADDITIONAL = "claim_requires_additional_conjunct"
MATCH_PARTIAL_OVERLAP = "boolean_partial_overlap"
MATCH_NOT_SEPARABLE = "result_not_separable_for_coaltered_query"

DIRECTIONAL_MATCH_TYPES = (
    MATCH_QUERY_MORE_SPECIFIC,
    MATCH_CLAIM_REQUIRES_ADDITIONAL,
    MATCH_PARTIAL_OVERLAP,
    MATCH_NOT_SEPARABLE,
)

MATCH_TYPES = tuple(BIO.MATCH_TYPES) + DIRECTIONAL_MATCH_TYPES

# `conjunction_satisfied` non compare fra i match type del 1.3. Non e' stato
# rinominato: e' stato diviso in due esiti con direzioni opposte, e tenerne il
# nome avrebbe suggerito che la decisione fosse la stessa.
SUPERSEDED_MATCH_TYPES = (BIO.MATCH_CONJUNCTION_SATISFIED,)

# --- reason code -------------------------------------------------------------

CLAIM_SCOPE_BROADER = "CLAIM_BIOMARKER_SCOPE_BROADER_THAN_QUERY"
NOT_SEPARABLE_FOR_COALTERED = "RESULT_NOT_SEPARABLE_FOR_COALTERED_CASE"
CLAIM_REQUIRES_ADDITIONAL = "CLAIM_REQUIRES_ADDITIONAL_CONJUNCT"
PARTIAL_OVERLAP = "BOOLEAN_PARTIAL_OVERLAP"
DISJUNCTIVE_CLAIM_UNDER_CONJUNCTIVE_QUERY = (
    "DISJUNCTIVE_CLAIM_NOT_SEPARABLE_UNDER_CONJUNCTIVE_QUERY"
)
NATIVE_BIOMARKER_MISMATCH = BIO.NATIVE_BIOMARKER_MISMATCH

PRIMARY_BUCKET = BIO.PRIMARY_BUCKET
WARNING_BUCKET = "retained_with_warning"
AUDIT_BUCKET = BIO.AUDIT_BUCKET
REJECTED_BUCKET = BIO.REJECTED_BUCKET

# Bucket dell'asse per i quattro esiti nuovi. Gli altri li porta il 1.2.
_AXIS_BUCKET = {
    MATCH_QUERY_MORE_SPECIFIC: WARNING_BUCKET,
    MATCH_NOT_SEPARABLE: WARNING_BUCKET,
    MATCH_CLAIM_REQUIRES_ADDITIONAL: REJECTED_BUCKET,
    MATCH_PARTIAL_OVERLAP: REJECTED_BUCKET,
}

_REASON_CODES = {
    MATCH_QUERY_MORE_SPECIFIC: (CLAIM_SCOPE_BROADER,),
    MATCH_NOT_SEPARABLE: (DISJUNCTIVE_CLAIM_UNDER_CONJUNCTIVE_QUERY,),
    MATCH_CLAIM_REQUIRES_ADDITIONAL: (
        CLAIM_REQUIRES_ADDITIONAL,
        NATIVE_BIOMARKER_MISMATCH,
    ),
    MATCH_PARTIAL_OVERLAP: (PARTIAL_OVERLAP, NATIVE_BIOMARKER_MISMATCH),
}

# Il codice di spiegazione e' lo stesso per i due esiti di warning: in entrambi
# il claim e' evidenza sul caso non co-alterato, e la ragione per cui non e'
# primaria e' quella.
_EXPLANATION_CODES = {
    MATCH_QUERY_MORE_SPECIFIC: (NOT_SEPARABLE_FOR_COALTERED,),
    MATCH_NOT_SEPARABLE: (NOT_SEPARABLE_FOR_COALTERED,),
}

# I codici che viaggiano nel canale dei warning e non in quello delle ragioni.
_WARNING_CODES = {
    MATCH_QUERY_MORE_SPECIFIC: (CLAIM_SCOPE_BROADER,),
    MATCH_NOT_SEPARABLE: (DISJUNCTIVE_CLAIM_UNDER_CONJUNCTIVE_QUERY,),
}

# Gli esiti in cui il claim e' raggiungibile e il gate a valle va interrogato con
# l'espressione del claim invece che con quella della query.
_SUBSTITUTING = frozenset(
    {
        MATCH_EXACT_BOOLEAN_SET,
        MATCH_QUERY_MORE_SPECIFIC,
        MATCH_NOT_SEPARABLE,
    }
)

_COMPATIBLE = frozenset({MATCH_NOT_CONSTRAINED, MATCH_EXACT, MATCH_EXACT_BOOLEAN_SET})


@dataclass(frozen=True)
class DirectionalMatch:
    """Relazione fra la query e il claim, con la direzione dichiarata."""

    match_type: str
    axis_bucket: str
    substitutes: bool
    primary_eligible: bool
    query_expression: BIO.BiomarkerExpression
    claim_expression: BIO.BiomarkerExpression
    reason_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    explanation_codes: tuple[str, ...] = ()
    decided_by: str = "biomarker_boolean_semantics"

    @property
    def compatible(self) -> bool:
        """Compatibile significa idoneo al primario, non semplicemente raggiunto.

        Un warning e' raggiunto e non compatibile: e' la distinzione che il 1.2
        non poteva fare, perche' il suo asse aveva due soli valori.
        """
        return self.primary_eligible

    @property
    def is_directional(self) -> bool:
        return self.match_type in DIRECTIONAL_MATCH_TYPES

    @property
    def is_unresolved(self) -> bool:
        return self.match_type == MATCH_UNRESOLVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "axis_bucket": self.axis_bucket,
            "claim_expression": self.claim_expression.to_dict(),
            "compatible": self.compatible,
            "contract_version": CONTRACT_VERSION,
            "decided_by": self.decided_by,
            "explanation_codes": list(self.explanation_codes),
            "match_type": self.match_type,
            "primary_eligible": self.primary_eligible,
            "query_expression": self.query_expression.to_dict(),
            "reason_codes": list(self.reason_codes),
            "substitution_applied": self.substitutes,
            "warning_codes": list(self.warning_codes),
        }


def _from_boolean(verdict: BIO.BiomarkerMatch) -> DirectionalMatch:
    """L'esito del 1.2, riportato senza cambiarlo.

    Vale per ogni query che non sia congiuntiva. La correzione del 1.3 riguarda
    un verso che solo una query con AND puo' percorrere, e allargarla alle altre
    cambierebbe decisioni che nessuno ha chiesto di rivedere.
    """
    return DirectionalMatch(
        match_type=verdict.match_type,
        axis_bucket=verdict.axis_bucket,
        substitutes=verdict.substitutes,
        primary_eligible=verdict.compatible,
        query_expression=verdict.query_expression,
        claim_expression=verdict.claim_expression,
        reason_codes=verdict.reason_codes,
        decided_by="biomarker_boolean_semantics",
    )


def _directional(
    match_type: str,
    query: BIO.BiomarkerExpression,
    claim: BIO.BiomarkerExpression,
) -> DirectionalMatch:
    return DirectionalMatch(
        match_type=match_type,
        axis_bucket=_AXIS_BUCKET[match_type],
        substitutes=match_type in _SUBSTITUTING,
        primary_eligible=False,
        query_expression=query,
        claim_expression=claim,
        reason_codes=_REASON_CODES[match_type],
        warning_codes=_WARNING_CODES.get(match_type, ()),
        explanation_codes=_EXPLANATION_CODES.get(match_type, ()),
        decided_by="biomarker_directional_semantics",
    )


def match(query_value: Any, claim_value: Any) -> DirectionalMatch:
    """Relazione direzionale fra il biomarcatore chiesto e quello del claim.

    Per ogni query che non porti un AND l'esito e' quello del gate 1.2, non
    ricalcolato ma riportato. Per le query congiuntive la tabella e' esplicita e
    non ha un ramo permissivo di chiusura.
    """
    verdict = BIO.match(query_value, claim_value)
    query = verdict.query_expression
    claim = verdict.claim_expression

    if query.operator != BIO.OP_AND:
        return _from_boolean(verdict)
    if verdict.is_unresolved:
        return _from_boolean(verdict)
    if claim.is_empty:
        return _from_boolean(verdict)

    # 1. stesso letterale, oppure stesso operatore e stesso insieme canonico.
    if verdict.match_type in (MATCH_EXACT, MATCH_EXACT_BOOLEAN_SET):
        return _from_boolean(verdict)

    wanted = query.term_set
    required = claim.term_set
    shared = wanted & required

    # 5. il claim e' disgiuntivo e la query congiuntiva. Il claim descrive
    #    l'alterazione da sola oppure l'altra da sola, mai le due insieme: il suo
    #    risultato non e' separabile per il caso co-alterato.
    if claim.operator == BIO.OP_OR:
        if shared:
            return _directional(MATCH_NOT_SEPARABLE, query, claim)
        return _from_boolean(verdict)

    # 2. il claim chiede meno della query: evidenza sul caso non co-alterato.
    if required < wanted:
        return _directional(MATCH_QUERY_MORE_SPECIFIC, query, claim)

    # 3. il claim chiede piu' della query: parla di un'altra popolazione.
    if required > wanted:
        return _directional(MATCH_CLAIM_REQUIRES_ADDITIONAL, query, claim)

    # 4. i due insiemi si intersecano senza contenersi.
    if shared:
        return _directional(MATCH_PARTIAL_OVERLAP, query, claim)

    return _from_boolean(verdict)


def score_eligibility(
    verdict: DirectionalMatch, *, policy_mode: str
) -> dict[str, bool]:
    """I flag di punteggio che l'asse concede, prima di ogni altro gate.

    Il warning direzionale non porta punteggio strutturale in nessuna modalita':
    il punteggio strutturale e' il punteggio del bucket primario, e questo bucket
    non lo e'. Il punteggio qualificato e' vietato in `strict_verified`, dove una
    ordinabilita' concessa a un risultato non separabile finirebbe per essere
    letta come una graduatoria clinica.
    """
    if not verdict.is_directional:
        return {}
    if verdict.axis_bucket != WARNING_BUCKET:
        return {
            "qualified_score_eligible": False,
            "structural_score_eligible": False,
        }
    return {
        "qualified_score_eligible": policy_mode != STRICT_POLICY_MODE,
        "structural_score_eligible": False,
    }


def directional_semantics_contract() -> dict[str, Any]:
    """Descrizione serializzabile della semantica, per gli artefatti di fase."""
    return {
        "applies_only_to_query_operator": BIO.OP_AND,
        "boolean_contract": BIO.CONTRACT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "directional_match_types": list(DIRECTIONAL_MATCH_TYPES),
        "match_type_axis_bucket": dict(sorted(_AXIS_BUCKET.items())),
        "match_type_explanation_codes": {
            name: list(codes) for name, codes in sorted(_EXPLANATION_CODES.items())
        },
        "match_type_reason_codes": {
            name: list(codes) for name, codes in sorted(_REASON_CODES.items())
        },
        "match_type_warning_codes": {
            name: list(codes) for name, codes in sorted(_WARNING_CODES.items())
        },
        "non_conjunctive_queries_are_decided_by": BIO.CONTRACT_VERSION,
        "query_superset_of_claim_does_not_grant_primary": True,
        "rules": [
            {
                "bucket": PRIMARY_BUCKET,
                "example": "query A AND B, claim A AND B",
                "match_type": MATCH_EXACT_BOOLEAN_SET,
                "rule": "stesso operatore e stesso insieme canonico",
            },
            {
                "bucket": WARNING_BUCKET,
                "example": "query A AND B, claim A",
                "match_type": MATCH_QUERY_MORE_SPECIFIC,
                "rule": "insieme del claim strettamente contenuto in quello della query",
            },
            {
                "bucket": REJECTED_BUCKET,
                "example": "query A AND B, claim A AND B AND C",
                "match_type": MATCH_CLAIM_REQUIRES_ADDITIONAL,
                "rule": "il claim richiede un congiunto che la query non afferma",
            },
            {
                "bucket": REJECTED_BUCKET,
                "example": "query A AND B, claim A AND C",
                "match_type": MATCH_PARTIAL_OVERLAP,
                "rule": "insiemi che si intersecano senza contenersi",
            },
            {
                "bucket": WARNING_BUCKET,
                "example": "query A AND B, claim A OR B",
                "match_type": MATCH_NOT_SEPARABLE,
                "rule": "claim disgiuntivo sotto una query congiuntiva",
            },
            {
                "bucket": AUDIT_BUCKET,
                "example": "claim A AND B OR C",
                "match_type": MATCH_UNRESOLVED,
                "rule": "espressione mista, annidata o non interpretabile",
            },
        ],
        "strict_mode_forbids_qualified_score_on_directional_warning": True,
        "superseded_match_types": list(SUPERSEDED_MATCH_TYPES),
        "supersedes": BIO.CONTRACT_VERSION,
    }


def describe(query_value: Any, claim_value: Any) -> dict[str, Any]:
    """Riga di audit per una singola coppia query/claim."""
    verdict = match(query_value, claim_value)
    payload = verdict.to_dict()
    payload["boolean_match_type"] = BIO.match(query_value, claim_value).match_type
    return payload


__all__ = [
    "AUDIT_BUCKET",
    "CLAIM_REQUIRES_ADDITIONAL",
    "CLAIM_SCOPE_BROADER",
    "CONTRACT_VERSION",
    "DIRECTIONAL_MATCH_TYPES",
    "DISJUNCTIVE_CLAIM_UNDER_CONJUNCTIVE_QUERY",
    "MATCH_CLAIM_REQUIRES_ADDITIONAL",
    "MATCH_EXACT",
    "MATCH_EXACT_BOOLEAN_SET",
    "MATCH_INCOMPATIBLE",
    "MATCH_NOT_SEPARABLE",
    "MATCH_PARTIAL_OVERLAP",
    "MATCH_QUERY_MORE_SPECIFIC",
    "MATCH_TYPES",
    "MATCH_UNRESOLVED",
    "NOT_SEPARABLE_FOR_COALTERED",
    "PARTIAL_OVERLAP",
    "PRIMARY_BUCKET",
    "REJECTED_BUCKET",
    "STRICT_POLICY_MODE",
    "SUPERSEDED_MATCH_TYPES",
    "WARNING_BUCKET",
    "DirectionalMatch",
    "describe",
    "directional_semantics_contract",
    "match",
    "score_eligibility",
]
