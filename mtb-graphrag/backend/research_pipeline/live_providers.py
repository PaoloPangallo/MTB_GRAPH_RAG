"""Adattatori dei componenti LIVE all'interfaccia dell'orchestratore.

Tre difetti dell'aggancio precedente, tutti invisibili finché la modalità LIVE
non veniva mai eseguita.

**Firma disallineata.** L'orchestratore chiama
``call_enricher_fn(budget, case_id, candidate_id, paper_id, …)``, mentre
``enricher_v2.call_enricher_v2`` comincia da ``case_id``. Passare la prima
direttamente alla seconda faceva scivolare ogni argomento di una posizione: il
budget finiva in ``case_id``, il caso in ``candidate_id``, e la chiamata sarebbe
partita con identificativi sbagliati.

**Budget mai speso.** ``CallBudget`` esiste e ``pipeline.run_case`` documenta che
sono i chiamanti a spenderlo, ma nessun chiamante lo faceva. Il tetto era
dichiarato e non applicato.

**Validatore v1 su enrichment v2.** Il default dell'orchestratore era
``validator.validate_enrichment``, che apre rifiutando ogni ``transport_result``
diverso da ``FORCED_TOOL_VALID``; l'enricher v2 produce ``V2_TRANSPORT_VALID``.
Ogni enrichment LIVE veniva quindi rigettato come guasto di trasporto prima di
qualunque verifica semantica, e ``PaperContextEnrichmentV2Validator`` — scritto,
completo, testato — non era raggiungibile da nessun percorso di esecuzione.

Il validatore **non viene modificato**: viene collegato.
"""

from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from functools import partial
from typing import Any

from backend.research_pipeline.casecontext import parser as cc_parser
from backend.research_pipeline.enrichment import enricher_v3
from backend.research_pipeline.enrichment.validator_v2 import validate_enrichment_v2
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3
from backend.research_pipeline.pipeline import CallBudgetExceeded

#: Campi del contratto v2.0 che il validatore legge. Un enrichment che non li ha
#: tutti non è un enrichment v2 e non va passato al validatore v2.
_V2_ARGUMENT_KEYS = (
    "decision", "source_unit_id", "author_claim_quote",
    "author_context_summary", "abstention_reason",
)


class LiveStageFailed(RuntimeError):
    """Uno stage LIVE non ha potuto essere eseguito.

    Non viene mai catturata per sostituire il risultato con un artefatto
    registrato: risale fino alla run, che resta ``FAILED`` con il proprio reason
    code. È la differenza fra "il modello si è astenuto" e "non ho parlato con il
    modello", che un fallback renderebbe indistinguibili.
    """

    def __init__(self, stage: str, reason_code: str, detail: str) -> None:
        super().__init__(f"{stage}: {reason_code} — {detail}")
        self.stage = stage
        self.reason_code = reason_code
        self.detail = detail
        self.call_result: dict[str, Any] | None = None


def parser_fn(budget: Any, case_id: str, clinical_text: str) -> dict[str, Any]:
    """CaseContext Parser reale. Spende una unità di budget."""
    try:
        budget.spend("casecontext_parser", case_id)
        result = cc_parser.call_parser(case_id, clinical_text)
    except CallBudgetExceeded as exc:
        raise LiveStageFailed("stage_2_casecontext_parser", "CALL_BUDGET_EXCEEDED", str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — risale come fallimento di stage
        raise LiveStageFailed("stage_2_casecontext_parser", "LIVE_STAGE_FAILED", str(exc)) from exc
    return {**result, "replayed": False, "artifact_origin": "GENERATED_NOW"}


def enricher_fn(
    budget: Any,
    case_id: str,
    candidate_id: str,
    paper_id: str,
    case_context: dict[str, Any],
    candidate_summary: dict[str, Any],
    drug: str,
    source_units: list[dict[str, Any]],
    *, request_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Canonical Paper Reader v3, with a strict observation-only contract.

    Le SourceUnit arrivano già limitate a monte: al massimo 5 per documento
    e al massimo 2 documenti per associazione. Nessun articolo integrale
    raggiunge il modello.
    """
    payload = None
    request_hash = None
    if request_cache is not None:
        from backend.research_pipeline.enrichment import transport
        payload = enricher_v3.build_reader_payload(case_context, candidate_summary, paper_id, source_units)
        identity = [transport.endpoint_url(), case_id, candidate_id, paper_id, drug, payload]
        request_hash = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if request_hash in request_cache:
            reused = deepcopy(request_cache[request_hash])
            reused.update(reader_response_reused=True, model_call_count=0,
                          input_tokens=0, output_tokens=0, latency_ms=0, retry_count=0)
            return reused
    try:
        budget.spend("paper_context_enricher_v3", case_id)
        kwargs = {"request_payload": payload} if payload is not None else {}
        result = enricher_v3.call_enricher_v3(
            case_id, candidate_id, paper_id, case_context, candidate_summary, source_units, **kwargs)
    except CallBudgetExceeded as exc:
        raise LiveStageFailed("stage_9_paper_context_enricher", "CALL_BUDGET_EXCEEDED", str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise LiveStageFailed("stage_9_paper_context_enricher", "LIVE_STAGE_FAILED", str(exc)) from exc
    if "HTTP_429" in (result.get("transport_reason_codes") or []):
        failure = LiveStageFailed("stage_9_paper_context_enricher", "PROVIDER_RATE_LIMITED",
                                  "HTTP 429 persisted after the bounded infrastructure retry; no further candidates sent.")
        failure.call_result = result
        raise failure
    result = {**result, "replayed": False, "artifact_origin": "GENERATED_NOW",
              "reader_response_reused": False, "model_call_count": result.get("model_call_count", 1 + (result.get("retry_count") or 0)),
              "reader_request_hash": request_hash}
    if request_cache is not None and request_hash is not None and result.get("transport_result") == "V3_TRANSPORT_VALID":
        request_cache[request_hash] = deepcopy(result)
    return result


def make_run_enricher():
    """One fresh cache per run; only exactly equal requests can share a response."""
    return partial(enricher_fn, request_cache={})


def _as_v2_arguments(enrichment: dict[str, Any] | None) -> dict[str, str] | None:
    """Proietta l'enrichment sui soli cinque campi del contratto v2.0.

    Il validatore deve vedere ciò che il modello ha prodotto, non i metadati che
    il runtime ha aggiunto localmente dopo un transport valido.
    """
    if enrichment is None:
        return None
    if not all(key in enrichment for key in _V2_ARGUMENT_KEYS):
        return None
    return {key: str(enrichment.get(key) or "") for key in _V2_ARGUMENT_KEYS}


def validate_fn(
    transport_result: str,
    enrichment: dict[str, Any] | None,
    *,
    candidate: dict[str, Any],
    paper_bundle: dict[str, Any],
    source_units_by_id: dict[str, dict[str, Any]],
    requested_drug: str,
    **_: Any,
) -> dict[str, Any]:
    """``PaperContextEnrichmentV2Validator``, eseguito davvero.

    ``case_context_text`` e ``candidate_text`` alimentano i controlli anti-eco del
    validatore: una quote che coincide con il testo del caso o con la candidate
    non proviene dal documento.
    """
    if transport_result == "V3_TRANSPORT_VALID":
        result = validate_enrichment_v3(
            transport_result, enrichment, candidate=candidate, paper_bundle=paper_bundle,
            source_units_by_id=source_units_by_id,
        )
        return {
            **result, "validator": "PaperRelationObservationValidatorV3",
            "observation_check_version": 'documentary-observation-checks/1.0',
            "replayed": False, "artifact_origin": "GENERATED_NOW",
        }
    args = _as_v2_arguments(enrichment)
    result = validate_enrichment_v2(
        transport_result, args,
        candidate=candidate,
        paper_bundle=paper_bundle,
        source_units_by_id=source_units_by_id,
        requested_drug=requested_drug,
        case_context_text=json.dumps(candidate.get("source_properties") or {}, ensure_ascii=False),
        candidate_text=json.dumps(
            {k: v for k, v in candidate.items() if k != "source_properties"},
            ensure_ascii=False, sort_keys=True,
        ),
    )
    offset = None
    if args and args["decision"] == "QUOTE" and str(result["outcome"]).startswith("ENRICHMENT_V2_ACCEPTED"):
        unit_text = (source_units_by_id.get(args["source_unit_id"]) or {}).get("text") or ""
        found = unit_text.find(args["author_claim_quote"].strip())
        offset = found if found >= 0 else None
    return {
        **result,
        "validator": "PaperContextEnrichmentV2Validator",
        "quote_offset": offset,
        "replayed": False,
        "artifact_origin": "GENERATED_NOW",
    }


def narrator_fn(case_id: str, narrator_input: dict[str, Any], run_index: int = 0) -> dict[str, Any]:
    """Dossier Narrator reale.

    Non spende ``CallBudget``: il budget protegge le chiamate che partecipano
    alla costruzione dell'evidenza, e la narrazione avviene dopo, su un dossier
    gia' chiuso. Un suo fallimento non invalida la run.
    """
    from backend.research_pipeline.narrative import narrator

    try:
        result = narrator.call_dossier_narrator(case_id, narrator_input, run_index=run_index)
    except CallBudgetExceeded as exc:
        raise LiveStageFailed('stage_14_narrator', 'CALL_BUDGET_EXCEEDED', str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise LiveStageFailed("stage_14_narrator", "NARRATION_TRANSPORT_FAILED", str(exc)) from exc
    return {**result, "replayed": False, "artifact_origin": "GENERATED_NOW"}
