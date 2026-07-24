"""Le due unita' attive, e le tre proposte che restano leggibili.

La differenza rispetto alla fase precedente non e' il numero. La', due proposte
venivano fuse perche' dicevano la stessa cosa due volte; qui due proposte non
diventano unita' perche' l'abstract non permette di sapere se dicano cose diverse.
Il primo caso e' una consolidazione, il secondo e' una **mancata risoluzione**, e
confonderli farebbe sembrare una decisione cio' che e' un limite del documento.

Da questo discende il campo che conta piu' di tutti sull'unita' preclinica:
`preclinical_model_composition = not_separable`. Non `unknown`. I componenti sono
confermati — SNU-2535, H3122 CR1 e i cloni compaiono tutti nell'abstract — ma la
loro relazione non e' ricostruibile. `unknown` suggerirebbe che qualcuno debba
ancora cercare il valore; `not_separable` dice che il documento disponibile non
lo contiene.

Lo script rifiuta di scrivere una unita' che affermi piu' di quanto la base
documentale permetta, e verifica il livello di propagazione invece di
dichiararlo.
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
from backend.pipeline.evidence.source_basis import (  # noqa: E402
    ABSTRACT_ONLY,
    NOT_SEPARABLE,
    AbstractOnlyOverclaimError,
)
from benchmarks.mtb_evidence.evaluation.author_approval_23344087 import (  # noqa: E402
    APPROVAL_VERSION,
    APPROVED_UNIT_IDS,
    APPROVED_UNITS,
    AUTHOR_APPROVED_ACTIVE_UNITS,
    AUTHOR_DECISION,
    CANONICAL_SOURCE_ID,
    DOCUMENT_HASH,
    PARENT_STATE,
    PARENT_UNIT_ID,
    PRECLINICAL_PANEL_ID,
    PROMOTED_PROPOSALS,
    PROMOTION_STATUS,
    REJECTED_PROPOSALS,
    REJECTION_RATIONALE,
    REJECTION_STATUS,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
    SOURCE_BASIS_FACTS,
    SOURCE_REVIEW_PROPOSED_UNITS,
    STRUCTURAL_DECISION,
    ApprovedUnit,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/author_approval_23344087")
DEFAULT_BATCH = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")

# Origine dei valori che l'autore ha fissato leggendo piu' di una proposta.
AUTHOR_RESOLVED = "author_approved_unresolved_panel"

# Cio' che nessun record di questa fase puo' dichiarare: la fonte non e' stata
# letta oltre l'abstract, e un campo che dicesse il contrario renderebbe la
# prudenza registrata qui indistinguibile da una verifica reale.
FORBIDDEN_CLAIMS = (
    "full_text_verified",
    "full_text_stored",
    "clinical_reviewed",
    "independent_review",
    "is_propagatable",
    "is_hard_filterable",
    "is_evaluable",
)


class ApprovalError(RuntimeError):
    """Una unita' approvata viola un invariante della fase."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _merge_values(proposals: list[dict[str, Any]], key: str) -> Any:
    """Il valore di una dimensione quando le proposte da fondere sono piu' di una.

    Se le proposte concordano, il valore e' quello. Se divergono, fondere in
    silenzio produrrebbe un valore che nessuna delle due sosteneva: serve un
    override esplicito, e in sua assenza lo script si ferma. Su questa fonte la
    divergenza e' il caso normale — e' esattamente il motivo per cui le due
    proposte non diventano due unita'.
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
    """La provenienza di ogni proposta, piu' quella dei valori fissati dall'autore."""
    entries: list[dict[str, Any]] = []
    for proposal in proposals:
        origin = str(proposal.get("proposed_profile_unit_id") or "")
        for item in proposal.get("provenance") or []:
            if item.get("field_name") in overrides:
                continue
            entries.append({**item, "derived_from_proposal_id": origin})

    locators = sorted(
        {
            str(locator)
            for proposal in proposals
            for locator in proposal.get("source_locators") or []
        }
    )
    for field_name in overrides:
        entries.append(
            {
                "field_name": field_name,
                # Non `source_document`: il valore risolve una divergenza fra due
                # proposte, e far sembrare che una frase dell'abstract lo contenga
                # gia' sarebbe il modo piu' rapido di perdere la distinzione.
                "value_origin": AUTHOR_RESOLVED,
                "source_locator": locators[0] if locators else "",
                "access_date": review_date,
                "asserted_by": f"{REVIEWER_ID} ({REVIEW_METHOD})",
                "span_hash": "",
                "note": (
                    "valore fissato dall'autore sulle proposte "
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
    """Aggiunge alla provenienza chi ha rivisto il campo, con quale metodo e su cosa.

    `source_basis` viaggia con ogni voce e non solo sull'unita': un campo estratto
    da un abstract e uno estratto da un full text non sono la stessa asserzione, e
    la differenza deve restare leggibile alla granularita' del campo.
    """
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
            "source_basis": ABSTRACT_ONLY,
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

    field_decisions = _merge_field_decisions(sources, overrides)

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
        field_decisions=field_decisions,
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
            "la fonte e' disponibile soltanto come abstract",
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
            **dict(SOURCE_BASIS_FACTS),
            **dict(spec.role_fields),
        }
    )
    _check_claims(record)
    return record


def _merge_field_decisions(
    proposals: list[dict[str, Any]], overrides: dict[str, Any]
) -> dict[str, str]:
    """Le decisioni di campo quando le proposte non concordano.

    Dove le proposte divergono e l'autore non ha fissato un valore, la decisione
    diventa `not_separable`: due letture diverse dello stesso abstract sono la
    prova che la dimensione non e' risolvibile, non un motivo per sceglierne una.
    """
    keys = sorted({key for proposal in proposals for key in proposal.get("field_decisions") or {}})
    merged: dict[str, str] = {}
    for key in keys:
        values = {str((proposal.get("field_decisions") or {}).get(key, "")) for proposal in proposals}
        if key in overrides:
            merged[key] = "confirmed"
        elif len(values) == 1:
            merged[key] = values.pop()
        else:
            merged[key] = NOT_SEPARABLE
    return merged


def _check_claims(record: dict[str, Any]) -> None:
    for claim in FORBIDDEN_CLAIMS:
        if record.get(claim):
            raise AbstractOnlyOverclaimError(
                f"{record.get('profile_unit_id')} dichiara {claim}=true su una fonte "
                f"{ABSTRACT_ONLY}: la revisione non ha visto piu' dell'abstract"
            )


def build_history(
    created_at: str, proposals: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """La parent e le tre proposte, tutte conservate e nessuna attiva."""
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
            "source_basis": ABSTRACT_ONLY,
            "note": (
                "sostituita da due unita' attive. Lo split clinico/preclinico e' "
                "confermato; la composizione della parte preclinica non lo e', e "
                "resta dentro una sola unita' dichiarata non separabile"
            ),
            "historical_references_preserved": [
                "cohort_split_audit/proposed_profile_units.jsonl",
                "clinical_preclinical_review_batch/proposed_profile_units.jsonl",
                "clinical_preclinical_review_batch/source_review_PMID-23344087.json",
                "clinical_preclinical_review_batch/annotation_packets/author_approval/"
                "AA-PMID-23344087.json",
            ],
            "statement_candidates_preserved": ["ES-V2-evidence-765", "ES-V2-evidence-767"],
            "created_at": created_at,
            "approval_version": APPROVAL_VERSION,
        }
    ]

    for unit_id in REJECTED_PROPOSALS:
        proposal = proposals.get(unit_id, {})
        rows.append(
            {
                "profile_unit_id": unit_id,
                "canonical_source_id": CANONICAL_SOURCE_ID,
                "role": "unapproved_structural_hypothesis",
                "cohort_state": proposal.get("cohort_state", "split_review_proposed"),
                "review_status": REJECTION_STATUS,
                "replacement_unit": PRECLINICAL_PANEL_ID,
                "reviewer": REVIEWER_ID,
                "is_active": False,
                "is_propagatable": False,
                "superseded_by": [PRECLINICAL_PANEL_ID],
                "supersedes": "",
                "unit_type": proposal.get("unit_type", ""),
                "unit_label": proposal.get("unit_label", ""),
                "source_locators": list(proposal.get("source_locators") or []),
                "statement_candidates": list(proposal.get("statement_candidates") or []),
                "rejection_reason": REJECTION_RATIONALE,
                "rejected_for_lack_of_source_resolution": True,
                "rejected_as_false": False,
                "retained_for": (
                    "storico: resta una ipotesi strutturale plausibile che l'abstract "
                    "non permette ne' di confermare ne' di escludere. Il full text "
                    "potrebbe riattivarla"
                ),
                "source_basis": ABSTRACT_ONLY,
                "created_at": created_at,
                "approval_version": APPROVAL_VERSION,
            }
        )

    for unit_id in PROMOTED_PROPOSALS:
        proposal = proposals.get(unit_id, {})
        rows.append(
            {
                "profile_unit_id": unit_id,
                "canonical_source_id": CANONICAL_SOURCE_ID,
                "role": "promoted_source_checked_proposal",
                "cohort_state": proposal.get("cohort_state", "split_review_proposed"),
                "review_status": PROMOTION_STATUS,
                "replacement_unit": unit_id,
                "reviewer": REVIEWER_ID,
                "is_active": False,
                "is_propagatable": False,
                "superseded_by": [unit_id],
                "supersedes": "",
                "unit_type": proposal.get("unit_type", ""),
                "unit_label": proposal.get("unit_label", ""),
                "source_locators": list(proposal.get("source_locators") or []),
                "statement_candidates": list(proposal.get("statement_candidates") or []),
                "retained_for": (
                    "storico: la proposta source-checked precede l'approvazione e ne "
                    "conserva lo stato di partenza"
                ),
                "source_basis": ABSTRACT_ONLY,
                "created_at": created_at,
                "approval_version": APPROVAL_VERSION,
            }
        )
    return rows


def build_unresolved_records(created_at: str) -> list[dict[str, Any]]:
    """Che cosa resta irrisolto, in un record che si possa cercare.

    Un limite descritto solo in prosa non e' interrogabile: la prossima fase che
    volesse sapere quali unita' aspettano un full text dovrebbe rileggere i
    report. Questo record esiste per rispondere a quella domanda.
    """
    panel = next(spec for spec in APPROVED_UNITS if spec.profile_unit_id == PRECLINICAL_PANEL_ID)
    role = dict(panel.role_fields)
    return [
        {
            "profile_unit_id": PRECLINICAL_PANEL_ID,
            "canonical_source_id": CANONICAL_SOURCE_ID,
            "parent_profile_unit_id": PARENT_UNIT_ID,
            "unresolved_dimension": "preclinical_model_composition",
            "resolution_state": NOT_SEPARABLE,
            "model_components": list(role["model_components"]),
            "model_component_count_known": False,
            "cellular_background_of_mutant_clones": "unknown",
            "component_to_statement_mapping": NOT_SEPARABLE,
            "not_asserted": list(role["not_asserted"]),
            "rejected_hypotheses": list(REJECTED_PROPOSALS),
            "blocked_by": "source_basis=abstract_only",
            "unblock_conditions": list(role["propagation_unblock_conditions"]),
            "propagation_blocked_beyond_second_review": True,
            "is_propagatable": False,
            "reviewer_id": REVIEWER_ID,
            "reviewer_role": REVIEWER_ROLE,
            "review_method": REVIEW_METHOD,
            "created_at": created_at,
            "approval_version": APPROVAL_VERSION,
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
    if len(proposals) != SOURCE_REVIEW_PROPOSED_UNITS:
        raise ApprovalError(
            f"attese {SOURCE_REVIEW_PROPOSED_UNITS} proposte source-checked, "
            f"trovate {len(proposals)}"
        )

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
    write_jsonl(args.output / "unresolved_structure_records.jsonl", build_unresolved_records(created_at))

    clinical = [row for row in units if row["is_clinical"]]
    preclinical = [row for row in units if row["is_preclinical"]]
    print(f"unita' attive: {len(units)} ({len(clinical)} cliniche, {len(preclinical)} precliniche)")
    for row in units:
        print(
            f"  {row['profile_unit_id']}: {row['unit_type']} · "
            f"{row['propagation_eligibility']} · propagabile {row['is_propagatable']} · "
            f"base {row['source_basis']}"
        )
    print(
        f"proposte non approvate come unita' attive: {len(REJECTED_PROPOSALS)} "
        f"({', '.join(REJECTED_PROPOSALS)})"
    )
    print(f"composizione preclinica: {NOT_SEPARABLE}")
    print(f"unita' attive attese: {AUTHOR_APPROVED_ACTIVE_UNITS} · trovate: {len(units)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
