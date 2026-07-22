"""Congela il perimetro della curation prioritaria."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_manifest import content_hash  # noqa: E402
from benchmarks.mtb_evidence.evaluation.priority_curation import (  # noqa: E402
    PRIORITY_CLASSES,
    PRIORITY_SCOPE_VERSION,
    WORK_ORDER,
    build_priority_queue,
    group_overlap,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_source_inventory import (  # noqa: E402
    write_csv,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
    write_text,
)

DEFAULT_CORPUS = Path("benchmarks/mtb_evidence/v3/qualification_corpus")
DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/priority_curation")

COLUMNS = (
    "priority_rank",
    "profile_unit_id",
    "canonical_source_id",
    "priority_class",
    "work_bucket",
    "risk_band",
    "propagation_risk",
    "statement_count",
    "pmids",
    "title",
    "diseases",
    "interventions",
    "directions",
    "assertion_polarities",
    "candidate_cohort_count",
    "candidate_intervention_count",
    "current_cohort_state",
    "current_review_status",
    "source_availability",
    "needs_external_access",
    "rationale",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def write_matrix(path: Path, queue: Sequence[Any]) -> None:
    import csv
    import io

    statement_ids = sorted({item for unit in queue for item in unit.statement_ids})
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["profile_unit_id", "canonical_source_id", *statement_ids])
    for unit in queue:
        owned = set(unit.statement_ids)
        writer.writerow(
            [
                unit.profile_unit_id,
                unit.canonical_source_id,
                *("1" if item in owned else "" for item in statement_ids),
            ]
        )
    write_text(path, buffer.getvalue())


def build_report(queue: Sequence[Any], overlap: dict[str, Any], digest: str) -> str:
    by_class: dict[str, int] = {}
    by_band: dict[str, int] = {}
    for unit in queue:
        by_class[unit.priority_class] = by_class.get(unit.priority_class, 0) + 1
        by_band[unit.risk_band] = by_band.get(unit.risk_band, 0) + 1

    lines = [
        "# Perimetro della curation prioritaria",
        "",
        f"- **Hash del perimetro:** `{digest}`",
        f"- **Unita' prioritarie:** {len(queue)}",
        "",
        "## Composizione dei gruppi",
        "",
        "| Gruppo | Unita' |",
        "| --- | ---: |",
        f"| A — coorte irrisolta | {overlap['group_a_unresolved_cohort']} |",
        f"| B — multi-statement | {overlap['group_b_multi_statement']} |",
        f"| **A ∩ B** | **{overlap['overlap_ab']}** |",
        f"| solo A | {overlap['a_only']} |",
        f"| solo B | {overlap['b_only']} |",
        f"| solo conflitto | {overlap['conflict_only']} |",
        f"| **unione** | **{overlap['union_total']}** |",
        "",
        "### Perche' A e' contenuto in B",
        "",
        overlap["overlap_note"],
        "",
        "La conseguenza pratica va detta: il numero di unita' prioritarie e'",
        f"{overlap['union_total']} e non la somma 16 + 29, perche' i due gruppi non sono",
        "disgiunti. Piu' importante, il rilevatore di coorti multiple ha un punto cieco",
        "noto e non stimabile con i dati attuali.",
        "",
        "## Classi",
        "",
        "| Classe | Unita' |",
        "| --- | ---: |",
    ]
    for name in PRIORITY_CLASSES:
        lines.append(f"| `{name}` | {by_class.get(name, 0)} |")

    lines += [
        "",
        "Le unita' conflittuali fuori da A e B sono **incluse** anche se l'obiettivo le",
        "richiedeva solo dentro A o B. Un conflitto e' il caso di propagazione piu'",
        "pericoloso gia' noto: escluderlo per rispettare il perimetro sarebbe la scelta",
        "rischiosa, includerlo costa soltanto lavoro.",
        "",
        "## Rischio di propagazione",
        "",
        "Il rischio e' `probabilita' dell'errore × numero di statement colpiti`. Il",
        "conteggio degli statement e' il moltiplicatore: e' su quante proposizioni",
        "l'errore si propaga. Per questo una fonte con otto statement e coorte ambigua",
        "precede una con venti statement e coorte unica.",
        "",
        "| Banda | Unita' |",
        "| --- | ---: |",
    ]
    for band in ("critical", "high", "medium", "low"):
        if band in by_band:
            lines.append(f"| {band} | {by_band[band]} |")

    lines += [
        "",
        "## Ordine di lavorazione",
        "",
        "| # | Bucket | Unita' |",
        "| ---: | --- | ---: |",
    ]
    counts: dict[str, int] = {}
    for unit in queue:
        counts[unit.work_bucket] = counts.get(unit.work_bucket, 0) + 1
    for bucket, order in sorted(WORK_ORDER.items(), key=lambda item: item[1]):
        lines.append(f"| {order + 1} | `{bucket}` | {counts.get(bucket, 0)} |")

    lines += [
        "",
        "## Prime dieci unita'",
        "",
        "| # | Unita' | Fonte | Statement | Rischio | Motivazione |",
        "| ---: | --- | --- | ---: | --- | --- |",
    ]
    for unit in queue[:10]:
        lines.append(
            f"| {unit.priority_rank} | `{unit.profile_unit_id}` | "
            f"`{unit.canonical_source_id}` | {unit.statement_count} | "
            f"{unit.risk_band} ({unit.propagation_risk}) | {unit.rationale} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    corpus = args.corpus_dir
    output = args.output
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    units = list(read_jsonl(corpus / "source_profile_units.jsonl"))
    inventory = {
        str(row.get("canonical_source_id")): row
        for row in read_jsonl(corpus / "source_inventory.jsonl")
    }
    conflicts = list(read_jsonl(corpus / "conflicts.jsonl"))
    metadata_keys = [
        str(row.get("identifier_key")) for row in read_jsonl(corpus / "source_metadata_cache.jsonl")
    ]
    abstract_cache = args.output / "source_abstract_cache.jsonl"
    abstract_keys = (
        [str(row.get("identifier_key")) for row in read_jsonl(abstract_cache)]
        if abstract_cache.is_file()
        else []
    )

    queue = build_priority_queue(
        units,
        inventory,
        conflicts,
        abstracts_available=abstract_keys,
        metadata_available=metadata_keys,
    )
    rows = [unit.as_dict() for unit in queue]
    digest = content_hash(rows)
    overlap = group_overlap(queue)

    write_jsonl(output / "priority_units.jsonl", rows)
    write_csv(output / "priority_units.csv", rows, COLUMNS)
    write_matrix(output / "priority_source_statement_matrix.csv", queue)
    write_text(output / "PRIORITY_SCOPE_REPORT.md", build_report(queue, overlap, digest))

    corpus_manifest = read_jsonl(corpus / "source_inventory.jsonl")
    import json

    previous = json.loads(
        (corpus / "qualification_corpus_manifest.json").read_text(encoding="utf-8")
    )
    write_json(
        output / "priority_scope_manifest.json",
        {
            "scope_version": PRIORITY_SCOPE_VERSION,
            "created_at": created_at,
            "priority_scope_hash": digest,
            "source_inventory_hash": previous["source_inventory_hash"],
            "statement_repository_hash": previous["statement_repository_hash"],
            "qualification_scope_hash": previous["qualification_scope_hash"],
            "snapshot_fingerprint": previous["snapshot_fingerprint"],
            "priority_unit_count": len(queue),
            "group_composition": overlap,
            "clinical_gold_used": False,
            "selection_criterion": (
                "rischio di propagazione errata, non guadagno atteso sulle metriche"
            ),
        },
    )

    print(f"unita' prioritarie: {len(queue)}")
    print(
        f"A={overlap['group_a_unresolved_cohort']} B={overlap['group_b_multi_statement']} "
        f"AB={overlap['overlap_ab']} solo-conflitto={overlap['conflict_only']}"
    )
    print(f"priority_scope_hash: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
