"""Errori del retriever qualificato.

Perche' tipizzarli. Un elenco di stringhe dice *che* qualcosa e' andato storto;
un tipo dice *cosa*, e permette a chi chiama di distinguere fra un errore di
configurazione — la query e' malformata, il corpus e' quello sbagliato — e una
violazione di politica, che e' un'altra cosa e va trattata diversamente.

`PrototypeQualifierAsHardFilterError` merita una riga da sola. Non descrive un
guasto: descrive qualcuno che sta usando un qualificatore prototipo per
escludere una evidenza. E' l'unico modo in cui questo prototipo puo' fare danno
reale, perche' un filtro sbagliato rimuove cio' che nessuno potra' piu' vedere.
"""

from __future__ import annotations

RETRIEVER_ERROR_VERSION = "qualified_retrieval_errors/1.0"


class QualifiedRetrievalError(RuntimeError):
    """Famiglia comune: chi esegue una retrieval intercetta questa."""

    rule_id = "qualified_retrieval"


# --- corpus -------------------------------------------------------------------


class CorpusMismatchError(QualifiedRetrievalError):
    """Il corpus caricato non e' quello che la query dichiara di volere."""

    rule_id = "corpus_mismatch"


class UnsupportedCorpusVersionError(QualifiedRetrievalError):
    """La versione del corpus non e' fra quelle che il retriever sa leggere."""

    rule_id = "unsupported_corpus_version"


class FingerprintMismatchError(CorpusMismatchError):
    """L'impronta del corpus non coincide con quella attesa.

    Distinta da `CorpusMismatchError` perche' la causa e' diversa: la versione
    puo' essere giusta e il contenuto no, ed e' il caso in cui qualcuno ha
    rigenerato il corpus senza cambiarne il numero.
    """

    rule_id = "fingerprint_mismatch"


class HistoricalUnitInActiveIndexError(QualifiedRetrievalError):
    """Una unita' storica e' finita nell'indice dei candidati.

    Una parent sostituita o una proposta respinta restano nel corpus perche' la
    storia sia leggibile. Trovarle fra i qualificatori di un risultato non
    porterebbe alcun segnale che dica che descrivono uno stato superato.
    """

    rule_id = "historical_unit_in_active_index"


class IndexIntegrityError(QualifiedRetrievalError):
    """Un indice punta a qualcosa che non esiste, o lo elenca due volte."""

    rule_id = "index_integrity"


# --- query --------------------------------------------------------------------


class InvalidQueryError(QualifiedRetrievalError):
    """La query non e' interrogabile cosi' com'e'."""

    rule_id = "invalid_query"


class UnknownRetrievalModeError(InvalidQueryError):
    """La modalita' richiesta non esiste."""

    rule_id = "unknown_retrieval_mode"


# --- politica -----------------------------------------------------------------


class RetrievalPolicyViolation(QualifiedRetrievalError):
    """Il retriever sta per fare qualcosa che la politica non permette."""

    rule_id = "retrieval_policy_violation"


class PrototypeQualifierAsHardFilterError(RetrievalPolicyViolation):
    """Un qualificatore non definitivo usato per escludere una evidenza.

    Non e' un guasto: e' l'unico modo in cui questo prototipo puo' fare danno
    reale. Mostrare un qualificatore sbagliato lo espone a chi puo' correggerlo;
    filtrare con un qualificatore sbagliato rimuove evidenza che nessuno vedra'
    piu'.
    """

    rule_id = "prototype_qualifier_used_as_hard_filter"


class NonDeterministicOrderingError(QualifiedRetrievalError):
    """Due risultati non sono ordinabili in modo stabile.

    Significa che il tie-break non ha esaurito le differenze, e quindi che
    l'ordine dipende da qualcosa che non e' dichiarato.
    """

    rule_id = "non_deterministic_ordering"


class ScoringConfigurationMismatchError(QualifiedRetrievalError):
    """La configurazione di scoring non e' quella dichiarata."""

    rule_id = "scoring_configuration_mismatch"


__all__ = [
    "RETRIEVER_ERROR_VERSION",
    "QualifiedRetrievalError",
    "CorpusMismatchError",
    "UnsupportedCorpusVersionError",
    "FingerprintMismatchError",
    "HistoricalUnitInActiveIndexError",
    "IndexIntegrityError",
    "InvalidQueryError",
    "UnknownRetrievalModeError",
    "RetrievalPolicyViolation",
    "PrototypeQualifierAsHardFilterError",
    "NonDeterministicOrderingError",
    "ScoringConfigurationMismatchError",
]
