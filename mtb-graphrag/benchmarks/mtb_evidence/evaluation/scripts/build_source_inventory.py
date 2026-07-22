"""Costruisce l'inventario delle fonti dei 147 EvidenceStatement congelati."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.mtb_evidence.evaluation.source_inventory import (  # noqa: E402
    ALL_STRATA,
    SourceInventoryEntry,
    apply_metadata,
    build_inventory,
    stratum_counts,
)
from benchmarks.mtb_evidence.evaluation.source_profiles import default_repository  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    canonical_json,
    read_jsonl,
    write_jsonl,
    write_text,
)

DEFAULT_STATEMENTS = Path("benchmarks/mtb_evidence/v3/qualification/evidence_statements.jsonl")
DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/pilot/audit")
DEFAULT_PILOT = Path("benchmarks/mtb_evidence/evaluation/results/pilot_v1")
DEFAULT_CONFLICTS = Path("benchmarks/mtb_evidence/v3/qualification/conflicts.jsonl")
DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/qualification_corpus")

INVENTORY_COLUMNS = (
    "canonical_source_id",
    "source_type",
    "pmids",
    "dois",
    "ncts",
    "other_identifiers",
    "title",
    "title_provenance",
    "statement_count",
    "statement_ids",
    "graph_evidence_ids",
    "cases",
    "diseases",
    "biomarkers",
    "interventions",
    "directions",
    "evidence_scopes",
    "assertion_polarities",
    "evidence_levels",
    "presence_in_snapshot",
    "profile_status",
    "profile_ids",
    "strata",
    "requires_cohort_split",
    "cohort_split_reason",
    "annotation_priority",
    "priority_reason",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statements", type=Path, default=DEFAULT_STATEMENTS)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--pilot-dir", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--conflicts", type=Path, default=DEFAULT_CONFLICTS)
    parser.add_argument("--metadata-cache", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def _cell(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def write_csv(path: Path, rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> None:
    """CSV con newline esplicito, per non dipendere dalla piattaforma."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(column)) for column in columns])
    write_text(path, buffer.getvalue())


def write_matrix(path: Path, entries: Sequence[SourceInventoryEntry]) -> None:
    """Matrice fonte × statement: quante volte una fonte qualifica piu' statement.

    Non e' ridondante rispetto all'inventario: e' la forma in cui si vede a colpo
    d'occhio che una singola annotazione puo' propagarsi su molti statement, che
    e' proprio il rischio che le metriche di linking devono sorvegliare.
    """
    statement_ids = sorted({item for entry in entries for item in entry.statement_ids})
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["canonical_source_id", *statement_ids])
    for entry in entries:
        owned = set(entry.statement_ids)
        writer.writerow(
            [entry.canonical_source_id, *("1" if item in owned else "" for item in statement_ids)]
        )
    write_text(path, buffer.getvalue())


def inventory_hash(rows: Sequence[dict[str, Any]]) -> str:
    payload = canonical_json([{key: row[key] for key in sorted(row)} for row in rows])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_report(
    entries: Sequence[SourceInventoryEntry],
    statements: Sequence[dict[str, Any]],
    digest: str,
) -> str:
    counts = stratum_counts(entries)
    presence: dict[str, int] = {}
    kinds: dict[str, int] = {}
    for entry in entries:
        presence[entry.presence_in_snapshot] = presence.get(entry.presence_in_snapshot, 0) + 1
        for kind, values in (("pmid", entry.identity.pmids), ("doi", entry.identity.dois), ("nct", entry.identity.ncts)):
            if values:
                kinds[kind] = kinds.get(kind, 0) + 1

    covered = {item for entry in entries for item in entry.statement_ids}
    multi = [entry for entry in entries if entry.statement_count > 1]

    lines = [
        "# Inventario delle fonti dei 147 EvidenceStatement",
        "",
        f"- **Hash dell'inventario:** `{digest}`",
        f"- **Statement congelati:** {len(statements)}",
        f"- **Statement con almeno una fonte:** {len(covered)}",
        f"- **Fonti uniche:** {len(entries)}",
        "",
        "L'universo di selezione e' definito dagli statement congelati, non dal clinical",
        "gold. E' la sola scelta che permette al corpus di smentire il sistema invece di",
        "assecondarlo: annotare le fonti che il gold considera rilevanti misurerebbe",
        "quanto bene sappiamo gia' la risposta.",
        "",
        "## Identificatori",
        "",
        "| Tipo | Fonti |",
        "| --- | ---: |",
    ]
    for kind in sorted(kinds):
        lines.append(f"| {kind} | {kinds[kind]} |")

    lines += [
        "",
        "## Presenza nello snapshot",
        "",
        "| Stato | Fonti |",
        "| --- | ---: |",
    ]
    for state in sorted(presence):
        lines.append(f"| {state} | {presence[state]} |")
    lines += [
        "",
        "`citation_only` significa che il PMID compare dentro `Evidence.citation_id` ma",
        "non esiste come nodo `Publication`. La distinzione non e' cosmetica: una fonte",
        "citation_only non e' interrogabile come entita' del grafo, e un retriever che",
        "la trattasse come un nodo troverebbe zero risultati senza segnalare un errore.",
        "",
        "## Strati di copertura",
        "",
        "Gli strati **non** sono filtri di inclusione. Tutte le fonti inventariate sono",
        "nello scope; gli strati servono a verificare che il corpus contenga anche cio'",
        "che al sistema farebbe comodo non avere.",
        "",
        "| Strato | Fonti |",
        "| --- | ---: |",
    ]
    for stratum in ALL_STRATA:
        lines.append(f"| `{stratum}` | {counts[stratum]} |")

    lines += [
        "",
        "## Fonti che qualificano piu' statement",
        "",
        f"{len(multi)} fonti su {len(entries)} coprono piu' di uno statement.",
        "Una singola annotazione sbagliata su queste si propaga su tutti gli statement",
        "collegati, quindi la precisione del linking conta piu' del recall.",
        "",
        "| Fonte | Statement | Interventi distinti |",
        "| --- | ---: | ---: |",
    ]
    for entry in sorted(multi, key=lambda item: (-item.statement_count, item.canonical_source_id))[:15]:
        lines.append(
            f"| `{entry.canonical_source_id}` | {entry.statement_count} | {len(entry.interventions)} |"
        )

    split = [entry for entry in entries if entry.requires_cohort_split]
    lines += [
        "",
        "## Sospetta suddivisione in coorti",
        "",
        f"{len(split)} fonti presentano piu' interventi o piu' denominazioni di malattia",
        "fra i loro statement. E' un **sospetto**, non una conclusione: solo la lettura",
        "della fonte primaria puo' dire se si tratta di coorti distinte o della stessa",
        "coorte descritta in modi diversi. Finche' quella lettura non avviene, i",
        "qualificatori non vengono propagati.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    statements = list(read_jsonl(args.statements))
    entries = build_inventory(
        statements,
        audit_dir=args.audit_dir,
        ablation_manifest=args.pilot_dir / "reporting_ablation_manifest.json",
        conflicts_path=args.conflicts,
        pilot_runs=args.pilot_dir / "case_runs.jsonl",
        profiles=default_repository(),
    )

    if args.metadata_cache and args.metadata_cache.is_file():
        metadata = {
            str(row.get("identifier_key")): row for row in read_jsonl(args.metadata_cache)
        }
        apply_metadata(entries, metadata)

    rows = [entry.as_dict() for entry in entries]
    digest = inventory_hash(rows)

    output = args.output
    write_jsonl(output / "source_inventory.jsonl", rows)
    write_csv(output / "source_inventory.csv", rows, INVENTORY_COLUMNS)
    write_matrix(output / "source_statement_matrix.csv", entries)
    write_text(
        output / "SOURCE_INVENTORY_REPORT.md", build_report(entries, statements, digest)
    )
    write_text(
        output / "source_inventory_hash.json",
        canonical_json(
            {
                "source_inventory_hash": digest,
                "source_count": len(entries),
                "statement_count": len(statements),
            }
        )
        + "\n",
    )

    covered = {item for entry in entries for item in entry.statement_ids}
    print(f"fonti uniche: {len(entries)}")
    print(f"statement coperti: {len(covered)} / {len(statements)}")
    print(f"source_inventory_hash: {digest}")
    return 0 if len(covered) == len(statements) else 1


if __name__ == "__main__":
    raise SystemExit(main())
