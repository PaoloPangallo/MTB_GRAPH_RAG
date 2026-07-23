"""Esegue le guardie di propagazione sulle proposte del batch.

Scrive soltanto nella cartella di questa fase: gli artefatti dell'audit
strutturale non vengono rigenerati, perche' dichiarano lo stato di allora e
riscriverli cancellerebbe la storia che serve a rileggere le sue metriche.

L'esito e' registrato per fonte, con i campi bloccati e quelli propagabili
distinti. Una violazione irrisolta mantiene `is_propagatable = false` — ma in
questa fase nessuna proposta e' propagabile comunque, perche' nessuna e' stata
approvata: la guardia e' un secondo lucchetto, non il primo.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.propagation_guards import (  # noqa: E402
    ALL_RULE_IDS,
    GUARD_VERSION,
    run_guards,
)
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_review import (  # noqa: E402
    REVIEW_VERSION,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")

# I dodici divieti della fase, con la regola che li fa rispettare. Elencarli
# esplicitamente serve a poter dire quale divieto resta scoperto, invece di
# fidarsi che «le regole ci sono».
REQUIRED_PROHIBITIONS = (
    ("popolazione clinica verso modello preclinico", "clinical_population_to_model"),
    ("setting clinico verso modello", "clinical_dimensions_to_model"),
    ("linea terapeutica verso modello", "clinical_dimensions_to_model"),
    ("stage clinico verso modello", "clinical_dimensions_to_model"),
    ("comparatore cellulare verso pazienti", "model_comparator_to_patients"),
    ("risposta in vitro trasformata in beneficio clinico", "in_vitro_to_clinical_benefit"),
    ("proprieta' di un modello attribuita a un altro modello", "cross_model_identity"),
    ("proprieta' di una coorte attribuita a un'altra coorte", "cross_cohort_identity"),
    ("intervento di un esperimento attribuito a un altro", "cross_arm_intervention"),
    ("mapping terminologico senza provenance", "mapping_needs_provenance"),
    ("resistenza relativa trasformata in completa", "relative_versus_complete_resistance"),
    ("reperto molecolare trasformato in criterio di arruolamento", "observed_biomarker_to_requirement"),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    units = list(read_jsonl(args.output / "proposed_profile_units.jsonl"))
    decisions = list(read_jsonl(args.output / "statement_unit_review_proposals.jsonl"))
    mappings = list(read_jsonl(args.output / "terminology_mappings.jsonl"))

    violations = run_guards(units=units, decisions=decisions, mappings=mappings)
    by_subject: dict[str, list[dict[str, Any]]] = {}
    for item in violations:
        by_subject.setdefault(item.subject, []).append(item.as_dict())

    rows: list[dict[str, Any]] = []
    for unit in units:
        unit_id = str(unit["proposed_profile_unit_id"])
        found = by_subject.get(unit_id, [])
        blocked = sorted({dimension for item in found for dimension in item["dimensions"]})
        propagatable_fields = [
            dimension
            for dimension in unit.get("known_dimensions") or ()
            if dimension not in blocked
        ]
        rows.append(
            {
                "proposed_profile_unit_id": unit_id,
                "parent_profile_unit_id": unit["parent_profile_unit_id"],
                "canonical_source_id": unit["canonical_source_id"],
                "rules_executed": list(ALL_RULE_IDS),
                "violations": found,
                "violation_count": len(found),
                "blocked_fields": blocked,
                "propagatable_fields": propagatable_fields,
                # Vale a prescindere dall'esito delle guardie: nessuna proposta
                # e' propagabile prima dell'approvazione dell'autore.
                "is_propagatable": False,
                "outcome": "clean" if not found else "blocked",
                "created_at": created_at,
                "guard_version": GUARD_VERSION,
                "review_version": REVIEW_VERSION,
            }
        )

    rows.sort(key=lambda row: row["proposed_profile_unit_id"])
    write_jsonl(args.output / "propagation_guard_results.jsonl", rows)

    by_rule = {rule: 0 for rule in ALL_RULE_IDS}
    for item in violations:
        by_rule[item.rule_id] = by_rule.get(item.rule_id, 0) + 1

    missing = [name for name, rule in REQUIRED_PROHIBITIONS if rule not in ALL_RULE_IDS]
    write_json(
        args.output / "propagation_guard_summary.json",
        {
            "created_at": created_at,
            "guard_version": GUARD_VERSION,
            "review_version": REVIEW_VERSION,
            "rules_available": list(ALL_RULE_IDS),
            "units_checked": len(units),
            "decisions_checked": len(decisions),
            "mappings_checked": len(mappings),
            "violations_total": len(violations),
            "violations_by_rule": by_rule,
            "required_prohibitions": [
                {"prohibition": name, "rule_id": rule, "covered": rule in ALL_RULE_IDS}
                for name, rule in REQUIRED_PROHIBITIONS
            ],
            "uncovered_prohibitions": missing,
            "note": (
                "Zero violazioni non dice che le regole siano inerti: la suite le prova "
                "una per una su dati deliberatamente scorretti. Qui misurano lo stato "
                "reale delle proposte."
            ),
        },
    )

    print(f"unita' controllate: {len(units)} | decisioni: {len(decisions)} | mapping: {len(mappings)}")
    print(f"violazioni: {len(violations)}")
    for item in violations:
        print(f"  [{item.rule_id}] {item.subject}: {item.message}")
    if missing:
        print(f"divieti scoperti: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
