"""Selezione del modello sui soli quattro casi development del pilota.

    cd mtb-graphrag
    PYTHONPATH=. python benchmarks/mtb_evidence/model_selection/scripts/\\
run_model_selection.py \\
        --models current qwen3:14b gemma4:12b gemma4:31b-cloud \\
        --roles planner verifier free_report \\
        --seeds 20240517 13 991 \\
        --output benchmarks/mtb_evidence/model_selection/results/v1

Un modello non disponibile viene saltato con la ragione registrata, non sostituito.
Un modello cloud non autenticato non interrompe l'esperimento: il suo fallimento
finisce in `failures.jsonl` e gli altri proseguono.

Nessun prompt contiene claim del gold, PMID attesi, etichette di applicabilita' o
decisioni dell'audit: `assert_no_leakage` verifica ogni prompt prima dell'invio e
solleva se qualcosa passa.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.pipeline.llm.model_registry import (  # noqa: E402
    ModelRegistry,
    assert_experiment_safe,
)
from backend.pipeline.llm.credentials import CredentialPool  # noqa: E402
from backend.pipeline.llm.ollama_adapter import OllamaClient  # noqa: E402
from benchmarks.mtb_evidence.evaluation.clinical_gold import load_clinical_gold  # noqa: E402
from benchmarks.mtb_evidence.evaluation.source_profiles import default_repository  # noqa: E402
from benchmarks.mtb_evidence.model_selection import harness, roles, scoring  # noqa: E402
from benchmarks.mtb_evidence.model_selection.run_identity import (  # noqa: E402
    SKIP,
    RunLedger,
    build_identity,
    case_hash,
    identity_manifest,
    source_profile_hash,
)
from benchmarks.mtb_evidence.pilot.audit_lib.normalize import norm_pmid_set  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    append_jsonl_atomic,
    read_jsonl,
    write_json,
    write_jsonl,
    write_text,
)


def _outcome_from_row(row) -> harness.TaskOutcome:
    """Ricostruisce un esito gia' su disco, per calcolare le metriche senza rieseguire."""
    return harness.TaskOutcome(
        task_id=str(row.get("task_id", "")),
        role=str(row.get("role", "")),
        case_id=str(row.get("case_id", "")),
        model=str(row.get("requested_model_tag") or row.get("model") or ""),
        seed=row.get("seed"),
        valid_output=bool(row.get("valid_output")),
        parsed=row.get("parsed"),
        raw_outputs=tuple(row.get("raw_outputs") or ()),
        retries=int(row.get("retries") or 0),
        structured_output_mode=str(row.get("structured_output_mode", "")),
        latency_ms=float(row.get("latency_ms") or 0.0),
        error=str(row.get("error", "")),
        error_class=str(row.get("error_class", "")),
        completed=True,
    )

DEFAULT_GOLD = Path("benchmarks/mtb_evidence/evaluation/data/clinical_gold_v1.jsonl")
DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/pilot/audit")

# I quattro casi development. Il test set non viene mai toccato qui.
DEVELOPMENT_CASES = (
    "PILOT-K1-FGFR2-iCCA",
    "PILOT-A2-ALK-G1202R",
    "PILOT-C1-EGFR-L858R-CONTEXT",
    "PILOT-N1-RMI2-SNAPSHOT",
)

ROLE_ALIASES = {"verifier": roles.VERIFIER, "source_verifier": roles.VERIFIER}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--roles", nargs="+", default=list(roles.ROLES))
    parser.add_argument("--seeds", nargs="+", type=int, default=[20240517, 13, 991])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clinical-gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--num-ctx", type=int, default=16384)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="riusa le run gia' presenti la cui identita' e' compatibile",
    )
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _frozen_records(audit_dir: Path, case_id: str) -> list[dict]:
    """I record del grafo gia' recuperati dall'audit, identici per ogni modello."""
    import json

    path = audit_dir / case_id / "normalized_records.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _probe_entitlement(client, model: str) -> tuple[bool, str]:
    """Verifica che l'account possa davvero usare il modello.

    Una chiamata minima: se il provider la nega per autorizzazione, il modello va
    escluso operativamente invece di accumulare fallimenti che sembrerebbero suoi.
    """
    from backend.pipeline.llm.ollama_adapter import OllamaUnavailable

    try:
        client.chat(model, [{"role": "user", "content": "ok"}], temperature=0.0)
    except OllamaUnavailable as error:
        message = str(error)
        if "403" in message or "401" in message:
            return False, f"accesso non autorizzato al modello: {message[:160]}"
        return False, f"modello non utilizzabile: {message[:160]}"
    except Exception as error:  # pragma: no cover - guasto imprevisto
        return False, f"probe fallito: {type(error).__name__}: {error}"[:200]
    return True, ""


def _write_csv(path: Path, columns, rows) -> Path:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buffer.getvalue(), encoding="utf-8", newline="\n")
    return path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    timestamp = args.timestamp or datetime.now(timezone.utc).isoformat()
    requested_roles = [ROLE_ALIASES.get(role, role) for role in args.roles]

    cases = [
        case
        for case in load_clinical_gold(args.clinical_gold)
        if case.case_id in DEVELOPMENT_CASES
    ]
    profiles = list(default_repository())
    registry = ModelRegistry(probe=True)

    # I compiti sono costruiti una volta sola: tutti i modelli ricevono gli stessi
    # prompt, con gli stessi record nello stesso ordine.
    tasks: dict[str, list[roles.RoleTask]] = {role: [] for role in requested_roles}
    available_pmids: dict[str, set[str]] = {}
    for case in cases:
        records = _frozen_records(args.audit_dir, case.case_id)
        available_pmids[case.case_id] = {
            pmid
            for record in records
            for pmid in norm_pmid_set(record.get("pmids") or [])
        }
        if roles.PLANNER in tasks:
            tasks[roles.PLANNER].append(roles.planner_task(case))
        if roles.VERIFIER in tasks:
            tasks[roles.VERIFIER].extend(roles.verifier_tasks(case, profiles))
        if roles.FREE_REPORT in tasks:
            tasks[roles.FREE_REPORT].append(roles.free_report_task(case, records))

    task_index = {
        role: {task.task_id: task for task in items} for role, items in tasks.items()
    }

    # Hash degli input: entrano nella run_key, così un cambiamento dei dati rende le
    # run precedenti non compatibili invece di confonderle con le nuove.
    profiles_digest = source_profile_hash(profiles)
    case_digests = {case.case_id: case_hash(case) for case in cases}

    ledger = RunLedger(read_jsonl(args.output / "raw_runs.jsonl") if args.resume else [])
    if ledger.incompatible:
        print(
            f"[nota] {len(ledger.incompatible)} run senza identita' verificabile: "
            "conservate, non riusate"
        )

    credentials = CredentialPool.from_env()
    failures: list[dict] = []
    exclusions: list[dict] = []
    role_metrics: dict[str, dict[str, dict]] = {role: {} for role in requested_roles}
    model_manifest: dict[str, dict] = {}
    outcomes_by_pair: dict[tuple[str, str], list[harness.TaskOutcome]] = {}
    runs_path = args.output / "raw_runs.jsonl"
    skipped = executed = 0

    for requested in args.models:
        spec = registry.spec(
            "planner", model_name=None if requested == "current" else requested
        )
        model = spec.model_name

        if not spec.is_available:
            # Un modello non servito non ha fallito: non e' stato messo alla prova.
            exclusions.append(
                {
                    "model": model,
                    "exclusion_type": "operational_exclusion",
                    "stage": "resolution",
                    "reason": spec.unavailable_reason,
                }
            )
            print(f"[skip] {model}: {spec.unavailable_reason[:70]}")
            continue

        model_manifest[model] = spec.as_metadata()
        safety = assert_experiment_safe({"planner": spec})
        if safety:
            model_manifest[model]["reproducibility_warnings"] = safety

        client = OllamaClient(
            spec.endpoint, timeout=300.0, credential_pool=credentials
        )

        # Sonda l'abilitazione prima di spendere l'intero protocollo. Un modello
        # elencato in /api/tags puo' comunque essere negato su /api/chat: e' un
        # limite di autorizzazione dell'account, non un fallimento del modello, e
        # scoprirlo alla dodicesima chiamata sprecherebbe undici run.
        entitled, entitlement_reason = _probe_entitlement(client, spec.effective_api_model)
        if not entitled:
            exclusions.append(
                {
                    "model": model,
                    "exclusion_type": "operational_exclusion",
                    "stage": "entitlement",
                    "reason": entitlement_reason,
                }
            )
            print(f"[skip] {model}: {entitlement_reason[:70]}")
            continue

        declared = spec.capabilities.context_length if spec.capabilities else None
        resolution = spec.resolution.as_dict() if spec.resolution else {}

        print(
            f"[run ] {model} -> {spec.effective_api_model} "
            f"({spec.endpoint_mode}, {spec.structured_output_mode})",
            flush=True,
        )
        for role in requested_roles:
            outcomes: list[harness.TaskOutcome] = []
            for seed in args.seeds:
                for task in tasks[role]:
                    identity = build_identity(
                        requested_model_tag=model,
                        resolution=resolution,
                        role=role,
                        case_id=task.case_id,
                        task_id=task.task_id,
                        seed=seed,
                        case_digest=case_digests.get(task.case_id, ""),
                        profiles_digest=profiles_digest,
                        temperature=0.0,
                        num_ctx=args.num_ctx,
                    )
                    decision = ledger.decide(identity)
                    if decision.action == SKIP:
                        outcomes.append(_outcome_from_row(decision.existing))
                        skipped += 1
                        continue

                    outcome = harness.run_task(
                        client, spec.effective_api_model, task,
                        mode=spec.structured_output_mode, seed=seed, temperature=0.0,
                        num_ctx=args.num_ctx, identity=identity,
                        declared_context=declared,
                        screen_privacy=spec.endpoint.is_cloud,
                    )
                    outcomes.append(outcome)
                    executed += 1
                    # endpoint_mode e endpoint_url non entrano nella run_key — non
                    # cambiano cosa il modello ha ricevuto — ma vanno registrati:
                    # dicono chi ha imposto lo schema e chi applica i rate limit.
                    append_jsonl_atomic(
                        runs_path,
                        {
                            **outcome.as_dict(),
                            "endpoint_mode": spec.endpoint_mode,
                            "endpoint_url_sanitized": spec.endpoint.sanitized,
                        },
                    )
                    if not outcome.valid_output:
                        failures.append(
                            {
                                "model": model,
                                "run_key": identity.run_key,
                                "stage": role,
                                "task_id": task.task_id,
                                "seed": seed,
                                "error_class": outcome.error_class,
                                "reason": outcome.error[:300],
                            }
                        )
            outcomes_by_pair[(model, role)] = outcomes

    # Le metriche si calcolano dopo, quando ogni coppia ha tutte le sue run.
    for (model, role), outcomes in outcomes_by_pair.items():
        if role == roles.FREE_REPORT:
            metrics = harness.evaluate_free_report(
                outcomes, task_index[role], available_pmids
            )
        else:
            metrics = harness.ROLE_EVALUATORS[role](outcomes, task_index[role])
        role_metrics[role][model] = metrics
        valid = sum(1 for outcome in outcomes if outcome.valid_output)
        print(f"       {model:22s} {role:14s} validi {valid}/{len(outcomes)}", flush=True)

    write_jsonl(args.output / "failures.jsonl", failures)
    write_jsonl(args.output / "exclusions.jsonl", exclusions)
    write_json(
        args.output / "progress.json",
        {
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "runs_skipped_by_resume": skipped,
            "runs_executed": executed,
            "credential_pool": credentials.report(),
            "completed": [
                {"model": m, "role": r, "metrics": mm}
                for r, per in role_metrics.items()
                for m, mm in per.items()
            ],
            "status": "complete",
        },
    )

    # ── Ammissibilita' e classifica ────────────────────────────────────────────
    scoring_role = {
        roles.PLANNER: scoring.ROLE_PLANNER,
        roles.VERIFIER: scoring.ROLE_VERIFIER,
        roles.FREE_REPORT: scoring.ROLE_REPORT,
    }
    checks: list[dict] = []
    scores_by_role: dict[str, list[scoring.RoleScore]] = {}

    for role, per_model in role_metrics.items():
        key = scoring_role.get(role, role)
        scores: list[scoring.RoleScore] = []
        for model, metrics in per_model.items():
            check = scoring.check_admissibility(model, key, metrics)
            checks.append(check.as_dict())
            scores.append(scoring.score_role(model, key, metrics, admissible=check.passed))
        scores_by_role[key] = scores

    rankings = {role: scoring.rank(scores) for role, scores in scores_by_role.items()}
    single_model, single_reason = scoring.select_single_model(scores_by_role)
    status = scoring.selection_status(scores_by_role)

    selected = {
        role: (items[0].model if items else None) for role, items in rankings.items()
    }

    output = args.output
    # `raw_runs.jsonl` e' gia' stato scritto riga per riga in modo atomico durante
    # l'esecuzione: qui si rilegge, non si riscrive.
    all_runs = read_jsonl(runs_path)
    write_json(output / "model_manifest.json", model_manifest)
    write_json(
        output / "run_manifest.json",
        {
            "generated_at_utc": timestamp,
            "development_cases": list(DEVELOPMENT_CASES),
            "roles": requested_roles,
            "seeds": args.seeds,
            "num_ctx": args.num_ctx,
            "temperature": 0.0,
            "models_requested": args.models,
            "models_evaluated": sorted(model_manifest),
            "task_counts": {role: len(items) for role, items in tasks.items()},
            "runs_executed": executed,
            "runs_skipped_by_resume": skipped,
            "runs_preserved_not_reused": len(ledger.incompatible),
            "credential_pool": credentials.report(),
            "source_profile_hash": profiles_digest,
            "case_hashes": case_digests,
            "leakage_overlaps": {
                case.case_id: roles.leakage_overlap(case) for case in cases
            },
            "research_question": (
                "Quanto la scelta fra modelli cloud di scala e famiglia differenti "
                "influenza planner, verifier e free report sui quattro casi "
                "development? Il confronto e' esplorativo: non permette di attribuire "
                "causalmente un miglioramento alla sola taglia del modello."
            ),
            "policy": (
                "Selezione sui soli quattro casi development. Il test set non viene "
                "usato: adoperarlo per scegliere lo consumerebbe."
            ),
        },
    )

    _write_csv(
        output / "role_metrics.csv",
        ("role", "model", "metric", "value"),
        [
            {"role": role, "model": model, "metric": name,
             "value": "" if value is None else round(float(value), 4)}
            for role, per_model in role_metrics.items()
            for model, metrics in per_model.items()
            for name, value in sorted(metrics.items())
        ],
    )
    _write_csv(
        output / "per_case_metrics.csv",
        ("model", "role", "case_id", "task_id", "seed", "valid_output", "retries",
         "latency_ms"),
        [
            {
                "model": run.get("requested_model_tag") or run.get("model"),
                "role": run["role"], "case_id": run["case_id"],
                "task_id": run["task_id"], "seed": run["seed"],
                "valid_output": run["valid_output"], "retries": run["retries"],
                "latency_ms": run["latency_ms"],
            }
            for run in all_runs
        ],
    )
    _write_csv(
        output / "model_rankings.csv",
        ("role", "rank", "model", "score", "admissible"),
        [
            {"role": role, "rank": index + 1, "model": item.model,
             "score": round(item.score, 4), "admissible": item.admissible}
            for role, items in rankings.items()
            for index, item in enumerate(items)
        ],
    )

    write_json(
        output / "selected_models.json",
        {
            "planner_model": selected.get(scoring.ROLE_PLANNER),
            "verifier_model": selected.get(scoring.ROLE_VERIFIER),
            "report_model": selected.get(scoring.ROLE_REPORT),
            "optional_single_model": single_model,
            "single_model_reason": single_reason,
            "model_revisions": {
                model: metadata.get("model_revision")
                for model, metadata in model_manifest.items()
            },
            "digests": {
                model: metadata.get("model_digest")
                for model, metadata in model_manifest.items()
            },
            "config": {
                "temperature": 0.0,
                "num_ctx": args.num_ctx,
                "seeds": args.seeds,
                "prompt_version": "v1",
                "schema_version": "v1",
            },
            "selection_reason": {
                role: [item.as_dict() for item in items]
                for role, items in rankings.items()
            },
            "admissibility_checks": checks,
            "development_cases": list(DEVELOPMENT_CASES),
            "selection_status": status,
        },
    )

    env_lines = [
        "# Valori proposti dalla selezione. Non applicati automaticamente:",
        "# l'adozione resta una decisione esplicita.",
        f"# Generato: {timestamp}",
        f"# Stato selezione: {status}",
        "",
        f"OLLAMA_PLANNER_MODEL={selected.get(scoring.ROLE_PLANNER) or ''}",
        f"OLLAMA_VERIFIER_MODEL={selected.get(scoring.ROLE_VERIFIER) or ''}",
        f"OLLAMA_REPORT_MODEL={selected.get(scoring.ROLE_REPORT) or ''}",
        f"OLLAMA_QUALIFIER_MODEL={selected.get(scoring.ROLE_VERIFIER) or ''}",
        f"OLLAMA_NUM_CTX={args.num_ctx}",
        "OLLAMA_TEMPERATURE=0",
    ]
    write_text(output / "selected_models.env.example", "\n".join(env_lines))
    write_text(
        output / "MODEL_SELECTION_REPORT.md",
        _report(timestamp, args, model_manifest, role_metrics, rankings, checks,
                single_model, single_reason, status, failures, cases),
    )

    print(f"\nStato selezione: {status}")
    for role, items in rankings.items():
        head = items[0].model if items else "nessun modello ammissibile"
        print(f"  {role:14s} -> {head}")
    print(f"  modello unico  -> {single_model or 'non ammesso'} ({single_reason})")
    print(f"Output: {output}")
    return 0


def _report(timestamp, args, manifest, role_metrics, rankings, checks, single_model,
            single_reason, status, failures, cases) -> str:
    lines = [
        "# Selezione del modello — risultati",
        "",
        f"- **Generato:** {timestamp}",
        f"- **Stato:** `{status}`",
        f"- **Casi development:** {len(cases)} (il test set non e' stato usato)",
        f"- **Seed:** {args.seeds} · **num_ctx:** {args.num_ctx} · **temperature:** 0",
        f"- **Modelli valutati:** {sorted(manifest) or 'nessuno'}",
        "",
        "La selezione usa soltanto i quattro casi development. Il modello scelto non e'",
        "quindi valutato in modo indipendente: questi casi dicono quale modello e'",
        "preferibile fra i candidati, non quanto sara' bravo.",
        "",
        "## Modelli valutati",
        "",
        "| Modello | Endpoint | Modalita' output | Digest | Quantizzazione |",
        "| --- | --- | --- | --- | --- |",
    ]
    for model, metadata in sorted(manifest.items()):
        lines.append(
            f"| `{model}` | {metadata.get('endpoint_type')} | "
            f"{metadata.get('structured_output_mode')} | "
            f"`{(metadata.get('model_digest') or '-')[:12]}` | "
            f"{metadata.get('quantization') or '-'} |"
        )

    lines += ["", "## Metriche per ruolo", ""]
    for role, per_model in role_metrics.items():
        if not per_model:
            continue
        names = sorted({name for metrics in per_model.values() for name in metrics})
        lines += [f"### {role}", "", "| Modello | " + " | ".join(names) + " |",
                  "| --- | " + " | ".join("---" for _ in names) + " |"]
        for model, metrics in sorted(per_model.items()):
            row = " | ".join(
                "-" if metrics.get(name) is None else f"{float(metrics[name]):.3f}"
                for name in names
            )
            lines.append(f"| `{model}` | {row} |")
        lines.append("")

    lines += ["## Ammissibilita'", ""]
    for check in checks:
        verdict = "ammesso" if check["passed"] else "**escluso**"
        detail = f" — {check['failures']}" if check["failures"] else ""
        lines.append(f"- `{check['model']}` / {check['role']}: {verdict}{detail}")

    lines += ["", "## Classifiche", ""]
    for role, items in rankings.items():
        lines.append(f"**{role}**")
        if not items:
            lines.append("- nessun modello ammissibile")
        for index, item in enumerate(items, start=1):
            lines.append(f"{index}. `{item.model}` — {item.score:.4f}")
        lines.append("")

    lines += [
        "## Modello unico",
        "",
        f"{single_model or 'non ammesso'} — {single_reason}",
        "",
        "## Fallimenti",
        "",
    ]
    if failures:
        for failure in failures[:20]:
            lines.append(
                f"- `{failure.get('model')}` / {failure.get('stage')}: {failure.get('reason')}"
            )
    else:
        lines.append("- nessuno")

    lines += [
        "",
        "## Limiti",
        "",
        "- Quattro casi: i punteggi descrivono questo campione, non stimano una popolazione.",
        "- Il modello selezionato non e' valutato in modo indipendente.",
        "- Modelli locali (`json_schema`) e cloud (`prompt_validated`) non partono alla",
        "  pari sul `valid_output_rate`: la differenza e' una proprieta' del deployment.",
        "- Tre seed danno un accordo run-to-run che vale solo 1/3, 2/3 o 1.",
        "- La domanda di C1 nomina la terapia attesa: il recall terapeutico di quel caso",
        "  e' meno informativo degli altri.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
