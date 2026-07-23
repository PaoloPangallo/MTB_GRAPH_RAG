"""Unita' proposte, mapping degli statement e normalizzazione terminologica.

Le unita' portano i valori letti sulla fonte, e ogni valore noto porta la sua
provenienza: un campo senza provenienza non e' distinguibile da un campo
inventato, ed e' l'invariante che rende il batch verificabile.

Tre sentinella, tre significati diversi:

- `unknown` — la domanda si pone e la fonte non risponde;
- `not_applicable` — la domanda non si pone (la linea di terapia di una linea
  cellulare non esiste);
- `not_separable` — la fonte descrive la dimensione ma non permette di
  attribuirla alle unita' separatamente.

Collassarli farebbe sparire informazione: `unknown` invita a cercare ancora,
`not_applicable` dice che non c'e' niente da cercare, `not_separable` dice che
cercare non basterebbe.
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

from backend.pipeline.evidence.profile_unit import (  # noqa: E402
    COHORT_SPLIT_REVIEW_PROPOSED,
    IN_VITRO_UNIT_TYPES,
    IN_VIVO_UNIT_TYPES,
    NOT_APPLICABLE,
    SOURCE_CHECKED,
    SOURCE_CHECKED_REVIEW_PROPOSAL,
    UNKNOWN,
    FieldProvenance,
    SourceClinicalProfileUnit,
)
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_findings import (  # noqa: E402
    FINDINGS,
    ProposedUnit,
    SourceFinding,
)
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_review import (  # noqa: E402
    CANDIDATE_LINK_STATES,
    REVIEW_VERSION,
    SUPPORT_TYPES,
    TERMINOLOGY_STATES,
    span_hash,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")

ASSERTED_BY = f"source_checked_documentary_review ({REVIEW_VERSION})"

# Dimensioni cliniche che su un modello non hanno risposta. Non sono ignote:
# chiedere lo stadio di una linea cellulare non e' una domanda a cui manchi il
# dato, e' una domanda che non si pone.
CLINICAL_ONLY_DIMENSIONS = (
    "population",
    "stage",
    "setting",
    "therapy_line",
    "resection_status",
    "prior_therapies",
    "inclusion_criteria",
    "exclusion_criteria",
)

# Dimensioni descrittive del modello: viaggiano nel record, non nella dataclass,
# perche' valgono solo per un tipo di unita'.
MODEL_FIELDS = (
    "model_type",
    "cell_line",
    "assay",
    "endpoint",
    "resistance_qualifier",
    "n_subjects",
    "outcomes",
)


class ProposalError(RuntimeError):
    """Una proposta non conforme agli invarianti della fase."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _is_preclinical(unit: ProposedUnit) -> bool:
    return unit.unit_type.startswith("preclinical")


def _field_decisions(unit: ProposedUnit) -> dict[str, str]:
    """Il verdetto su ogni dimensione, che e' l'autorita' sul sentinella."""
    decisions: dict[str, str] = {}
    preclinical = _is_preclinical(unit)

    for dimension in CLINICAL_ONLY_DIMENSIONS:
        if dimension in unit.not_separable:
            decisions[dimension] = "not_separable"
        elif preclinical:
            decisions[dimension] = NOT_APPLICABLE
        else:
            value = getattr(unit, dimension, UNKNOWN)
            decisions[dimension] = "confirmed" if value not in (UNKNOWN, (), "") else UNKNOWN

    for dimension in ("disease", "biomarker_requirements", "intervention", "comparator", "evidence_design"):
        if dimension in unit.not_separable:
            decisions[dimension] = "not_separable"
            continue
        value = getattr(unit, dimension, UNKNOWN)
        if value == NOT_APPLICABLE:
            decisions[dimension] = NOT_APPLICABLE
        elif value in (UNKNOWN, (), ""):
            decisions[dimension] = UNKNOWN
        else:
            decisions[dimension] = "confirmed"

    decisions["regimen"] = UNKNOWN
    return decisions


def _provenance(unit: ProposedUnit, dimensions: tuple[str, ...], access_date: str) -> list[FieldProvenance]:
    primary = unit.locator_ids[0] if unit.locator_ids else ""
    joined = ", ".join(unit.locator_ids)
    return [
        FieldProvenance(
            field_name=dimension,
            value_origin="source_document",
            source_locator=primary,
            access_date=access_date,
            asserted_by=ASSERTED_BY,
            span_hash=span_hash(f"{unit.unit_id}:{dimension}:{joined}"),
            note=f"locator: {joined}",
        )
        for dimension in dimensions
    ]


def build_unit(
    unit: ProposedUnit,
    finding: SourceFinding,
    *,
    created_at: str,
    access_date: str,
    source_checked: bool,
) -> dict[str, Any]:
    preclinical = _is_preclinical(unit)
    decisions = _field_decisions(unit)

    profile = SourceClinicalProfileUnit(
        profile_unit_id=unit.unit_id,
        canonical_source_id=finding.canonical_source_id,
        pmids=(finding.pmid,),
        cohort_id=unit.unit_id.rsplit("-", 2)[-1] if "-" in unit.unit_id else "unit-1",
        cohort_label=unit.label,
        cohort_state=COHORT_SPLIT_REVIEW_PROPOSED,
        cohort_note=unit.rationale,
        unit_type=unit.unit_type,
        disease=unit.disease,
        biomarker_requirements=unit.biomarker_requirements,
        intervention=unit.intervention,
        comparator=unit.comparator,
        population=NOT_APPLICABLE if preclinical else unit.population,
        stage=NOT_APPLICABLE if preclinical else UNKNOWN,
        setting=NOT_APPLICABLE if preclinical else UNKNOWN,
        therapy_line=NOT_APPLICABLE if preclinical else unit.therapy_line,
        prior_therapies=unit.prior_therapies,
        resection_status=NOT_APPLICABLE if preclinical else UNKNOWN,
        inclusion_criteria=NOT_APPLICABLE if preclinical else UNKNOWN,
        exclusion_criteria=NOT_APPLICABLE if preclinical else UNKNOWN,
        evidence_design=unit.evidence_design,
        field_decisions=decisions,
        statement_ids=unit.statement_candidates,
        source_spans=unit.locator_ids,
        extraction_status=SOURCE_CHECKED if source_checked else "machine_extracted",
        review_status=SOURCE_CHECKED_REVIEW_PROPOSAL,
        requires_human_review=True,
        human_review_reasons=(
            "proposta prodotta da verifica documentale automatica, non da revisione umana",
            "i valori letti sulla fonte vanno confermati prima di poter propagare",
        ),
        created_at=created_at,
    )
    profile = SourceClinicalProfileUnit(
        **{
            **{key: getattr(profile, key) for key in profile.__dataclass_fields__},
            "provenance": tuple(_provenance(unit, profile.known_dimensions(), access_date)),
        }
    )

    if not profile.provenance_complete():
        raise ProposalError(
            f"{unit.unit_id}: provenienza mancante per {list(profile.missing_provenance())}"
        )
    if profile.is_propagatable:
        raise ProposalError(f"{unit.unit_id}: una proposta non puo' essere propagabile")

    record = profile.as_dict()
    record.update(
        {
            "proposed_profile_unit_id": unit.unit_id,
            "parent_profile_unit_id": finding.parent_unit_id,
            "unit_label": unit.label,
            "structural_decision": finding.decision,
            "human_reviewed": False,
            "first_review_complete": False,
            "second_review_complete": False,
            "is_evaluable": False,
            "requires_author_approval": True,
            "requires_second_independent_review": True,
            "source_checked": source_checked,
            "is_in_vitro": unit.unit_type in IN_VITRO_UNIT_TYPES,
            "is_in_vivo": unit.unit_type in IN_VIVO_UNIT_TYPES,
            "not_separable_dimensions": list(unit.not_separable),
            "source_locators": list(unit.locator_ids),
            "statement_candidates": list(unit.statement_candidates),
            "audit_rationale": unit.rationale,
            "biomarker_role": unit.biomarker_role,
            "review_version": REVIEW_VERSION,
            **{field: _serialise(getattr(unit, field)) for field in MODEL_FIELDS},
        }
    )
    return record


def _serialise(value: Any) -> Any:
    return list(value) if isinstance(value, tuple) else value


def build_statement_rows(finding: SourceFinding, *, created_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for statement in finding.statements:
        if statement.support_type not in SUPPORT_TYPES:
            raise ProposalError(f"support_type non ammesso: {statement.support_type!r}")
        if statement.candidate_link_status not in CANDIDATE_LINK_STATES:
            raise ProposalError(
                f"candidate_link_status non ammesso: {statement.candidate_link_status!r}"
            )
        rows.append(
            {
                "statement_id": statement.statement_id,
                "parent_profile_unit_id": finding.parent_unit_id,
                "canonical_source_id": finding.canonical_source_id,
                "proposed_profile_unit_ids": list(statement.proposed_unit_ids),
                "support_type": statement.support_type,
                "candidate_link_status": statement.candidate_link_status,
                "directness": statement.directness,
                "clinical_or_preclinical": _level(statement.support_type),
                "clinical_support": statement.clinical_support,
                "preclinical_support": statement.preclinical_support,
                "evidence_context": finding.availability,
                "normalization_required": bool(finding.terminology),
                "conflict_dimensions": list(statement.conflict_dimensions),
                "not_separable_dimensions": list(finding.not_separable_dimensions),
                "non_propagation_rules": list(statement.non_propagation_rules),
                "source_locators": list(statement.locator_ids),
                "rationale": statement.rationale,
                "is_gold": False,
                "human_reviewed": False,
                "requires_author_approval": True,
                "created_at": created_at,
                "review_version": REVIEW_VERSION,
            }
        )
    return rows


def _level(support_type: str) -> str:
    if support_type.startswith("direct_clinical") or support_type == "clinical_context_only":
        return "clinical"
    if support_type.startswith("direct_preclinical") or support_type == "preclinical_context_only":
        return "preclinical"
    if support_type == "clinical_observation_with_preclinical_validation":
        return "both"
    return "not_determinable"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()
    access_date = created_at[:10]

    verification = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(args.output / "source_access_verification.jsonl")
    }

    units: list[dict[str, Any]] = []
    statements: list[dict[str, Any]] = []
    terminology: list[dict[str, Any]] = []
    provisional: list[dict[str, Any]] = []

    for finding in FINDINGS:
        access = verification.get(finding.parent_unit_id, {})
        source_checked = bool(access.get("locators_verified"))
        for unit in finding.units:
            units.append(
                build_unit(
                    unit,
                    finding,
                    created_at=created_at,
                    access_date=access_date,
                    source_checked=source_checked,
                )
            )

        statements.extend(build_statement_rows(finding, created_at=created_at))

        for mapping in finding.terminology:
            if mapping.mapping_status not in TERMINOLOGY_STATES:
                raise ProposalError(f"stato di mapping non ammesso: {mapping.mapping_status!r}")
            terminology.append(
                {
                    "parent_profile_unit_id": finding.parent_unit_id,
                    "canonical_source_id": finding.canonical_source_id,
                    "original_source_term": mapping.original_source_term,
                    "normalized_term": mapping.normalized_term,
                    "mapping_type": mapping.mapping_type,
                    "mapping_source": mapping.mapping_source,
                    "mapping_status": mapping.mapping_status,
                    "literal_string_present": mapping.literal_string_present,
                    "review_required": mapping.review_required,
                    "source_locators": list(mapping.locator_ids),
                    "rationale": mapping.rationale,
                    "created_at": created_at,
                    "review_version": REVIEW_VERSION,
                }
            )

    for row in statements:
        provisional.append(
            {
                "statement_id": row["statement_id"],
                "parent_profile_unit_id": row["parent_profile_unit_id"],
                "proposed_profile_unit_ids": row["proposed_profile_unit_ids"],
                "review_stage": "awaiting_author_approval",
                "final_status": "provisional_unreviewed",
                "is_evaluable": False,
                "first_annotator": None,
                "second_annotator": None,
                "agreement": None,
                "adjudication": None,
                "created_at": row["created_at"],
                "review_version": REVIEW_VERSION,
            }
        )

    units.sort(key=lambda row: row["proposed_profile_unit_id"])
    statements.sort(key=lambda row: (row["parent_profile_unit_id"], row["statement_id"]))
    terminology.sort(key=lambda row: (row["parent_profile_unit_id"], row["original_source_term"]))
    provisional.sort(key=lambda row: row["statement_id"])

    write_jsonl(args.output / "proposed_profile_units.jsonl", units)
    write_jsonl(args.output / "statement_unit_review_proposals.jsonl", statements)
    write_jsonl(args.output / "terminology_mappings.jsonl", terminology)
    write_jsonl(args.output / "provisional_review_records.jsonl", provisional)

    print(f"unita' proposte: {len(units)}")
    print(f"  cliniche: {sum(1 for row in units if row['is_clinical'])}")
    print(f"  precliniche: {sum(1 for row in units if row['is_preclinical'])}")
    print(f"  in vitro: {sum(1 for row in units if row['is_in_vitro'])}")
    print(f"  in vivo: {sum(1 for row in units if row['is_in_vivo'])}")
    print(f"statement mappati: {len(statements)}")
    print(f"mapping terminologici: {len(terminology)}")
    print(f"record provvisori: {len(provisional)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
