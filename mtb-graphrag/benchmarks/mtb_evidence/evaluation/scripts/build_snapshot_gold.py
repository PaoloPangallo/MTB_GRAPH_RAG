"""Costruisce clinical gold e snapshot gold come oggetti distinti.

    cd mtb-graphrag
    PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/build_snapshot_gold.py

Il clinical gold e' una riorganizzazione dell'annotazione umana, verificata per
assenza di perdite. Lo snapshot gold registra che cosa di quell'annotazione e'
presente e raggiungibile nel grafo identificato dal fingerprint.

`proposed_gold_amendments.jsonl` **non** viene applicato: sono proposte per un
revisore, e applicarle qui lascerebbe che lo stato del grafo riscriva la verita'
clinica.
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

from benchmarks.mtb_evidence.evaluation.clinical_gold import (  # noqa: E402
    build_from_pilot,
    verify_no_loss,
)
from benchmarks.mtb_evidence.evaluation.snapshot_gold import (  # noqa: E402
    AuditArtifacts,
    build_snapshot_gold,
    mapping_rows,
    presence_summary,
)
from benchmarks.mtb_evidence.pilot.audit_lib.aliases import build_alias_table  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    sha256_file,
    write_json,
    write_jsonl,
    write_text,
)

DEFAULT_PILOT = Path("benchmarks/mtb_evidence/pilot/input/mtb_evidence_gold_pilot_v1.jsonl")
DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/pilot/audit")
DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/evaluation/data")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-gold", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _pilot_records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _report(clinical, snapshot, fingerprint: str, timestamp: str, integrity: dict) -> str:
    summary = presence_summary(snapshot)
    lines = [
        "# Clinical gold e snapshot gold",
        "",
        f"- **Generato:** {timestamp}",
        f"- **Fingerprint snapshot:** `{fingerprint}`",
        f"- **Casi:** {len(clinical)}",
        f"- **Hash del gold pilota di input:** `{integrity['pilot_sha256']}`",
        "",
        "Il clinical gold descrive cio' che dovrebbe essere ricostruito secondo fonti "
        "primarie e annotazione umana. Lo snapshot gold descrive cio' che di quella "
        "annotazione e' presente e raggiungibile in questo grafo. Sono oggetti "
        "distinti: una fonte clinica valida ma assente dal grafo abbassa la copertura "
        "del Knowledge Graph, non il recall del retriever.",
        "",
        "## Stati di presenza per tipo di elemento",
        "",
        "| Tipo | " + " | ".join(sorted({s for v in summary.values() for s in v})) + " |",
    ]
    all_states = sorted({s for v in summary.values() for s in v})
    lines.append("| --- | " + " | ".join("---" for _ in all_states) + " |")
    for kind, states in summary.items():
        row = " | ".join(str(states.get(state, 0)) for state in all_states)
        lines.append(f"| {kind} | {row} |")

    lines += ["", "## Per caso", ""]
    for case in snapshot:
        retrievable = [item for item in case.items if item.is_retrievable]
        lines += [
            f"### {case.case_id}",
            "",
            f"- elementi clinici mappati: {len(case.items)}",
            f"- recuperabili dallo snapshot: {len(retrievable)}",
            f"- terapie recuperabili: {list(case.retrievable_therapies) or 'nessuna'}",
            f"- PMID recuperabili: {list(case.retrievable_pmids) or 'nessuno'}",
            f"- NCT recuperabili: {list(case.retrievable_nct_ids) or 'nessuno'}",
            f"- astensione attesa: {'si' if case.expected_abstention else 'no'}",
            "",
        ]
        for note in case.notes[:6]:
            lines.append(f"  - {note}")
        lines.append("")

    lines += [
        "## Integrita'",
        "",
        f"- clinical gold non modificato rispetto al pilota: "
        f"{'si' if not integrity['losses'] else 'NO'}",
        f"- emendamenti proposti NON applicati: {integrity['amendments_seen']} "
        "righe lette e ignorate deliberatamente",
        "",
    ]
    if integrity["losses"]:
        lines.append("### Perdite rilevate nella conversione")
        lines.append("")
        for loss in integrity["losses"]:
            lines.append(f"- {loss}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    timestamp = args.timestamp or datetime.now(timezone.utc).isoformat()

    pilot_path = args.pilot_gold
    records = _pilot_records(pilot_path)
    clinical = build_from_pilot(pilot_path)
    losses = verify_no_loss(records, clinical)
    if losses:
        print("ERRORE: la conversione ha perso informazione dal gold pilota:")
        for loss in losses:
            print("  -", loss)
        return 2

    artifacts = AuditArtifacts(args.audit_dir)
    fingerprint = artifacts.fingerprint
    if not fingerprint:
        print("ERRORE: fingerprint dello snapshot assente dal manifest di audit")
        return 3

    alias_table = build_alias_table()
    snapshot = [
        build_snapshot_gold(case, artifacts, alias_table=alias_table) for case in clinical
    ]

    amendments_path = args.audit_dir / "proposed_gold_amendments.jsonl"
    amendments_seen = (
        len([line for line in amendments_path.read_text(encoding="utf-8").splitlines() if line.strip()])
        if amendments_path.is_file()
        else 0
    )

    output = args.output
    write_jsonl(output / "clinical_gold_v1.jsonl", [case.as_dict() for case in clinical])
    write_jsonl(
        output / f"snapshot_gold_{fingerprint[:16]}.jsonl",
        [case.as_dict() for case in snapshot],
    )
    write_jsonl(output / "clinical_snapshot_mapping.jsonl", mapping_rows(clinical, snapshot))

    integrity = {
        "pilot_sha256": sha256_file(pilot_path),
        "losses": losses,
        "amendments_seen": amendments_seen,
        "amendments_applied": 0,
    }
    write_json(
        output / "gold_build_manifest.json",
        {
            "generated_at_utc": timestamp,
            "snapshot_fingerprint": fingerprint,
            "pilot_gold_path": str(pilot_path),
            "pilot_gold_sha256": integrity["pilot_sha256"],
            "audit_dir": str(args.audit_dir),
            "case_count": len(clinical),
            "presence_summary": presence_summary(snapshot),
            "amendments_seen_but_not_applied": amendments_seen,
            "policy": (
                "Il clinical gold non viene modificato in alcun modo. Le proposte di "
                "emendamento dell'audit sono lette solo per essere contate."
            ),
        },
    )
    write_text(
        output / "snapshot_gold_report.md",
        _report(clinical, snapshot, fingerprint, timestamp, integrity),
    )

    print(f"Fingerprint snapshot: {fingerprint}")
    print(f"Casi: {len(clinical)}")
    for case in snapshot:
        retrievable = sum(1 for item in case.items if item.is_retrievable)
        print(f"  {case.case_id:32s} elementi={len(case.items):3d} recuperabili={retrievable:3d}")
    print(f"Emendamenti letti e NON applicati: {amendments_seen}")
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
