"""Packet di approvazione per l'autore, e prova che i packet ciechi non cambiano.

Questi packet possono mostrare la proposta source-checked: sono destinati alla
prima approvazione, e nasconderle renderebbe impossibile approvarle.

I packet della seconda revisione sono un'altra cosa. Restano ciechi, e la loro
invarianza viene **dimostrata**: gli hash sono calcolati prima e dopo la
generazione e confrontati file per file. Un controllo che si limitasse a
rileggere un hash registrato altrove proverebbe soltanto che quel numero non e'
cambiato.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.mtb_evidence.evaluation.clinical_preclinical_findings import FINDINGS  # noqa: E402
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_review import (  # noqa: E402
    AUTHOR_DECISIONS,
    FIELD_DECISIONS,
    REVIEW_VERSION,
    SOURCE_CHECKED_REVIEW_PROPOSAL,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_source_review_reports import QUESTIONS  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_text,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")
DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")
SECOND_REVIEW = Path("annotation_packets/second_review")
PACKET_DIR = Path("annotation_packets/author_approval")

# Termini che in un packet di approvazione non devono comparire. Il nome
# dell'autore incluso: chiedergli di approvare una proposta che lo cita gia'
# come revisore sarebbe una domanda a cui e' gia' stata data risposta.
FORBIDDEN_TERMS = ("clinical gold", "expected therapy", "terapia attesa", "Paolo", "Pangallo")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def hash_directory(directory: Path) -> dict[str, str]:
    if not directory.is_dir():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def build_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Approvazione — {payload['canonical_source_id']}",
        "",
        f"**Proposta: `{payload['structural_decision']}`** "
        f"({payload['audit_unit_count']} → {payload['reviewed_unit_count']} unita')",
        "",
        payload["decision_rationale"],
        "",
        "## Unita' proposte",
        "",
        "| Unita' | Tipo | In vitro | Statement |",
        "| --- | --- | :-: | --- |",
    ]
    for unit in payload["units"]:
        statements = ", ".join(f"`{item}`" for item in unit["statement_candidates"]) or "—"
        lines.append(
            f"| `{unit['proposed_profile_unit_id']}` | {unit['unit_type']} | "
            f"{'si' if unit['is_in_vitro'] else '—'} | {statements} |"
        )

    lines += ["", "## Statement", "", "| Statement | Supporto | Stato |", "| --- | --- | --- |"]
    for statement in payload["statements"]:
        lines.append(
            f"| `{statement['statement_id']}` | {statement['support_type']} | "
            f"**{statement['candidate_link_status']}** |"
        )

    lines += ["", "## Checklist", ""]
    for item in payload["checklist"]:
        lines.append(f"- [ ] {item}")

    lines += ["", "## Domande", ""]
    for index, question in enumerate(payload["questions_for_author"], start=1):
        lines.append(f"{index}. {question}")

    lines += [
        "",
        "## Modulo di decisione",
        "",
        "Decisione complessiva (una sola):",
        "",
    ]
    for decision in payload["available_decisions"]:
        lines.append(f"- [ ] `{decision}`")
    lines += [
        "",
        "Decisione per campo, ammessi: "
        + ", ".join(f"`{item}`" for item in payload["field_level_decisions"]),
        "",
        "```",
        f"review_status            = {SOURCE_CHECKED_REVIEW_PROPOSAL}",
        "human_reviewed           = false",
        "requires_author_approval = true",
        "```",
        "",
        "Nessuna approvazione e' registrata da questo packet: il modulo va compilato da",
        "una persona, e finche' non lo e' le proposte restano non propagabili.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    second_review_dir = args.curation_dir / SECOND_REVIEW
    before = hash_directory(second_review_dir)

    units = list(read_jsonl(args.output / "proposed_profile_units.jsonl"))
    statements = list(read_jsonl(args.output / "statement_unit_review_proposals.jsonl"))
    packet_dir = args.output / PACKET_DIR

    written: list[str] = []
    for finding in FINDINGS:
        parent = finding.parent_unit_id
        own_units = [row for row in units if row["parent_profile_unit_id"] == parent]
        own_statements = [row for row in statements if row["parent_profile_unit_id"] == parent]
        slug = finding.canonical_source_id.replace(":", "-")

        payload = {
            "packet_id": f"AA-{slug}",
            "canonical_source_id": finding.canonical_source_id,
            "parent_profile_unit_id": parent,
            "pmid": finding.pmid,
            "availability": finding.availability,
            "structural_decision": finding.decision,
            "decision_rationale": finding.decision_rationale,
            "audit_unit_count": finding.audit_unit_count,
            "reviewed_unit_count": finding.reviewed_unit_count,
            "units": [
                {
                    "proposed_profile_unit_id": row["proposed_profile_unit_id"],
                    "unit_type": row["unit_type"],
                    "unit_label": row["unit_label"],
                    "is_clinical": row["is_clinical"],
                    "is_preclinical": row["is_preclinical"],
                    "is_in_vitro": row["is_in_vitro"],
                    "is_in_vivo": row["is_in_vivo"],
                    "statement_candidates": row["statement_candidates"],
                    "field_decisions": row["field_decisions"],
                    "source_locators": row["source_locators"],
                }
                for row in own_units
            ],
            "statements": [
                {
                    "statement_id": row["statement_id"],
                    "support_type": row["support_type"],
                    "candidate_link_status": row["candidate_link_status"],
                    "proposed_profile_unit_ids": row["proposed_profile_unit_ids"],
                    "non_propagation_rules": row["non_propagation_rules"],
                }
                for row in own_statements
            ],
            "checklist": [
                "Le unita' proposte corrispondono a cio' che la fonte descrive?",
                "Il numero di unita' e' giusto, o va aumentato o ridotto?",
                "Gli statement sono attribuiti alle unita' corrette?",
                "I campi `unknown` sono davvero ignoti, e non «non applicabili»?",
                "Le dimensioni non separabili sono segnate come tali?",
                "I mapping terminologici che richiedono verifica sono accettabili?",
                "Serve una revisione clinica indipendente prima di procedere?",
            ],
            "questions_for_author": list(QUESTIONS[parent]),
            "available_decisions": list(AUTHOR_DECISIONS),
            "field_level_decisions": list(FIELD_DECISIONS),
            "limitations": list(finding.limitations),
            "residual_risk": finding.residual_risk,
            "review_status": SOURCE_CHECKED_REVIEW_PROPOSAL,
            "human_reviewed": False,
            "first_review_complete": False,
            "is_evaluable": False,
            "requires_author_approval": True,
            "requires_second_independent_review": True,
            "decision": None,
            "decided_by": None,
            "decided_at": None,
            "created_at": created_at,
            "review_version": REVIEW_VERSION,
        }

        markdown = build_markdown(payload)
        leaked = [term for term in FORBIDDEN_TERMS if term.casefold() in markdown.casefold()]
        if leaked:
            raise RuntimeError(f"packet {payload['packet_id']}: termini vietati {leaked}")

        write_json(packet_dir / f"AA-{slug}.json", payload)
        write_text(packet_dir / f"AA-{slug}.md", markdown)
        written.append(payload["packet_id"])

    after = hash_directory(second_review_dir)
    changed = sorted(
        name
        for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    )
    write_json(
        args.output / "second_review_blinding_check.json",
        {
            "created_at": created_at,
            "directory": str(SECOND_REVIEW).replace("\\", "/"),
            "file_count_before": len(before),
            "file_count_after": len(after),
            "byte_identical": not changed,
            "changed_files": changed,
            "hashes_before": before,
            "hashes_after": after,
            "review_version": REVIEW_VERSION,
        },
    )

    print(f"packet di approvazione: {len(written)} ({', '.join(written)})")
    print(f"packet di seconda revisione invariati: {not changed} ({len(after)} file)")
    return 0 if not changed else 1


if __name__ == "__main__":
    raise SystemExit(main())
