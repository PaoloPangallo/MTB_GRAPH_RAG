"""Risoluzione bibliografica dei PMID tramite l'API ufficiale NCBI E-utilities.

Vincoli rispettati:

* si interroga **solo** l'endpoint ufficiale ``eutils.ncbi.nlm.nih.gov``;
* si richiede **solo metadata** (``esummary``): titolo, tipi di pubblicazione,
  DOI, PMCID, data. Nessun testo integrale viene scaricato o committato;
* il rate limit pubblico NCBI è 3 richieste/secondo senza API key: il client
  attende almeno ``MIN_INTERVAL`` fra due richieste e usa richieste in batch
  (fino a ``BATCH_SIZE`` identificatori ciascuna) per ridurne il numero;
* ogni richiesta è registrata con data, endpoint, query, stato e conteggio dei
  risultati, in modo che la run sia ricostruibile.

La cache documentale locale è consultata **prima** della rete: un PMID già
presente non viene richiesto di nuovo.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
TOOL = "mtb-graphrag-evaluation"

#: NCBI consente 3 richieste/secondo senza API key; teniamo un margine.
MIN_INTERVAL = 0.40
BATCH_SIZE = 200
TIMEOUT = 30
MAX_RETRIES = 2

# Stati di risoluzione
RESOLVED = "PMID_RESOLVED_METADATA_ONLY"
DOCUMENT_AVAILABLE = "PMID_DOCUMENT_AVAILABLE"
NOT_FOUND = "PMID_NOT_FOUND"
UNRESOLVED_TRANSPORT = "PMID_UNRESOLVED_TRANSPORT_ERROR"


@dataclass
class RequestLogEntry:
    at: str
    endpoint: str
    query: str
    status: int | str
    returned: int
    attempt: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class PubMedRecord:
    pmid: str
    status: str
    title: str | None = None
    journal: str | None = None
    pubdate: str | None = None
    publication_types: list[str] = field(default_factory=list)
    doi: str | None = None
    pmcid: str | None = None
    retraction_signals: list[str] = field(default_factory=list)
    source: str = "ncbi_esummary"

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


#: Tipi di pubblicazione che segnalano una ritrattazione o una correzione.
#: Provengono dal vocabolario ufficiale MeSH dei publication type.
_RETRACTION_TYPES = {
    "Retracted Publication",
    "Retraction of Publication",
    "Published Erratum",
    "Expression of Concern",
    "Corrected and Republished Article",
}


class PubMedResolver:
    """Client E-utilities con rate limit, retry di trasporto e log delle richieste."""

    def __init__(self, cache_path: Path | None = None, email: str | None = None):
        self.cache_path = cache_path
        self.email = email
        self.log: list[RequestLogEntry] = []
        self._last_call = 0.0
        self._cache: dict[str, dict[str, Any]] = {}
        if cache_path and cache_path.exists():
            self._cache = json.loads(cache_path.read_text(encoding="utf-8"))

    def _throttle(self) -> None:
        delta = time.monotonic() - self._last_call
        if delta < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - delta)
        self._last_call = time.monotonic()

    def _request(self, pmids: list[str]) -> dict[str, Any] | None:
        params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json", "tool": TOOL}
        if self.email:
            params["email"] = self.email
        url = f"{ESUMMARY}?{urllib.parse.urlencode(params)}"
        query = f"db=pubmed&id=<{len(pmids)} ids>&retmode=json"
        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            try:
                with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                self.log.append(RequestLogEntry(
                    at=datetime.now(timezone.utc).isoformat(), endpoint=ESUMMARY,
                    query=query, status=response.status,
                    returned=len(payload.get("result", {}).get("uids", [])), attempt=attempt,
                ))
                return payload
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as error:
                self.log.append(RequestLogEntry(
                    at=datetime.now(timezone.utc).isoformat(), endpoint=ESUMMARY,
                    query=query, status=f"{type(error).__name__}: {error}",
                    returned=0, attempt=attempt,
                ))
                if attempt < MAX_RETRIES:
                    time.sleep(2.0 * attempt)
        return None

    @staticmethod
    def _parse(pmid: str, entry: dict[str, Any]) -> PubMedRecord:
        doi = pmcid = None
        for article_id in entry.get("articleids") or []:
            kind = (article_id.get("idtype") or "").lower()
            value = article_id.get("value")
            if kind == "doi" and value:
                doi = value
            elif kind == "pmc" and value:
                pmcid = value
        pub_types = [str(t) for t in (entry.get("pubtype") or [])]
        return PubMedRecord(
            pmid=pmid,
            status=RESOLVED,
            title=entry.get("title"),
            journal=entry.get("fulljournalname") or entry.get("source"),
            pubdate=entry.get("pubdate"),
            publication_types=pub_types,
            doi=doi,
            pmcid=pmcid,
            retraction_signals=sorted(set(pub_types) & _RETRACTION_TYPES),
        )

    def resolve_many(self, pmids: Iterable[str]) -> dict[str, PubMedRecord]:
        wanted = sorted({p for p in pmids if p})
        out: dict[str, PubMedRecord] = {}
        pending: list[str] = []
        for pmid in wanted:
            cached = self._cache.get(pmid)
            if cached:
                out[pmid] = PubMedRecord(**cached)
            else:
                pending.append(pmid)

        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start:start + BATCH_SIZE]
            payload = self._request(batch)
            if payload is None:
                for pmid in batch:
                    out[pmid] = PubMedRecord(pmid=pmid, status=UNRESOLVED_TRANSPORT)
                continue
            result = payload.get("result") or {}
            for pmid in batch:
                entry = result.get(pmid)
                if not entry or entry.get("error"):
                    out[pmid] = PubMedRecord(pmid=pmid, status=NOT_FOUND)
                else:
                    out[pmid] = self._parse(pmid, entry)
                self._cache[pmid] = out[pmid].to_dict()

        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=1, sort_keys=True),
                encoding="utf-8",
            )
        return out

    def log_rows(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.log]
