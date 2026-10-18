"""Optional post-dossier presentation. Cannot alter canonical evidence decisions."""

from __future__ import annotations

from typing import Any

from .. import events as ev, execution_mode as em
from ..contracts import StageProducer
from ..live_providers import LiveStageFailed
from ..recording import _deterministic
from . import input_projection as narrative_projection, prompt as narrative_prompt
from . import verifier as narrative_verifier, presentation as narrative_presentation


def narrate_and_verify(
    recorder,
    case_id,
    canonical_dossier,
    call_narrator_fn,
    verify_narrative_fn,
    canonical,
    replay_origin,
    narrative_verifier_mode: str = "CANONICAL",
) -> None:
    """Stage 14 e 15. Separati dallo stage 13 in modo osservabile.

    L'ordine è il contratto: il dossier canonico è già stato costruito ed emesso
    con ``DOSSIER_BUILT`` prima che il Narrator venga invocato.
    """
    narrator_input = narrative_projection.build_narrator_input(canonical_dossier)

    # --- STAGE 14: narrazione (LLM) -----------------------------------------
    narrator_producer = StageProducer(
        kind="LLM",
        component="dossier_narrator",
        version=narrative_prompt.NARRATOR_PROMPT_VERSION,
        model="unknown",
        prompt_version=narrative_prompt.NARRATOR_PROMPT_VERSION,
    )
    recorder.start("stage_14_narrator", narrator_producer)

    call: dict[str, Any] | None = None
    narrative = None
    narration_error: str | None = None
    if call_narrator_fn is None:
        narration_error = "NARRATOR_NOT_CONFIGURED"
    else:
        try:
            call = call_narrator_fn(case_id, narrator_input)
            narrative = (call or {}).get("narrative")
        except LiveStageFailed as failure:
            narration_error = failure.reason_code
            call = failure.call_result
        except Exception as exc:  # noqa: BLE001 — un guasto resta visibile
            narration_error = f"{type(exc).__name__}"

    if call is not None:
        narrator_producer = StageProducer(
            kind="LLM",
            component="dossier_narrator",
            version=narrative_prompt.NARRATOR_PROMPT_VERSION,
            model=call.get("model") or "unknown",
            prompt_version=call.get("prompt_version")
            or narrative_prompt.NARRATOR_PROMPT_VERSION,
            transport_version=call.get("transport_version"),
        )

    transport_ok = bool(
        call and call.get("transport_result") == "FORCED_TOOL_VALID" and narrative
    )
    narration_reasons = tuple(
        [narration_error]
        if narration_error
        else (
            []
            if transport_ok
            else [str((call or {}).get("transport_result") or "NARRATION_FAILED")]
        )
    )
    recorder.finish(
        "stage_14_narrator",
        narrator_producer,
        status="SUCCEEDED" if transport_ok else "WARNING",
        artifact_origin=(
            (em.GENERATED_NOW if canonical else replay_origin)
            if call
            else em.NOT_EXECUTED
        ),
        domain_event=ev.NARRATION_GENERATED if transport_ok else None,
        reason_codes=narration_reasons,
        output_preview={
            "narrator_input_hash": narrator_input["narrator_input_hash"],
            "narrator_input_contract": narrator_input["contract_version"],
            "candidates_projected": narrator_input["counts"]["candidates"],
            "transport_result": (call or {}).get("transport_result"),
            "narrative": narrative,
            "generation_mode": (call or {}).get("generation_mode"),
            "model_plan_valid": (call or {}).get("model_plan_valid"),
            "deterministic_fallback": (call or {}).get("deterministic_fallback"),
            "attempts": (call or {}).get("attempts"),
            "token_usage_complete": (call or {}).get("token_usage_complete"),
        },
        metrics={
            "latency_ms": (call or {}).get("latency_ms"),
            "input_tokens": (call or {}).get("input_tokens"),
            "output_tokens": (call or {}).get("output_tokens"),
            "retry_count": (call or {}).get("retry_count"),
            "real_llm_calls": (
                call.get("model_call_count", 1) if (call and canonical)
                else None if canonical and call_narrator_fn is not None else 0
            ),
        },
    )

    # --- STAGE 15: verifica (DETERMINISTICO) --------------------------------
    effective_verifier_version = narrative_verifier.VERIFIER_VERSION
    if isinstance(narrative, dict) and "controlled_contract" in narrative:
        from .controlled import CONTROLLED_VERSION

        effective_verifier_version = CONTROLLED_VERSION
    p = _deterministic("narrative_verifier", effective_verifier_version)
    recorder.start("stage_15_narrative_verifier", p)
    if narrative_verifier_mode == "OFFLINE_ABLATION_BYPASS":
        result = {
            "status": "VERIFIER_BYPASSED_FOR_OFFLINE_ABLATION",
            "reason_codes": ["VERIFIER_BYPASSED_FOR_OFFLINE_ABLATION"],
            "presentation": "PRESENTED_IN_OFFLINE_ABLATION",
        }
        verified = False
        recorder.finish(
            "stage_15_narrative_verifier",
            p,
            status="SKIPPED",
            reason_codes=("VERIFIER_BYPASSED_FOR_OFFLINE_ABLATION",),
            output_preview={
                "verification": result,
                "presentation_mode": "PRESENTED_IN_OFFLINE_ABLATION",
            },
        )
        return
    if narrative_verifier_mode != "CANONICAL":
        raise ValueError(f"unknown narrative_verifier_mode: {narrative_verifier_mode}")
    verifier = verify_narrative_fn or narrative_verifier.verify_narrative
    try:
        result = verifier(canonical_dossier, narrator_input, narrative)
    except (
        Exception
    ):  # noqa: BLE001 - presentation failure must not invalidate stage 13
        result = {
            "status": narrative_verifier.FAIL,
            "reason_codes": ["NARRATIVE_VERIFIER_INTERNAL_ERROR"],
            "candidate_results": [],
            "verifier_version": narrative_verifier.VERIFIER_VERSION,
            "input_hash": narrator_input["narrator_input_hash"],
            "narrative_hash": (narrative or {}).get("narrative_hash", ""),
        }
    verified = result["status"] == narrative_verifier.PASS

    deterministic_narrative = (
        (call or {}).get("deterministic_fallback") if not verified else None
    )
    deterministic_verification = None
    if deterministic_narrative is not None:
        # The fallback must independently satisfy the same closed contract.
        # It never changes the model's verdict or counts as model success.
        from .controlled import verify_controlled

        deterministic_verification = verify_controlled(
            narrator_input, deterministic_narrative
        )
        if deterministic_verification.get("status") != narrative_verifier.PASS:
            deterministic_narrative = None

    # Regola non negoziabile: una narrativa non verificata non viene mostrata.
    # Nessun secondo passaggio LLM, nessun retry semantico.
    try:
        presentation = narrative_presentation.build_narrative_presentation(
            canonical_dossier,
            narrative if verified else deterministic_narrative,
            result if verified else deterministic_verification or result,
        )
        if deterministic_narrative is not None:
            presentation["presentation_mode"] = "DETERMINISTIC_NARRATIVE_FALLBACK"
            presentation["generation_origin"] = "DETERMINISTIC_FALLBACK"
    except Exception:  # noqa: BLE001 - presentation must not invalidate dossier
        presentation_error = "NARRATIVE_PRESENTATION_INTERNAL_ERROR"
        verified = False
        deterministic_narrative = None
        result = {
            **result,
            "status": narrative_verifier.FAIL,
            "reason_codes": sorted(
                set([*(result.get("reason_codes") or []), presentation_error])
            ),
        }
        presentation = None
    recorder.finish(
        "stage_15_narrative_verifier",
        p,
        status="SUCCEEDED" if verified else "WARNING",
        domain_event=ev.NARRATION_VERIFIED if verified else ev.NARRATION_REJECTED,
        reason_codes=tuple(result["reason_codes"]),
        output_preview={
            "verification": result,
            "narrative_available": verified,
            "model_narrative_verified": verified,
            "explanation_available": verified or deterministic_narrative is not None,
            "presentation_mode": (
                "VERIFIED_NARRATIVE"
                if verified
                else (
                    "DETERMINISTIC_NARRATIVE_FALLBACK"
                    if deterministic_narrative is not None
                    else "STRUCTURED_DOSSIER_FALLBACK"
                )
            ),
            "verified_narrative": narrative if verified else None,
            "deterministic_narrative": deterministic_narrative,
            "deterministic_verification": deterministic_verification,
            "presentation": presentation,
            "fallback_reason": (
                None
                if verified
                else (list(result["reason_codes"]) or ["NARRATION_UNAVAILABLE"])
            ),
        },
    )
    if not verified:
        # ``stage_id`` viaggia nel payload come in ogni altro evento di stage:
        # è nel preimage dell'hash del ledger, e un evento che non lo porta non
        # sarebbe attribuibile.
        recorder.emit_domain_event(
            ev.STRUCTURED_FALLBACK_USED,
            "stage_15_narrative_verifier",
            _deterministic("narrative_fallback"),
            case_id=case_id,
            reason_codes=list(result["reason_codes"]),
            narrator_input_hash=narrator_input["narrator_input_hash"],
            narrative_hash=result.get("narrative_hash") or "",
        )
