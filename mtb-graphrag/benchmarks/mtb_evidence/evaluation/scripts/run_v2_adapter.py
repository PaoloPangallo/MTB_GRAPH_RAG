"""Esegue l'adapter V2 → EvidenceStatement sui record del pilota e ne misura la fedelta'.

    cd mtb-graphrag
    PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/run_v2_adapter.py \\
        --output benchmarks/mtb_evidence/evaluation/results/adapter_v1

Non tocca il grafo: legge i record gia' recuperati dagli artefatti dell'audit. La
domanda a cui risponde e' se il modello di evidenza V3 riesca a rappresentare i dati
che gia' esistono, senza perdere cio' che c'e' e senza inventare cio' che non c'e'.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.pipeline.evidence.adapter_metrics import (  # noqa: E402
    compatible_records,
    evaluate,
    meets_acceptance,
)
from backend.pipeline.evidence.v2_adapter import adapt_records  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
    write_text,
)

DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/pilot/audit")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def load_records(audit_dir: Path) -> tuple[list[dict], dict[str, str]]:
    """Record grezzi dell'audit più lo stato di presenza di ogni PMID.

    Lo stato viene dagli artefatti dell'audit, che lo hanno gia' determinato
    interrogando il grafo: distingue un PMID presente come nodo Publication da uno
    presente solo dentro Evidence.citation_id.
    """
    records: list[dict] = []
    presence: dict[str, str] = {}

    for case_dir in sorted(p for p in audit_dir.iterdir() if p.is_dir()):
        for row in read_jsonl(case_dir / "raw_records.jsonl"):
            record = row.get("record") if isinstance(row, dict) else None
            if isinstance(record, dict):
                records.append(record)

        entities_path = case_dir / "graph_entities.json"
        if entities_path.is_file():
            discovery = (
                json.loads(entities_path.read_text(encoding="utf-8"))
                .get("entities", {})
                .get("pmid_discovery", {})
            )
            for pmid in discovery.get("as_publication_node") or []:
                presence[str(pmid)] = "node"
            for pmid in discovery.get("as_evidence_citation") or []:
                presence.setdefault(str(pmid), "citation_only")
            for pmid in discovery.get("expected_absent_entirely") or []:
                presence[str(pmid)] = "absent"
    return records, presence


def _fingerprint(audit_dir: Path) -> str:
    manifest = audit_dir / "graph_snapshot_manifest.json"
    if not manifest.is_file():
        return ""
    return str(
        json.loads(manifest.read_text(encoding="utf-8"))
        .get("snapshot_fingerprint", {})
        .get("value", "")
    )


def _report(evaluation: dict, ok: bool, failures: list[str], fingerprint: str) -> str:
    measures = evaluation["measures"]
    lines = [
        "# Adapter V2 → EvidenceStatement — fedelta' della conversione",
        "",
        f"- **Snapshot:** `{fingerprint}`",
        f"- **Record compatibili:** {evaluation['compatible_records']}",
        f"- **Convertiti:** {evaluation['converted']}",
        f"- **Esito:** {'ACCETTATO' if ok else 'NON ACCETTATO'}",
        "",
        "Un record e' *compatibile* se e' un'evidenza con almeno una citazione. I record",
        "di trial descrivono uno studio, non una proposizione clinica, e diventeranno",
        "riferimenti di altri statement: contarli fra i fallimenti misurerebbe la cosa",
        "sbagliata.",
        "",
        "## Misure",
        "",
        "| Misura | Valore | Numeratore | Denominatore |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, measure in measures.items():
        value = measure["value"]
        rendered = "n/d" if value is None else f"{value:.4f}"
        lines.append(
            f"| `{name}` | {rendered} | {measure['numerator']:g} | {measure['denominator']:g} |"
        )

    lines += [
        "",
        "`source_field_preservation` ha come denominatore **solo i campi effettivamente",
        "presenti** nel record originale: chiedere di piu' misurerebbe la completezza del",
        "grafo, non la fedelta' dell'adapter.",
        "",
        "`unknown_field_honesty` verifica il contrario di tutte le altre: che un dato",
        "assente sia rimasto assente. Un adapter che riempisse i vuoti con valori",
        "plausibili otterrebbe punteggi migliori altrove e falsificherebbe la baseline.",
        "",
        "## Presenza delle fonti nello snapshot",
        "",
        "| Stato | Riferimenti |",
        "| --- | ---: |",
    ]
    for state, count in evaluation["source_presence_breakdown"].items():
        lines.append(f"| `{state}` | {count} |")
    lines += [
        "",
        "`citation_only` significa che il PMID esiste dentro `Evidence.citation_id` ma non",
        "come nodo `Publication`. E' recuperabile come citazione e non ha metadati",
        "bibliografici: appiattirlo su `node` nasconderebbe un limite reale del grafo.",
        "",
    ]

    if failures:
        lines += ["## Criteri non soddisfatti", ""]
        lines += [f"- {failure}" for failure in failures]
        lines.append("")

    for name, measure in measures.items():
        if measure["detail"]:
            lines += [f"### Dettaglio — `{name}`", ""]
            lines += [f"- {item}" for item in measure["detail"][:15]]
            lines.append("")

    lines += [
        "## Che cosa il grafo non contiene",
        "",
        "I qualificatori clinici — setting, stadio, linea di terapia, resezione,",
        "popolazione — non sono rappresentati dallo schema del grafo V2. L'adapter li",
        "lascia vuoti e lo registra: non e' un difetto della conversione ma la misura del",
        "punto di partenza, ed e' esattamente cio' che la V3 esiste per colmare.",
        "",
        "Anche il disegno dello studio (`evidence_type` nel senso V3) e' assente. Il campo",
        "`evidence_type` del grafo contiene i valori CIViC — Predictive, Prognostic — che",
        "descrivono il *tipo di affermazione* e nel modello V3 corrispondono a",
        "`evidence_scope`. Mapparlo su `evidence_type` sarebbe un errore di categoria.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    timestamp = args.timestamp or datetime.now(timezone.utc).isoformat()

    records, presence = load_records(args.audit_dir)
    fingerprint = _fingerprint(args.audit_dir)
    compatible = compatible_records(records)

    print(f"Record letti: {len(records)}")
    print(f"Record compatibili: {len(compatible)}")

    results = adapt_records(
        compatible, snapshot_fingerprint=fingerprint,
        source_presence=presence, now=timestamp,
    )
    evaluation = evaluate(results, compatible)
    ok, failures = meets_acceptance(evaluation)

    output = args.output
    write_jsonl(
        output / "evidence_statements.jsonl",
        [r.statement for r in results if r.converted and r.statement],
    )
    write_jsonl(
        output / "adaptation_outcomes.jsonl",
        [
            {
                "record_id": r.record_id,
                "converted": r.converted,
                "reason": r.reason,
                "preserved": r.preserved_fields,
                "absent": r.absent_fields,
                "unmapped": [f.__dict__ for f in r.unmapped_fields],
            }
            for r in results
        ],
    )
    write_json(
        output / "adapter_metrics.json",
        {"generated_at_utc": timestamp, "snapshot_fingerprint": fingerprint,
         "accepted": ok, "failures": failures, **evaluation},
    )
    write_text(output / "ADAPTER_REPORT.md", _report(evaluation, ok, failures, fingerprint))

    for name, measure in evaluation["measures"].items():
        value = measure["value"]
        print(f"  {name:28s} {'n/d' if value is None else f'{value:.4f}'}"
              f"  ({measure['numerator']:g}/{measure['denominator']:g})")
    print(f"\nEsito: {'ACCETTATO' if ok else 'NON ACCETTATO'}")
    for failure in failures:
        print(f"  - {failure}")
    print(f"Output: {output}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
