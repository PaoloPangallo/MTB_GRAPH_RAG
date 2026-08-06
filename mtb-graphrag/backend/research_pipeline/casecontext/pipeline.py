"""Catena deterministica fra il parser e il retrieval.

Un solo punto di ingresso per: menzioni tipizzate → verifica semantica →
contraddizioni → eligibility gate. Nessun LLM è coinvolto in nessuno di questi
passi.

Serve sia all'orchestratore sia all'harness di valutazione, che devono eseguire
**esattamente la stessa** catena: duplicarla renderebbe il benchmark una misura
di un'altra pipeline.
"""

from __future__ import annotations

from typing import Any

from ..eligibility.gate import EligibilityDecision, evaluate as evaluate_gate
from . import match_verifier
from .contradictions import detect as detect_contradictions
from .control_instructions import detect_control_instruction_spans
from .mentions import build_mentions, to_contract
from .semantic_verifier import verify as verify_semantics

DETERMINISTIC_CHAIN_VERSION = "casecontext-deterministic-chain/1.0"


def run(
    clinical_text: str,
    case_context: dict[str, Any] | None,
    transport_ok: bool = True,
) -> dict[str, Any]:
    """Esegue la catena deterministica completa.

    ``case_context`` è l'output grezzo del parser (contratto 1.0). Restituisce
    il CaseContext 2.0, i record di verifica e la decisione del gate.
    """
    text = clinical_text or ""
    control_spans = detect_control_instruction_spans(text)

    if not isinstance(case_context, dict):
        decision = evaluate_gate(text, None, [], control_spans, [], transport_ok=False)
        return {
            "contract_version": DETERMINISTIC_CHAIN_VERSION,
            "case_context_v2": None,
            "mentions": [],
            "textual_records": [],
            "semantic_records": [],
            "contradictions": [],
            "control_instruction_spans": control_spans,
            "eligibility": decision.to_dict(),
        }

    # A — verifica testuale, invariata: resta il gate di letteralità.
    textual = match_verifier.verify_case_context(case_context, text)
    textual_ok, textual_warnings = match_verifier.essential_fields_pass(textual)

    # Menzioni tipizzate + verifica semantica (tipo, ruolo, asserzione).
    mentions = build_mentions(case_context, text, control_spans)
    mentions, semantic_records = verify_semantics(mentions)

    # Contraddizioni deterministiche.
    contradictions = detect_contradictions(text, mentions, case_context)

    decision = evaluate_gate(
        text, case_context, mentions, control_spans, contradictions,
        transport_ok=transport_ok,
    )
    if not textual_ok and decision.eligible:
        # La verifica testuale conserva il potere di veto: un mismatch letterale
        # non può essere superato da una verifica semantica favorevole.
        decision = evaluate_gate(text, case_context, [], control_spans, contradictions,
                                 transport_ok=transport_ok)
        decision.reason_codes = ["TEXTUAL_MATCH_VERIFIER_MISMATCH"] + decision.reason_codes

    return {
        "contract_version": DETERMINISTIC_CHAIN_VERSION,
        "case_context_v2": to_contract(
            case_context, mentions, control_spans,
            [c.to_dict() for c in contradictions]),
        "mentions": [m.to_dict() for m in mentions],
        "textual_records": [r.to_dict() for r in textual],
        "textual_essential_pass": textual_ok,
        "textual_warnings": list(textual_warnings),
        "semantic_records": semantic_records,
        "contradictions": [c.to_dict() for c in contradictions],
        "control_instruction_spans": control_spans,
        "eligibility": decision.to_dict(),
    }
