"""Vocabolario eventi del research runtime e costruzione dei payload.

Perché un vocabolario separato da ``backend/pipeline/control/events.py``: quel
modulo è **sigillato** dal manifest dell'esperimento comparativo finale
(``final_experiment/systems_v1.json``), e il suo vocabolario descrive il ciclo
plan-act-observe agentico, non gli stage di questa pipeline. Estenderlo
romperebbe il sigillo; duplicarlo sarebbe inutile. Qui vive solo ciò che è
specifico della pipeline verificabile.

Il **meccanismo** invece è riusato integralmente: ``EventLedger`` fornisce
append-only con trigger SQLite, hash-chain SHA-256, ``payload_hash``,
``parent_action_id`` per la causation e ``generating_action_id`` per il lineage.

L'identità di stage viaggia **nel payload**, non in una colonna: ``payload_json``
entra nel preimage dell'hash, quindi ``stage_id`` è protetto esattamente quanto
lo sarebbe una colonna, senza toccare file sigillati.
"""

from __future__ import annotations

from typing import Any, Mapping

from backend.research_pipeline.contracts import LLM_STAGE_IDS, StageProducer

# --- Eventi di run e stage --------------------------------------------------

RUN_CREATED = "RUN_CREATED"
STAGE_STARTED = "STAGE_STARTED"
STAGE_COMPLETED = "STAGE_COMPLETED"
STAGE_WARNING = "STAGE_WARNING"
STAGE_FAILED = "STAGE_FAILED"
STAGE_SKIPPED = "STAGE_SKIPPED"
RUN_COMPLETED = "RUN_COMPLETED"

# --- Eventi di dominio ------------------------------------------------------
# Emessi *in aggiunta* a STAGE_COMPLETED, non al suo posto: portano il risultato
# specifico dello stage, ed è da questi che il replay ricostruisce la vista.

CASECONTEXT_PARSED = "CASECONTEXT_PARSED"
CASECONTEXT_VERIFIED = "CASECONTEXT_VERIFIED"
RETRIEVAL_COMPLETED = "RETRIEVAL_COMPLETED"
CANDIDATES_FOUND = "CANDIDATES_FOUND"
DOCUMENT_RESOLVED = "DOCUMENT_RESOLVED"
SOURCE_UNIT_MATERIALIZED = "SOURCE_UNIT_MATERIALIZED"
PAPER_SELECTED = "PAPER_SELECTED"
ENRICHMENT_PROPOSED = "ENRICHMENT_PROPOSED"
ENRICHMENT_VALIDATED = "ENRICHMENT_VALIDATED"
GATES_COMPUTED = "GATES_COMPUTED"
STATUS_ASSIGNED = "STATUS_ASSIGNED"
DOSSIER_BUILT = "DOSSIER_BUILT"

#: Stage 14-15, ora implementati. ``DOSSIER_BUILT`` resta l'evento che segna la
#: costruzione del dossier **canonico**: precede sempre la narrazione, e la loro
#: separazione è ciò che rende leggibile dal ledger che la narrativa non ha
#: partecipato alla decisione.
NARRATION_GENERATED = "NARRATION_GENERATED"
NARRATION_VERIFIED = "NARRATION_VERIFIED"
NARRATION_REJECTED = "NARRATION_REJECTED"
STRUCTURED_FALLBACK_USED = "STRUCTURED_FALLBACK_USED"

#: Nessun evento è più definito-ma-mai-emesso.
NEVER_EMITTED: frozenset[str] = frozenset()

DOMAIN_EVENT_TYPES: tuple[str, ...] = (
    CASECONTEXT_PARSED, CASECONTEXT_VERIFIED, RETRIEVAL_COMPLETED, CANDIDATES_FOUND,
    DOCUMENT_RESOLVED, SOURCE_UNIT_MATERIALIZED, PAPER_SELECTED, ENRICHMENT_PROPOSED,
    ENRICHMENT_VALIDATED, GATES_COMPUTED, STATUS_ASSIGNED, DOSSIER_BUILT,
    NARRATION_GENERATED, NARRATION_VERIFIED, NARRATION_REJECTED, STRUCTURED_FALLBACK_USED,
)

LIFECYCLE_EVENT_TYPES: tuple[str, ...] = (
    RUN_CREATED, STAGE_STARTED, STAGE_COMPLETED, STAGE_WARNING,
    STAGE_FAILED, STAGE_SKIPPED, RUN_COMPLETED,
)

EVENT_TYPES: tuple[str, ...] = (*LIFECYCLE_EVENT_TYPES, *DOMAIN_EVENT_TYPES)

#: Da questi il replay deve saper ricostruire la vista della run senza rileggere
#: gli output degli stage.
REPLAYABLE_EVENT_TYPES: frozenset[str] = frozenset(DOMAIN_EVENT_TYPES)

# --- Campi vietati nel payload ----------------------------------------------

#: Nessun ragionamento interno del modello entra nel ledger, quindi non può
#: comparire in UI. Sono ammessi prompt_version, tool call, output strutturato,
#: citazioni, summary, abstention reason e reason code — non il pensiero.
_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "thinking", "reasoning", "chain_of_thought", "cot", "scratchpad",
    "internal_monologue", "raw_completion", "reasoning_content",
})

#: Il testo del documento non esce mai dall'API: l'indice SourceUnit contiene
#: solo locatori e ``content_hash``, e il join col document store resta interno
#: all'enricher.
_FORBIDDEN_TEXT_KEYS: frozenset[str] = frozenset({
    "full_text", "document_text", "body", "abstract", "source_text",
})


class ForbiddenPayloadField(ValueError):
    """Sollevata quando un payload contiene campi che non possono essere resi."""


def assert_payload_is_publishable(payload: Mapping[str, Any], *, path: str = "") -> None:
    """Rifiuta chain-of-thought e testo documentale prima della scrittura.

    Il controllo è **ricorsivo** e avviene a monte del ledger: un ledger
    append-only non consente di rimuovere ciò che vi è già entrato.
    """
    for key, value in payload.items():
        lowered = str(key).lower()
        where = f"{path}.{key}" if path else str(key)
        if lowered in _FORBIDDEN_KEYS:
            raise ForbiddenPayloadField(
                f"{where}: il ragionamento interno del modello non può entrare "
                "nel ledger né essere mostrato"
            )
        if lowered in _FORBIDDEN_TEXT_KEYS:
            raise ForbiddenPayloadField(
                f"{where}: il testo documentale non può entrare nel ledger; "
                "sono ammessi locatori, content_hash e la quote validata"
            )
        if isinstance(value, Mapping):
            assert_payload_is_publishable(value, path=where)
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                if isinstance(item, Mapping):
                    assert_payload_is_publishable(item, path=f"{where}[{index}]")


def stage_payload(
    *,
    stage_id: str,
    stage_type: str,
    producer: StageProducer,
    **extra: Any,
) -> dict[str, Any]:
    """Payload di un evento di stage, con identità e producer inclusi.

    ``stage_id`` sta nel payload per necessità architetturale, non per comodità:
    le colonne del ledger non sono estendibili senza rompere il sigillo
    dell'esperimento finale, e il payload è comunque nel preimage dell'hash.
    """
    if producer.kind == "LLM" and stage_id not in LLM_STAGE_IDS:
        raise ValueError(
            f"{stage_id} non può dichiarare un producer LLM: solo "
            f"{sorted(LLM_STAGE_IDS)} sono prodotti da un modello"
        )
    payload = {
        "stage_id": stage_id,
        "stage_type": stage_type,
        "producer": producer.to_dict(),
        **extra,
    }
    assert_payload_is_publishable(payload)
    return payload
