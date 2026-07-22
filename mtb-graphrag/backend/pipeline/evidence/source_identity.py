"""Identita' normalizzata di una fonte bibliografica.

Il repository degli statement indicizza per PMID, DOI e NCT usando la
normalizzazione gia' validata dall'audit del grafo. Qui serve qualcosa di piu':
decidere **quando due riferimenti sono la stessa fonte**, che e' una domanda
diversa dal normalizzare un identificatore.

La regola e' una sola e non ammette eccezioni: due riferimenti sono la stessa
fonte se e solo se **condividono almeno un identificatore controllato**
normalizzato (PMID, DOI, NCT o altro identificatore di registro). Il titolo non
partecipa mai alla decisione.

Il motivo e' asimmetrico. Un falso negativo lascia due unita' separate che un
revisore puo' unire; un falso positivo fonde due studi diversi e propaga i
qualificatori clinici dell'uno sugli statement dell'altro, producendo una
qualificazione sbagliata che nessuna metrica a valle distingue da una giusta.
Poiche' la precisione conta piu' del recall, il titolo resta diagnostica.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ._normalize import normalize_nct, normalize_pmid, normalize_text

IDENTITY_VERSION = "source_identity/1.0"

# Tipi di identificatore, in ordine di preferenza per il canonical id.
PMID = "pmid"
DOI = "doi"
NCT = "nct"
OTHER = "other"

IDENTIFIER_PRIORITY = (PMID, DOI, NCT, OTHER)

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi.org/",
    "dx.doi.org/",
)
_DOI_LABEL = re.compile(r"^doi\s*:\s*", re.IGNORECASE)
_DOI_BODY = re.compile(r"^10\.\d{4,9}/\S+$")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class NormalizedDoi:
    """Un DOI nella forma canonica minuscola, senza prefisso risolutore.

    I DOI sono case-insensitive per specifica (ISO 26324): `10.1056/NEJMoa1713137`
    e `10.1056/nejmoa1713137` sono lo stesso oggetto. Trattarli come fonti diverse
    duplicherebbe la stessa pubblicazione nell'inventario.
    """

    raw: str
    text: str
    valid: bool
    reason: str = ""


def norm_doi(value: object) -> NormalizedDoi:
    """DOI canonico: prefisso risolutore rimosso, casefold, spazi collassati."""
    raw = "" if value is None else str(value)
    stripped = _WHITESPACE.sub("", raw.strip())
    if not stripped:
        return NormalizedDoi(raw=raw, text="", valid=False, reason="empty")

    stripped = _DOI_LABEL.sub("", stripped)
    lowered = stripped.casefold()
    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            stripped = stripped[len(prefix) :]
            break

    candidate = stripped.casefold().rstrip(".")
    if not candidate:
        return NormalizedDoi(raw=raw, text="", valid=False, reason="empty")
    if not _DOI_BODY.match(candidate):
        return NormalizedDoi(raw=raw, text=candidate, valid=False, reason="malformed")
    return NormalizedDoi(raw=raw, text=candidate, valid=True)


def norm_doi_set(values: object) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        candidates: list[object] = [values]
    else:
        try:
            candidates = list(values)  # type: ignore[arg-type]
        except TypeError:
            candidates = [values]
    return tuple(sorted({item.text for item in map(norm_doi, candidates) if item.valid}))


def normalize_identifier(kind: str, value: object) -> tuple[str, bool, str]:
    """Normalizza un identificatore del tipo indicato.

    Restituisce `(testo, valido, motivo)`. Un identificatore di tipo sconosciuto
    viene solo ripulito: non si inventa una regola di validita' per un registro
    che non conosciamo.
    """
    if kind == PMID:
        from benchmarks.mtb_evidence.pilot.audit_lib.normalize import norm_pmid

        normalized = norm_pmid(value)
        return normalized.text, normalized.valid, normalized.reason
    if kind == DOI:
        normalized_doi = norm_doi(value)
        return normalized_doi.text, normalized_doi.valid, normalized_doi.reason
    if kind == NCT:
        from benchmarks.mtb_evidence.pilot.audit_lib.normalize import norm_nct

        normalized_nct = norm_nct(value)
        return normalized_nct.text, normalized_nct.valid, normalized_nct.reason
    text = normalize_text(value)
    return text, bool(text), "" if text else "empty"


@dataclass(frozen=True)
class SourceIdentifier:
    """Un identificatore singolo, con il valore originale sempre conservato."""

    kind: str
    raw: str
    text: str
    valid: bool
    reason: str = ""

    @property
    def key(self) -> str:
        """Chiave di equivalenza fra fonti: tipo piu' forma normalizzata."""
        return f"{self.kind}:{self.text}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "raw": self.raw,
            "text": self.text,
            "valid": self.valid,
            "reason": self.reason,
        }


def build_identifier(kind: str, value: object) -> SourceIdentifier:
    raw = "" if value is None else str(value)
    text, valid, reason = normalize_identifier(kind, value)
    return SourceIdentifier(kind=kind, raw=raw, text=text, valid=valid, reason=reason)


@dataclass
class SourceIdentity:
    """Una fonte, potenzialmente nominata da piu' identificatori.

    `titles` esiste per la diagnostica e la revisione umana. Non entra mai nella
    decisione di fusione: due fonti con lo stesso titolo restano distinte se non
    condividono un identificatore.
    """

    identifiers: tuple[SourceIdentifier, ...] = ()
    titles: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    unresolved: tuple[SourceIdentifier, ...] = ()

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(sorted({item.key for item in self.identifiers if item.valid}))

    def values(self, kind: str) -> tuple[str, ...]:
        return tuple(
            sorted({item.text for item in self.identifiers if item.valid and item.kind == kind})
        )

    @property
    def pmids(self) -> tuple[str, ...]:
        return self.values(PMID)

    @property
    def dois(self) -> tuple[str, ...]:
        return self.values(DOI)

    @property
    def ncts(self) -> tuple[str, ...]:
        return self.values(NCT)

    @property
    def others(self) -> tuple[str, ...]:
        return self.values(OTHER)

    @property
    def canonical_source_id(self) -> str:
        """Identificatore canonico deterministico.

        Si sceglie il tipo piu' alto in `IDENTIFIER_PRIORITY` fra quelli
        disponibili, e all'interno del tipo il valore minore in ordine
        lessicografico. Non dipende dall'ordine di inserimento: due costruzioni
        della stessa fonte producono la stessa stringa.
        """
        for kind in IDENTIFIER_PRIORITY:
            values = self.values(kind)
            if values:
                return f"{kind.upper()}:{values[0]}"
        if self.unresolved:
            worst = sorted(item.raw for item in self.unresolved)[0]
            return f"UNRESOLVED:{worst}"
        return "UNRESOLVED:"

    @property
    def is_resolved(self) -> bool:
        return bool(self.keys)

    @property
    def is_multi_identifier(self) -> bool:
        return len(self.keys) > 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_source_id": self.canonical_source_id,
            "identifiers": [item.as_dict() for item in sorted(self.identifiers, key=lambda i: (i.kind, i.text, i.raw))],
            "pmids": list(self.pmids),
            "dois": list(self.dois),
            "ncts": list(self.ncts),
            "other_identifiers": list(self.others),
            "titles": list(self.titles),
            "provenance": list(self.provenance),
            "unresolved": [item.as_dict() for item in sorted(self.unresolved, key=lambda i: (i.kind, i.raw))],
            "is_resolved": self.is_resolved,
            "is_multi_identifier": self.is_multi_identifier,
            "identity_version": IDENTITY_VERSION,
        }


def _merge_into(target: SourceIdentity, other: SourceIdentity) -> SourceIdentity:
    identifiers = {item.key: item for item in target.identifiers}
    for item in other.identifiers:
        identifiers.setdefault(item.key, item)
    unresolved = {(item.kind, item.raw): item for item in target.unresolved}
    for item in other.unresolved:
        unresolved.setdefault((item.kind, item.raw), item)
    return SourceIdentity(
        identifiers=tuple(sorted(identifiers.values(), key=lambda i: (i.kind, i.text, i.raw))),
        titles=tuple(sorted(set(target.titles) | set(other.titles))),
        provenance=tuple(sorted(set(target.provenance) | set(other.provenance))),
        unresolved=tuple(sorted(unresolved.values(), key=lambda i: (i.kind, i.raw))),
    )


class SourceIdentityResolver:
    """Raggruppa riferimenti in fonti, fondendo solo su identificatore condiviso.

    La fusione e' transitiva: se A condivide il PMID con B e B condivide il DOI
    con C, le tre sono la stessa fonte. E' il comportamento voluto, perche' ogni
    passaggio della catena e' giustificato da un identificatore controllato.
    """

    def __init__(self) -> None:
        self._groups: dict[str, SourceIdentity] = {}
        self._key_to_group: dict[str, str] = {}
        self._unresolved: list[SourceIdentity] = []
        self._counter = 0

    def add(
        self,
        *,
        identifiers: Iterable[SourceIdentifier],
        title: str = "",
        provenance: str = "",
    ) -> str:
        """Aggiunge un riferimento e restituisce l'id interno del gruppo."""
        items = tuple(identifiers)
        valid = tuple(item for item in items if item.valid)
        invalid = tuple(item for item in items if not item.valid)
        titles = (normalize_text(title),) if normalize_text(title) else ()
        provenances = (provenance,) if provenance else ()
        incoming = SourceIdentity(
            identifiers=valid, titles=titles, provenance=provenances, unresolved=invalid
        )

        if not valid:
            # Nessun identificatore controllato: la fonte resta isolata. Fonderla
            # per titolo sarebbe esattamente cio' che questo modulo rifiuta.
            self._counter += 1
            group_id = f"__unresolved_{self._counter}__"
            self._groups[group_id] = incoming
            return group_id

        touched = sorted({self._key_to_group[item.key] for item in valid if item.key in self._key_to_group})
        if not touched:
            self._counter += 1
            group_id = f"__group_{self._counter}__"
            self._groups[group_id] = incoming
        else:
            group_id = touched[0]
            merged = self._groups[group_id]
            for other in touched[1:]:
                merged = _merge_into(merged, self._groups.pop(other))
            merged = _merge_into(merged, incoming)
            self._groups[group_id] = merged

        for key, target in list(self._key_to_group.items()):
            if target in touched:
                self._key_to_group[key] = group_id
        for item in self._groups[group_id].identifiers:
            self._key_to_group[item.key] = group_id
        return group_id

    def identities(self) -> tuple[SourceIdentity, ...]:
        """Le fonti risolte, ordinate per canonical id: output deterministico."""
        return tuple(
            sorted(self._groups.values(), key=lambda identity: identity.canonical_source_id)
        )

    def group_of(self, identifier: SourceIdentifier) -> SourceIdentity | None:
        return self.resolve_key(identifier.key)

    def resolve_key(self, key: str) -> SourceIdentity | None:
        """La fonte che contiene `key` **allo stato attuale** delle fusioni.

        Va usata al posto dell'id restituito da `add`: quell'id puo' diventare
        stale, perche' un inserimento successivo che collega due gruppi ne fonde
        uno dentro l'altro e rimuove il perdente.
        """
        group_id = self._key_to_group.get(key)
        return self._groups.get(group_id) if group_id else None

    def group_id_of_key(self, key: str) -> str:
        """Id del gruppo corrente per `key`, vuoto se la chiave e' sconosciuta."""
        return self._key_to_group.get(key, "")


def identifiers_from_source_reference(reference: Mapping[str, Any]) -> list[SourceIdentifier]:
    """Estrae gli identificatori da un `source_reference` di EvidenceStatement.

    Il campo `source_type` dello statement dice gia' quale registro nomina la
    fonte; non si tenta di indovinare il tipo dal formato del valore.
    """
    source_type = normalize_text(reference.get("source_type"))
    external = reference.get("external_identifier")
    source_id = reference.get("source_id")

    kind = {
        "pubmed": PMID,
        "pmid": PMID,
        "doi": DOI,
        "clinicaltrials": NCT,
        "nct": NCT,
    }.get(source_type, OTHER)

    found: list[SourceIdentifier] = []
    if external not in (None, ""):
        found.append(build_identifier(kind, external))
    if not found and source_id not in (None, ""):
        # `source_id` ha forma "PUBMED:30892989": si tiene la parte dopo il primo
        # separatore, perche' il prefisso ripete il tipo gia' noto.
        text = str(source_id)
        payload = text.split(":", 1)[1] if ":" in text else text
        found.append(build_identifier(kind, payload))
    return found


def identifiers_from_trial_reference(reference: Mapping[str, Any]) -> list[SourceIdentifier]:
    value = reference.get("nct_id") or reference.get("external_identifier") or reference.get("trial_id")
    if value in (None, ""):
        return []
    return [build_identifier(NCT, value)]


def identifiers_from_profile(profile: Any) -> list[SourceIdentifier]:
    """Identificatori di un `SourceClinicalProfile` gia' revisionato."""
    found: list[SourceIdentifier] = []
    pmid = getattr(profile, "pmid", "") or ""
    if pmid:
        found.append(build_identifier(PMID, pmid))
    for nct in getattr(profile, "nct_ids", ()) or ():
        found.append(build_identifier(NCT, nct))
    doi = getattr(profile, "doi", "") or ""
    if doi:
        found.append(build_identifier(DOI, doi))
    return found


def titles_are_similar(left: object, right: object) -> bool:
    """Diagnostica soltanto: due titoli normalizzati coincidono?

    Deliberatamente esposta come funzione separata e mai chiamata dal resolver.
    Serve a segnalare a un revisore che due fonti *potrebbero* essere la stessa,
    non a deciderlo.
    """
    left_text = normalize_text(left)
    right_text = normalize_text(right)
    return bool(left_text) and left_text == right_text


__all__ = [
    "IDENTITY_VERSION",
    "PMID",
    "DOI",
    "NCT",
    "OTHER",
    "IDENTIFIER_PRIORITY",
    "NormalizedDoi",
    "norm_doi",
    "norm_doi_set",
    "normalize_identifier",
    "SourceIdentifier",
    "build_identifier",
    "SourceIdentity",
    "SourceIdentityResolver",
    "identifiers_from_source_reference",
    "identifiers_from_trial_reference",
    "identifiers_from_profile",
    "titles_are_similar",
    "normalize_pmid",
    "normalize_nct",
]
