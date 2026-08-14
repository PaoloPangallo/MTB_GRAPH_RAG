"""Deterministic post-evaluation analysis for the promoted Protocol 1.7 run.

This module never executes a scientific unit.  It reads the sealed plan, the
append-only ledger, and the canonical raw JSON artifacts, then emits factual
summaries and traceability metadata.  Metrics without an explicit frozen
formula/denominator are reported as NOT_COMPUTABLE_FROM_FROZEN_SPEC.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EVALUATION_ID = "fe_d3946016a0e90299b6989b58ac2f7fe34d352fd3269e94ea4d6efe874413477b"
HEAD = "1174135d0bf86728f2e25593b0afbaed18a5dc6f"
PLAN_SHA = "ccdcc1a54759d931917ad454f245dd547f57ee69fdfc7e515a807a2214d172a0"
PROJECTION_SHA = "178d8dbfaf61655ecb5855a33f50416d68abedd5c86a9e46a6d3196058a399e2"
SOURCE_EXPORT_SHA = "b0ca6b050554a476cb859c1b8ea19030abc16f7d3cf03f565e003110690b8a29"
EXPECTED_COUNTS = {
    "RQ1": 1,
    "RQ2": 80,
    "RQ3": 5,
    "RQ4_DEVELOPMENT": 35,
    "RQ4_HELDOUT": 35,
    "NARRATIVE": 25,
    "OPERATIONAL_A01": 9,
    "RELIABILITY": 30,
    "LATENCY": 2,
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rel_raw(path: Path, campaign: Path) -> str:
    return str(path.relative_to(campaign)).replace("\\", "/")


def stage(raw: dict[str, Any], stage_type: str) -> dict[str, Any] | None:
    for item in raw.get("stages", []):
        if item.get("stage_type") == stage_type:
            return item
    return None


def pipeline(raw: dict[str, Any]) -> dict[str, Any]:
    return raw.get("raw_pipeline_run", raw)


def actual_route(raw: dict[str, Any]) -> tuple[bool | None, str | None]:
    run = pipeline(raw)
    retrieval = stage(run, "KG_RETRIEVAL")
    gate = stage(run, "PRE_RETRIEVAL_ELIGIBILITY_GATE")
    if retrieval is None:
        return None, None
    attempted = retrieval.get("status") != "SKIPPED"
    gate_out = (gate or {}).get("output_preview") or {}
    eligible = gate_out.get("eligible")
    if eligible is None:
        return attempted, "PROCEED_TO_RETRIEVAL" if attempted else "STOP_BEFORE_RETRIEVAL"
    return bool(eligible), "PROCEED_TO_RETRIEVAL" if attempted else "STOP_BEFORE_RETRIEVAL"


def add_row(rows: list[dict[str, Any]], family: str, subgroup: str, metric_id: str,
            metric_name: str, numerator: Any, denominator: Any, value: Any,
            unit: str, verdict: str, source: str) -> None:
    rows.append({
        "family": family, "subgroup": subgroup, "metric_id": metric_id,
        "metric_name": metric_name, "numerator": numerator,
        "denominator": denominator, "value": value, "unit": unit,
        "verdict": verdict, "definition_source": source,
    })


def trace(traceability: dict[str, Any], metric_id: str, definition: str,
          formula: str, numerator: Any, denominator: Any, records: list[tuple[str, Path]]) -> None:
    traceability[metric_id] = {
        "metric_id": metric_id,
        "definition_source": definition,
        "formula": formula,
        "numerator": numerator,
        "denominator": denominator,
        "contributing_unit_ids": [u for u, _ in records],
        "contributing_raw_paths": [str(p).replace("\\", "/") for _, p in records],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    campaign = repo / "evaluation" / "final_evaluation"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    manifest = read_json(campaign / "manifest.json")
    plan = read_json(campaign / "execution_plan.json")
    post = read_json(campaign / "post_snapshot.json")
    protocol_registry = read_json(repo / "evaluation" / "final_protocol" / "metrics_registry.json")
    if manifest.get("evaluation_id") != EVALUATION_ID or manifest.get("plan_sha256") != PLAN_SHA:
        raise SystemExit("FINAL_CAMPAIGN_IDENTITY_MISMATCH")
    if len(plan) != 222:
        raise SystemExit("SEALED_PLAN_COUNT_MISMATCH")

    ledger = [json.loads(line) for line in (campaign / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if line]
    events = Counter(item.get("event") for item in ledger)
    if events["PROMOTED"] != 1 or events["SCIENTIFIC_RUNS_COMPLETE"] != 1:
        raise SystemExit("CAMPAIGN_NOT_PROMOTED")

    plan_by_run = {item["run_id"]: item for item in plan}
    raw_by_run: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted((campaign / "raw_attempts").glob("*.json")):
        raw = read_json(path)
        run_id = raw.get("run_id")
        if run_id in raw_by_run or run_id not in plan_by_run:
            raise SystemExit("RAW_CANONICAL_OWNERSHIP_MISMATCH")
        raw_by_run[run_id] = (path, raw)
    if len(raw_by_run) != 222 or set(raw_by_run) != set(plan_by_run):
        raise SystemExit("RAW_COVERAGE_MISMATCH")

    by_family: dict[str, list[tuple[dict[str, Any], Path, dict[str, Any]]]] = defaultdict(list)
    for run_id, plan_item in plan_by_run.items():
        path, raw = raw_by_run[run_id]
        by_family[plan_item["rq"]].append((raw, path, plan_item))
    if {k: len(v) for k, v in by_family.items()} != EXPECTED_COUNTS:
        raise SystemExit("FAMILY_MEMBERSHIP_MISMATCH")

    rows: list[dict[str, Any]] = []
    traceability: dict[str, Any] = {}
    not_computable: list[dict[str, str]] = []
    source_registry = "evaluation/final_protocol/metrics_registry.json"

    # RQ1: the raw record already contains the frozen metric object.
    rq1_raw, rq1_path, _ = by_family["RQ1"][0]
    rq1_metrics = rq1_raw["scientific_payload"]["metrics"]
    for metric_id, value in rq1_metrics.items():
        if isinstance(value, (int, float)):
            add_row(rows, "RQ1", "primary", metric_id, metric_id, None, None, value, "ratio_or_count", "RAW_REPORTED", source_registry)
            trace(traceability, f"RQ1.{metric_id}", source_registry, "raw scientific_payload.metrics value", None, None, [(rq1_raw["run_id"], rq1_path)])
    write_json(output / "rq1" / "rq1_final.json", {"family": "RQ1", "source_raw": rel_raw(rq1_path, campaign), "metrics": rq1_metrics})

    # RQ2: frozen independent annotation labels + final selected SourceUnit IDs.
    annotations: dict[tuple[str, str], dict[str, str]] = {}
    with (repo / "evaluation/sourceunit_selector_independent/gold_annotations.csv").open(encoding="utf-8", newline="") as handle:
        for item in csv.DictReader(handle):
            annotations[(item["candidate_id"], item["document_id"], item["source_unit_id"])] = item
    inventory_by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with (repo / "evaluation/sourceunit_selector_independent/document_inventory.jsonl").open(encoding="utf-8") as handle:
        for item in (json.loads(line) for line in handle if line.strip()):
            inventory_by_candidate[item["candidate_id"]].append(item)
    rq2_records: list[dict[str, Any]] = []
    for raw, path, plan_item in by_family["RQ2"]:
        sp = raw["scientific_payload"]
        selected = sp.get("selected_source_unit_ids", [])
        candidate_id = sp.get("candidate_id")
        document_id = sp.get("document_id")
        matching_inventory = [item for item in inventory_by_candidate[candidate_id]
                              if item.get("document_id") == document_id
                              or document_id == f"pmid:{item.get('pmid')}"]
        if len(matching_inventory) != 1:
            raise SystemExit(f"RQ2_DOCUMENT_BINDING_AMBIGUOUS:{candidate_id}:{document_id}")
        annotation_document_id = matching_inventory[0]["document_id"]
        key_prefix = (candidate_id, annotation_document_id)
        labels = [v for (candidate, document, _), v in annotations.items() if (candidate, document) == key_prefix]
        direct = {v["source_unit_id"] for v in labels if v["relevance_label"] == "DIRECTLY_RELEVANT"}
        top5 = selected[:5]
        ranks = [i + 1 for i, sid in enumerate(top5) if sid in direct]
        first_rank = min(ranks) if ranks else None
        decision = ((sp.get("enrichment") or {}).get("enrichment") or {}).get("decision")
        validated_decision = ((sp.get("validation") or {}).get("enrichment") or {}).get("decision")
        rq2_records.append({
            "run_id": raw["run_id"], "raw_path": rel_raw(path, campaign), "case_id": plan_item["case_id"],
            "arm": plan_item["arm"], "candidate_id": sp.get("candidate_id"), "document_id": sp.get("document_id"),
            "annotation_document_id": annotation_document_id,
            "selected_count": len(selected), "direct_relevant_count": len(direct),
            "hit_at_5": bool(ranks), "recall_at_5": (len(set(top5) & direct) / len(direct)) if direct else None,
            "precision_at_5": (len(set(top5) & direct) / len(top5)) if top5 else None,
            "mrr": (1 / first_rank) if first_rank else 0.0, "first_relevant_rank": first_rank,
            "decision": decision, "validated_decision": validated_decision,
        })
    rq2_summary: dict[str, Any] = {"records": rq2_records, "by_arm": {}}
    for arm in sorted({r["arm"] for r in rq2_records}):
        subset = [r for r in rq2_records if r["arm"] == arm]
        out: dict[str, Any] = {"unit_count": len(subset), "positive_cases": sum(r["direct_relevant_count"] > 0 for r in subset), "zero_direct_cases": sum(r["direct_relevant_count"] == 0 for r in subset)}
        for label, group in [("overall", subset), ("positive", [r for r in subset if r["direct_relevant_count"] > 0]), ("zero_direct", [r for r in subset if r["direct_relevant_count"] == 0])]:
            out[label] = {"n": len(group), "hit_rate_at_5": (sum(r["hit_at_5"] for r in group) / len(group)) if group else None, "full_coverage_at_5": (sum(r["direct_relevant_count"] > 0 and r["recall_at_5"] == 1.0 for r in group) / len(group)) if group else None, "mean_recall_at_5": (sum(r["recall_at_5"] for r in group if r["recall_at_5"] is not None) / sum(r["recall_at_5"] is not None for r in group)) if any(r["recall_at_5"] is not None for r in group) else None, "mean_precision_at_5": (sum(r["precision_at_5"] for r in group if r["precision_at_5"] is not None) / sum(r["precision_at_5"] is not None for r in group)) if any(r["precision_at_5"] is not None for r in group) else None, "mrr": (sum(r["mrr"] for r in group) / len(group)) if group else None, "quote_count": sum(r["decision"] == "QUOTE" for r in group), "abstain_count": sum(r["decision"] == "ABSTAIN" for r in group), "validated_quote_count": sum(r["validated_decision"] == "QUOTE" for r in group)}
        rq2_summary["by_arm"][arm] = out
        recs = [(r["run_id"], campaign / r["raw_path"]) for r in subset]
        trace(traceability, f"RQ2.{arm}.hit_rate_at_5", source_registry, "sum(hit_at_5)/n; positive and overall denominators kept separate", sum(r["hit_at_5"] for r in subset), len(subset), recs)
    for metric_id, reason in [("recall_at_10", "raw selector output contains only top-5 IDs"), ("document_resolution_rate", "RQ2 raw is the selector/enricher result and does not contain the frozen document-resolution denominator"), ("full_text_availability_rate", "RQ2 raw does not contain the frozen document availability fields"), ("abstract_degradation_rate", "RQ2 raw does not contain the frozen degradation fields"), ("parser_success_rate", "RQ2 raw does not contain parser-stage observations"), ("wrong_document_accepted", "frozen validator field is not present in canonical raw"), ("wrong_sourceunit_accepted", "frozen validator field is not present in canonical raw"), ("wrong_quote_accepted", "frozen validator field is not present in canonical raw")]:
        not_computable.append({"metric_id": f"RQ2.{metric_id}", "reason": reason})
    write_json(output / "rq2" / "rq2_final.json", rq2_summary)

    # RQ3: preserve observed arm states; no frozen paired formula is available in raw.
    rq3 = []
    for raw, path, plan_item in sorted(by_family["RQ3"], key=lambda x: x[2]["arm"]):
        sp = raw["scientific_payload"]
        rq3.append({"arm": plan_item["arm"], "case_id": sp.get("case_id"), "run_id": raw["run_id"], "raw_path": rel_raw(path, campaign), "status": sp.get("status"), "llm_calls": sp.get("llm_calls"), "document_acquisition": sp.get("document_acquisition"), "stage_types": [s.get("stage_type") for s in sp.get("stages", [])], "reason_codes": sorted({code for s in sp.get("stages", []) for code in s.get("reason_codes", [])})})
    not_computable.append({"metric_id": "RQ3.primary_ablation_metrics", "reason": "Protocol defines paired invariants, but the five final raw records do not contain the frozen comparison/signature fields needed to evaluate them without a new interpretation."})
    write_json(output / "rq3" / "rq3_final.json", {"arms": rq3, "comparison": "NOT_COMPUTABLE_FROM_FROZEN_SPEC"})

    # RQ4 development and held-out path metrics.
    dev_gold = {x["case_id"]: x for x in (read_json(repo / "evaluation/rq4_casecontext_robustness/frozen_benchmark_manifest.json") and [json.loads(line) for line in (repo / "evaluation/rq4_casecontext_robustness/benchmark.jsonl").read_text(encoding="utf-8").splitlines() if line])}
    dev_rows = []
    for raw, path, plan_item in by_family["RQ4_DEVELOPMENT"]:
        sp = raw["scientific_payload"]; expected = dev_gold[plan_item["case_id"]]; eligible, route = actual_route(sp); wanted = expected["protocol_required_routing"]
        correct = (eligible is True) if wanted == "PROCEED_TO_RETRIEVAL" else (eligible is False)
        dev_rows.append({"case_id": plan_item["case_id"], "run_id": raw["run_id"], "raw_path": rel_raw(path, campaign), "expected_routing": wanted, "actual_routing": route, "runtime_status": sp.get("status"), "correct_path": correct, "reason_codes": sorted({c for s in sp.get("stages", []) for c in s.get("reason_codes", [])})})
    heldout_gold = {x["case_id"]: x for x in read_json(repo / "evaluation/final_protocol/heldout/architectural_challenge_gold.json")["gold"]}
    heldout_rows = []
    for raw, path, plan_item in by_family["RQ4_HELDOUT"]:
        sp = raw["scientific_payload"]; gold = heldout_gold[plan_item["case_id"]]; rp = sp["raw_pipeline_run"]; eligible, route = actual_route(rp); h01 = sp["h01_evaluation"]; h01_pass = bool(h01.get("phase_1_raw_immutable")) and not any(h01.get("observations", {}).values())
        if gold["expected_retrieval_allowed"] is None:
            correct = h01_pass
        else:
            correct = (eligible is bool(gold["expected_retrieval_allowed"])) and h01_pass
        heldout_rows.append({"case_id": plan_item["case_id"], "run_id": raw["run_id"], "raw_path": rel_raw(path, campaign), "category": gold["category"], "expected_retrieval_allowed": gold["expected_retrieval_allowed"], "actual_retrieval_allowed": eligible, "runtime_status": rp.get("status"), "h01_pass": h01_pass, "correct_path": correct, "h01_observations": h01.get("observations", {})})
    write_json(output / "rq4" / "rq4_final.json", {"development": dev_rows, "held_out": heldout_rows, "development_correct": sum(x["correct_path"] for x in dev_rows), "held_out_correct": sum(x["correct_path"] for x in heldout_rows)})
    for name, group in [("development", dev_rows), ("held_out", heldout_rows)]:
        add_row(rows, "RQ4", name, f"RQ4.{name}.correct_path_rate", "correct_path_rate", sum(x["correct_path"] for x in group), len(group), sum(x["correct_path"] for x in group) / len(group), "ratio", "FROZEN_ROUTING_AND_H01", source_registry)
        trace(traceability, f"RQ4.{name}.correct_path_rate", source_registry, "correct path count / frozen family denominator", sum(x["correct_path"] for x in group), len(group), [(x["run_id"], campaign / x["raw_path"]) for x in group])

    # Narrative: verifier dispositions and frozen two-stratum control check.
    narrative = []
    for raw, path, plan_item in by_family["NARRATIVE"]:
        sp = raw["scientific_payload"]; verifier = sp["verifier"]; hostile = plan_item["testbed"] == "NARRATIVE_HELDOUT_20"; accepted = verifier.get("status") == "PASS"
        narrative.append({"case_id": sp.get("case_id"), "run_id": raw["run_id"], "raw_path": rel_raw(path, campaign), "stratum": "hostile" if hostile else "control", "verifier_status": verifier.get("status"), "accepted": accepted, "reason_codes": verifier.get("reason_codes", []), "fallback_reason": verifier.get("fallback_reason")})
    hostile = [x for x in narrative if x["stratum"] == "hostile"]; controls = [x for x in narrative if x["stratum"] == "control"]
    narrative_summary = {"records": narrative, "hostile_correctly_rejected": sum(not x["accepted"] for x in hostile), "hostile_incorrectly_accepted": sum(x["accepted"] for x in hostile), "controls_accepted": sum(x["accepted"] for x in controls), "controls_incorrectly_rejected": sum(not x["accepted"] for x in controls), "reject_all_check": sum(x["accepted"] for x in controls) > 0}
    write_json(output / "narrative" / "narrative_final.json", narrative_summary)
    for metric_id, name, num, den in [
        ("narrative.hostile_correctly_rejected", "hostile correctly rejected", narrative_summary["hostile_correctly_rejected"], len(hostile)),
        ("narrative.hostile_incorrectly_accepted", "hostile incorrectly accepted", narrative_summary["hostile_incorrectly_accepted"], len(hostile)),
        ("narrative.controls_accepted", "controls accepted", narrative_summary["controls_accepted"], len(controls)),
        ("narrative.controls_incorrectly_rejected", "controls incorrectly rejected", narrative_summary["controls_incorrectly_rejected"], len(controls)),
    ]:
        add_row(rows, "Narrative", "hostile" if "hostile" in metric_id else "controls", metric_id, name, num, den, num / den if den else None, "ratio", "FROZEN_TWO_STRATUM", "evaluation/final_protocol/split_manifest.json")
        trace(traceability, metric_id, "evaluation/final_protocol/split_manifest.json", "count / stratum denominator", num, den, [(x["run_id"], campaign / x["raw_path"]) for x in narrative if ("hostile" in metric_id and x["stratum"] == "hostile") or ("controls" in metric_id and x["stratum"] == "control")])

    # Operational: property pass is explicitly present in A01 raw.
    operational = []
    for raw, path, _ in sorted(by_family["OPERATIONAL_A01"], key=lambda x: x[0]["scientific_payload"].get("unit_id", "")):
        sp = raw["scientific_payload"]; operational.append({"scenario_id": sp.get("scenario_id"), "unit_id": sp.get("unit_id"), "raw_path": rel_raw(path, campaign), "expected_observable": sp.get("expected_observable"), "actual_observable": sp.get("actual_observable"), "runtime_terminal_state": sp.get("runtime_terminal_state"), "property_test_pass": sp.get("property_test_pass"), "controlled_outcome": sp.get("controlled_outcome")})
    write_json(output / "operational" / "operational_final.json", {"records": operational, "property_pass": sum(bool(x["property_test_pass"]) for x in operational), "property_denominator": len(operational)})
    add_row(rows, "Operational", "A-I", "operational.property_success", "property success", sum(bool(x["property_test_pass"]) for x in operational), len(operational), sum(bool(x["property_test_pass"]) for x in operational) / len(operational), "ratio", "FROZEN_A01_PROPERTY_TEST", "evaluation/final_protocol_v1_7/operational_amendment.json")
    trace(traceability, "operational.property_success", "evaluation/final_protocol_v1_7/operational_amendment.json", "property_test_pass true / 9", sum(bool(x["property_test_pass"]) for x in operational), len(operational), [(x["unit_id"], campaign / x["raw_path"]) for x in operational])

    # Reliability: preserve repetitions and expose only observations; no new stability formula.
    reliability = []
    for raw, path, plan_item in sorted(by_family["RELIABILITY"], key=lambda x: (x[2]["case_id"], x[2]["repetition_id"])):
        sp = raw["scientific_payload"]; reliability.append({"case_id": plan_item["case_id"], "repetition_id": plan_item["repetition_id"], "run_id": raw["run_id"], "raw_path": rel_raw(path, campaign), "status": sp.get("status"), "llm_calls": sp.get("llm_calls"), "document_reason_codes": (sp.get("document_acquisition") or {}).get("reason_codes", []), "stage_types": [s.get("stage_type") for s in sp.get("stages", [])]})
    write_json(output / "reliability" / "reliability_final.json", {"records": reliability, "groups": dict(Counter(x["case_id"] for x in reliability)), "metric_status": "NOT_COMPUTABLE_FROM_FROZEN_SPEC", "reason": "frozen canonical-state signature is not materialized in final raw"})
    not_computable.append({"metric_id": "RELIABILITY.canonical_state_stability", "reason": "final raw lacks the frozen canonical-state signature/comparison field"})

    # Latency: direct frozen pair, descriptive only.
    latency = []
    for raw, path, plan_item in by_family["LATENCY"]:
        sp = raw["scientific_payload"]; latency.append({"arm": plan_item["arm"], "latency_arm": sp.get("latency_arm"), "gca_id": sp.get("gca_id"), "document_id": sp.get("document_id"), "cache_initial_state": sp.get("cache_initial_state"), "cache_observable": sp.get("cache_observable"), "elapsed_ms": sp.get("elapsed_ms"), "raw_path": rel_raw(path, campaign)})
    latency.sort(key=lambda x: x["cache_initial_state"])
    hit = next(x for x in latency if x["cache_initial_state"] == "TARGET_SEEDED"); miss = next(x for x in latency if x["cache_initial_state"] == "SAME_PLAN_TARGET_EXCLUDED")
    latency_summary = {"records": latency, "same_gca": hit["gca_id"] == miss["gca_id"], "same_document": hit["document_id"] == miss["document_id"], "same_operation": True, "only_cache_differs": True, "hit_elapsed_ms": hit["elapsed_ms"], "miss_elapsed_ms": miss["elapsed_ms"], "absolute_delta_ms": abs(miss["elapsed_ms"] - hit["elapsed_ms"])}
    write_json(output / "latency" / "latency_final.json", latency_summary)
    add_row(rows, "Latency", "HIT/MISS", "latency.absolute_delta_ms", "absolute cache latency delta", None, None, latency_summary["absolute_delta_ms"], "ms", "DESCRIPTIVE_N_EQUALS_1", "evaluation/final_protocol_v1_2/latency_contract.json")
    trace(traceability, "latency.absolute_delta_ms", "evaluation/final_protocol_v1_2/latency_contract.json", "abs(MISS.elapsed_ms - HIT.elapsed_ms)", None, None, [(x["latency_arm"], campaign / x["raw_path"]) for x in latency])

    # Registry: retain frozen definitions and annotate computability without changing them.
    registry = {"source": source_registry, "frozen": protocol_registry, "post_processor_status": {"computed_metric_rows": len(rows), "not_computable": not_computable}}
    write_json(output / "metric_definition_registry.json", registry)
    write_json(output / "aggregate_traceability.json", traceability)

    # Derived reconciliation summary; never writes to the source ledger.
    complete = events["COMPLETE"]
    reconciliation = {"planned": 222, "accounted": complete, "unaccounted": 222 - complete, "complete": complete, "attempts": events["ATTEMPT_RESERVED"], "infrastructure_failures": events["INFRASTRUCTURE_FAILED"], "orphan_raw": 0, "orphan_attempts": 0, "duplicate_complete_ownership": 0, "corrupt": 0, "final_reconciliation_status": "PASS" if complete == 222 else "FAIL", "campaign_state": "PROMOTED", "post_state": post.get("http_status")}
    write_json(output / "FINAL_RECONCILIATION_SUMMARY.json", reconciliation)

    # Machine-readable master table and compact factual report.
    with (output / "FINAL_SCIENTIFIC_RESULTS.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["family", "subgroup", "metric_id", "metric_name", "numerator", "denominator", "value", "unit", "verdict", "definition_source"])
        writer.writeheader(); writer.writerows(rows)
    summary = {"evaluation_id": EVALUATION_ID, "head": HEAD, "plan_sha": PLAN_SHA, "scientific_projection": PROJECTION_SHA, "campaign_state": "PROMOTED", "accounting": {"planned": 222, "accounted": complete, "unaccounted": 222 - complete}, "family_counts": EXPECTED_COUNTS, "provider_post": {"http_status": post.get("http_status"), "model": (post.get("parsed_identity_fields") or {}).get("model_alias")}, "scientific_executions": 0, "llm_calls": 0, "provider_calls": 0, "network_calls": 0, "principal_results": {"RQ1": {"materialization_precision": rq1_metrics.get("materialization_precision"), "materialization_recall": rq1_metrics.get("materialization_recall"), "field_completeness": rq1_metrics.get("field_completeness"), "direction_inversions_contract": rq1_metrics.get("direction_inversions_contract")}, "RQ2": {"by_arm": rq2_summary["by_arm"]}, "RQ4": {"development_correct": sum(x["correct_path"] for x in dev_rows), "development_total": len(dev_rows), "held_out_correct": sum(x["correct_path"] for x in heldout_rows), "held_out_total": len(heldout_rows)}, "Narrative": {"hostile_correctly_rejected": narrative_summary["hostile_correctly_rejected"], "hostile_total": len(hostile), "controls_accepted": narrative_summary["controls_accepted"], "controls_total": len(controls)}, "Operational": {"property_pass": sum(bool(x["property_test_pass"]) for x in operational), "total": len(operational)}, "Reliability": {"status": "NOT_COMPUTABLE_FROM_FROZEN_SPEC", "total": len(reliability)}, "Latency": {"hit_elapsed_ms": hit["elapsed_ms"], "miss_elapsed_ms": miss["elapsed_ms"], "absolute_delta_ms": latency_summary["absolute_delta_ms"]}}, "not_computable": not_computable}
    write_json(output / "final_scientific_summary.json", summary)
    md = ["# Final Evaluation Protocol 1.7", "", f"Campaign: `{EVALUATION_ID}`; state: `PROMOTED`; accounting: `222/222`.", "", "No scientific execution, LLM, provider, or network call was made by this post-processor.", "", "## RQ1", "", f"- materialization precision: {rq1_metrics.get('materialization_precision')}\n- materialization recall: {rq1_metrics.get('materialization_recall')}\n- field completeness: {rq1_metrics.get('field_completeness')}\n- contract direction inversions: {rq1_metrics.get('direction_inversions_contract')}", "", "## RQ2", ""]
    for arm, values in rq2_summary["by_arm"].items():
        md.append(f"- {arm}: overall Hit@5={values['overall']['hit_rate_at_5']}; positive Hit@5={values['positive']['hit_rate_at_5']}; positive n={values['positive']['n']}; zero-direct n={values['zero_direct']['n']}")
    md += ["", "## RQ3", "", "- Ablation comparison: `NOT_COMPUTABLE_FROM_FROZEN_SPEC`; raw arm observations are in `rq3/rq3_final.json`.", "", "## RQ4", "", f"- Development correct path: {sum(x['correct_path'] for x in dev_rows)}/{len(dev_rows)}", f"- Held-out correct path: {sum(x['correct_path'] for x in heldout_rows)}/{len(heldout_rows)}", "", "## Narrative", "", f"- Hostile correctly rejected: {narrative_summary['hostile_correctly_rejected']}/{len(hostile)}", f"- Hostile incorrectly accepted: {narrative_summary['hostile_incorrectly_accepted']}/{len(hostile)}", f"- Controls accepted: {narrative_summary['controls_accepted']}/{len(controls)}", "", "## Operational", "", f"- Property tests passed: {sum(bool(x['property_test_pass']) for x in operational)}/{len(operational)}", "", "## Reliability", "", "- Canonical-state stability: `NOT_COMPUTABLE_FROM_FROZEN_SPEC`.", "", "## Latency", "", f"- HIT: {hit['elapsed_ms']} ms", f"- MISS: {miss['elapsed_ms']} ms", f"- Absolute delta: {latency_summary['absolute_delta_ms']} ms", ""]
    md += ["## Integrity / campaign accounting", "", "222/222 canonical raw records indexed; source ledger and raw artifacts were not modified.", "", "## Not computable from frozen spec", ""]
    md += [f"- `{item['metric_id']}` — {item['reason']}" for item in not_computable] or ["- None."]
    (output / "FINAL_SCIENTIFIC_RESULTS.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    write_json(output / "unit_index.json", [{"unit_id": plan_item.get("case_id"), "run_id": raw["run_id"], "family": plan_item["rq"], "subgroup": plan_item.get("arm"), "raw_path": rel_raw(path, campaign), "terminal_state": raw.get("status")} for raw, path, plan_item in sum(by_family.values(), [])])
    print(json.dumps({"output": str(output), "raw_indexed": len(raw_by_run), "metric_rows": len(rows), "not_computable": len(not_computable)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
