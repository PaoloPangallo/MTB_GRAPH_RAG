"""Harness di valutazione del CaseContext Parser.

Importa i **moduli canonici** del runtime — non li duplica e non li modifica:

* ``backend.research_pipeline.casecontext.parser.call_parser``
* ``backend.research_pipeline.casecontext.match_verifier``

Il test si ferma dopo *parser → match verifier → decisione di routing*. Gli
stage documentali, il retrieval e l'enrichment (Gemma) **non sono importati né
invocati**: le chiamate downstream proibite sono quindi zero per costruzione, e
il contatore lo registra come fatto verificabile, non come speranza.

Politica di retry: nessun retry semantico. Il transport del runtime esegue già un
solo retry per errori infrastrutturali (timeout, 5xx), che viene contato e
riportato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.research_pipeline.casecontext import match_verifier as verifier
from backend.research_pipeline.casecontext import parser as canonical_parser
from backend.research_pipeline.casecontext import prompt as canonical_prompt

#: Stage che questo harness non deve mai raggiungere.
FORBIDDEN_STAGES = ("retrieval", "document_resolution", "paper_selection", "enrichment")

#: Esito di trasporto che il runtime considera valido
#: (``enrichment.transport.transport_result``). Ogni altro valore —
#: ``FORCED_TOOL_IGNORED``, ``INVALID_TOOL_ARGUMENTS``, ``TEXT_RESPONSE``,
#: ``HTTP_ERROR``, ``TIMEOUT`` — è un fallimento, ma **non tutti** sono
#: infrastrutturali: ``FORCED_TOOL_IGNORED`` e ``INVALID_TOOL_ARGUMENTS``
#: descrivono il comportamento del modello e vanno contati come tali.
TRANSPORT_OK = "FORCED_TOOL_VALID"

#: Fallimenti imputabili all'infrastruttura, non al modello.
INFRASTRUCTURE_FAILURES = ("HTTP_ERROR", "TIMEOUT")


@dataclass
class CallBudget:
    """Budget di chiamate al parser, applicato in modo duro."""

    max_calls: int
    used: int = 0

    def spend(self, case_id: str) -> None:
        if self.used >= self.max_calls:
            raise RuntimeError(
                f"budget di chiamate al parser esaurito ({self.max_calls}); "
                f"rifiutata la chiamata per {case_id}"
            )
        self.used += 1


@dataclass
class StageTracker:
    """Registra ogni stage downstream eventualmente invocato.

    Nessuno stage downstream è importato da questo modulo; il tracker esiste per
    rendere l'assenza *misurata* invece che assunta.
    """

    invoked: list[str] = field(default_factory=list)

    def record(self, stage: str) -> None:
        self.invoked.append(stage)

    @property
    def forbidden_calls(self) -> int:
        return sum(1 for stage in self.invoked if stage in FORBIDDEN_STAGES)


def routing_decision(essential_ok: bool, transport_result: str) -> str:
    """Decisione di routing secondo le regole *del runtime*.

    Riproduce ``orchestrator``: se il transport fallisce la run si ferma; se
    ``essential_fields_pass`` è falso si ferma con ``CASECONTEXT_MISMATCH``;
    altrimenti si procede al retrieval.

    Non introduce stati nuovi. In particolare **non** esiste uno stato
    ``OUT_OF_SCOPE``: la sua assenza è uno dei risultati di RQ4.
    """
    if transport_result in INFRASTRUCTURE_FAILURES:
        return "STOP_TRANSPORT_FAILURE"
    if transport_result != TRANSPORT_OK:
        # Il modello ha risposto, ma non con una tool call conforme: il runtime
        # non ottiene un CaseContext e la run si ferma comunque.
        return "STOP_NO_VALID_CASECONTEXT"
    return "PROCEED_TO_RETRIEVAL" if essential_ok else "STOP_CASECONTEXT_MISMATCH"


def run_case(case: dict[str, Any], run_index: int, budget: CallBudget,
             tracker: StageTracker) -> dict[str, Any]:
    """Esegue un caso: parser reale, verifier reale, nessuno stage downstream."""
    case_id = case["case_id"]
    text = case["text"]

    budget.spend(case_id)
    started = datetime.now(timezone.utc).isoformat()
    result = canonical_parser.call_parser(case_id, text, run_index=run_index)

    case_context = result.get("case_context_raw")
    transport = result.get("transport_result")

    if isinstance(case_context, dict):
        records = verifier.verify_case_context(case_context, text)
        essential_ok, warnings = verifier.essential_fields_pass(records)
        record_dicts = [r.to_dict() for r in records]
    else:
        records, record_dicts, warnings = [], [], []
        essential_ok = False

    return {
        "case_id": case_id,
        "category": case["category"],
        "run_index": run_index,
        "started_at": started,
        "model": result.get("model"),
        "provider_endpoint": result.get("endpoint"),
        "delivery_transport": result.get("delivery_transport"),
        "prompt_version": result.get("prompt_version"),
        "prompt_hash": canonical_prompt.prompt_hash(),
        "execution_mode": "LIVE",
        "transport_result": transport,
        "transport_reason_codes": result.get("transport_reason_codes"),
        "finish_reason": result.get("finish_reason"),
        "status_code": result.get("status_code"),
        "retry_count": result.get("retry_count"),
        "latency_ms": result.get("latency_ms"),
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "raw_response_hash": result.get("raw_response_hash"),
        "case_context": case_context,
        "verifier_records": record_dicts,
        "verifier_essential_pass": essential_ok,
        "verifier_warnings": list(warnings),
        "routing_decision": routing_decision(essential_ok, transport or ""),
        "downstream_stages_invoked": list(tracker.invoked),
        "forbidden_downstream_calls": tracker.forbidden_calls,
    }
