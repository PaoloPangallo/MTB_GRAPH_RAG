"""Driver RQ2 — audit delle associazioni candidate–PMID.

Uso::

    python -m evaluation.run_rq2 [--offline]

``--offline`` salta la risoluzione bibliografica in rete e usa solo la cache
documentale locale. Senza il flag vengono interrogate le API ufficiali NCBI
E-utilities in modalità **solo metadata**.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from evaluation.rq1.compare import load_candidates
from evaluation.rq2.pairs import (
    PAIR_FIELDS, PMID_CANDIDATE_LEVEL, PMID_PARENT_LEVEL_ONLY, build_pairs,
)
from evaluation.rq2.resolve import DOCUMENT_AVAILABLE, NOT_FOUND, PubMedResolver, RESOLVED

REPO_ROOT = Path(__file__).resolve().parents[1]
DGC = REPO_ROOT / "benchmarks" / "mtb_evidence" / "document_grounded_claims"
CANDIDATES = DGC / "graph_candidate_repository" / "2.0" / "candidates.jsonl"
DOC_MANIFEST = DGC / "authorized_document_cache_pilot" / "document_manifest.jsonl"
BUNDLES = DGC / "evidence_bundle" / "evidence_bundles.jsonl"
MISMATCHES = REPO_ROOT / "evaluation" / "rq1_graph_candidate_fidelity" / "mismatches.csv"
OUT = REPO_ROOT / "evaluation" / "rq2_pmid_associations"
PUBMED_CACHE = REPO_ROOT / "evaluation" / "rq2" / "pubmed_metadata_cache.json"


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _sibling_drug_counts() -> dict[str, int]:
    """Numero di farmaci del record Evidence padre, da RQ1 (REGIMEN_SPLIT)."""
    counts: dict[str, int] = {}
    if not MISMATCHES.exists():
        return counts
    with MISMATCHES.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["error_class"] == "REGIMEN_SPLIT" and row.get("candidate_id"):
                detail = json.loads(row["detail"])
                counts[row["candidate_id"]] = detail.get("evidence_drug_edge_count", 1)
    return counts


def _cached_documents() -> dict[str, dict]:
    """PMID presenti nella cache documentale autorizzata."""
    out: dict[str, dict] = {}
    if not DOC_MANIFEST.exists():
        return out
    for line in DOC_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        pmid = (record.get("identifiers") or {}).get("pmid")
        if not pmid and str(record.get("document_id", "")).startswith("pmid:"):
            pmid = record["document_id"].split(":", 1)[1]
        if pmid:
            out[str(pmid)] = record
    return out


def _bundle_signals() -> dict[str, list[dict]]:
    """Indicatori automatici della pipeline, per coppia candidate/documento.

    **Non sono gold standard.** Sono registrati per la revisione umana e non
    entrano in nessuna metrica di pertinenza semantica.
    """
    out: dict[str, list[dict]] = defaultdict(list)
    if not BUNDLES.exists():
        return out
    for line in BUNDLES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        bundle = json.loads(line)
        document_id = str(bundle.get("document_id") or "")
        if not document_id.startswith("pmid:"):
            continue
        key = f"{bundle.get('candidate_id')}::{document_id.split(':', 1)[1]}"
        out[key].append({
            "support_status": bundle.get("support_status"),
            "coherence_status": bundle.get("coherence_status"),
            "core_support_mask": bundle.get("core_support_mask"),
            "contradiction_detected": bundle.get("contradiction_detected"),
            "negation_detected": bundle.get("negation_detected"),
            "review_required": bundle.get("review_required"),
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="nessuna chiamata di rete")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()

    candidates = list(load_candidates(CANDIDATES))
    pairs = build_pairs(candidates, _sibling_drug_counts())
    print(f"[rq2] candidate: {len(candidates)} | coppie candidate–PMID: {len(pairs)}")

    _write_csv(OUT / "candidate_pmid_pairs.csv", PAIR_FIELDS, [p.to_row() for p in pairs])

    cached = _cached_documents()
    signals = _bundle_signals()
    unique_pmids = sorted({p.pmid for p in pairs if p.pmid})
    print(f"[rq2] PMID unici: {len(unique_pmids)} | in cache documentale: "
          f"{len(set(unique_pmids) & set(cached))}")

    # ------------------------------------------------- risoluzione bibliografica
    records = {}
    request_log: list[dict] = []
    if args.offline:
        print("[rq2] modalità offline: nessuna chiamata di rete")
    else:
        resolver = PubMedResolver(cache_path=PUBMED_CACHE, email=os.getenv("NCBI_EMAIL") or None)
        print(f"[rq2] risoluzione NCBI esummary (solo metadata) di {len(unique_pmids)} PMID…")
        records = resolver.resolve_many(unique_pmids)
        request_log = resolver.log_rows()
        print(f"[rq2] richieste HTTP effettuate: {len(request_log)}")

    # -------------------------------------------------------------- risultati
    resolution_rows = []
    for pmid in unique_pmids:
        record = records.get(pmid)
        cache_entry = cached.get(pmid)
        if cache_entry:
            availability = cache_entry.get("availability")
            document_status = (
                DOCUMENT_AVAILABLE
                if availability in {"ABSTRACT_AVAILABLE", "PMC_XML_AVAILABLE"}
                else "PMID_DOCUMENT_UNAVAILABLE"
            )
        else:
            availability = None
            document_status = "PMID_DOCUMENT_UNAVAILABLE"
        resolution_rows.append({
            "pmid": pmid,
            "resolution_status": record.status if record else "PMID_NOT_QUERIED",
            "document_status": document_status,
            "cache_availability": availability,
            "title": record.title if record else None,
            "journal": record.journal if record else None,
            "pubdate": record.pubdate if record else None,
            "publication_types": record.publication_types if record else [],
            "doi": record.doi if record else None,
            "pmcid": record.pmcid if record else None,
            "retraction_signals": record.retraction_signals if record else [],
        })
    with (OUT / "resolution_results.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for row in resolution_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    by_pmid = {row["pmid"]: row for row in resolution_rows}

    _write_csv(
        OUT / "unavailable_pmids.csv",
        ["pmid", "resolution_status", "document_status", "cache_availability", "candidate_count"],
        [
            {
                "pmid": row["pmid"], "resolution_status": row["resolution_status"],
                "document_status": row["document_status"],
                "cache_availability": row["cache_availability"] or "",
                "candidate_count": sum(1 for p in pairs if p.pmid == row["pmid"]),
            }
            for row in resolution_rows if row["document_status"] != DOCUMENT_AVAILABLE
        ],
    )
    _write_csv(
        OUT / "parent_level_only.csv",
        ["candidate_id", "pmid", "predicate", "intervention", "direction",
         "sibling_drug_count", "evidence_record_ids"],
        [
            {
                "candidate_id": p.candidate_id, "pmid": p.pmid or "", "predicate": p.predicate,
                "intervention": "|".join(p.intervention), "direction": p.direction or "",
                "sibling_drug_count": p.sibling_drug_count,
                "evidence_record_ids": "|".join(p.evidence_record_ids),
            }
            for p in pairs if p.provenance_level == PMID_PARENT_LEVEL_ONLY
        ],
    )

    if request_log:
        _write_json(OUT / "ncbi_request_log.json", {
            "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            "mode": "metadata_only",
            "note": "Nessun testo integrale scaricato. Rate limit rispettato (>=0.40 s fra richieste).",
            "requests": request_log,
        })

    # --------------------------------------------------------------- metriche
    resolved = sum(1 for r in resolution_rows if r["resolution_status"] == RESOLVED)
    not_found = sum(1 for r in resolution_rows if r["resolution_status"] == NOT_FOUND)
    doc_available = sum(1 for r in resolution_rows if r["document_status"] == DOCUMENT_AVAILABLE)
    pmids_per_candidate = Counter(
        sum(1 for p in pairs if p.candidate_id == c) for c in {p.candidate_id for p in pairs}
    ) if pairs else Counter()

    metrics = {
        "generated_at": started,
        "offline": args.offline,
        "unit_of_analysis": "coppia candidate-PMID",
        "candidates_total": len(candidates),
        "candidates_with_pmid": len({p.candidate_id for p in pairs}),
        "candidates_without_pmid": len(candidates) - len({p.candidate_id for p in pairs}),
        "candidate_pmid_pairs": len(pairs),
        "raw_identifier_rows": sum(
            1 for c in candidates for i in (c.get("document_identifiers") or []) if i.get("pmid")
        ),
        "unique_pmids": len(unique_pmids),
        "pmid_syntactically_valid": sum(1 for p in pairs if p.syntactically_valid),
        "pmid_invalid_format": sum(1 for p in pairs if not p.syntactically_valid),
        "invalid_reasons": dict(Counter(p.invalid_reason for p in pairs if p.invalid_reason)),
        "pmid_resolved_metadata_only": resolved,
        "pmid_not_found": not_found,
        "pmid_in_document_cache": len(set(unique_pmids) & set(cached)),
        "pmid_document_available": doc_available,
        "pmid_document_unavailable": len(unique_pmids) - doc_available,
        "pairs_candidate_level": sum(1 for p in pairs if p.provenance_level == PMID_CANDIDATE_LEVEL),
        "pairs_parent_level_only": sum(1 for p in pairs if p.provenance_level == PMID_PARENT_LEVEL_ONLY),
        "pairs_parent_level_multi_drug": sum(
            1 for p in pairs
            if p.provenance_level == PMID_PARENT_LEVEL_ONLY and p.sibling_drug_count > 1
        ),
        "scope_distribution": dict(Counter("+".join(p.scopes) for p in pairs)),
        "pmids_per_candidate_distribution": dict(sorted(pmids_per_candidate.items())),
        "mean_pmids_per_candidate": (
            len(pairs) / len({p.candidate_id for p in pairs}) if pairs else None
        ),
        "publication_type_distribution": dict(Counter(
            t for r in resolution_rows for t in (r["publication_types"] or [])
        ).most_common(20)),
        "retraction_or_correction_signals": sum(
            1 for r in resolution_rows if r["retraction_signals"]
        ),
        "pmids_with_pmcid": sum(1 for r in resolution_rows if r["pmcid"]),
        "pmids_with_doi": sum(1 for r in resolution_rows if r["doi"]),
        "automatic_pipeline_signals_available": len(signals),
        "semantic_relevance": {
            "status": "NOT_MEASURED",
            "reason": (
                "La pertinenza semantica richiede annotazione umana. Gli indicatori "
                "automatici della pipeline sono registrati ma non usati come gold."
            ),
            "semantic_pmid_precision_claimed_without_gold": False,
        },
        "ncbi_requests": len(request_log),
    }
    _write_json(OUT / "aggregate_metrics.json", metrics)

    print(json.dumps({k: metrics[k] for k in (
        "candidates_with_pmid", "candidates_without_pmid", "candidate_pmid_pairs",
        "unique_pmids", "pmid_syntactically_valid", "pmid_invalid_format",
        "pmid_resolved_metadata_only", "pmid_not_found", "pmid_document_available",
        "pairs_candidate_level", "pairs_parent_level_only", "pairs_parent_level_multi_drug",
        "retraction_or_correction_signals", "pmids_with_pmcid", "ncbi_requests",
    )}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
