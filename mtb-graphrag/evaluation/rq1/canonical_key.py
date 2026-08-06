"""Chiave canonica di una GraphCandidateAssertion.

La chiave serve a due scopi distinti che non vanno confusi:

* la **identity key** stabilisce quando una candidate materializzata e un path
  eleggibile ricostruito dal grafo sono *lo stesso oggetto*. Include l'identità
  del path (node_ids + edge_ids) perché due relazioni identiche nel contenuto ma
  provenienti da righe diverse del grafo restano oggetti distinti;
* la **semantic key** stabilisce quando due candidate *dicono la stessa cosa*.
  Esclude l'identità del path. Serve solo a contare i duplicati semantici, che
  in questo studio sono un'osservazione, non un errore (§5 del protocollo).

Regole di normalizzazione, esplicitate perché il risultato di RQ1 dipende da
esse:

``NULL_TOKENS``
    ``None``, stringa vuota, e i marcatori testuali prodotti dagli export pandas
    (``nan``, ``none``, ``null``, ``na``) collassano tutti su ``None``. Questo è
    l'unico collasso ammesso: non normalizziamo sinonimi clinici, non facciamo
    fuzzy matching e non mappiamo alias di farmaco (cfr. §11, BGJ398).

Confronto case-insensitive
    Le etichette sono confrontate in ``casefold()`` con spazi interni
    normalizzati. Gli **identificatori** (``id``, ``canonical_id``, PMID, NCT)
    non sono mai normalizzati in questo modo: un identificatore che differisce
    per case è un identificatore diverso.

Ordinamento
    Gli insiemi (disease, biomarkers, interventions, document_identifiers) sono
    ordinati lessicograficamente *nella chiave*. L'ordine con cui la
    materializzazione li ha emessi è verificato separatamente, come controllo di
    fedeltà a sé stante (``ORDER_MISMATCH``): normalizzare l'ordine nella chiave
    e poi dichiarare l'ordine corretto sarebbe circolare.

Null vs assente
    Un campo assente e un campo esplicitamente ``None`` producono la stessa
    chiave, ma sono distinti nel report di fedeltà per campo.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

#: Marcatori che gli export CSV usano per "valore assente". Collassano su None.
NULL_TOKENS = {"", "nan", "none", "null", "na", "n/a"}

_WHITESPACE = re.compile(r"\s+")


def norm_text(value: Any) -> str | None:
    """Normalizza un'etichetta libera per il confronto semantico.

    Restituisce ``None`` per ogni marcatore di assenza. Non tocca il contenuto
    clinico: nessun sinonimo, nessuno stemming, nessuna mappatura.
    """
    if value is None:
        return None
    text = _WHITESPACE.sub(" ", str(value).strip())
    if text.lower() in NULL_TOKENS:
        return None
    return text.casefold()


def norm_identifier(value: Any) -> str | None:
    """Normalizza un identificatore: solo strip, mai casefold."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in NULL_TOKENS:
        return None
    return text


def norm_entity(entity: Mapping[str, Any] | None) -> tuple | None:
    """Riduce un nodo tipizzato a una tupla confrontabile."""
    if not entity:
        return None
    return (
        norm_identifier(entity.get("id")),
        norm_text(entity.get("label")),
        norm_identifier(entity.get("canonical_id")),
        norm_identifier(entity.get("type")),
    )


def norm_entity_set(entities: Iterable[Mapping[str, Any]] | None) -> tuple:
    """Insieme ordinato di entità. L'ordine originale è verificato altrove."""
    if not entities:
        return ()
    normalized = [norm_entity(entity) for entity in entities]
    return tuple(sorted(item for item in normalized if item is not None))


def norm_document_identifiers(identifiers: Iterable[Mapping[str, Any]] | None) -> tuple:
    """Insieme ordinato di identificatori documentali ``(tipo, valore, scope)``.

    Lo ``scope`` fa parte della chiave: lo stesso PMID visto come
    ``evidence_record`` e come ``linked_publication`` è la stessa fonte ma una
    provenance diversa, e RQ2 misura esattamente quella differenza.
    """
    if not identifiers:
        return ()
    rows = []
    for identifier in identifiers:
        scope = norm_identifier(identifier.get("scope"))
        for key in ("pmid", "pmcid", "doi", "nct"):
            value = norm_identifier(identifier.get(key))
            if value is not None:
                rows.append((key, value, scope))
    return tuple(sorted(set(rows)))


def _entity_labels(entities: Iterable[Mapping[str, Any]] | None, wanted_type: str) -> tuple:
    """Etichette normalizzate delle entità di un dato tipo."""
    if not entities:
        return ()
    out = []
    for entity in entities:
        if norm_identifier(entity.get("type")) == wanted_type:
            label = norm_text(entity.get("label"))
            if label is not None:
                out.append(label)
    return tuple(sorted(set(out)))


@dataclass(frozen=True)
class CanonicalKey:
    """Chiave canonica completa di una GraphCandidateAssertion."""

    rule_id: str | None
    predicate: str | None
    subject: tuple | None
    object: tuple | None
    disease: tuple
    gene: tuple
    alteration: tuple
    biomarkers: tuple
    interventions: tuple
    regimen: tuple
    direction: str | None
    evidence_scope: str | None
    diagnostic_scope: str | None
    evidence_record_ids: tuple
    document_identifiers: tuple
    node_ids: tuple
    edge_ids: tuple

    def semantic(self) -> tuple:
        """Proiezione semantica: cosa la candidate afferma, senza il path.

        Esclude ``node_ids``/``edge_ids``/``evidence_record_ids`` perché due
        candidate prodotte da righe diverse del grafo possono affermare la stessa
        relazione. Include disease e direction: fondere su gene+drug soltanto
        sarebbe un collasso clinicamente scorretto.
        """
        return (
            self.predicate,
            self.subject,
            self.object,
            self.disease,
            self.gene,
            self.alteration,
            self.biomarkers,
            self.interventions,
            self.regimen,
            self.direction,
            self.evidence_scope,
            self.diagnostic_scope,
        )

    def identity(self) -> tuple:
        """Proiezione di identità: include il path. Usata per l'accoppiamento 1:1."""
        return (self.rule_id, self.predicate, self.node_ids, self.edge_ids)

    def digest(self) -> str:
        payload = json.dumps(self.__dict__, sort_keys=True, default=list, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_key(candidate: Mapping[str, Any]) -> CanonicalKey:
    """Costruisce la chiave canonica da un record GraphCandidateAssertion."""
    biomarkers = candidate.get("biomarkers") or []
    return CanonicalKey(
        rule_id=norm_identifier(candidate.get("materialization_rule_id")),
        predicate=norm_identifier(candidate.get("predicate")),
        subject=norm_entity(candidate.get("subject")),
        object=norm_entity(candidate.get("object")),
        disease=norm_entity_set(candidate.get("disease")),
        gene=_entity_labels(biomarkers, "Gene"),
        alteration=_entity_labels(biomarkers, "Variant"),
        biomarkers=norm_entity_set(biomarkers),
        interventions=norm_entity_set(candidate.get("interventions")),
        regimen=norm_entity_set(candidate.get("regimen")),
        direction=norm_text(candidate.get("direction")),
        evidence_scope=norm_text(candidate.get("evidence_scope")),
        diagnostic_scope=norm_text(candidate.get("diagnostic_scope")),
        evidence_record_ids=tuple(sorted(
            v for v in (norm_identifier(x) for x in candidate.get("evidence_record_ids") or []) if v
        )),
        document_identifiers=norm_document_identifiers(candidate.get("document_identifiers")),
        node_ids=tuple(norm_identifier(x) for x in candidate.get("node_ids") or []),
        edge_ids=tuple(sorted(
            v for v in (norm_identifier(x) for x in candidate.get("edge_ids") or []) if v
        )),
    )


def order_signature(candidate: Mapping[str, Any]) -> dict[str, Sequence]:
    """Ordine *emesso* delle liste, per il controllo ORDER_MISMATCH."""
    return {
        "node_ids": list(candidate.get("node_ids") or []),
        "graph_path": list(candidate.get("graph_path") or []),
        "biomarkers": [norm_identifier(b.get("id")) for b in candidate.get("biomarkers") or []],
        "document_identifiers": [
            (norm_identifier(d.get("pmid")) or norm_identifier(d.get("nct")), norm_identifier(d.get("scope")))
            for d in candidate.get("document_identifiers") or []
        ],
    }
