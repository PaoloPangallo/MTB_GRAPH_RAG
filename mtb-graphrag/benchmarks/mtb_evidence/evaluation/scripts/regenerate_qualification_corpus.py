"""Rigenera le unita' canoniche del qualification corpus dagli otto artefatti.

Lo stato corrente di una unita' non vive in nessun file: vive nell'ordine in cui
otto directory vanno lette. Questo script scrive quell'ordine una volta sola,
come dato, e lo esegue.

    cd mtb-graphrag
    PYTHONPATH=. python benchmarks/mtb_evidence/evaluation/scripts/\\
regenerate_qualification_corpus.py --timestamp 2026-07-24T18:00:00+00:00

Due scelte che sembrano dettagli e non lo sono.

**Storia e decisione hanno rank diversi dentro la stessa fase.** Le approvazioni
scrivono due file: le unita' approvate e lo storico delle proposte, e per tre
unita' di PMID 22235099 lo stesso id compare in entrambi con `is_active` opposto.
Non e' una contraddizione: lo storico fotografa la proposta *prima*
dell'approvazione. Dando allo storico il rank pari e alle unita' il rank dispari
della stessa fase, l'id condiviso si risolve verso l'approvazione e gli id che
esistono solo nello storico restano inattivi — senza casi speciali.

**Le proposte non nascono attive.** Una unita' proposta da un audit o da una
verifica documentale e' una ipotesi: `is_active` parte da falso, e soltanto una
approvazione la accende. Il contrario avrebbe reso attive sei proposte che
nessuno ha mai approvato.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_regeneration import (  # noqa: E402
    DERIVED_POLICY_FIELDS,
    EXPECTED_AUTHOR_APPROVAL,
    EXPECTED_HISTORY_UPDATE,
    EXPECTED_POLICY_MIGRATION,
    EXPECTED_UNIT_RESTRUCTURE,
    REGENERATION_VERSION,
    SourceLayer,
    UnresolvedMergeConflict,
    apply_policy,
    merge_records,
    migrate_policy,
    stable_hash,
    validate_active_units,
    validate_integrity,
    validate_policy_fields,
)
from backend.pipeline.evidence.profile_unit import PROFILE_UNIT_VERSION  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

V3 = Path("benchmarks/mtb_evidence/v3")
DEFAULT_OUTPUT = V3 / "qualification_corpus_v2"
DEFAULT_STATEMENTS = Path(
    "benchmarks/mtb_evidence/evaluation/results/adapter_v1/evidence_statements.jsonl"
)

# --- la precedenza, dichiarata una volta --------------------------------------
# `rank` cresce con l'autorita'. I rank pari sono storia (fotografie di uno stato
# precedente), i dispari sono decisioni. Nessun rank e' condiviso da due strati
# che possano parlare della stessa entita': un pareggio sarebbe un conflitto, e i
# conflitti fanno fallire la rigenerazione invece di essere risolti da una regola.
LAYERS: tuple[tuple[SourceLayer, str, bool], ...] = (
    (
        SourceLayer("qualification_corpus_base", 3, "qualification_corpus/source_profile_units.jsonl",
                    change_class=EXPECTED_UNIT_RESTRUCTURE),
        "qualification_corpus/source_profile_units.jsonl",
        True,
    ),
    (
        SourceLayer("priority_curation_unresolved", 4,
                    "priority_curation/unresolved_profile_units.jsonl",
                    change_class=EXPECTED_UNIT_RESTRUCTURE),
        "priority_curation/unresolved_profile_units.jsonl",
        True,
    ),
    (
        SourceLayer("priority_curation_resolved", 5,
                    "priority_curation/resolved_profile_units.jsonl",
                    change_class=EXPECTED_UNIT_RESTRUCTURE),
        "priority_curation/resolved_profile_units.jsonl",
        True,
    ),
    (
        SourceLayer("cohort_split_audit_proposals", 6,
                    "cohort_split_audit/proposed_profile_units.jsonl",
                    change_class=EXPECTED_UNIT_RESTRUCTURE),
        "cohort_split_audit/proposed_profile_units.jsonl",
        False,
    ),
    (
        SourceLayer("clinical_preclinical_review_proposals", 8,
                    "clinical_preclinical_review_batch/proposed_profile_units.jsonl",
                    change_class=EXPECTED_UNIT_RESTRUCTURE),
        "clinical_preclinical_review_batch/proposed_profile_units.jsonl",
        False,
    ),
    (
        SourceLayer("first_review_22277784_history", 10,
                    "first_review/superseded_profile_units.jsonl",
                    change_class=EXPECTED_HISTORY_UPDATE),
        "first_review/superseded_profile_units.jsonl",
        False,
    ),
    (
        SourceLayer("first_review_22277784_units", 11, "first_review/reviewed_profile_units.jsonl",
                    change_class=EXPECTED_AUTHOR_APPROVAL),
        "first_review/reviewed_profile_units.jsonl",
        True,
    ),
    (
        SourceLayer("author_approval_31358542_history", 12,
                    "author_approval/parent_unit_history.jsonl",
                    change_class=EXPECTED_HISTORY_UPDATE),
        "author_approval/parent_unit_history.jsonl",
        False,
    ),
    (
        SourceLayer("author_approval_31358542_units", 13,
                    "author_approval/approved_profile_units.jsonl",
                    change_class=EXPECTED_AUTHOR_APPROVAL),
        "author_approval/approved_profile_units.jsonl",
        True,
    ),
    (
        SourceLayer("author_approval_22235099_history", 14,
                    "author_approval_22235099/parent_unit_history.jsonl",
                    change_class=EXPECTED_HISTORY_UPDATE),
        "author_approval_22235099/parent_unit_history.jsonl",
        False,
    ),
    (
        SourceLayer("author_approval_22235099_units", 15,
                    "author_approval_22235099/approved_profile_units.jsonl",
                    change_class=EXPECTED_AUTHOR_APPROVAL),
        "author_approval_22235099/approved_profile_units.jsonl",
        True,
    ),
    (
        SourceLayer("author_approval_23344087_history", 16,
                    "author_approval_23344087/parent_unit_history.jsonl",
                    change_class=EXPECTED_HISTORY_UPDATE),
        "author_approval_23344087/parent_unit_history.jsonl",
        False,
    ),
    (
        SourceLayer("author_approval_23344087_units", 17,
                    "author_approval_23344087/approved_profile_units.jsonl",
                    change_class=EXPECTED_AUTHOR_APPROVAL),
        "author_approval_23344087/approved_profile_units.jsonl",
        True,
    ),
)

# I campi che uno strato di storia puo' dire. Una riga di storico non e' una
# unita': se la lasciassimo contribuire tutti i suoi campi, sostituirebbe il
# record con una fotografia parziale — e `unit_label` o `note` cancellerebbero
# valori clinici che nessuno ha messo in discussione.
HISTORY_FIELDS = (
    "profile_unit_id",
    "canonical_source_id",
    "is_active",
    "review_status",
    "cohort_state",
    "superseded_by",
    "supersedes",
    "replacement_unit",
    "parent_state",
    "role",
    "rejection_reason",
    "replacement_reason",
    "retained_for",
    "rejected_as_false",
    "rejected_for_lack_of_source_resolution",
    "historical_references_preserved",
    "statement_candidates_preserved",
    "note",
)

REGENERATION_REASON = (
    "incorporare la politica di propagazione normalizzata e le quattro prime "
    "revisioni approvate in un corpus unico, eliminando i flag serializzati che il "
    "codice non onora piu'"
)


class RegenerationFailure(RuntimeError):
    """La rigenerazione non puo' produrre un corpus coerente."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--v3-dir", type=Path, default=V3)
    parser.add_argument("--statements", type=Path, default=DEFAULT_STATEMENTS)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument(
        "--reverse-input-order",
        action="store_true",
        help=(
            "legge gli strati in ordine inverso. Il risultato deve essere identico: "
            "se non lo e', la precedenza dipende dall'ordine di lettura e non e' una "
            "precedenza"
        ),
    )
    return parser.parse_args(argv)


def unit_id_of(row: dict[str, Any]) -> str:
    return str(row.get("profile_unit_id") or row.get("proposed_profile_unit_id") or "")


def collect_contributions(
    v3_dir: Path, *, reverse: bool = False
) -> tuple[dict[str, list[tuple[SourceLayer, dict[str, Any]]]], dict[str, str]]:
    """Le righe di ogni strato, indicizzate per unita', con l'hash dell'artefatto."""
    layers = list(reversed(LAYERS)) if reverse else list(LAYERS)
    contributions: dict[str, list[tuple[SourceLayer, dict[str, Any]]]] = {}
    artifact_hashes: dict[str, str] = {}

    for layer, relative, active_default in layers:
        path = v3_dir / relative
        rows = list(read_jsonl(path))
        artifact_hashes[layer.layer_id] = stable_hash(rows)
        is_history = layer.change_class == EXPECTED_HISTORY_UPDATE
        for row in rows:
            unit_id = unit_id_of(row)
            if not unit_id:
                continue
            payload = (
                {key: value for key, value in row.items() if key in HISTORY_FIELDS}
                if is_history
                else dict(row)
            )
            payload.setdefault("profile_unit_id", unit_id)
            payload.setdefault("is_active", active_default)
            payload["source_layer"] = layer.layer_id
            contributions.setdefault(unit_id, []).append((layer, payload))
    return contributions, artifact_hashes


def build_units(
    contributions: dict[str, list[tuple[SourceLayer, dict[str, Any]]]],
    artifact_hashes: dict[str, str],
    *,
    created_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Unita' canoniche, audit del merge, migrazione della politica, conflitti."""
    units: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    migrations: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for unit_id in sorted(contributions):
        merged = merge_records(unit_id, contributions[unit_id])
        if merged.has_conflicts:
            conflicts.extend(
                {"entity_id": unit_id, **conflict} for conflict in merged.conflicts
            )

        record = dict(merged.record)
        record.pop("source_layer", None)
        record.pop("proposed_profile_unit_id", None)
        record["profile_unit_id"] = unit_id
        record["contributing_layers"] = list(merged.candidate_layers)
        record["canonical_layer"] = merged.selected_layer
        record["schema_version"] = PROFILE_UNIT_VERSION
        record["corpus_regeneration_version"] = REGENERATION_VERSION

        migration = migrate_policy(record)
        migrations.append(migration.as_dict())
        record = apply_policy(record)
        units.append(record)

        audit.append(
            merged.audit_row(
                rationale=(
                    f"{len(merged.candidate_layers)} strati hanno parlato di questa unita'; "
                    f"prevale {merged.selected_layer} per i campi che dichiara, gli altri "
                    "restano dello strato sottostante"
                ),
                artifact_hashes=artifact_hashes,
            )
        )

    return units, audit, migrations, conflicts


def count_stale_input_flags(v3_dir: Path) -> tuple[int, list[dict[str, Any]]]:
    """Quanti flag serializzati obsoleti esistono negli artefatti di ingresso.

    Il conteggio va fatto **prima** del merge, sulle righe cosi' come sono scritte
    su disco. Farlo sul record fuso darebbe sempre zero — il merge scarta i campi
    calcolati dalla politica — e zero non e' la risposta alla domanda «quanti dati
    vecchi c'erano»: e' la risposta a «quanti ne ho copiati», che e' un'altra cosa
    e vale zero per costruzione.
    """
    rows: list[dict[str, Any]] = []
    for layer, relative, _ in LAYERS:
        path = v3_dir / relative
        for raw in read_jsonl(path):
            if not any(key in raw for key in DERIVED_POLICY_FIELDS):
                continue
            migration = migrate_policy(raw)
            if not migration.stale_serialized_fields:
                continue
            rows.append(
                {
                    "profile_unit_id": unit_id_of(raw),
                    "source_layer": layer.layer_id,
                    "source_artifact": relative,
                    "stale_fields": list(migration.stale_serialized_fields),
                    "serialized": {
                        key: raw[key] for key in migration.stale_serialized_fields
                    },
                    "recomputed": {
                        key: migration.after[key] for key in migration.stale_serialized_fields
                    },
                    "reason": migration.reason,
                    "change_class": EXPECTED_POLICY_MIGRATION,
                    "regeneration_version": REGENERATION_VERSION,
                }
            )
    return len(rows), rows


def build_inventory(units: list[dict[str, Any]], *, created_at: str) -> list[dict[str, Any]]:
    """Una riga per fonte, con quante unita' attive e storiche porta."""
    by_source: dict[str, list[dict[str, Any]]] = {}
    for unit in units:
        by_source.setdefault(str(unit.get("canonical_source_id") or ""), []).append(unit)

    rows: list[dict[str, Any]] = []
    for source_id in sorted(by_source):
        group = by_source[source_id]
        active = [unit for unit in group if unit.get("is_active")]
        rows.append(
            {
                "canonical_source_id": source_id,
                "pmids": sorted({pmid for unit in group for pmid in unit.get("pmids") or []}),
                "profile_unit_count": len(group),
                "active_profile_unit_count": len(active),
                "historical_profile_unit_count": len(group) - len(active),
                "active_profile_unit_ids": sorted(unit["profile_unit_id"] for unit in active),
                "review_statuses": sorted({str(unit.get("review_status") or "") for unit in group}),
                "propagation_eligibilities": sorted(
                    {str(unit.get("propagation_eligibility") or "") for unit in active}
                ),
                "source_basis": sorted(
                    {str(unit.get("source_basis") or "unknown") for unit in active}
                ),
                "author_approved": any(unit.get("author_decision") for unit in group),
                "created_at": created_at,
                "regeneration_version": REGENERATION_VERSION,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    contributions, artifact_hashes = collect_contributions(
        args.v3_dir, reverse=args.reverse_input_order
    )
    units, audit, migrations, conflicts = build_units(
        contributions, artifact_hashes, created_at=created_at
    )
    if conflicts:
        write_jsonl(args.output / "unresolved_merge_conflicts.jsonl", conflicts)
        raise UnresolvedMergeConflict(
            f"{len(conflicts)} conflitti di merge non risolti: "
            + "; ".join(f"{c['entity_id']}.{c['field_name']}" for c in conflicts[:5])
        )

    active = [unit for unit in units if unit.get("is_active")]
    historical = [unit for unit in units if not unit.get("is_active")]

    findings = (
        validate_active_units(active)
        + validate_policy_fields(units)
        + validate_integrity(units)
    )
    if findings:
        write_jsonl(
            args.output / "validation_findings.jsonl", [f.as_dict() for f in findings]
        )
        raise RegenerationFailure(
            f"{len(findings)} violazioni: "
            + "; ".join(f"[{f.rule_id}] {f.message}" for f in findings[:5])
        )

    statements = list(read_jsonl(args.statements))
    inventory = build_inventory(units, created_at=created_at)

    write_jsonl(args.output / "evidence_statements.jsonl", statements)
    write_jsonl(args.output / "source_inventory.jsonl", inventory)
    write_jsonl(args.output / "source_profile_units.jsonl", units)
    write_jsonl(args.output / "active_source_profile_units.jsonl", active)
    write_jsonl(args.output / "historical_source_profile_units.jsonl", historical)
    write_jsonl(args.output / "canonical_merge_audit.jsonl", audit)
    write_jsonl(args.output / "policy_migration.jsonl", migrations)

    stale_before, stale_rows = count_stale_input_flags(args.v3_dir)
    write_jsonl(args.output / "obsolete_serialized_flags.jsonl", stale_rows)
    stale_after = sum(
        1 for unit in units if migrate_policy(unit).stale_serialized_fields
    )
    scope = {
        "created_at": created_at,
        "regeneration_version": REGENERATION_VERSION,
        "regeneration_reason": REGENERATION_REASON,
        "precedence_order": [layer.layer_id for layer, _, _ in LAYERS],
        "artifact_hashes": artifact_hashes,
        "source_count": len(inventory),
        "profile_unit_count": len(units),
        "active_profile_unit_count": len(active),
        "historical_profile_unit_count": len(historical),
        "statement_count": len(statements),
        "obsolete_serialized_flags_before": stale_before,
        "obsolete_serialized_flags_after": stale_after,
        "obsolete_serialized_flags_by_artifact": dict(
            sorted(Counter(row["source_artifact"] for row in stale_rows).items())
        ),
        "derived_policy_fields": list(DERIVED_POLICY_FIELDS),
        "reverse_input_order": bool(args.reverse_input_order),
    }
    write_json(args.output / "qualification_scope.json", scope)

    print(f"unita' canoniche: {len(units)} ({len(active)} attive, {len(historical)} storiche)")
    print(f"fonti: {len(inventory)} · statement: {len(statements)}")
    print(f"flag serializzati obsoleti: {stale_before} prima, {stale_after} dopo")
    print("review status:", dict(Counter(u.get("review_status") for u in units)))
    print("eligibility:", dict(Counter(u.get("propagation_eligibility") for u in units)))
    print("eligibility (attive):", dict(Counter(u.get("propagation_eligibility") for u in active)))
    print(f"conflitti di merge: {len(conflicts)} · violazioni: {len(findings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
