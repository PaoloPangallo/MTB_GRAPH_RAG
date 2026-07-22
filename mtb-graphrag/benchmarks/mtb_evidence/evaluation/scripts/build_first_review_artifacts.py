"""Costruisce gli artefatti della prima revisione del pacchetto BA-22b14dbcbc62e29b.

Le regole di propagazione dichiarate dalla revisione vengono **verificate**, non
solo documentate: se la popolazione clinica finisse su una unita' preclinica, o
un qualificatore preclinico su quella clinica, lo script fallisce. Una regola che
nessuno controlla e' un commento.
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

from backend.pipeline.evidence.corpus_manifest import content_hash  # noqa: E402
from backend.pipeline.evidence.profile_unit import (  # noqa: E402
    COHORT_RESOLVED,
    COHORT_SUPERSEDED,
    FIRST_REVIEW_COMPLETE,
    NOT_APPLICABLE,
    PRECLINICAL_UNIT_TYPES,
    SOURCE_CHECKED,
    UNIT_DIMENSIONS,
    UNKNOWN,
    FieldProvenance,
    SourceClinicalProfileUnit,
    validate_units,
)
from benchmarks.mtb_evidence.evaluation.first_review_batch1 import (  # noqa: E402
    CANONICAL_SOURCE_ID,
    INTERVENTION_MAPPINGS,
    ORIGINAL_UNIT_ID,
    PACKET_ID,
    PMID,
    PROPAGATION_RULES,
    REVIEW_METADATA,
    REVIEW_VERSION,
    SOURCE_TITLE,
    SPLIT_DECISION,
    STATEMENT_DECISIONS,
    UNITS,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")
DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/first_review")

PROVISIONAL_FIRST_REVIEW = "provisional_first_review"

LIST_DIMENSIONS = ("biomarker_requirements", "intervention", "prior_therapies")


class PropagationViolation(RuntimeError):
    """Una regola di propagazione dichiarata dalla revisione e' stata violata."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _materialise(spec: Mapping[str, Any], dimension: str) -> Any:
    """Traduce `(value, decision)` nel valore della dataclass.

    `None` con decisione `not_applicable` diventa il sentinella omonimo; `None`
    con qualunque altra decisione diventa `unknown`. La distinzione sopravvive
    fino all'artefatto, perche' e' la differenza fra «nessuno lo ha ancora
    cercato» e «la domanda non si pone».
    """
    field = spec["fields"].get(dimension, {})
    value = field.get("value")
    decision = str(field.get("decision") or "unknown")
    if value is None:
        return NOT_APPLICABLE if decision == "not_applicable" else UNKNOWN
    if dimension in LIST_DIMENSIONS:
        return tuple(value) if isinstance(value, (list, tuple)) else (value,)
    return value


def build_unit(
    spec: Mapping[str, Any],
    *,
    verification: Mapping[str, Mapping[str, Any]],
    created_at: str,
    document_hash: str,
) -> SourceClinicalProfileUnit:
    values: dict[str, Any] = {}
    decisions: dict[str, str] = {}
    provenance: list[FieldProvenance] = []

    locators = [verification[key] for key in spec["locators"] if key in verification]
    verified = [item for item in locators if item.get("status") == "verified"]
    locator_text = "; ".join(
        f"{item['locator_id']}={item['value']} ({item['match_type']})" for item in verified
    )
    unverified = [item["locator_id"] for item in locators if item.get("status") != "verified"]

    for dimension in UNIT_DIMENSIONS:
        field = spec["fields"].get(dimension, {})
        decision = str(field.get("decision") or "unknown")
        decisions[dimension] = decision
        value = _materialise(spec, dimension)
        values[dimension] = value

        is_known = value not in (UNKNOWN, NOT_APPLICABLE, "", ()) if not isinstance(
            value, (tuple, list)
        ) else bool(value)
        if is_known:
            note = field.get("note") or ""
            provenance.append(
                FieldProvenance(
                    field_name=dimension,
                    value_origin="primary_source_text",
                    source_locator=f"PMC full text | {locator_text}" if locator_text else "PMC full text",
                    access_date=created_at[:10],
                    asserted_by=(
                        f"{REVIEW_METADATA['reviewer_id']} "
                        f"({REVIEW_METADATA['review_method']})"
                    ),
                    span_hash=document_hash,
                    note=(
                        f"decisione di revisione: {decision}"
                        + (f"; {note}" if note else "")
                        + (
                            f"; locator non verificati: {', '.join(unverified)}"
                            if unverified
                            else ""
                        )
                    ),
                )
            )

    reasons = [
        "prima revisione non indipendente e non clinica, assistita da LLM e approvata "
        "dall'autore della tesi: richiede una seconda revisione indipendente"
    ]
    if unverified:
        reasons.append(f"locator non verificati: {', '.join(unverified)}")

    return SourceClinicalProfileUnit(
        profile_unit_id=str(spec["profile_unit_id"]),
        canonical_source_id=CANONICAL_SOURCE_ID,
        pmids=(PMID,),
        title=SOURCE_TITLE,
        cohort_id=str(spec["cohort_id"]),
        cohort_label=str(spec["cohort_label"]),
        cohort_state=COHORT_RESOLVED,
        cohort_note=str(SPLIT_DECISION["rationale"]),
        unit_type=str(spec["unit_type"]),
        supersedes=ORIGINAL_UNIT_ID,
        field_decisions=decisions,
        source_spans=tuple(item["locator_id"] for item in verified),
        extraction_status=SOURCE_CHECKED,
        review_status=FIRST_REVIEW_COMPLETE,
        reviewer=str(REVIEW_METADATA["reviewer_id"]),
        requires_human_review=True,
        human_review_reasons=tuple(reasons),
        provenance=tuple(provenance),
        created_at=created_at,
        **values,
    )


def check_propagation(
    units: Sequence[SourceClinicalProfileUnit], decisions: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Verifica le regole dichiarate dalla revisione. Ritorna le violazioni."""
    problems: list[str] = []
    by_id = {unit.profile_unit_id: unit for unit in units}

    clinical = [unit for unit in units if unit.is_clinical]
    preclinical = [unit for unit in units if unit.is_preclinical]

    forbidden = tuple(
        item.casefold() for item in PROPAGATION_RULES["clinical_population_must_not_reach"]
    )
    for unit in clinical:
        haystack = " ".join(
            str(getattr(unit, dimension) or "") for dimension in UNIT_DIMENSIONS
        ).casefold()
        for term in forbidden:
            if term in haystack:
                problems.append(
                    f"{unit.profile_unit_id}: la coorte clinica cita «{term}», che "
                    "appartiene agli esperimenti in vitro"
                )

    # Nessuna popolazione di pazienti su una unita' preclinica.
    for unit in preclinical:
        population = str(unit.population or "").casefold()
        if "patient" in population:
            problems.append(
                f"{unit.profile_unit_id}: una unita' preclinica dichiara una "
                f"popolazione di pazienti: «{unit.population}»"
            )
        for dimension in ("therapy_line", "prior_therapies", "resection_status", "stage"):
            value = getattr(unit, dimension)
            has_value = bool(value) if isinstance(value, tuple) else value not in (
                UNKNOWN,
                NOT_APPLICABLE,
                "",
            )
            if has_value:
                problems.append(
                    f"{unit.profile_unit_id}: `{dimension}` valorizzato su una unita' "
                    "preclinica, dove la domanda non si pone"
                )

    # Nessun setting preclinico sulla coorte clinica.
    for unit in clinical:
        if "preclinical" in str(unit.setting or "").casefold():
            problems.append(
                f"{unit.profile_unit_id}: setting preclinico su una coorte di pazienti"
            )

    # Uno statement legato solo a unita' precliniche non puo' dichiarare una
    # risposta clinica osservata.
    for decision in decisions:
        linked = [by_id[item] for item in decision["profile_unit_ids"] if item in by_id]
        if linked and all(unit.is_preclinical for unit in linked):
            if decision.get("clinical_response_observed") is not False:
                problems.append(
                    f"{decision['statement_id']}: collegato solo a unita' precliniche ma "
                    "non dichiara clinical_response_observed = false"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    verification_rows = list(read_jsonl(output / f"locator_verification_{PACKET_ID}.jsonl"))
    verification = {str(row["locator_id"]): row for row in verification_rows}
    document_hash = next(
        (str(row.get("document_sha256") or "") for row in verification_rows), ""
    )

    # --- verifica della fonte -------------------------------------------------
    access = [
        row
        for row in read_jsonl(args.curation_dir / "source_access_manifest.jsonl")
        if PMID in (row.get("pmids") or [])
    ]
    if not access:
        print(f"nessun record di accesso per PMID {PMID}")
        return 1
    source_check = {
        "pmid": PMID,
        "packet_id": PACKET_ID,
        "pmid_matches_packet": True,
        "abstract_sha256": access[0].get("abstract_sha256", ""),
        "full_text_document_sha256": document_hash,
        "pmc_id": next((str(row.get("pmc_id") or "") for row in verification_rows), ""),
        "locators_total": len(verification_rows),
        "locators_verified": sum(
            1 for row in verification_rows if row["status"] == "verified"
        ),
        "locators_not_verified": [
            row["locator_id"] for row in verification_rows if row["status"] != "verified"
        ],
        "match_types": sorted({str(row.get("match_type")) for row in verification_rows}),
        "note": (
            "il full text e' stato interrogato in memoria per verificare i locator e non "
            "e' conservato nel repository"
        ),
    }
    write_json(output / f"source_verification_{PACKET_ID}.json", source_check)

    # --- unita' derivate ------------------------------------------------------
    units = [
        build_unit(spec, verification=verification, created_at=created_at, document_hash=document_hash)
        for spec in UNITS
    ]
    violations = check_propagation(units, STATEMENT_DECISIONS)
    if violations:
        for item in violations:
            print(f"VIOLAZIONE: {item}")
        raise PropagationViolation(
            f"{len(violations)} regole di propagazione violate: gli artefatti non "
            "vengono scritti"
        )

    problems = validate_units(units)
    if problems:
        for item in problems:
            print(f"problema: {item}")
        return 1

    # --- unita' originale, conservata e neutralizzata -------------------------
    original = next(
        (
            row
            for row in read_jsonl(args.curation_dir / "unresolved_profile_units.jsonl")
            if row["profile_unit_id"] == ORIGINAL_UNIT_ID
        ),
        None,
    ) or next(
        (
            row
            for row in read_jsonl(args.curation_dir / "resolved_profile_units.jsonl")
            if row["profile_unit_id"] == ORIGINAL_UNIT_ID
        ),
        None,
    )
    if original is None:
        print(f"unita' originale non trovata: {ORIGINAL_UNIT_ID}")
        return 1

    superseded = dict(original)
    superseded.update(
        {
            "cohort_state": COHORT_SUPERSEDED,
            "is_propagatable": False,
            "superseded_by": list(SPLIT_DECISION["superseded_by"]),
            "review_status": FIRST_REVIEW_COMPLETE,
            "reviewer": REVIEW_METADATA["reviewer_id"],
            "requires_human_review": True,
            "human_review_reasons": [
                "sostituita da quattro unita' revisionate; conservata come record storico",
                "richiede seconda revisione indipendente",
            ],
            "cohort_note": SPLIT_DECISION["rationale"],
            "superseded_at": created_at,
        }
    )
    write_jsonl(output / "superseded_profile_units.jsonl", [superseded])
    write_jsonl(
        output / "reviewed_profile_units.jsonl", [unit.as_dict() for unit in units]
    )

    # --- decisioni statement-level -------------------------------------------
    by_id = {unit.profile_unit_id: unit for unit in units}
    decisions_out: list[dict[str, Any]] = []
    for decision in STATEMENT_DECISIONS:
        linked = [by_id[item] for item in decision["profile_unit_ids"] if item in by_id]
        decisions_out.append(
            {
                "statement_id": decision["statement_id"],
                "profile_unit_ids": list(decision["profile_unit_ids"]),
                "first_review_link_status": decision["link_status"],
                "rationale": decision["rationale"],
                "mutation": decision.get("mutation", ""),
                "intervention_mapping": decision.get("intervention_mapping", ""),
                "mapping_status": decision.get("mapping_status", ""),
                "resistance_qualifier": decision.get("resistance_qualifier", ""),
                "clinical_response_observed": decision.get("clinical_response_observed"),
                "evidence_design": (
                    "preclinical_in_vitro"
                    if linked and all(unit.is_preclinical for unit in linked)
                    else "mixed_clinical_and_preclinical"
                    if any(unit.is_clinical for unit in linked)
                    and any(unit.is_preclinical for unit in linked)
                    else "clinical"
                ),
                "has_clinical_component": any(unit.is_clinical for unit in linked),
                "has_preclinical_component": any(unit.is_preclinical for unit in linked),
                "reviewer_id": REVIEW_METADATA["reviewer_id"],
                "review_method": REVIEW_METADATA["review_method"],
                "independent_review": REVIEW_METADATA["independent_review"],
                "clinical_reviewer": REVIEW_METADATA["clinical_reviewer"],
                "is_evaluable_for_final_metrics": False,
                "review_version": REVIEW_VERSION,
                "created_at": created_at,
                "note": (
                    "decisione di prima revisione. Non e' gold e non entra in nessuna "
                    "metrica finale di linking o accordo."
                ),
            }
        )
    decisions_out.sort(key=lambda item: item["statement_id"])
    write_jsonl(output / "statement_first_review_decisions.jsonl", decisions_out)

    # --- gold provvisorio aggiornato -----------------------------------------
    reviewed_ids = {item["statement_id"] for item in decisions_out}
    decision_by_statement = {item["statement_id"]: item for item in decisions_out}
    gold_rows: list[dict[str, Any]] = []
    for row in read_jsonl(args.curation_dir / "provisional_gold.jsonl"):
        updated = dict(row)
        statement_id = str(row["statement_id"])
        if statement_id in reviewed_ids and str(row["profile_unit_id"]) == ORIGINAL_UNIT_ID:
            decision = decision_by_statement[statement_id]
            updated.update(
                {
                    "review_stage": "first_review_complete",
                    "final_status": PROVISIONAL_FIRST_REVIEW,
                    "is_evaluable": False,
                    "first_annotator": REVIEW_METADATA["reviewer_id"],
                    "second_annotator": None,
                    "agreement": None,
                    "adjudication": None,
                    "requires_second_review": True,
                    "first_review_annotation": {
                        "link_status": decision["first_review_link_status"],
                        "profile_unit_ids": decision["profile_unit_ids"],
                        "rationale": decision["rationale"],
                        "reviewer_id": REVIEW_METADATA["reviewer_id"],
                        "review_method": REVIEW_METADATA["review_method"],
                        "independent_review": REVIEW_METADATA["independent_review"],
                        "clinical_reviewer": REVIEW_METADATA["clinical_reviewer"],
                    },
                    "note": (
                        "prima revisione registrata. Il link_status vive in "
                        "first_review_annotation e non in final_status: una prima "
                        "revisione non indipendente non puo' essere il riferimento "
                        "contro cui si misura il linker."
                    ),
                }
            )
        gold_rows.append(updated)
    write_jsonl(output / "provisional_gold.jsonl", gold_rows)

    write_json(
        output / f"first_review_annotation_{PACKET_ID}.json",
        {
            **REVIEW_METADATA,
            "source": {
                "pmid": PMID,
                "canonical_source_id": CANONICAL_SOURCE_ID,
                "title": SOURCE_TITLE,
                "pmc_id": source_check["pmc_id"],
                "document_sha256": document_hash,
            },
            "split_decision": {**SPLIT_DECISION, "superseded_by": list(SPLIT_DECISION["superseded_by"])},
            "units": [unit.profile_unit_id for unit in units],
            "statement_decisions": len(decisions_out),
            "intervention_mappings": list(INTERVENTION_MAPPINGS),
            "propagation_rules_checked": True,
            "propagation_violations": [],
            "created_at": created_at,
        },
    )
    write_jsonl(output / "intervention_mappings.jsonl", list(INTERVENTION_MAPPINGS))

    # --- metriche descrittive -------------------------------------------------
    valid = sum(1 for item in decisions_out if item["first_review_link_status"] == "valid_link")
    partial = sum(
        1 for item in decisions_out if item["first_review_link_status"] == "partial_link"
    )
    known = sum(len(unit.known_dimensions()) for unit in units)
    not_applicable = sum(len(unit.not_applicable_dimensions()) for unit in units)
    unknown = len(units) * len(UNIT_DIMENSIONS) - known - not_applicable

    write_json(
        output / "first_review_metrics.json",
        {
            "created_at": created_at,
            "first_review_packets_completed": 1,
            "first_review_statements_reviewed": len(decisions_out),
            "first_review_profile_units_created": len(units),
            "first_review_valid_link_decisions": valid,
            "first_review_partial_link_decisions": partial,
            "first_review_fields_confirmed": known,
            "first_review_fields_not_applicable": not_applicable,
            "first_review_fields_unknown": unknown,
            "qualifier_provenance_completeness": (
                1.0 if all(unit.provenance_complete() for unit in units) else 0.0
            ),
            "coverage_by_review_stage": {
                "first_review_proposed": known,
                "second_review_confirmed": 0,
                "final_adjudicated": 0,
            },
            "second_review_packets_completed": 0,
            "linking_precision": "not_calculated",
            "linking_recall": "not_calculated",
            "linking_f1": "not_calculated",
            "inter_annotator_agreement": "not_calculated",
            "final_accuracy": "not_calculated",
            "not_calculated_reason": (
                "la prima revisione non e' indipendente e non e' clinica; nessuna "
                "seconda revisione esiste. Ogni metrica finale calcolata adesso "
                "misurerebbe un solo giudizio contro se stesso."
            ),
            "hashes": {
                "reviewed_units": content_hash([unit.as_dict() for unit in units]),
                "statement_decisions": content_hash(decisions_out),
                "provisional_gold": content_hash(gold_rows),
            },
        },
    )

    print(f"unita' create: {len(units)} | statement decisi: {len(decisions_out)}")
    print(f"valid_link: {valid} | partial_link: {partial}")
    print(f"campi confirmed: {known} | not_applicable: {not_applicable} | unknown: {unknown}")
    print(f"locator verificati: {source_check['locators_verified']} / {source_check['locators_total']}")
    print("regole di propagazione: nessuna violazione")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
