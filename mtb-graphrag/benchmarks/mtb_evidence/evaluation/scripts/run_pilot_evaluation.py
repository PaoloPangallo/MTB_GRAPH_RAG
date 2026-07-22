"""Valutazione del pilota sulle due architetture verificabili.

    cd mtb-graphrag
    PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/\\
run_pilot_evaluation.py \\
        --selected-models benchmarks/mtb_evidence/model_selection/results/v1/\\
selected_models.json \\
        --architectures deterministic agentic \\
        --seeds 20240517 13 991 \\
        --output benchmarks/mtb_evidence/evaluation/results/pilot_v1

Usa `build_run` di `backend/comparison/live_runs.py`, che seleziona
`FixedPlanStrategy` o `AgenticPlanStrategy` e chiama `run_verified_pipeline`. **Non
esiste un runner parallelo**: reimplementare la pipeline renderebbe la differenza fra
le due architetture non attribuibile alla sola strategia di raccolta, che e' l'unica
cosa che questo esperimento vuole misurare.

Ogni run ha una `run_key` e viene scritta in modo atomico, quindi `--resume` riprende
esattamente da dove si era interrotto.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from benchmarks.mtb_evidence.evaluation import case_mapping, pilot_extraction  # noqa: E402
from benchmarks.mtb_evidence.evaluation.aggregation import (  # noqa: E402
    _write_csv,
    aggregate,
    write_aggregate_metrics,
    write_case_metrics,
    write_loss_decomposition,
)
from benchmarks.mtb_evidence.evaluation.clinical_gold import load_clinical_gold  # noqa: E402
from benchmarks.mtb_evidence.evaluation.contracts import (  # noqa: E402
    ARCHITECTURE_AGENTIC,
    ARCHITECTURE_DETERMINISTIC,
    BRANCH_VERIFIED,
    CaseEvaluation,
    SnapshotGoldCase,
    SnapshotGoldClaim,
)
from benchmarks.mtb_evidence.evaluation.loss_decomposition import decompose_case  # noqa: E402
from benchmarks.mtb_evidence.evaluation.metrics.applicability import (  # noqa: E402
    applicability_metrics,
)
from benchmarks.mtb_evidence.evaluation.metrics.kg_coverage import (  # noqa: E402
    all_coverage_metrics,
)
from benchmarks.mtb_evidence.evaluation.metrics.orchestration import (  # noqa: E402
    orchestration_metrics,
)
from benchmarks.mtb_evidence.evaluation.metrics.report_fidelity import (  # noqa: E402
    report_metrics,
)
from benchmarks.mtb_evidence.evaluation.metrics.retrieval_fidelity import (  # noqa: E402
    retrieval_metrics,
)
from benchmarks.mtb_evidence.evaluation.source_profiles import default_repository  # noqa: E402
from benchmarks.mtb_evidence.model_selection.run_identity import (  # noqa: E402
    SKIP,
    RunLedger,
    RunIdentity,
    case_hash,
    source_profile_hash,
)
from benchmarks.mtb_evidence.pilot.audit_lib.aliases import build_alias_table  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    append_jsonl_atomic,
    read_jsonl,
    write_json,
)

DEFAULT_GOLD = Path("benchmarks/mtb_evidence/evaluation/data/clinical_gold_v1.jsonl")
DEFAULT_DATA = Path("benchmarks/mtb_evidence/evaluation/data")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clinical-gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--snapshot-gold", type=Path, default=None)
    parser.add_argument("--selected-models", type=Path, default=None)
    parser.add_argument(
        "--architectures", nargs="+",
        default=[ARCHITECTURE_DETERMINISTIC, ARCHITECTURE_AGENTIC],
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[20240517, 13, 991])
    parser.add_argument("--execution-mode", default="live")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--cases", nargs="*", default=None)
    return parser.parse_args(argv)


def _load_snapshot_gold(path: Path | None) -> dict[str, SnapshotGoldCase]:
    target = path
    if target is None:
        candidates = sorted(DEFAULT_DATA.glob("snapshot_gold_*.jsonl"))
        if not candidates:
            raise SystemExit("snapshot gold non trovato: esegui build_snapshot_gold.py")
        target = candidates[0]
    cases: dict[str, SnapshotGoldCase] = {}
    for payload in read_jsonl(target):
        items = tuple(
            SnapshotGoldClaim(
                **{
                    key: (tuple(value) if isinstance(value, list) else value)
                    for key, value in item.items()
                    if key != "is_retrievable"
                }
            )
            for item in payload["items"]
        )
        cases[payload["case_id"]] = SnapshotGoldCase(
            case_id=payload["case_id"],
            snapshot_fingerprint=payload["snapshot_fingerprint"],
            items=items,
            retrievable_therapies=tuple(payload["retrievable_therapies"]),
            retrievable_pmids=tuple(payload["retrievable_pmids"]),
            retrievable_nct_ids=tuple(payload["retrievable_nct_ids"]),
            expected_abstention=payload["expected_abstention"],
            notes=tuple(payload["notes"]),
        )
    return cases


def _selected_models(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "planner": payload.get("planner_model") or "",
        "verifier": payload.get("verifier_model") or "",
        "report": payload.get("report_model") or "",
        "revisions": payload.get("model_revisions", {}),
    }


def _identity(case_id, architecture, seed, case_digest, profiles_digest, models):
    """Identita' di una run del pilota.

    Il `task_id` porta l'architettura: cambiare strategia di raccolta produce una run
    diversa, non una replica della stessa.
    """
    return RunIdentity(
        requested_model_tag=models.get("planner", ""),
        effective_api_model=models.get("planner", ""),
        model_revision=str(models.get("revisions", {}).get(models.get("planner", ""), "")),
        role="pipeline",
        case_id=case_id,
        task_id=f"{case_id}::{architecture}",
        seed=seed,
        prompt_version="v1",
        schema_version="v1",
        case_hash=case_digest,
        source_profile_hash=profiles_digest,
        temperature=0.0,
        num_ctx=16384,
    )


def check_snapshot_preconditions(expected_fingerprint: str) -> tuple[bool, str]:
    """Verifica che il grafo sia raggiungibile e sia **quello giusto**.

    Senza questo controllo la run produce risultati plausibili e privi di
    significato. Con Neo4j irraggiungibile ogni strumento solleva un'eccezione, la
    raccolta resta vuota, e un caso di astensione come N1 risulta `correctly_abstained`
    — non perche' il traversal sia vuoto, ma perche' non e' mai stato eseguito. E'
    successo davvero durante lo sviluppo di questo runner.

    Il fingerprint va confrontato per la stessa ragione: un grafo diverso da quello su
    cui e' stato costruito lo snapshot gold renderebbe il confronto senza senso.
    """
    from benchmarks.mtb_evidence.pilot.audit_lib.graph_client import (
        GraphUnavailable,
        Neo4jGraphClient,
    )
    from benchmarks.mtb_evidence.pilot.audit_lib.snapshot import (
        build_fingerprint_statistics,
        compute_fingerprint,
    )

    client = Neo4jGraphClient()
    try:
        client.run("RETURN 1 AS ok", {})
    except GraphUnavailable as error:
        return False, (
            f"Neo4j non raggiungibile: {error}\n"
            "  Le run non vengono eseguite: con il grafo giu' ogni strumento fallisce, "
            "la raccolta resta vuota e i casi di astensione risultano corretti per il "
            "motivo sbagliato."
        )
    if not expected_fingerprint:
        return True, "nessun fingerprint atteso: confronto saltato"
    try:
        actual = compute_fingerprint(build_fingerprint_statistics(client))
    except GraphUnavailable as error:
        return False, f"fingerprint non calcolabile: {error}"
    if actual != expected_fingerprint:
        return False, (
            "lo snapshot non corrisponde a quello dello snapshot gold.\n"
            f"  atteso: {expected_fingerprint}\n"
            f"  trovato: {actual}\n"
            "  Ricostruisci lo snapshot gold, oppure ripristina il grafo: confrontare "
            "predizioni con un gold costruito su un altro grafo non misura nulla."
        )
    return True, f"snapshot verificato: {actual[:16]}"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    timestamp = datetime.now(timezone.utc).isoformat()

    from backend.comparison.live_runs import build_run
    from backend.comparison.service import (
        _build_dossier,
        _checks_from_verifications,
        _render_verified_report,
        _source_profile_cache,
    )
    from backend.pipeline.control.verification.source_port import PubMedSourceVerifier

    cases = list(load_clinical_gold(args.clinical_gold))
    if args.cases:
        cases = [case for case in cases if case.case_id in set(args.cases)]
    snapshot_gold = _load_snapshot_gold(args.snapshot_gold)
    profiles = default_repository()
    alias_table = build_alias_table()
    models = _selected_models(args.selected_models)

    profiles_digest = source_profile_hash(list(profiles))
    case_digests = {case.case_id: case_hash(case) for case in cases}

    runs_path = args.output / "case_runs.jsonl"
    ledger = RunLedger(read_jsonl(runs_path) if args.resume else [])
    fingerprint = next(iter(snapshot_gold.values())).snapshot_fingerprint if snapshot_gold else ""

    if args.execution_mode == "live":
        ok, detail = check_snapshot_preconditions(fingerprint)
        print(f"Precondizioni snapshot: {detail}")
        if not ok:
            print("\nERRORE: precondizioni non soddisfatte, nessuna run eseguita.",
                  file=sys.stderr)
            return 3

    evaluations: list[CaseEvaluation] = []
    errors: list[dict] = []
    executed = skipped = 0

    for case in cases:
        snapshot = snapshot_gold.get(case.case_id)
        if snapshot is None:
            errors.append({"case_id": case.case_id, "error": "snapshot gold mancante"})
            continue
        coverage = all_coverage_metrics(case, snapshot)

        for architecture in args.architectures:
            for seed in args.seeds:
                identity = _identity(
                    case.case_id, architecture, seed,
                    case_digests[case.case_id], profiles_digest, models,
                )
                decision = ledger.decide(identity)
                if decision.action == SKIP:
                    skipped += 1
                    continue

                request = case_mapping.build_request(
                    case, execution_mode=args.execution_mode
                )
                started = time.perf_counter()
                try:
                    _, result = build_run(
                        request,
                        architecture,
                        source_verifier=PubMedSourceVerifier(
                            profile_cache=_source_profile_cache()
                        ),
                        build_dossier=_build_dossier,
                        build_claim_checks=_checks_from_verifications,
                        render_verified=_render_verified_report,
                    )
                except Exception as error:  # la run fallisce, l'esperimento no
                    errors.append(
                        {
                            "case_id": case.case_id,
                            "architecture": architecture,
                            "seed": seed,
                            "run_key": identity.run_key,
                            "error_class": type(error).__name__,
                            "error": str(error)[:400],
                        }
                    )
                    append_jsonl_atomic(
                        runs_path,
                        {
                            **identity.as_dict(),
                            "architecture": architecture,
                            "completed": True,
                            "valid_output": False,
                            "error_class": type(error).__name__,
                            "error": str(error)[:400],
                        },
                    )
                    print(f"  {case.case_id:30s} {architecture:14s} seed={seed} FALLITA")
                    continue

                elapsed = (time.perf_counter() - started) * 1000
                retrieval = pilot_extraction.retrieval_from_result(result, alias_table)
                report = pilot_extraction.report_from_result(
                    result, BRANCH_VERIFIED, alias_table
                )
                telemetry = pilot_extraction.run_telemetry(result, elapsed)

                metrics = dict(coverage)
                metrics.update(retrieval_metrics(case, snapshot, retrieval))
                metrics.update(
                    report_metrics(
                        report, retrieval, profiles,
                        expected_abstention=case.expected_abstention,
                        expected_human_review=case.expected_human_review,
                    )
                )
                metrics.update(applicability_metrics(case, report, profiles))
                metrics.update(
                    orchestration_metrics(
                        case, retrieval,
                        actions=[{"tool": tool} for tool in retrieval.tools_called],
                        known_tools=telemetry["mandatory_tools"] + list(retrieval.tools_called),
                        runs=[{"run_id": telemetry["run_id"],
                               "used_fallback": bool(telemetry["fallback_reason"])}],
                        latencies_ms=[telemetry["planner_elapsed_ms"]],
                    )
                )
                loss = decompose_case(case, snapshot, retrieval, report)

                evaluations.append(
                    CaseEvaluation(
                        case_id=case.case_id, category=case.category,
                        architecture=architecture, metrics=metrics, loss=loss,
                    )
                )
                append_jsonl_atomic(
                    runs_path,
                    {
                        **identity.as_dict(),
                        "architecture": architecture,
                        "completed": True,
                        "valid_output": True,
                        "snapshot_fingerprint": fingerprint,
                        "retrieval": retrieval.as_dict(),
                        "report": report.as_dict(),
                        "telemetry": telemetry,
                        "loss_decomposition": [item.as_dict() for item in loss],
                    },
                )
                executed += 1
                print(
                    f"  {case.case_id:30s} {architecture:14s} seed={seed} "
                    f"tool={len(retrieval.tools_called)} planner={retrieval.planner_calls} "
                    f"terapie={len(retrieval.therapies)}",
                    flush=True,
                )

    output = args.output
    if evaluations:
        write_case_metrics(output / "case_metrics.csv", evaluations)
        write_loss_decomposition(output / "loss_decomposition.csv", evaluations)
        aggregates = {
            architecture: aggregate(
                [e for e in evaluations if e.architecture == architecture],
                scope=architecture,
            )
            for architecture in args.architectures
        }
        aggregates["all"] = aggregate(evaluations, scope="all")
        write_aggregate_metrics(output / "aggregate_metrics.csv", aggregates)
        for name, prefixes in (
            ("kg_coverage.csv", ("entity_", "therapy_coverage", "pmid_coverage",
                                 "nct_coverage", "claim_coverage", "qualifier_")),
            ("retrieval_fidelity.csv", ("therapy_p", "therapy_r", "therapy_f",
                                        "pmid_p", "pmid_r", "pmid_f", "nct_",
                                        "negative_case", "required_tool", "unnecessary_")),
            ("report_fidelity.csv", ("claim_p", "claim_r", "citation_", "qualifier_pres",
                                     "context_om", "unsupported_", "contradiction_",
                                     "structural_cov", "abstention_", "human_review_")),
            ("applicability_metrics.csv", ("documentary_", "applicability_", "setting_",
                                           "therapy_line_", "prior_therapy_",
                                           "missing_context", "compatible_", "not_compatible_")),
            ("orchestration_metrics.csv", ("task_completion", "conditional_", "stop_",
                                           "valid_action", "planner_", "fallback_",
                                           "run_to_run", "median_")),
        ):
            from benchmarks.mtb_evidence.evaluation.aggregation import write_metric_family

            write_metric_family(output / name, evaluations, prefixes)

    append_errors(output, errors)
    write_json(
        output / "run_manifest.json",
        {
            "generated_at_utc": timestamp,
            "snapshot_fingerprint": fingerprint,
            "architectures": args.architectures,
            "seeds": args.seeds,
            "execution_mode": args.execution_mode,
            "cases": [case.case_id for case in cases],
            "selected_models": models,
            "runs_executed": executed,
            "runs_skipped_by_resume": skipped,
            "runs_failed": len(errors),
            "case_mapping": case_mapping.mapping_manifest(),
            "pipeline_entrypoint": (
                "backend.comparison.live_runs.build_run -> run_verified_pipeline; "
                "nessun runner parallelo"
            ),
        },
    )

    print(f"\nRun eseguite: {executed}, saltate: {skipped}, fallite: {len(errors)}")
    print(f"Output: {output}")
    return 0


def append_errors(output: Path, errors: list[dict]) -> None:
    from benchmarks.mtb_evidence.pilot.audit_lib.serialize import write_jsonl

    write_jsonl(output / "errors.jsonl", errors)


if __name__ == "__main__":
    raise SystemExit(main())
