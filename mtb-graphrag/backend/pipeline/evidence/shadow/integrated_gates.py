"""Composizione congiunta dei gate strutturali.

Fino alla 1.2 ogni gate decideva da solo e il risultato veniva letto come se le
decisioni fossero indipendenti. Non lo sono. Un claim con disease exact e
biomarcatore incompatibile non e' "buono su un asse e meno buono sull'altro": non
risponde alla domanda, e l'unico modo di dirlo senza ambiguita' e' far derivare
l'eleggibilita' finale dalla congiunzione e non dalla somma.

La regola e' una sola, e vale in entrambe le direzioni:

    un singolo gate incompatibile impedisce il primary ranking
    un singolo gate compatibile non promuove nulla

Da qui discende la precedenza dei bucket, che e' conservativa per costruzione::

    rejected_by_native_constraints
    audit_only_results
    retained_with_warning
    primary_ranked_results

Il motivo piu' restrittivo domina. Un claim unsupported o deprecated resta
audit-only anche con disease, biomarcatore e intervento tutti exact, perche' cio'
che lo trattiene non e' la qualita' del match ma lo stato dell'oggetto.

L'ultima parte del modulo e' la piu' importante e la piu' facile da dimenticare:
quando il risultato integrato e' rejected o audit-only, **nessun flag di score
sopravvive**. I gate individuali continuano a riportare la propria idoneita' —
serve a spiegare l'esito — ma l'idoneita' integrata viene azzerata invece di
essere ereditata dal gate piu' permissivo. Un flag ereditato sarebbe una porta da
cui un punteggio alto rientra a decidere cio' che il gate aveva escluso.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow import disease_gate as DISEASE
from backend.pipeline.evidence.shadow import domain_gates as DOMAIN

GATE_VERSION = "qualified_claim_structural_gate/1.0"

PRIMARY_BUCKET = DOMAIN.PRIMARY_BUCKET
WARNING_BUCKET = DOMAIN.WARNING_BUCKET
AUDIT_BUCKET = DOMAIN.AUDIT_BUCKET
REJECTED_BUCKET = DOMAIN.REJECTED_BUCKET

# Ordine di restrittivita' decrescente. La posizione nella tupla *e'* la
# precedenza: `BUCKET_PRECEDENCE.index` decide, e non esiste un secondo posto in
# cui la stessa regola sia scritta diversamente.
BUCKET_PRECEDENCE = (
    REJECTED_BUCKET,
    AUDIT_BUCKET,
    WARNING_BUCKET,
    PRIMARY_BUCKET,
)

GATE_NAMES = (
    "claim_status",
    "claim_domain",
    "biomarker",
    "disease",
    "intervention",
    "direction",
)

# --- stato dell'oggetto -------------------------------------------------------

STATUS_ACTIVE_CLAIM = "active_claim"
STATUS_DEPRECATED_CLAIM = "deprecated_claim"
STATUS_UNSUPPORTED_ASSOCIATION = "unsupported_association"
STATUS_UNRESOLVED_ASSOCIATION = "unresolved_association"
STATUS_PARENT_CONTAINER = "parent_provenance_container"

CLAIM_DEPRECATED = "CLAIM_DEPRECATED"
ASSOCIATION_IS_NOT_A_CLAIM = "ASSOCIATION_IS_NOT_A_CLAIM"
PARENT_PROVENANCE_CONTAINER_NOT_CLAIM = "PARENT_PROVENANCE_CONTAINER_NOT_CLAIM"

INTEGRATED_GATE_PRECEDES_SCORING = "INTEGRATED_GATE_PRECEDES_SCORING"
SINGLE_INCOMPATIBLE_GATE_BLOCKS_PRIMARY = "SINGLE_INCOMPATIBLE_GATE_BLOCKS_PRIMARY"

# Gli assi che il gate 1.1 gia' valuta e che qui vengono soltanto letti. Il
# disease non e' fra questi: viene tolto dalla query passata al gate 1.1 e
# ridecisi dal gate direzionale, perche' le due nozioni di "disease match" non
# coincidono e sovrapporle darebbe due volte lo stesso voto.
BASE_AXES = ("biomarker", "intervention", "direction", "polarity")


class IntegratedGateError(RuntimeError):
    """Il gate integrato e' stato aggirato o interrogato fuori ordine."""


def _blank_eligibility(bucket: str) -> dict[str, Any]:
    return {
        "bucket": bucket,
        "final_ranking_eligible": False,
        "positive_score_forbidden": True,
        "qualified_score_eligible": False,
        "ranks_within_bucket_only": False,
        "structural_score_eligible": False,
    }


def claim_status(obj: Any) -> dict[str, Any]:
    """Stato dell'oggetto, indipendente dalla query.

    E' il primo gate perche' e' l'unico che non guarda la domanda: un claim
    ritirato e un'associazione non sostenuta non diventano candidati per nessuna
    query, e verificarlo prima evita di calcolare un match che non puo' contare.
    """
    kind = getattr(obj, "kind", None)
    if kind == "graph_evidence_record":
        return {
            "audit_only_object": True,
            "deprecated": False,
            "eligible_for_primary": False,
            "is_claim": False,
            "reason_codes": (PARENT_PROVENANCE_CONTAINER_NOT_CLAIM,),
            "status": STATUS_PARENT_CONTAINER,
        }
    if kind in ("unsupported_association", "unresolved_association"):
        return {
            "audit_only_object": True,
            "deprecated": False,
            "eligible_for_primary": False,
            "is_claim": False,
            "reason_codes": (ASSOCIATION_IS_NOT_A_CLAIM,),
            "status": kind,
        }
    deprecated = bool(getattr(obj, "deprecated", False))
    return {
        "audit_only_object": deprecated,
        "deprecated": deprecated,
        "eligible_for_primary": not deprecated,
        "is_claim": True,
        "reason_codes": (CLAIM_DEPRECATED,) if deprecated else (),
        "status": STATUS_DEPRECATED_CLAIM if deprecated else STATUS_ACTIVE_CLAIM,
    }


def _bucket_of(*buckets: str) -> str:
    """Il piu' restrittivo fra i bucket proposti dai singoli gate."""
    unknown = [bucket for bucket in buckets if bucket not in BUCKET_PRECEDENCE]
    if unknown:
        raise IntegratedGateError(f"bucket non riconosciuto: {sorted(set(unknown))}")
    return min(buckets, key=BUCKET_PRECEDENCE.index)


def _query_without_disease(query: Mapping[str, Any]) -> dict[str, Any]:
    """La query vista dal gate 1.1, privata del solo vincolo di malattia.

    Il gate 1.1 conosce una nozione di disease match binaria — exact oppure
    `unresolved_disease_relation`, che diventa un vincolo nativo violato — e
    quella nozione non sa distinguere un parent da un sibling da un cross-disease.
    Lasciarla attiva accanto al gate direzionale significherebbe far decidere
    due volte lo stesso asse, con la decisione piu' grossolana che vince sempre.
    Il vincolo viene quindi tolto qui e ridecisi per intero dal gate direzionale,
    che e' l'unico a esprimersi sulla malattia.
    """
    return {key: value for key, value in query.items() if key != "disease"}


@dataclass(frozen=True)
class IntegratedStructuralMatchResult:
    """Eleggibilita' finale, derivata dalla congiunzione di tutti i gate."""

    claim_id: str
    query_id: str
    claim_domain: str
    claim_type: str
    claim_status_result: dict[str, Any] = field(default_factory=dict)
    domain_match_result: dict[str, Any] = field(default_factory=dict)
    biomarker_match_result: dict[str, Any] = field(default_factory=dict)
    disease_match_result: dict[str, Any] = field(default_factory=dict)
    intervention_match_result: dict[str, Any] = field(default_factory=dict)
    direction_match_result: dict[str, Any] = field(default_factory=dict)
    final_bucket: str = REJECTED_BUCKET
    primary_candidate_eligible: bool = False
    warning_eligible: bool = False
    audit_only: bool = False
    rejected_by_native_constraints: bool = False
    structural_score_eligible: bool = False
    qualified_score_eligible: bool = False
    final_ranking_eligible: bool = False
    score_eligibility: dict[str, Any] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    explanation_codes: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    policy_mode: str = DISEASE.DEFAULT_POLICY_MODE
    blocking_gates: tuple[str, ...] = ()
    gate_version: str = GATE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_only": self.audit_only,
            "biomarker_match_result": dict(self.biomarker_match_result),
            "blocking_gates": list(self.blocking_gates),
            "claim_domain": self.claim_domain,
            "claim_id": self.claim_id,
            "claim_status_result": dict(self.claim_status_result),
            "claim_type": self.claim_type,
            "direction_match_result": dict(self.direction_match_result),
            "disease_match_result": dict(self.disease_match_result),
            "domain_match_result": dict(self.domain_match_result),
            "explanation_codes": list(self.explanation_codes),
            "final_bucket": self.final_bucket,
            "final_ranking_eligible": self.final_ranking_eligible,
            "gate_version": self.gate_version,
            "intervention_match_result": dict(self.intervention_match_result),
            "policy_mode": self.policy_mode,
            "primary_candidate_eligible": self.primary_candidate_eligible,
            "provenance": dict(self.provenance),
            "qualified_score_eligible": self.qualified_score_eligible,
            "query_id": self.query_id,
            "reason_codes": list(self.reason_codes),
            "rejected_by_native_constraints": self.rejected_by_native_constraints,
            "score_eligibility": dict(self.score_eligibility),
            "structural_score_eligible": self.structural_score_eligible,
            "warning_codes": list(self.warning_codes),
            "warning_eligible": self.warning_eligible,
        }


def _base_axis_results(
    base: DOMAIN.DomainMatchResult,
) -> dict[str, dict[str, Any]]:
    """Gli assi valutati dal gate 1.1, letti uno per uno invece che in blocco."""
    detail = dict(base.structural_match)
    exclusions = set(base.exclusion_reason_codes)
    return {
        "biomarker": {
            "match_type": detail.get("biomarker_match_type", "not_evaluated"),
            "compatible": "NATIVE_BIOMARKER_MISMATCH" not in exclusions,
            "reason_codes": (
                ["NATIVE_BIOMARKER_MISMATCH"]
                if "NATIVE_BIOMARKER_MISMATCH" in exclusions
                else []
            ),
        },
        "intervention": {
            "match_type": detail.get("intervention_match_type", "not_evaluated"),
            "claim_interventions": list(detail.get("claim_interventions") or ()),
            "query_interventions": list(detail.get("query_interventions") or ()),
            "compatible": not exclusions
            & {
                "NATIVE_INTERVENTION_MISMATCH",
                "NON_THERAPEUTIC_CLAIM_HAS_NO_INTERVENTION_TO_MATCH",
            },
            "reason_codes": sorted(
                exclusions
                & {
                    "ATOMIC_COMPONENT_NOT_REGIMEN_MATCH",
                    "CLASS_RELATION_UNVERIFIED",
                    "INTERVENTION_ASSOCIATION_UNSUPPORTED_BY_SOURCE",
                    "INTERVENTION_MAPPING_PENDING",
                    "NATIVE_INTERVENTION_MISMATCH",
                    "NON_THERAPEUTIC_CLAIM_HAS_NO_INTERVENTION_TO_MATCH",
                    "QUERY_REGIMEN_IS_PROPER_SUBSET",
                    "QUERY_REGIMEN_IS_PROPER_SUPERSET",
                }
            ),
        },
        "direction": {
            "direction_match_type": detail.get("direction_match_type", "not_evaluated"),
            "polarity_match_type": detail.get("polarity_match_type", "not_evaluated"),
            "compatible": not exclusions
            & {"NATIVE_DIRECTION_MISMATCH", "NATIVE_POLARITY_MISMATCH"},
            "reason_codes": sorted(
                exclusions & {"NATIVE_DIRECTION_MISMATCH", "NATIVE_POLARITY_MISMATCH"}
            ),
        },
    }


def evaluate(
    query: Mapping[str, Any],
    obj: Any,
    *,
    mode: str | None = None,
) -> IntegratedStructuralMatchResult:
    """Applica tutti i gate e ne compone l'esito. Nessun punteggio entra qui."""
    resolved_mode = mode if mode is not None else DISEASE.policy_mode(query)

    status = claim_status(obj)
    base = DOMAIN.evaluate(_query_without_disease(query), obj)
    disease = DISEASE.evaluate(query, obj, mode=resolved_mode)
    axes = _base_axis_results(base)

    # --- bucket proposto da ciascun gate -------------------------------------
    status_bucket = AUDIT_BUCKET if status["audit_only_object"] else PRIMARY_BUCKET
    domain_bucket = base.bucket if not base.domain_match else PRIMARY_BUCKET
    structural_bucket = base.bucket
    # Un oggetto senza disease scope proprio non viene respinto dal gate di
    # malattia: non ha una relazione da violare. Il suo esito e' gia' deciso
    # dallo stato, e sommare un audit ridondante nasconderebbe il motivo vero.
    disease_bucket = (
        disease.bucket if disease.object_carries_disease_scope else PRIMARY_BUCKET
    )

    final_bucket = _bucket_of(
        status_bucket, domain_bucket, structural_bucket, disease_bucket
    )

    blocking = []
    if status_bucket != PRIMARY_BUCKET:
        blocking.append("claim_status")
    if not base.domain_match:
        blocking.append("claim_domain")
    if not axes["biomarker"]["compatible"]:
        blocking.append("biomarker")
    if disease_bucket != PRIMARY_BUCKET:
        blocking.append("disease")
    if not axes["intervention"]["compatible"] or structural_bucket in (
        WARNING_BUCKET,
        AUDIT_BUCKET,
    ):
        blocking.append("intervention")
    if not axes["direction"]["compatible"]:
        blocking.append("direction")

    primary = final_bucket == PRIMARY_BUCKET
    warning = final_bucket == WARNING_BUCKET
    audit = final_bucket == AUDIT_BUCKET
    rejected = final_bucket == REJECTED_BUCKET

    # --- idoneita' allo scoring ----------------------------------------------
    # Nei bucket non ordinabili i flag non vengono ereditati: vengono azzerati.
    if rejected or audit:
        eligibility = _blank_eligibility(final_bucket)
    else:
        base_eligibility = dict(base.score_eligibility)
        disease_eligibility = dict(disease.score_eligibility)
        structural = bool(
            primary
            and base_eligibility.get("structural_score_eligible")
            and disease_eligibility.get("structural_score_eligible")
        )
        qualified = bool(
            base_eligibility.get("qualified_score_eligible")
            and disease_eligibility.get("qualified_score_eligible")
        )
        eligibility = {
            "bucket": final_bucket,
            "final_ranking_eligible": primary,
            "positive_score_forbidden": not (structural or qualified),
            "qualified_score_eligible": qualified,
            "ranks_within_bucket_only": warning and qualified,
            "structural_score_eligible": structural,
        }

    # I codici del gate di malattia entrano soltanto se l'oggetto porta davvero
    # un disease scope. Su un parent o un'associazione la relazione non e' stata
    # valutata, e riportarne il codice suggerirebbe che il disease abbia
    # contribuito a un esito che invece dipende interamente dallo stato.
    reasons = set(status["reason_codes"]) | set(base.exclusion_reason_codes)
    warnings = set(base.warning_codes)
    explanations = set(base.explanation_codes)
    if disease.object_carries_disease_scope:
        reasons |= set(disease.reason_codes)
        warnings |= set(disease.warning_codes)
        explanations |= set(disease.explanation_codes)
    if not primary:
        reasons.add(INTEGRATED_GATE_PRECEDES_SCORING)
    if len(blocking) >= 1 and not primary:
        reasons.add(SINGLE_INCOMPATIBLE_GATE_BLOCKS_PRIMARY)

    return IntegratedStructuralMatchResult(
        claim_id=str(
            getattr(obj, "claim_id", None)
            or getattr(obj, "association_id", None)
            or getattr(obj, "parent_id", "")
        ),
        query_id=str(query.get("query_id") or ""),
        claim_domain=base.claim_domain,
        claim_type=base.claim_type,
        claim_status_result=dict(status) | {"reason_codes": list(status["reason_codes"])},
        domain_match_result={
            "claim_domain": base.claim_domain,
            "domain_match": base.domain_match,
            "query_domain": base.query_domain,
            "section": base.section,
            "therapy_score_allowed": base.therapy_score_allowed,
        },
        biomarker_match_result=axes["biomarker"],
        disease_match_result=disease.to_dict(),
        intervention_match_result=axes["intervention"],
        direction_match_result=axes["direction"],
        final_bucket=final_bucket,
        primary_candidate_eligible=primary,
        warning_eligible=warning,
        audit_only=audit,
        rejected_by_native_constraints=rejected,
        structural_score_eligible=bool(eligibility["structural_score_eligible"]),
        qualified_score_eligible=bool(eligibility["qualified_score_eligible"]),
        final_ranking_eligible=bool(eligibility["final_ranking_eligible"]),
        score_eligibility=eligibility,
        reason_codes=tuple(sorted(reasons)),
        warning_codes=tuple(sorted(warnings)),
        explanation_codes=tuple(sorted(explanations)),
        provenance={
            "claim_type_contract": "claim-type-retrieval-contract/1.0",
            "disease_contract": disease.contract_version,
            "disease_gate": DISEASE.GATE_VERSION,
            "domain_gate": DOMAIN.GATE_VERSION,
            "integrated_gate": GATE_VERSION,
            "relation_provenance": disease.relation_provenance,
            "relation_source": disease.relation_source,
            "relation_verified": disease.relation_verified,
        },
        policy_mode=resolved_mode,
        blocking_gates=tuple(dict.fromkeys(blocking)),
    )


def check_no_score_survives_a_blocking_gate(
    result: IntegratedStructuralMatchResult,
    hypothetical_score: float,
) -> None:
    """Rende l'invariante un test invece che una promessa.

    Il punteggio ipotetico non entra in nessuna delle espressioni: la funzione
    ricalcola le condizioni dai soli flag del risultato. Se un punteggio potesse
    spostare un esito, questo controllo non se ne accorgerebbe — ed e' proprio il
    punto: non c'e' nessuna via per cui possa farlo.
    """
    if result.final_bucket in (REJECTED_BUCKET, AUDIT_BUCKET):
        if (
            result.structural_score_eligible
            or result.qualified_score_eligible
            or result.final_ranking_eligible
        ):
            raise IntegratedGateError(
                f"{result.claim_id}: flag di score sopravvissuto nel bucket "
                f"{result.final_bucket} (punteggio ipotetico {hypothetical_score})"
            )
        if not result.score_eligibility.get("positive_score_forbidden"):
            raise IntegratedGateError(
                f"{result.claim_id}: punteggio positivo ammesso nel bucket "
                f"{result.final_bucket}"
            )
    if result.primary_candidate_eligible and result.blocking_gates:
        raise IntegratedGateError(
            f"{result.claim_id}: primary concesso con gate bloccanti "
            f"{list(result.blocking_gates)}"
        )
    if result.final_ranking_eligible != result.primary_candidate_eligible:
        raise IntegratedGateError(
            f"{result.claim_id}: ranking finale incoerente con l'idoneita' primaria"
        )
    if result.structural_score_eligible and not result.primary_candidate_eligible:
        raise IntegratedGateError(
            f"{result.claim_id}: punteggio strutturale fuori dal bucket primario"
        )


def bucket_precedence_contract() -> dict[str, Any]:
    """Descrizione serializzabile della precedenza, per il manifest della fase."""
    return {
        "buckets_most_to_least_restrictive": list(BUCKET_PRECEDENCE),
        "conjunction_rule": (
            "L'eleggibilita' finale e' la congiunzione dei gate: un solo gate "
            "incompatibile impedisce il primary ranking, e un solo gate "
            "compatibile non promuove nulla."
        ),
        "explicit_exceptions": [],
        "gate_names": list(GATE_NAMES),
        "gate_version": GATE_VERSION,
        "inherited_score_flags_cleared_outside_rankable_buckets": True,
        "score_flags_cleared_in_buckets": [REJECTED_BUCKET, AUDIT_BUCKET],
        "unsupported_or_deprecated_stays_audit_with_all_axes_exact": True,
    }


__all__ = [
    "AUDIT_BUCKET",
    "BUCKET_PRECEDENCE",
    "GATE_NAMES",
    "GATE_VERSION",
    "PRIMARY_BUCKET",
    "REJECTED_BUCKET",
    "WARNING_BUCKET",
    "IntegratedGateError",
    "IntegratedStructuralMatchResult",
    "bucket_precedence_contract",
    "check_no_score_survives_a_blocking_gate",
    "claim_status",
    "evaluate",
]
