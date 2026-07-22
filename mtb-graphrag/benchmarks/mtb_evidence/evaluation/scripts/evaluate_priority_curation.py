"""Gold provvisorio, riesecuzione del linker e copertura prima/dopo."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_manifest import content_hash  # noqa: E402
from backend.pipeline.evidence.profile_unit import (  # noqa: E402
    HUMAN_REVIEWED,
    SOURCE_CHECKED,
    UNIT_DIMENSIONS,
    UNKNOWN,
)
from backend.pipeline.evidence.qualification import LINK_VERSION, build_link  # noqa: E402
from backend.pipeline.evidence.qualification_gold import gold_link_id  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_CORPUS = Path("benchmarks/mtb_evidence/v3/qualification_corpus")
DEFAULT_QUALIFICATION = Path("benchmarks/mtb_evidence/v3/qualification")
DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/priority_curation")

# Sentinella di fase: nessun verdetto esiste su questo collegamento.
PROVISIONAL_UNREVIEWED = "provisional_unreviewed"
NOT_EVALUATED = "not_evaluated"

# Stati di coorte in cui i qualificatori non possono essere propagati.
NON_PROPAGATING_COHORT_STATES = frozenset(
    {"cohort_partially_resolved", "cohort_not_separable", "insufficient_source_information",
     "source_unavailable", "requires_clinical_review"}
)


@dataclass
class UnitAsProfile:
    """Adattatore che espone una profile unit come profilo per il linker.

    Serve a **riusare il linker reale** invece di riscriverne la logica di
    matching: una seconda implementazione divergerebbe, e le prediction
    valutate non sarebbero piu' quelle della pipeline.
    """

    source_id: str
    pmid: str = ""
    nct_ids: tuple[str, ...] = ()
    disease: str = ""
    interventions: tuple[str, ...] = ()
    setting: str = ""
    stage: str = ""
    therapy_line: str = ""
    population: str = ""
    prior_therapies: tuple[str, ...] = ()
    biomarker_requirements: tuple[str, ...] = ()
    regimen: str = ""
    inclusion_criteria_summary: str = ""
    exclusion_criteria_summary: str = ""

    @classmethod
    def from_unit(cls, unit: Mapping[str, Any]) -> "UnitAsProfile":
        def scalar(name: str) -> str:
            value = str(unit.get(name) or "")
            return "" if value == UNKNOWN else value

        def listed(name: str) -> tuple[str, ...]:
            return tuple(item for item in (unit.get(name) or ()) if item and item != UNKNOWN)

        pmids = unit.get("pmids") or ()
        return cls(
            source_id=str(unit.get("profile_unit_id") or ""),
            pmid=str(pmids[0]) if pmids else "",
            nct_ids=tuple(unit.get("ncts") or ()),
            disease=scalar("disease"),
            interventions=listed("intervention"),
            setting=scalar("setting"),
            stage=scalar("stage"),
            therapy_line=scalar("therapy_line"),
            population=scalar("population"),
            prior_therapies=listed("prior_therapies"),
            biomarker_requirements=listed("biomarker_requirements"),
            regimen=scalar("regimen"),
            inclusion_criteria_summary=scalar("inclusion_criteria"),
            exclusion_criteria_summary=scalar("exclusion_criteria"),
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--qualification-dir", type=Path, default=DEFAULT_QUALIFICATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _known(unit: Mapping[str, Any], dimension: str) -> bool:
    value = unit.get(dimension)
    if isinstance(value, (list, tuple)):
        return bool(value)
    return bool(value) and value != UNKNOWN


def _coverage(units: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Copertura per dimensione, separata per origine del valore.

    Le cinque origini restano distinte anche quando alcune valgono zero: una
    tabella che le collassasse presenterebbe un valore `source_checked` come se
    fosse stato letto da una persona.
    """
    buckets = {
        "frozen_kg": {dimension: 0 for dimension in UNIT_DIMENSIONS},
        "human_reviewed": {dimension: 0 for dimension in UNIT_DIMENSIONS},
        "source_checked": {dimension: 0 for dimension in UNIT_DIMENSIONS},
        "machine_extracted": {dimension: 0 for dimension in UNIT_DIMENSIONS},
    }
    for unit in units:
        if unit.get("review_status") == HUMAN_REVIEWED:
            key = "human_reviewed"
        elif unit.get("extraction_status") == SOURCE_CHECKED:
            key = "source_checked"
        else:
            key = "machine_extracted"
        for dimension in UNIT_DIMENSIONS:
            if _known(unit, dimension):
                buckets[key][dimension] += 1

    total = {
        dimension: sum(bucket[dimension] for bucket in buckets.values())
        for dimension in UNIT_DIMENSIONS
    }
    buckets["total_known"] = total
    buckets["still_unknown"] = {
        dimension: len(units) - total[dimension] for dimension in UNIT_DIMENSIONS
    }
    return buckets


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    statements = list(read_jsonl(args.qualification_dir / "evidence_statements.jsonl"))
    statements_by_id = {str(row["evidence_statement_id"]): row for row in statements}

    before_units = list(read_jsonl(args.corpus_dir / "source_profile_units.jsonl"))
    before_by_id = {str(row["profile_unit_id"]): row for row in before_units}

    curated = list(read_jsonl(output / "resolved_profile_units.jsonl")) + list(
        read_jsonl(output / "unresolved_profile_units.jsonl")
    )
    curated_by_id = {str(row["profile_unit_id"]): row for row in curated}

    # Il corpus precedente non viene sovrascritto: si costruisce una vista
    # aggiornata in cui le unita' curate rimpiazzano le proprie omonime.
    after_units = [curated_by_id.get(str(row["profile_unit_id"]), row) for row in before_units]

    resolutions = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(output / "cohort_resolution_decisions.jsonl")
    }
    candidates = list(read_jsonl(output / "statement_profile_candidates.jsonl"))

    # --- linker reale sulle unita' curate ------------------------------------
    predictions: list[dict[str, Any]] = []
    for unit in curated:
        profile = UnitAsProfile.from_unit(unit)
        cohort_state = str(
            resolutions.get(str(unit["profile_unit_id"]), {}).get("resolution_state") or ""
        )
        blocked = cohort_state in NON_PROPAGATING_COHORT_STATES
        for statement_id in unit.get("statement_ids") or ():
            statement = statements_by_id.get(statement_id)
            if statement is None:
                continue
            link = build_link(statement, profile, now=created_at)
            added = [item for item in link.as_dict()["added_dimensions"]]
            suppressed: list[str] = []
            if blocked and added:
                # La coorte non e' risolta: le dimensioni non vengono propagate
                # anche quando il linker le dichiarerebbe applicabili. Il link
                # resta, la propagazione no.
                suppressed = [item["dimension"] for item in added]
                added = []
            predictions.append(
                {
                    "statement_id": statement_id,
                    "profile_unit_id": str(unit["profile_unit_id"]),
                    "match_method": link.match_method,
                    "match_status": link.match_status,
                    "matched_source_ids": list(link.matched_source_ids),
                    "cohort_resolution_state": cohort_state,
                    "propagation_blocked_by_cohort": blocked,
                    "added_dimensions": added,
                    "suppressed_dimensions": suppressed,
                    "conflicts": [dict(item) for item in link.conflicts],
                    "ambiguity_reasons": list(link.ambiguity_reasons),
                    "linker_version": LINK_VERSION,
                    "is_gold": False,
                    "evaluation_status": NOT_EVALUATED,
                    "note": "prediction del linker: non e' un verdetto e non va copiata nel gold",
                }
            )
    predictions.sort(key=lambda item: (item["statement_id"], item["profile_unit_id"]))
    write_jsonl(output / "linking_predictions.jsonl", predictions)

    # --- gold provvisorio -----------------------------------------------------
    provisional: list[dict[str, Any]] = []
    for candidate in candidates:
        unit = curated_by_id.get(str(candidate["profile_unit_id"]), {})
        provisional.append(
            {
                "gold_link_id": gold_link_id(
                    str(candidate["statement_id"]), str(candidate["profile_unit_id"])
                ),
                "statement_id": candidate["statement_id"],
                "profile_unit_id": candidate["profile_unit_id"],
                "final_status": PROVISIONAL_UNREVIEWED,
                "first_annotator": None,
                "first_annotation": None,
                "second_annotator": None,
                "second_annotation": None,
                "agreement": None,
                "adjudicator": None,
                "adjudication": None,
                "is_evaluable": False,
                "profile_review_status": unit.get("review_status", ""),
                "automatic_candidate_state": candidate.get("candidate_state", ""),
                "automatic_support_type": candidate.get("support_type", ""),
                "created_at": created_at,
                "frozen_at": "",
                "note": (
                    "Nessuna revisione umana esiste su questo collegamento. La "
                    "classificazione automatica e' conservata come informazione, non "
                    "come verdetto: copiarla nel gold darebbe al linker una precision "
                    "misurata contro se stesso."
                ),
            }
        )
    provisional.sort(key=lambda item: (item["statement_id"], item["profile_unit_id"]))
    write_jsonl(output / "provisional_gold.jsonl", provisional)

    # --- copertura prima/dopo -------------------------------------------------
    before = _coverage(before_units)
    after = _coverage(after_units)
    delta = {
        dimension: after["total_known"][dimension] - before["total_known"][dimension]
        for dimension in UNIT_DIMENSIONS
    }
    write_json(
        output / "coverage_before_after.json",
        {
            "created_at": created_at,
            "unit_count": len(after_units),
            "before": before,
            "after": after,
            "delta": delta,
            "note": (
                "source_checked e human_reviewed restano colonne distinte. Un valore "
                "estratto da uno span dell'abstract non e' un valore letto da una "
                "persona, e presentarli insieme farebbe sembrare revisionato cio' che "
                "non lo e'."
            ),
        },
    )

    # --- metriche -------------------------------------------------------------
    cohort_counts: dict[str, int] = {}
    for row in resolutions.values():
        state = str(row["resolution_state"])
        cohort_counts[state] = cohort_counts.get(state, 0) + 1
    candidate_counts: dict[str, int] = {}
    for row in candidates:
        state = str(row["candidate_state"])
        candidate_counts[state] = candidate_counts.get(state, 0) + 1
    support_counts: dict[str, int] = {}
    for row in candidates:
        state = str(row["support_type"])
        support_counts[state] = support_counts.get(state, 0) + 1

    access = list(read_jsonl(output / "source_access_manifest.jsonl"))
    accessible = sum(1 for row in access if row["abstract_available"])
    provenance_complete = all(
        all(
            any(item["field_name"] == dimension for item in unit.get("provenance") or [])
            for dimension in UNIT_DIMENSIONS
            if _known(unit, dimension)
        )
        for unit in curated
    )

    statements_with_qualifier = {
        statement_id
        for unit in after_units
        if any(_known(unit, dimension) for dimension in UNIT_DIMENSIONS)
        and unit.get("cohort_state") != "unresolved_cohort"
        for statement_id in unit.get("statement_ids") or ()
    }

    metrics = {
        "created_at": created_at,
        "priority_units": len(curated),
        "sources_accessible": accessible,
        "sources_not_accessible": len(access) - accessible,
        "cohort_resolution": cohort_counts,
        "candidate_states": candidate_counts,
        "support_types": support_counts,
        "new_units_created": 0,
        "units_source_checked": sum(
            1 for unit in curated if unit.get("extraction_status") == SOURCE_CHECKED
        ),
        "units_human_reviewed": sum(
            1 for unit in curated if unit.get("review_status") == HUMAN_REVIEWED
        ),
        "units_awaiting_review": sum(
            1 for unit in curated if unit.get("requires_human_review")
        ),
        "qualifier_provenance_completeness": 1.0 if provenance_complete else 0.0,
        "ambiguous_qualification_rate": round(
            sum(1 for unit in after_units if unit.get("cohort_state") == "unresolved_cohort")
            / (len(after_units) or 1),
            4,
        ),
        "conflicting_qualification_rate": round(
            candidate_counts.get("candidate_conflicting", 0) / (len(candidates) or 1), 4
        ),
        "not_separable_rate": round(
            cohort_counts.get("cohort_not_separable", 0) / (len(resolutions) or 1), 4
        ),
        "source_unavailable_rate": round(
            cohort_counts.get("source_unavailable", 0) / (len(resolutions) or 1), 4
        ),
        "statements_with_propagatable_qualifier": len(statements_with_qualifier),
        "statement_total": len(statements),
        "linking_predictions": len(predictions),
        "predictions_with_suppressed_dimensions": sum(
            1 for row in predictions if row["suppressed_dimensions"]
        ),
        "provisional_gold_records": len(provisional),
        "evaluable_gold_records": 0,
        "linking_precision": NOT_EVALUATED,
        "linking_recall": NOT_EVALUATED,
        "inter_annotator_agreement": NOT_EVALUATED,
        "agreement_note": (
            "Nessuna seconda revisione esiste. Un accordo calcolato adesso "
            "descriverebbe una copia, non due giudizi."
        ),
        "hashes": {
            "curated_units": content_hash(curated),
            "predictions": content_hash(predictions),
            "provisional_gold": content_hash(provisional),
        },
    }
    write_json(output / "curation_metrics.json", metrics)

    print(f"prediction del linker: {len(predictions)}")
    print(f"  con dimensioni soppresse per coorte non risolta: "
          f"{metrics['predictions_with_suppressed_dimensions']}")
    print(f"gold provvisori: {len(provisional)} | valutabili: 0")
    moved = {key: value for key, value in delta.items() if value}
    print(f"delta copertura: {moved or 'nessuna variazione'}")
    print(f"provenance completa: {provenance_complete}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
