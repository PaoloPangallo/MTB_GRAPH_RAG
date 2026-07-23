"""Verifica documentale delle tre fonti del batch clinico/preclinico.

E' l'unico script della fase che tocca la rete, e la tocca in lettura. Il full
text viene interrogato in memoria e non viene mai scritto su disco: restano
l'hash del documento, i locator con il loro tipo di match, la posizione, lo span
hash e un estratto breve.

Senza `--allow-network` ogni locator resta `not_verified`. Non e' una modalita'
degradata da nascondere: e' quello che deve succedere quando la fonte non e'
stata davvero consultata, ed e' anche la ragione per cui la suite di test puo'
girare offline senza mentire su cio' che e' stato verificato.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.mtb_evidence.evaluation.clinical_preclinical_findings import (  # noqa: E402
    FINDINGS,
    SourceFinding,
)
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_review import (  # noqa: E402
    MATCH_NOT_VERIFIED,
    REVIEW_VERSION,
    VERIFIED_MATCH_TYPES,
    normalize,
    span_hash,
)
from benchmarks.mtb_evidence.evaluation.scripts.verify_source_locators import (  # noqa: E402
    DEFAULT_MAX_GAP,
    EFETCH,
    USER_AGENT,
    _clean,
    fetch_pmc_document,
    locate_query,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")
DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")

EXCERPT_RADIUS = 90


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="consulta PMC e PubMed; senza, nessun locator viene verificato",
    )
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def fetch_abstract(pmid: str, *, timeout: int = 45) -> tuple[str, str, list[str]]:
    """`(testo, hash del testo, etichette di sezione)` dell'abstract PubMed.

    L'hash e' calcolato sul testo normalizzato dell'abstract e non sulla risposta
    grezza: e' cosi' che la priority curation lo aveva registrato, e confrontarli
    ha senso solo se sono la stessa cosa.
    """
    query = urllib.parse.urlencode({"db": "pubmed", "id": pmid, "retmode": "xml"})
    request = urllib.request.Request(f"{EFETCH}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return "", "", []

    parts: list[str] = []
    labels: list[str] = []
    for node in root.iter("AbstractText"):
        label = node.get("Label") or node.get("NlmCategory") or ""
        if label:
            labels.append(label)
        parts.append(_clean(" ".join(node.itertext())))

    text = _clean(" ".join(part for part in parts if part))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""
    return text, digest, sorted(set(labels))


def excerpt(text: str, offset: int | None, query: str) -> str:
    if offset is None:
        return ""
    cleaned = _clean(text)
    end = offset + len(_clean(query))
    left = max(0, offset - EXCERPT_RADIUS)
    right = min(len(cleaned), end + EXCERPT_RADIUS)
    return ("…" if left else "") + cleaned[left:right].strip() + ("…" if right < len(cleaned) else "")


def verify_finding(
    finding: SourceFinding,
    *,
    allow_network: bool,
    stored_abstract_hash: str,
    access_date: str,
) -> dict[str, Any]:
    """Verifica una fonte e i suoi locator, senza conservare il documento."""
    text = ""
    document_hash = ""
    labels: list[str] = []
    systems: list[str] = []
    limitations = list(finding.limitations)
    abstract_hash_matches: bool | None = None

    if allow_network:
        if finding.pmc_id:
            pmc_numeric = finding.pmc_id.removeprefix("PMC")
            text, document_hash, labels = fetch_pmc_document(pmc_numeric)
            systems.append("pmc_efetch")
        else:
            text, document_hash, labels = fetch_abstract(finding.pmid)
            systems.append("pubmed_efetch")
            if stored_abstract_hash:
                abstract_hash_matches = document_hash == stored_abstract_hash
                if abstract_hash_matches is False:
                    limitations.append(
                        "l'hash dell'abstract recuperato non coincide con quello "
                        "registrato dalla priority curation"
                    )
    else:
        limitations.append("rete non abilitata: nessun locator verificato sulla fonte")

    locators: list[dict[str, Any]] = []
    for locator in finding.locators:
        if not text:
            locators.append(
                {
                    **locator.as_dict(),
                    "match_type": MATCH_NOT_VERIFIED,
                    "verified": False,
                    "char_offset": None,
                    "max_gap": 0,
                    "span_hash": "",
                    "excerpt": "",
                }
            )
            continue

        match_type, offset, gap = locate_query(
            locator.query,
            text,
            labels=labels,
            section_hint=locator.section_hint,
            max_gap=DEFAULT_MAX_GAP,
        )
        found = excerpt(text, offset, locator.query)
        locators.append(
            {
                **locator.as_dict(),
                "match_type": match_type,
                "verified": match_type in VERIFIED_MATCH_TYPES,
                "char_offset": offset,
                "max_gap": gap,
                # L'impronta e' della citazione normalizzata, non dell'estratto:
                # e' cio' che permette di riconoscere la stessa citazione anche
                # se il raggio dell'estratto cambia.
                "span_hash": span_hash(locator.query) if offset is not None else "",
                "excerpt": found,
            }
        )

    verified = [row for row in locators if row["verified"]]
    return {
        "profile_unit_id": finding.parent_unit_id,
        "canonical_source_id": finding.canonical_source_id,
        "source_identifier": f"PMID:{finding.pmid}",
        "pmid": finding.pmid,
        "pmc_id": finding.pmc_id,
        "availability": finding.availability,
        "systems_consulted": systems,
        "access_date": access_date,
        "document_hash": document_hash,
        "stored_abstract_hash": stored_abstract_hash,
        "abstract_hash_matches": abstract_hash_matches,
        "full_text_stored": False,
        "full_text_redistributed": False,
        "sections_located": sorted({locator.section_hint for locator in finding.locators}),
        "figures_and_tables_located": labels,
        "locator_count": len(locators),
        "locators_verified": len(verified),
        "locators_not_verified": len(locators) - len(verified),
        "match_type_counts": _count(locators),
        "locators": locators,
        "limitations": limitations,
        "review_version": REVIEW_VERSION,
    }


def _count(locators: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in locators:
        counts[row["match_type"]] = counts.get(row["match_type"], 0) + 1
    return dict(sorted(counts.items()))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    access_date = (args.timestamp or datetime.now(timezone.utc).isoformat())[:10]

    stored = {
        str(row["profile_unit_id"]): str(row.get("abstract_sha256") or "")
        for row in read_jsonl(args.curation_dir / "source_access_manifest.jsonl")
    }

    rows = [
        verify_finding(
            finding,
            allow_network=args.allow_network,
            stored_abstract_hash=stored.get(finding.parent_unit_id, ""),
            access_date=access_date,
        )
        for finding in FINDINGS
    ]
    rows.sort(key=lambda row: row["profile_unit_id"])
    write_jsonl(args.output / "source_access_verification.jsonl", rows)

    for row in rows:
        print(
            f"{row['profile_unit_id']}: {row['availability']} | "
            f"locator {row['locators_verified']}/{row['locator_count']} verificati | "
            f"{json.dumps(row['match_type_counts'])}"
        )
        for limitation in row["limitations"]:
            print(f"    limite: {limitation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
