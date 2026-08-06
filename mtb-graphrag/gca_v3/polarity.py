"""Polarità della fonte — tre concetti tenuti separati.

L'audit (`docs/graph_candidate_v3/01_source_semantics_audit.md`) ha stabilito
che la sorgente porta **due colonne ortogonali**:

* ``significance`` — *quale* relazione il grafo propone (18 valori distinti);
* ``evidence_direction`` — *se la fonte la sostiene* (3 valori, uno dei quali
  è l'assenza).

Il contratto v2 fondeva le due in un unico campo ``direction`` derivato dalla
sola ``significance``, e la posizione della fonte sopravviveva solo dentro
``source_properties``. v3 le separa.

**Regola non negoziabile**: ``DOES_NOT_SUPPORT_ASSERTION`` non viene mai
convertito nella direzione opposta.

    "Does Not Support Resistance"  ≠  "Supports Sensitivity"

Una fonte che non sostiene una resistenza non sostiene, per ciò stesso, una
sensibilità: sostiene l'assenza di quella specifica associazione, e
tipicamente riporta un risultato non differente. ``source_supported_direction``
resta perciò ``None`` in tutti questi casi.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------- 1
#: Direzione proposta dal path del Knowledge Graph. I valori derivano
#: **esattamente** dai 18 valori di ``significance`` osservati nell'export:
#: nessun enum è stato inventato, nessun valore osservato è stato collassato.
GRAPH_DIRECTION_BY_SIGNIFICANCE: dict[str, str] = {
    "sensitivity/response": "SENSITIVITY",
    "resistance": "RESISTANCE",
    "reduced sensitivity": "REDUCED_SENSITIVITY",
    "adverse response": "ADVERSE_RESPONSE",
    "better outcome": "BETTER_OUTCOME",
    "poor outcome": "POOR_OUTCOME",
    "positive": "POSITIVE",
    "negative": "NEGATIVE",
    "predisposition": "PREDISPOSITION",
    "protectiveness": "PROTECTIVENESS",
    "oncogenicity": "ONCOGENICITY",
    "gain of function": "GAIN_OF_FUNCTION",
    "loss of function": "LOSS_OF_FUNCTION",
    "dominant negative": "DOMINANT_NEGATIVE",
    "neomorphic": "NEOMORPHIC",
    "unaltered function": "UNALTERED_FUNCTION",
    "uncertain significance": "UNCERTAIN_SIGNIFICANCE",
}
GRAPH_DIRECTION_UNKNOWN = "UNKNOWN"
GRAPH_DIRECTION_UNMAPPED = "UNMAPPED_SOURCE_VALUE"

#: Direzioni che non affermano un effetto: non possono produrre
#: ``SOURCE_ALIGNED`` nemmeno quando la fonte le sostiene.
NON_DIRECTIONAL = frozenset({
    "UNCERTAIN_SIGNIFICANCE", "UNALTERED_FUNCTION", "UNKNOWN", "UNMAPPED_SOURCE_VALUE",
})

# --------------------------------------------------------------------------- 2
SUPPORTS_ASSERTION = "SUPPORTS_ASSERTION"
DOES_NOT_SUPPORT_ASSERTION = "DOES_NOT_SUPPORT_ASSERTION"
CONTRADICTS_ASSERTION = "CONTRADICTS_ASSERTION"
NEUTRAL_OR_NO_DIFFERENCE = "NEUTRAL_OR_NO_DIFFERENCE"
UNCLEAR = "UNCLEAR"
NOT_REPORTED = "NOT_REPORTED"
UNMAPPED_SOURCE_VALUE = "UNMAPPED_SOURCE_VALUE"

#: Mappatura dai valori realmente osservati di ``evidence_direction``.
#:
#: ``CONTRADICTS_ASSERTION`` e ``NEUTRAL_OR_NO_DIFFERENCE`` fanno parte
#: dell'enum ma **nessun valore sorgente vi mappa**: l'export non contiene un
#: valore "Contradicts". Restano definiti perché il contratto deve poterli
#: esprimere se una sorgente futura li portasse; non vengono prodotti per
#: inferenza da ``Does Not Support``.
SOURCE_POLARITY_BY_DIRECTION: dict[str, str] = {
    "supports": SUPPORTS_ASSERTION,
    "does not support": DOES_NOT_SUPPORT_ASSERTION,
}

# --------------------------------------------------------------------------- 3
SOURCE_ALIGNED = "SOURCE_ALIGNED"
SOURCE_DOES_NOT_SUPPORT = "SOURCE_DOES_NOT_SUPPORT"
SOURCE_CONTRADICTS = "SOURCE_CONTRADICTS"
SOURCE_NEUTRAL = "SOURCE_NEUTRAL"
SOURCE_ALIGNMENT_UNCLEAR = "SOURCE_ALIGNMENT_UNCLEAR"
SOURCE_ALIGNMENT_NOT_AVAILABLE = "SOURCE_ALIGNMENT_NOT_AVAILABLE"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def graph_direction(significance: Any) -> str:
    """Direzione proposta dal grafo, dalla sola ``significance``."""
    text = _clean(significance).lower()
    if not text:
        return GRAPH_DIRECTION_UNKNOWN
    return GRAPH_DIRECTION_BY_SIGNIFICANCE.get(text, GRAPH_DIRECTION_UNMAPPED)


def source_support_polarity(evidence_direction: Any) -> str:
    """Posizione della fonte rispetto all'asserzione, da ``evidence_direction``."""
    text = _clean(evidence_direction).lower()
    if not text:
        return NOT_REPORTED
    return SOURCE_POLARITY_BY_DIRECTION.get(text, UNMAPPED_SOURCE_VALUE)


def source_supported_direction(polarity: str, direction: str) -> str | None:
    """Direzione **esplicitamente sostenuta** dalla fonte, o ``None``.

    Restituisce una direzione soltanto quando la fonte sostiene l'asserzione e
    la direzione è effettivamente direzionale. In ogni altro caso è ``None``:
    in particolare ``DOES_NOT_SUPPORT_ASSERTION`` **non** produce mai la
    direzione opposta, perché l'opposto non è ciò che la fonte afferma.
    """
    if polarity != SUPPORTS_ASSERTION:
        return None
    if direction in NON_DIRECTIONAL:
        return None
    return direction


def source_alignment_status(polarity: str, direction: str) -> str:
    """Relazione fra candidate e metadato sorgente.

    **Non** è uno status clinico, **non** è un esito del Paper Context Enricher
    e **non** sostituisce la validazione documentale: descrive soltanto se il
    metadato della fonte sostiene la relazione che la candidate afferma.
    """
    if polarity == DOES_NOT_SUPPORT_ASSERTION:
        return SOURCE_DOES_NOT_SUPPORT
    if polarity == CONTRADICTS_ASSERTION:
        return SOURCE_CONTRADICTS
    if polarity == NEUTRAL_OR_NO_DIFFERENCE:
        return SOURCE_NEUTRAL
    if polarity == NOT_REPORTED:
        return SOURCE_ALIGNMENT_NOT_AVAILABLE
    if polarity in {UNCLEAR, UNMAPPED_SOURCE_VALUE}:
        return SOURCE_ALIGNMENT_UNCLEAR
    # polarity == SUPPORTS_ASSERTION
    if direction in NON_DIRECTIONAL:
        return SOURCE_NEUTRAL
    return SOURCE_ALIGNED


def describe(significance: Any, evidence_direction: Any) -> dict[str, Any]:
    """I quattro campi di polarità, più il raw preservato."""
    direction = graph_direction(significance)
    polarity = source_support_polarity(evidence_direction)
    return {
        "graph_direction": direction,
        "source_support_polarity": polarity,
        "source_supported_direction": source_supported_direction(polarity, direction),
        "source_alignment_status": source_alignment_status(polarity, direction),
        "source_polarity_raw": {
            "significance": _clean(significance) or None,
            "evidence_direction": _clean(evidence_direction) or None,
        },
    }
