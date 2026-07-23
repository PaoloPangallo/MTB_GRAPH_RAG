"""L'unita' clinica approvata, e lo storico di cio' che e' stato respinto.

Una sola unita' resta attiva. Le proposte che la revisione ha respinto — la
componente clinica e quella preclinica dell'audit — restano nello storico con
stato `rejected`: cancellarle renderebbe illeggibile la storia del corpus, e
soprattutto renderebbe invisibile che il rilevatore aveva sbagliato.

L'unita' approvata **non e' propagabile**. Lo stato
`reviewed_pending_independent_review` non compare fra quelli propagabili, quindi
il blocco non dipende da un controllo che qualcuno potrebbe dimenticare di
scrivere.
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
    COHORT_REVIEWED_PENDING_INDEPENDENT,
    COHORT_SUPERSEDED_BY_RESTRUCTURE,
    FIRST_REVIEW_COMPLETE,
    SOURCE_CHECKED,
    FieldProvenance,
    SourceClinicalProfileUnit,
)
from benchmarks.mtb_evidence.evaluation.author_approval import (  # noqa: E402
    APPROVAL_VERSION,
    APPROVED_UNIT_ID,
    AUTHOR_DECISION,
    CANONICAL_SOURCE_ID,
    NOT_SEPARABLE_FIELDS,
    PARENT_UNIT_ID,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
    STRUCTURAL_DECISION,
    SUBGROUP_STRUCTURE,
    UNKNOWN_FIELDS,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/author_approval")
DEFAULT_BATCH = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")
DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/v3/cohort_split_audit")

# Le due unita' che l'audit aveva proposto e che la revisione ha respinto.
REJECTED_PROPOSALS = (
    "PU-PMID-31358542-clinical-component",
    "PU-PMID-31358542-preclinical-component",
)


class ApprovalError(RuntimeError):
    """L'unita' approvata viola un invariante della fase."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def enrich_provenance(
    entries: list[dict[str, Any]],
    *,
    document_hash: str,
    review_date: str,
) -> list[dict[str, Any]]:
    """Aggiunge alla provenienza chi ha rivisto il campo e con quale metodo.

    La provenienza documentale dice da dove viene il valore; senza il revisore e
    il metodo non dice chi risponde di quel valore, che e' l'altra meta' della
    domanda.
    """
    return [
        {
            **entry,
            "source_identifier": CANONICAL_SOURCE_ID,
            "document_hash": document_hash,
            "extraction_method": REVIEW_METHOD,
            "reviewer": REVIEWER_ID,
            "reviewer_role": REVIEWER_ROLE,
            "review_method": REVIEW_METHOD,
            "review_date": review_date,
        }
        for entry in entries
    ]


def build_approved_unit(
    proposal: dict[str, Any],
    *,
    document_hash: str,
    created_at: str,
) -> dict[str, Any]:
    review_date = created_at[:10]

    unit = SourceClinicalProfileUnit(
        profile_unit_id=APPROVED_UNIT_ID,
        canonical_source_id=proposal["canonical_source_id"],
        pmids=tuple(proposal["pmids"]),
        cohort_id=proposal["cohort_id"],
        cohort_label=proposal["cohort_label"],
        cohort_state=COHORT_REVIEWED_PENDING_INDEPENDENT,
        cohort_note=(
            "prima revisione approvata: la fonte e' interamente clinica. Lo split "
            "clinico/preclinico proposto dall'audit e' stato respinto, quindi il "
            "risultato non e' uno split ma una unita' sola."
        ),
        unit_type=proposal["unit_type"],
        disease=proposal["disease"],
        biomarker_requirements=tuple(proposal["biomarker_requirements"]),
        intervention=tuple(proposal["intervention"]),
        regimen=proposal["regimen"],
        comparator=proposal["comparator"],
        population=proposal["population"],
        stage=proposal["stage"],
        setting=proposal["setting"],
        therapy_line=proposal["therapy_line"],
        prior_therapies=tuple(proposal["prior_therapies"]),
        resection_status=proposal["resection_status"],
        inclusion_criteria=proposal["inclusion_criteria"],
        exclusion_criteria=proposal["exclusion_criteria"],
        evidence_design=proposal["evidence_design"],
        field_decisions=dict(proposal["field_decisions"]),
        statement_ids=tuple(proposal["statement_ids"]),
        source_spans=tuple(proposal["source_spans"]),
        extraction_status=SOURCE_CHECKED,
        review_status=FIRST_REVIEW_COMPLETE,
        reviewer=REVIEWER_ID,
        requires_human_review=True,
        human_review_reasons=(
            "prima revisione approvata dall'autore, non da un clinico",
            "serve una seconda revisione indipendente prima di poter propagare",
        ),
        supersedes=PARENT_UNIT_ID,
        provenance=tuple(
            FieldProvenance(**{key: entry[key] for key in FieldProvenance.__dataclass_fields__})
            for entry in proposal["provenance"]
        ),
        created_at=created_at,
    )

    if unit.is_propagatable:
        raise ApprovalError(
            f"{APPROVED_UNIT_ID}: una unita' in attesa di revisione indipendente non "
            "puo' essere propagabile"
        )
    if not unit.provenance_complete():
        raise ApprovalError(
            f"{APPROVED_UNIT_ID}: provenienza mancante per {list(unit.missing_provenance())}"
        )

    record = unit.as_dict()
    record["provenance"] = enrich_provenance(
        record["provenance"], document_hash=document_hash, review_date=review_date
    )
    record.update(
        {
            "parent_profile_unit_id": PARENT_UNIT_ID,
            "is_active": True,
            "human_reviewed": True,
            "clinical_reviewed": False,
            "independent_review": False,
            "first_review_complete": True,
            "second_review_complete": False,
            "requires_second_independent_review": True,
            "is_evaluable": False,
            "reviewer_id": REVIEWER_ID,
            "reviewer_role": REVIEWER_ROLE,
            "review_method": REVIEW_METHOD,
            "review_date": review_date,
            "author_decision": AUTHOR_DECISION,
            "structural_decision": STRUCTURAL_DECISION,
            "document_hash": document_hash,
            "unknown_fields": list(UNKNOWN_FIELDS),
            "not_separable_fields": list(NOT_SEPARABLE_FIELDS),
            **{key: value for key, value in SUBGROUP_STRUCTURE.items() if key != "rationale"},
            "subgroup_rationale": SUBGROUP_STRUCTURE["rationale"],
            "subgroup_future_split_conditions": list(
                SUBGROUP_STRUCTURE["future_split_conditions"]
            ),
            "approval_version": APPROVAL_VERSION,
        }
    )
    return record


def build_history(created_at: str, audit_units: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """La parent e le proposte respinte, conservate e disattivate."""
    rows: list[dict[str, Any]] = [
        {
            "profile_unit_id": PARENT_UNIT_ID,
            "canonical_source_id": CANONICAL_SOURCE_ID,
            "role": "parent_unit",
            "cohort_state": COHORT_SUPERSEDED_BY_RESTRUCTURE,
            "review_status": FIRST_REVIEW_COMPLETE,
            "reviewer": REVIEWER_ID,
            "is_active": False,
            "is_propagatable": False,
            "superseded_by": [APPROVED_UNIT_ID],
            "supersedes": "",
            "note": (
                "sostituita da una sola unita' clinica. Non e' uno split: la revisione "
                "ha respinto lo split e ha confermato che la fonte descrive una "
                "struttura sola"
            ),
            "created_at": created_at,
            "approval_version": APPROVAL_VERSION,
        }
    ]
    for unit_id in REJECTED_PROPOSALS:
        audit = audit_units.get(unit_id, {})
        rows.append(
            {
                "profile_unit_id": unit_id,
                "canonical_source_id": CANONICAL_SOURCE_ID,
                "role": "rejected_audit_proposal",
                "cohort_state": audit.get("cohort_state", "candidate_cohort"),
                "review_status": "rejected",
                "reviewer": REVIEWER_ID,
                "is_active": False,
                "is_propagatable": False,
                "superseded_by": [],
                "supersedes": "",
                "unit_type": audit.get("unit_type", ""),
                "rejection_reason": (
                    "la fonte non contiene esperimenti preclinici propri: la componente "
                    "che questa proposta separava non esiste"
                ),
                "retained_for": "storico: la proposta respinta documenta l'errore del rilevatore",
                "created_at": created_at,
                "approval_version": APPROVAL_VERSION,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    proposals = {
        str(row["proposed_profile_unit_id"]): row
        for row in read_jsonl(args.batch_dir / "proposed_profile_units.jsonl")
    }
    proposal = proposals[APPROVED_UNIT_ID]
    access = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(args.batch_dir / "source_access_verification.jsonl")
    }
    document_hash = access[PARENT_UNIT_ID]["document_hash"]
    audit_units = {
        str(row["proposed_profile_unit_id"]): row
        for row in read_jsonl(args.audit_dir / "proposed_profile_units.jsonl")
    }

    approved = build_approved_unit(
        proposal, document_hash=document_hash, created_at=created_at
    )
    write_jsonl(args.output / "approved_profile_units.jsonl", [approved])
    write_jsonl(args.output / "parent_unit_history.jsonl", build_history(created_at, audit_units))

    print(f"unita' attive: 1 ({APPROVED_UNIT_ID})")
    print(f"  propagabile: {approved['is_propagatable']} · valutabile: {approved['is_evaluable']}")
    print(f"  sottogruppi analizzati: {approved['analyzed_subgroups_count']} (nessuna unita' creata)")
    print(f"unita' disattivate: {1 + len(REJECTED_PROPOSALS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
