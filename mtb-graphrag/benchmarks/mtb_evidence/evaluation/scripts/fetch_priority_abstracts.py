"""Recupera gli abstract delle fonti prioritarie da PubMed.

Secondo e ultimo punto del corpus che tocca la rete, anch'esso **opt-in**. Scrive
una cache; tutto cio' che sta a valle legge la cache e resta deterministico e
offline.

Viene salvato il testo dell'abstract con le sue sezioni etichettate, perche' la
sezione e' il locator: dire che «linea di terapia = seconda» e' verificabile solo
se si sa che l'affermazione viene da METHODS e non dalla discussione. Insieme
all'abstract si salva un hash del testo, cosi' che una revisione futura possa
accorgersi se la fonte e' cambiata sotto i piedi.

Non viene salvato il full text: non e' redistribuibile, e per le decisioni di
questa fase l'abstract con le sue sezioni e' cio' che serve.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
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

ABSTRACT_CACHE_VERSION = "source_abstract/1.0"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
USER_AGENT = "mtb-graphrag-benchmark/1.0 (research; contact via repository)"
BATCH_SIZE = 40
_WHITESPACE = re.compile(r"\s+")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority-units", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    return parser.parse_args(argv)


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _clean(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _parse_article(article: ET.Element) -> dict[str, Any] | None:
    pmid_node = article.find(".//MedlineCitation/PMID")
    if pmid_node is None or not pmid_node.text:
        return None
    pmid = pmid_node.text.strip()

    sections: list[dict[str, str]] = []
    for node in article.findall(".//Abstract/AbstractText"):
        label = (node.get("Label") or node.get("NlmCategory") or "UNLABELLED").upper()
        text = _clean("".join(node.itertext()))
        if text:
            sections.append({"label": label, "text": text})

    full = " ".join(section["text"] for section in sections)
    title_node = article.find(".//ArticleTitle")
    title = _clean("".join(title_node.itertext())) if title_node is not None else ""

    mesh = sorted(
        {
            _clean("".join(node.itertext()))
            for node in article.findall(".//MeshHeading/DescriptorName")
        }
    )
    types = sorted(
        {
            _clean("".join(node.itertext()))
            for node in article.findall(".//PublicationTypeList/PublicationType")
        }
    )

    return {
        "identifier_key": f"pmid:{pmid}",
        "pmid": pmid,
        "title": title,
        "abstract_sections": sections,
        "abstract_text": full,
        "abstract_available": bool(full),
        "abstract_sha256": hashlib.sha256(full.encode("utf-8")).hexdigest() if full else "",
        "abstract_length": len(full),
        "mesh_terms": mesh,
        "publication_types": types,
        "retrieved_from": "pubmed_efetch",
        "locator": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "access_date": datetime.now(timezone.utc).date().isoformat(),
        "cache_version": ABSTRACT_CACHE_VERSION,
    }


def fetch_abstracts(pmids: list[str], *, timeout: int = 40) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for batch in _chunks(sorted(pmids), BATCH_SIZE):
        query = urllib.parse.urlencode(
            {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}
        )
        request = urllib.request.Request(
            f"{EFETCH}?{query}", headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            root = ET.fromstring(response.read().decode("utf-8"))
        for article in root.findall(".//PubmedArticle"):
            parsed = _parse_article(article)
            if parsed:
                found[parsed["pmid"]] = parsed
        time.sleep(0.4)
    return found


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    units = list(read_jsonl(args.priority_units))
    pmids = sorted({pmid for unit in units for pmid in unit.get("pmids") or []})

    cached: dict[str, dict[str, Any]] = {}
    if args.cache.is_file():
        for row in read_jsonl(args.cache):
            cached[str(row.get("identifier_key"))] = row

    missing = [pmid for pmid in pmids if f"pmid:{pmid}" not in cached]
    print(f"PMID prioritari: {len(pmids)} | gia' in cache: {len(pmids) - len(missing)}")

    if not missing:
        print("cache completa: nessuna richiesta di rete")
        return 0
    if not args.allow_network:
        print(f"{len(missing)} abstract mancanti. Rilancia con --allow-network.")
        return 1

    fetched = fetch_abstracts(missing)
    without_abstract = [
        pmid for pmid, record in fetched.items() if not record["abstract_available"]
    ]
    print(f"record recuperati: {len(fetched)} / {len(missing)}")
    print(f"senza abstract nel record: {len(without_abstract)}")
    for pmid in missing:
        if pmid not in fetched:
            print(f"  non risolto dal registro: {pmid}")

    for record in fetched.values():
        cached[record["identifier_key"]] = record

    write_jsonl(args.cache, [cached[key] for key in sorted(cached)])
    print(f"cache scritta: {args.cache} ({len(cached)} record)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
