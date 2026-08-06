"""Driver RQ4 — repeatability (§23): 5 casi × 3 run.

Uso::

    python -m evaluation.run_rq4_repeat

Configurazione invariata rispetto allo smoke. Budget complessivo del parser:
35 (smoke) + 15 (qui) = **50**, il massimo previsto dal protocollo.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
if not os.getenv("RESEARCH_PIPELINE_LLM_BASE_URL"):
    os.environ["RESEARCH_PIPELINE_LLM_BASE_URL"] = "https://ollama.com"

from evaluation.rq4.harness import CallBudget, StageTracker, run_case  # noqa: E402
from evaluation.rq4.metrics import evaluate_case  # noqa: E402

OUT = REPO_ROOT / "evaluation" / "rq4_casecontext_robustness"
REPEAT_BUDGET = 15
RUNS_PER_CASE = 3

#: Selezione imposta dal §23: un completo, un ambiguo, "Mi fa male la gamba",
#: un contraddittorio, un avversariale.
SELECTED = (
    "A1-therapy-evaluation-strong-match",
    "C1-anaphora",
    "E1-leg-pain",
    "F2-mutation-status-contradiction",
    "G1-ignore-instructions",
)


def _field_set(case_context) -> tuple:
    if not isinstance(case_context, dict):
        return ("<no-case-context>",)
    populated = []
    if (case_context.get("disease") or {}).get("raw_value"):
        populated.append("disease")
    if case_context.get("biomarkers"):
        populated.append(f"biomarkers:{len(case_context['biomarkers'])}")
    if case_context.get("previous_interventions"):
        populated.append(f"previous:{len(case_context['previous_interventions'])}")
    if (case_context.get("target_intervention") or {}).get("raw_value"):
        populated.append("target_intervention")
    return tuple(sorted(populated))


def _output_signature(case_context) -> str:
    if not isinstance(case_context, dict):
        return "<no-case-context>"
    return json.dumps(case_context, ensure_ascii=False, sort_keys=True)


def main() -> int:
    cases = {
        json.loads(line)["case_id"]: json.loads(line)
        for line in (OUT / "benchmark.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    missing = [c for c in SELECTED if c not in cases]
    if missing:
        raise SystemExit(f"casi assenti dal benchmark congelato: {missing}")

    budget = CallBudget(max_calls=REPEAT_BUDGET)
    tracker = StageTracker()
    started = datetime.now(timezone.utc).isoformat()
    runs: list[dict] = []

    for case_id in SELECTED:
        case = cases[case_id]
        for run_index in range(RUNS_PER_CASE):
            print(f"[rq4-repeat] {case_id} run {run_index + 1}/{RUNS_PER_CASE}", flush=True)
            run = run_case(case, run_index=run_index, budget=budget, tracker=tracker)
            run["evaluation"] = evaluate_case(case, run)
            runs.append(run)

    by_case: dict[str, list[dict]] = {}
    for run in runs:
        by_case.setdefault(run["case_id"], []).append(run)

    per_case = {}
    for case_id, items in by_case.items():
        signatures = [_output_signature(r.get("case_context")) for r in items]
        field_sets = [_field_set(r.get("case_context")) for r in items]
        routings = [r["routing_decision"] for r in items]
        verifiers = [r["verifier_essential_pass"] for r in items]
        transports = [r["transport_result"] for r in items]
        per_case[case_id] = {
            "runs": len(items),
            "exact_output_agreement": len(set(signatures)) == 1,
            "distinct_outputs": len(set(signatures)),
            "field_set_agreement": len(set(field_sets)) == 1,
            "field_sets": [list(f) for f in field_sets],
            "routing_agreement": len(set(routings)) == 1,
            "routings": routings,
            "verifier_agreement": len(set(verifiers)) == 1,
            "verifier_results": verifiers,
            "transport_results": transports,
            "latency_ms": [r["latency_ms"] for r in items],
        }

    total = len(per_case)
    summary = {
        "generated_at": started,
        "cases": SELECTED,
        "runs_per_case": RUNS_PER_CASE,
        "parser_calls_executed": budget.used,
        "parser_call_budget_this_phase": REPEAT_BUDGET,
        "cumulative_parser_calls": 35 + budget.used,
        "cumulative_budget": 50,
        "forbidden_downstream_calls": tracker.forbidden_calls,
        "exact_output_agreement_rate": round(
            sum(1 for v in per_case.values() if v["exact_output_agreement"]) / total, 4),
        "field_set_agreement_rate": round(
            sum(1 for v in per_case.values() if v["field_set_agreement"]) / total, 4),
        "routing_agreement_rate": round(
            sum(1 for v in per_case.values() if v["routing_agreement"]) / total, 4),
        "verifier_agreement_rate": round(
            sum(1 for v in per_case.values() if v["verifier_agreement"]) / total, 4),
        "transport_outcomes": dict(Counter(r["transport_result"] for r in runs)),
        "per_case": per_case,
    }
    (OUT / "repeatability.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with (OUT / "repeatability_runs.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for run in runs:
            handle.write(json.dumps(run, ensure_ascii=False, sort_keys=True) + "\n")

    print("\n=== REPEATABILITY ===")
    for key in ("exact_output_agreement_rate", "field_set_agreement_rate",
                "routing_agreement_rate", "verifier_agreement_rate"):
        print(f"  {key:32} = {summary[key]}")
    print(f"  parser calls (cumulative)        = {summary['cumulative_parser_calls']}/50")
    for case_id, value in per_case.items():
        print(f"  {case_id:40} exact={value['exact_output_agreement']} "
              f"fields={value['field_set_agreement']} routing={value['routing_agreement']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
