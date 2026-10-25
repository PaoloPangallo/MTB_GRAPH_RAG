"""Decisioni di prima revisione sugli statement, gold provvisorio, caso del rilevatore.

Nessuna delle due decisioni cambia lo stato del candidato. Cio' che
l'approvazione aggiunge sono due distinzioni che il solo stato non porta.

`ES-V2-evidence-765` resta `candidate_partial`, e la ragione e' una differenza di
**forza**, non di direzione. L'abstract distingue due intensita' nella stessa
frase — SNU-2535 «resistant», i cloni «less sensitive» — e lo statement dice
«resistance» senza qualificatore. Non e' un conflitto: la fonte non nega la
resistenza. Ma trasformare una riduzione relativa in resistenza completa
aggiungerebbe forza che la fonte non fornisce.

`ES-V2-evidence-767` resta `candidate_ambiguous`, e non diventa
`candidate_conflicting`. La distinzione non e' di sfumatura: `conflicting` direbbe
che la fonte contraddice lo statement, e la fonte non lo contraddice. Dice meno,
in un modo preciso — l'unico paziente con copy number gain portava anche EGFR
L858R, quindi il contributo causale delle due alterazioni non e' separabile.

La regola case-level non viene riscritta: e' quella della fase PMID 22235099, e
lo script verifica che protegga anche questa decisione invece di assumerlo.

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
    GRANULARITY_VERSION,
    is_non_generalizable,
)
from backend.pipeline.evidence.propagation_guards import (  # noqa: E402
    GUARD_VERSION,
    GUARD_V12_RULE_IDS,
    run_guards,
)
from backend.pipeline.evidence.source_basis import (  # noqa: E402
    ABSTRACT_ONLY,
    NOT_SEPARABLE,
    SOURCE_BASIS_VERSION,
)
from benchmarks.mtb_evidence.evaluation.author_approval_23344087 import (  # noqa: E402
    APPROVAL_VERSION,
    APPROVED_UNIT_IDS,
    AUDIT_PROPOSED_UNITS,
    AUTHOR_APPROVED_ACTIVE_UNITS,
    CANDIDATE_AMBIGUOUS_COUNT,
    CANDIDATE_PARTIAL_COUNT,
    CANONICAL_SOURCE_ID,
    CLINICAL_UNIT_COUNT,
    DETECTOR_REFERENCE_CASE,
    FORBIDDEN_STATUSES,
    LIMITATIONS,
    PARENT_UNIT_ID,
    PRECLINICAL_PANEL_ID,
    PRECLINICAL_UNIT_COUNT,
    REJECTED_PROPOSALS,
    RESIDUAL_RISK,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
    SOURCE_BASIS_FACTS,
    SOURCE_PMID,
    SOURCE_REVIEW_PROPOSED_UNITS,
    STATEMENT_REVISIONS,
    TERMINOLOGY_MAPPINGS,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/author_approval_23344087")
DEFAULT_PREVIOUS = Path("benchmarks/mtb_evidence/v3/author_approval_22235099")
DEFAULT_BATCH = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")

# Il batch clinico/preclinico si chiude qui. Il passo successivo non e' una
# quarta approvazione: e' la rigenerazione versionata del corpus.
NEXT_STEP = "versioned_qualification_corpus_regeneration"


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
                "decisione di prima revisione su abstract. Non e' gold e non entra "
                "in nessuna metrica finale di linking o accordo."
            ),
            "created_at": created_at,
            "granularity_version": GRANULARITY_VERSION,
            "source_basis_version": SOURCE_BASIS_VERSION,
            "approval_version": APPROVAL_VERSION,
        }
        row.update(extra)
        rows.append(row)
    return rows


def check_granularity(decisions: list[dict[str, Any]]) -> None:
    """La regola della fase precedente viene eseguita, non assunta.

    Riusare una regola significa poterla vedere fallire su dati sbagliati e
    passare su questi. Dichiarare di riusarla senza eseguirla non protegge nulla.
    """
    violations = run_guards(decisions=decisions)
    if violations:
        raise GranularityError(
            "violazioni sulle decisioni: "
            + "; ".join(f"[{item.rule_id}] {item.message}" for item in violations)
        )
    protected = [
        row["statement_id"]
        for row in decisions
        if is_non_generalizable(row.get("evidence_granularity"))
    ]
    if not protected:
        raise GranularityError(
            "nessuna decisione risulta case-level: la policy non sta proteggendo niente"
        )


def build_case_level_annotations(created_at: str) -> list[dict[str, Any]]:
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
                "case_identifier_verified": bool(extra.get("case_identifier_verified")),
                "case_identifier_reason": extra.get("case_identifier_reason", ""),
                "case_identifier_locators": list(extra.get("case_identifier_locators") or []),
                "cohort_generalizable": extra.get("cohort_generalizable"),
                "population_level_propagation": extra.get("population_level_propagation"),
                "frequency_inference": extra.get("frequency_inference"),
                "enrolment_requirement_promotion": extra.get("enrolment_requirement_promotion"),
                # La policy e' quella della fase precedente: il record lo dice, cosi'
                # un lettore non deve dedurlo dal fatto che i campi combaciano.
                "policy_reused_from": "author_approval/1.1 (PMID:22235099)",
                "guard_rule_ids": list(GUARD_V12_RULE_IDS),
                "guard_version": GUARD_VERSION,
                "granularity_version": GRANULARITY_VERSION,
                "source_basis": ABSTRACT_ONLY,
                "rationale": revision.rationale,
                "reviewer_id": REVIEWER_ID,
                "reviewer_role": REVIEWER_ROLE,
                "review_method": REVIEW_METHOD,
                "created_at": created_at,
                "approval_version": APPROVAL_VERSION,
            }
        )
    return rows


def build_confounding_annotations(created_at: str) -> list[dict[str, Any]]:
    """Le decisioni in cui due meccanismi coesistono e nessuno e' isolabile.

    Distinto dal case-level, e la distinzione conta: un caso singolo ha un
    denominatore troppo piccolo, un caso confuso ha un denominatore qualunque e
    due spiegazioni. Sommarli sotto la stessa etichetta perderebbe il motivo per
    cui lo statement non e' utilizzabile.
    """
    rows: list[dict[str, Any]] = []
    for revision in STATEMENT_REVISIONS:
        extra = dict(revision.extra or {})
        if not extra.get("cooccurring_alterations"):
            continue
        rows.append(
            {
                "statement_id": revision.statement_id,
                "canonical_source_id": CANONICAL_SOURCE_ID,
                "profile_unit_ids": list(extra.get("profile_unit_ids") or []),
                "candidate_link_status": revision.first_review_status,
                "confounding_status": extra.get("confounding_status"),
                "cooccurring_alterations": list(extra.get("cooccurring_alterations") or []),
                "cooccurrence_detail": extra.get("cooccurrence_detail", ""),
                "causal_attribution": extra.get("causal_attribution"),
                "isolated_mechanism_support": extra.get("isolated_mechanism_support"),
                # I due campi che impediscono la lettura sbagliata piu' comune:
                # ambiguo non e' conflittuale.
                "assertion_conflict": extra.get("assertion_conflict"),
                "source_contradicts_statement": extra.get("source_contradicts_statement"),
                "why_not_conflicting": extra.get("why_not_conflicting", ""),
                "source_locators": list(extra.get("case_identifier_locators") or []),
                "source_basis": ABSTRACT_ONLY,
                "reviewer_id": REVIEWER_ID,
                "reviewer_role": REVIEWER_ROLE,
                "review_method": REVIEW_METHOD,
                "created_at": created_at,
                "approval_version": APPROVAL_VERSION,
            }
        )
    return rows


def build_terminology(created_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mapping in TERMINOLOGY_MAPPINGS:
        row = {
            "canonical_source_id": CANONICAL_SOURCE_ID,
            "parent_profile_unit_id": PARENT_UNIT_ID,
            "reviewer_id": REVIEWER_ID,
            "reviewer_role": REVIEWER_ROLE,
            "review_method": REVIEW_METHOD,
            "first_review_status": "requires_terminology_verification",
            "review_required": True,
            "source_basis": ABSTRACT_ONLY,
            "created_at": created_at,
            "approval_version": APPROVAL_VERSION,
            **dict(mapping),
        }
        if row["mapping_status"] != "requires_terminology_verification":
            raise RuntimeError(
                f"{row['mapping_id']}: il mapping non puo' essere promosso qui"
            )
        if row["promoted_to_verified_synonym"]:
            raise RuntimeError(f"{row['mapping_id']}: promosso a sinonimo verificato")
        rows.append(row)
    return rows


def annotate_gold(
    gold: list[dict[str, Any]], *, created_at: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Annota i soli link fra i due statement e la parent unit di questa fonte."""
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
                "assertion_conflict": extra.get("assertion_conflict"),
                "source_basis": ABSTRACT_ONLY,
                "structural_confidence": extra.get("structural_confidence", ""),
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
                "prima revisione registrata su abstract. Il link_status vive in "
                "first_review_annotation e non in final_status: una prima revisione "
                "non indipendente, non clinica e senza full text non puo' essere il "
                "riferimento contro cui si misura il linker."
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

    confounding = build_confounding_annotations(created_at)
    write_jsonl(args.output / "confounding_annotations.jsonl", confounding)

    mappings = build_terminology(created_at)
    write_jsonl(args.output / "terminology_mappings.jsonl", mappings)

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

    metrics = {
        "created_at": created_at,
        "approval_version": APPROVAL_VERSION,
        "canonical_source_id": CANONICAL_SOURCE_ID,
        "metric_kind": "descriptive_first_review_metrics",
        "metric_kind_note": (
            "Contano decisioni e coperture. Nessuna misura la qualita' del sistema: "
            "esiste una sola annotazione per link, non indipendente, non clinica e "
            "prodotta sul solo abstract."
        ),
        "source_basis": ABSTRACT_ONLY,
        "author_approval_packets_completed": 1,
        "first_review_sources_completed": 1,
        "first_review_statements_reviewed": len(decisions),
        "first_review_profile_units_approved": AUTHOR_APPROVED_ACTIVE_UNITS,
        "first_review_clinical_units": CLINICAL_UNIT_COUNT,
        "first_review_preclinical_units": PRECLINICAL_UNIT_COUNT,
        "first_review_candidate_partial": CANDIDATE_PARTIAL_COUNT,
        "first_review_candidate_ambiguous": CANDIDATE_AMBIGUOUS_COUNT,
        "first_review_case_level_statements": case_level,
        "first_review_abstract_only_sources": 1,
        "first_review_structural_splits_partially_supported": 1,
        "first_review_terminology_mappings_unverified": len(mappings),
        "first_review_confounded_statements": len(confounding),
        "first_review_unapproved_structural_hypotheses": len(REJECTED_PROPOSALS),
        "detector_reference_partial_positives": 1,
        "unresolved_preclinical_panels": 1,
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
                + AUTHOR_APPROVED_ACTIVE_UNITS
            ),
            "author_approval_packets_completed": (
                previous_metrics["cumulative"]["author_approval_packets_completed"] + 1
            ),
        },
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
            "revisione esiste. Su questa fonte non esiste nemmeno un numero corretto "
            "di unita' contro cui misurare il rilevatore: il full text non e' "
            "accessibile."
        ),
        "hashes": {
            "statement_decisions": content_hash(decisions),
            "case_level_annotations": content_hash(annotations),
            "confounding_annotations": content_hash(confounding),
            "terminology_mappings": content_hash(mappings),
            "provisional_gold": content_hash(gold),
            "detector_reference_cases": content_hash([reference]),
        },
        "supersedes_gold": (
            "benchmarks/mtb_evidence/v3/author_approval_22235099/provisional_gold.jsonl"
        ),
        "annotated_gold_links": touched,
        "guard_version": GUARD_VERSION,
        "granularity_version": GRANULARITY_VERSION,
        "source_basis_version": SOURCE_BASIS_VERSION,
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
        "clinical_preclinical_true_positives_confirmed": previous_readiness[
            "clinical_preclinical_true_positives_confirmed"
        ],
        "clinical_preclinical_partial_positives_confirmed": 1,
        "abstract_only_first_reviews": 1,
        "unresolved_preclinical_composition_count": 1,
        "negative_experiments_preserved": previous_readiness["negative_experiments_preserved"],
        "case_level_evidence_guard_ready": previous_readiness[
            "case_level_evidence_guard_ready"
        ],
        "case_level_guard_rule_ids": list(GUARD_V12_RULE_IDS),
        # Il batch si chiude: tre fonti, tre approvazioni, zero in attesa.
        "clinical_preclinical_author_approval_batch_complete": True,
        "detector_promotion_ready": False,
        "hard_filtering_available": False,
        "ready_for_final_evaluation": False,
        "gold_evaluable": False,
        "ready_for_versioned_corpus_regeneration": True,
        "second_review_required": True,
        "second_review_packets_unchanged": blinding["byte_identical"],
        "protected_phases_unchanged": blinding["protected_phases_byte_identical"],
        "standard_queue_resumed": False,
        "note": (
            "Il batch clinico/preclinico e' completo a livello di prima revisione. La "
            "coda standard non riprende in questo branch: il passo successivo e' la "
            "rigenerazione versionata del qualification corpus, con aggiornamento "
            "degli hash e nuovo snapshot fingerprint."
        ),
        "next_step": NEXT_STEP,
        "next_report_to_approve": None,
        "forbidden_statuses_declared": [],
        "forbidden_statuses_checked": list(FORBIDDEN_STATUSES),
        "limitations": list(LIMITATIONS),
        "residual_risk": RESIDUAL_RISK,
    }
    if readiness["author_approvals_pending"] != 0:
        raise RuntimeError(
            "il batch non risulta completo: restano approvazioni in attesa "
            f"({readiness['author_approvals_pending']})"
        )
    write_json(args.output / "readiness.json", readiness)

    manifest = {
        "created_at": created_at,
        "approval_version": APPROVAL_VERSION,
        "canonical_source_id": CANONICAL_SOURCE_ID,
        "pmid": SOURCE_PMID,
        "phase": "author_approval",
        "supersedes_phase": str(args.previous_dir).replace("\\", "/"),
        "source_basis": ABSTRACT_ONLY,
        "structural_confidence": SOURCE_BASIS_FACTS["structural_confidence"],
        "audit_proposed_units": AUDIT_PROPOSED_UNITS,
        "source_review_proposed_units": SOURCE_REVIEW_PROPOSED_UNITS,
        "author_approved_active_units": AUTHOR_APPROVED_ACTIVE_UNITS,
        "unapproved_structural_hypotheses": list(REJECTED_PROPOSALS),
        "preclinical_model_composition": NOT_SEPARABLE,
        "batch_complete": True,
        "next_step": NEXT_STEP,
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
            f"granularita' {row.get('evidence_granularity')} · "
            f"conflitto {row.get('assertion_conflict')}"
        )
    print(f"gold annotato: {touched} su {len(gold)} righe")
    print(f"case-level protetti: {case_level} · confusi: {len(confounding)}")
    print(f"mapping terminologici non verificati: {len(mappings)}")
    print(
        f"rilevatore: {reference['reference_case_type']} · promosso "
        f"{reference['detector_promoted']}"
    )
    print(
        f"batch completo: {readiness['clinical_preclinical_author_approval_batch_complete']} "
        f"· approvazioni in attesa: {readiness['author_approvals_pending']}"
    )
    print(f"prossimo passo: {NEXT_STEP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
