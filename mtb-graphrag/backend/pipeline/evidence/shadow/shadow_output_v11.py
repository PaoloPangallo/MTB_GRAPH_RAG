"""Output shadow 1.1: rappresentazione per dominio.

Il campo che porta il peso e' `subject_representation`. Nel 1.0 era
`intervention_representation`, e per un claim che non ha interventi l'unica
risposta possibile era `none` — corretta ma muta: diceva cosa il claim non ha,
non cosa afferma. Nel 1.1 ogni dominio ha la propria rappresentazione, e
`intervention_representation` resta presente soltanto dove significa qualcosa.

I quattro divieti del 1.0 restano, e se ne aggiunge uno: un claim diagnostico o
prognostico non puo' uscire con una rappresentazione di intervento, nemmeno
vuota. Un campo `intervention: null` in un dossier invita a riempirlo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow import shadow_output as OUT_V10
from backend.pipeline.evidence.shadow.domain import (
    DOMAIN_DIAGNOSTIC,
    DOMAIN_PROGNOSTIC,
    DOMAIN_THERAPEUTIC,
)
from backend.pipeline.evidence.shadow.domain_gates import (
    AUDIT_BUCKET,
    PRIMARY_BUCKET,
    REJECTED_BUCKET,
    SECTION_FOR_DOMAIN,
    WARNING_BUCKET,
    DomainMatchResult,
    rank_within_domain,
)
from backend.pipeline.evidence.shadow.schema import OUTPUT_CONTRACT_VERSION_V11

OUTPUT_CONTRACT_VERSION = OUTPUT_CONTRACT_VERSION_V11

SUBJECT_REPRESENTATIONS = (
    "atomic_intervention",
    "regimen",
    "intervention_class",
    "intervention_aggregate",
    "diagnostic_subject",
    "prognostic_subject",
    "none",
)


class OutputContractError(ValueError):
    """L'output avrebbe appiattito o travisato la rappresentazione."""


def subject_representation(obj: Any) -> str:
    claim_type = getattr(obj, "claim_type", None)
    if claim_type == "diagnostic_claim":
        return "diagnostic_subject"
    if claim_type == "prognostic_claim":
        return "prognostic_subject"
    mapped = {
        "atomic": "atomic_intervention",
        "regimen": "regimen",
        "class": "intervention_class",
        "aggregate": "intervention_aggregate",
        "none": "none",
    }
    return mapped[OUT_V10.representation_for(obj)]


def _diagnostic_payload(obj: Any) -> dict[str, Any]:
    return {
        "diagnostic_subject": obj.diagnostic_subject,
        "diagnostic_interpretation": obj.diagnostic_interpretation,
        "assay_or_method": obj.assay_or_method,
        "population_or_sample_scope": obj.population_or_sample_scope,
        "clinical_validation_asserted": False,
        "prevalence_attributable_to_subject": obj.prevalence_attributable_to_subject,
        "limitation_codes": list(obj.limitation_codes),
    }


def _prognostic_payload(obj: Any) -> dict[str, Any]:
    return {
        "prognostic_subject": obj.prognostic_subject,
        "outcome": obj.outcome,
        "population_scope": obj.population_scope,
        "predictive_effect_asserted": False,
        "causality_asserted": False,
        "limitation_codes": list(obj.limitation_codes),
    }


@dataclass(frozen=True)
class QualifiedClaimRetrievalResult:
    query_id: str
    object_id: str
    object_kind: str
    claim_domain: str
    claim_type: str
    parent_graph_evidence_id: str
    section: str | None
    bucket: str
    subject_representation: str
    biomarker: str
    disease_scope: str
    direction: str
    polarity: str
    structural_match: dict[str, Any]
    score_eligibility: dict[str, Any]
    is_positive_evidence: bool
    therapy_score_allowed: bool
    intervention_representation: dict[str, Any] | None = None
    diagnostic_representation: dict[str, Any] | None = None
    prognostic_representation: dict[str, Any] | None = None
    source_unit_ids: tuple[str, ...] = ()
    locators: tuple[dict[str, Any], ...] = ()
    qualification_link_ids: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    review_status: str = "not_reviewed"
    deprecated: bool = False
    audit_status: str = "not_audited"
    warnings: tuple[str, ...] = ()
    exclusion_reason_codes: tuple[str, ...] = ()
    explanation_codes: tuple[str, ...] = ()
    contract_version: str = OUTPUT_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "object_id": self.object_id,
            "object_kind": self.object_kind,
            "claim_domain": self.claim_domain,
            "claim_type": self.claim_type,
            "parent_graph_evidence_id": self.parent_graph_evidence_id,
            "section": self.section,
            "bucket": self.bucket,
            "subject_representation": self.subject_representation,
            "intervention_representation": self.intervention_representation,
            "diagnostic_representation": self.diagnostic_representation,
            "prognostic_representation": self.prognostic_representation,
            "biomarker": self.biomarker,
            "disease_scope": self.disease_scope,
            "direction": self.direction,
            "polarity": self.polarity,
            "structural_match": dict(self.structural_match),
            "score_eligibility": dict(self.score_eligibility),
            "is_positive_evidence": self.is_positive_evidence,
            "therapy_score_allowed": self.therapy_score_allowed,
            "source_unit_ids": list(self.source_unit_ids),
            "locators": [dict(x) for x in self.locators],
            "qualification_link_ids": list(self.qualification_link_ids),
            "provenance": dict(self.provenance),
            "review_status": self.review_status,
            "deprecated": self.deprecated,
            "audit_status": self.audit_status,
            "warnings": list(self.warnings),
            "exclusion_reason_codes": list(self.exclusion_reason_codes),
            "explanation_codes": list(self.explanation_codes),
            "contract_version": self.contract_version,
        }


def build_result(
    query_id: str, obj: Any, match: DomainMatchResult
) -> QualifiedClaimRetrievalResult:
    kind = getattr(obj, "kind", None) or getattr(obj, "claim_type", "unknown")
    domain = match.claim_domain
    representation = (
        subject_representation(obj) if getattr(obj, "claim_type", None) else "none"
    )

    intervention = diagnostic = prognostic = None
    if domain == DOMAIN_THERAPEUTIC:
        intervention = OUT_V10.intervention_payload(obj)
    elif domain == DOMAIN_DIAGNOSTIC:
        diagnostic = _diagnostic_payload(obj)
    elif domain == DOMAIN_PROGNOSTIC:
        prognostic = _prognostic_payload(obj)

    is_positive = bool(
        getattr(obj, "is_claim", False)
        and match.bucket in (PRIMARY_BUCKET, WARNING_BUCKET)
        and not match.score_eligibility.get("positive_score_forbidden", False)
    )

    result = QualifiedClaimRetrievalResult(
        query_id=query_id,
        object_id=match.claim_id,
        object_kind=kind,
        claim_domain=domain,
        claim_type=match.claim_type,
        parent_graph_evidence_id=match.parent_graph_evidence_id,
        section=match.section,
        bucket=match.bucket,
        subject_representation=representation,
        intervention_representation=intervention,
        diagnostic_representation=diagnostic,
        prognostic_representation=prognostic,
        biomarker=getattr(obj, "biomarker", "")
        or getattr(obj, "biomarker_context", "")
        or "",
        disease_scope=getattr(obj, "disease_scope", "")
        or getattr(obj, "disease_context", "")
        or "",
        direction=getattr(obj, "direction", "unknown"),
        polarity=getattr(obj, "polarity", "unknown"),
        structural_match=dict(match.structural_match),
        score_eligibility=dict(match.score_eligibility),
        is_positive_evidence=is_positive,
        therapy_score_allowed=match.therapy_score_allowed,
        source_unit_ids=tuple(getattr(obj, "source_unit_ids", ()) or ()),
        locators=tuple(getattr(obj, "locators", ()) or ()),
        qualification_link_ids=tuple(getattr(obj, "qualification_link_ids", ()) or ()),
        provenance=dict(getattr(obj, "provenance", {}) or {}),
        review_status=getattr(obj, "review_status", "not_reviewed"),
        deprecated=bool(getattr(obj, "deprecated", False)),
        audit_status="audit_only" if match.audit_only else "not_audited",
        warnings=match.warning_codes,
        exclusion_reason_codes=match.exclusion_reason_codes,
        explanation_codes=match.explanation_codes,
    )
    check_output_invariants(result)
    return result


def check_output_invariants(result: QualifiedClaimRetrievalResult) -> None:
    if result.subject_representation not in SUBJECT_REPRESENTATIONS:
        raise OutputContractError(
            f"{result.object_id}: rappresentazione sconosciuta "
            f"{result.subject_representation!r}"
        )

    # Il divieto nuovo del 1.1: nessun campo di intervento su un claim che non ne
    # ha uno, nemmeno vuoto o nullo.
    if result.claim_domain in (DOMAIN_DIAGNOSTIC, DOMAIN_PROGNOSTIC):
        if result.intervention_representation is not None:
            raise OutputContractError(
                f"{result.object_id}: claim {result.claim_domain} appiattito in una "
                "rappresentazione di intervento"
            )
        if result.therapy_score_allowed:
            raise OutputContractError(
                f"{result.object_id}: therapy score concesso a un claim "
                f"{result.claim_domain}"
            )

    if result.claim_domain == DOMAIN_DIAGNOSTIC:
        if result.diagnostic_representation is None:
            raise OutputContractError(f"{result.object_id}: diagnostico senza soggetto")
        if result.diagnostic_representation["clinical_validation_asserted"]:
            raise OutputContractError(
                f"{result.object_id}: utilita' clinica affermata senza fonte"
            )

    if result.claim_domain == DOMAIN_PROGNOSTIC:
        if result.prognostic_representation is None:
            raise OutputContractError(f"{result.object_id}: prognostico senza soggetto")
        if result.prognostic_representation["predictive_effect_asserted"]:
            raise OutputContractError(
                f"{result.object_id}: prognostico presentato come predittivo"
            )

    # I divieti del 1.0 restano, applicati alla forma 1.1.
    if result.claim_domain == DOMAIN_THERAPEUTIC and result.intervention_representation:
        payload = result.intervention_representation
        if result.subject_representation == "regimen" and len(payload.get("members", ())) < 2:
            raise OutputContractError(
                f"{result.object_id}: regime appiattito a un singolo intervento"
            )
        if result.subject_representation in ("intervention_class", "intervention_aggregate"):
            members = payload.get("members", ())
            if members and members != [payload.get("aggregate_label")]:
                raise OutputContractError(
                    f"{result.object_id}: aggregato appiattito su un membro"
                )

    if result.object_kind == "graph_evidence_record":
        if result.bucket not in (AUDIT_BUCKET, REJECTED_BUCKET) or result.is_positive_evidence:
            raise OutputContractError(
                f"{result.object_id}: contenitore di provenienza presentato come claim"
            )

    if result.object_kind in ("unsupported_association", "unresolved_association"):
        if result.is_positive_evidence or result.bucket == PRIMARY_BUCKET:
            raise OutputContractError(
                f"{result.object_id}: associazione presentata come evidenza positiva"
            )


def sectioned_output(
    query_id: str, results: list[QualifiedClaimRetrievalResult]
) -> dict[str, Any]:
    """Output di una query senza tipo: sezioni distinte, nessun ranking incrociato."""
    sections: dict[str, list[dict[str, Any]]] = {
        name: [] for name in SECTION_FOR_DOMAIN.values()
    }
    unsectioned: list[dict[str, Any]] = []
    for result in results:
        if result.section in sections:
            sections[result.section].append(result.to_dict())
        else:
            unsectioned.append(result.to_dict())

    for name, rows in sections.items():
        rows.sort(key=lambda r: (r["claim_type"], r["parent_graph_evidence_id"], r["object_id"]))
    unsectioned.sort(key=lambda r: (r["object_kind"], r["object_id"]))

    return {
        "query_id": query_id,
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "sections_are_separate": True,
        "cross_domain_ranking": False,
        "cross_domain_score_comparison": False,
        "therapeutic_results": sections["therapeutic_results"],
        "diagnostic_results": sections["diagnostic_results"],
        "prognostic_results": sections["prognostic_results"],
        "unsectioned_audit_objects": unsectioned,
        "section_counts": {name: len(rows) for name, rows in sorted(sections.items())},
    }
