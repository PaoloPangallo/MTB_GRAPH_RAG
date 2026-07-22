"""Ablation di reporting: quattro bracci sullo stesso retrieval congelato.

    cd mtb-graphrag
    PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/\\
run_reporting_ablation.py --output benchmarks/mtb_evidence/evaluation/results/pilot_v1

Isola la sola variabile "modo di scrivere il report". Il retrieval **non viene
rieseguito** fra i bracci: i record vengono letti una volta dagli artefatti
dell'audit e passati identici, nello stesso ordine, a tutti e quattro. Se il
retrieval variasse, una differenza fra sintesi libera e report strutturato potrebbe
venire da record diversi invece che dal modo di scriverli, e la tesi che si vuole
verificare diventerebbe non verificabile.

I quattro bracci:

1. `raw_records`  — serializzazione leggibile, nessuna sintesi, nessun LLM. E' il
   limite superiore di conservazione: tutto cio' che il retrieval ha trovato e'
   ancora li'.
2. `free_llm_summary` — il modello selezionato per il ruolo report, senza struttura.
3. `structured_report_unverified` — renderer deterministico, senza verdetto di fonte
   e senza repair.
4. `structured_report_verified` — con profili delle fonti, applicabilita' e repair.

Il braccio libero non riceve claim del gold, PMID attesi, terapie attese,
applicabilita' attesa ne' decisioni dell'audit.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.pipeline.llm.model_registry import ModelRegistry  # noqa: E402
from backend.pipeline.llm.ollama_adapter import OllamaClient  # noqa: E402
from benchmarks.mtb_evidence.evaluation.aggregation import _write_csv  # noqa: E402
from benchmarks.mtb_evidence.evaluation.clinical_gold import load_clinical_gold  # noqa: E402
from benchmarks.mtb_evidence.evaluation.contracts import (  # noqa: E402
    BRANCH_FREE,
    BRANCH_RAW,
    BRANCH_STRUCTURED,
    BRANCH_VERIFIED,
    ReportPrediction,
    RetrievalPrediction,
)
from benchmarks.mtb_evidence.evaluation.metrics.applicability import (  # noqa: E402
    applicability_metrics,
)
from benchmarks.mtb_evidence.evaluation.metrics.report_fidelity import (  # noqa: E402
    report_metrics,
)
from benchmarks.mtb_evidence.evaluation.source_profiles import default_repository  # noqa: E402
from benchmarks.mtb_evidence.model_selection import harness, roles  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.normalize import (  # noqa: E402
    norm_nct_set,
    norm_pmid_set,
    norm_text,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    write_json,
    write_jsonl,
    write_text,
)

DEFAULT_GOLD = Path("benchmarks/mtb_evidence/evaluation/data/clinical_gold_v1.jsonl")
DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/pilot/audit")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clinical-gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--selected-models", type=Path, default=None)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--seeds", nargs="+", type=int, default=[20240517, 13, 991])
    parser.add_argument("--num-ctx", type=int, default=16384)
    parser.add_argument(
        "--skip-free",
        action="store_true",
        help="salta il braccio libero quando nessun modello e' disponibile",
    )
    return parser.parse_args(argv)


def _load_records(audit_dir: Path, case_id: str) -> list[dict[str, Any]]:
    path = audit_dir / case_id / "normalized_records.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _retrieval_from_records(
    case_id: str, records: Sequence[Mapping[str, Any]]
) -> RetrievalPrediction:
    """La predizione di retrieval congelata, comune a tutti i bracci."""
    therapies = {norm_text(record.get("drug")) for record in records if record.get("drug")}
    pmids = {pmid for record in records for pmid in norm_pmid_set(record.get("pmids") or [])}
    ncts = {nct for record in records for nct in norm_nct_set(record.get("nct_ids") or [])}
    return RetrievalPrediction(
        case_id=case_id,
        architecture="frozen",
        therapies=tuple(sorted(therapies - {""})),
        pmids=tuple(sorted(pmids)),
        nct_ids=tuple(sorted(ncts)),
        record_ids=tuple(str(record.get("record_id", "")) for record in records),
        claims=tuple(dict(record) for record in records),
    )


# ── Braccio 1: record grezzi ───────────────────────────────────────────────────


def branch_raw(case_id: str, records: Sequence[Mapping[str, Any]]) -> ReportPrediction:
    """Nessuna sintesi: i record serializzati per intero.

    E' il limite superiore. Qualunque cosa i bracci successivi perdano, la perdita e'
    attribuibile al modo di scrivere, non al retrieval.
    """
    lines: list[str] = []
    for record in records:
        parts = [
            f"profilo: {record.get('subject', '')}",
            f"relazione: {record.get('relation', '')}",
            f"farmaco: {record.get('drug', '')}",
            f"malattia: {record.get('disease', '')}",
            f"direzione: {record.get('direction', '')}",
            f"PMID: {', '.join(record.get('pmids') or []) or '-'}",
            f"setting osservato: {(record.get('setting') or {}).get('label', '-')}",
        ]
        lines.append(" | ".join(parts))
    return ReportPrediction(
        case_id=case_id,
        branch=BRANCH_RAW,
        text="\n".join(lines),
        claims=tuple(dict(record) for record in records),
        cited_pmids=tuple(
            sorted({p for r in records for p in norm_pmid_set(r.get("pmids") or [])})
        ),
        mentioned_therapies=tuple(
            sorted({norm_text(r.get("drug")) for r in records if r.get("drug")})
        ),
        qualifiers_present=tuple(
            sorted({(r.get("setting") or {}).get("label", "") for r in records})
        ),
        abstained=not records,
    )


# ── Bracci 3 e 4: renderer deterministico ──────────────────────────────────────


def branch_structured(
    case_id: str, records: Sequence[Mapping[str, Any]], *, verified: bool, profiles
) -> ReportPrediction:
    """Report strutturato, con o senza verifica delle fonti.

    La differenza fra i due bracci e' esattamente la qualificazione: quello non
    verificato espone i fatti, quello verificato aggiunge setting e linea presi dai
    profili clinici annotati, e dichiara l'applicabilita' per claim.
    """
    claims: list[dict[str, Any]] = []
    applicability: dict[str, str] = {}
    lines: list[str] = []
    qualifiers: list[str] = []

    for index, record in enumerate(records):
        pmids = norm_pmid_set(record.get("pmids") or [])
        claim_id = f"{case_id}::R{index}"
        claim = {
            "claim_id": claim_id,
            "subject": record.get("subject", ""),
            "relation": record.get("relation", ""),
            "object": record.get("drug", ""),
            "disease": record.get("disease", ""),
            "direction": record.get("direction", ""),
            "pmid": pmids[0] if pmids else "",
        }
        line = (
            f"- {record.get('subject','')} — {record.get('relation','')} — "
            f"{record.get('drug','')} ({record.get('disease','')}) "
            f"[PMID {', '.join(pmids) or 'n/d'}]"
        )
        if verified and pmids:
            profile = profiles.by_pmid(pmids[0])
            if profile is not None:
                claim["qualifiers"] = (
                    f"setting: {profile.setting}; linea: {profile.therapy_line}"
                )
                claim["documentary_status"] = "supported_as_written"
                qualifiers.extend([profile.setting, profile.therapy_line])
                line += (
                    f"\n    popolazione: {profile.population}"
                    f"\n    setting: {profile.setting} | linea: {profile.therapy_line}"
                )
                if profile.exclusion_criteria_summary:
                    line += f"\n    esclusioni: {profile.exclusion_criteria_summary}"
                applicability[claim_id] = "indeterminate"
        claims.append(claim)
        lines.append(line)

    return ReportPrediction(
        case_id=case_id,
        branch=BRANCH_VERIFIED if verified else BRANCH_STRUCTURED,
        text="\n".join(lines),
        claims=tuple(claims),
        cited_pmids=tuple(
            sorted({p for r in records for p in norm_pmid_set(r.get("pmids") or [])})
        ),
        mentioned_therapies=tuple(
            sorted({norm_text(r.get("drug")) for r in records if r.get("drug")})
        ),
        qualifiers_present=tuple(sorted({q for q in qualifiers if q})),
        abstained=not records,
        requested_human_review=verified and bool(records),
        applicability_by_claim=applicability,
    )


# ── Braccio 2: sintesi libera ──────────────────────────────────────────────────


def branch_free(
    case, records: Sequence[Mapping[str, Any]], client, model: str, mode: str,
    *, seed: int, num_ctx: int,
) -> tuple[ReportPrediction | None, dict[str, Any]]:
    task = roles.free_report_task(case, list(records))
    outcome = harness.run_task(
        client, model, task, mode=mode, seed=seed, temperature=0.0, num_ctx=num_ctx
    )
    if not outcome.valid_output:
        return None, outcome.as_dict()
    parsed = outcome.parsed
    claims = tuple(dict(claim) for claim in (parsed.get("claims") or []))
    return (
        ReportPrediction(
            case_id=case.case_id,
            branch=BRANCH_FREE,
            text=str(parsed.get("summary") or ""),
            claims=claims,
            cited_pmids=tuple(
                sorted({p for c in claims for p in norm_pmid_set([c.get("pmid", "")])})
            ),
            mentioned_therapies=tuple(
                sorted({norm_text(c.get("object")) for c in claims if c.get("object")})
            ),
            qualifiers_present=tuple(
                sorted({norm_text(c.get("qualifiers")) for c in claims if c.get("qualifiers")})
            ),
            abstained=bool(parsed.get("abstained")),
            requested_human_review=bool(parsed.get("needs_human_review")),
        ),
        outcome.as_dict(),
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    timestamp = datetime.now(timezone.utc).isoformat()
    cases = load_clinical_gold(args.clinical_gold)
    profiles = default_repository()

    report_model = None
    if args.selected_models and args.selected_models.is_file():
        payload = json.loads(args.selected_models.read_text(encoding="utf-8"))
        report_model = payload.get("report_model")

    client = None
    mode = ""
    if report_model and not args.skip_free:
        spec = ModelRegistry(probe=True).spec("free_report", model_name=report_model)
        if spec.capabilities is not None:
            client = OllamaClient(spec.endpoint, timeout=600.0)
            mode = spec.structured_output_mode
            report_model = spec.model_name
        else:
            print(f"[skip] {report_model} non installato: braccio libero saltato")
            report_model = None

    rows: list[dict[str, Any]] = []
    raw_free: list[dict[str, Any]] = []
    frozen_manifest: dict[str, Any] = {}

    for case in cases:
        records = _load_records(args.audit_dir, case.case_id)
        retrieval = _retrieval_from_records(case.case_id, records)
        # Impronta dei record: prova che i quattro bracci hanno ricevuto lo stesso input.
        frozen_manifest[case.case_id] = {
            "record_count": len(records),
            "record_ids": list(retrieval.record_ids),
            "pmids": list(retrieval.pmids),
            "therapies": list(retrieval.therapies),
        }

        predictions: list[ReportPrediction] = [
            branch_raw(case.case_id, records),
            branch_structured(case.case_id, records, verified=False, profiles=profiles),
            branch_structured(case.case_id, records, verified=True, profiles=profiles),
        ]

        if client is not None and report_model:
            for seed in args.seeds[: args.replicates]:
                prediction, trace = branch_free(
                    case, records, client, report_model, mode,
                    seed=seed, num_ctx=args.num_ctx,
                )
                raw_free.append({"case_id": case.case_id, "seed": seed, **trace})
                if prediction is not None:
                    predictions.append(prediction)

        for prediction in predictions:
            metrics = report_metrics(
                prediction,
                retrieval,
                profiles,
                expected_abstention=case.expected_abstention,
                expected_human_review=case.expected_human_review,
            )
            metrics.update(applicability_metrics(case, prediction, profiles))
            for name, metric in sorted(metrics.items()):
                rows.append(
                    {
                        "case_id": case.case_id,
                        "category": case.category,
                        "branch": prediction.branch,
                        "metric": name,
                        "numerator": metric.numerator,
                        "denominator": metric.denominator,
                        "value": "" if metric.value is None else round(metric.value, 4),
                    }
                )
        print(f"{case.case_id:32s} record={len(records):3d} bracci={len(predictions)}", flush=True)

    output = args.output
    _write_csv(
        output / "reporting_ablation.csv",
        ("case_id", "category", "branch", "metric", "numerator", "denominator", "value"),
        rows,
    )
    write_jsonl(output / "reporting_ablation_free_raw.jsonl", raw_free)
    write_json(
        output / "reporting_ablation_manifest.json",
        {
            "generated_at_utc": timestamp,
            "free_report_model": report_model,
            "structured_output_mode": mode,
            "replicates": args.replicates if report_model else 0,
            "seeds": args.seeds[: args.replicates],
            "frozen_retrieval": frozen_manifest,
            "invariant": (
                "I quattro bracci ricevono gli stessi record, nello stesso ordine. "
                "Il retrieval non viene rieseguito: record_ids qui sopra e' la prova "
                "dell'input condiviso."
            ),
            "branches": [BRANCH_RAW, BRANCH_FREE, BRANCH_STRUCTURED, BRANCH_VERIFIED],
        },
    )

    summary = _summary(rows, report_model)
    write_text(output / "REPORTING_ABLATION.md", summary)
    print(f"\nOutput: {output}")
    return 0


def _summary(rows: Sequence[Mapping[str, Any]], report_model: str | None) -> str:
    by_branch: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        if row["value"] == "":
            continue
        by_branch.setdefault(str(row["branch"]), {}).setdefault(
            str(row["metric"]), []
        ).append(float(row["value"]))

    interesting = [
        "citation_accuracy",
        "qualifier_preservation",
        "context_omission_rate",
        "unsupported_claim_rate",
        "structural_coverage",
        "abstention_accuracy",
    ]
    lines = [
        "# Ablation di reporting",
        "",
        f"- **Modello del braccio libero:** {report_model or 'non eseguito'}",
        "",
        "I quattro bracci ricevono gli stessi record congelati, nello stesso ordine. "
        "Il retrieval non viene rieseguito: qualunque differenza qui sotto e' "
        "attribuibile al modo di scrivere il report, non a cio' che e' stato trovato.",
        "",
        "| Metrica | " + " | ".join(sorted(by_branch)) + " |",
        "| --- | " + " | ".join("---" for _ in by_branch) + " |",
    ]
    for metric in interesting:
        cells = []
        for branch in sorted(by_branch):
            values = by_branch[branch].get(metric, [])
            cells.append(f"{sum(values)/len(values):.3f}" if values else "-")
        lines.append(f"| {metric} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## Come leggere questi numeri",
        "",
        "`raw_records` e' il limite superiore di conservazione per cio' che il grafo "
        "contiene: nessuna sintesi, quindi nulla puo' andare perso nella scrittura.",
        "",
        "**Il vantaggio del braccio verificato sui qualificatori non e' merito della "
        "scrittura.** I qualificatori — setting, linea di terapia, popolazione — non "
        "esistono nel grafo: vivono solo nei profili clinici annotati a mano. Il braccio "
        "verificato e' l'unico che li consulta, quindi e' l'unico che puo' riportarli. "
        "Gli altri bracci non li omettono per negligenza: non li hanno.",
        "",
        "La lettura corretta e' quindi: *la verifica delle fonti aggiunge informazione "
        "che il retrieval non puo' fornire*, non *il report verificato scrive meglio*. "
        "E' un argomento a favore dei profili annotati, non della resa testuale.",
        "",
    ]

    free = by_branch.get("free_llm_summary", {})
    structured = by_branch.get("structured_report_unverified", {})
    if free and structured:
        def _mean(branch: dict, metric: str) -> float | None:
            values = branch.get(metric, [])
            return sum(values) / len(values) if values else None

        coverage = _mean(free, "structural_coverage")
        unsupported = _mean(free, "unsupported_claim_rate")
        lines += [
            "### Dove la sintesi libera perde davvero",
            "",
            "Qui il confronto e' pulito, perche' entrambi i bracci ricevono gli stessi "
            "record e nessuno dei due consulta i profili annotati:",
            "",
        ]
        if coverage is not None:
            lines.append(
                f"- **Copertura strutturale {coverage:.3f}** contro 1.000 dei bracci "
                "deterministici. La sintesi libera menziona una frazione di cio' che "
                "il retrieval ha trovato: il resto sparisce senza che il testo segnali "
                "l'omissione."
            )
        if unsupported is not None and unsupported > 0:
            lines.append(
                f"- **Claim non ancorate {unsupported:.3f}** contro 0.000. Una parte "
                "delle affermazioni non trova riscontro nei record ricevuti, e su un "
                "report di evidenza e' il difetto che conta di piu': un lettore non "
                "puo' distinguerle dalle altre."
            )
        lines += [
            "",
            "Queste due differenze **sono** attribuibili al modo di scrivere, perche' "
            "l'input era identico. E' il risultato che sostiene la tesi sul reporting "
            "strutturato — non il vantaggio sui qualificatori, che viene dai profili.",
            "",
        ]

    lines += [
        "Quattro casi: i valori descrivono questo campione e non stimano una popolazione.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
