"""Grammatica condivisa fra renderer e verificatori strutturali.

Questo modulo sta deliberatamente **fuori** da ``rendering/``: se il
verificatore importasse il renderer, "il report è corretto" significherebbe
soltanto "il renderer ha fatto ciò che fa", cioè una tautologia. Qui entrambi
dipendono da un contratto neutrale e nessuno dei due è l'autorità sull'altro.

Se renderer e verificatore divergono sull'interpretazione della grammatica, il
verificatore fallisce — ed è l'esito corretto: significa che l'artefatto non è
più analizzabile con le regole dichiarate.
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping

from backend.pipeline.control.contracts import OriginalClaim

#: Identificatori citabili. Sono ancore verificabili in modo esatto, non
#: euristico: un PMID o un NCT o è nell'insieme atteso o non c'è.
PMID_RE = re.compile(r"PMID:\s*(\d{5,9})")
NCT_RE = re.compile(r"\b(NCT\d{8})\b")

#: Token che, comparendo nel testo, devono corrispondere a un'entità dichiarata
#: nei record attesi. Parole capitalizzate o farmaco-simili.
_ENTITY_CANDIDATE_RE = re.compile(r"\b([A-Z][A-Za-z0-9-]{3,}|[a-z]+(?:tinib|mab|ciclib|parib|zomib))\b")

#: Vocabolario di servizio del renderer: connettivi, intestazioni e termini
#: clinici generici che non sono entità e non vanno confrontati con i record.
BOILERPLATE_TOKENS = frozenset({
    "caso", "evidenze", "evidenza", "candidate", "documentalmente", "supportate",
    "come", "formulate", "dopo", "contestualizzazione", "contesto", "della",
    "fonte", "supporto", "documentale", "applicabilità", "richiesto", "claim",
    "contestualizzata", "dalla", "molecular", "tumor", "board", "mtb", "report",
    "revisione", "revisionato", "raccomandazione", "terapeutica", "compatibili",
    "compatibile", "indeterminata", "indeterminate", "non", "restano", "sono",
    "discutere", "soggette", "presentate", "candidate", "terapeutiche", "per",
    "caso", "nessuna", "provenienza", "sufficiente", "generare", "fattuali",
    "richiesta", "oncologo", "disponibile", "assente", "prerequisiti",
    "costituisce", "organizza", "disponibile", "deve", "essere", "comunque",
    "dichiarato", "sezione", "trial", "eleggibilità", "verificata",
})

#: Formulazioni che presenterebbero un'evidenza come decisione clinica. Il
#: report è un artefatto destinato alla revisione del MTB, non una prescrizione.
BANNED_RECOMMENDATION_PHRASES = frozenset({
    "terapia raccomandata",
    "terapia indicata",
    "paziente eleggibile",
    "opzione applicabile",
    "trattamento raccomandato",
})


def claim_text(claim: OriginalClaim) -> str:
    """Forma canonica di una claim resa. Unico punto di verità."""
    return f"{claim.subject} — {claim.relation} — {claim.object} ({claim.context})."


def claim_key(claim: OriginalClaim) -> str:
    """Chiave normalizzata usata per cercare una claim dentro un testo."""
    return " ".join(
        part.strip().casefold()
        for part in (claim.subject, claim.relation, claim.object)
        if part and part.strip()
    )


def citation_token(source_id: str | None) -> str:
    return f"[{source_id}]" if source_id else "[fonte assente]"


def extract_citations(text: str) -> frozenset[str]:
    """Estrae gli identificatori citati, normalizzati come ``PMID:n``/``NCTn``."""
    pmids = {f"PMID:{match}" for match in PMID_RE.findall(text)}
    ncts = set(NCT_RE.findall(text))
    return frozenset(pmids | ncts)


def claim_is_present(text: str, claim: OriginalClaim) -> bool:
    """Una claim è presente se soggetto e oggetto compaiono nella stessa riga.

    Il confronto è per riga e non sull'intero testo: due claim distinte che
    condividono il soggetto non devono coprirsi a vicenda.
    """
    subject = (claim.subject or "").strip().casefold()
    obj = (claim.object or "").strip().casefold()
    if not subject:
        return False
    for line in text.splitlines():
        lowered = line.casefold()
        if subject in lowered and (not obj or obj in lowered):
            return True
    return False


def lexicon_for(claim: OriginalClaim) -> frozenset[str]:
    """Token che il renderer è autorizzato a emettere per un record."""
    parts = (
        claim.subject, claim.relation, claim.object, claim.context,
        claim.source_id or "", claim.evidence_level or "",
    )
    tokens = {
        token.casefold()
        for part in parts
        for token in re.split(r"[^A-Za-z0-9:-]+", part or "")
        if len(token) >= 3
    }
    return frozenset(tokens)


def entities_for(claim: OriginalClaim) -> frozenset[str]:
    """Entità strutturate del record: farmaci, biomarker, tipo di relazione.

    A differenza del lessico, sono confrontabili in modo esatto: è su queste
    che poggiano i controlli bloccanti, non sull'euristica lessicale.
    """
    values = (claim.subject, claim.object, claim.relation)
    return frozenset(
        value.strip().casefold() for value in values if value and value.strip()
    )


def candidate_entities(text: str) -> frozenset[str]:
    """Token del testo che si presentano come entità e vanno giustificati."""
    found = {match.casefold() for match in _ENTITY_CANDIDATE_RE.findall(text)}
    return frozenset(token for token in found if token not in BOILERPLATE_TOKENS)


def banned_phrases_in(text: str) -> tuple[str, ...]:
    lowered = text.casefold()
    return tuple(sorted(phrase for phrase in BANNED_RECOMMENDATION_PHRASES if phrase in lowered))


def asserted_lines(text: str) -> tuple[str, ...]:
    """Righe che asseriscono una tripla, cioè le voci di elenco del report."""
    return tuple(
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("- ") and "—" in line
    )


def count_in_header(text: str, pattern: str) -> int | None:
    """Legge un conteggio dichiarato nell'intestazione, se presente."""
    match = re.search(pattern, text)
    return int(match.group(1)) if match else None


def tokens_of(values: Iterable[str]) -> frozenset[str]:
    return frozenset(value.casefold() for value in values if value)


def entity_appears(text: str, entity: str) -> bool:
    return entity.casefold() in text.casefold()


def resolve_citation_owner(
    citation: str, by_citation: Mapping[str, str]
) -> str | None:
    return by_citation.get(citation)
