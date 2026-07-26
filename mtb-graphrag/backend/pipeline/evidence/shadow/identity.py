"""Identita' deterministica di parent, claim e associazioni.

La formula del claim e' quella congelata dall'adjudication::

    claim_id = SHA256(
        graph_evidence_id | claim_type | canonical_intervention_or_regimen
        | biomarker | direction | polarity | source_unit_id
    )

Tre scelte meritano di essere dette, perche' ognuna e' un modo di sbagliare che
e' stato escluso.

**Il separatore e' esplicito.** Concatenare i campi senza separatore rende
`("ab", "c")` e `("a", "bc")` la stessa stringa. Con `|` due composizioni diverse
restano ID diversi. I campi non possono contenere il separatore, e questo viene
verificato invece che assunto.

**I regimi sono order-invariant.** La canonicalizzazione ordina i componenti,
quindi `erlotinib + ramucirumab` e `ramucirumab + erlotinib` sono lo stesso
claim. L'ordine di scrittura non e' un'informazione clinica.

**Gli alias pending non vengono fusi.** `BGJ398` non diventa `infigratinib` nella
canonicalizzazione. Se lo diventasse, l'ID renderebbe stabile un'equivalenza che
nessuno ha verificato — esattamente l'inferenza che l'adjudication ha rifiutato
in evidence:1851 e evidence:1853.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from typing import Any

CLAIM_ID_FORMULA_VERSION = "claim_id_formula/1.0"

FIELD_SEPARATOR = "|"
REGIMEN_COMPONENT_SEPARATOR = " + "

CLAIM_ID_PREFIX = "CLM-"
PARENT_ID_PREFIX = "GEP-"
UNSUPPORTED_ID_PREFIX = "UNS-"
UNRESOLVED_ID_PREFIX = "UNR-"

# Lunghezza del troncamento esadecimale. Congelata dalla specification insieme al
# prefisso: gli ID gia' emessi dall'adjudication devono essere riprodotti tali e
# quali, non ricalcolati con una convenzione nuova.
ID_HEX_LENGTH = 20

CLAIM_IDENTITY_FIELDS = (
    "graph_evidence_id",
    "claim_type",
    "canonical_intervention_or_regimen",
    "biomarker",
    "direction",
    "polarity",
    "source_unit_id",
)


class IdentityError(ValueError):
    """Un campo di identita' e' assente o non serializzabile senza ambiguita'."""


def _require_field(name: str, value: Any) -> str:
    if value is None:
        raise IdentityError(f"campo di identita' assente: {name}")
    text = str(value)
    if not text.strip():
        raise IdentityError(f"campo di identita' vuoto: {name}")
    if FIELD_SEPARATOR in text:
        raise IdentityError(
            f"il campo {name} contiene il separatore {FIELD_SEPARATOR!r}: "
            "la serializzazione canonica diventerebbe ambigua"
        )
    return text


def canonical_serialization(fields: Sequence[tuple[str, Any]]) -> str:
    """Serializzazione canonica esplicita: nessun campo opzionale, nessun default."""
    return FIELD_SEPARATOR.join(_require_field(name, value) for name, value in fields)


def canonical_regimen(components: Iterable[str]) -> str:
    """Forma canonica di un regime: componenti ordinati, separatore fisso.

    L'ordinamento e' cio' che rende l'identita' indipendente dall'ordine di
    scrittura. La normalizzazione si ferma qui: nessuna sostituzione di codici di
    sviluppo con nomi generici, per le ragioni dette nel docstring del modulo.
    """
    normalized = [" ".join(str(item).split()) for item in components]
    if not normalized or any(not item for item in normalized):
        raise IdentityError("un regime richiede componenti non vuoti")
    return REGIMEN_COMPONENT_SEPARATOR.join(sorted(normalized))


def claim_identity_payload(
    *,
    graph_evidence_id: str,
    claim_type: str,
    canonical_intervention_or_regimen: str,
    biomarker: str,
    direction: str,
    polarity: str,
    source_unit_id: str,
) -> str:
    """La stringa esatta su cui viene calcolato l'hash di identita'."""
    return canonical_serialization(
        (
            ("graph_evidence_id", graph_evidence_id),
            ("claim_type", claim_type),
            ("canonical_intervention_or_regimen", canonical_intervention_or_regimen),
            ("biomarker", biomarker),
            ("direction", direction),
            ("polarity", polarity),
            ("source_unit_id", source_unit_id),
        )
    )


def _digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def claim_identity_sha256(**kwargs: str) -> str:
    return _digest(claim_identity_payload(**kwargs))


def claim_id(**kwargs: str) -> str:
    """ID del claim: prefisso piu' i primi 20 caratteri esadecimali dell'hash."""
    return CLAIM_ID_PREFIX + claim_identity_sha256(**kwargs)[:ID_HEX_LENGTH]


def parent_id(graph_evidence_id: str) -> str:
    """ID del contenitore di provenienza.

    Il kind entra nel payload perche' parent e claim non condividano mai lo
    spazio degli ID: un parent non deve poter essere scambiato per un claim
    nemmeno per collisione di stringa.
    """
    payload = canonical_serialization(
        (("kind", "graph_evidence_record"), ("graph_evidence_id", graph_evidence_id))
    )
    return PARENT_ID_PREFIX + _digest(payload)[:ID_HEX_LENGTH]


def association_id(
    *,
    kind: str,
    graph_evidence_id: str,
    intervention_literal: str,
    biomarker: str,
    source_unit_id: str,
) -> str:
    """ID di un'associazione unsupported o unresolved.

    Le associazioni non hanno direction ne' polarity — non affermano nulla, e
    darne una sarebbe attribuire loro un contenuto che non hanno. L'identita' e'
    quindi il letterale di intervento sul biomarcatore, dentro l'unita' di fonte
    in cui compare.
    """
    if kind == "unsupported_association":
        prefix = UNSUPPORTED_ID_PREFIX
    elif kind == "unresolved_association":
        prefix = UNRESOLVED_ID_PREFIX
    else:
        raise IdentityError(f"kind di associazione sconosciuto: {kind}")
    payload = canonical_serialization(
        (
            ("kind", kind),
            ("graph_evidence_id", graph_evidence_id),
            ("intervention_literal", intervention_literal),
            ("biomarker", biomarker),
            ("source_unit_id", source_unit_id),
        )
    )
    return prefix + _digest(payload)[:ID_HEX_LENGTH]
