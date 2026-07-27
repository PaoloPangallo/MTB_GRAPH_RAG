"""Rerun dei gate integrati sui casi che decidono la composizione.

L'audit non ricontrolla le 7776 coppie della 1.3: quella simulazione esiste gia'
ed e' congelata. Ricontrolla invece i sette casi in cui la **congiunzione** puo'
sbagliare, ognuno costruito perche' un solo gate sia incompatibile mentre tutti
gli altri sono exact. Se la composizione fosse una somma invece che una
congiunzione, esattamente questi sette casi cambierebbero esito e nessun altro.

Il settimo caso non ha un gate incompatibile: ha un punteggio arbitrariamente
alto. Serve a rendere osservabile che il punteggio non entra in nessuna delle
espressioni del gate — non che sia piccolo abbastanza da non contare.

Gli oggetti su cui i casi girano non sono inventati: sono claim e associazioni
reali della 1.3, ricostruiti dai loro record. Un caso costruito su un oggetto
sintetico proverebbe una proprieta' del test, non del repository.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from backend.pipeline.evidence.shadow import disease_gate as DISEASE
from backend.pipeline.evidence.shadow import integrated_gates as GATE
from backend.pipeline.evidence.shadow.associations import (
    UnresolvedAssociation,
    UnsupportedAssociation,
)
from backend.pipeline.evidence.shadow.claims import (
    AggregateInterventionClaim,
    AtomicInterventionClaim,
    RegimenClaim,
)
from benchmarks.mtb_evidence.evaluation.claim_type_retrieval_contract import (
    is_pending_pair,
)

# Il termine con cui la query interroga un claim il cui mapping non e' stato
# approvato. E' il codice di sviluppo, non il nome canonico: la coppia
# `BGJ398`/`infigratinib` e' pending nel contratto congelato, e resta pending
# anche dopo che la 1.3 ha canonicalizzato i due aggregati.
PENDING_QUERY_TERM = "BGJ398"

# L'ordine dichiarato dei gate. Non e' decorativo: `blocking_gates` viene emesso
# in quest'ordine, e la precedenza del bucket ne discende.
GATE_ORDER = (
    "claim_status",
    "claim_domain",
    "biomarker",
    "disease",
    "intervention",
    "direction",
    "score_eligibility",
)

# Un punteggio che nessuna configurazione di pesi potrebbe produrre. Se il gate
# fosse componibile con lo scoring, questo numero lo mostrerebbe.
ARBITRARILY_HIGH_SCORE = 10**9

THERAPEUTIC = "therapeutic_evidence_query"

RANKABLE_BUCKETS = (GATE.PRIMARY_BUCKET, GATE.WARNING_BUCKET)
NON_RANKABLE_BUCKETS = (GATE.AUDIT_BUCKET, GATE.REJECTED_BUCKET)


class GateAuditError(RuntimeError):
    """Un invariante del gate integrato non regge sotto rerun."""


def _atomic(claim: Mapping[str, Any]) -> AtomicInterventionClaim:
    return AtomicInterventionClaim(
        claim_id=claim["claim_id"],
        parent_id=claim["parent_id"],
        graph_evidence_id=claim["graph_evidence_id"],
        intervention=claim["intervention"],
        biomarker=claim["biomarker"],
        disease_scope=claim["disease_scope"],
        direction=claim["direction"],
        polarity=claim["polarity"],
        source_unit_ids=tuple(claim.get("source_unit_ids") or ()),
        review_status=claim.get("review_status", "not_reviewed"),
        evidence_setting=claim.get("evidence_setting"),
        deprecated=bool(claim.get("deprecated")),
        mapping_pending=bool(claim.get("mapping_pending")),
    )


def _regimen(claim: Mapping[str, Any]) -> RegimenClaim:
    return RegimenClaim(
        claim_id=claim["claim_id"],
        parent_id=claim["parent_id"],
        graph_evidence_id=claim["graph_evidence_id"],
        regimen_components=tuple(claim["regimen_components"]),
        biomarker=claim["biomarker"],
        disease_scope=claim["disease_scope"],
        direction=claim["direction"],
        polarity=claim["polarity"],
        source_unit_ids=tuple(claim.get("source_unit_ids") or ()),
        review_status=claim.get("review_status", "not_reviewed"),
        evidence_setting=claim.get("evidence_setting"),
    )


def _aggregate(claim: Mapping[str, Any]) -> AggregateInterventionClaim:
    return AggregateInterventionClaim(
        claim_id=claim["claim_id"],
        parent_id=claim["parent_id"],
        graph_evidence_id=claim["graph_evidence_id"],
        aggregate_type=claim["aggregate_type"],
        aggregate_label=claim["aggregate_label"],
        aggregate_members_literal=tuple(claim.get("aggregate_members_literal") or ()),
        biomarker=claim["biomarker"],
        disease_scope=claim["disease_scope"],
        direction=claim["direction"],
        polarity=claim["polarity"],
        source_unit_ids=tuple(claim.get("source_unit_ids") or ()),
        review_status=claim.get("review_status", "not_reviewed"),
        evidence_setting=claim.get("evidence_setting"),
    )


def _unsupported(row: Mapping[str, Any]) -> UnsupportedAssociation:
    return UnsupportedAssociation(
        association_id=row["association_id"],
        parent_id=row["parent_id"],
        graph_evidence_id=row["graph_evidence_id"],
        intervention_literal=row["intervention_literal"],
        biomarker=row["biomarker"],
        source_unit_ids=tuple(row.get("source_unit_ids") or ()),
        reason_codes=tuple(row.get("reason_codes") or ()),
        review_status=row.get("review_status", "adjudicated"),
    )


def _unresolved(row: Mapping[str, Any]) -> UnresolvedAssociation:
    return UnresolvedAssociation(
        association_id=row["association_id"],
        parent_id=row["parent_id"],
        graph_evidence_id=row["graph_evidence_id"],
        intervention_literal=row["intervention_literal"],
        biomarker=row["biomarker"],
        source_unit_ids=tuple(row.get("source_unit_ids") or ()),
        unresolved_reason_codes=tuple(row.get("unresolved_reason_codes") or ()),
        terminology_status=row.get("terminology_status", ""),
        review_status=row.get("review_status", "adjudicated"),
    )


def _first(rows: Sequence[Mapping[str, Any]], **match: Any) -> Mapping[str, Any]:
    for row in rows:
        if all(row.get(key) == value for key, value in match.items()):
            return row
    raise GateAuditError(f"nessuna riga della 1.3 soddisfa {match}")


def _exact_query(claim: Mapping[str, Any], **override: Any) -> dict[str, Any]:
    """Query che combacia su ogni asse con il claim dato."""
    query = {
        "query_id": "audit-exact",
        "query_domain": THERAPEUTIC,
        "biomarker": claim["biomarker"],
        "disease": claim["disease_scope"],
        "direction": claim["direction"],
        "polarity": claim["polarity"],
        "interventions": [claim.get("canonical_intervention") or claim.get("intervention")],
    }
    query.update(override)
    return query


def build_cases(repository: Mapping[str, Any]) -> list[dict[str, Any]]:
    """I sette casi richiesti, costruiti su oggetti reali della 1.3."""
    claims = repository["claims"]
    atomic = _first(claims, claim_type="atomic_intervention_claim", migration_origin="adjudicated_review")
    regimen_row = _first(claims, claim_type="regimen_claim")
    unsupported_row = repository["unsupported"][0]
    retired_row = _first(repository["deprecated"], claim_type="aggregate_intervention_claim")

    # Un claim il cui scope e' un sottotipo della disease chiesta: la relazione
    # e' `claim_is_child_of_query`, che non e' exact in nessuna modalita'.
    child = _first(claims, disease_scope="Intrahepatic Cholangiocarcinoma")

    # Il caso mapping-pending richiede un claim il cui intervento formi davvero
    # una coppia pending con il termine della query. Sceglierne uno qualunque
    # produrrebbe `incompatible` — un rifiuto nativo — e il caso verificherebbe
    # il gate sbagliato: e' esattamente l'errore in cui questa selezione e'
    # caduta la prima volta.
    mapping_pending_source = next(
        (
            claim
            for claim in claims
            if claim["claim_type"] == "atomic_intervention_claim"
            and is_pending_pair(PENDING_QUERY_TERM, claim["canonical_intervention"])
        ),
        None,
    )
    if mapping_pending_source is None:
        raise GateAuditError(
            f"nessun claim atomico forma una coppia pending con {PENDING_QUERY_TERM!r}"
        )

    cases: list[dict[str, Any]] = [
        {
            "case_id": "exact-disease-biomarker-incompatible",
            "expected_blocking_gate": "biomarker",
            "expected_bucket": GATE.REJECTED_BUCKET,
            "object": _atomic(atomic),
            "query": _exact_query(atomic, biomarker="BRAF V600E"),
            "scenario": "disease exact, biomarcatore incompatibile",
        },
        {
            "case_id": "disease-child-biomarker-exact",
            "expected_blocking_gate": "disease",
            "expected_bucket": GATE.WARNING_BUCKET,
            "object": _atomic(child) if child["claim_type"] == "atomic_intervention_claim" else _aggregate(child),
            "query": _exact_query(child, disease="Cholangiocarcinoma"),
            "scenario": "disease child, biomarcatore exact",
        },
        {
            "case_id": "disease-exact-regimen-component",
            "expected_blocking_gate": "intervention",
            "expected_bucket": GATE.WARNING_BUCKET,
            "object": _regimen(regimen_row),
            "query": _exact_query(
                regimen_row, interventions=[regimen_row["regimen_components"][0]]
            ),
            "scenario": "disease exact, query su un componente del regime",
        },
        {
            "case_id": "unsupported-with-everything-exact",
            "expected_blocking_gate": "claim_status",
            "expected_bucket": GATE.AUDIT_BUCKET,
            "object": _unsupported(unsupported_row),
            "query": {
                "query_id": "audit-exact",
                "query_domain": THERAPEUTIC,
                "biomarker": unsupported_row["biomarker"],
                "interventions": [unsupported_row["intervention_literal"]],
            },
            "scenario": "associazione non sostenuta con tutti gli assi exact",
        },
        {
            "case_id": "deprecated-with-everything-exact",
            "expected_blocking_gate": "claim_status",
            "expected_bucket": GATE.AUDIT_BUCKET,
            "object": replace(_aggregate(retired_row), deprecated=True),
            "query": _exact_query(
                retired_row,
                interventions=list(retired_row.get("aggregate_members_literal") or ()),
            ),
            "scenario": "claim ritirato con tutti gli assi exact",
        },
        {
            "case_id": "mapping-pending-with-everything-exact",
            "expected_blocking_gate": "intervention",
            "expected_bucket": GATE.AUDIT_BUCKET,
            "object": _atomic(mapping_pending_source),
            # `BGJ398` e `infigratinib` sono una coppia pending nel contratto
            # congelato: la query li tratta come lo stesso farmaco, il gate no.
            "query": _exact_query(
                mapping_pending_source, interventions=[PENDING_QUERY_TERM]
            ),
            "scenario": "mapping terminologico non approvato, tutto il resto exact",
        },
        {
            "case_id": "arbitrarily-high-score",
            "expected_blocking_gate": None,
            "expected_bucket": None,
            "object": _atomic(atomic),
            "query": _exact_query(atomic, biomarker="BRAF V600E"),
            "scenario": "punteggio arbitrariamente alto su un esito respinto",
        },
    ]
    return cases


def _mapping_pending_case(case: Mapping[str, Any]) -> bool:
    return case["case_id"] == "mapping-pending-with-everything-exact"


def evaluate_case(case: Mapping[str, Any], mode: str) -> dict[str, Any]:
    """Un caso in una modalita', con l'invariante di score verificato sul posto."""
    result = GATE.evaluate(case["query"], case["object"], mode=mode)
    bypass: str | None = None
    try:
        GATE.check_no_score_survives_a_blocking_gate(result, ARBITRARILY_HIGH_SCORE)
    except GATE.IntegratedGateError as error:  # pragma: no cover - difeso dal test
        bypass = str(error)

    eligibility = dict(result.score_eligibility)
    score_flags = {
        key: bool(value)
        for key, value in eligibility.items()
        if key.endswith("_eligible")
    }
    return {
        "audit_only": result.audit_only,
        "blocking_gates": list(result.blocking_gates),
        "case_id": case["case_id"],
        "claim_id": result.claim_id,
        "claim_type": result.claim_type,
        "expected_blocking_gate": case["expected_blocking_gate"],
        "expected_bucket": case["expected_bucket"],
        "final_bucket": result.final_bucket,
        "final_ranking_eligible": result.final_ranking_eligible,
        "gate_bypass": bypass,
        "gate_order": list(GATE_ORDER),
        "hypothetical_score": ARBITRARILY_HIGH_SCORE,
        "policy_mode": mode,
        "positive_score_forbidden": bool(eligibility.get("positive_score_forbidden")),
        "primary_candidate_eligible": result.primary_candidate_eligible,
        "qualified_score_eligible": result.qualified_score_eligible,
        "reason_codes": list(result.reason_codes),
        "rejected_by_native_constraints": result.rejected_by_native_constraints,
        "relation_type": result.disease_match_result.get("relation_type"),
        "scenario": case["scenario"],
        "score_flags": score_flags,
        "score_flags_cleared": (
            not any(score_flags.values())
            if result.final_bucket in NON_RANKABLE_BUCKETS
            else None
        ),
        "structural_score_eligible": result.structural_score_eligible,
        "warning_eligible": result.warning_eligible,
    }


def case_rows(repository: Mapping[str, Any]) -> list[dict[str, Any]]:
    cases = build_cases(repository)
    rows = [
        evaluate_case(case, mode)
        for case in cases
        for mode in DISEASE.MODES
    ]
    return sorted(rows, key=lambda row: (row["case_id"], row["policy_mode"]))


def _precedence_holds(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Il bucket finale non e' mai piu' permissivo del gate piu' restrittivo."""
    return all(
        not (row["primary_candidate_eligible"] and row["blocking_gates"]) for row in rows
    )


def audit(repository: Mapping[str, Any]) -> dict[str, Any]:
    rows = case_rows(repository)
    bypasses = [row for row in rows if row["gate_bypass"]]
    leaked = [
        row
        for row in rows
        if row["final_bucket"] in NON_RANKABLE_BUCKETS and any(row["score_flags"].values())
    ]
    primary_with_blocking = [
        row for row in rows if row["primary_candidate_eligible"] and row["blocking_gates"]
    ]
    warning_outside_mode = [
        row
        for row in rows
        if row["final_bucket"] == GATE.WARNING_BUCKET
        and not row["qualified_score_eligible"]
        and row["score_flags"].get("qualified_score_eligible")
    ]
    unexpected_bucket = [
        {
            "case_id": row["case_id"],
            "expected": row["expected_bucket"],
            "observed": row["final_bucket"],
            "policy_mode": row["policy_mode"],
        }
        for row in rows
        if row["expected_bucket"] is not None
        and row["policy_mode"] == DISEASE.DEFAULT_POLICY_MODE
        and row["final_bucket"] != row["expected_bucket"]
    ]
    unexpected_gate = [
        {
            "case_id": row["case_id"],
            "expected": row["expected_blocking_gate"],
            "observed": row["blocking_gates"],
        }
        for row in rows
        if row["expected_blocking_gate"] is not None
        and row["policy_mode"] == DISEASE.DEFAULT_POLICY_MODE
        and row["expected_blocking_gate"] not in row["blocking_gates"]
    ]

    primary_by_case = {
        row["case_id"]: {
            other["primary_candidate_eligible"]
            for other in rows
            if other["case_id"] == row["case_id"]
        }
        for row in rows
    }
    return {
        "bucket_precedence": list(GATE.BUCKET_PRECEDENCE),
        "cases_evaluated": len(rows),
        "gate_bypasses": len(bypasses),
        "gate_bypass_details": [row["gate_bypass"] for row in bypasses],
        "gate_order": list(GATE_ORDER),
        "gate_version": GATE.GATE_VERSION,
        "hypothetical_score": ARBITRARILY_HIGH_SCORE,
        "integrated_gate_invariants_hold": bool(
            not bypasses
            and not leaked
            and not primary_with_blocking
            and not warning_outside_mode
            and not unexpected_bucket
            and not unexpected_gate
            and _precedence_holds(rows)
        ),
        "modes": list(DISEASE.MODES),
        "primary_bucket_is_mode_invariant": all(
            len(values) == 1 for values in primary_by_case.values()
        ),
        "primary_with_blocking_gate": len(primary_with_blocking),
        "score_flags_leaked_outside_rankable_buckets": len(leaked),
        "unexpected_blocking_gate": unexpected_gate,
        "unexpected_bucket": unexpected_bucket,
    }


__all__ = [
    "ARBITRARILY_HIGH_SCORE",
    "GATE_ORDER",
    "NON_RANKABLE_BUCKETS",
    "RANKABLE_BUCKETS",
    "GateAuditError",
    "audit",
    "build_cases",
    "case_rows",
    "evaluate_case",
]
