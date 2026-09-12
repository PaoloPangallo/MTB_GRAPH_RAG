"""Final 200-case PAPER rerun using identity-validated documents only."""
from __future__ import annotations

import csv, hashlib, json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.research_pipeline.documents.cache_runtime import ReadOnlyDocumentCache
from preflight_document_cache import main as run_document_preflight
from backend.research_pipeline.enrichment.enricher_v3 import call_enricher_v3
from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3
from backend.research_pipeline.experimental.sourceunit_selector import SourceUnitSelectionInput, select

ROOT = Path(__file__).parent
OUT = ROOT / "results_runtime_v4_8_document_integrity_final_200"
# The sealed authoritative corpus is the single offline source of truth.
CACHE = ROOT / "documents" / "authoritative_fulltext_cache_200" / "cache"
PREFLIGHT = ROOT / "documents" / "authoritative_fulltext_cache_200" / "document_manifest.jsonl"

def rows(path: Path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def sha(path: Path): return hashlib.sha256(path.read_bytes()).hexdigest()


def _units_in_selection_order(units, selected_source_unit_ids):
    units_by_id = {unit["source_unit_id"]: unit for unit in units}
    return [
        units_by_id[source_unit_id]
        for source_unit_id in selected_source_unit_ids
        if source_unit_id in units_by_id
    ]

def main():
    if run_document_preflight() != 0:
        raise RuntimeError("document cache preflight failed; provider run blocked")
    candidates = rows(ROOT / "rq3_main_sample_manifest.jsonl")
    if len(candidates) != 200 or len({r["candidate_id"] for r in candidates}) != 200:
        raise RuntimeError("candidate manifest must contain 200 unique candidates")
    old = rows(ROOT / "results_runtime_v4_8_reader_granularity_paired_200" / "rq3_full_pipeline_predictions_clean.jsonl")
    old_ids = {r["candidate_id"] for r in old}
    cand_ids = {r["candidate_id"] for r in candidates}
    if old_ids != cand_ids:
        raise RuntimeError(f"candidate set mismatch old={len(old_ids)} new={len(cand_ids)}")
    units_out, resolutions_out, pred_out = (OUT / n for n in ("sourceunits.jsonl", "document_resolutions.jsonl", "rq3_final_predictions.jsonl"))
    OUT.mkdir(parents=True, exist_ok=True)
    cache = ReadOnlyDocumentCache(CACHE)
    all_units, resolutions, predictions = [], [], []
    for item in candidates:
        cid, pmid, candidate = item["candidate_id"], str(item["PMID"]), item["gca"]
        preflight = next(x for x in rows(PREFLIGHT) if x["candidate_id"] == cid)
        if preflight["document_kind"] == "PMC_FULLTEXT":
            resolution = cache.resolve_pmc(preflight["resolved_pmcid"])
        elif preflight["document_kind"] == "PUBMED_ABSTRACT":
            resolution = cache.resolve_pmid(pmid)
        else:
            resolution = {"document_id": f"pmid:{pmid}", "availability": "DOCUMENT_UNAVAILABLE", "local_cache_path": None, "identifiers": {"pmid": pmid}}
        docid = resolution.get("document_id")
        resolved_pmid = docid.split(":", 1)[1] if isinstance(docid, str) and docid.startswith("pmid:") else cache._pmc_article_pmid(resolution) if isinstance(docid, str) and docid.startswith("pmcid:") else None
        identity = resolved_pmid == pmid
        rs = {"candidate_id":cid,"requested_pmid":pmid,"resolved_document_id":docid,"resolved_pmcid":docid.split(":",1)[1] if isinstance(docid,str) and docid.startswith("pmcid:") else None,"resolved_pmc_article_pmid":resolved_pmid,"document_identity_validated":identity,"availability":resolution.get("availability"),"local_cache_path":resolution.get("local_cache_path"),"degradation_reason":resolution.get("degradation_reason"),"rejected_pmcids":resolution.get("rejected_pmcids",[]),"content_hash":resolution.get("content_hash")}
        resolutions.append(rs)
        if not identity:
            predictions.append({"candidate_id":cid,"document_id":docid,"resolution":rs,"selected_sourceunit_ids":[],"errors":["DOCUMENT_IDENTITY_NOT_VALIDATED"],"final_support":"UNVERIFIABLE"})
            continue
        units = [dict(u, unit_type=u.get("source_unit_type")) for u in cache.source_units_for_record(resolution)]
        all_units.extend([{**u,"candidate_id":cid} for u in units])
        selected = list(select(SourceUnitSelectionInput.from_candidate(candidate, docid, units), top_k=5).selected_source_unit_ids)
        chosen = _units_in_selection_order(units, selected)
        try:
            call = call_enricher_v3("RQ3_FINAL_DOCUMENT_INTEGRITY", cid, docid, {}, candidate, chosen, run_index=0)
            val = validate_enrichment_v3(call["transport_result"], call["enrichment"], candidate=candidate, paper_bundle={"document_id":docid,"resolved_source_unit_ids":selected}, source_units_by_id={u["source_unit_id"]:u for u in units})
            if val.get("outcome") == "ENRICHMENT_V3_ACCEPTED":
                sup = assess_relation_support(candidate, call["enrichment"])
                predictions.append({"candidate_id":cid,"document_id":docid,"resolution":rs,"selected_sourceunit_ids":selected,"reader":call,"validator":val,"field_support_states":sup.get("fields",{}),"final_support":sup["result"],"errors":[]})
            else:
                predictions.append({"candidate_id":cid,"document_id":docid,"resolution":rs,"selected_sourceunit_ids":selected,"reader":call,"validator":val,"field_support_states":{},"final_support":"UNVERIFIABLE","errors":["VALIDATION_NOT_ACCEPTED_FOR_RELATION_SUPPORT"]})
        except Exception as exc:
            predictions.append({"candidate_id":cid,"document_id":docid,"resolution":rs,"selected_sourceunit_ids":selected,"errors":[f"{type(exc).__name__}: {exc}"],"final_support":"UNVERIFIABLE"})
    for path, data in ((units_out,all_units),(resolutions_out,resolutions),(pred_out,predictions)):
        path.write_text("".join(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n" for x in data),encoding="utf-8")
    manifest={"run_identity":"FINAL_PAPER_V4_8_DOCUMENT_INTEGRITY_200","target_count":200,"model":"gemma4:cloud","prompt_version":"paper-context-enricher-prompt/4.8","transport_version":"paper-context-enrichment-transport/4.5","normalizer_version":"paper-canonical-normalizer/1.0","validator_version":"paper-validator/4.0","verifier_policy_version":"paper-relation-verifier/4.0","top_k":5,"document_identity_fix_enabled":True,"semantic_runtime_changed":False,"candidate_manifest_sha256":sha(ROOT/"rq3_main_sample_manifest.jsonl"),"sourceunit_corpus_sha256":sha(ROOT/"sourceunits/sourceunits.jsonl"),"output_hashes":{p.name:sha(p) for p in (units_out,resolutions_out,pred_out)}}
    (OUT/"execution_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding="utf-8")
    from collections import Counter
    print(json.dumps({"cases":len(predictions),"identity_validated":sum(r["document_identity_validated"] for r in resolutions),"identity_failed":sum(not r["document_identity_validated"] for r in resolutions),"states":Counter(r["final_support"] for r in predictions),"errors":sum(bool(r.get("errors")) for r in predictions),"output":str(OUT)},default=str))

if __name__ == "__main__": main()
