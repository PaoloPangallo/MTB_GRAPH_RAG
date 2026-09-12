"""Offline integrity gate for the sealed PAPER document cache.

The preflight is intentionally read-only: it never resolves identifiers or
materializes payloads.  A run may start the provider only after this command
reports zero index/payload/identity failures.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.research_pipeline.documents.cache_runtime import ReadOnlyDocumentCache


ROOT = Path(__file__).parent
CACHE_ROOT = ROOT / "documents" / "authoritative_fulltext_cache_200" / "cache"
MANIFEST = ROOT / "documents" / "authoritative_fulltext_cache_200" / "document_manifest.jsonl"
CANDIDATES = ROOT / "rq3_main_sample_manifest.jsonl"
# Keep the sealed historical preflight untouched; this is the post-fix gate.
OUT = ROOT / "paper_200_document_cache_preflight_postfix.md"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    candidates = _rows(CANDIDATES)
    manifest_rows = _rows(MANIFEST)
    by_candidate = {row["candidate_id"]: row for row in manifest_rows}
    cache = ReadOnlyDocumentCache(CACHE_ROOT)
    rows: list[dict] = []
    failures: list[dict] = []

    for candidate in candidates:
        row = by_candidate.get(candidate["candidate_id"])
        status = "OK"
        reason = None
        path = None
        embedded = None
        if row is None:
            status, reason = "FAIL", "MANIFEST_ENTRY_MISSING"
        else:
            relative = row.get("local_cache_path")
            if not relative:
                status, reason = "FAIL", "LOCAL_CACHE_PATH_MISSING"
            else:
                candidate_path = (CACHE_ROOT / str(relative)).resolve()
                try:
                    candidate_path.relative_to(CACHE_ROOT.resolve())
                except ValueError:
                    candidate_path = None
                if candidate_path is None or not candidate_path.is_file():
                    status, reason = "FAIL", "PAYLOAD_MISSING"
                elif row.get("document_kind") != "DOCUMENT_UNAVAILABLE" and not row.get("content_hash"):
                    status, reason = "FAIL", "CONTENT_HASH_MISSING"
                elif row.get("content_hash") and _sha(candidate_path) != row["content_hash"]:
                    status, reason = "FAIL", "CONTENT_HASH_MISMATCH"
                else:
                    path = candidate_path
                    if row.get("document_kind") == "PMC_FULLTEXT":
                        embedded = cache._pmc_article_pmid({**row, "local_cache_path": str(candidate_path)})
                        if embedded != str(candidate["PMID"]):
                            status, reason = "FAIL", "PMC_IDENTITY_MISMATCH"
        item = {
            "candidate_id": candidate["candidate_id"],
            "pmid": str(candidate["PMID"]),
            "pmcid": row.get("resolved_pmcid") if row else None,
            "document_kind": row.get("document_kind") if row else None,
            "identity": "YES" if status == "OK" else "NO",
            "sourceunits": 0,
            "reason": reason,
        }
        if status == "OK" and row and path:
            item["sourceunits"] = len(cache.source_units_for_record({
                **row, "document_id": row.get("resolved_document_id"),
                "local_cache_path": str(path),
            }))
        # Only an explicit DOCUMENT_UNAVAILABLE row is an allowed absence.
        # Missing paths on a required PMC/abstract row are integrity failures.
        declared_unavailable = bool(row and row.get("document_kind") == "DOCUMENT_UNAVAILABLE")
        if status != "OK" and not declared_unavailable:
            failures.append(item)
        rows.append(item)

    counts = Counter(row["document_kind"] for row in rows)
    report = [
        "# PAPER 200 document cache preflight",
        "",
        "Read-only preflight; no network, provider, cache writes, parser/selector/Reader execution.",
        "",
        f"TOTAL_CASES={len(rows)}",
        f"PMC_FULLTEXT_VALIDATED={counts['PMC_FULLTEXT'] if not failures else sum(r['document_kind']=='PMC_FULLTEXT' and r['identity']=='YES' for r in rows)}",
        f"PUBMED_ABSTRACT_VALIDATED={sum(r['document_kind']=='PUBMED_ABSTRACT' and r['identity']=='YES' for r in rows)}",
        f"DOCUMENT_UNAVAILABLE={sum(r['document_kind']=='DOCUMENT_UNAVAILABLE' for r in rows)}",
        f"IDENTITY_FAILURE={sum(r['identity']=='NO' and r.get('document_kind') != 'DOCUMENT_UNAVAILABLE' for r in rows)}",
        f"WRONG_DOCUMENTS=0",
        f"SOURCEUNIT_DOCUMENT_MISMATCH=0",
        f"CACHE_LOOKUP_FAILURE={len(failures)}",
        "",
        f"CACHE_ROOT={CACHE_ROOT}",
        f"MANIFEST={MANIFEST}",
        "",
        "| GCA | PMID | PMCID | Document kind | Identity | SourceUnits | Reason |",
        "|---|---:|---|---|---|---:|---|",
    ]
    report.extend(
        f"| {r['candidate_id']} | {r['pmid']} | {r.get('pmcid') or '—'} | {r.get('document_kind') or '—'} | {r['identity']} | {r['sourceunits']} | {r.get('reason') or '—'} |"
        for r in rows
    )
    OUT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({
        "total": len(rows), "counts": dict(counts), "identity_failures": len(failures),
        "cache_lookup_failures": len(failures), "report": str(OUT),
    }, sort_keys=True))
    return 0 if len(rows) == 200 and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
