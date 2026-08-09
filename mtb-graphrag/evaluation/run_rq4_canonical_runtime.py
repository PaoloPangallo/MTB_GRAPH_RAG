"""RQ4 attraverso il runtime canonico — chiusura di ISS-005.

``run_runtime_v3_integration.rq4_rerun`` misura ``casecontext.pipeline.run``,
cioè la catena deterministica, e lo dichiara esplicitamente nel proprio codice:

    # Nessuno stage downstream è raggiungibile da questo harness: non li importa.

La claim di RQ4 riguarda però il **runtime**: «un input non eleggibile viene
fermato prima di produrre retrieval». Fra la catena e il runtime c'era la
giunzione in cui viveva ISS-001, e nessuno dei due percorsi la attraversava.

Questo script esegue gli **stessi 35 casi congelati** attraverso
``orchestrator.run_case``, contando le chiamate a valle invece di dedurle, e
confronta i due percorsi.

Non riscrive nulla di storico: scrive in ``evaluation/rq4_canonical_runtime/``.
``evaluation/rq4_casecontext_robustness/`` e ``evaluation/runtime_v3_integration/``
restano intatti.

    python -m evaluation.run_rq4_canonical_runtime [--out DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.agentic.ledger import EventLedger  # noqa: E402
from backend.research_pipeline import execution_mode as em  # noqa: E402
from backend.research_pipeline import orchestrator  # noqa: E402
from backend.research_pipeline.casecontext.pipeline import run as run_chain  # noqa: E402
from backend.research_pipeline.contracts import is_controlled_stop  # noqa: E402
from backend.research_pipeline.retrieval import kg_retrieval  # noqa: E402

RQ4 = REPO_ROOT / "evaluation" / "rq4_casecontext_robustness"
DEFAULT_OUT = REPO_ROOT / "evaluation" / "rq4_canonical_runtime"

#: Categorie che non devono mai raggiungere il retrieval.
MUST_NOT_RETRIEVE = {
    "OUT_OF_SCOPE": "out_of_scope_retrieval",
    "NON_ACTIONABLE_MEDICAL_INPUT": "non_actionable_retrieval",
    "CONTRADICTORY": "contradictory_case_retrieval",
}


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _verify_frozen_benchmark() -> tuple[dict[str, dict], str]:
    manifest = json.loads((RQ4 / "frozen_benchmark_manifest.json").read_text(encoding="utf-8"))
    payload = (RQ4 / "benchmark.jsonl").read_text(encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if digest != manifest["benchmark_sha256"]:
        raise SystemExit("[rq4-canonical] RIFIUTO: il benchmark congelato e' cambiato.")
    cases = {json.loads(line)["case_id"]: json.loads(line)
             for line in payload.splitlines() if line.strip()}
    return cases, digest


def _run_through_orchestrator(case, recorded_run, ledger) -> dict:
    """Un caso attraverso ``orchestrator.run_case``, con il parser rigiocato.

    Il parser **non** viene richiamato: si rigioca l'output registrato nella run
    congelata, così il confronto con il percorso della catena è a parità di
    CaseContext e nessuna chiamata al modello viene spesa. È la stessa scelta
    che fa ``rq4_rerun``.
    """
    transport_ok = recorded_run["transport_result"] == "FORCED_TOOL_VALID"
    case_context = recorded_run.get("case_context")

    calls = Counter()
    real_retrieve = orchestrator.retrieval_mod.retrieve_frozen_bundles
    real_select = orchestrator.select_papers_for_association

    def counting_retrieve(cc):
        calls["retrieval"] += 1
        return real_retrieve(cc)

    def counting_select(association, units):
        calls["paper_selection"] += 1
        return real_select(association, units)

    def counting_enricher(*args, **kwargs):
        calls["enrichment"] += 1
        return {"transport_result": "V2_TRANSPORT_VALID", "enrichment": None}

    def replayed_parser(budget, case_id, clinical_text):
        return {
            "transport_result": recorded_run["transport_result"],
            "case_context_raw": case_context or {},
            "model": recorded_run.get("model") or "REPLAYED_FROM_FROZEN_RUN",
            "prompt_version": recorded_run.get("prompt_version") or "rq4-frozen/1.0",
        }

    orchestrator.retrieval_mod.retrieve = counting_retrieve
    orchestrator.select_papers_for_association = counting_select
    run, error = None, None
    try:
        run = orchestrator.run_case(
            case_id=case["case_id"], clinical_text=case["text"],
            call_parser_fn=replayed_parser, call_enricher_fn=counting_enricher,
            source_units_by_id={}, budget=None, ledger=ledger,
            research_frozen_artifacts=True, document_runtime=None,
            validate_fn=lambda t, e, **kw: {"outcome": "ENRICHMENT_ABSTAINED"},
        )
    except Exception as exc:  # noqa: BLE001 — un crash e' un risultato da registrare
        error = f"{type(exc).__name__}: {exc}"
    finally:
        orchestrator.retrieval_mod.retrieve = real_retrieve
        orchestrator.select_papers_for_association = real_select

    # Percorso precedente, sugli stessi input, per il confronto.
    chain = run_chain(case["text"], case_context, transport_ok=transport_ok)
    chain_status = chain["eligibility"]["eligibility_status"]
    chain_eligible = chain["eligibility"]["eligible"]

    stages = list(run.stages) if run else []
    gate = next((s for s in stages
                 if s.stage_id == "stage_3b_pre_retrieval_eligibility_gate"), None)
    runtime_status = (gate.output_preview or {}).get("eligibility_status") if gate else None

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "transport_result": recorded_run["transport_result"],
        # --- percorso precedente: casecontext.pipeline.run ---
        "chain_eligibility_status": chain_status,
        "chain_eligible": chain_eligible,
        # --- percorso canonico: orchestrator.run_case ---
        "runtime_eligibility_status": runtime_status,
        "runtime_run_status": run.status if run else "RAISED",
        "runtime_stopped_at": run.stopped_at if run else None,
        "runtime_controlled_stop": is_controlled_stop(run.stopped_at) if run else False,
        "runtime_exception": error,
        "runtime_stages_executed": [s.stage_id for s in stages if s.status != "SKIPPED"],
        # --- chiamate a valle MISURATE, non dedotte ---
        "retrieval_called": calls["retrieval"],
        "paper_selection_called": calls["paper_selection"],
        "enrichment_called": calls["enrichment"],
        "forbidden_downstream_calls": (
            0 if chain_eligible
            else calls["retrieval"] + calls["paper_selection"] + calls["enrichment"]),
        "paths_agree": (runtime_status == chain_status) if runtime_status else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="directory di output (default: evaluation/rq4_canonical_runtime)")
    args = parser.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    cases, digest = _verify_frozen_benchmark()
    print(f"[rq4-canonical] benchmark congelato verificato: {digest[:16]}...")
    runs = _load_jsonl(RQ4 / "run_outputs.jsonl")

    rows: list[dict] = []
    metrics: Counter = Counter()
    by_category: dict[str, Counter] = defaultdict(Counter)

    with tempfile.TemporaryDirectory() as tmp:
        ledger = EventLedger(Path(tmp) / "rq4_canonical.sqlite3")
        for recorded in runs:
            case = cases[recorded["case_id"]]
            row = _run_through_orchestrator(case, recorded, ledger)
            rows.append(row)

            by_category[row["category"]][row["runtime_eligibility_status"] or
                                         row["runtime_stopped_at"] or "NO_GATE"] += 1

            if row["runtime_exception"]:
                metrics["runtime_exceptions"] += 1
            # Un caso il cui trasporto del parser e' fallito si ferma allo stage 2
            # e NON raggiunge il gate: non e' uno stop del gate mancato, e' un
            # guasto del modello. Contarlo fra gli stop falliti misurerebbe il
            # denominatore sbagliato. E' riportato a parte (ISS-012, P2).
            reached_gate = row["transport_result"] == "FORCED_TOOL_VALID"
            if not reached_gate:
                metrics["parser_transport_failures"] += 1

            if not row["chain_eligible"]:
                metrics["noneligible_cases"] += 1
                metrics["noneligible_retrieval_calls"] += row["retrieval_called"]
                metrics["forbidden_downstream_calls"] += row["forbidden_downstream_calls"]
                if not reached_gate:
                    metrics["noneligible_not_reaching_gate"] += 1
                elif row["runtime_run_status"] == "RAISED":
                    metrics["expected_controlled_stops_failed"] += 1
                elif row["runtime_run_status"] != "STOPPED":
                    metrics["expected_controlled_stops_failed"] += 1
                elif not row["runtime_controlled_stop"]:
                    metrics["stops_classified_as_failure"] += 1
                else:
                    metrics["controlled_stops_ok"] += 1
            else:
                metrics["eligible_cases"] += 1
                if MUST_NOT_RETRIEVE.get(row["category"]):
                    metrics[MUST_NOT_RETRIEVE[row["category"]]] += 1
            if row["paths_agree"] is False:
                metrics["path_disagreements"] += 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_sha256": digest,
        "cases": len(rows),
        "evaluation_path": "backend.research_pipeline.orchestrator.run_case",
        "compared_against": "backend.research_pipeline.casecontext.pipeline.run",
        "parser": "REPLAYED_FROM_FROZEN_RUN — nessuna chiamata al modello",
        "execution_mode": "REPLAY",
        "downstream_calls_measured": True,
        **{k: metrics[k] for k in (
            "noneligible_cases", "eligible_cases", "controlled_stops_ok",
            "noneligible_retrieval_calls", "forbidden_downstream_calls",
            "expected_controlled_stops_failed", "stops_classified_as_failure",
            "runtime_exceptions", "path_disagreements",
            "parser_transport_failures", "noneligible_not_reaching_gate",
            "out_of_scope_retrieval", "non_actionable_retrieval", "contradictory_case_retrieval")},
        "note_parser_transport": (
            "I casi con transport != FORCED_TOOL_VALID si fermano allo stage 2 e non "
            "raggiungono il gate: sono guasti del modello (ISS-012, P2), non stop del "
            "gate mancati, e sono contati a parte."),
        "eligibility_by_category": {k: dict(v) for k, v in sorted(by_category.items())},
    }

    (out / "rq4_canonical_runtime_results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (out / "rq4_canonical_runtime_metrics.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"[rq4-canonical] {len(rows)} casi attraverso orchestrator.run_case")
    for key in ("noneligible_cases", "controlled_stops_ok", "noneligible_retrieval_calls",
                "forbidden_downstream_calls", "expected_controlled_stops_failed",
                "runtime_exceptions", "path_disagreements",
                "parser_transport_failures", "noneligible_not_reaching_gate"):
        print(f"  {key:38} = {metrics[key]}")
    print(f"[rq4-canonical] -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
