from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, ClassVar


ASSESSMENT_STATUSES = frozenset(
    {
        "DRAFT",
        "INCOMPLETE",
        "READY_FOR_REVIEW",
        "CURATED",
        "REJECTED",
        "CONFLICTING_EVIDENCE",
        "NOT_APPLICABLE",
        "SUPERSEDED",
    }
)
ASSESSMENT_ORIGINS = frozenset(
    {"EXPLICIT_SOURCE", "LEGACY_DERIVED", "RULE_DERIVED", "MANUAL_REVIEW", "UNKNOWN"}
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _datetime_to_json(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _datetime_from_json(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class EscatFrameworkReference:
    framework: str = "ESCAT"
    version: str | None = None
    citation: str | None = None
    doi: str | None = None
    pmid: str | None = None
    locator: str | None = None
    source_path: str | None = None
    valid_from: str | None = None

    @property
    def available(self) -> bool:
        return bool(
            self.framework == "ESCAT"
            and self.version
            and self.citation
            and (self.doi or self.pmid or self.source_path)
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "EscatFrameworkReference":
        return cls(**(value or {}))


@dataclass(frozen=True)
class EscatRule:
    rule_id: str
    framework_version: str
    tier: str
    subtier: str | None = None
    requirements: list[str] = field(default_factory=list)
    source: EscatFrameworkReference = field(default_factory=EscatFrameworkReference)
    notes: str | None = None
    required_fields: list[str] = field(default_factory=list)
    required_conditions: list[dict[str, Any]] = field(default_factory=list)
    exclusion_conditions: list[dict[str, Any]] = field(default_factory=list)
    alternative_conditions: list[dict[str, Any]] = field(default_factory=list)
    subtier_requirements: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.required_fields and self.requirements:
            object.__setattr__(self, "required_fields", list(self.requirements))

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["source"] = self.source.to_dict()
        value["requirements"] = list(self.required_fields or self.requirements)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EscatRule":
        data = dict(value)
        data["source"] = EscatFrameworkReference.from_dict(data.get("source"))
        if "required_fields" not in data:
            data["required_fields"] = list(data.get("requirements", []))
        return cls(**data)


@dataclass
class EscatRuleSet:
    framework: str = "ESCAT"
    version: str | None = None
    reference: EscatFrameworkReference = field(default_factory=EscatFrameworkReference)
    rules: list[EscatRule] = field(default_factory=list)
    status: str = "OFFICIAL_RULESET_NOT_AVAILABLE"

    @property
    def is_test_fixture(self) -> bool:
        return self.status == "TEST_FIXTURE_ONLY"

    @property
    def available(self) -> bool:
        return bool(
            self.status == "OFFICIAL_RULESET_AVAILABLE"
            and self.framework == "ESCAT"
            and self.version
            and self.reference.available
            and self.rules
        )

    @property
    def structurally_available(self) -> bool:
        return bool(
            self.status in {"OFFICIAL_RULESET_AVAILABLE", "TEST_FIXTURE_ONLY"}
            and self.framework == "ESCAT"
            and self.version
            and self.reference.available
            and self.reference.framework == self.framework
            and self.reference.version == self.version
            and self.rules
            and all(
                rule.framework_version == self.version
                and rule.source.available
                and rule.source.framework == self.framework
                and rule.source.version == self.version
                for rule in self.rules
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework": self.framework,
            "version": self.version,
            "reference": self.reference.to_dict(),
            "rules": [rule.to_dict() for rule in self.rules],
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EscatRuleSet":
        return cls(
            framework=value.get("framework", "ESCAT"),
            version=value.get("version"),
            reference=EscatFrameworkReference.from_dict(value.get("reference")),
            rules=[EscatRule.from_dict(item) for item in value.get("rules", [])],
            status=value.get("status", "OFFICIAL_RULESET_NOT_AVAILABLE"),
        )


@dataclass
class EscatAssessmentRecord:
    assessment_id: str
    claim_id: str
    framework: str = "ESCAT"
    framework_version: str | None = None
    assessment_status: str = "DRAFT"
    tier: str | None = None
    subtier: str | None = None
    biomarker: str | None = None
    disease: str | None = None
    intervention: str | None = None
    direction: str | None = None
    tumour_context_relation: str | None = None
    study_design: str | None = None
    outcome_basis: list[str] = field(default_factory=list)
    evidence_scope: str | None = None
    assessment_origin: str = "MANUAL_REVIEW"
    supporting_sources: list[dict[str, Any]] = field(default_factory=list)
    supporting_passages: list[dict[str, Any]] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    rationale: str | None = None
    curator: str | None = None
    curated_at: datetime | None = None
    created_at: datetime = field(default_factory=_utc_now)
    supersedes_assessment_id: str | None = None
    source_field_origins: dict[str, dict[str, Any]] = field(default_factory=dict)
    framework_status: str = "OFFICIAL_RULESET_NOT_AVAILABLE"

    _required_statuses: ClassVar[frozenset[str]] = ASSESSMENT_STATUSES

    def __post_init__(self) -> None:
        if self.assessment_status not in self._required_statuses:
            raise ValueError(f"unsupported assessment status: {self.assessment_status}")
        if self.assessment_origin not in ASSESSMENT_ORIGINS:
            raise ValueError(f"unsupported assessment origin: {self.assessment_origin}")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["curated_at"] = _datetime_to_json(self.curated_at)
        value["created_at"] = _datetime_to_json(self.created_at)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EscatAssessmentRecord":
        allowed = {item.name for item in fields(cls) if item.init}
        data = {key: item for key, item in value.items() if key in allowed}
        data["curated_at"] = _datetime_from_json(data.get("curated_at"))
        data["created_at"] = _datetime_from_json(data.get("created_at")) or _utc_now()
        return cls(**data)


@dataclass
class EscatCurationDraft:
    assessment: EscatAssessmentRecord
    prefilled_fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing_requirements: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment": self.assessment.to_dict(),
            "prefilled_fields": self.prefilled_fields,
            "missing_requirements": self.missing_requirements,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EscatCurationDraft":
        return cls(
            assessment=EscatAssessmentRecord.from_dict(value["assessment"]),
            prefilled_fields=dict(value.get("prefilled_fields", {})),
            missing_requirements=list(value.get("missing_requirements", [])),
        )


@dataclass(frozen=True)
class EscatAssessmentEvent:
    event_id: str
    assessment_id: str
    timestamp: datetime
    actor: str
    action: str
    field: str | None = None
    previous_value: Any = None
    new_value: Any = None
    reason: str | None = None
    rationale: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["timestamp"] = _datetime_to_json(self.timestamp)
        value["rationale"] = self.rationale or self.reason
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EscatAssessmentEvent":
        data = dict(value)
        data["timestamp"] = _datetime_from_json(data.get("timestamp")) or _utc_now()
        data.setdefault("rationale", data.get("reason"))
        return cls(**data)
