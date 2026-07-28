"""Gate integrato 1.3: la direzione della congiunzione entra nel bucket.

Il 1.2 ha dato all'asse del biomarcatore la capacita' di leggere gli operatori.
Nel farlo ha adottato una regola sola per le congiunzioni — i termini del claim
contenuti in quelli della query bastano — che e' vera come implicazione logica e
sbagliata come affermazione clinica. Su una query `EGFR L858R AND EGFR T790M`
quella regola promuoveva al bucket primario 59 claim misurati su popolazioni che
la co-alterazione non avevano.

Il 1.3 non aggiunge un asse e non ne toglie: divide in due un esito che il 1.2
teneva unito, secondo la direzione del contenimento. Un claim piu' generale della
query e' evidenza indebolita e va in warning; un claim piu' specifico della query
parla di un'altra popolazione e va fra i respinti. `conjunction_satisfied` non
viene rinominato: viene sostituito da due esiti con direzioni opposte, e tenerne
il nome avrebbe suggerito che la decisione fosse la stessa.

Tre scelte meritano di essere lette come scelte.

**Il 1.2 resta byte-identico e resta eseguibile.** Vale la stessa ragione per cui
il 1.2 non ha toccato il 1.1: gli artefatti della fase precedente sono stati
misurati sotto quel gate, e riprodurli deve restare possibile senza rigenerarli.
Un retriever costruito con `gate=integrated_gates_v12` ricalcola quelle misure
parola per parola.

**Solo le query congiuntive cambiano.** La correzione riguarda un verso che solo
una query con AND puo' percorrere. Una query a termine singolo e una query
disgiuntiva restano decise dal 1.2: `evidence:11219` resta raggiunto dal suo
disgiunto, `evidence:11598` e `evidence:11599` restano respinti dalla congiunzione
soddisfatta a meta'.

**Il warning direzionale non porta punteggio strutturale.** Il punteggio
strutturale e' il punteggio del bucket primario, e questo bucket non lo e'. In
`strict_verified` non porta nemmeno il punteggio qualificato: una ordinabilita'
concessa a un risultato non separabile finirebbe per essere letta come una
graduatoria clinica, che e' esattamente cio' che il bucket sta negando.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow import biomarker_query_direction as DIR
from backend.pipeline.evidence.shadow import integrated_gates_v12 as GATE_V12

GATE_VERSION = "qualified_claim_structural_gate/1.3"
OUTPUT_CONTRACT_VERSION = "qualified_claim_retrieval_result/1.6"

PRIMARY_BUCKET = GATE_V12.PRIMARY_BUCKET
WARNING_BUCKET = GATE_V12.WARNING_BUCKET
AUDIT_BUCKET = GATE_V12.AUDIT_BUCKET
REJECTED_BUCKET = GATE_V12.REJECTED_BUCKET

BUCKET_PRECEDENCE = GATE_V12.BUCKET_PRECEDENCE
GATE_NAMES = GATE_V12.GATE_NAMES
NOT_EVALUATED = GATE_V12.NOT_EVALUATED

FORMULATION_MISMATCH_NOT_COMPENSABLE = GATE_V12.FORMULATION_MISMATCH_NOT_COMPENSABLE
FORMULATION_NOT_APPLICABLE = GATE_V12.FORMULATION_NOT_APPLICABLE
BOOLEAN_BIOMARKER_AXIS_RESOLVED = GATE_V12.BOOLEAN_BIOMARKER_AXIS_RESOLVED

# Il codice che segnala il ramo nuovo del 1.3: la direzione del contenimento ha
# deciso il bucket, e non il solo fatto che i due insiemi si contenessero.
DIRECTIONAL_BIOMARKER_AXIS_APPLIED = "DIRECTIONAL_BIOMARKER_AXIS_APPLIED"

# I codici con cui il 1.2 descrive il proprio confronto sull'asse. Su un esito
# direzionale il 1.2 ha visto l'espressione *sostituita* e ha risposto su quella:
# tenere il suo `BIOMARKER_EXACT_LITERAL_MATCH` accanto a un
# `query_more_specific_than_claim` affermerebbe un'identita' letterale che non
# c'e'. I codici non vengono corretti, vengono tolti: la relazione la dichiara il
# match type direzionale, e due vocabolari sulla stessa decisione sono uno di
# troppo.
_SUPERSEDED_AXIS_REASON_CODES = frozenset(
    {
        "BIOMARKER_CONJUNCTION_ONLY_PARTIALLY_SATISFIED",
        "BIOMARKER_EXACT_BOOLEAN_SET_MATCH",
        "BIOMARKER_EXACT_LITERAL_MATCH",
        "BIOMARKER_QUERY_SATISFIES_EVERY_CONJUNCT",
        "BIOMARKER_QUERY_SATISFIES_ONE_DISJUNCT",
    }
)


class IntegratedGateV13Error(RuntimeError):
    """Il gate 1.3 e' stato aggirato o interrogato fuori ordine."""


def _bucket_of(*buckets: str) -> str:
    return GATE_V12._bucket_of(*buckets)  # noqa: SLF001 - stessa precedenza


@dataclass(frozen=True)
class IntegratedStructuralMatchResultV13(GATE_V12.IntegratedStructuralMatchResultV12):
    """Esito del gate 1.3. Estende il 1.2 con la direzione dell'asse booleano."""

    biomarker_direction: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["biomarker_direction"] = dict(self.biomarker_direction)
        return payload

    def gate_trace(self) -> dict[str, Any]:
        trace = super().gate_trace()
        trace["biomarker_direction"] = dict(self.biomarker_direction)
        return trace


def _claim_biomarker(obj: Any) -> str:
    return str(getattr(obj, "biomarker", "") or "")


def _demoted_eligibility(bucket: str) -> dict[str, Any]:
    return {
        "bucket": bucket,
        "final_ranking_eligible": False,
        "positive_score_forbidden": True,
        "qualified_score_eligible": False,
        "ranks_within_bucket_only": False,
        "structural_score_eligible": False,
    }


def evaluate(
    query: Mapping[str, Any],
    obj: Any,
    *,
    mode: str | None = None,
) -> IntegratedStructuralMatchResultV13:
    """Applica il gate 1.2 con un asse di biomarcatore che legge la direzione."""
    claim_expression = _claim_biomarker(obj)
    verdict = DIR.match(query.get("biomarker"), claim_expression)

    # Il 1.2 viene interrogato con l'espressione del claim quando la relazione
    # rende il claim raggiungibile: senza sostituzione risponderebbe sul
    # letterale della query, che non e' la domanda. La query ricevuta non viene
    # toccata — `effective` e' un dizionario locale.
    effective = (
        dict(query) | {"biomarker": claim_expression} if verdict.substitutes else query
    )
    base = GATE_V12.evaluate(effective, obj, mode=mode)

    policy_mode = base.policy_mode

    # Il cappello direzionale si applica **solo** agli esiti direzionali. Fuori
    # da quelli l'asse non ha aggiunto niente al 1.2, e comporne comunque il
    # bucket cancellerebbe il bucket di audit: un contenitore di provenienza ha
    # un asse di biomarcatore incompatibile e resta comunque recuperabile,
    # perche' il suo bucket lo decide cio' che l'oggetto e' prima di cio' a cui
    # somiglia. E' lo stesso argomento con cui il 1.2 tiene i propri
    # `gate_local_buckets` descrittivi invece che prescrittivi.
    if verdict.is_directional:
        local_buckets = dict(base.gate_local_buckets) | {
            "biomarker": verdict.axis_bucket
        }
        # Il bucket dell'asse puo' solo trattenere, mai promuovere: comporlo per
        # minimo impedisce a un warning direzionale di scavalcare un rifiuto
        # deciso da un altro gate.
        final_bucket = _bucket_of(base.final_bucket, verdict.axis_bucket)
    else:
        local_buckets = dict(base.gate_local_buckets)
        final_bucket = base.final_bucket

    reasons = set(base.reason_codes) | set(verdict.reason_codes)
    warnings = set(base.warning_codes) | set(verdict.warning_codes)
    explanations = tuple(base.explanation_codes) + tuple(verdict.explanation_codes)
    blocking = list(base.blocking_gates)

    if verdict.is_directional:
        reasons -= _SUPERSEDED_AXIS_REASON_CODES
        reasons.discard(BOOLEAN_BIOMARKER_AXIS_RESOLVED)
        reasons.add(DIRECTIONAL_BIOMARKER_AXIS_APPLIED)
        reasons |= set(verdict.reason_codes)
        if verdict.axis_bucket != PRIMARY_BUCKET and "biomarker" not in blocking:
            blocking.append("biomarker")

    if final_bucket in (REJECTED_BUCKET, AUDIT_BUCKET):
        eligibility = _demoted_eligibility(final_bucket)
        primary = warning = False
    else:
        eligibility = dict(base.score_eligibility) | {"bucket": final_bucket}
        primary = final_bucket == PRIMARY_BUCKET and base.primary_candidate_eligible
        warning = final_bucket == WARNING_BUCKET
        eligibility["final_ranking_eligible"] = primary
        if not primary:
            eligibility["structural_score_eligible"] = False
        eligibility |= DIR.score_eligibility(verdict, policy_mode=policy_mode)
        eligibility["ranks_within_bucket_only"] = bool(
            warning and eligibility["qualified_score_eligible"]
        )
        eligibility["positive_score_forbidden"] = not (
            eligibility["structural_score_eligible"]
            or eligibility["qualified_score_eligible"]
        )

    return IntegratedStructuralMatchResultV13(
        claim_id=base.claim_id,
        query_id=base.query_id,
        claim_domain=base.claim_domain,
        claim_type=base.claim_type,
        claim_status_result=dict(base.claim_status_result),
        domain_match_result=dict(base.domain_match_result),
        biomarker_match_result=verdict.to_dict(),
        disease_match_result=dict(base.disease_match_result),
        intervention_match_result=dict(base.intervention_match_result),
        formulation_match_result=dict(base.formulation_match_result),
        direction_match_result=dict(base.direction_match_result),
        final_bucket=final_bucket,
        primary_candidate_eligible=primary,
        warning_eligible=warning,
        audit_only=final_bucket == AUDIT_BUCKET,
        rejected_by_native_constraints=final_bucket == REJECTED_BUCKET,
        structural_score_eligible=bool(eligibility["structural_score_eligible"]),
        qualified_score_eligible=bool(eligibility["qualified_score_eligible"]),
        final_ranking_eligible=bool(eligibility["final_ranking_eligible"]),
        score_eligibility=eligibility,
        reason_codes=tuple(sorted(reasons)),
        warning_codes=tuple(sorted(warnings)),
        explanation_codes=tuple(dict.fromkeys(explanations)),
        provenance=dict(base.provenance)
        | {
            "biomarker_directional_contract": DIR.CONTRACT_VERSION,
            "integrated_gate": GATE_VERSION,
            "output_contract": OUTPUT_CONTRACT_VERSION,
        },
        policy_mode=policy_mode,
        blocking_gates=tuple(dict.fromkeys(blocking)),
        gate_version=GATE_VERSION,
        output_contract=OUTPUT_CONTRACT_VERSION,
        gate_local_buckets=local_buckets,
        dominant_gate=GATE_V12.dominant_gate(local_buckets),
        biomarker_substitution={
            "claim_biomarker_expression": verdict.claim_expression.literal,
            "effective_biomarker_passed_to_v12": (
                verdict.claim_expression.literal
                if verdict.substitutes
                else verdict.query_expression.literal
            ),
            "original_query_biomarker": verdict.query_expression.literal,
            "substitution_reason": (
                verdict.match_type if verdict.substitutes else "none"
            ),
        },
        biomarker_direction={
            "applies_to_conjunctive_query": verdict.query_expression.operator
            == "and",
            "contract_version": DIR.CONTRACT_VERSION,
            "decided_by": verdict.decided_by,
            "is_directional": verdict.is_directional,
            "match_type": verdict.match_type,
            "primary_eligible": verdict.primary_eligible,
        },
    )


def check_no_score_survives_a_blocking_gate(
    result: IntegratedStructuralMatchResultV13, hypothetical_score: float
) -> None:
    """Gli invarianti del 1.2, piu' i due che il 1.3 rende verificabili."""
    GATE_V12.check_no_score_survives_a_blocking_gate(result, hypothetical_score)

    direction = getattr(result, "biomarker_direction", None)
    if not direction or not direction.get("is_directional"):
        return

    # Nessun esito direzionale raggiunge il bucket primario. E' la regola che il
    # 1.3 esiste per imporre, e verificarla dai soli flag e' cio' che la rende un
    # test invece che una promessa.
    if result.primary_candidate_eligible:
        raise IntegratedGateV13Error(
            f"{result.claim_id}: esito direzionale {direction['match_type']!r} "
            f"nel bucket primario (punteggio ipotetico {hypothetical_score})"
        )
    if result.structural_score_eligible:
        raise IntegratedGateV13Error(
            f"{result.claim_id}: punteggio strutturale su un esito direzionale "
            f"{direction['match_type']!r}"
        )
    if (
        result.policy_mode == DIR.STRICT_POLICY_MODE
        and result.qualified_score_eligible
    ):
        raise IntegratedGateV13Error(
            f"{result.claim_id}: punteggio qualificato concesso in "
            f"{DIR.STRICT_POLICY_MODE} su un esito direzionale"
        )


def gate_contract() -> dict[str, Any]:
    """Descrizione serializzabile del gate 1.3, per il manifest della fase."""
    inherited = GATE_V12.gate_contract()
    return dict(inherited) | {
        "biomarker_axis_direction": DIR.directional_semantics_contract(),
        "biomarker_substitution_fields": [
            "claim_biomarker_expression",
            "effective_biomarker_passed_to_v12",
            "original_query_biomarker",
            "substitution_reason",
        ],
        "directional_outcomes_never_reach_primary": True,
        "gate_version": GATE_VERSION,
        "output_contract": OUTPUT_CONTRACT_VERSION,
        "query_superset_of_claim_does_not_grant_primary": True,
        "supersedes": GATE_V12.GATE_VERSION,
    }


__all__ = [
    "AUDIT_BUCKET",
    "BUCKET_PRECEDENCE",
    "DIRECTIONAL_BIOMARKER_AXIS_APPLIED",
    "GATE_NAMES",
    "GATE_VERSION",
    "NOT_EVALUATED",
    "OUTPUT_CONTRACT_VERSION",
    "PRIMARY_BUCKET",
    "REJECTED_BUCKET",
    "WARNING_BUCKET",
    "IntegratedGateV13Error",
    "IntegratedStructuralMatchResultV13",
    "check_no_score_survives_a_blocking_gate",
    "evaluate",
    "gate_contract",
]
