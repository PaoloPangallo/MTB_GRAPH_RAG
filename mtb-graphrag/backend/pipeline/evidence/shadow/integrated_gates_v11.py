"""Gate integrato 1.1: la relazione di forma entra nella congiunzione.

Il gate 1.0 compone sei assi. Il 1.1 ne aggiunge uno, e lo colloca dove serve:
**dopo** l'identita' dell'intervento e **prima** di direzione e punteggio.

    1. claim status
    2. claim domain
    3. biomarker
    4. disease
    5. intervention identity
    6. formulation relation
    7. direction / polarity
    8. score eligibility

L'ordine non e' estetico. L'identita' risponde a "e' lo stesso farmaco?", la
forma a "e' la stessa forma di quel farmaco?", e la seconda domanda ha senso
solo dopo la prima. Metterle insieme in un unico asse — che e' cio' che la
tabella dei suffissi faceva — significa rispondere a entrambe con un confronto
di stringhe.

Sull'asse dell'intervento le due decisioni si compongono con una regola sola,
scritta qui e in nessun altro punto:

    quando il registro ha qualcosa da dire sulla forma, e' il registro a
    decidere il bucket dell'asse; quando tace, decide l'identita'

E' l'unica eccezione alla composizione per minimo di tutto il gate, ed e'
dichiarata come tale in `bucket_precedence_contract`. La ragione e' che il
registro *sa* qualcosa che il confronto di stringhe non sa. Un sale verificato
della moiety chiesta non e' "nessuna relazione": e' una relazione nota, e
diversa. Respingerlo come farmaco estraneo perderebbe l'informazione; renderlo
primario la falsificherebbe. Warning e' l'unico posto in cui entrambe le cose
restano vere.

L'eccezione non puo' promuovere nulla al bucket primario. `primary` richiede,
oltre a tutto il resto, che la relazione di forma sia exact — e nessuna voce di
registro produce una relazione exact.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow import disease_gate as DISEASE
from backend.pipeline.evidence.shadow import domain_gates as DOMAIN
from backend.pipeline.evidence.shadow import formulation as FORM
from backend.pipeline.evidence.shadow import integrated_gates as GATE_V10

GATE_VERSION = "qualified_claim_structural_gate/1.1"
OUTPUT_CONTRACT_VERSION = "qualified_claim_retrieval_result/1.3"

PRIMARY_BUCKET = GATE_V10.PRIMARY_BUCKET
WARNING_BUCKET = GATE_V10.WARNING_BUCKET
AUDIT_BUCKET = GATE_V10.AUDIT_BUCKET
REJECTED_BUCKET = GATE_V10.REJECTED_BUCKET

BUCKET_PRECEDENCE = GATE_V10.BUCKET_PRECEDENCE

GATE_NAMES = (
    "claim_status",
    "claim_domain",
    "biomarker",
    "disease",
    "intervention_identity",
    "formulation",
    "direction",
)

FORMULATION_MISMATCH_NOT_COMPENSABLE = "FORMULATION_MISMATCH_NOT_COMPENSABLE"

# Una query che non nomina un intervento non ha una forma da confrontare.
# L'asse non viene valutato, e dirlo e' diverso dal riportare un mismatch: un
# `incompatible_active_moiety` su una domanda che non chiede farmaci sarebbe un
# esito inventato per un confronto mai avvenuto.
FORMULATION_NOT_APPLICABLE = "not_applicable_no_intervention_constraint"


class IntegratedGateV11Error(RuntimeError):
    """Il gate 1.1 e' stato aggirato o interrogato fuori ordine."""


def _bucket_of(*buckets: str) -> str:
    unknown = [bucket for bucket in buckets if bucket not in BUCKET_PRECEDENCE]
    if unknown:
        raise IntegratedGateV11Error(f"bucket non riconosciuto: {sorted(set(unknown))}")
    return min(buckets, key=BUCKET_PRECEDENCE.index)


def _claim_literals(obj: Any) -> tuple[str, ...]:
    """I letterali con cui il claim puo' essere raggiunto, forma compresa.

    Per un aggregato canonicalizzato sono sia i membri canonici sia quelli
    letterali: la fonte del 2013 resta raggiungibile con il nome che usa, e
    questa e' la ragione per cui `intervention_members` li tiene entrambi.
    """
    members = getattr(obj, "intervention_members", None)
    if members:
        return tuple(str(item) for item in members)
    literal = getattr(obj, "intervention_literal", None)
    return (str(literal),) if literal else ()


def _query_literals(query: Mapping[str, Any]) -> tuple[str, ...]:
    interventions = tuple(query.get("interventions") or ())
    if interventions:
        return tuple(str(item) for item in interventions)
    intervention_class = query.get("intervention_class")
    return (str(intervention_class),) if intervention_class else ()


def _query_without_intervention(query: Mapping[str, Any]) -> dict[str, Any]:
    """La query privata del solo vincolo di intervento.

    Serve a isolare il contributo degli altri assi. Il gate 1.0 non espone il
    bucket dell'asse intervento separatamente, e dedurlo dai reason code
    significherebbe ricostruire una decisione invece di misurarla: valutando due
    volte, la differenza fra i due esiti **e'** il contributo dell'intervento.
    """
    return {
        key: value
        for key, value in query.items()
        if key not in ("interventions", "intervention_class", "intervention_combination")
    }


@dataclass(frozen=True)
class IntegratedStructuralMatchResultV11:
    """Esito del gate 1.1. Estende il 1.0 con l'asse di forma."""

    claim_id: str
    query_id: str
    claim_domain: str
    claim_type: str
    claim_status_result: dict[str, Any] = field(default_factory=dict)
    domain_match_result: dict[str, Any] = field(default_factory=dict)
    biomarker_match_result: dict[str, Any] = field(default_factory=dict)
    disease_match_result: dict[str, Any] = field(default_factory=dict)
    intervention_match_result: dict[str, Any] = field(default_factory=dict)
    formulation_match_result: dict[str, Any] = field(default_factory=dict)
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
    output_contract: str = OUTPUT_CONTRACT_VERSION

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
            "formulation_match_result": dict(self.formulation_match_result),
            "gate_version": self.gate_version,
            "intervention_match_result": dict(self.intervention_match_result),
            "output_contract": self.output_contract,
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


def intervention_axis_bucket(
    identity_bucket: str, relation: FORM.FormulationRelation
) -> tuple[str, str]:
    """Bucket dell'asse intervento, e chi lo ha deciso.

    Restituire anche il decisore evita che la sola eccezione del gate resti
    implicita nel risultato: chi legge una riga di simulazione vede se il
    bucket viene dall'identita' o dal registro delle forme.
    """
    if relation.relation_type in FORM.EXACT_FORM_RELATIONS:
        return identity_bucket, "intervention_identity"
    if relation.relation_type in FORM.VERIFIED_DIFFERENT_FORM_RELATIONS:
        # L'unica eccezione alla composizione per minimo, e vale in entrambi i
        # versi: il registro puo' abbassare un primario a warning e puo'
        # sollevare a warning cio' che il confronto di stringhe respingeva.
        return WARNING_BUCKET, "formulation_registry"
    if relation.relation_type == FORM.UNRESOLVED_FORMULATION_RELATION:
        return _bucket_of(identity_bucket, AUDIT_BUCKET), "formulation_registry"
    return identity_bucket, "intervention_identity"


def evaluate(
    query: Mapping[str, Any],
    obj: Any,
    *,
    mode: str | None = None,
) -> IntegratedStructuralMatchResultV11:
    """Applica tutti i gate, forma compresa, e ne compone l'esito."""
    base = GATE_V10.evaluate(query, obj, mode=mode)
    context = GATE_V10.evaluate(_query_without_intervention(query), obj, mode=mode)

    relation = FORM.best_relation(_query_literals(query), _claim_literals(obj))
    # Il contributo dell'asse intervento e' la differenza fra i due esiti. Se
    # coincidono, l'intervento non ha vincolato nulla e il suo bucket e'
    # primario; se divergono, la divergenza *e'* il suo bucket.
    identity_bucket = (
        base.final_bucket if base.final_bucket != context.final_bucket else PRIMARY_BUCKET
    )
    axis_bucket, decided_by = intervention_axis_bucket(identity_bucket, relation)

    # La query che non vincola l'intervento non ha una forma da confrontare, e
    # chiederne una produrrebbe un audit su un asse che la domanda non usa.
    constrains_intervention = bool(_query_literals(query))
    if not constrains_intervention:
        axis_bucket, decided_by = identity_bucket, "no_intervention_constraint"

    registry_overrode = (
        constrains_intervention
        and identity_bucket == REJECTED_BUCKET
        and relation.relation_type in FORM.VERIFIED_DIFFERENT_FORM_RELATIONS
    )
    final_bucket = _bucket_of(context.final_bucket, axis_bucket)

    blocking = [gate for gate in base.blocking_gates if gate != "intervention"]
    if axis_bucket != PRIMARY_BUCKET and "intervention_identity" not in blocking:
        blocking.append("intervention_identity")
    formulation_blocks = constrains_intervention and not relation.is_exact_form
    if formulation_blocks and "formulation" not in blocking:
        blocking.append("formulation")

    # La forma vincola il primario soltanto quando la query nomina un
    # intervento. Una query che non lo nomina non ha una forma da confrontare, e
    # pretenderne una exact respingerebbe ogni claim su un asse che la domanda
    # non usa.
    form_allows_primary = relation.is_exact_form or not constrains_intervention
    primary = final_bucket == PRIMARY_BUCKET and form_allows_primary
    if not primary and final_bucket == PRIMARY_BUCKET:
        # Un primario senza forma exact non esiste: se l'asse di forma non e'
        # exact il bucket non puo' restare primario, e abbassarlo qui e' cio'
        # che rende la regola vera invece che dichiarata.
        final_bucket = WARNING_BUCKET
    warning = final_bucket == WARNING_BUCKET
    audit = final_bucket == AUDIT_BUCKET
    rejected = final_bucket == REJECTED_BUCKET

    if rejected or audit:
        eligibility = {
            "bucket": final_bucket,
            "final_ranking_eligible": False,
            "positive_score_forbidden": True,
            "qualified_score_eligible": False,
            "ranks_within_bucket_only": False,
            "structural_score_eligible": False,
        }
    else:
        # L'idoneita' viene composta dagli assi che restano validi, non dal
        # risultato 1.0 completo: quando il registro delle forme solleva una
        # coppia che il confronto di stringhe aveva respinto, l'esito 1.0 porta
        # i flag azzerati dal proprio rifiuto, e ereditarli qui cancellerebbe
        # l'ordinabilita' che l'eccezione ha appena concesso.
        base_eligibility = dict(base.score_eligibility)
        context_eligibility = dict(context.score_eligibility)
        structural = bool(
            primary
            and identity_bucket == PRIMARY_BUCKET
            and base_eligibility.get("structural_score_eligible")
            and (relation.structural_score_eligible or not constrains_intervention)
        )
        if registry_overrode:
            # Il rifiuto 1.0 ha azzerato i propri flag: ereditarli cancellerebbe
            # l'ordinabilita' che l'eccezione ha appena concesso. Gli altri assi
            # restano quelli misurati senza il vincolo di intervento.
            qualified = bool(
                context_eligibility.get("qualified_score_eligible")
                and relation.qualified_score_eligible
            )
        else:
            qualified = bool(
                base_eligibility.get("qualified_score_eligible")
                and (relation.qualified_score_eligible or not constrains_intervention)
            )
        eligibility = {
            "bucket": final_bucket,
            "final_ranking_eligible": primary,
            "positive_score_forbidden": not (structural or qualified),
            "qualified_score_eligible": qualified,
            "ranks_within_bucket_only": warning and qualified,
            "structural_score_eligible": structural,
        }

    reasons = set(base.reason_codes)
    warnings = set(base.warning_codes)
    if constrains_intervention:
        reasons |= set(relation.reason_codes)
        warnings |= set(relation.warning_codes)
    if formulation_blocks:
        reasons.add(FORMULATION_MISMATCH_NOT_COMPENSABLE)

    return IntegratedStructuralMatchResultV11(
        claim_id=base.claim_id,
        query_id=base.query_id,
        claim_domain=base.claim_domain,
        claim_type=base.claim_type,
        claim_status_result=dict(base.claim_status_result),
        domain_match_result=dict(base.domain_match_result),
        biomarker_match_result=dict(base.biomarker_match_result),
        disease_match_result=dict(base.disease_match_result),
        intervention_match_result=dict(base.intervention_match_result)
        | {"identity_bucket": identity_bucket},
        formulation_match_result=(
            relation.to_dict()
            if constrains_intervention
            else {
                "axis_evaluated": False,
                "contract_version": FORM.CONTRACT_VERSION,
                "is_exact_form": False,
                "relation_type": FORMULATION_NOT_APPLICABLE,
            }
        )
        | {"axis_bucket": axis_bucket, "axis_bucket_decided_by": decided_by},
        direction_match_result=dict(base.direction_match_result),
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
        explanation_codes=tuple(base.explanation_codes),
        provenance=dict(base.provenance)
        | {
            "formulation_contract": FORM.CONTRACT_VERSION,
            "formulation_registry": FORM.REGISTRY_VERSION,
            "integrated_gate": GATE_VERSION,
            "output_contract": OUTPUT_CONTRACT_VERSION,
        },
        policy_mode=base.policy_mode,
        blocking_gates=tuple(dict.fromkeys(blocking)),
    )


def check_no_score_survives_a_blocking_gate(
    result: IntegratedStructuralMatchResultV11, hypothetical_score: float
) -> None:
    """Rende l'invariante un test invece che una promessa.

    Il punteggio ipotetico non entra in nessuna espressione: la funzione
    ricalcola le condizioni dai soli flag. Al controllo del gate 1.0 se ne
    aggiunge uno: un mismatch di forma non puo' convivere con il bucket
    primario, per quanto alto sia il punteggio o buono il resto del match.
    """
    if result.final_bucket in (REJECTED_BUCKET, AUDIT_BUCKET):
        if (
            result.structural_score_eligible
            or result.qualified_score_eligible
            or result.final_ranking_eligible
        ):
            raise IntegratedGateV11Error(
                f"{result.claim_id}: flag di score sopravvissuto nel bucket "
                f"{result.final_bucket} (punteggio ipotetico {hypothetical_score})"
            )
        if not result.score_eligibility.get("positive_score_forbidden"):
            raise IntegratedGateV11Error(
                f"{result.claim_id}: punteggio positivo ammesso nel bucket "
                f"{result.final_bucket}"
            )
    if result.primary_candidate_eligible and result.blocking_gates:
        raise IntegratedGateV11Error(
            f"{result.claim_id}: primary concesso con gate bloccanti "
            f"{list(result.blocking_gates)}"
        )
    if result.final_ranking_eligible != result.primary_candidate_eligible:
        raise IntegratedGateV11Error(
            f"{result.claim_id}: ranking finale incoerente con l'idoneita' primaria"
        )
    if result.structural_score_eligible and not result.primary_candidate_eligible:
        raise IntegratedGateV11Error(
            f"{result.claim_id}: punteggio strutturale fuori dal bucket primario"
        )
    relation = result.formulation_match_result.get("relation_type")
    if relation == FORMULATION_NOT_APPLICABLE:
        return
    if result.primary_candidate_eligible and relation not in FORM.EXACT_FORM_RELATIONS:
        raise IntegratedGateV11Error(
            f"{result.claim_id}: primary concesso con relazione di forma "
            f"{relation!r}, che non e' un'identita' di forma"
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
        "explicit_exceptions": [
            {
                "applies_to": sorted(FORM.VERIFIED_DIFFERENT_FORM_RELATIONS),
                "cannot_reach_primary": True,
                "exception": (
                    "Quando il registro delle forme dichiara una relazione "
                    "verificata ma diversa, il bucket dell'asse intervento e' "
                    "retained_with_warning anche se il confronto di stringhe "
                    "aveva respinto la coppia."
                ),
                "rationale": (
                    "Il registro sa che le due forme sono correlate e diverse. "
                    "Respingerle come estranee perderebbe l'informazione; "
                    "renderle primarie la falsificherebbe."
                ),
            }
        ],
        "formulation_mismatch_is_not_compensable_by": [
            "disease exact",
            "biomarker exact",
            "provenance",
            "source quality",
            "punteggio elevato",
        ],
        "gate_names": list(GATE_NAMES),
        "gate_version": GATE_VERSION,
        "inherited_score_flags_cleared_outside_rankable_buckets": True,
        "output_contract": OUTPUT_CONTRACT_VERSION,
        "primary_requires_exact_form_relation": True,
        "score_flags_cleared_in_buckets": [REJECTED_BUCKET, AUDIT_BUCKET],
        "unsupported_or_deprecated_stays_audit_with_all_axes_exact": True,
    }


__all__ = [
    "AUDIT_BUCKET",
    "BUCKET_PRECEDENCE",
    "FORMULATION_MISMATCH_NOT_COMPENSABLE",
    "GATE_NAMES",
    "GATE_VERSION",
    "OUTPUT_CONTRACT_VERSION",
    "PRIMARY_BUCKET",
    "REJECTED_BUCKET",
    "WARNING_BUCKET",
    "IntegratedGateV11Error",
    "IntegratedStructuralMatchResultV11",
    "bucket_precedence_contract",
    "check_no_score_survives_a_blocking_gate",
    "evaluate",
    "intervention_axis_bucket",
]
