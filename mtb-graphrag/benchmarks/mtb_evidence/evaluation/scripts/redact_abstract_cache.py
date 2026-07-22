"""Riduce la cache degli abstract a estratti brevi, hash e locator.

Gli abstract di PubMed sono in larga parte coperti da copyright dell'editore.
Il vincolo dichiarato per questo corpus e' di registrare identificatore, locator
e hash **senza redistribuire testi protetti lunghi**, e la cache completa lo
violerebbe.

Qui resta cio' che serve a un revisore per orientarsi e a un verificatore per
controllare: etichette delle sezioni, termini MeSH, tipi di pubblicazione, hash
del testo, e un estratto **limitato** attorno a ciascuno span effettivamente
rilevato. Il testo completo resta una cache di lavoro locale, rigenerabile con
`fetch_priority_abstracts.py`, e non entra nel repository.

L'hash e' cio' che rende l'operazione onesta: chi rifa' il fetch puo' verificare
di avere sotto gli occhi lo stesso testo su cui le decisioni sono state prese.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.mtb_evidence.evaluation.source_curation import detect  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_jsonl,
)

REDACTED_VERSION = "source_abstract_spans/1.0"
EXCERPT_RADIUS = 110
MAX_EXCERPTS = 12


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _excerpt(text: str, start: int, end: int) -> str:
    left = max(0, start - EXCERPT_RADIUS)
    right = min(len(text), end + EXCERPT_RADIUS)
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(text) else ""
    return f"{prefix}{text[left:right].strip()}{suffix}"


def redact(record: dict[str, Any]) -> dict[str, Any]:
    sections = {
        str(item.get("label")): str(item.get("text") or "")
        for item in record.get("abstract_sections") or []
    }
    excerpts: list[dict[str, Any]] = []
    for item in detect(record)[:MAX_EXCERPTS]:
        text = sections.get(item.section_label, "")
        if not text:
            continue
        excerpts.append(
            {
                "dimension": item.dimension,
                "value": item.value,
                "pattern_id": item.pattern_id,
                "section_label": item.section_label,
                "char_start": item.start,
                "char_end": item.end,
                "matched_text": item.matched_text,
                "excerpt": _excerpt(text, item.start, item.end),
            }
        )

    return {
        "identifier_key": record["identifier_key"],
        "pmid": record["pmid"],
        "title": record.get("title", ""),
        "section_labels": [str(item.get("label")) for item in record.get("abstract_sections") or []],
        "abstract_available": bool(record.get("abstract_available")),
        "abstract_sha256": record.get("abstract_sha256", ""),
        "abstract_length": record.get("abstract_length", 0),
        "mesh_terms": list(record.get("mesh_terms") or []),
        "publication_types": list(record.get("publication_types") or []),
        "retrieved_from": record.get("retrieved_from", ""),
        "locator": record.get("locator", ""),
        "access_date": record.get("access_date", ""),
        "span_excerpts": excerpts,
        "redaction_note": (
            "estratti limitati attorno agli span rilevati; testo completo non "
            "redistribuito, rigenerabile con fetch_priority_abstracts.py e "
            "verificabile con abstract_sha256"
        ),
        "cache_version": REDACTED_VERSION,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.cache.is_file():
        print(f"cache di lavoro assente: {args.cache}")
        return 1
    rows = [redact(row) for row in read_jsonl(args.cache)]
    rows.sort(key=lambda item: item["identifier_key"])
    write_jsonl(args.output, rows)
    total = sum(len(row["span_excerpts"]) for row in rows)
    print(f"record redatti: {len(rows)} | estratti conservati: {total}")
    print(f"scritto: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
