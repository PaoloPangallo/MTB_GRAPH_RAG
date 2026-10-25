"""Output shadow 1.2: quattro bucket e la relazione di malattia esplicita.

Rispetto alla 1.1 cambiano due cose.

La prima: il risultato non e' piu' una lista con un bucket per riga, ma quattro
bucket dichiarati. `primary_ranked_results`, `retained_with_warning`,
`audit_only_results`, `rejected_by_native_constraints` sono contenitori distinti,
e un consumatore che ne legga uno solo legge esattamente cio' che quel bucket
promette. Nella 1.1 la separazione esisteva ma andava ricostruita filtrando, e
una separazione che va ricostruita e' una separazione che prima o poi non viene
ricostruita.

La seconda: la relazione di malattia esce con nome, direzione e provenienza. Nel
1.1 un claim su un sottotipo e uno su una malattia sorella uscivano entrambi
senza dire perche' non fossero primari. Adesso l'output porta il motivo, e il
motivo e' direzionale: `claim_is_child_of_query` e `claim_is_parent_of_query`
sono due errori diversi e nessuno dei due e' "quasi un match".

I divieti della 1.1 restano tutti. Aggregate, regimen e domini non vengono
appiattiti, e la terminologia canonicalizzata non cancella il letterale della
fonte: escono entrambi, in campi distinti.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow import shadow_output as OUT_V10
from backend.pipeline.evidence.shadow import shadow_output_v11 as OUT_V11
from backend.pipeline.evidence.shadow.domain import (
    DOMAIN_DIAGNOSTIC,
    DOMAIN_PROGNOSTIC,
    DOMAIN_THERAPEUTIC,
)
from backend.pipeline.evidence.shadow.domain_gates import SECTION_FOR_DOMAIN
from backend.pipeline.evidence.shadow.integrated_gates import (
    AUDIT_BUCKET,
    BUCKET_PRECEDENCE,
    PRIMARY_BUCKET,
    REJECTED_BUCKET,
    WARNING_BUCKET,
    IntegratedStructuralMatchResult,
)
from backend.pipeline.evidence.shadow.terminology_v13 import REPOSITORY_VERSION

OUTPUT_CONTRACT_VERSION = "qualified_claim_retrieval_result/1.2"

BUCKET_FIELDS = {
    PRIMARY_BUCKET: "primary_ranked_results",
    WARNING_BUCKET: "retained_with_warning",
    AUDIT_BUCKET: "audit_only_results",
    REJECTED_BUCKET: "rejected_by_native_constraints",
}


class OutputContractError(ValueError):
    """L'output avrebbe appiattito o travisato la rappresentazione."""


def _terminology_payload(obj: Any) -> dict[str, Any] | None:
    """Rappresentazione canonica e letterali di fonte, tenuti distinti.

    Restituisce `None` per gli oggetti su cui nessuna decisione terminologica e'
    stata applicata: un campo vuoto suggerirebbe che la coda sia stata guardata
    e trovata vuota, che e' diverso dal non averla guardata affatto.
    """
    provenance = getattr(obj, "terminology_provenance", None)
    if not provenance:
        return None
    return {
        "canonical_label": provenance.get("canonical_label", ""),
        "canonical_members": list(getattr(obj, "canonical_members", ()) or ()),
        "mapping_scope": provenance.get("mapping_scope", ""),
        "propagation_policy": provenance.get("propagation_policy", ""),
        "review_status": provenance.get("review_status", ""),
        "source_literal_members": list(
            getattr(obj, "source_literal_members", ()) or ()
        ),
        "source_literal_preserved": True,
        "source_literal_term": provenance.get("source_literal_term", ""),
        "superseded_claim_id": provenance.get("superseded_claim_id", ""),
        "terminology_decision_id": provenance.get("terminology_decision_id", ""),
    }


def _disease_relation_payload(match: IntegratedStructuralMatchResult) -> dict[str, Any]:
    disease = dict(match.disease_match_result)
    return {
        "claim_disease_scope": disease.get("claim_disease_scope", ""),
        "is_exact_relation": disease.get("is_exact_relation", False),
        "object_carries_disease_scope": disease.get(
            "object_carries_disease_scope", True
        ),
        "policy_mode": disease.get("policy_mode", ""),
        "query_disease": disease.get("query_disease", ""),
        "relation_direction": disease.get("relation_direction", ""),
        "relation_type": disease.get("relation_type", ""),
    }


@dataclass(frozen=True)
class QualifiedClaimRetrievalResult:
    """Una riga di risultato shadow, con l'eleggibilita' gia' decisa dai gate."""

    query_id: str
    object_id: str
    object_kind: str
    parent_id: str
    claim_domain: str
    claim_type: str
    section: str | None
    final_bucket: str
    subject_representation: str
    biomarker: str
    disease_scope: str
    direction: str
    polarity: str
    repository_version: str = REPOSITORY_VERSION
    policy_mode: str = ""
    intervention_representation: dict[str, Any] | None = None
    diagnostic_representation: dict[str, Any] | None = None
    prognostic_representation: dict[str, Any] | None = None
    disease_relation: dict[str, Any] = field(default_factory=dict)
    disease_relation_provenance: dict[str, Any] = field(default_factory=dict)
    integrated_structural_match: dict[str, Any] = field(default_factory=dict)
    score_eligibility: dict[str, Any] = field(default_factory=dict)
    score_breakdown: dict[str, Any] | None = None
    terminology_provenance: dict[str, Any] | None = None
    is_positive_evidence: bool = False
    therapy_score_allowed: bool = False
    source_unit_ids: tuple[str, ...] = ()
    locators: tuple[dict[str, Any], ...] = ()
    qualification_link_ids: tuple[str, ...] = ()
    claim_provenance: dict[str, Any] = field(default_factory=dict)
    review_status: str = "not_reviewed"
    deprecated: bool = False
    audit_status: str = "not_audited"
    warnings: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    explanation_codes: tuple[str, ...] = ()
    contract_version: str = OUTPUT_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_status": self.audit_status,
            "biomarker": self.biomarker,
            "claim_domain": self.claim_domain,
            "claim_provenance": dict(self.claim_provenance),
            "claim_type": self.claim_type,
            "contract_version": self.contract_version,
            "deprecated": self.deprecated,
            "diagnostic_representation": self.diagnostic_representation,
            "direction": self.direction,
            "disease_relation": dict(self.disease_relation),
            "disease_relation_provenance": dict(self.disease_relation_provenance),
            "disease_scope": self.disease_scope,
            "explanation_codes": list(self.explanation_codes),
            "final_bucket": self.final_bucket,
            "integrated_structural_match": dict(self.integrated_structural_match),
            "intervention_representation": self.intervention_representation,
            "is_positive_evidence": self.is_positive_evidence,
            "locators": [dict(item) for item in self.locators],
            "object_id": self.object_id,
            "object_kind": self.object_kind,
            "parent_id": self.parent_id,
            "policy_mode": self.policy_mode,
            "prognostic_representation": self.prognostic_representation,
            "qualification_link_ids": list(self.qualification_link_ids),
            "query_id": self.query_id,
            "reason_codes": list(self.reason_codes),
            "repository_version": self.repository_version,
            "review_status": self.review_status,
            "score_breakdown": self.score_breakdown,
            "score_eligibility": dict(self.score_eligibility),
            "section": self.section,
            "source_unit_ids": list(self.source_unit_ids),
            "subject_representation": self.subject_representation,
            "terminology_provenance": self.terminology_provenance,
            "therapy_score_allowed": self.therapy_score_allowed,
            "warnings": list(self.warnings),
        }


def build_result(
    obj: Any,
    match: IntegratedStructuralMatchResult,
    *,
    score_breakdown: Mapping[str, Any] | None = None,
) -> QualifiedClaimRetrievalResult:
    """Costruisce una riga di output dall'oggetto e dall'esito integrato."""
    kind = getattr(obj, "kind", None) or getattr(obj, "claim_type", "unknown")
    domain = match.claim_domain
    representation = (
        OUT_V11.subject_representation(obj)
        if getattr(obj, "claim_type", None)
        else "none"
    )

    intervention = diagnostic = prognostic = None
    if domain == DOMAIN_THERAPEUTIC:
        intervention = OUT_V10.intervention_payload(obj)
    elif domain == DOMAIN_DIAGNOSTIC:
        diagnostic = OUT_V11._diagnostic_payload(obj)
    elif domain == DOMAIN_PROGNOSTIC:
        prognostic = OUT_V11._prognostic_payload(obj)

    is_positive = bool(
        getattr(obj, "is_claim", False)
        and match.final_bucket in (PRIMARY_BUCKET, WARNING_BUCKET)
        and not match.score_eligibility.get("positive_score_forbidden", True)
    )

    result = QualifiedClaimRetrievalResult(
        query_id=match.query_id,
        object_id=match.claim_id,
        object_kind=kind,
        parent_id=str(getattr(obj, "parent_id", "") or ""),
        claim_domain=domain,
        claim_type=match.claim_type,
        section=SECTION_FOR_DOMAIN.get(domain),
        final_bucket=match.final_bucket,
        subject_representation=representation,
        biomarker=getattr(obj, "biomarker", "")
        or getattr(obj, "biomarker_context", "")
        or "",
        disease_scope=getattr(obj, "disease_scope", "")
        or getattr(obj, "disease_context", "")
        or "",
        direction=getattr(obj, "direction", "unknown"),
        polarity=getattr(obj, "polarity", "unknown"),
        policy_mode=match.policy_mode,
        intervention_representation=intervention,
        diagnostic_representation=diagnostic,
        prognostic_representation=prognostic,
        disease_relation=_disease_relation_payload(match),
        disease_relation_provenance=dict(
            match.disease_match_result.get("provenance") or {}
        ),
        integrated_structural_match=match.to_dict(),
        score_eligibility=dict(match.score_eligibility),
        score_breakdown=dict(score_breakdown) if score_breakdown else None,
        terminology_provenance=_terminology_payload(obj),
        is_positive_evidence=is_positive,
        therapy_score_allowed=bool(
            match.domain_match_result.get("therapy_score_allowed", False)
        ),
        source_unit_ids=tuple(getattr(obj, "source_unit_ids", ()) or ()),
        locators=tuple(getattr(obj, "locators", ()) or ()),
        qualification_link_ids=tuple(getattr(obj, "qualification_link_ids", ()) or ()),
        claim_provenance=dict(getattr(obj, "provenance", {}) or {}),
        review_status=getattr(obj, "review_status", "not_reviewed"),
        deprecated=bool(getattr(obj, "deprecated", False)),
        audit_status="audit_only" if match.audit_only else "not_audited",
        warnings=match.warning_codes,
        reason_codes=match.reason_codes,
        explanation_codes=match.explanation_codes,
    )
    check_output_invariants(result)
    return result


def check_output_invariants(result: QualifiedClaimRetrievalResult) -> None:
    """I divieti della 1.1, piu' quelli che la 1.2 aggiunge."""
    if result.subject_representation not in OUT_V11.SUBJECT_REPRESENTATIONS:
        raise OutputContractError(
            f"{result.object_id}: rappresentazione sconosciuta "
            f"{result.subject_representation!r}"
        )
    if result.final_bucket not in BUCKET_FIELDS:
        raise OutputContractError(
            f"{result.object_id}: bucket sconosciuto {result.final_bucket!r}"
        )

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

    if result.claim_domain == DOMAIN_THERAPEUTIC and result.intervention_representation:
        payload = result.intervention_representation
        if (
            result.subject_representation == "regimen"
            and len(payload.get("members", ())) < 2
        ):
            raise OutputContractError(
                f"{result.object_id}: regime appiattito a un singolo intervento"
            )

    # Il divieto nuovo della 1.2: una canonicalizzazione non cancella la fonte.
    if result.terminology_provenance is not None:
        payload = result.terminology_provenance
        if not payload["source_literal_members"] or not payload["canonical_members"]:
            raise OutputContractError(
                f"{result.object_id}: terminologia senza una delle due rappresentazioni"
            )
        if payload["source_literal_members"] == payload["canonical_members"]:
            raise OutputContractError(
                f"{result.object_id}: canonicalizzazione registrata senza differenza"
            )

    # Un aggregato canonicalizzato resta un aggregato: se uscisse come atomico
    # avremmo separato per farmaco un risultato che la fonte non separa.
    if result.terminology_provenance is not None and result.subject_representation == (
        "atomic_intervention"
    ):
        raise OutputContractError(
            f"{result.object_id}: aggregato canonicalizzato presentato come atomico"
        )

    if result.final_bucket in (AUDIT_BUCKET, REJECTED_BUCKET):
        eligibility = result.score_eligibility
        if any(
            eligibility.get(flag)
            for flag in (
                "structural_score_eligible",
                "qualified_score_eligible",
                "final_ranking_eligible",
            )
        ):
            raise OutputContractError(
                f"{result.object_id}: idoneita' allo scoring nel bucket "
                f"{result.final_bucket}"
            )
        if result.is_positive_evidence:
            raise OutputContractError(
                f"{result.object_id}: evidenza positiva in un bucket non ordinabile"
            )

    if result.object_kind == "graph_evidence_record":
        if result.final_bucket not in (AUDIT_BUCKET, REJECTED_BUCKET):
            raise OutputContractError(
                f"{result.object_id}: contenitore di provenienza presentato come claim"
            )

    if result.object_kind in ("unsupported_association", "unresolved_association"):
        if result.is_positive_evidence or result.final_bucket == PRIMARY_BUCKET:
            raise OutputContractError(
                f"{result.object_id}: associazione presentata come evidenza positiva"
            )

    if result.deprecated and result.final_bucket == PRIMARY_BUCKET:
        raise OutputContractError(
            f"{result.object_id}: claim ritirato nel bucket primario"
        )


def bucketed_output(
    query_id: str,
    results: Sequence[QualifiedClaimRetrievalResult],
    *,
    policy_mode: str,
) -> dict[str, Any]:
    """Output di una query: quattro bucket dichiarati, ordinati deterministicamente.

    L'ordinamento dentro ogni bucket non e' clinico: e' lessicografico su tipo,
    parent e ID. Un ordinamento clinico richiederebbe un punteggio, e nessun
    punteggio esiste in questa fase.
    """
    buckets: dict[str, list[dict[str, Any]]] = {
        field_name: [] for field_name in BUCKET_FIELDS.values()
    }
    for result in results:
        buckets[BUCKET_FIELDS[result.final_bucket]].append(result.to_dict())
    for rows in buckets.values():
        rows.sort(key=lambda row: (row["claim_type"], row["parent_id"], row["object_id"]))

    return {
        "bucket_precedence": list(BUCKET_PRECEDENCE),
        "bucket_counts": {name: len(rows) for name, rows in sorted(buckets.items())},
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "cross_domain_ranking": False,
        "policy_mode": policy_mode,
        "query_id": query_id,
        "repository_version": REPOSITORY_VERSION,
        **{name: rows for name, rows in sorted(buckets.items())},
    }


__all__ = [
    "BUCKET_FIELDS",
    "OUTPUT_CONTRACT_VERSION",
    "OutputContractError",
    "QualifiedClaimRetrievalResult",
    "bucketed_output",
    "build_result",
    "check_output_invariants",
]
