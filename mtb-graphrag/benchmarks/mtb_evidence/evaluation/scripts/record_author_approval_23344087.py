"""Registra l'approvazione dell'autore su PMID 23344087 e la traccia di audit.

Terza fase del batch, e la prima su una fonte disponibile soltanto come abstract.
La verifica preliminare e' quindi piu' lunga di quella delle due precedenti: oltre
a hash e locator controlla che la fonte sia **davvero** `abstract_only`, che il
full text non sia conservato, e che la dichiarazione di indisponibilita' di
Europe PMC sia presente negli artefatti source-checked.

Il controllo non e' burocratico. `abstract_only` e' la ragione per cui due delle
tre unita' proposte non vengono attivate: se l'artefatto dicesse `full_text`, la
decisione sarebbe basata su un presupposto falso e la prudenza registrata qui
sarebbe ingiustificata.

Gli hash dei 70 packet ciechi e delle fasi gia' approvate sono presi prima e
dopo. Se uno solo cambia, lo script esce con errore.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.source_basis import ABSTRACT_ONLY  # noqa: E402
from benchmarks.mtb_evidence.evaluation.author_approval_23344087 import (  # noqa: E402
    APPROVAL_VERSION,
    APPROVED_UNIT_IDS,
    AUDIT_PROPOSED_UNITS,
    AUTHOR_APPROVED_ACTIVE_UNITS,
    AUTHOR_DECISION,
    AUTHOR_DECISIONS,
    CANONICAL_SOURCE_ID,
    CLINICAL_PRECLINICAL_SPLIT,
    CLINICAL_UNIT_COUNT,
    DECISION_RATIONALE,
    DOCUMENT_HASH,
    FULL_TEXT_ACCESS,
    LIMITATIONS,
    LOCATOR_COUNT,
    LOCATOR_MATCH_TYPES,
    PARENT_STATE,
    PARENT_UNIT_ID,
    PRECLINICAL_UNIT_COUNT,
    REJECTED_PROPOSALS,
    REJECTION_RATIONALE,
    RESIDUAL_RISK,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
    SOURCE_BASIS_FACTS,
    SOURCE_PACKET_ID,
    SOURCE_PMC,
    SOURCE_PMID,
    SOURCE_REPORT,
    SOURCE_REVIEW_PROPOSED_UNITS,
    SOURCE_TITLE,
    STATEMENT_REVISIONS,
    STRUCTURAL_DECISION,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/author_approval_23344087")
DEFAULT_BATCH = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")
DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")
SECOND_REVIEW = Path("annotation_packets/second_review")

# Le fasi gia' approvate. Un artefatto committato non cambia perche' una fase
# successiva ha deciso qualcosa: la sequenza delle decisioni e' l'unica cosa che
# rende leggibile un corpus revisionato in piu' passate.
PROTECTED_PHASES = (
    Path("benchmarks/mtb_evidence/v3/author_approval"),
    Path("benchmarks/mtb_evidence/v3/author_approval_22235099"),
    Path("benchmarks/mtb_evidence/v3/first_review"),
)

EXPECTED_BLIND_PACKETS = 70

# Frammento che la dichiarazione di indisponibilita' deve contenere. Cercarlo e'
# piu' robusto che confrontare la stringa intera, che porta virgolette tipografiche.
SUBSCRIPTION_MARKER = "Subscription required"


class BlindingViolation(RuntimeError):
    """Un packet cieco, o un artefatto gia' approvato, e' cambiato."""


class SourceMismatch(RuntimeError):
    """Gli artefatti source-checked non coincidono con il report approvato."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def hash_directory(directory: Path) -> dict[str, str]:
    if not directory.is_dir():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def verify_source(batch_dir: Path) -> dict[str, Any]:
    """Hash, locator, e la prova che la fonte sia davvero soltanto un abstract."""
    rows = {
        str(row.get("profile_unit_id")): row
        for row in read_jsonl(batch_dir / "source_access_verification.jsonl")
    }
    access = rows.get(PARENT_UNIT_ID)
    if access is None:
        raise SourceMismatch(f"nessuna verifica di accesso per {PARENT_UNIT_ID}")

    problems: list[str] = []
    if access.get("document_hash") != DOCUMENT_HASH:
        problems.append(
            f"document_hash {access.get('document_hash')!r} invece di {DOCUMENT_HASH!r}"
        )
    if access.get("stored_abstract_hash") != DOCUMENT_HASH:
        problems.append(
            f"stored_abstract_hash {access.get('stored_abstract_hash')!r} invece di "
            f"{DOCUMENT_HASH!r}"
        )
    if not access.get("abstract_hash_matches"):
        problems.append("abstract_hash_matches non e' vero")
    if int(access.get("locators_verified") or 0) != LOCATOR_COUNT:
        problems.append(
            f"locator verificati {access.get('locators_verified')} invece di {LOCATOR_COUNT}"
        )
    if int(access.get("locators_not_verified") or 0) != 0:
        problems.append(f"locator non verificati: {access.get('locators_not_verified')}")
    if dict(access.get("match_type_counts") or {}) != dict(LOCATOR_MATCH_TYPES):
        problems.append(
            f"match_type_counts {access.get('match_type_counts')!r} invece di "
            f"{dict(LOCATOR_MATCH_TYPES)!r}"
        )

    # --- la fonte e' davvero soltanto un abstract? --------------------------
    if access.get("availability") != ABSTRACT_ONLY:
        problems.append(
            f"availability {access.get('availability')!r} invece di {ABSTRACT_ONLY!r}"
        )
    if access.get("full_text_stored"):
        problems.append("full_text_stored e' vero: la fonte non sarebbe abstract_only")
    if access.get("full_text_redistributed"):
        problems.append("full_text_redistributed e' vero")
    if str(access.get("pmc_id") or ""):
        problems.append(
            f"pmc_id {access.get('pmc_id')!r} presente: la fonte sarebbe in PMC"
        )
    declarations = [str(item) for item in access.get("limitations") or []]
    if not any(SUBSCRIPTION_MARKER in item for item in declarations):
        problems.append(
            f"nessuna limitazione dichiara {SUBSCRIPTION_MARKER!r}: la "
            "indisponibilita' del full text non e' documentata"
        )

    if problems:
        raise SourceMismatch(
            "gli artefatti source-checked non coincidono con il report approvato: "
            + "; ".join(problems)
        )

    return {
        "document_hash": DOCUMENT_HASH,
        "abstract_hash": DOCUMENT_HASH,
        "abstract_hash_matches": True,
        "locators_verified": LOCATOR_COUNT,
        "locators_not_verified": 0,
        "locator_match_type_counts": dict(LOCATOR_MATCH_TYPES),
        "locator_ids": [str(item.get("locator_id")) for item in access.get("locators") or []],
        "availability": ABSTRACT_ONLY,
        "full_text_stored": False,
        "pmc_id": "",
        "source_declarations": declarations,
        "verified_against": "source_access_verification.jsonl",
    }


def build_record(created_at: str, source_check: dict[str, Any]) -> dict[str, Any]:
    if AUTHOR_DECISION not in AUTHOR_DECISIONS:
        raise RuntimeError(f"decisione non ammessa: {AUTHOR_DECISION!r}")
    return {
        "approval_id": f"AP-PMID-{SOURCE_PMID}",
        "canonical_source_id": CANONICAL_SOURCE_ID,
        "pmid": SOURCE_PMID,
        "pmc_id": SOURCE_PMC,
        "title": SOURCE_TITLE,
        "parent_profile_unit_id": PARENT_UNIT_ID,
        "approved_profile_unit_ids": list(APPROVED_UNIT_IDS),
        "source_packet_id": SOURCE_PACKET_ID,
        "source_report": SOURCE_REPORT,
        # --- chi ha deciso, e con quale autorita' ---------------------------
        "reviewer_id": REVIEWER_ID,
        "reviewer_role": REVIEWER_ROLE,
        "review_method": REVIEW_METHOD,
        "independent_review": False,
        "clinical_reviewer": False,
        "clinical_reviewed": False,
        "review_status": "first_review_complete",
        "human_reviewed": True,
        "requires_second_independent_review": True,
        "is_evaluable_for_final_metrics": False,
        # --- su quanto documento ---------------------------------------------
        **dict(SOURCE_BASIS_FACTS),
        "full_text_access": dict(FULL_TEXT_ACCESS),
        # --- che cosa e' stato deciso ---------------------------------------
        "author_decision": AUTHOR_DECISION,
        "structural_decision": STRUCTURAL_DECISION,
        "clinical_preclinical_split": CLINICAL_PRECLINICAL_SPLIT,
        "audit_proposed_units": AUDIT_PROPOSED_UNITS,
        "source_review_proposed_units": SOURCE_REVIEW_PROPOSED_UNITS,
        "author_approved_active_units": AUTHOR_APPROVED_ACTIVE_UNITS,
        "final_number_of_active_profile_units": AUTHOR_APPROVED_ACTIVE_UNITS,
        "clinical_unit_count": CLINICAL_UNIT_COUNT,
        "preclinical_unit_count": PRECLINICAL_UNIT_COUNT,
        "parent_state": PARENT_STATE,
        "decision_rationale": DECISION_RATIONALE,
        "rejected_proposal_ids": list(REJECTED_PROPOSALS),
        "rejection_rationale": REJECTION_RATIONALE,
        "corrections": [
            {
                "target": revision.statement_id,
                "from": revision.previous_candidate_status,
                "to": revision.first_review_status,
                "changed": revision.previous_candidate_status != revision.first_review_status,
            }
            for revision in STATEMENT_REVISIONS
        ]
        + [
            {
                "target": "active_profile_unit_count",
                "from": SOURCE_REVIEW_PROPOSED_UNITS,
                "to": AUTHOR_APPROVED_ACTIVE_UNITS,
                "changed": True,
            }
        ],
        "source_check": source_check,
        "limitations": list(LIMITATIONS),
        "residual_risk": RESIDUAL_RISK,
        "reviewed_at": created_at,
        "created_at": created_at,
        "approval_version": APPROVAL_VERSION,
    }


def build_audit_trail(created_at: str) -> list[dict[str, Any]]:
    """La sequenza degli stati attraversati dalla fonte, con chi li ha decisi."""
    steps = (
        (
            "priority_curation",
            "cohort_partially_resolved",
            "automatic",
            "la coorte non era risolvibile con i soli statement",
        ),
        (
            "cohort_split_audit",
            "clinical_preclinical_split_required",
            "automatic",
            "un solo segnale «in vitro», ma nei metodi dell'abstract: due unita' proposte",
        ),
        (
            "clinical_preclinical_review_batch",
            "audit_split_partially_supported",
            "source_checked_documentary_review",
            "l'abstract conferma le due componenti; la composizione della parte "
            "preclinica resta indeterminata. Tre unita' proposte",
        ),
        (
            "author_approval",
            "first_review_complete",
            REVIEWER_ID,
            "approvazione con correzioni: split confermato, due unita' attive. Le "
            "due proposte precliniche separate restano ipotesi non approvate",
        ),
    )
    return [
        {
            "sequence": index,
            "phase": phase,
            "state": state,
            "decided_by": decided_by,
            "is_human_decision": decided_by == REVIEWER_ID,
            "rationale": rationale,
            "canonical_source_id": CANONICAL_SOURCE_ID,
            "parent_profile_unit_id": PARENT_UNIT_ID,
            "source_basis": ABSTRACT_ONLY,
            "created_at": created_at,
            "approval_version": APPROVAL_VERSION,
        }
        for index, (phase, state, decided_by, rationale) in enumerate(steps, start=1)
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    source_check = verify_source(args.batch_dir)

    second_review_dir = args.curation_dir / SECOND_REVIEW
    before = hash_directory(second_review_dir)
    if len(before) != EXPECTED_BLIND_PACKETS:
        raise BlindingViolation(
            f"attesi {EXPECTED_BLIND_PACKETS} packet ciechi, trovati {len(before)}"
        )
    protected_before = {
        str(phase).replace("\\", "/"): hash_directory(phase) for phase in PROTECTED_PHASES
    }

    write_jsonl(
        args.output / "author_approval_records.jsonl",
        [build_record(created_at, source_check)],
    )
    write_jsonl(args.output / "audit_trail.jsonl", build_audit_trail(created_at))

    after = hash_directory(second_review_dir)
    changed = sorted(
        name for name in set(before) | set(after) if before.get(name) != after.get(name)
    )
    protected_after = {
        str(phase).replace("\\", "/"): hash_directory(phase) for phase in PROTECTED_PHASES
    }
    protected_changed = {
        phase: sorted(
            name
            for name in set(protected_before[phase]) | set(protected_after[phase])
            if protected_before[phase].get(name) != protected_after[phase].get(name)
        )
        for phase in protected_before
    }
    protected_violations = {
        phase: names for phase, names in protected_changed.items() if names
    }

    write_json(
        args.output / "second_review_blinding_check.json",
        {
            "created_at": created_at,
            "directory": str(SECOND_REVIEW).replace("\\", "/"),
            "file_count_before": len(before),
            "file_count_after": len(after),
            "expected_file_count": EXPECTED_BLIND_PACKETS,
            "byte_identical": not changed,
            "changed_files": changed,
            "hashes_before": before,
            "hashes_after": after,
            "protected_phases": sorted(protected_after),
            "protected_phases_byte_identical": not protected_violations,
            "protected_phases_changed_files": protected_violations,
            "protected_phase_hashes": protected_after,
            "approval_version": APPROVAL_VERSION,
        },
    )
    if changed:
        raise BlindingViolation(f"packet ciechi modificati: {changed}")
    if protected_violations:
        raise BlindingViolation(f"fasi gia' approvate modificate: {protected_violations}")

    print(f"approvazione registrata: {AUTHOR_DECISION} su {CANONICAL_SOURCE_ID}")
    print(f"revisore: {REVIEWER_ID} ({REVIEWER_ROLE}) · metodo: {REVIEW_METHOD}")
    print(
        f"base documentale: {ABSTRACT_ONLY} · confidenza strutturale "
        f"{SOURCE_BASIS_FACTS['structural_confidence']} · full text verificato "
        f"{SOURCE_BASIS_FACTS['full_text_verified']}"
    )
    print(f"abstract: {DOCUMENT_HASH[:16]}… · locator {LOCATOR_COUNT}/{LOCATOR_COUNT} exact")
    print(
        f"unita': audit {AUDIT_PROPOSED_UNITS} · revisione {SOURCE_REVIEW_PROPOSED_UNITS} "
        f"· attive {AUTHOR_APPROVED_ACTIVE_UNITS} · split {CLINICAL_PRECLINICAL_SPLIT}"
    )
    print(f"packet ciechi invariati: {not changed} ({len(after)} file)")
    for phase, hashes in sorted(protected_after.items()):
        print(f"  fase protetta invariata: {phase} ({len(hashes)} file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
