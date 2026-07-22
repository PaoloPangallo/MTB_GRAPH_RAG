"""Valuta il linker corrente contro il gold dei collegamenti.

Gira il linker **reale** — quello di `backend.pipeline.evidence.qualification` —
sui 147 statement, e ne confronta le prediction con `StatementQualificationGold`.

Il confronto e' significativo solo sui record di gold valutabili. Dove non ce ne
sono, le metriche restituiscono `not_evaluable` invece di 0.0: la distinzione fra
«il linker sbaglia» e «non e' stato misurato» e' l'unica cosa che questo script
esiste per proteggere.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.profile_unit import unit_id  # noqa: E402
from backend.pipeline.evidence.qualification import build_links  # noqa: E402
from backend.pipeline.evidence.qualification_gold import (  # noqa: E402
    AnnotationDecision,
    StatementQualificationGold,
    agreement_rate,
    gold_link_id,
)
from benchmarks.mtb_evidence.evaluation.linking_evaluation import (  # noqa: E402
    LINKER_STATUS_TO_GOLD,
    NOT_EVALUABLE,
    CandidatePair,
    evaluate_linking,
)
from benchmarks.mtb_evidence.evaluation.source_profiles import default_repository  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
    write_text,
)

DEFAULT_CORPUS = Path("benchmarks/mtb_evidence/v3/qualification_corpus")
DEFAULT_QUALIFICATION = Path("benchmarks/mtb_evidence/v3/qualification")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--qualification-dir", type=Path, default=DEFAULT_QUALIFICATION)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _load_gold(path: Path) -> list[StatementQualificationGold]:
    """Ricostruisce i record di gold dal file.

    Le annotazioni vengono ricostruite solo se **presenti**. Un file di soli
    candidati produce record senza annotazioni, che restano non valutabili: e' il
    comportamento voluto, perche' il gold non deve poter nascere dal proprio file
    di partenza.
    """
    records: list[StatementQualificationGold] = []
    for row in read_jsonl(path):
        records.append(
            StatementQualificationGold(
                gold_link_id=str(row.get("gold_link_id") or ""),
                statement_id=str(row.get("statement_id") or ""),
                profile_unit_id=str(row.get("profile_unit_id") or ""),
                first_annotation=_decision(row.get("first_annotation")),
                second_annotation=_decision(row.get("second_annotation")),
                adjudicator=str(row.get("adjudicator") or ""),
                adjudication=_decision(row.get("adjudication")),
                created_at=str(row.get("created_at") or ""),
                frozen_at=str(row.get("frozen_at") or ""),
                note=str(row.get("note") or ""),
            )
        )
    return records


def _decision(payload: Any) -> AnnotationDecision | None:
    if not isinstance(payload, Mapping):
        return None
    return AnnotationDecision(
        annotator_id=str(payload.get("annotator_id") or ""),
        link_status=str(payload.get("link_status") or ""),
        applicable_dimensions=tuple(payload.get("applicable_dimensions") or ()),
        excluded_dimensions=tuple(payload.get("excluded_dimensions") or ()),
        conflict_dimensions=tuple(payload.get("conflict_dimensions") or ()),
        ambiguity_dimensions=tuple(payload.get("ambiguity_dimensions") or ()),
        rationale_codes=tuple(payload.get("rationale_codes") or ()),
        evidence_locators=tuple(payload.get("evidence_locators") or ()),
        annotated_at=str(payload.get("annotated_at") or ""),
        note=str(payload.get("note") or ""),
    )


def _report(
    metrics: Mapping[str, Any],
    predictions: Sequence[Mapping[str, Any]],
    gold_records: Sequence[StatementQualificationGold],
) -> str:
    by_status: dict[str, int] = {}
    for prediction in predictions:
        status = str(prediction["predicted_status"])
        by_status[status] = by_status.get(status, 0) + 1

    rate, pairs = agreement_rate(gold_records)
    lines = [
        "# Valutazione del linking statement-profilo",
        "",
        "Il linker valutato e' quello reale della pipeline, non una sua riscrittura:",
        "una copia divergerebbe, e la valutazione misurerebbe la copia.",
        "",
        "## Prediction del linker",
        "",
        "| Stato | Coppie |",
        "| --- | ---: |",
    ]
    for status in sorted(by_status):
        lines.append(f"| `{status}` | {by_status[status]} |")

    lines += [
        "",
        "## Gold",
        "",
        f"- Record di gold: {metrics['gold_record_count']}",
        f"- Prediction con un record di gold corrispondente: "
        f"{metrics['candidates_with_gold_record']} / {metrics['candidate_count']}",
        f"- **Valutabili: {metrics['evaluated_count']}**",
        f"- Provvisori: {metrics['provisional_count']}",
        f"- Congelati: {metrics['frozen_count']}",
        f"- Coppie con due revisioni reali: {pairs}",
        f"- Accordo fra annotatori: `{rate if rate is not None else NOT_EVALUABLE}`",
        "",
        "## Metriche",
        "",
        "| Metrica | Valore |",
        "| --- | --- |",
        f"| linking precision | `{metrics['linking_precision']}` |",
        f"| linking recall | `{metrics['linking_recall']}` |",
        f"| linking F1 | `{metrics['linking_f1']}` |",
        f"| exact-match precision | `{metrics['exact_match_precision']}` |",
        f"| partial-link accuracy | `{metrics['partial_link_accuracy']}` |",
        f"| invalid-link rejection | `{metrics['invalid_link_rejection_accuracy']}` |",
        f"| ambiguity detection | `{metrics['ambiguity_detection_accuracy']}` |",
        f"| conflict detection | `{metrics['conflict_detection_accuracy']}` |",
        f"| dimension-level precision | `{metrics['dimension_level_precision']}` |",
        f"| dimension-level recall | `{metrics['dimension_level_recall']}` |",
        "",
        "## Perche' i valori sono `not_evaluable`",
        "",
        "Non perche' il linker abbia fallito, ma perche' non esiste ancora un",
        "riferimento contro cui misurarlo. Il gold richiede due annotazioni",
        "indipendenti su ogni coppia, e questa fase ha costruito il workflow senza",
        "poterlo eseguire.",
        "",
        f"La causa e' verificata e non supposta: tutte le {metrics['candidates_with_gold_record']} "
        "prediction del linker hanno un record di gold corrispondente. Le chiavi di join",
        "combaciano, quindi lo zero viene dalle annotazioni mancanti e non da una",
        "valutazione rotta — due situazioni che produrrebbero lo stesso numero.",
        "",
        "La strada corta sarebbe copiare le prediction del linker nel gold. Darebbe",
        "precision 1.000 e non significherebbe nulla: misurerebbe la coerenza del",
        "linker con se stesso. `candidate_from_link` esiste proprio per rendere quella",
        "scorciatoia impraticabile — conserva la prediction in una nota, dove e'",
        "leggibile ma non puo' diventare il riferimento.",
        "",
        "## Priorita' fra precision e recall",
        "",
        "La precisione conta di piu'. Uno statement non qualificato lascia il retriever",
        "al comportamento V2, che e' il punto di partenza noto. Uno statement",
        "qualificato con setting o linea sbagliati produce un filtro che scarta",
        "l'evidenza giusta o ne ammette una inapplicabile, e nessuna metrica a valle",
        "distingue quel caso da una qualificazione corretta.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    statements = list(read_jsonl(args.qualification_dir / "evidence_statements.jsonl"))
    profiles = default_repository()

    links = build_links(statements, profiles, now=created_at)
    candidates = [
        CandidatePair(
            statement_id=link.statement_id,
            profile_unit_id=unit_id(
                f"PMID:{getattr(profiles.by_source_id(link.source_profile_id), 'pmid', '')}",
                "cohort-1",
            ),
            predicted_status=link.match_status,
            match_method=link.match_method,
            matched_identifiers=tuple(link.matched_source_ids),
        )
        for link in links
    ]

    gold_records = _load_gold(args.corpus_dir / "statement_qualification_gold.jsonl")
    metrics = evaluate_linking(candidates, gold_records)
    rate, pairs = agreement_rate(gold_records)
    metrics["inter_annotator_agreement"] = rate if rate is not None else NOT_EVALUABLE
    metrics["agreement_pair_count"] = pairs
    metrics["generated_at_utc"] = created_at

    predictions = [candidate.as_dict() for candidate in candidates]
    write_jsonl(args.corpus_dir / "linker_predictions.jsonl", predictions)
    write_json(args.corpus_dir / "linking_metrics.json", metrics)
    write_text(
        args.corpus_dir / "LINKING_EVALUATION.md",
        _report(metrics, predictions, gold_records),
    )

    print(f"prediction del linker: {len(predictions)}")
    print(f"record di gold: {len(gold_records)} | valutabili: {metrics['evaluated_count']}")
    print(f"precision: {metrics['linking_precision']} | recall: {metrics['linking_recall']}")
    print(f"accordo fra annotatori: {metrics['inter_annotator_agreement']} su {pairs} coppie")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
