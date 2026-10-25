"""Le quattro unita' approvate, la consolidazione, e lo storico di cio' che resta.

Quattro unita' restano attive. Cinque proposte source-checked restano nel
repository: tre promosse a unita' approvate, due sostituite da una sola unita'
epistemica. Nessuna viene cancellata — la differenza fra cinque e quattro **e'**
la decisione, e un repository che conservasse solo il risultato renderebbe
illeggibile il ragionamento che ci ha portato.

Nessuna unita' e' propagabile, e non perche' un controllo lo vieti: lo stato
`reviewed_pending_independent_review` non compare fra quelli propagabili, quindi
il blocco viene dalla politica e non da una riga che qualcuno potrebbe
dimenticare di scrivere. Lo script lo verifica invece di dichiararlo.

La consolidazione Ba/F3 + NIH3T3 e' l'unico punto in cui un valore non viene da
una singola proposta: `evidence_design` descrive due saggi, e la sua provenienza
lo dice esplicitamente invece di far sembrare che una frase della fonte lo
contenga gia'.
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
from backend.pipeline.evidence.propagation_guards import run_guards  # noqa: E402
from backend.pipeline.evidence.propagation_policy import (  # noqa: E402
    PROTOTYPE_ONLY,
    validate_units,
)
from benchmarks.mtb_evidence.evaluation.author_approval_22235099 import (  # noqa: E402
    APPROVAL_VERSION,
    APPROVED_UNIT_IDS,
    APPROVED_UNITS,
    AUTHOR_APPROVED_UNITS,
    AUTHOR_DECISION,
    CANONICAL_SOURCE_ID,
    CONSOLIDATION,
    DOCUMENT_HASH,
    PARENT_STATE,
    PARENT_UNIT_ID,
    REPLACED_PROPOSALS,
    REPLACEMENT_STATUS,
    RETAINED_PROPOSALS,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
    SOURCE_REVIEW_PROPOSED_UNITS,
    STRUCTURAL_DECISION,
    ApprovedUnit,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/author_approval_22235099")
DEFAULT_BATCH = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")
DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/v3/cohort_split_audit")

CONSOLIDATED_ORIGIN = "author_approved_consolidation"


class ApprovalError(RuntimeError):
    """Una unita' approvata viola un invariante della fase."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _merge_values(proposals: list[dict[str, Any]], key: str) -> Any:
    """Il valore di una dimensione quando le proposte da fondere sono piu' di una.

    Se le proposte concordano il valore e' quello, e la fusione non ha aggiunto
    nulla. Se divergono, fondere in silenzio produrrebbe un valore che nessuna
    delle due sosteneva: chi chiama deve fornire un override esplicito, e in
    assenza lo script si ferma.
    """
    values = [proposal.get(key) for proposal in proposals]
    first = values[0]
    for value in values[1:]:
        if value != first:
            raise ApprovalError(
                f"le proposte divergono su {key!r} e nessun override e' dichiarato: "
                f"{values!r}"
            )
    return first


def merged_provenance(
    proposals: list[dict[str, Any]],
    overrides: dict[str, Any],
    *,
    review_date: str,
) -> list[dict[str, Any]]:
    """La provenienza di ogni proposta, piu' quella dei valori consolidati.

    Le voci delle proposte restano distinte anche quando riguardano la stessa
    dimensione: ciascun modello ha letto la fonte per conto proprio, e fonderle in
    una sola farebbe sparire il fatto che le letture erano due.
    """
    entries: list[dict[str, Any]] = []
    for proposal in proposals:
        origin = str(proposal.get("proposed_profile_unit_id") or "")
        for item in proposal.get("provenance") or []:
            if item.get("field_name") in overrides:
                continue
            entries.append({**item, "derived_from_proposal_id": origin})

    for field_name, value in overrides.items():
        locators = sorted(
            {
                str(locator)
                for proposal in proposals
                for locator in proposal.get("source_locators") or []
            }
        )
        entries.append(
            {
                "field_name": field_name,
                # Non `source_document`: il valore e' la congiunzione di due
                # letture verificate, non una frase che la fonte contenga.
                "value_origin": CONSOLIDATED_ORIGIN,
                "source_locator": locators[0] if locators else "",
                "access_date": review_date,
                "asserted_by": f"{REVIEWER_ID} ({REVIEW_METHOD})",
                "span_hash": "",
                "note": (
                    "valore consolidato dalle proposte "
                    + ", ".join(
                        str(proposal.get("proposed_profile_unit_id") or "")
                        for proposal in proposals
                    )
                    + "; locator: "
                    + ", ".join(locators)
                ),
                "derived_from_proposal_id": ",".join(
                    str(proposal.get("proposed_profile_unit_id") or "")
                    for proposal in proposals
                ),
            }
        )
    return entries


def enrich_provenance(
    entries: list[dict[str, Any]], *, review_date: str
) -> list[dict[str, Any]]:
    """Aggiunge alla provenienza chi ha rivisto il campo e con quale metodo."""
    return [
        {
            **entry,
            "source_identifier": CANONICAL_SOURCE_ID,
            "document_hash": DOCUMENT_HASH,
            "extraction_method": REVIEW_METHOD,
            "reviewer": REVIEWER_ID,
            "reviewer_role": REVIEWER_ROLE,
            "review_method": REVIEW_METHOD,
            "review_date": review_date,
        }
        for entry in entries
    ]


def build_unit(
    spec: ApprovedUnit,
    proposals: dict[str, dict[str, Any]],
    *,
    created_at: str,
) -> dict[str, Any]:
    review_date = created_at[:10]
    sources = [proposals[unit_id] for unit_id in spec.source_proposal_ids]
    overrides = dict(spec.overrides)

    def value(key: str) -> Any:
        if key in overrides:
            return overrides[key]
        return _merge_values(sources, key)

    unit = SourceClinicalProfileUnit(
        profile_unit_id=spec.profile_unit_id,
        canonical_source_id=CANONICAL_SOURCE_ID,
        pmids=tuple(value("pmids")),
        cohort_id=spec.cohort_id,
        cohort_label=spec.cohort_label,
        cohort_state=COHORT_REVIEWED_PENDING_INDEPENDENT,
        cohort_note=spec.cohort_note,
        unit_type=spec.unit_type,
        disease=value("disease"),
        biomarker_requirements=tuple(value("biomarker_requirements")),
        intervention=tuple(value("intervention")),
        regimen=value("regimen"),
        comparator=value("comparator"),
        population=value("population"),
        stage=value("stage"),
        setting=value("setting"),
        therapy_line=value("therapy_line"),
        prior_therapies=tuple(value("prior_therapies")),
        resection_status=value("resection_status"),
        inclusion_criteria=value("inclusion_criteria"),
        exclusion_criteria=value("exclusion_criteria"),
        evidence_design=value("evidence_design"),
        field_decisions=dict(_merge_values(sources, "field_decisions")),
        statement_ids=tuple(spec.statement_ids),
        source_spans=tuple(
            sorted({str(span) for source in sources for span in source.get("source_spans") or []})
        ),
        extraction_status=SOURCE_CHECKED,
        review_status=FIRST_REVIEW_COMPLETE,
        reviewer=REVIEWER_ID,
        independent_review=False,
        clinical_reviewed=False,
        gold_covered=False,
        requires_human_review=True,
        human_review_reasons=(
            "prima revisione approvata dall'autore, non da un clinico",
            "serve una seconda revisione indipendente prima di poter propagare",
        ),
        supersedes=PARENT_UNIT_ID,
        provenance=tuple(
            FieldProvenance(
                **{
                    key: entry[key]
                    for key in FieldProvenance.__dataclass_fields__
                    if key in entry
                }
            )
            for entry in merged_provenance(sources, overrides, review_date=review_date)
        ),
        created_at=created_at,
    )

    if unit.is_propagatable:
        raise ApprovalError(
            f"{spec.profile_unit_id}: una unita' in attesa di revisione indipendente "
            "non puo' essere propagabile"
        )
    if unit.propagation_eligibility != PROTOTYPE_ONLY:
        raise ApprovalError(
            f"{spec.profile_unit_id}: eligibility {unit.propagation_eligibility!r} "
            f"invece di {PROTOTYPE_ONLY!r}"
        )
    if not unit.provenance_complete():
        raise ApprovalError(
            f"{spec.profile_unit_id}: provenienza mancante per "
            f"{list(unit.missing_provenance())}"
        )

    record = unit.as_dict()
    record["provenance"] = enrich_provenance(
        merged_provenance(sources, overrides, review_date=review_date),
        review_date=review_date,
    )
    record.update(
        {
            "parent_profile_unit_id": PARENT_UNIT_ID,
            "source_proposal_ids": list(spec.source_proposal_ids),
            "is_active": True,
            "human_reviewed": True,
            "clinical_reviewed": False,
            "clinical_reviewer": False,
            "independent_review": False,
            "first_review_complete": True,
            "second_review_complete": False,
            "requires_second_independent_review": True,
            "is_evaluable": False,
            "is_hard_filterable": False,
            "used_as_hard_filter": False,
            "reviewer_id": REVIEWER_ID,
            "reviewer_role": REVIEWER_ROLE,
            "review_method": REVIEW_METHOD,
            "review_date": review_date,
            "author_decision": AUTHOR_DECISION,
            "structural_decision": STRUCTURAL_DECISION,
            "document_hash": DOCUMENT_HASH,
            "experiment_role": spec.experiment_role,
            "assertion_polarity": spec.assertion_polarity,
            "source_locators": list(
                sorted(
                    {
                        str(locator)
                        for source in sources
                        for locator in source.get("source_locators") or []
                    }
                )
            ),
            "author_corrections": list(spec.corrections),
            "approval_version": APPROVAL_VERSION,
            **dict(spec.role_fields),
        }
    )
    return record


def build_history(
    created_at: str, proposals: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """La parent e le cinque proposte, tutte conservate e nessuna attiva."""
    rows: list[dict[str, Any]] = [
        {
            "profile_unit_id": PARENT_UNIT_ID,
            "canonical_source_id": CANONICAL_SOURCE_ID,
            "role": "parent_unit",
            "cohort_state": COHORT_SUPERSEDED_BY_RESTRUCTURE,
            "parent_state": PARENT_STATE,
            "review_status": FIRST_REVIEW_COMPLETE,
            "reviewer": REVIEWER_ID,
            "is_active": False,
            "is_propagatable": False,
            "superseded_by": list(APPROVED_UNIT_IDS),
            "supersedes": "",
            "note": (
                "sostituita da quattro unita' approvate. Lo split proposto dall'audit "
                "e' confermato; cio' che la revisione ha corretto e' il numero delle "
                "parti, non la loro esistenza"
            ),
            "historical_references_preserved": [
                "cohort_split_audit/proposed_profile_units.jsonl",
                "clinical_preclinical_review_batch/proposed_profile_units.jsonl",
                "clinical_preclinical_review_batch/source_review_PMID-22235099.json",
                "clinical_preclinical_review_batch/annotation_packets/author_approval/"
                "AA-PMID-22235099.json",
            ],
            "created_at": created_at,
            "approval_version": APPROVAL_VERSION,
        }
    ]

    for unit_id in REPLACED_PROPOSALS:
        proposal = proposals.get(unit_id, {})
        rows.append(
            {
                "profile_unit_id": unit_id,
                "canonical_source_id": CANONICAL_SOURCE_ID,
                "role": "replaced_source_checked_proposal",
                "cohort_state": proposal.get("cohort_state", "split_review_proposed"),
                "review_status": REPLACEMENT_STATUS,
                "replacement_unit": CONSOLIDATION["consolidated_unit_id"],
                "reviewer": REVIEWER_ID,
                "is_active": False,
                "is_propagatable": False,
                "superseded_by": [CONSOLIDATION["consolidated_unit_id"]],
                "supersedes": "",
                "unit_type": proposal.get("unit_type", ""),
                "unit_label": proposal.get("unit_label", ""),
                "source_locators": list(proposal.get("source_locators") or []),
                "replacement_reason": CONSOLIDATION["rationale"],
                "retained_for": (
                    "storico: la proposta conserva la lettura separata dei due sistemi, "
                    "che la consolidazione riassume ma non annulla"
                ),
                "created_at": created_at,
                "approval_version": APPROVAL_VERSION,
            }
        )

    for unit_id in RETAINED_PROPOSALS:
        proposal = proposals.get(unit_id, {})
        rows.append(
            {
                "profile_unit_id": unit_id,
                "canonical_source_id": CANONICAL_SOURCE_ID,
                "role": "promoted_source_checked_proposal",
                "cohort_state": proposal.get("cohort_state", "split_review_proposed"),
                "review_status": "superseded_by_author_approved_unit",
                "replacement_unit": unit_id,
                "reviewer": REVIEWER_ID,
                "is_active": False,
                "is_propagatable": False,
                "superseded_by": [unit_id],
                "supersedes": "",
                "unit_type": proposal.get("unit_type", ""),
                "unit_label": proposal.get("unit_label", ""),
                "source_locators": list(proposal.get("source_locators") or []),
                "retained_for": (
                    "storico: la proposta source-checked precede l'approvazione e ne "
                    "conserva lo stato di partenza"
                ),
                "created_at": created_at,
                "approval_version": APPROVAL_VERSION,
            }
        )
    return rows


def build_consolidation(created_at: str) -> list[dict[str, Any]]:
    return [
        {
            "canonical_source_id": CANONICAL_SOURCE_ID,
            "parent_profile_unit_id": PARENT_UNIT_ID,
            "reviewer_id": REVIEWER_ID,
            "reviewer_role": REVIEWER_ROLE,
            "review_method": REVIEW_METHOD,
            "author_decision": AUTHOR_DECISION,
            "source_review_proposed_units": SOURCE_REVIEW_PROPOSED_UNITS,
            "author_approved_units": AUTHOR_APPROVED_UNITS,
            "created_at": created_at,
            "approval_version": APPROVAL_VERSION,
            **dict(CONSOLIDATION),
        }
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    proposals = {
        str(row["proposed_profile_unit_id"]): row
        for row in read_jsonl(args.batch_dir / "proposed_profile_units.jsonl")
        if str(row.get("canonical_source_id")) == CANONICAL_SOURCE_ID
    }
    missing = sorted(
        unit_id
        for spec in APPROVED_UNITS
        for unit_id in spec.source_proposal_ids
        if unit_id not in proposals
    )
    if missing:
        raise ApprovalError(f"proposte source-checked mancanti: {missing}")

    units = [build_unit(spec, proposals, created_at=created_at) for spec in APPROVED_UNITS]

    violations = validate_units(units)
    if violations:
        raise ApprovalError(
            "violazioni della politica di propagazione: "
            + "; ".join(item.message for item in violations)
        )
    guard_violations = run_guards(units=units)
    if guard_violations:
        raise ApprovalError(
            "violazioni delle guardie: "
            + "; ".join(item.message for item in guard_violations)
        )

    write_jsonl(args.output / "approved_profile_units.jsonl", units)
    write_jsonl(args.output / "parent_unit_history.jsonl", build_history(created_at, proposals))
    write_jsonl(args.output / "consolidation_records.jsonl", build_consolidation(created_at))

    clinical = [row for row in units if row["is_clinical"]]
    preclinical = [row for row in units if row["is_preclinical"]]
    print(f"unita' attive: {len(units)} ({len(clinical)} cliniche, {len(preclinical)} precliniche)")
    for row in units:
        print(
            f"  {row['profile_unit_id']}: {row['unit_type']} · "
            f"{row['propagation_eligibility']} · propagabile {row['is_propagatable']} · "
            f"polarita' {row['assertion_polarity']}"
        )
    print(
        f"consolidazione: {len(REPLACED_PROPOSALS)} proposte -> 1 unita' "
        f"({CONSOLIDATION['model_instance_count']} model instances)"
    )
    print(f"proposte conservate nello storico: {SOURCE_REVIEW_PROPOSED_UNITS} + parent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
