"""Ricostruzione della vista canonica per replay degli eventi del ledger.

Prima, la vista canonica veniva calcolata dallo stato in memoria e *poi*
registrata: il log era l'unica copia, e nulla garantiva che descrivesse
davvero ciò che gli strumenti avevano prodotto. Qui il rapporto è invertito —
la vista è una funzione **pura** della sequenza di eventi, quindi è
riproducibile da chiunque abbia il ledger e verificabile senza rieseguire la
pipeline.

La purezza è anche ciò che rende semplice la riparazione: dopo una nuova
azione basta rifare il fold sull'intera lista, senza patch incrementali e
senza rischio che la vista diverga dal ledger.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.pipeline.control.canonical import (
    identity_key,
    merge_observations,
    weakest_completeness,
)
from backend.pipeline.control.contracts import (
    CanonicalView,
    ProvenanceRef,
    RecordObservation,
    ReplayFidelity,
)
from backend.pipeline.control.events import TOOL_COMPLETED


def _provenance(event: Mapping[str, Any]) -> ProvenanceRef:
    return ProvenanceRef(
        event_id=str(event.get("event_id") or ""),
        sequence=int(event.get("sequence") or 0),
        # Gli eventi v1 non hanno action_id: si sintetizza un surrogato
        # tracciabile, così la genealogia resta esprimibile anche sui run
        # storici, pur segnalando il degrado tramite replay_fidelity.
        action_id=str(event.get("action_id") or f"v1:{event.get('event_id')}"),
        tool_name=event.get("tool_name") or (event.get("payload") or {}).get("tool"),
        tool_version=event.get("tool_version"),
        observed_at=str(event.get("created_at") or ""),
    )


def replay_to_canonical_view(events: Sequence[Mapping[str, Any]]) -> CanonicalView:
    """Ricostruisce la vista canonica dai soli eventi.

    Funzione pura: nessun I/O, nessuno stato condiviso, nessuna richiesta.
    A parità di eventi restituisce sempre la stessa vista.
    """
    run_id = str(events[0]["run_id"]) if events else ""

    grouped: dict[tuple[str, ...], list[RecordObservation]] = {}
    kinds: dict[tuple[str, ...], str] = {}
    completeness: dict[tuple[str, ...], list[str]] = {}
    order: list[tuple[str, ...]] = []

    records_in = 0
    unreplayable: list[str] = []
    saw_v1 = False
    saw_truncation = False

    for event in events:
        if int(event.get("schema_version") or 1) < 2:
            saw_v1 = True

        if event.get("event_type") != TOOL_COMPLETED:
            continue

        payload = event.get("payload") or {}
        record_kind = payload.get("record_kind")
        records = payload.get("records")

        if int(event.get("schema_version") or 1) < 2:
            # Evento v1: il payload non trasporta record strutturati, quindi il
            # fatto è noto ma non ricostruibile. Deve risultare *non*
            # replayabile, altrimenti un run interamente storico si
            # presenterebbe come vista completa con zero record.
            unreplayable.append(str(event.get("event_id") or ""))
            continue

        if record_kind == "":
            # Strumento che non produce record (assess_complexity classifica
            # soltanto): assenza attesa, non un degrado.
            continue

        if not record_kind or not isinstance(records, list):
            unreplayable.append(str(event.get("event_id") or ""))
            continue

        if payload.get("payload_truncated"):
            saw_truncation = True

        status = str(
            event.get("completeness_status") or payload.get("completeness_status") or "unknown"
        )
        provenance = _provenance(event)

        for record in records:
            if not isinstance(record, Mapping):
                continue
            records_in += 1
            key = identity_key(record_kind, record)
            if key not in grouped:
                grouped[key] = []
                kinds[key] = record_kind
                completeness[key] = []
                order.append(key)
            # Merge, mai scarto: ogni occorrenza resta con la sua provenienza.
            grouped[key].append(RecordObservation(provenance=provenance, payload=dict(record)))
            completeness[key].append(status)

    canonical = tuple(
        merge_observations(kinds[key], key, grouped[key], completeness[key]) for key in order
    )

    fidelity: ReplayFidelity = "full"
    if unreplayable:
        fidelity = "degraded_v1_events" if saw_v1 else "partial"
    elif saw_truncation:
        fidelity = "partial"

    return CanonicalView(
        run_id=run_id,
        records=canonical,
        records_in=records_in,
        replay_fidelity=fidelity,
        unreplayable_event_ids=tuple(unreplayable),
        completeness_status=weakest_completeness(
            [record.completeness_status for record in canonical]
        ),
    )
