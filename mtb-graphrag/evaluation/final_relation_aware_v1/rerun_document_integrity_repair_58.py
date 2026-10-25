"""Rerun only the 58 v4.8 cases whose cached PMCID identity was wrong."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.research_pipeline.documents.cache_runtime import ReadOnlyDocumentCache
try:
    from .preflight_document_cache import main as run_document_preflight
except ImportError:  # pragma: no cover - direct script execution
    from preflight_document_cache import main as run_document_preflight
from backend.research_pipeline.enrichment.enricher_v3 import call_enricher_v3
from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3
from backend.research_pipeline.experimental.sourceunit_selector import SourceUnitSelectionInput, select

ROOT = Path(__file__).parent


def _units_in_selection_order(units, selected_source_unit_ids):
    units_by_id = {unit["source_unit_id"]: unit for unit in units}
    return [
        units_by_id[source_unit_id]
        for source_unit_id in selected_source_unit_ids
        if source_unit_id in units_by_id
    ]
OUT = ROOT / "results_runtime_v4_8_document_integrity_repair_58"
DOC_CACHE = ROOT / "documents" / "authoritative_fulltext_cache_200" / "cache"
AUDIT_CSV = ROOT / "audit_pmid_pmcid_document_integrity_200.csv"
PREDICTIONS = OUT / "rq3_document_integrity_repair_predictions.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if run_document_preflight() != 0:
        raise RuntimeError("document cache preflight failed; provider run blocked")
    wrong = [row for row in csv.DictReader(AUDIT_CSV.open(encoding="utf-8")) if row["status"] == "INCORRECT"]
    if len(wrong) != 58:
        raise RuntimeError(f"expected exactly 58 contaminated cases, found {len(wrong)}")
    candidates = {row["candidate_id"]: row["gca"] for row in load_jsonl(ROOT / "rq3_main_sample_manifest.jsonl")}
    cache = ReadOnlyDocumentCache(DOC_CACHE)
    OUT.mkdir(parents=True, exist_ok=True)
    units_out = OUT / "sourceunits.jsonl"
    resolutions_out = OUT / "document_resolutions.jsonl"
    rows = []
    all_units = []
    resolutions = []
    for item in wrong:
        cid = item["candidate_id"]
        requested_pmid = item["candidate_pmid"]
        candidate = candidates[cid]
        resolution = cache.resolve_live_identifier({"pmid": requested_pmid})
        resolved_pmid = None
        resolved_pmcid = None
        if str(resolution.get("document_id", "")).startswith("pmcid:"):
            resolved_pmcid = resolution["document_id"].split(":", 1)[1]
            resolved_pmid = cache._pmc_article_pmid(resolution)
        elif str(resolution.get("document_id", "")).startswith("pmid:"):
            resolved_pmid = resolution["document_id"].split(":", 1)[1]
        identity_validated = resolved_pmid == requested_pmid
        resolution_summary = {
            "candidate_id": cid,
            "requested_pmid": requested_pmid,
            "resolved_document_id": resolution.get("document_id"),
            "resolved_pmcid": resolved_pmcid,
            "resolved_pmc_article_pmid": resolved_pmid,
            "document_identity_validated": identity_validated,
            "availability": resolution.get("availability"),
            "degradation_reason": resolution.get("degradation_reason"),
            "rejected_pmcids": resolution.get("rejected_pmcids", []),
            "local_cache_path": resolution.get("local_cache_path"),
            "content_hash": resolution.get("content_hash"),
        }
        resolutions.append(resolution_summary)
        if not identity_validated:
            rows.append({"candidate_id": cid, "document_id": resolution.get("document_id"), "errors": ["DOCUMENT_IDENTITY_NOT_VALIDATED"], "resolution": resolution_summary, "selected_sourceunit_ids": [], "final_support": "UNVERIFIABLE"})
            continue
        units = [dict(unit, unit_type=unit.get("source_unit_type")) for unit in cache.source_units_for_record(resolution)]
        all_units.extend([{**unit, "candidate_id": cid} for unit in units])
        selected_ids = list(select(SourceUnitSelectionInput.from_candidate(candidate, resolution["document_id"], units), top_k=5).selected_source_unit_ids)
        chosen = _units_in_selection_order(units, selected_ids)
        try:
            call = call_enricher_v3("RQ3_DOCUMENT_INTEGRITY_REPAIR", cid, resolution["document_id"], {}, candidate, chosen, run_index=0)
            validation = validate_enrichment_v3(
                call["transport_result"], call["enrichment"], candidate=candidate,
                paper_bundle={"document_id": resolution["document_id"], "resolved_source_unit_ids": selected_ids},
                source_units_by_id={unit["source_unit_id"]: unit for unit in units},
            )
            if validation.get("outcome") == "ENRICHMENT_V3_ACCEPTED":
                support = assess_relation_support(candidate, call["enrichment"])
                result = {"candidate_id": cid, "document_id": resolution["document_id"], "resolution": resolution_summary, "selected_sourceunit_ids": selected_ids, "reader": call, "validator": validation, "field_support_states": support.get("fields", {}), "final_support": support["result"], "errors": []}
            else:
                result = {"candidate_id": cid, "document_id": resolution["document_id"], "resolution": resolution_summary, "selected_sourceunit_ids": selected_ids, "reader": call, "validator": validation, "field_support_states": {}, "final_support": "UNVERIFIABLE", "errors": ["VALIDATION_NOT_ACCEPTED_FOR_RELATION_SUPPORT"]}
        except Exception as exc:
            result = {"candidate_id": cid, "document_id": resolution["document_id"], "resolution": resolution_summary, "selected_sourceunit_ids": selected_ids, "errors": [f"{type(exc).__name__}: {exc}"], "final_support": "UNVERIFIABLE"}
        rows.append(result)
    PREDICTIONS.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    units_out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in all_units), encoding="utf-8")
    resolutions_out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in resolutions), encoding="utf-8")
    manifest = {
        "benchmark_role": "DOCUMENT_INTEGRITY_REPAIR_SUBSET",
        "target_count": 58,
        "candidate_ids": [row["candidate_id"] for row in wrong],
        "model": "gemma4:cloud",
        "prompt_version": "paper-context-enricher-prompt/4.8",
        "transport_version": "paper-context-enrichment-transport/4.5",
        "normalizer_version": "paper-canonical-normalizer/1.0",
        "validator_version": "paper-validator/4.0",
        "verifier_policy_version": "paper-relation-verifier/4.0",
        "top_k": 5,
        "source_cache_root": str(DOC_CACHE),
        "output_hashes": {str(path.name): sha256(path) for path in (PREDICTIONS, units_out, resolutions_out)},
    }
    (OUT / "execution_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"cases": len(rows), "validated": sum(r.get("resolution", {}).get("document_identity_validated") is True for r in rows), "states": {state: sum(r.get("final_support") == state for r in rows) for state in ("FULL_SUPPORT", "PARTIAL_SUPPORT", "UNVERIFIABLE", "CONTRADICTORY")}, "provider_failures": sum(bool(r.get("errors")) and not r.get("reader") for r in rows), "output": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
