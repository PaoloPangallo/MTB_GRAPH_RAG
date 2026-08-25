"""Acquire only the frozen sample's document sources; never invokes an LLM."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache
from backend.research_pipeline.retrieval.relation_family import KG_ONLY

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
SAMPLE_PATH = ROOT / "evaluation/relation_aware_1_0/candidate_sample.json"
SAMPLE_SHA = "d168027b5e4994109c9cf1975a8d27bddcd214ae7d46a077a0aa4af594cc3233"
OUT = BASE / "sources"
CACHE = OUT / "cache"


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def sha_json(value: object) -> str:
    return sha_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def write_json(path: Path, value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha_bytes(payload)


def ids(entry: dict, key: str) -> list[str]:
    return sorted({str(item[key]) for item in entry.get("document_identifiers") or [] if isinstance(item, dict) and item.get(key)})


def attempts(record: dict) -> list[dict]:
    values = list(record.get("resolution_attempts") or [])
    nested = record.get("pmc_resolution")
    if isinstance(nested, dict):
        values.extend(nested.get("resolution_attempts") or [])
    return values


def copy_cache_files(record: dict, target: Path, cache: Path, extra: list[str] | None = None) -> list[dict]:
    copied = []
    paths = []
    for key in ("metadata_cache_path", "local_cache_path"):
        value = record.get(key)
        if value:
            paths.append(str(value))
    nested = record.get("pmid_resolution")
    if isinstance(nested, dict):
        for key in ("metadata_cache_path", "local_cache_path"):
            if nested.get(key):
                paths.append(str(nested[key]))
    paths.extend(extra or [])
    for relative in sorted(set(paths)):
        source = cache / relative
        if source.is_file():
            destination = target / "raw" / relative.replace("/", "_")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append({"relative": relative, "sha256": sha_file(destination), "bytes": destination.stat().st_size})
    return copied


def paper(entry: dict, cache: AuthorizedDocumentCache, manifest: dict) -> tuple[dict, list[dict]]:
    sample_id = entry["sample_id"]
    pmid = ids(entry, "pmid")[0]
    target = OUT / "paper" / sample_id
    record = cache.resolve_live_identifier({"pmid": pmid})
    pmcid = (record.get("identifiers") or {}).get("pmcid")
    extra = [f"pubmed/metadata/{pmid}.json", f"pubmed/abstracts/{pmid}.xml"]
    if pmcid:
        extra.append(f"pmc/xml/{pmcid}.xml")
    copied = copy_cache_files(record, target, cache.root, extra)
    availability = record.get("availability")
    if availability == "PMC_XML_AVAILABLE":
        status, document_type = "PAPER_RESOLVED_PMC", "PMC_FULLTEXT"
    elif availability == "ABSTRACT_AVAILABLE":
        status, document_type = "PAPER_RESOLVED_ABSTRACT", "PUBMED_ABSTRACT"
    elif availability in {"METADATA_ONLY", "ABSTRACT_EMPTY", "PMC_NOT_FOUND", "PMC_NOT_OPEN", "PMC_RESOLUTION_FAILED", "PMID_NOT_FOUND"}:
        status, document_type = "PAPER_UNAVAILABLE", "UNAVAILABLE"
    else:
        status, document_type = "PAPER_UNAVAILABLE", "UNAVAILABLE"
    units = []
    parser_status = "NOT_RUN"
    parser_error = None
    if document_type != "UNAVAILABLE":
        try:
            units = cache.source_units_for_record(record)
            parser_status = "PARSED" if units else "PARSER_FAILED"
            if not units:
                status = "PAPER_PARSER_FAILED"
        except Exception as exc:  # data-dependent parser failures remain recorded
            parser_status, parser_error, status = "PARSER_FAILED", repr(exc), "PAPER_PARSER_FAILED"
    unit_hash = write_json(target / "sourceunits.json", units) if units else None
    canonical_hash = None
    relative = record.get("local_cache_path")
    if relative and (cache.root / relative).is_file():
        canonical_hash = sha_file(cache.root / relative)
    raw_hash = sha_json(copied)
    result = {
        "sample_id": sample_id, "candidate_id": entry["candidate_id"], "relation_family": entry["relation_family"],
        "pmid": pmid, "pmcid": pmcid, "acquisition_status": status,
        "canonical_document_type": document_type, "document_id": record.get("document_id"),
        "raw_payload_sha256": raw_hash, "canonical_document_sha256": canonical_hash,
        "raw_payloads": copied,
        "sourceunit_bundle_sha256": unit_hash, "sourceunit_count": len(units),
        "parser_status": parser_status, "parser_error": parser_error,
        "http_attempts": attempts(record), "resolver_record": record,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(target / "acquisition_record.json", result)
    manifest.update(result)
    return result, attempts(record)


def trial(entry: dict, cache: AuthorizedDocumentCache, manifest: dict) -> tuple[dict, list[dict]]:
    sample_id = entry["sample_id"]
    nct = ids(entry, "nct")[0]
    target = OUT / "trial" / sample_id
    record = cache.resolve_nct(nct)
    copied = copy_cache_files(record, target, cache.root)
    status = record.get("availability")
    if status == "METADATA_ONLY" and record.get("title"):
        acquisition_status = "TRIAL_RESOLVED"
    elif status == "METADATA_ONLY":
        acquisition_status = "TRIAL_PARSE_FAILED"
    else:
        acquisition_status = "TRIAL_UNAVAILABLE"
    normalized = {"nct_id": nct, "title": record.get("title"), "overall_status": record.get("recruitment_status"),
                  "phase": record.get("phase") or [], "conditions": record.get("conditions") or [],
                  "interventions": record.get("interventions") or [], "eligibility": record.get("eligibility")}
    normalized_hash = write_json(target / "normalized_record.json", normalized)
    raw_hash = sha_json(copied)
    result = {"sample_id": sample_id, "candidate_id": entry["candidate_id"], "relation_family": entry["relation_family"],
              "nct_id": nct, "acquisition_status": acquisition_status, "raw_payload_sha256": raw_hash,
              "raw_payloads": copied,
              "normalized_record_sha256": normalized_hash, "title": normalized["title"],
              "status": normalized["overall_status"], "phase": normalized["phase"],
              "conditions": normalized["conditions"], "interventions": normalized["interventions"],
              "eligibility_raw": normalized["eligibility"], "http_attempts": attempts(record),
              "resolver_record": record, "acquired_at": datetime.now(timezone.utc).isoformat()}
    write_json(target / "acquisition_record.json", result)
    manifest.update(result)
    return result, attempts(record)


def rebuild_existing_metadata() -> None:
    """Complete request metadata from persisted payloads; performs no network I/O."""
    path = OUT / "source_snapshot_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    all_attempts = []
    for row in manifest["entries"]:
        if row["relation_family"] in {"PAPER_EVIDENCE", "CLINICAL_TRIAL"}:
            family_dir = "paper" if row["relation_family"] == "PAPER_EVIDENCE" else "trial"
            raw_dir = OUT / family_dir / row["sample_id"] / "raw"
            row["raw_payloads"] = [{"relative": str(path.relative_to(OUT / family_dir / row["sample_id"])).replace("\\", "/"), "sha256": sha_file(path), "bytes": path.stat().st_size} for path in sorted(raw_dir.glob("*")) if path.is_file()]
        if row["relation_family"] == "PAPER_EVIDENCE":
            pmid = row["pmid"]
            pubmed = [
                {"attempt": 1, "status": 200, "url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=" + quote(pmid)},
                {"attempt": 1, "status": 200, "url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id=" + quote(pmid)},
            ]
            if row["canonical_document_type"] == "PMC_FULLTEXT":
                pubmed.append({"attempt": 1, "status": 200, "url": "https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi?verb=GetRecord&metadataPrefix=pmc&identifier=oai:pubmedcentral.nih.gov:" + quote(row["pmcid"][3:])})
            row["http_attempts"] = pubmed
            row["http_attempts_observability"] = "RECONSTRUCTED_FROM_SUCCESSFUL_RESOLVER_PATH_AND_PERSISTED_PAYLOADS"
        all_attempts.extend(row.get("http_attempts") or [])
    manifest["total_external_requests"] = len(all_attempts)
    write_json(path, manifest)
    report_path = OUT / "acquisition_report.md"
    report = report_path.read_text(encoding="utf-8")
    report = report.replace("TOTAL_EXTERNAL_REQUESTS=37", f"TOTAL_EXTERNAL_REQUESTS={len(all_attempts)}")
    report += "\nRequest count note: the resolver's successful PMC return record did not retain the preceding PubMed attempt list; counts above were reconstructed offline from the successful resolver path and the persisted PubMed/PMC payload files. No new request was made.\n"
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"reconstructed_external_requests": len(all_attempts), "network_calls": 0}, sort_keys=True))


def main() -> None:
    sample_bytes = SAMPLE_PATH.read_bytes()
    if sha_bytes(sample_bytes) != SAMPLE_SHA:
        raise SystemExit("candidate_sample SHA mismatch")
    sample = json.loads(sample_bytes)
    if "--rebuild-existing" in sys.argv:
        rebuild_existing_metadata()
        return
    if (OUT / "source_snapshot_manifest.json").exists():
        raise SystemExit("source snapshot manifest already exists; refusing a second acquisition")
    cache = AuthorizedDocumentCache(CACHE, network=True)
    rows, all_attempts = [], []
    for entry in sample["entries"]:
        family = entry["relation_family"]
        if family == KG_ONLY:
            if entry.get("document_identifiers"):
                raise SystemExit(f"KG_ONLY identifier violation: {entry['sample_id']}")
            rows.append({"sample_id": entry["sample_id"], "candidate_id": entry["candidate_id"], "relation_family": family,
                         "expected_identifier": None, "acquisition_status": "NOT_APPLICABLE",
                         "source_acquisition": "NOT_APPLICABLE", "reason": "KG_ONLY_NO_DOCUMENT_PROVENANCE"})
        elif family == "PAPER_EVIDENCE":
            row, attempts_used = paper(entry, cache, {})
            rows.append(row); all_attempts.extend(attempts_used)
        elif family == "CLINICAL_TRIAL":
            row, attempts_used = trial(entry, cache, {})
            rows.append(row); all_attempts.extend(attempts_used)
        else:
            raise SystemExit(f"unknown relation family: {family}")
    manifest = {"sample_sha256": SAMPLE_SHA, "sample_commit": "c7d3e1361fbc3be9aecc4949f7483b73bbf3b1e2",
                "core_commit": "dd010056ae348e42e66a6f0098c9e9eb26890d6b2", "entries": rows}
    write_json(OUT / "source_snapshot_manifest.json", manifest)
    paper_rows = [x for x in rows if x["relation_family"] == "PAPER_EVIDENCE"]
    trial_rows = [x for x in rows if x["relation_family"] == "CLINICAL_TRIAL"]
    statuses = Counter(x["acquisition_status"] for x in rows)
    http_failures = Counter()
    for attempt in all_attempts:
        status = attempt.get("status")
        if not isinstance(status, int) or status >= 400:
            service = urlparse(attempt.get("url", "")).netloc or "unknown"
            http_failures[f"{service}:{status or attempt.get('kind', 'unknown')}"] += 1
    report = f"""# Source snapshot acquisition report

Acquisition was performed only for the frozen 16 PAPER_EVIDENCE and 10 CLINICAL_TRIAL entries. The 10 KG_ONLY entries made zero resolver calls. No parser LLM, Reader, Writer, or support checker was invoked.

PAPER_TOTAL=16
PAPER_PMC_FULLTEXT={statuses['PAPER_RESOLVED_PMC']}
PAPER_ABSTRACT_ONLY={statuses['PAPER_RESOLVED_ABSTRACT']}
PAPER_UNAVAILABLE={statuses['PAPER_UNAVAILABLE']}
PAPER_PARSER_FAILED={statuses['PAPER_PARSER_FAILED']}

TRIAL_TOTAL=10
TRIAL_RESOLVED={statuses['TRIAL_RESOLVED']}
TRIAL_UNAVAILABLE={statuses['TRIAL_UNAVAILABLE']}
TRIAL_PARSE_FAILED={statuses['TRIAL_PARSE_FAILED']}

KG_ONLY_TOTAL=10
KG_ONLY_FETCH_ATTEMPTS=0

TOTAL_EXTERNAL_REQUESTS={len(all_attempts)}
HTTP_FAILURES={json.dumps(dict(sorted(http_failures)), sort_keys=True)}

The canonical paper rule was fixed before acquisition: PMC full text when available, otherwise PubMed abstract. No source was substituted after failure. SourceUnit parsing was deterministic and produced all units available from each canonical document; no selection or scientific interpretation was performed.
"""
    (OUT / "acquisition_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"paper": Counter(x["acquisition_status"] for x in paper_rows), "trial": Counter(x["acquisition_status"] for x in trial_rows),
                      "kg_only_fetch_attempts": 0, "total_external_requests": len(all_attempts)}, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
