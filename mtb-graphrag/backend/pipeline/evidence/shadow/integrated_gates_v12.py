"""Gate integrato 1.2: l'asse del biomarcatore impara gli operatori booleani.

Il 1.1 aggiunse la relazione di forma al 1.0. Il 1.2 non aggiunge un asse: ne
corregge uno che c'era gia' e che rispondeva a una domanda piu' povera di quella
che gli veniva posta. Il biomarcatore veniva confrontato per uguaglianza di
stringa normalizzata, e su un corpus in cui `EGFR L858R OR EGFR Exon 19 Deletion`
e `EGFR L858R AND EGFR T790M` convivono quel confronto non e' piu' fine: e' cieco
all'operatore. Respingeva `evidence:11219` su una query `EGFR L858R` — dove il
letterale chiesto *e'* uno dei due disgiunti — con lo stesso codice con cui
respingeva un claim congiuntivo soddisfatto a meta'.

Perche' un modulo nuovo e non una modifica al 1.1. Il 1.1 e il contratto
congelato che gli sta sotto sono la base su cui le fasi chiuse hanno misurato i
propri artefatti; cambiarli li riaprirebbe tutti per correggere un asse che
riguarda il solo retriever V3. Il 1.2 e' quindi selezionabile e non imposto:
`integrated_gates_v11` resta importabile, eseguibile e identico, e chi vuole
riprodurre una misura della fase 1.4 lo interroga ancora.

Tre scelte meritano di essere lette come scelte.

**La correzione passa per una seconda valutazione, non per una riscrittura.** E'
lo stesso schema che il 1.1 usa sull'asse intervento: si valuta due volte e la
differenza *e'* il contributo dell'asse. Quando il matcher booleano stabilisce
che la query raggiunge il claim per una relazione — un disgiunto soddisfatto,
una congiunzione interamente coperta — il 1.1 viene interrogato con l'espressione
del claim al posto di quella della query, perche' interrogato con quella della
query risponderebbe alla domanda sbagliata. Nessuna riga del 1.1 cambia.

**La query osservabile non muta.** La sostituzione vive dentro un dizionario
locale e non raggiunge mai il risultato: `query` resta quella posta. Perche' la
sostituzione sia una scelta dichiarata e non un effetto collaterale, il
risultato porta per esteso che cosa e' stato passato al 1.1 e per quale
relazione.

**Il bucket finale non cancella i bucket dei singoli gate.** Il 1.1 pubblica
l'esito di ogni asse ma non il bucket che ogni asse avrebbe imposto da solo, e
senza quello un `rejected` non dice quale gate lo abbia deciso — solo che
qualcuno lo ha fatto. `gate_local_buckets` li tiene tutti e `dominant_gate` nomina
il piu' restrittivo, cosi' un risultato respinto per il biomarcatore resta
distinguibile da uno respinto per la malattia anche quando entrambi gli assi
avevano qualcosa da eccepire.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow import biomarker_expression as BIO
from backend.pipeline.evidence.shadow import integrated_gates_v11 as GATE_V11

GATE_VERSION = "qualified_claim_structural_gate/1.2"
OUTPUT_CONTRACT_VERSION = "qualified_claim_retrieval_result/1.5"

PRIMARY_BUCKET = GATE_V11.PRIMARY_BUCKET
WARNING_BUCKET = GATE_V11.WARNING_BUCKET
AUDIT_BUCKET = GATE_V11.AUDIT_BUCKET
REJECTED_BUCKET = GATE_V11.REJECTED_BUCKET

BUCKET_PRECEDENCE = GATE_V11.BUCKET_PRECEDENCE
GATE_NAMES = GATE_V11.GATE_NAMES

FORMULATION_MISMATCH_NOT_COMPENSABLE = GATE_V11.FORMULATION_MISMATCH_NOT_COMPENSABLE
FORMULATION_NOT_APPLICABLE = GATE_V11.FORMULATION_NOT_APPLICABLE

# Un asse che questa combinazione di query e oggetto non fa entrare in gioco. Non
# e' un bucket: e' l'assenza di un bucket, e resta fuori dalla composizione.
NOT_EVALUATED = "not_evaluated"

# Il codice che segnala il ramo nuovo del 1.2: la relazione booleana c'e', ed e'
# stata riconosciuta dopo che il confronto letterale aveva gia' fallito.
BOOLEAN_BIOMARKER_AXIS_RESOLVED = "BOOLEAN_BIOMARKER_AXIS_RESOLVED"


class IntegratedGateV12Error(RuntimeError):
    """Il gate 1.2 e' stato aggirato o interrogato fuori ordine."""


def _bucket_of(*buckets: str) -> str:
    known = [bucket for bucket in buckets if bucket != NOT_EVALUATED]
    unknown = [bucket for bucket in known if bucket not in BUCKET_PRECEDENCE]
    if unknown:
        raise IntegratedGateV12Error(f"bucket non riconosciuto: {sorted(set(unknown))}")
    if not known:
        return PRIMARY_BUCKET
    return min(known, key=BUCKET_PRECEDENCE.index)


@dataclass(frozen=True)
class IntegratedStructuralMatchResultV12(GATE_V11.IntegratedStructuralMatchResultV11):
    """Esito del gate 1.2. Estende il 1.1 con l'asse booleano e la sua traccia."""

    gate_local_buckets: dict[str, str] = field(default_factory=dict)
    dominant_gate: str = ""
    biomarker_substitution: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["biomarker_substitution"] = dict(self.biomarker_substitution)
        payload["dominant_gate"] = self.dominant_gate
        payload["gate_local_buckets"] = dict(self.gate_local_buckets)
        return payload

    def gate_trace(self) -> dict[str, Any]:
        """La traccia dei gate, nella forma che il risultato V3 pubblica."""
        return {
            "biomarker_match": dict(self.biomarker_match_result),
            "biomarker_substitution": dict(self.biomarker_substitution),
            "dominant_gate": self.dominant_gate,
            "gate_local_buckets": dict(self.gate_local_buckets),
            "gate_version": self.gate_version,
        }


def _claim_biomarker(obj: Any) -> str:
    return str(getattr(obj, "biomarker", "") or "")


def _query_with_resolved_biomarker(
    query: Mapping[str, Any], expression: str
) -> dict[str, Any]:
    """La query con il solo vincolo di biomarcatore riscritto.

    E' un dizionario nuovo: la query ricevuta non viene toccata, e quella che il
    risultato pubblica resta quella posta.
    """
    return dict(query) | {"biomarker": expression}


def _claim_status_bucket(result: Mapping[str, Any]) -> str:
    if not result:
        return NOT_EVALUATED
    if result.get("eligible_for_primary"):
        return PRIMARY_BUCKET
    # Un claim ritirato o un oggetto dichiarato di solo audit non e' un
    # candidato, ma resta recuperabile: e' audit, non rifiuto.
    return AUDIT_BUCKET


def _domain_bucket(result: Mapping[str, Any]) -> str:
    if not result:
        return NOT_EVALUATED
    if result.get("domain_match"):
        return PRIMARY_BUCKET
    # Un claim di dominio sbagliato resta materiale di audit quando e' in
    # perimetro; fuori perimetro e' l'asse del biomarcatore a respingerlo.
    return AUDIT_BUCKET


def _disease_bucket(result: Mapping[str, Any]) -> str:
    if not result:
        return NOT_EVALUATED
    bucket = result.get("bucket")
    return str(bucket) if bucket in BUCKET_PRECEDENCE else NOT_EVALUATED


def _direction_bucket(result: Mapping[str, Any]) -> str:
    if not result:
        return NOT_EVALUATED
    return PRIMARY_BUCKET if result.get("compatible", True) else REJECTED_BUCKET


def gate_local_buckets(
    base: GATE_V11.IntegratedStructuralMatchResultV11,
    biomarker: BIO.BiomarkerMatch,
) -> dict[str, str]:
    """Il bucket che ogni asse avrebbe imposto da solo.

    Gli assi che questa combinazione non fa entrare in gioco restano marcati
    `not_evaluated` e non partecipano alla composizione: attribuire loro un
    bucket significherebbe riportare l'esito di un confronto mai avvenuto.

    Sull'asse dell'intervento vale l'unica eccezione dichiarata dal gate 1.1:
    quando il registro delle forme ha qualcosa da dire, e' il registro a decidere
    il bucket dell'asse. In quel caso il verdetto dell'identita' e' superato, e
    riportarlo qui come se avesse deciso direbbe che un sale verificato della
    moiety chiesta e' stato respinto — mentre e' stato trattenuto con avviso,
    che e' il punto dell'eccezione.
    """
    intervention = base.intervention_match_result or {}
    formulation = base.formulation_match_result or {}
    identity = intervention.get("identity_bucket")
    axis = formulation.get("axis_bucket")
    if formulation.get("axis_bucket_decided_by") == "formulation_registry":
        identity = axis
    return {
        "biomarker": biomarker.axis_bucket,
        "claim_domain": _domain_bucket(base.domain_match_result),
        "claim_status": _claim_status_bucket(base.claim_status_result),
        "direction": _direction_bucket(base.direction_match_result),
        "disease": _disease_bucket(base.disease_match_result),
        "formulation": str(axis) if axis in BUCKET_PRECEDENCE else NOT_EVALUATED,
        "intervention_identity": (
            str(identity) if identity in BUCKET_PRECEDENCE else NOT_EVALUATED
        ),
    }


def dominant_gate(local_buckets: Mapping[str, str]) -> str:
    """Il gate piu' restrittivo. Pareggi risolti nell'ordine dichiarato dei gate.

    Restituire un nome, e non solo un bucket, e' cio' che rende leggibile un
    `rejected` deciso da due assi diversi: `dominant_gate` dice quale dei due
    avrebbe respinto anche da solo, e l'ordine dei nomi non e' arbitrario ma
    quello in cui i gate vengono applicati.
    """
    evaluated = {
        name: bucket
        for name, bucket in local_buckets.items()
        if bucket != NOT_EVALUATED
    }
    if not evaluated:
        return ""
    order = {name: index for index, name in enumerate(GATE_NAMES)}
    return min(
        sorted(evaluated),
        key=lambda name: (
            BUCKET_PRECEDENCE.index(evaluated[name]),
            order.get(name, len(GATE_NAMES)),
        ),
    )


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
) -> IntegratedStructuralMatchResultV12:
    """Applica il gate 1.1 con un asse di biomarcatore che legge gli operatori."""
    claim_expression = _claim_biomarker(obj)
    verdict = BIO.match(query.get("biomarker"), claim_expression)
    substitution = BIO.substitution_record(
        query.get("biomarker"), claim_expression, verdict
    )

    effective = (
        _query_with_resolved_biomarker(query, claim_expression)
        if verdict.substitutes
        else query
    )
    base = GATE_V11.evaluate(effective, obj, mode=mode)

    final_bucket = base.final_bucket
    reasons = set(base.reason_codes)
    blocking = list(base.blocking_gates)

    if verdict.substitutes:
        # Il 1.1 ha visto l'espressione del claim e ha risposto `exact`. Il
        # risultato dice invece quale relazione booleana ha deciso: riportare
        # `exact` affermerebbe un'identita' letterale che non c'e'.
        reasons.discard(BIO.NATIVE_BIOMARKER_MISMATCH)
        reasons.add(BOOLEAN_BIOMARKER_AXIS_RESOLVED)
    reasons |= set(verdict.reason_codes)

    if not verdict.compatible and "biomarker" not in blocking:
        blocking.append("biomarker")
    if verdict.compatible and not verdict.is_unresolved:
        blocking = [gate for gate in blocking if gate != "biomarker"]

    if verdict.is_unresolved:
        # Una relazione non decisa non respinge e non promuove: abbassa fino ad
        # audit e non oltre. Se un altro asse respingeva gia', resta respinto —
        # l'audit non solleva niente, e' solo il posto in cui una domanda senza
        # risposta resta recuperabile.
        final_bucket = _bucket_of(final_bucket, AUDIT_BUCKET)

    # I bucket per asse sono una descrizione, non una seconda decisione. Imporre
    # qui la composizione per minimo cancellerebbe il bucket di audit: un
    # contenitore di provenienza e un claim fuori dominio hanno un asse di
    # biomarcatore incompatibile e restano comunque recuperabili in audit,
    # perche' il bucket lo decide cio' che l'oggetto *e'* prima di cio' a cui
    # somiglia. La composizione resta vera dove e' vera — sui claim — ed e' li'
    # che l'invariante la verifica.
    local_buckets = gate_local_buckets(base, verdict)

    demoted = final_bucket in (REJECTED_BUCKET, AUDIT_BUCKET)
    if demoted:
        eligibility = _demoted_eligibility(final_bucket)
        primary = warning = False
    else:
        eligibility = dict(base.score_eligibility) | {"bucket": final_bucket}
        primary = final_bucket == PRIMARY_BUCKET and base.primary_candidate_eligible
        warning = final_bucket == WARNING_BUCKET
        eligibility["final_ranking_eligible"] = primary
        if not primary:
            eligibility["structural_score_eligible"] = False

    return IntegratedStructuralMatchResultV12(
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
        warning_codes=tuple(base.warning_codes),
        explanation_codes=tuple(base.explanation_codes),
        provenance=dict(base.provenance)
        | {
            "biomarker_boolean_contract": BIO.CONTRACT_VERSION,
            "integrated_gate": GATE_VERSION,
            "output_contract": OUTPUT_CONTRACT_VERSION,
        },
        policy_mode=base.policy_mode,
        blocking_gates=tuple(dict.fromkeys(blocking)),
        gate_version=GATE_VERSION,
        output_contract=OUTPUT_CONTRACT_VERSION,
        gate_local_buckets=local_buckets,
        dominant_gate=dominant_gate(local_buckets),
        biomarker_substitution=substitution,
    )


def check_no_score_survives_a_blocking_gate(
    result: IntegratedStructuralMatchResultV12, hypothetical_score: float
) -> None:
    """L'invariante del 1.1, piu' i due che il 1.2 rende verificabili.

    Il punteggio ipotetico non entra in nessuna espressione: le condizioni
    vengono ricalcolate dai soli flag.
    """
    GATE_V11.check_no_score_survives_a_blocking_gate(result, hypothetical_score)

    local = getattr(result, "gate_local_buckets", None)
    if not local:
        return

    # `dominant_gate` deve essere il minimo di cio' che dichiara, altrimenti
    # nomina un gate che non ha deciso niente.
    expected = dominant_gate(local)
    if result.dominant_gate != expected:
        raise IntegratedGateV12Error(
            f"{result.claim_id}: gate dominante {result.dominant_gate!r} diverso "
            f"dall'asse piu' restrittivo {expected!r} ({dict(sorted(local.items()))})"
        )

    # La regola di congiunzione vale sui claim: un solo asse incompatibile
    # impedisce il primario, e nessun asse compatibile promuove. Non vale sui
    # contenitori di provenienza e sulle associazioni, il cui bucket dipende da
    # cio' che l'oggetto e' — ed e' esattamente la ragione per cui esiste il
    # bucket di audit.
    if not result.claim_status_result.get("is_claim"):
        return

    composed = _bucket_of(*local.values())
    if composed != result.final_bucket:
        raise IntegratedGateV12Error(
            f"{result.claim_id}: bucket finale {result.final_bucket!r} diverso "
            f"dalla composizione degli assi {composed!r} ({dict(sorted(local.items()))})"
        )


def gate_contract() -> dict[str, Any]:
    """Descrizione serializzabile del gate 1.2, per il manifest della fase."""
    inherited = GATE_V11.bucket_precedence_contract()
    return dict(inherited) | {
        "biomarker_axis": BIO.boolean_semantics_contract(),
        "biomarker_substitution_fields": [
            "claim_biomarker_expression",
            "effective_biomarker_passed_to_v11",
            "original_query_biomarker",
            "substitution_reason",
        ],
        "dominant_gate_rule": (
            "Il gate piu' restrittivo fra quelli valutati; i pareggi si "
            "risolvono nell'ordine in cui i gate vengono applicati."
        ),
        "final_bucket_equals_axis_composition": True,
        "gate_local_buckets_preserved": True,
        "gate_version": GATE_VERSION,
        "observable_query_is_never_mutated": True,
        "output_contract": OUTPUT_CONTRACT_VERSION,
        "supersedes": GATE_V11.GATE_VERSION,
        "unresolved_boolean_expression_bucket": AUDIT_BUCKET,
    }


__all__ = [
    "AUDIT_BUCKET",
    "BOOLEAN_BIOMARKER_AXIS_RESOLVED",
    "BUCKET_PRECEDENCE",
    "FORMULATION_MISMATCH_NOT_COMPENSABLE",
    "FORMULATION_NOT_APPLICABLE",
    "GATE_NAMES",
    "GATE_VERSION",
    "NOT_EVALUATED",
    "OUTPUT_CONTRACT_VERSION",
    "PRIMARY_BUCKET",
    "REJECTED_BUCKET",
    "WARNING_BUCKET",
    "IntegratedGateV12Error",
    "IntegratedStructuralMatchResultV12",
    "check_no_score_survives_a_blocking_gate",
    "dominant_gate",
    "evaluate",
    "gate_contract",
    "gate_local_buckets",
]
