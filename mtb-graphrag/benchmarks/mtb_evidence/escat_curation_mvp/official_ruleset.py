from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RULESET_DIR = Path(__file__).resolve().parent / "rulesets" / "ESCAT_2018_MATEO_RESEARCH_DRAFT_v1"
RULESET_PATH = RULESET_DIR / "ruleset.json"
PILOT_DRAFTS_PATH = Path(__file__).resolve().parent / "data" / "pilot_drafts.jsonl"
SOURCE_PATH = Path(__file__).resolve().parents[3].parent / "Mateo.pdf"
EXPECTED_SOURCE_SHA256 = "56660fd9c3d929a3f2e2744ca3b53687cff0954f609e65d267c1bb3b94c3c910"


@dataclass(frozen=True)
class SourceVerification:
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ResearchRule:
    rule_id: str
    tier: str
    subtier: str | None
    label: str
    requirements: list[dict[str, Any]]
    source_locators: list[dict[str, Any]]
    clinical_value_class: str | None
    clinical_implication: str | None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ResearchRule":
        return cls(
            rule_id=value["rule_id"],
            tier=value["tier"],
            subtier=value.get("subtier"),
            label=value["label"],
            requirements=list(value.get("requirements", [])),
            source_locators=list(value.get("source_locators", [])),
            clinical_value_class=value.get("clinical_value_class"),
            clinical_implication=value.get("clinical_implication"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "tier": self.tier,
            "subtier": self.subtier,
            "label": self.label,
            "requirements": self.requirements,
            "source_locators": self.source_locators,
            "clinical_value_class": self.clinical_value_class,
            "clinical_implication": self.clinical_implication,
        }


@dataclass(frozen=True)
class ResearchRuleSet:
    framework: str
    version: str
    status: str
    classification: str
    source: dict[str, Any]
    rules: list[ResearchRule]
    ambiguity_registry_path: str

    @property
    def available(self) -> bool:
        return False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ResearchRuleSet":
        registry = Path(value["ambiguity_registry_path"])
        if not registry.is_absolute():
            registry = RULESET_DIR / registry
        return cls(
            framework=value["framework"],
            version=value["version"],
            status=value["status"],
            classification=value["classification"],
            source=dict(value["source"]),
            rules=[ResearchRule.from_dict(item) for item in value.get("rules", [])],
            ambiguity_registry_path=str(registry),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework": self.framework,
            "version": self.version,
            "status": self.status,
            "classification": self.classification,
            "source": self.source,
            "rules": [rule.to_dict() for rule in self.rules],
            "ambiguity_registry_path": self.ambiguity_registry_path,
        }


def verify_source(path: Path | None = None) -> SourceVerification:
    source = path or SOURCE_PATH
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return SourceVerification(path=str(source), sha256=digest, size_bytes=source.stat().st_size)


def load_research_ruleset(path: Path | None = None) -> ResearchRuleSet:
    ruleset = ResearchRuleSet.from_dict(json.loads((path or RULESET_PATH).read_text(encoding="utf-8")))
    verification = verify_source()
    if ruleset.source.get("sha256") != verification.sha256:
        raise ValueError("SOURCE_HASH_MISMATCH")
    if ruleset.status != "RESEARCH_DRAFT" or ruleset.classification != "RESEARCH_DRAFT":
        raise ValueError("RULESET_MUST_BE_RESEARCH_DRAFT")
    return ruleset


def compare_pilot_drafts_read_only(
    drafts_path: Path | None = None,
    ruleset: ResearchRuleSet | None = None,
) -> dict[str, Any]:
    loaded_ruleset = ruleset or load_research_ruleset()
    path = drafts_path or PILOT_DRAFTS_PATH
    drafts = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    comparisons: list[dict[str, Any]] = []
    for item in drafts:
        assessment = item["assessment"]
        comparisons.append(
            {
                "assessment_id": assessment["assessment_id"],
                "claim_id": assessment["claim_id"],
                "assessment_status": assessment["assessment_status"],
                "tier_before": assessment.get("tier"),
                "subtier_before": assessment.get("subtier"),
                "assigned_tier": None,
                "assigned_subtier": None,
                "selected_rule_ids": [],
                "candidate_rule_status": "HUMAN_REVIEW_REQUIRED",
                "candidate_rule_basis": "Read-only comparison; no automatic rule selection",
                "missing_requirements": list(assessment.get("missing_requirements", [])),
                "ruleset_version_seen": loaded_ruleset.version,
            }
        )
    return {
        "comparison_mode": "READ_ONLY",
        "automatic_assignment": False,
        "ruleset_status": loaded_ruleset.status,
        "draft_count": len(comparisons),
        "drafts": comparisons,
    }
