"""Gate di malattia direzionale nel percorso shadow.

La fase precedente ha congelato il contratto: undici relazioni, tre modalita', e
la regola che il bucket primario non cambia fra modalita'. Quel contratto vive in
`benchmarks/.../disease_hierarchy_policy.py` come definizione. Qui diventa un
gate: riceve un oggetto tipizzato del modello shadow e una query, e restituisce
un esito che il gate integrato puo' comporre con gli altri.

La divisione del lavoro e' deliberata. Il modulo del contratto risolve la
relazione fra due stringhe di malattia e non sa nulla di claim; questo modulo sa
dove trovare il disease scope di un claim, di un'associazione o di un parent, e
non decide nulla sulla relazione. Nessuna delle due tabelle viene ridefinita:
se la politica cambiasse, cambierebbe in un posto solo.

Il gate non conosce punteggi. `score_eligibility` e' derivato dalla tabella
congelata e non da un confronto numerico, ed e' per questo che un biomarcatore
exact non puo' spostare un claim child dentro il bucket primario.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy import (
    AUDIT,
    AUDIT_ALL,
    CONTRACT_VERSION,
    DEFAULT_MODE,
    EXACT_RELATIONS,
    ONTOLOGY_AWARE_WARNING,
    POLICY_MODES,
    PRIMARY,
    REJECTED,
    RELATION_TYPES,
    STRICT_VERIFIED,
    WARNING,
    match_disease_scope,
    policy_for,
    resolve_relation,
)

GATE_VERSION = "claim_disease_gate/1.0"

# Rieportati per nome perche' i consumatori di questo modulo non debbano
# importare il contratto solo per nominare un bucket o una modalita'.
PRIMARY_BUCKET = PRIMARY
WARNING_BUCKET = WARNING
AUDIT_BUCKET = AUDIT
REJECTED_BUCKET = REJECTED

MODES = POLICY_MODES
DEFAULT_POLICY_MODE = DEFAULT_MODE

# Gli oggetti che non portano un disease scope proprio. Non sono claim, e
# chiedere loro una relazione di malattia sarebbe chiedere una risposta a una
# domanda che non hanno: il gate lo dice invece di inventarla.
NON_CLAIM_KINDS = (
    "graph_evidence_record",
    "unsupported_association",
    "unresolved_association",
)

NON_CLAIM_RELATION = "missing_claim_disease"


class DiseaseGateError(RuntimeError):
    """Il gate di malattia e' stato interrogato fuori dalle sue premesse."""


def policy_mode(query: Mapping[str, Any], default: str = DEFAULT_MODE) -> str:
    """Modalita' richiesta dalla query, con `strict_verified` come default.

    Il default non e' un fallback silenzioso: e' la politica. Una query che non
    dichiara nulla ottiene la modalita' piu' conservativa, e le due modalita'
    piu' larghe vanno chieste esplicitamente.
    """
    declared = query.get("disease_policy_mode") or query.get("policy_mode")
    if declared is None:
        return default
    if declared not in POLICY_MODES:
        raise DiseaseGateError(f"modalita' di disease policy sconosciuta: {declared!r}")
    return declared


def claim_disease_scope(obj: Any) -> str:
    """Disease scope dell'oggetto, o stringa vuota se l'oggetto non ne ha uno."""
    kind = getattr(obj, "kind", None)
    if kind in NON_CLAIM_KINDS:
        # Il parent porta un `disease_context`, che e' contesto del record grezzo
        # e non lo scope di una proposizione. Non viene promosso a disease scope.
        return ""
    return str(getattr(obj, "disease_scope", "") or "")


@dataclass(frozen=True)
class DiseaseGateResult:
    """Esito del gate di malattia per una coppia query/oggetto in una modalita'."""

    claim_id: str
    query_id: str
    policy_mode: str
    query_disease: str
    claim_disease_scope: str
    normalized_query_disease: str
    normalized_claim_disease: str
    relation_type: str
    relation_direction: str
    relation_source: str
    relation_source_version: str
    relation_provenance: str
    relation_verified: bool
    bucket: str
    primary_candidate_eligible: bool
    warning_eligible: bool
    audit_only: bool
    rejected_by_native_constraints: bool
    score_eligibility: dict[str, Any] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    explanation_codes: tuple[str, ...] = ()
    is_exact_relation: bool = False
    object_carries_disease_scope: bool = True
    contract_version: str = CONTRACT_VERSION
    gate_version: str = GATE_VERSION

    def provenance(self) -> dict[str, Any]:
        """Da dove viene la relazione, non che cosa se ne fa."""
        return {
            "contract_version": self.contract_version,
            "gate_version": self.gate_version,
            "relation_provenance": self.relation_provenance,
            "relation_source": self.relation_source,
            "relation_source_version": self.relation_source_version,
            "relation_verified": self.relation_verified,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_only": self.audit_only,
            "bucket": self.bucket,
            "claim_disease_scope": self.claim_disease_scope,
            "claim_id": self.claim_id,
            "contract_version": self.contract_version,
            "explanation_codes": list(self.explanation_codes),
            "gate_version": self.gate_version,
            "is_exact_relation": self.is_exact_relation,
            "normalized_claim_disease": self.normalized_claim_disease,
            "normalized_query_disease": self.normalized_query_disease,
            "object_carries_disease_scope": self.object_carries_disease_scope,
            "policy_mode": self.policy_mode,
            "primary_candidate_eligible": self.primary_candidate_eligible,
            "provenance": self.provenance(),
            "query_disease": self.query_disease,
            "query_id": self.query_id,
            "reason_codes": list(self.reason_codes),
            "rejected_by_native_constraints": self.rejected_by_native_constraints,
            "relation_direction": self.relation_direction,
            "relation_provenance": self.relation_provenance,
            "relation_source": self.relation_source,
            "relation_source_version": self.relation_source_version,
            "relation_type": self.relation_type,
            "relation_verified": self.relation_verified,
            "score_eligibility": dict(self.score_eligibility),
            "warning_codes": list(self.warning_codes),
            "warning_eligible": self.warning_eligible,
        }


def evaluate(
    query: Mapping[str, Any],
    obj: Any,
    *,
    mode: str | None = None,
) -> DiseaseGateResult:
    """Applica il contratto congelato a un oggetto del modello shadow."""
    resolved_mode = mode if mode is not None else policy_mode(query)
    if resolved_mode not in POLICY_MODES:
        raise DiseaseGateError(f"modalita' di disease policy sconosciuta: {resolved_mode!r}")

    scope = claim_disease_scope(obj)
    carries_scope = getattr(obj, "kind", None) not in NON_CLAIM_KINDS
    match = match_disease_scope(query.get("disease"), scope, mode=resolved_mode)

    identifier = (
        getattr(obj, "claim_id", None)
        or getattr(obj, "association_id", None)
        or getattr(obj, "parent_id", "")
    )
    return DiseaseGateResult(
        claim_id=str(identifier),
        query_id=str(query.get("query_id") or ""),
        policy_mode=resolved_mode,
        query_disease=match.query_disease,
        claim_disease_scope=match.claim_disease_scope,
        normalized_query_disease=match.normalized_query_disease,
        normalized_claim_disease=match.normalized_claim_disease,
        relation_type=match.relation_type,
        relation_direction=match.relation_direction,
        relation_source=match.relation_source,
        relation_source_version=match.relation_source_version,
        relation_provenance=match.relation_provenance,
        relation_verified=match.relation_verified,
        bucket=match.score_eligibility["bucket"],
        primary_candidate_eligible=match.primary_candidate_eligible,
        warning_eligible=match.warning_eligible,
        audit_only=match.audit_only,
        rejected_by_native_constraints=match.rejected_by_native_constraints,
        score_eligibility=dict(match.score_eligibility),
        reason_codes=match.reason_codes,
        warning_codes=match.warning_codes,
        explanation_codes=match.explanation_codes,
        is_exact_relation=match.relation_type in EXACT_RELATIONS,
        object_carries_disease_scope=carries_scope,
    )


def evaluate_all_modes(query: Mapping[str, Any], obj: Any) -> dict[str, DiseaseGateResult]:
    """Lo stesso oggetto nelle tre modalita'. Serve a rendere testabile l'invariante.

    Il tipo di relazione e' identico nelle tre: cio' che cambia e' soltanto il
    bucket. Restituirle insieme rende il confronto un fatto osservabile invece
    che un'affermazione della documentazione.
    """
    return {mode: evaluate(query, obj, mode=mode) for mode in POLICY_MODES}


def primary_bucket_is_mode_invariant(
    results: Mapping[str, DiseaseGateResult],
) -> bool:
    """Vero se l'idoneita' primaria non dipende dalla modalita'."""
    values = {result.primary_candidate_eligible for result in results.values()}
    return len(values) <= 1


def gate_contract() -> dict[str, Any]:
    """Descrizione serializzabile del gate, per il manifest della fase."""
    return {
        "buckets": [PRIMARY, WARNING, AUDIT, REJECTED],
        "contract_version": CONTRACT_VERSION,
        "default_mode": DEFAULT_MODE,
        "exact_relations": sorted(EXACT_RELATIONS),
        "gate_version": GATE_VERSION,
        "modes": list(POLICY_MODES),
        "non_claim_kinds": list(NON_CLAIM_KINDS),
        "non_claim_relation": NON_CLAIM_RELATION,
        "per_relation_per_mode": {
            relation: {
                mode: policy_for(relation, mode).as_row() for mode in POLICY_MODES
            }
            for relation in RELATION_TYPES
        },
        "primary_bucket_is_mode_invariant": True,
        "relation_type_is_mode_invariant": True,
        "relation_types": list(RELATION_TYPES),
        "structural_score_reserved_to_exact_relations": True,
    }


__all__ = [
    "AUDIT_ALL",
    "AUDIT_BUCKET",
    "DEFAULT_POLICY_MODE",
    "GATE_VERSION",
    "MODES",
    "NON_CLAIM_KINDS",
    "ONTOLOGY_AWARE_WARNING",
    "PRIMARY_BUCKET",
    "REJECTED_BUCKET",
    "STRICT_VERIFIED",
    "WARNING_BUCKET",
    "DiseaseGateError",
    "DiseaseGateResult",
    "claim_disease_scope",
    "evaluate",
    "evaluate_all_modes",
    "gate_contract",
    "policy_mode",
    "primary_bucket_is_mode_invariant",
    "resolve_relation",
]
