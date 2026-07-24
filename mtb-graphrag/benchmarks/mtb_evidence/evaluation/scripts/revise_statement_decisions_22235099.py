"""Decisioni di prima revisione sugli statement, gold provvisorio, caso del rilevatore.

Nessuna delle tre decisioni cambia lo stato del candidato: la revisione
documentale aveva letto bene. Cio' che l'approvazione aggiunge e' il
**denominatore**, e senza di esso due dei tre statement erano indistinguibili da
affermazioni sulla coorte.

- `ES-V2-evidence-4288` riguarda un paziente. Resta `candidate_partial`, e la
  granularita' `case_level` gli impedisce di diventare una proprieta' di
  quattordici.
- `ES-V2-evidence-766` ne riguarda due, entrambi nominati nel locator verificato.
  `named_patient_subset` esiste per questo: `case_level` direbbe «uno» quando
  sono due, e `subgroup_level` gli darebbe un denominatore che non ha.
- `ES-V2-evidence-764` e' l'unico in cui osservazione clinica e validazione
  preclinica coesistono, e per questo l'unico in cui possono confondersi. I due
  supporti restano in campi separati: la validazione mostra resistenza in
  coltura, non risposta clinica.

Il link_status vive in `first_review_annotation` e **non** in `final_status`.
Copiarlo nel gold darebbe al linker una precision misurata contro un solo
giudizio, non indipendente e non clinico.

Il gold prodotto qui e' una versione completa e nuova: quello della fase
precedente resta invariato, e il manifest dice quale supera quale.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_manifest import content_hash  # noqa: E402
from backend.pipeline.evidence.evidence_granularity import (  # noqa: E402
    GRANULARITY_CASE,
    GRANULARITY_NAMED_PATIENT_SUBSET,
    GRANULARITY_VERSION,
    is_non_generalizable,
)
from backend.pipeline.evidence.propagation_guards import (  # noqa: E402
    GUARD_VERSION,
    GUARD_V12_RULE_IDS,
    run_guards,
)
from benchmarks.mtb_evidence.evaluation.author_approval_22235099 import (  # noqa: E402
    APPROVAL_VERSION,
    APPROVED_UNIT_IDS,
    AUDIT_PROPOSED_UNITS,
    AUTHOR_APPROVED_UNITS,
    CANDIDATE_PARTIAL_COUNT,
    CANDIDATE_VALID_COUNT,
    CANONICAL_SOURCE_ID,
    CLINICAL_UNIT_COUNT,
    CONSOLIDATION,
    DETECTOR_REFERENCE_CASE,
    ES766_DISCREPANCY,
    FORBIDDEN_STATUSES,
    H3122_KRAS,
    H3122_KRAS_ID,
    LIMITATIONS,
    PARENT_UNIT_ID,
    PRECLINICAL_UNIT_COUNT,
    REPLACED_PROPOSALS,
    RESIDUAL_RISK,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
    SOURCE_PMID,
    SOURCE_REVIEW_PROPOSED_UNITS,
    STATEMENT_REVISIONS,
    TERMINOLOGY_MAPPING,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/author_approval_22235099")
DEFAULT_PREVIOUS = Path("benchmarks/mtb_evidence/v3/author_approval")
DEFAULT_BATCH = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")

NEXT_REPORT = "SOURCE_REVIEW_PMID-23344087.md"


class GoldError(RuntimeError):
    """Il gold provvisorio viola un invariante."""


class GranularityError(RuntimeError):
    """Una decisione dichiara un denominatore che non ha."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--previous-dir", type=Path, default=DEFAULT_PREVIOUS)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def build_decisions(created_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for revision in STATEMENT_REVISIONS:
        extra = dict(revision.extra or {})
        row = {
            "statement_id": revision.statement_id,
            "canonical_source_id": CANONICAL_SOURCE_ID,
            "parent_profile_unit_id": PARENT_UNIT_ID,
            "previous_candidate_status": revision.previous_candidate_status,
            "first_review_candidate_status": revision.first_review_status,
            "first_review_link_status": revision.link_status,
            "supported_dimensions": list(revision.supported_dimensions),
            "unsupported_or_not_separable_dimensions": list(revision.unsupported_dimensions),
            "invalid_reason": revision.invalid_reason,
            "rationale": revision.rationale,
            "reviewer_id": REVIEWER_ID,
            "reviewer_role": REVIEWER_ROLE,
            "review_method": REVIEW_METHOD,
            "independent_review": False,
            "clinical_reviewer": False,
            "is_evaluable_for_final_metrics": False,
            "note": (
                "decisione di prima revisione. Non e' gold e non entra in nessuna "
                "metrica finale di linking o accordo."
            ),
            "created_at": created_at,
            "granularity_version": GRANULARITY_VERSION,
            "approval_version": APPROVAL_VERSION,
        }
        row.update(extra)
        rows.append(row)
    return rows


def check_granularity(decisions: list[dict[str, Any]]) -> None:
    """Le regole di granularita' girano sulle decisioni prima che vengano scritte.

    Non e' un controllo di forma. Una decisione puo' dichiararsi case-level e
    generalizzabile insieme, e il record resterebbe sintatticamente valido: e'
    esattamente il modo in cui un caso singolo diventa una coorte senza che nessuno
    lo abbia deciso.
    """
    violations = run_guards(decisions=decisions)
    if violations:
        raise GranularityError(
            "violazioni sulle decisioni: "
            + "; ".join(f"[{item.rule_id}] {item.message}" for item in violations)
        )


def build_case_level_annotations(created_at: str) -> list[dict[str, Any]]:
    """Le decisioni che non hanno un denominatore, isolate e motivate."""
    rows: list[dict[str, Any]] = []
    for revision in STATEMENT_REVISIONS:
        extra = dict(revision.extra or {})
        granularity = str(extra.get("evidence_granularity") or "")
        if not is_non_generalizable(granularity):
            continue
        rows.append(
            {
                "statement_id": revision.statement_id,
                "canonical_source_id": CANONICAL_SOURCE_ID,
                "profile_unit_ids": list(extra.get("profile_unit_ids") or []),
                "evidence_granularity": granularity,
                "population_scope": extra.get("population_scope"),
                "subset_size": extra.get("subset_size"),
                "cohort_size": extra.get("cohort_size"),
                "case_identifier": extra.get("case_identifier"),
                "case_identifiers": list(
                    extra.get("case_identifiers")
                    or ([extra["case_identifier"]] if extra.get("case_identifier") else [])
                ),
                "case_identifiers_verified": bool(
                    extra.get("case_identifier_verified")
                    or extra.get("case_identifiers_verified")
                ),
                "case_identifier_locators": list(extra.get("case_identifier_locators") or []),
                # Dentro un sottoinsieme nominato puo' esistere un caso ancora piu'
                # stretto: qui, il paziente per cui il meccanismo e' isolato. Senza
                # questo campo la distinzione vivrebbe solo nella prosa.
                "narrowest_case_identifier": extra.get("narrowest_case_identifier"),
                "narrowest_case_rationale": extra.get("narrowest_case_rationale", ""),
                "cohort_generalizable": extra.get("cohort_generalizable"),
                "population_level_propagation": extra.get("population_level_propagation"),
                "frequency_inference": extra.get("frequency_inference"),
                "enrolment_requirement_promotion": extra.get("enrolment_requirement_promotion"),
                "guard_rule_ids": list(GUARD_V12_RULE_IDS),
                "guard_version": GUARD_VERSION,
                "granularity_version": GRANULARITY_VERSION,
                "rationale": revision.rationale,
                "reviewer_id": REVIEWER_ID,
                "reviewer_role": REVIEWER_ROLE,
                "review_method": REVIEW_METHOD,
                "created_at": created_at,
                "approval_version": APPROVAL_VERSION,
            }
        )
    return rows


def build_negative_experiment(created_at: str) -> list[dict[str, Any]]:
    """L'esperimento negativo, registrato perche' resti negativo.

    Un risultato che non conferma nulla e' il piu' facile da perdere: non produce
    statement, non entra in nessun link, e sparirebbe senza che una metrica se ne
    accorgesse. Il record esiste per renderlo cercabile.
    """
    role = dict(H3122_KRAS.role_fields)
    return [
        {
            "profile_unit_id": H3122_KRAS_ID,
            "canonical_source_id": CANONICAL_SOURCE_ID,
            "parent_profile_unit_id": PARENT_UNIT_ID,
            "unit_type": H3122_KRAS.unit_type,
            "experiment_role": H3122_KRAS.experiment_role,
            "assertion_polarity": H3122_KRAS.assertion_polarity,
            "model": role["model"],
            "intervention": ["crizotinib"],
            "hypothesis_tested": role["hypothesis_tested"],
            "result_direction": role["result_direction"],
            "result_interpretation": role["result_interpretation"],
            "evidence_design": "preclinical in-vitro negative functional experiment",
            "cohort_generalizable": False,
            "clinical_response_observed": False,
            "must_not_be_read_as": role["must_not_be_read_as"],
            "removed_from_corpus": False,
            "visible_in_prototype": True,
            "propagation_eligibility": "prototype_only",
            "is_propagatable": False,
            "statement_ids": [],
            "source_locators": ["A-pre-kras", "A-pre-kras-negative"],
            "quote": (
                "The IC 50 of H3122 expressing KRAS G12V was not significantly "
                "different from H3122 harboring the empty vector."
            ),
            "reviewer_id": REVIEWER_ID,
            "reviewer_role": REVIEWER_ROLE,
            "review_method": REVIEW_METHOD,
            "created_at": created_at,
            "approval_version": APPROVAL_VERSION,
        }
    ]


def annotate_gold(
    gold: list[dict[str, Any]], *, created_at: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Annota i soli link fra i tre statement e la parent unit di questa fonte."""
    by_statement = {revision.statement_id: revision for revision in STATEMENT_REVISIONS}
    touched: list[str] = []
    rows: list[dict[str, Any]] = []

    for row in gold:
        revision = by_statement.get(str(row.get("statement_id")))
        if revision is None or str(row.get("profile_unit_id")) != PARENT_UNIT_ID:
            rows.append(row)
            continue

        extra = dict(revision.extra or {})
        annotated = {
            **row,
            "review_stage": "first_review_complete",
            "final_status": "provisional_first_review",
            "is_evaluable": False,
            "requires_second_review": True,
            "first_annotator": REVIEWER_ID,
            "first_review_annotation": {
                "reviewer_id": REVIEWER_ID,
                "reviewer_role": REVIEWER_ROLE,
                "review_method": REVIEW_METHOD,
                "independent_review": False,
                "clinical_reviewer": False,
                "link_status": revision.link_status,
                "candidate_status": revision.first_review_status,
                "support_type": extra.get("support_type", ""),
                "profile_unit_ids": list(extra.get("profile_unit_ids") or []),
                "evidence_granularity": extra.get("evidence_granularity", ""),
                "population_scope": extra.get("population_scope", ""),
                "cohort_generalizable": extra.get("cohort_generalizable"),
                "invalid_reason": revision.invalid_reason,
                "supported_dimensions": list(revision.supported_dimensions),
                "unsupported_or_not_separable_dimensions": list(revision.unsupported_dimensions),
                "rationale": revision.rationale,
                "reviewed_at": created_at,
            },
            "second_annotation": None,
            "second_annotator": None,
            "agreement": None,
            "adjudication": None,
            "adjudicator": None,
            "frozen_at": "",
            "profile_review_status": "first_review_complete",
            "note": (
                "prima revisione registrata. Il link_status vive in "
                "first_review_annotation e non in final_status: una prima revisione "
                "non indipendente e non clinica non puo' essere il riferimento contro "
                "cui si misura il linker."
            ),
        }
        touched.append(str(row.get("gold_link_id")))
        rows.append(annotated)

    return rows, touched


def check_gold(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        if row.get("is_evaluable"):
            raise GoldError(f"{row.get('gold_link_id')}: il gold non puo' essere valutabile")
        if row.get("final_status") in ("final", "frozen", "adjudicated"):
            raise GoldError(f"{row.get('gold_link_id')}: final_status non ammesso")
        annotation = row.get("first_review_annotation") or {}
        if annotation.get("candidate_status") and row.get("final_status") == annotation.get(
            "candidate_status"
        ):
            raise GoldError(
                f"{row.get('gold_link_id')}: lo stato del candidato e' stato copiato in "
                "final_status"
            )
        if row.get("second_annotator") is not None:
            raise GoldError(f"{row.get('gold_link_id')}: esiste un secondo annotatore")
        if row.get("agreement") is not None:
            raise GoldError(f"{row.get('gold_link_id')}: esiste un accordo dichiarato")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    decisions = build_decisions(created_at)
    check_granularity(decisions)
    write_jsonl(args.output / "statement_first_review_decisions.jsonl", decisions)

    annotations = build_case_level_annotations(created_at)
    write_jsonl(args.output / "case_level_annotations.jsonl", annotations)

    negative = build_negative_experiment(created_at)
    write_jsonl(args.output / "negative_experiment_records.jsonl", negative)

    mapping = {
        "canonical_source_id": CANONICAL_SOURCE_ID,
        "parent_profile_unit_id": PARENT_UNIT_ID,
        "reviewer_id": REVIEWER_ID,
        "reviewer_role": REVIEWER_ROLE,
        "review_method": REVIEW_METHOD,
        "first_review_status": "requires_terminology_verification",
        "created_at": created_at,
        "approval_version": APPROVAL_VERSION,
        **dict(TERMINOLOGY_MAPPING),
    }
    if mapping["mapping_status"] != "requires_terminology_verification":
        raise RuntimeError("il mapping terminologico non puo' essere promosso qui")
    write_jsonl(args.output / "terminology_mappings.jsonl", [mapping])

    previous_gold = list(read_jsonl(args.previous_dir / "provisional_gold.jsonl"))
    gold, touched = annotate_gold(previous_gold, created_at=created_at)
    if len(touched) != len(STATEMENT_REVISIONS):
        raise GoldError(
            f"annotati {len(touched)} link invece di {len(STATEMENT_REVISIONS)}: {touched}"
        )
    if len(gold) != len(previous_gold):
        raise GoldError("il gold ha cambiato numero di righe: nessuna riga va persa")
    check_gold(gold)
    write_jsonl(args.output / "provisional_gold.jsonl", gold)

    reference = {
        "canonical_source_id": CANONICAL_SOURCE_ID,
        "profile_unit_id": PARENT_UNIT_ID,
        "approved_profile_unit_ids": list(APPROVED_UNIT_IDS),
        "reviewer_id": REVIEWER_ID,
        "created_at": created_at,
        "approval_version": APPROVAL_VERSION,
        **dict(DETECTOR_REFERENCE_CASE),
    }
    if reference["detector_promoted"]:
        raise RuntimeError("il rilevatore non puo' essere promosso in questa fase")
    write_jsonl(args.output / "detector_reference_cases.jsonl", [reference])

    previous_metrics = json.loads(
        (args.previous_dir / "review_metrics.json").read_text(encoding="utf-8")
    )
    batch_units = [
        row
        for row in read_jsonl(args.batch_dir / "proposed_profile_units.jsonl")
        if str(row.get("canonical_source_id")) == CANONICAL_SOURCE_ID
    ]
    case_level = sum(
        1 for row in annotations if row["evidence_granularity"] == GRANULARITY_CASE
    )
    named_subset = sum(
        1
        for row in annotations
        if row["evidence_granularity"] == GRANULARITY_NAMED_PATIENT_SUBSET
    )

    metrics = {
        "created_at": created_at,
        "approval_version": APPROVAL_VERSION,
        "canonical_source_id": CANONICAL_SOURCE_ID,
        "metric_kind": "descriptive_first_review_metrics",
        "metric_kind_note": (
            "Contano decisioni e coperture. Nessuna misura la qualita' del sistema: "
            "esiste una sola annotazione per link, non indipendente e non clinica."
        ),
        "author_approval_packets_completed": 1,
        "first_review_sources_completed": 1,
        "first_review_statements_reviewed": len(decisions),
        "first_review_profile_units_approved": AUTHOR_APPROVED_UNITS,
        "first_review_clinical_units": CLINICAL_UNIT_COUNT,
        "first_review_preclinical_units": PRECLINICAL_UNIT_COUNT,
        "first_review_candidate_valid": CANDIDATE_VALID_COUNT,
        "first_review_candidate_partial": CANDIDATE_PARTIAL_COUNT,
        # Tenuti distinti: sommarli direbbe «tre statement su un paziente», che e'
        # falso per due di essi in modo diverso.
        "first_review_case_level_statements": case_level,
        "first_review_named_patient_subset_statements": named_subset,
        "first_review_non_generalizable_statements": len(annotations),
        "first_review_negative_experiments": len(negative),
        "first_review_units_consolidated_from": CONSOLIDATION["replaced_count"],
        "first_review_units_consolidated_to": CONSOLIDATION["resulting_count"],
        "first_review_structural_splits_confirmed": 1,
        "first_review_terminology_mappings_unverified": 1,
        "detector_reference_confirmed_positives": 1,
        "cumulative": {
            "first_review_packets_completed": (
                previous_metrics["cumulative"]["first_review_packets_completed"] + 1
            ),
            "first_review_statements_reviewed": (
                previous_metrics["cumulative"]["first_review_statements_reviewed"]
                + len(decisions)
            ),
            "first_review_profile_units_created": (
                previous_metrics["cumulative"]["first_review_profile_units_created"]
                + AUTHOR_APPROVED_UNITS
            ),
            "author_approval_packets_completed": (
                previous_metrics["author_approval_packets_completed"] + 1
            ),
        },
        # La copertura separa gli stadi perche' confonderli e' il modo piu' rapido
        # di far sembrare revisionato cio' che e' soltanto proposto.
        "coverage_by_review_stage": {
            "source_checked_proposal": len(batch_units),
            "first_review_confirmed": (
                previous_metrics["coverage_by_review_stage"]["first_review_confirmed"]
                + len(decisions)
            ),
            "second_review_confirmed": 0,
            "final_adjudicated": 0,
        },
        "qualifier_provenance_completeness": 1.0,
        "second_review_packets_completed": 0,
        "not_calculated": {
            "linking_precision": "not_calculated",
            "linking_recall": "not_calculated",
            "linking_f1": "not_calculated",
            "inter_annotator_agreement": "not_calculated",
            "detector_accuracy": "not_calculated",
            "clinical_applicability_accuracy": "not_calculated",
            "retrieval_quality": "not_calculated",
        },
        "not_calculated_reason": (
            "la prima revisione non e' indipendente e non e' clinica; nessuna seconda "
            "revisione esiste. Due casi confermati non stimano le prestazioni del "
            "rilevatore."
        ),
        "hashes": {
            "statement_decisions": content_hash(decisions),
            "case_level_annotations": content_hash(annotations),
            "negative_experiment_records": content_hash(negative),
            "terminology_mappings": content_hash([mapping]),
            "provisional_gold": content_hash(gold),
            "detector_reference_cases": content_hash([reference]),
        },
        "supersedes_gold": (
            "benchmarks/mtb_evidence/v3/author_approval/provisional_gold.jsonl"
        ),
        "annotated_gold_links": touched,
        "guard_version": GUARD_VERSION,
        "granularity_version": GRANULARITY_VERSION,
    }
    write_json(args.output / "review_metrics.json", metrics)

    blinding = json.loads(
        (args.output / "second_review_blinding_check.json").read_text(encoding="utf-8")
    )
    previous_readiness = json.loads(
        (args.previous_dir / "readiness.json").read_text(encoding="utf-8")
    )
    readiness = {
        "created_at": created_at,
        "approval_version": APPROVAL_VERSION,
        "author_approvals_completed": previous_readiness["author_approvals_completed"] + 1,
        "author_approvals_pending": previous_readiness["author_approvals_pending"] - 1,
        "clinical_preclinical_false_positives_confirmed": previous_readiness[
            "clinical_preclinical_false_positives_confirmed"
        ],
        "clinical_preclinical_true_positives_confirmed": 1,
        "negative_experiments_preserved": len(negative),
        "case_level_evidence_guard_ready": True,
        "case_level_guard_rule_ids": list(GUARD_V12_RULE_IDS),
        "detector_promotion_ready": False,
        "hard_filtering_available": False,
        "ready_for_final_evaluation": False,
        "gold_evaluable": False,
        "second_review_required": True,
        "second_review_packets_unchanged": blinding["byte_identical"],
        "previous_phase_unchanged": blinding["previous_phase_byte_identical"],
        "standard_queue_resumed": False,
        "note": (
            "La coda standard non riprende in questo branch. Il passo successivo e' "
            "l'approvazione della terza fonte del batch clinico/preclinico."
        ),
        "next_report_to_approve": NEXT_REPORT,
        "forbidden_statuses_declared": [],
        "forbidden_statuses_checked": list(FORBIDDEN_STATUSES),
        "limitations": list(LIMITATIONS),
        "residual_risk": RESIDUAL_RISK,
    }
    write_json(args.output / "readiness.json", readiness)

    manifest = {
        "created_at": created_at,
        "approval_version": APPROVAL_VERSION,
        "canonical_source_id": CANONICAL_SOURCE_ID,
        "pmid": SOURCE_PMID,
        "phase": "author_approval",
        "supersedes_phase": str(args.previous_dir).replace("\\", "/"),
        "audit_proposed_units": AUDIT_PROPOSED_UNITS,
        "source_review_proposed_units": SOURCE_REVIEW_PROPOSED_UNITS,
        "author_approved_units": AUTHOR_APPROVED_UNITS,
        "replaced_proposal_ids": list(REPLACED_PROPOSALS),
        "brief_discrepancies": [dict(ES766_DISCREPANCY)],
        "artifacts": {
            path.name: content_hash(
                list(read_jsonl(path))
                if path.suffix == ".jsonl"
                else json.loads(path.read_text(encoding="utf-8"))
            )
            for path in sorted(args.output.iterdir())
            if path.suffix in (".json", ".jsonl") and path.name != "manifest.json"
        },
    }
    write_json(args.output / "manifest.json", manifest)

    print(f"decisioni registrate: {len(decisions)}")
    for row in decisions:
        print(
            f"  {row['statement_id']}: {row['previous_candidate_status']} -> "
            f"{row['first_review_candidate_status']} · "
            f"granularita' {row.get('evidence_granularity')}"
        )
    print(f"gold annotato: {touched} su {len(gold)} righe")
    print(f"non generalizzabili: {case_level} case_level, {named_subset} named_patient_subset")
    print(f"esperimenti negativi conservati: {len(negative)}")
    print(f"mapping terminologico: {mapping['mapping_status']}")
    print(
        f"rilevatore: {reference['reference_case_type']} · promosso "
        f"{reference['detector_promoted']}"
    )
    print(f"prossimo report da approvare: {NEXT_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
