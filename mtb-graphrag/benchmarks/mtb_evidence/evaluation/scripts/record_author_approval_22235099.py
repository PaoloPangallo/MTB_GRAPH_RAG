"""Registra l'approvazione dell'autore su PMID 22235099 e la traccia di audit.

Stessa forma della fase su PMID 31358542, con una differenza che vale la pena
dire: l'output non e' la stessa directory. Gli artefatti della prima approvazione
restano dove sono, byte per byte, e questa fase scrive in una directory propria
che dichiara quale file supera quale. Riscrivere in luogo un artefatto gia'
committato farebbe sparire la sequenza delle decisioni, che e' l'unica cosa che
rende leggibile un corpus revisionato in piu' passate.

Gli hash dei 70 packet ciechi della seconda revisione sono presi prima e dopo. Se
uno solo cambia, lo script esce con errore: la seconda revisione vale solo se chi
la fa non sa che cosa ha deciso la prima.
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

from benchmarks.mtb_evidence.evaluation.author_approval_22235099 import (  # noqa: E402
    APPROVAL_VERSION,
    APPROVED_UNIT_IDS,
    AUDIT_PROPOSED_UNITS,
    AUTHOR_APPROVED_UNITS,
    AUTHOR_DECISION,
    AUTHOR_DECISIONS,
    CANONICAL_SOURCE_ID,
    CLINICAL_PRECLINICAL_SPLIT,
    CLINICAL_UNIT_COUNT,
    CONSOLIDATION,
    DECISION_RATIONALE,
    DOCUMENT_HASH,
    ES766_DISCREPANCY,
    LIMITATIONS,
    LOCATOR_COUNT,
    LOCATOR_MATCH_TYPES,
    PARENT_STATE,
    PARENT_UNIT_ID,
    PRECLINICAL_UNIT_COUNT,
    REPLACED_PROPOSALS,
    RESIDUAL_RISK,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
    SOURCE_PACKET_ID,
    SOURCE_PMC,
    SOURCE_PMID,
    SOURCE_REPORT,
    SOURCE_REVIEW_PROPOSED_UNITS,
    STATEMENT_REVISIONS,
    STRUCTURAL_DECISION,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/author_approval_22235099")
DEFAULT_BATCH = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")
DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")
DEFAULT_PREVIOUS = Path("benchmarks/mtb_evidence/v3/author_approval")
SECOND_REVIEW = Path("annotation_packets/second_review")

EXPECTED_BLIND_PACKETS = 70


class BlindingViolation(RuntimeError):
    """Un packet cieco della seconda revisione e' cambiato."""


class SourceMismatch(RuntimeError):
    """Gli artefatti source-checked non coincidono con il report approvato."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--previous-dir", type=Path, default=DEFAULT_PREVIOUS)
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
    """Il documento e i locator sono quelli su cui il report e' stato scritto?

    Il controllo precede la scrittura e non la accompagna. Approvare un report e
    poi accorgersi che l'artefatto descrive un altro documento produrrebbe una
    decisione umana attaccata alla fonte sbagliata, che e' peggio di nessuna
    decisione.
    """
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
    if access.get("pmc_id") != SOURCE_PMC:
        problems.append(f"pmc_id {access.get('pmc_id')!r} invece di {SOURCE_PMC!r}")
    if problems:
        raise SourceMismatch(
            "gli artefatti source-checked non coincidono con il report approvato: "
            + "; ".join(problems)
        )

    return {
        "document_hash": DOCUMENT_HASH,
        "locators_verified": LOCATOR_COUNT,
        "locators_not_verified": 0,
        "locator_match_type_counts": dict(LOCATOR_MATCH_TYPES),
        "locator_ids": [str(item.get("locator_id")) for item in access.get("locators") or []],
        "full_text_stored": bool(access.get("full_text_stored")),
        "availability": str(access.get("availability") or ""),
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
        # --- che cosa e' stato deciso ---------------------------------------
        "author_decision": AUTHOR_DECISION,
        "structural_decision": STRUCTURAL_DECISION,
        "clinical_preclinical_split": CLINICAL_PRECLINICAL_SPLIT,
        "audit_proposed_units": AUDIT_PROPOSED_UNITS,
        "source_review_proposed_units": SOURCE_REVIEW_PROPOSED_UNITS,
        "author_approved_units": AUTHOR_APPROVED_UNITS,
        "final_number_of_profile_units": AUTHOR_APPROVED_UNITS,
        "clinical_unit_count": CLINICAL_UNIT_COUNT,
        "preclinical_unit_count": PRECLINICAL_UNIT_COUNT,
        "parent_state": PARENT_STATE,
        "decision_rationale": DECISION_RATIONALE,
        "consolidation": dict(CONSOLIDATION),
        "replaced_proposal_ids": list(REPLACED_PROPOSALS),
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
                "target": "profile_unit_count",
                "from": SOURCE_REVIEW_PROPOSED_UNITS,
                "to": AUTHOR_APPROVED_UNITS,
                "changed": True,
            }
        ],
        "brief_discrepancies": [dict(ES766_DISCREPANCY)],
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
            "185 segnali source-level, due componenti riconosciute, due unita' proposte",
        ),
        (
            "clinical_preclinical_review_batch",
            "audit_split_confirmed_with_more_units",
            "source_checked_documentary_review",
            "il full text contiene esperimenti propri: quattro sistemi preclinici, "
            "cinque unita' proposte",
        ),
        (
            "author_approval",
            "first_review_complete",
            REVIEWER_ID,
            "approvazione con correzioni: split confermato, cinque unita' ridotte a "
            "quattro per consolidazione dei due modelli isogenici",
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
    previous = hash_directory(args.previous_dir)

    write_jsonl(
        args.output / "author_approval_records.jsonl",
        [build_record(created_at, source_check)],
    )
    write_jsonl(args.output / "audit_trail.jsonl", build_audit_trail(created_at))

    after = hash_directory(second_review_dir)
    changed = sorted(
        name for name in set(before) | set(after) if before.get(name) != after.get(name)
    )
    previous_after = hash_directory(args.previous_dir)
    previous_changed = sorted(
        name
        for name in set(previous) | set(previous_after)
        if previous.get(name) != previous_after.get(name)
    )
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
            # La fase precedente e' anch'essa un artefatto da non toccare: se
            # cambiasse, la catena delle decisioni diventerebbe irricostruibile.
            "previous_phase_directory": str(args.previous_dir).replace("\\", "/"),
            "previous_phase_byte_identical": not previous_changed,
            "previous_phase_changed_files": previous_changed,
            "previous_phase_hashes": previous_after,
            "approval_version": APPROVAL_VERSION,
        },
    )
    if changed:
        raise BlindingViolation(f"packet ciechi modificati: {changed}")
    if previous_changed:
        raise BlindingViolation(
            f"artefatti della fase precedente modificati: {previous_changed}"
        )

    print(f"approvazione registrata: {AUTHOR_DECISION} su {CANONICAL_SOURCE_ID}")
    print(f"revisore: {REVIEWER_ID} ({REVIEWER_ROLE}) · metodo: {REVIEW_METHOD}")
    print(
        f"unita': audit {AUDIT_PROPOSED_UNITS} · revisione {SOURCE_REVIEW_PROPOSED_UNITS} "
        f"· approvate {AUTHOR_APPROVED_UNITS} · split {CLINICAL_PRECLINICAL_SPLIT}"
    )
    print(f"documento: {DOCUMENT_HASH[:16]}… · locator {LOCATOR_COUNT}/{LOCATOR_COUNT} exact")
    print(f"packet ciechi invariati: {not changed} ({len(after)} file)")
    print(f"fase precedente invariata: {not previous_changed} ({len(previous_after)} file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
