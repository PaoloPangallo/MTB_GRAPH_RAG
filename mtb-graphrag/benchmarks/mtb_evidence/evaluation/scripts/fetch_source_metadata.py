"""Metadati bibliografici delle fonti, da registro ufficiale.

Unico punto del corpus che tocca la rete, ed e' deliberatamente **opt-in**: va
lanciato a mano e scrive una cache. Tutto il resto della pipeline legge la cache,
mai la rete, cosi' che gli artefatti restino deterministici e i test offline.

Vengono richiesti soltanto metadati che il registro *afferma*: titolo, rivista,
anno, tipi di pubblicazione. Nessun qualificatore clinico viene derivato qui.
Setting, linea di terapia, stadio e popolazione richiedono la lettura della fonte
da parte di una persona, e restano `unknown` finche' quella lettura non avviene:
dedurli dal titolo produrrebbe un profilo plausibile e non verificato, che e' la
cosa peggiore che questo corpus possa contenere.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_jsonl,
)

METADATA_VERSION = "source_metadata/1.0"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
USER_AGENT = "mtb-graphrag-benchmark/1.0 (research; contact via repository)"
BATCH_SIZE = 100


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="senza questo flag non viene aperta nessuna connessione",
    )
    return parser.parse_args(argv)


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def fetch_pubmed_summaries(pmids: list[str], *, timeout: int = 30) -> dict[str, dict[str, Any]]:
    """Interroga E-utilities e restituisce i soli campi asseriti dal registro."""
    found: dict[str, dict[str, Any]] = {}
    for batch in _chunks(sorted(pmids), BATCH_SIZE):
        query = urllib.parse.urlencode(
            {"db": "pubmed", "id": ",".join(batch), "retmode": "json"}
        )
        request = urllib.request.Request(
            f"{ESUMMARY}?{query}", headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = payload.get("result") or {}
        accessed = datetime.now(timezone.utc).date().isoformat()
        for pmid in batch:
            record = result.get(pmid)
            if not isinstance(record, dict):
                continue
            found[pmid] = {
                "identifier_key": f"pmid:{pmid}",
                "pmid": pmid,
                "title": str(record.get("title") or "").strip(),
                "journal": str(record.get("fulljournalname") or "").strip(),
                "publication_year": str(record.get("pubdate") or "")[:4],
                "publication_types": sorted(
                    str(item) for item in (record.get("pubtype") or []) if str(item)
                ),
                "retrieved_from": "pubmed_esummary",
                "access_date": accessed,
                "locator": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "metadata_version": METADATA_VERSION,
            }
        # Cortesia verso il registro pubblico: nessuna chiave API in uso.
        time.sleep(0.4)
    return found


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    entries = list(read_jsonl(args.inventory))
    pmids = sorted({pmid for entry in entries for pmid in entry.get("pmids") or []})

    cached: dict[str, dict[str, Any]] = {}
    if args.cache.is_file():
        for row in read_jsonl(args.cache):
            cached[str(row.get("identifier_key"))] = row

    missing = [pmid for pmid in pmids if f"pmid:{pmid}" not in cached]
    print(f"PMID nell'inventario: {len(pmids)} | gia' in cache: {len(pmids) - len(missing)}")

    if not missing:
        print("cache completa: nessuna richiesta di rete")
        return 0
    if not args.allow_network:
        print(f"{len(missing)} PMID mancanti. Rilancia con --allow-network per recuperarli.")
        return 1

    fetched = fetch_pubmed_summaries(missing)
    print(f"metadati recuperati: {len(fetched)} / {len(missing)}")
    for pmid in missing:
        if pmid not in fetched:
            print(f"  non risolto dal registro: {pmid}")

    for record in fetched.values():
        cached[record["identifier_key"]] = record

    rows = [cached[key] for key in sorted(cached)]
    write_jsonl(args.cache, rows)
    print(f"cache scritta: {args.cache} ({len(rows)} record)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
