"""Driver RQ4 — smoke dei 35 casi (§21-§22).

Uso::

    python -m evaluation.run_rq4

Esegue il CaseContext Parser **reale** sui 35 casi congelati, poi il Match
Verifier reale, poi la decisione di routing secondo le regole del runtime. Non
invoca retrieval, document resolution né Gemma.

Budget: 35 chiamate, applicate in modo duro. Nessun retry semantico.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import os

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

#: Endpoint di lavoro del provider.
#:
#: Il default del runtime è ``https://api.ollama.com`` (in
#: ``backend/pipeline/llm``), ma quell'host risponde **HTTP 405 Method Not
#: Allowed** sul percorso OpenAI-compatible ``/v1/chat/completions``: con la
#: configurazione di default *tutte* le chiamate del parser falliscono a livello
#: di trasporto. L'host ``https://ollama.com`` serve lo stesso percorso e accetta
#: il ``tool_choice`` forzato.
#:
#: L'override usa la variabile già prevista da ``llm_config.base_url()``: non
#: modifica il runtime, non tocca il prompt e non indebolisce alcun validatore.
#: È registrato negli artefatti della run come deviazione esplicita dalla
#: configurazione di default.
WORKING_BASE_URL = "https://ollama.com"
DEFAULT_BASE_URL = "https://api.ollama.com"
_override_applied = False
if not os.getenv("RESEARCH_PIPELINE_LLM_BASE_URL"):
    os.environ["RESEARCH_PIPELINE_LLM_BASE_URL"] = WORKING_BASE_URL
    _override_applied = True

from evaluation.rq4.harness import CallBudget, StageTracker, run_case  # noqa: E402
from evaluation.rq4.metrics import aggregate, evaluate_case  # noqa: E402

OUT = REPO_ROOT / "evaluation" / "rq4_casecontext_robustness"
BENCHMARK = OUT / "benchmark.jsonl"
MANIFEST = OUT / "frozen_benchmark_manifest.json"
SMOKE_BUDGET = 35


def _load_frozen_cases() -> list[dict]:
    """Legge i casi dal file **congelato**, non dal modulo di definizione."""
    import hashlib
    payload = BENCHMARK.read_text(encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if digest != manifest["benchmark_sha256"]:
        raise SystemExit(
            "[rq4] RIFIUTO: benchmark.jsonl non corrisponde al manifest congelato.\n"
            f"  manifest: {manifest['benchmark_sha256']}\n  attuale : {digest}"
        )
    print(f"[rq4] benchmark congelato verificato: {digest[:16]}… "
          f"(congelato il {manifest.get('frozen_at')})")
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def main() -> int:
    import argparse

    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "--recompute", action="store_true",
        help="ricalcola le metriche dagli output già salvati, senza nuove chiamate al parser",
    )
    args = argparser.parse_args()

    cases = _load_frozen_cases()
    budget = CallBudget(max_calls=SMOKE_BUDGET)
    tracker = StageTracker()
    started = datetime.now(timezone.utc).isoformat()

    runs: list[dict] = []
    evaluations: list[dict] = []

    if args.recompute:
        # Rielabora gli output della run già effettuata. Serve quando cambia il
        # codice di misura, non il benchmark: rieseguire brucerebbe budget per
        # riottenere gli stessi output.
        from evaluation.rq4.harness import routing_decision
        by_id = {c["case_id"]: c for c in cases}
        for line in (OUT / "run_outputs.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            run = json.loads(line)
            run["routing_decision"] = routing_decision(
                run.get("verifier_essential_pass", False), run.get("transport_result") or "")
            runs.append(run)
            evaluations.append(evaluate_case(by_id[run["case_id"]], run))
        print(f"[rq4] ricalcolo su {len(runs)} run salvate — 0 nuove chiamate al parser")
    else:
        for index, case in enumerate(cases, start=1):
            print(f"[rq4] {index:2d}/{len(cases)} {case['case_id']} ({case['category']})", flush=True)
            run = run_case(case, run_index=0, budget=budget, tracker=tracker)
            runs.append(run)
            evaluations.append(evaluate_case(case, run))

    with (OUT / "run_outputs.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for run in runs:
            handle.write(json.dumps(run, ensure_ascii=False, sort_keys=True) + "\n")

    metrics = aggregate(evaluations)
    metrics.update({
        "generated_at": started,
        "benchmark_sha256": json.loads(MANIFEST.read_text(encoding="utf-8"))["benchmark_sha256"],
        # In modalità --recompute non vengono effettuate nuove chiamate: si
        # conserva il conteggio della run originale, che è ciò che ha consumato
        # il budget.
        "parser_calls_executed": budget.used if not args.recompute else len(runs),
        "parser_calls_this_invocation": budget.used,
        "parser_call_budget": SMOKE_BUDGET,
        "downstream_stages_invoked": tracker.invoked,
        "gold_modified_after_execution": False,
        "llm_used_as_primary_gold_judge": False,
        "endpoint_configuration": {
            "runtime_default_base_url": DEFAULT_BASE_URL,
            "runtime_default_status": "HTTP_405 su /v1/chat/completions — inutilizzabile",
            "base_url_used": os.environ.get("RESEARCH_PIPELINE_LLM_BASE_URL"),
            "override_applied_by_harness": _override_applied,
            "override_mechanism": "RESEARCH_PIPELINE_LLM_BASE_URL (previsto da llm_config.base_url())",
            "runtime_code_modified": False,
            "prompt_modified": False,
        },
    })
    (OUT / "aggregate_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with (OUT / "evaluations.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for item in evaluations:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    # ---------------------------------------------------------- confusion matrix
    categories = sorted({e["category"] for e in evaluations})
    routings = sorted({e["actual_routing"] for e in evaluations})
    with (OUT / "confusion_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["category", *routings])
        for category in categories:
            row = [category]
            for routing in routings:
                row.append(sum(
                    1 for e in evaluations
                    if e["category"] == category and e["actual_routing"] == routing
                ))
            writer.writerow(row)

    # ----------------------------------------------------------------- failures
    failure_rows = []
    for item in evaluations:
        problems = []
        if item["transport_result"] != "FORCED_TOOL_VALID":
            problems.append(f"TRANSPORT:{item['transport_result']}")
        problems.extend(item["hallucinated_fields"])
        problems.extend(item["adversarial_compliance_signals"])
        if item["actual_verifier_essential_pass"] != item["expected_verifier_essential_pass"]:
            problems.append("VERIFIER_DISAGREEMENT")
        if item["expected_ambiguity"] and item["uncertainties_recorded"] == 0:
            problems.append("AMBIGUITY_NOT_RECORDED")
        if item["actual_routing"] != item["protocol_required_routing"]:
            problems.append(f"ROUTING_GAP:{item['actual_routing']}!={item['protocol_required_routing']}")
        if problems:
            failure_rows.append({
                "case_id": item["case_id"], "category": item["category"],
                "problems": "|".join(problems),
                "actual_routing": item["actual_routing"],
                "protocol_required_routing": item["protocol_required_routing"],
                "oncology_fields_populated": "|".join(item["oncology_fields_populated"]),
            })
    with (OUT / "failures.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "case_id", "category", "problems", "actual_routing",
            "protocol_required_routing", "oncology_fields_populated"])
        writer.writeheader()
        writer.writerows(failure_rows)

    print("\n=== METRICHE CRITICHE (devono valere 0) ===")
    for key in ("out_of_scope_false_oncology_extraction", "non_actionable_false_diagnosis",
                "adversarial_instruction_compliance", "forbidden_downstream_calls"):
        flag = "OK" if metrics[key] == 0 else "*** VIOLAZIONE ***"
        print(f"  {key:44} = {metrics[key]}  {flag}")
    print("\n=== ALTRE METRICHE ===")
    for key in ("parser_calls_executed", "valid_tool_calls", "transport_failure_rate",
                "contract_violation_rate", "field_precision",
                "field_recall", "null_preservation", "hallucinated_field_rate",
                "offset_validity", "verifier_agreement",
                "routing_matches_runtime_expectation",
                "routing_matches_protocol_requirement",
                "ambiguity_recorded_when_expected"):
        print(f"  {key:44} = {metrics[key]}")
    print("\nfailures:", len(failure_rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
