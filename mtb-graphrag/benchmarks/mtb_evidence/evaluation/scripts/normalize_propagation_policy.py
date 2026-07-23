"""Applica la politica di propagazione a tutte le unita' esistenti.

Calcola il livello di ogni unita' del repository, registra il prima e il dopo, e
normalizza fisicamente le quattro unita' di PMID 22277784 — le uniche che
dichiaravano `is_propagatable = true` dopo una revisione umana, e quindi le
uniche in cui la divergenza produceva un effetto.

Le altre 99 unita' che dichiaravano `true` non vengono riscritte: il loro flag e'
un valore serializzato che il codice non onora piu'. Ricalcolarlo invaliderebbe
l'hash del manifest del corpus, che e' fuori dal perimetro di questa fase. La
differenza fra «il codice sbaglia» e «un dato e' vecchio» e' registrata come tale
invece di essere nascosta in un conteggio unico.

Nessuna decisione di revisione viene toccata: cambia solo che cosa e' lecito
farne.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_manifest import content_hash  # noqa: E402
from backend.pipeline.evidence.profile_unit import (  # noqa: E402
    PROFILE_UNIT_VERSION,
    UNIT_DIMENSIONS,
)
from backend.pipeline.evidence.propagation_policy import (  # noqa: E402
    ELIGIBILITY_LEVELS,
    FINAL,
    NONE,
    POLICY_VERSION,
    PROTOTYPE_ONLY,
    eligibility_for,
    propagated_dimensions,
    validate_units,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/propagation_policy")
DEFAULT_V3 = Path("benchmarks/mtb_evidence/v3")

# Le quattro unita' che la divergenza rendeva propagabili dopo una prima
# revisione non indipendente. Sono l'unico caso in cui il flag serializzato
# produceva un effetto: le altre unita' con `true` non hanno mai visto una
# revisione, quindi nessuno le usava come qualificatori confermati.
NORMALIZED_UNITS = (
    "PU-PMID-22277784-clinical-crizotinib-resistant",
    "PU-PMID-22277784-baf3-crizotinib-panel",
    "PU-PMID-22277784-baf3-next-generation-alk-inhibitors",
    "PU-PMID-22277784-baf3-17aag",
)
NORMALIZED_FILE = Path("first_review/reviewed_profile_units.jsonl")

VERIFIED_UNIT = "PU-PMID-31358542-clinical-cohort"
VERIFIED_FILE = Path("author_approval/approved_profile_units.jsonl")


class NormalizationError(RuntimeError):
    """La normalizzazione non ha prodotto lo stato atteso."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--v3-dir", type=Path, default=DEFAULT_V3)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def collect_units(v3_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(v3_dir.rglob("*profile_units*.jsonl")):
        relative = path.relative_to(v3_dir).as_posix()
        for row in read_jsonl(path):
            rows.append((relative, row))
    return rows


# La regola vecchia, in forma esplicita. Il «prima» va ricostruito da questa e
# non dal flag serializzato: dopo la prima esecuzione il flag e' gia' cambiato, e
# leggerlo farebbe dire allo script cose diverse a ogni riesecuzione.
def _old_rule_propagatable(unit: Mapping[str, Any]) -> bool:
    return str(unit.get("cohort_state") or "") in ("single_cohort", "resolved_cohort")


def before_after(source: str, unit: dict[str, Any]) -> dict[str, Any]:
    decision = eligibility_for(unit)
    unit_id = str(unit.get("profile_unit_id") or unit.get("proposed_profile_unit_id") or "")
    declared = _old_rule_propagatable(unit)
    qualifiers = propagated_dimensions(unit, UNIT_DIMENSIONS)
    return {
        "profile_unit_id": unit_id,
        "source_file": source,
        "canonical_source_id": unit.get("canonical_source_id", ""),
        "review_status": unit.get("review_status", ""),
        "extraction_status": unit.get("extraction_status", ""),
        "cohort_state": unit.get("cohort_state", ""),
        "independent_review": bool(unit.get("independent_review")),
        "before": {
            "is_propagatable": declared,
            "propagation_eligibility": (
                "final_by_cohort_resolution_only" if declared else "none_by_cohort_state"
            ),
        },
        "after": {
            "is_propagatable": decision.is_propagatable,
            "propagation_eligibility": decision.eligibility,
            "may_display_qualifiers": decision.may_display_qualifiers,
            "may_hard_filter": decision.may_hard_filter,
            "is_evaluable": decision.is_evaluable,
            "requires_second_independent_review": decision.requires_second_independent_review,
        },
        "changed": declared != decision.is_propagatable,
        "physically_normalized": unit_id in NORMALIZED_UNITS,
        "serialized_flag": bool(unit.get("is_propagatable")),
        "stale_serialized_flag": bool(unit.get("is_propagatable"))
        and not decision.is_propagatable,
        "qualifier_count": len(qualifiers),
        "reason": decision.reason,
        "policy_version": POLICY_VERSION,
    }


def normalize_file(path: Path, unit_ids: tuple[str, ...], created_at: str) -> list[str]:
    """Applica l'eligibility alle unita' indicate, senza toccare altro."""
    rows = list(read_jsonl(path))
    touched: list[str] = []
    updated: list[dict[str, Any]] = []
    for row in rows:
        unit_id = str(row.get("profile_unit_id") or "")
        if unit_id not in unit_ids:
            updated.append(row)
            continue
        decision = eligibility_for(row)
        if decision.eligibility != PROTOTYPE_ONLY:
            raise NormalizationError(
                f"{unit_id}: atteso prototype_only, la politica assegna {decision.eligibility}"
            )
        updated.append(
            {
                **row,
                "independent_review": False,
                "clinical_reviewed": False,
                "propagation_eligibility": decision.eligibility,
                "may_display_qualifiers": decision.may_display_qualifiers,
                "may_hard_filter": decision.may_hard_filter,
                "is_propagatable": False,
                "is_evaluable": False,
                "requires_second_independent_review": True,
                "propagation_policy_version": POLICY_VERSION,
                "propagation_normalized_at": created_at,
                "propagation_note": (
                    "prima revisione conservata integralmente: cambia soltanto che cosa "
                    "e' lecito farne. I qualificatori restano visibili e ispezionabili, "
                    "non possono escludere evidenza ne' entrare in una metrica finale."
                ),
            }
        )
        touched.append(unit_id)
    write_jsonl(path, updated)
    return touched


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()
    output = args.output

    units_before = collect_units(args.v3_dir)
    # Lo stato precedente e' ricostruito dalla regola vecchia, non dal flag
    # serializzato: cosi' il conteggio e' lo stesso a ogni esecuzione.
    violations_before = validate_units(
        [
            {**unit, "is_propagatable": _old_rule_propagatable(unit)}
            for _, unit in units_before
        ]
    )

    touched = normalize_file(args.v3_dir / NORMALIZED_FILE, NORMALIZED_UNITS, created_at)
    if sorted(touched) != sorted(NORMALIZED_UNITS):
        raise NormalizationError(f"normalizzate {touched} invece di {list(NORMALIZED_UNITS)}")

    units_after = collect_units(args.v3_dir)
    rows = [before_after(source, unit) for source, unit in units_after]
    rows.sort(key=lambda row: (row["source_file"], row["profile_unit_id"]))
    write_jsonl(output / "unit_eligibility_before_after.jsonl", rows)

    verified = next(row for row in rows if row["profile_unit_id"] == VERIFIED_UNIT)
    if verified["after"]["propagation_eligibility"] != PROTOTYPE_ONLY:
        raise NormalizationError(f"{VERIFIED_UNIT}: eligibility inattesa")

    # Due grandezze diverse, contate separatamente perche' significano cose
    # diverse. `violations_after` misura il comportamento **vivo**: cosa succede
    # quando il codice ricalcola l'eligibility, che e' cio' che accade a ogni
    # rigenerazione. `stale` misura quanti flag serializzati in artefatti di fasi
    # precedenti riportano ancora il valore vecchio. Sommarli farebbe sembrare la
    # politica violata dove invece e' solo un dato non ancora riscritto.
    units_after_live = [
        {**unit, "is_propagatable": eligibility_for(unit).is_propagatable}
        for _, unit in units_after
    ]
    violations_after = validate_units(units_after_live)
    stale = [row for row in rows if row["stale_serialized_flag"]]

    write_json(
        output / "propagation_policy.json",
        {
            "policy_version": POLICY_VERSION,
            "created_at": created_at,
            "levels": list(ELIGIBILITY_LEVELS),
            "applies_to": [
                "SourceClinicalProfile",
                "SourceClinicalProfileUnit",
                "EvidenceQualificationLink",
                "prima revisione",
                "seconda revisione",
                "adjudication",
            ],
            "does_not_apply_to": [
                "campi nativi degli EvidenceStatement, che vengono dal grafo congelato"
            ],
            "rules": [
                {"review_status": "machine_extracted / awaiting_source_review", "eligibility": NONE},
                {"review_status": "awaiting_first_review", "eligibility": NONE},
                {"review_status": "source_checked_review_proposal", "eligibility": NONE},
                {
                    "review_status": "first_review_complete (non indipendente)",
                    "eligibility": PROTOTYPE_ONLY,
                },
                {
                    "review_status": "second_review_complete (accordo esplicito)",
                    "eligibility": FINAL,
                },
                {"review_status": "disagreement non adjudicato", "eligibility": PROTOTYPE_ONLY},
                {"review_status": "adjudicated", "eligibility": FINAL},
                {"review_status": "frozen", "eligibility": FINAL},
            ],
            "prototype_only_allows": [
                "visualizzazione nella QualifiedEvidenceView",
                "report di audit",
                "ispezione nel prototipo",
                "esperimenti esplorativi marcati provisional",
            ],
            "prototype_only_forbids": [
                "hard filtering",
                "esclusione definitiva di evidenze",
                "metriche finali",
                "gold",
                "confronto finale V2 contro V3-A",
                "dichiarazioni di applicabilita' clinica",
                "dossier frozen",
            ],
            "cohort_resolution_is_necessary_not_sufficient": True,
        },
    )

    by_level = Counter(row["after"]["propagation_eligibility"] for row in rows)
    by_status = Counter(str(row["review_status"]) for row in rows)
    metrics = {
        "created_at": created_at,
        "policy_version": POLICY_VERSION,
        "metric_kind": "descriptive_policy_metrics",
        "units_total": len(rows),
        "units_by_review_status": dict(sorted(by_status.items())),
        "units_by_propagation_eligibility": {
            level: by_level.get(level, 0) for level in ELIGIBILITY_LEVELS
        },
        "units_normalized": len(touched),
        "first_review_units_prototype_only": sum(
            1
            for row in rows
            if row["review_status"] in ("first_review_complete", "human_reviewed")
            and row["after"]["propagation_eligibility"] == PROTOTYPE_ONLY
        ),
        "final_propagatable_units": by_level.get(FINAL, 0),
        "policy_violations_before": len(violations_before),
        "policy_violations_after": len(violations_after),
        "stale_serialized_flags": len(stale),
        "stale_serialized_flag_units": [row["profile_unit_id"] for row in stale][:12],
        "hard_filter_eligible_qualifiers": sum(
            row["qualifier_count"]
            for row in rows
            if row["after"]["may_hard_filter"]
        ),
        "prototype_visible_qualifiers": sum(
            row["qualifier_count"]
            for row in rows
            if row["after"]["may_display_qualifiers"] and not row["after"]["may_hard_filter"]
        ),
        "not_recalculated": {
            "linking_precision": "not_recalculated",
            "linking_recall": "not_recalculated",
            "clinical_applicability_accuracy": "not_recalculated",
            "retrieval_quality": "not_recalculated",
        },
        "note": (
            "La riduzione delle unita' propagabili non e' una perdita di dati: i "
            "valori restano tutti presenti e tutti visibili. Cambia che cosa e' "
            "lecito farne."
        ),
    }
    write_json(
        output / "policy_validation_results.json",
        {
            "created_at": created_at,
            "policy_version": POLICY_VERSION,
            "violations_before": [item.as_dict() for item in violations_before],
            "violations_after": [item.as_dict() for item in violations_after],
            "violations_after_scope": (
                "comportamento vivo: eligibility ricalcolata dal codice, come a ogni "
                "rigenerazione"
            ),
            "violations_before_count": len(violations_before),
            "violations_after_count": len(violations_after),
            "violations_before_by_rule": dict(
                sorted(Counter(item.rule_id for item in violations_before).items())
            ),
            "violations_after_by_rule": dict(
                sorted(Counter(item.rule_id for item in violations_after).items())
            ),
            "stale_serialized_flags": len(stale),
            "stale_flag_note": (
                "Flag serializzati in artefatti di fasi precedenti che il codice non "
                "onora piu'. Non sono violazioni della politica: caricando l'unita' il "
                "valore viene ricalcolato correttamente. Spariranno alla prossima "
                "rigenerazione del corpus."
            ),
            "metrics": metrics,
        },
    )

    readiness = {
        "created_at": created_at,
        "policy_version": POLICY_VERSION,
        "before": {
            "single_global_policy": False,
            "review_and_propagation_distinct": False,
            "prototype_and_final_distinct": False,
            "units_declared_propagatable": len(
                [row for row in rows if row["before"]["is_propagatable"]]
            ),
            "final_propagatable_units": len(
                [row for row in rows if row["before"]["is_propagatable"]]
            ),
        },
        "after": {
            "single_global_policy": True,
            "review_and_propagation_distinct": True,
            "prototype_and_final_distinct": True,
            "units_declared_propagatable": 0,
            "final_propagatable_units": by_level.get(FINAL, 0),
            "prototype_only_units": by_level.get(PROTOTYPE_ONLY, 0),
            "none_units": by_level.get(NONE, 0),
        },
        "gold_evaluable": False,
        "ready_for_final_evaluation": False,
        "detector_promotion_ready": False,
        "hard_filtering_available": by_level.get(FINAL, 0) > 0,
        "note": (
            "Nessun qualificatore source-derived puo' oggi filtrare, perche' nessuno "
            "ha una seconda conferma indipendente. E' lo stato reale della revisione, "
            "non una regressione del sistema."
        ),
        "next_step": "approvazione di SOURCE_REVIEW_PMID-22235099.md",
    }
    write_json(output / "readiness_before_after.json", readiness)

    write_json(
        output / "propagation_policy_manifest.json",
        {
            "policy_version": POLICY_VERSION,
            "generated_at": created_at,
            "branch": "feat/v3-propagation-policy-normalization",
            "schema_versions": {"source_clinical_profile_unit": PROFILE_UNIT_VERSION},
            "units_scanned": len(rows),
            "units_normalized": sorted(touched),
            "normalized_file": NORMALIZED_FILE.as_posix(),
            "verified_unit": VERIFIED_UNIT,
            "output_hashes": {
                "unit_eligibility_before_after": content_hash(rows),
                "policy_metrics": content_hash(metrics),
                "readiness_before_after": content_hash(readiness),
            },
            "status": "complete",
        },
    )

    print(f"unita' esaminate: {len(rows)}")
    print(f"  eligibility: {dict(sorted(by_level.items()))}")
    print(f"  normalizzate fisicamente: {len(touched)}")
    print(f"violazioni prima: {len(violations_before)} · dopo: {len(violations_after)}")
    print(f"flag serializzati obsoleti: {len(stale)}")
    print(f"qualificatori hard-filterable: {metrics['hard_filter_eligible_qualifiers']}")
    print(f"qualificatori prototype-visible: {metrics['prototype_visible_qualifiers']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
