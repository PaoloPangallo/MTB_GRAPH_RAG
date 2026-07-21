"""Vocabolario degli eventi e costruzione dei payload del ledger.

Entrambe le architetture emettono gli **stessi tipi di evento**: è ciò che
rende il replay cieco rispetto all'orchestrazione e il confronto sensato.
L'unica differenza osservabile è l'attore di ``plan_decision`` e il numero di
chiamate al planner.

Il ledger non è un archivio documentale. I payload sono sanitizzati (nessuna
credenziale può finire in un archivio append-only, dove non sarebbe
cancellabile) e limitati in dimensione: si conservano i campi strutturati che
il replay usa davvero più i riferimenti risolvibili, non i testi lunghi già
disponibili altrove.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping, Sequence

# --- Tipi di evento ---------------------------------------------------------

RUN_STARTED = "run_started"
ORCHESTRATION_STARTED = "orchestration_started"
PLAN_DECISION = "plan_decision"
TOOL_STARTED = "tool_started"
TOOL_COMPLETED = "tool_completed"
TOOL_FAILED = "tool_failed"
PLANNER_FALLBACK_TRIGGERED = "planner_fallback_triggered"
COLLECTION_COMPLETED = "collection_completed"
CANONICAL_VIEW_CREATED = "canonical_view_created"
PROJECTION_CREATED = "projection_created"
CANDIDATE_REPORT_RENDERED = "candidate_report_rendered"
STRUCTURAL_VERIFICATION_COMPLETED = "structural_verification_completed"
SOURCE_VERIFICATION_COMPLETED = "source_verification_completed"
APPLICABILITY_EVALUATED = "applicability_evaluated"
REPAIR_PLANNED = "repair_planned"
REPAIR_EXECUTED = "repair_executed"
REPAIR_FAILED = "repair_failed"
ESCALATION_RAISED = "escalation_raised"
VERIFIED_REPORT_RENDERED = "verified_report_rendered"
NARRATION_RENDERED = "narration_rendered"
DOSSIER_BUILT = "dossier_built"
RUN_COMPLETED = "run_completed"

#: Eventi che il replay deve saper interpretare per ricostruire la vista.
REPLAYABLE_EVENT_TYPES = frozenset({TOOL_COMPLETED})

# --- Attori -----------------------------------------------------------------

ACTOR_CONTROLLER = "controller"
ACTOR_FIXED_PLAN = "fixed_plan_controller"
ACTOR_PLANNER = "llm_planner"
ACTOR_CANONICALIZER = "canonicalizer"
ACTOR_PROJECTOR = "projector"
ACTOR_RENDERER = "deterministic_renderer"
ACTOR_STRUCTURAL_VERIFIER = "structural_verifier"
ACTOR_SOURCE_VERIFIER = "source_verifier"
ACTOR_REPAIR_PLANNER = "repair_planner"

# --- Bounding e sanitizzazione ---------------------------------------------

#: Limite per payload serializzato. Oltre questa soglia gli elementi in coda
#: vengono omessi e l'omissione è registrata esplicitamente.
MAX_EVENT_PAYLOAD_BYTES = 64_000

#: Oltre questa lunghezza un campo testuale non viene persistito per esteso:
#: si conservano lunghezza e riferimento, non il testo.
MAX_TEXT_FIELD_CHARS = 600

#: Campi il cui contenuto integrale non serve al replay. Gli abstract PubMed
#: sono già ottenibili dal PMID e dalla cache del profilo sorgente: duplicarli
#: nel ledger gonfia il file senza aggiungere verificabilità.
_DROPPED_TEXT_FIELDS = frozenset({"abstract", "pubmed_abstract", "full_text", "body"})

# L'ordine conta: lo schema "Bearer <token>" va consumato per primo, altrimenti
# il pattern chiave/valore mangia soltanto la parola "Bearer" e lascia il token
# in chiaro.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/@]+:[^\s/@]+@\S+"),  # credenziali in URL
    re.compile(r"(?i)\b(api[-_ ]?key|token|password|passwd|secret|authorization)\b\s*[=:]\s*\S+"),
)

_REDACTED = "[redatto]"


def sanitize_text(value: str) -> str:
    """Rimuove credenziali riconoscibili da un testo destinato al ledger.

    Il ledger è append-only: un segreto che vi entra non può più esserne
    rimosso. La sanitizzazione va quindi applicata **prima** della scrittura,
    non a valle in lettura.
    """
    sanitized = value
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub(_REDACTED, sanitized)
    return sanitized


def _bound_value(key: str, value: Any) -> Any:
    if key in _DROPPED_TEXT_FIELDS and isinstance(value, str) and value:
        return {"omitted": True, "chars": len(value), "reason": "non necessario al replay"}
    if isinstance(value, str):
        clean = sanitize_text(value)
        if len(clean) > MAX_TEXT_FIELD_CHARS:
            return clean[:MAX_TEXT_FIELD_CHARS] + f"… [troncato, {len(clean)} caratteri]"
        return clean
    if isinstance(value, Mapping):
        return {str(k): _bound_value(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_bound_value(key, item) for item in value]
    return value


def sanitize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Applica sanitizzazione e bounding a un singolo record strutturato."""
    return {str(key): _bound_value(str(key), value) for key, value in record.items()}


def bound_records(records: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Sanitizza e limita una lista di record.

    Restituisce ``(record_conservati, numero_omessi)``. L'omissione non è mai
    silenziosa: il chiamante la registra nel payload, così il degrado della
    fedeltà di replay resta visibile.
    """
    kept: list[dict[str, Any]] = []
    size = 0
    for index, record in enumerate(records):
        bounded = sanitize_record(record)
        size += len(json.dumps(bounded, ensure_ascii=False, default=str))
        if size > MAX_EVENT_PAYLOAD_BYTES and index > 0:
            return kept, len(records) - len(kept)
        kept.append(bounded)
    return kept, 0


# --- Costruttori di payload -------------------------------------------------


def plan_decision_payload(
    *,
    step: int,
    selected_tool: str,
    allowed_tools: Iterable[str],
    rationale: str,
    planning_mode: str,
    fallback: bool = False,
) -> dict[str, Any]:
    return {
        "step": step,
        "selected_tool": selected_tool,
        "allowed_tools": sorted(allowed_tools),
        "rationale": sanitize_text(rationale),
        "planning_mode": planning_mode,
        "fallback": fallback,
    }


def tool_completed_payload(
    *,
    tool: str,
    record_kind: str,
    records: Sequence[Mapping[str, Any]],
    completeness_status: str = "complete",
    pagination_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Payload di ``tool_completed``: i record strutturati servono al replay.

    Un conteggio non basterebbe: senza i record la vista canonica non sarebbe
    ricostruibile dal solo ledger, e il replay resterebbe una dichiarazione
    anziché una proprietà verificabile.
    """
    kept, omitted = bound_records(records)
    payload: dict[str, Any] = {
        "tool": tool,
        "record_kind": record_kind,
        "records": kept,
        "record_count": len(records),
        "completeness_status": "truncated" if omitted else completeness_status,
    }
    if omitted:
        payload["payload_truncated"] = True
        payload["omitted_records"] = omitted
    if pagination_state is not None:
        payload["pagination_state"] = dict(pagination_state)
    return payload


def structural_verification_payload(verdict: Any) -> dict[str, Any]:
    return {
        "stage": verdict.stage,
        "status": verdict.status,
        "coverage": round(verdict.coverage, 4),
        "violations": [
            {
                "code": v.code,
                "severity": v.severity,
                "detail": sanitize_text(v.detail),
                "canonical_record_id": v.canonical_record_id,
            }
            for v in verdict.violations
        ],
        "warnings": [{"code": w.code, "detail": sanitize_text(w.detail)} for w in verdict.warnings],
        "missing_claims": list(verdict.missing_claims),
        "unsupported_claims": list(verdict.unsupported_claims),
        "spurious_citations": list(verdict.spurious_citations),
        "requires_repair": verdict.requires_repair,
        "requires_human_review": verdict.requires_human_review,
    }
