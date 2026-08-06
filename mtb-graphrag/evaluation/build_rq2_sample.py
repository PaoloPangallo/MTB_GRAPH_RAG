"""Genera ``evaluation/gold/rq2_pmid_manual_review.csv`` (§9).

Uso::

    python -m evaluation.build_rq2_sample [--offline]

Campione stratificato deterministico di 50 coppie candidate–PMID. Le colonne di
annotazione umana restano **vuote**: nessun output automatico viene scritto in
esse.

Gli abstract sono richiesti **solo per i PMID del campione** e conservati come
anteprima troncata (``ABSTRACT_PREVIEW_CHARS`` caratteri), non come testo
integrale. Servono al revisore per giudicare la pertinenza; l'articolo completo
non viene scaricato né committato.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PAIRS = REPO_ROOT / "evaluation" / "rq2_pmid_associations" / "candidate_pmid_pairs.csv"
RESOLUTION = REPO_ROOT / "evaluation" / "rq2_pmid_associations" / "resolution_results.jsonl"
OUT = REPO_ROOT / "evaluation" / "gold" / "rq2_pmid_manual_review.csv"
SAMPLE_OUT = REPO_ROOT / "evaluation" / "rq2_pmid_associations" / "relevance_review_sample.csv"

EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
ABSTRACT_PREVIEW_CHARS = 400
SAMPLE_SIZE = 50

FIELDS = [
    "candidate_id", "pmid", "disease", "gene", "alteration", "biomarker",
    "intervention", "direction", "stratum", "title", "journal", "publication_types",
    "abstract_preview_redacted", "provenance_level", "sibling_drug_count",
    "automatic_resolution_status", "automatic_document_status",
    "automatic_retraction_signals",
    # Annotazione umana — deve restare vuota.
    "reviewer_relevant", "reviewer_direction", "reviewer_specificity", "reviewer_notes",
]


def fetch_abstract_previews(pmids: list[str]) -> dict[str, str]:
    """Anteprime di abstract per i soli PMID del campione (API ufficiale NCBI)."""
    out: dict[str, str] = {}
    if not pmids:
        return out
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml", "rettype": "abstract",
              "tool": "mtb-graphrag-evaluation"}
    url = f"{EFETCH}?{urllib.parse.urlencode(params)}"
    time.sleep(0.4)
    with urllib.request.urlopen(url, timeout=45) as response:
        root = ET.fromstring(response.read())
    for article in root.iter("PubmedArticle"):
        pmid_node = article.find(".//PMID")
        if pmid_node is None or not pmid_node.text:
            continue
        texts = [
            "".join(node.itertext()).strip()
            for node in article.iter("AbstractText")
        ]
        joined = " ".join(t for t in texts if t)
        if joined:
            preview = joined[:ABSTRACT_PREVIEW_CHARS]
            if len(joined) > ABSTRACT_PREVIEW_CHARS:
                preview += " […TRONCATO]"
            out[pmid_node.text.strip()] = preview
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    pairs = list(csv.DictReader(PAIRS.open(encoding="utf-8")))
    resolution = {
        json.loads(line)["pmid"]: json.loads(line)
        for line in RESOLUTION.read_text(encoding="utf-8").splitlines() if line.strip()
    }

    def resolved(row) -> dict:
        return resolution.get(row["pmid"], {})

    strata = OrderedDict([
        ("invalid_format", lambda r: r["syntactically_valid"] == "False"),
        ("retraction_or_erratum", lambda r: bool(resolved(r).get("retraction_signals"))),
        ("not_found", lambda r: resolved(r).get("resolution_status") == "PMID_NOT_FOUND"),
        ("document_available", lambda r: resolved(r).get("document_status") == "PMID_DOCUMENT_AVAILABLE"),
        ("candidate_level", lambda r: r["provenance_level"] == "PMID_CANDIDATE_LEVEL"),
        ("parent_level_single_drug", lambda r: r["provenance_level"] == "PMID_PARENT_LEVEL_ONLY"
         and int(r["sibling_drug_count"] or 1) == 1),
        ("parent_level_multi_drug", lambda r: r["provenance_level"] == "PMID_PARENT_LEVEL_ONLY"
         and int(r["sibling_drug_count"] or 1) > 1),
        ("sensitivity", lambda r: "sensitiv" in r["direction"].lower() or "response" in r["direction"].lower()),
        ("resistance", lambda r: "resistance" in r["direction"].lower()),
        ("does_not_support", lambda r: r["direction"].strip().lower() == "does not support"),
        ("with_pmcid", lambda r: bool(resolved(r).get("pmcid"))),
        ("no_pmcid", lambda r: not resolved(r).get("pmcid")),
        ("scope_evidence_record_only", lambda r: r["scopes"] == "evidence_record"),
        ("gene_only", lambda r: bool(r["gene"]) and not r["alteration"]),
    ])

    ordered = sorted(pairs, key=lambda r: (r["candidate_id"], r["pmid_raw"]))
    selected: "OrderedDict[str, tuple[dict, str]]" = OrderedDict()

    def take(name, predicate, quota):
        taken = 0
        for row in ordered:
            if taken >= quota:
                return
            key = f'{row["candidate_id"]}::{row["pmid_raw"]}'
            if key in selected:
                continue
            if predicate(row):
                selected[key] = (row, name)
                taken += 1

    # Gli strati rari per primi: devono comparire nel campione.
    for name in ("retraction_or_erratum", "not_found", "invalid_format", "document_available"):
        take(name, strata[name], 4)
    per_stratum = max(1, (SAMPLE_SIZE - len(selected)) // len(strata))
    for name, predicate in strata.items():
        take(name, predicate, per_stratum)
    for name, predicate in strata.items():
        if len(selected) >= SAMPLE_SIZE:
            break
        take(name, predicate, 1)

    chosen = list(selected.values())[:SAMPLE_SIZE]

    previews: dict[str, str] = {}
    if not args.offline:
        wanted = sorted({row["pmid"] for row, _ in chosen if row["pmid"]})
        print(f"[rq2-sample] abstract preview per {len(wanted)} PMID del campione…")
        previews = fetch_abstract_previews(wanted)

    rows = []
    for row, stratum in chosen:
        meta = resolution.get(row["pmid"], {})
        rows.append({
            "candidate_id": row["candidate_id"],
            "pmid": row["pmid"] or row["pmid_raw"],
            "disease": row["disease"],
            "gene": row["gene"],
            "alteration": row["alteration"],
            "biomarker": "|".join(x for x in (row["gene"], row["alteration"]) if x),
            "intervention": row["intervention"],
            "direction": row["direction"],
            "stratum": stratum,
            "title": meta.get("title") or "",
            "journal": meta.get("journal") or "",
            "publication_types": "|".join(meta.get("publication_types") or []),
            "abstract_preview_redacted": previews.get(row["pmid"], ""),
            "provenance_level": row["provenance_level"],
            "sibling_drug_count": row["sibling_drug_count"],
            "automatic_resolution_status": meta.get("resolution_status") or "PMID_NOT_QUERIED",
            "automatic_document_status": meta.get("document_status") or "",
            "automatic_retraction_signals": "|".join(meta.get("retraction_signals") or []),
            "reviewer_relevant": "",
            "reviewer_direction": "",
            "reviewer_specificity": "",
            "reviewer_notes": "",
        })

    for target in (OUT, SAMPLE_OUT):
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    blank = all(
        not r["reviewer_relevant"] and not r["reviewer_direction"]
        and not r["reviewer_specificity"] and not r["reviewer_notes"]
        for r in rows
    )
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["stratum"]] = counts.get(r["stratum"], 0) + 1
    print(f"[rq2-sample] righe: {len(rows)} -> {OUT.relative_to(REPO_ROOT)}")
    print("[rq2-sample] strati:", json.dumps(counts, indent=1))
    print(f"[rq2-sample] anteprime abstract presenti: {sum(1 for r in rows if r['abstract_preview_redacted'])}")
    print(f"[rq2-sample] colonne revisore vuote: {blank}")
    print(f"[rq2-sample] generato: {datetime.now(timezone.utc).isoformat()}")
    return 0 if blank else 1


if __name__ == "__main__":
    sys.exit(main())
