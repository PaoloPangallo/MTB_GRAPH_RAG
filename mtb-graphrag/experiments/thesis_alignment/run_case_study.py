"""Case study EGFR L858R sulle due architetture GraphRAG verificabili.

Esegue, per ciascuna architettura, una fase cold e una warm, esportando le
metriche necessarie ad aggiornare il manoscritto.

**Isolamento della cache.** Le due architetture consultano lo stesso corpus di
PMID: con una cache condivisa il cold della seconda sarebbe gia' caldo per
effetto della prima, e i cache_misses misurerebbero l'ordine di esecuzione
anziche' l'architettura. Ogni fase cold usa quindi un file di cache dedicato e
appena creato; la fase warm riusa esattamente la cache lasciata dal proprio
cold, mai quella dell'altra architettura.

Uso:
    PYTHONPATH=. python experiments/thesis_alignment/run_case_study.py --live
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from backend.api.schemas import ArchitectureComparisonRequest
from backend.comparison.live_runs import build_run
from backend.comparison.service import (
    _build_dossier,
    _checks_from_verifications,
    _render_verified_report,
)
from backend.pipeline.agentic.ledger import EventLedger
from backend.pipeline.agentic.source_profile_cache import SourceProfileCache
from backend.pipeline.control.verification.source_port import PubMedSourceVerifier

CASE = dict(
    gene="EGFR",
    variant="L858R",
    tumor_type="Lung Adenocarcinoma",
    alteration_type="point_mutation",
    therapy_line="first-line",
    mtb_goal="general-review",
)

OUTPUT_DIR = Path(__file__).resolve().parent
ARCHITECTURES = ("deterministic", "agentic")


def commit_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:  # noqa: BLE001 - il commit e' un'annotazione, non un requisito
        return "unknown"


def export(run: Any, result: Any, *, architecture: str, phase: str, elapsed_ms: int) -> dict:
    """Estrae i campi richiesti dal protocollo del case study."""
    metrics = run.metrics
    view = result.canonical_view
    return {
        "run_id": run.run_id,
        "commit_sha": commit_sha(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_kind": "live",  # distinto da: LLM scriptato, benchmark, case study descrittivo
        "architecture": architecture,
        "architecture_title": run.title,
        "phase": phase,
        "orchestration_mode": result.orchestration_mode,
        "planning_mode": metrics.planning_mode,
        "fallback_reason": metrics.fallback_reason,
        "tool_path": list(result.collection.tool_path),
        "mandatory_tools": list(metrics.mandatory_tools),
        "missing_mandatory_tools": list(metrics.missing_mandatory_tools),
        "ledger_valid": metrics.ledger_valid,
        "ledger_events": metrics.ledger_events,
        "canonical_records": {
            "observed": view.records_in,
            "canonical": view.records_out,
            "conflicts": metrics.canonical_conflicts,
            "replay_fidelity": view.replay_fidelity,
        },
        "projection_records": {
            "admitted": metrics.projection_admitted,
            "excluded": metrics.projection_excluded,
        },
        "structural_verification": {
            "candidate_status": result.candidate_verdict.status,
            "final_status": result.final_verdict.status,
            "dossier_status": result.dossier_verdict.status,
            "coverage": metrics.structural_coverage,
            "violations": metrics.structural_violations,
            "warnings": metrics.structural_warnings,
            "spurious_citations": metrics.spurious_citations,
            "escalated": metrics.escalated,
        },
        "support_counts": {
            "supported_as_written": metrics.source_supported_as_written_count,
            "supported_after_contextualization":
                metrics.source_supported_after_contextualization_count,
            "uncertain": metrics.source_uncertain_count,
            "contradicted": metrics.source_unsupported_count,
        },
        "applicability_counts": {
            "compatible": metrics.applicability_compatible_count,
            "indeterminate": metrics.applicability_indeterminate_count,
            "not_compatible": metrics.applicability_not_compatible_count,
        },
        "repair_attempts": metrics.repair_attempts,
        "cache_hits": metrics.cache_hits,
        "cache_misses": metrics.cache_misses,
        "stage_timings": metrics.stage_timings_ms,
        "elapsed_ms": elapsed_ms,
        "model_revision": metrics.model_revision,
        "prompt_version": metrics.prompt_version,
        "counters": {
            "retrieval_tool_calls": metrics.retrieval_tool_calls,
            "planner_calls": metrics.planner_calls,
            "llm_synthesis_calls": metrics.llm_synthesis_calls,
            "source_verifier_calls": metrics.source_verifier_calls,
            "pipeline_nodes_executed": metrics.pipeline_nodes_executed,
            "verifier_batches": metrics.verifier_batches,
        },
        "llm_roles": list(run.llm_roles),
    }


def run_phase(architecture: str, phase: str, cache_path: Path, ledger_path: Path) -> dict:
    req = ArchitectureComparisonRequest(**CASE, execution_mode="live")
    verifier = PubMedSourceVerifier(profile_cache=SourceProfileCache(cache_path))

    started = perf_counter()
    run, result = build_run(
        req,
        architecture,
        source_verifier=verifier,
        ledger=EventLedger(ledger_path),
        build_dossier=_build_dossier,
        build_claim_checks=_checks_from_verifications,
        render_verified=_render_verified_report,
    )
    elapsed = int((perf_counter() - started) * 1000)
    return export(run, result, architecture=architecture, phase=phase, elapsed_ms=elapsed)


def check_cache_protocol(record: dict, phase: str) -> list[str]:
    """Verifica che l'isolamento cold/warm abbia retto.

    Meglio nessun dato che dati contaminati: se il protocollo non regge,
    l'anomalia va segnalata invece di finire silenziosamente nei risultati.
    """
    anomalies = []
    if phase == "cold" and record["cache_hits"] > 0:
        anomalies.append(
            f"cold con {record['cache_hits']} cache hit: la cache non era isolata."
        )
    if phase == "warm" and record["cache_misses"] > 0:
        anomalies.append(
            f"warm con {record['cache_misses']} cache miss: la cache del cold non e' stata riusata."
        )
    return anomalies


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="esegue le run live")
    parser.add_argument("--architectures", nargs="*", default=list(ARCHITECTURES))
    args = parser.parse_args()

    if not args.live:
        print("Specificare --live per eseguire il case study contro Neo4j e gli LLM reali.")
        return 2

    workdir = OUTPUT_DIR / "_work"
    workdir.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    anomalies: list[str] = []

    for architecture in args.architectures:
        # Cache dedicata per architettura: il cold non deve vedere i profili
        # prodotti dall'altra run.
        cache_path = workdir / f"cache_{architecture}.sqlite3"
        if cache_path.exists():
            cache_path.unlink()
        ledger_path = workdir / f"ledger_{architecture}.sqlite3"

        for phase in ("cold", "warm"):
            print(f"[{architecture}/{phase}] avvio…", flush=True)
            record = run_phase(architecture, phase, cache_path, ledger_path)
            found = check_cache_protocol(record, phase)
            record["cache_protocol_anomalies"] = found
            anomalies.extend(f"{architecture}/{phase}: {item}" for item in found)

            path = OUTPUT_DIR / f"egfr_l858r_{architecture}_{phase}.json"
            path.write_text(
                json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            results[f"{architecture}_{phase}"] = record
            print(
                f"[{architecture}/{phase}] fatto in {record['elapsed_ms']} ms — "
                f"{record['projection_records']['admitted']} record ammessi, "
                f"cache {record['cache_hits']}h/{record['cache_misses']}m",
                flush=True,
            )

    (OUTPUT_DIR / "comparison_summary.md").write_text(
        render_summary(results, anomalies), encoding="utf-8"
    )
    if anomalies:
        print("\nANOMALIE nel protocollo della cache:")
        for item in anomalies:
            print(" -", item)
    print(f"\nRisultati in {OUTPUT_DIR}")
    return 0


def render_summary(results: dict[str, dict], anomalies: list[str]) -> str:
    lines = [
        "# Case study EGFR L858R — due architetture GraphRAG verificabili",
        "",
        "Caso: EGFR L858R, Lung Adenocarcinoma, first-line, obiettivo `general-review`.",
        "Run **live** contro Neo4j e i modelli reali (distinte da test con LLM",
        "scriptato, benchmark e case study descrittivo).",
        "",
    ]
    if results:
        any_record = next(iter(results.values()))
        lines += [
            f"Commit: `{any_record['commit_sha']}`",
            f"Revisione del modello: `{any_record['model_revision']}`, "
            f"prompt `{any_record['prompt_version']}`",
            "",
        ]

    lines += [
        "## Confronto",
        "",
        "| Metrica | " + " | ".join(results) + " |",
        "|---|" + "---|" * len(results),
    ]

    def row(label: str, fn) -> str:
        return f"| {label} | " + " | ".join(str(fn(r)) for r in results.values()) + " |"

    if results:
        lines += [
            row("Modalità di pianificazione", lambda r: r["planning_mode"]),
            row("Chiamate al planner", lambda r: r["counters"]["planner_calls"]),
            row("Chiamate a strumenti di retrieval",
                lambda r: r["counters"]["retrieval_tool_calls"]),
            row("Nodi di controllo eseguiti",
                lambda r: r["counters"]["pipeline_nodes_executed"]),
            row("Eventi nel ledger", lambda r: r["ledger_events"]),
            row("Hash-chain valida", lambda r: r["ledger_valid"]),
            row("Record osservati → canonici",
                lambda r: f"{r['canonical_records']['observed']} → {r['canonical_records']['canonical']}"),
            row("Record ammessi dalla proiezione",
                lambda r: r["projection_records"]["admitted"]),
            row("Copertura strutturale",
                lambda r: r["structural_verification"]["coverage"]),
            row("Violazioni strutturali",
                lambda r: r["structural_verification"]["violations"]),
            row("Supportate come formulate",
                lambda r: r["support_counts"]["supported_as_written"]),
            row("Supportate dopo contestualizzazione",
                lambda r: r["support_counts"]["supported_after_contextualization"]),
            row("Supporto incerto", lambda r: r["support_counts"]["uncertain"]),
            row("Claim contraddette", lambda r: r["support_counts"]["contradicted"]),
            row("Applicabilità compatibile",
                lambda r: r["applicability_counts"]["compatible"]),
            row("Applicabilità indeterminata",
                lambda r: r["applicability_counts"]["indeterminate"]),
            row("Applicabilità non compatibile",
                lambda r: r["applicability_counts"]["not_compatible"]),
            row("Tentativi di riparazione", lambda r: r["repair_attempts"]),
            row("Cache hit / miss", lambda r: f"{r['cache_hits']} / {r['cache_misses']}"),
            row("Durata (ms)", lambda r: r["elapsed_ms"]),
        ]

    lines += [
        "",
        "## Lettura",
        "",
        "Le due architetture attraversano lo stesso strato di controllo: la",
        "differenza attesa e' concentrata in `planner_calls` (0 per il piano fisso)",
        "e nel percorso con cui gli strumenti vengono raggiunti, non nelle fasi di",
        "canonicalizzazione, proiezione, verifica e dossier.",
        "",
        "Il dossier e' un artefatto destinato alla revisione del Molecular Tumor",
        "Board; nessun risultato qui riportato costituisce una raccomandazione",
        "terapeutica. Il ledger e' append-only e tamper-evident nel threat model",
        "considerato, non immutabile in senso assoluto.",
        "",
    ]

    if anomalies:
        lines += ["## Anomalie del protocollo", ""]
        lines += [f"- {item}" for item in anomalies]
        lines += [""]

    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
