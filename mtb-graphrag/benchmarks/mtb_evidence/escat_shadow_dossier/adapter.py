from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from benchmarks.mtb_evidence.escat_curation_mvp.models import (
    ASSESSMENT_STATUSES,
    EscatAssessmentRecord,
    EscatRuleSet,
)
from benchmarks.mtb_evidence.escat_curation_mvp.validation import validate_assessment


PRESENTATION_STATUSES = frozenset(
    {
        "NOT_ASSESSED",
        "INCOMPLETE",
        "READY_FOR_REVIEW",
        "CURATED",
        "REJECTED",
        "CONFLICTING_EVIDENCE",
        "NOT_APPLICABLE",
        "SUPERSEDED",
    }
)
PILOT_PATH = Path(__file__).resolve().parents[1] / "escat_curation_mvp" / "data" / "pilot_drafts.jsonl"
QUALIFIED_CLAIM_ROOT = (
    Path(__file__).resolve().parents[3]
    / "backend"
    / "pipeline"
    / "evidence"
    / "corpus"
    / "v3"
    / "qualified_claim_repository_1_4"
)


@dataclass(frozen=True)
class AssessmentResolution:
    claim_id: str
    current: EscatAssessmentRecord | None
    current_ids: tuple[str, ...]
    superseded_ids: tuple[str, ...]
    claim_missing: bool = False

    @property
    def is_conflicting(self) -> bool:
        return len(self.current_ids) > 1


def _record(value: EscatAssessmentRecord | dict[str, Any]) -> EscatAssessmentRecord:
    if isinstance(value, EscatAssessmentRecord):
        return value
    if "assessment" in value:
        return EscatAssessmentRecord.from_dict(value["assessment"])
    return EscatAssessmentRecord.from_dict(value)


def resolve_assessment(
    claim_id: str,
    assessments: Iterable[EscatAssessmentRecord | dict[str, Any]],
    *,
    known_claim_ids: set[str] | frozenset[str] | None = None,
) -> AssessmentResolution:
    """Resolve only records whose stored claim_id exactly equals claim_id."""

    if known_claim_ids is not None and claim_id not in known_claim_ids:
        return AssessmentResolution(claim_id, None, (), (), claim_missing=True)
    matching = [_record(item) for item in assessments if _record(item).claim_id == claim_id]
    superseded = tuple(item.assessment_id for item in matching if item.assessment_status == "SUPERSEDED")
    current = tuple(item for item in matching if item.assessment_status != "SUPERSEDED")
    current_ids = tuple(item.assessment_id for item in current)
    return AssessmentResolution(
        claim_id=claim_id,
        current=current[0] if len(current) == 1 else None,
        current_ids=current_ids,
        superseded_ids=superseded,
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _ruleset_status(ruleset: EscatRuleSet | None, explicit: str | None) -> str:
    if explicit:
        return explicit
    if ruleset:
        return ruleset.status
    return "RESEARCH_DRAFT"


def _base_block(ruleset_status: str) -> dict[str, Any]:
    return {
        "framework": "ESCAT",
        "framework_version": None,
        "status": "NOT_ASSESSED",
        "tier": None,
        "subtier": None,
        "origin": None,
        "ruleset_status": ruleset_status,
        "assessment_id": None,
        "rule_ids": [],
        "candidate_rule_ids": [],
        "supporting_sources": [],
        "supporting_passages": [],
        "missing_requirements": [],
        "manual_review_required": True,
        "curator": None,
        "curated_at": None,
        "notes": [],
    }


def present_assessment(
    claim_id: str,
    assessments: Iterable[EscatAssessmentRecord | dict[str, Any]],
    *,
    ruleset: EscatRuleSet | None = None,
    ruleset_status: str | None = None,
    known_claim_ids: set[str] | frozenset[str] | None = None,
    candidate_rule_ids: list[str] | None = None,
) -> dict[str, Any]:
    status = _ruleset_status(ruleset, ruleset_status)
    block = _base_block(status)
    resolution = resolve_assessment(claim_id, assessments, known_claim_ids=known_claim_ids)
    if candidate_rule_ids:
        block["candidate_rule_ids"] = list(candidate_rule_ids)
    if resolution.claim_missing:
        block["notes"].append("CLAIM_NOT_FOUND")
        return block
    if resolution.is_conflicting:
        block["status"] = "CONFLICTING_EVIDENCE"
        block["notes"].extend(
            ["CONCURRENT_ASSESSMENTS", *[f"CONCURRENT_ASSESSMENT:{item}" for item in resolution.current_ids]]
        )
        if resolution.superseded_ids:
            block["notes"].append("SUPERSEDED_HISTORY_PRESENT")
        return block
    record = resolution.current
    if record is None:
        if resolution.superseded_ids:
            block["notes"].append("SUPERSEDED_ASSESSMENT_NOT_CURRENT")
        return block

    display_status = "INCOMPLETE" if record.assessment_status == "DRAFT" else record.assessment_status
    block.update(
        {
            "framework_version": record.framework_version,
            "status": display_status,
            "tier": record.tier,
            "subtier": record.subtier,
            "origin": record.assessment_origin,
            "assessment_id": record.assessment_id,
            "rule_ids": list(record.rule_ids),
            "supporting_sources": copy.deepcopy(record.supporting_sources),
            "supporting_passages": copy.deepcopy(record.supporting_passages),
            "missing_requirements": list(record.missing_requirements),
            "curator": record.curator,
            "curated_at": _iso(record.curated_at),
        }
    )
    if record.assessment_status == "DRAFT":
        block["notes"].append("DRAFT_PRESENTED_AS_INCOMPLETE")
    if status == "RESEARCH_DRAFT":
        block["notes"].append("RESEARCH_DRAFT_NOT_CLINICALLY_VALIDATED")
        if record.assessment_status == "INCOMPLETE" and not block["missing_requirements"]:
            block["missing_requirements"].append("RESEARCH_RULESET_NOT_CLINICALLY_VALIDATED")
        block["manual_review_required"] = True
    if status == "TEST_FIXTURE_ONLY":
        block["notes"].extend(["TEST_FIXTURE_ONLY", "NOT_A_CLINICAL_ESCAT_ASSESSMENT"])
        block["manual_review_required"] = True
    if record.assessment_status == "CURATED":
        result = validate_assessment(record, ruleset or EscatRuleSet())
        if not result.valid:
            block["tier"] = None
            block["subtier"] = None
            block["notes"].append("CURATED_ASSESSMENT_NOT_FORMALLY_VALID")
            block["notes"].extend(result.errors)
            block["manual_review_required"] = True
        else:
            block["manual_review_required"] = status != "OFFICIAL_RULESET_AVAILABLE"
    if record.assessment_status not in ASSESSMENT_STATUSES:
        block["status"] = "NOT_ASSESSED"
        block["notes"].append("UNSUPPORTED_ASSESSMENT_STATUS")
    return block


def build_shadow_dossier(
    claim_id: str,
    *,
    claim_relevance: dict[str, Any],
    claim_sources: list[dict[str, Any]],
    rule_sources: list[dict[str, Any]] | None = None,
    document_support: dict[str, Any],
    assessments: Iterable[EscatAssessmentRecord | dict[str, Any]],
    known_claim_ids: set[str] | frozenset[str] | None = None,
    ruleset: EscatRuleSet | None = None,
    ruleset_status: str | None = None,
    candidate_rule_ids: list[str] | None = None,
    retrieval_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append actionability to a copied dossier without changing V3 fields."""

    actionability = present_assessment(
        claim_id,
        assessments,
        ruleset=ruleset,
        ruleset_status=ruleset_status,
        known_claim_ids=known_claim_ids,
        candidate_rule_ids=candidate_rule_ids,
    )
    dossier: dict[str, Any] = {
        "claim_relevance": copy.deepcopy(claim_relevance),
        "provenance": {
            "claim_sources": copy.deepcopy(claim_sources),
            "rule_sources": copy.deepcopy(rule_sources or []),
        },
        "assessment_supporting_sources": copy.deepcopy(actionability["supporting_sources"]),
        "supporting_passages": copy.deepcopy(actionability["supporting_passages"]),
        "document_support": copy.deepcopy(document_support),
        "clinical_actionability": actionability,
    }
    if retrieval_context:
        for key, value in retrieval_context.items():
            dossier[key] = copy.deepcopy(value)
    return dossier


def _active_claim_ids() -> set[str]:
    result: set[str] = set()
    for name in ("therapeutic_claims.jsonl", "diagnostic_claims.jsonl"):
        path = QUALIFIED_CLAIM_ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if not value.get("deprecated", False):
                    result.add(str(value["claim_id"]))
    return result


def load_pilot_preview() -> dict[str, Any]:
    rows = [json.loads(line) for line in PILOT_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    assessments = [row["assessment"] for row in rows]
    pilot = []
    for row in rows:
        assessment = row["assessment"]
        pilot.append(
            {
                "claim_id": assessment["claim_id"],
                "assessment_id": assessment["assessment_id"],
                "clinical_actionability": present_assessment(
                    assessment["claim_id"], assessments, ruleset_status="RESEARCH_DRAFT"
                ),
            }
        )
    state_counts: dict[str, int] = {}
    for item in pilot:
        status = item["clinical_actionability"]["status"]
        state_counts[status] = state_counts.get(status, 0) + 1
    return {
        "preview_mode": "OFFLINE_READ_ONLY",
        "ruleset_status": "RESEARCH_DRAFT",
        "automatic_assignment": False,
        "pilot_draft_count": len(pilot),
        "assigned_tier_count": sum(item["clinical_actionability"]["tier"] is not None for item in pilot),
        "assigned_subtier_count": sum(item["clinical_actionability"]["subtier"] is not None for item in pilot),
        "state_counts": state_counts,
        "pilot_drafts": pilot,
    }
