"""Explicit documentary verification policies and the public audit boundary.

These policies describe source relation support. They do not determine clinical
applicability, therapeutic efficacy or individual trial eligibility.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from ..text_integrity import CANONICAL_TEXT_DIGEST_VERSION, canonical_text_sha256


@dataclass(frozen=True)
class VerificationPolicy:
    policy_id: str
    relation_family: str
    requires_semantic_comparison: bool
    requirements: tuple[str, ...]
    scope: str = "SOURCE_RELATION_CORRESPONDENCE"
    clinical_applicability: str = "NOT_EVALUATED"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "requirements": list(self.requirements)}


def policy_for(candidate: dict[str, Any]) -> VerificationPolicy:
    family = str(candidate.get("relation_family") or "UNSPECIFIED")
    if family == "EVIDENCE_DRUG":
        return VerificationPolicy(
            "evidence-drug-semantic-admission/2.0",
            family,
            True,
            (
                "LITERAL_QUOTE",
                "AUTHORIZED_PROVENANCE",
                "EXACT_ARGUMENT_IDENTITIES",
                "DIRECT_ASSERTION",
                "OBSERVED_RESULT",
                "COMPARABLE_MOLECULAR_SCOPE",
                "COMPARABLE_POPULATION",
                "EXACT_INTERVENTION",
                "DIRECT_INFERENCE",
                "ESTABLISHED_ASSERTION",
            ),
        )
    contract = (candidate.get("source_properties") or {}).get("relation_contract") or {}
    requirements = [
        "LITERAL_QUOTE",
        "AUTHORIZED_PROVENANCE",
        "ANCHORED_ASSERTED_RELATION",
        "APPLICABLE_CENTRAL_FIELDS",
        "NO_CONTRADICTORY_REQUIRED_DIMENSION",
    ]
    if (
        candidate.get("disease_required") is True
        or contract.get("disease_required") is True
    ):
        requirements.append("EXACT_DISEASE_CONTEXT")
    if contract.get("evidence_context_required") is True:
        requirements.append("COMPATIBLE_EVIDENCE_CONTEXT")
    return VerificationPolicy(
        "paper-relation-verifier/5.2", family, False, tuple(requirements)
    )


def public_verification_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """Expose decisions, excerpt and resolvable hashes; keep full context private."""
    result = deepcopy(trace)
    gep = result.get("GEP_snapshot")
    if isinstance(gep, dict):
        context = gep.pop("required_context", None)
        if isinstance(context, str):
            gep["context_sha256"] = canonical_text_sha256(context)
            gep["context_digest_contract"] = CANONICAL_TEXT_DIGEST_VERSION
            gep["context_chars"] = len(context)
    target = result.get("target_snapshot")
    if isinstance(target, dict):
        target.pop("evidence_statement", None)
    return result


def public_artifact(value: Any) -> Any:
    """Project after decision making, so private context can still be verified."""
    if isinstance(value, dict):
        projected = (
            public_verification_trace(value) if "GEP_snapshot" in value else value
        )
        result = {}
        for key, item in projected.items():
            if key in {"source_unit_text", "required_context"}:
                if isinstance(item, str):
                    prefix = "source_unit" if key == "source_unit_text" else "context"
                    result[f"{prefix}_sha256"] = canonical_text_sha256(item)
                    result[f"{prefix}_digest_contract"] = CANONICAL_TEXT_DIGEST_VERSION
                    result[f"{prefix}_chars"] = len(item)
                continue
            result[key] = public_artifact(item)
        return result
    if isinstance(value, (list, tuple)):
        return [public_artifact(item) for item in value]
    return value
