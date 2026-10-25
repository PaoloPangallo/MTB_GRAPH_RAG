"""Durable public run and stage recording, independent of orchestration policy."""

from __future__ import annotations

import time
import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping

from backend.pipeline.agentic.ledger import EventLedger
from . import events as ev, execution_mode as em
from .contracts import (
    NOT_IMPLEMENTED_STAGE_IDS,
    STAGE_SEQUENCE,
    PipelineRun,
    PipelineStage,
    StageProducer,
    stage_type_for,
)
from .versions import ORCHESTRATOR_VERSION
from .enrichment.verification_policy import public_artifact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deterministic(
    component: str, version: str = ORCHESTRATOR_VERSION
) -> StageProducer:
    return StageProducer(kind="DETERMINISTIC", component=component, version=version)


class RunRecorder:
    """Accumula gli stage e scrive gli eventi sul ledger append-only.

    Il ledger è la fonte di verità; ``PipelineRun`` è una proiezione comoda per
    l'API. Le due non devono divergere, quindi ogni transizione passa di qui.
    """

    def __init__(self, ledger: EventLedger, run_id: str, execution_mode: str) -> None:
        self._ledger = ledger
        self._run_id = run_id
        self._mode = execution_mode
        self._stages: list[PipelineStage] = []
        self._started: dict[str, float] = {}
        self._started_at: dict[str, str] = {}

    @property
    def stages(self) -> tuple[PipelineStage, ...]:
        return tuple(self._stages)

    @property
    def origins(self) -> tuple[str, ...]:
        return tuple(stage.artifact_origin for stage in self._stages)

    def _stage_mode(self, origin: str) -> str:
        """Modalità dichiarabile da uno stage con questa origine.

        Uno stage che rigioca un artefatto registrato non può dichiararsi LIVE —
        il contratto lo rifiuterebbe. Marcarlo ``REPLAY`` anche dentro una run
        avviata LIVE è ciò che poi rende la run ``HYBRID`` invece che ``LIVE``.
        """
        if origin == em.RECORDED_REAL_RUN:
            return em.REPLAY
        return self._mode

    def _emit(
        self, event_type: str, payload: Mapping[str, Any], producer: StageProducer
    ) -> dict[str, Any]:
        ev.assert_payload_is_publishable(payload)
        return self._ledger.append(
            self._run_id,
            event_type,
            producer.component,
            dict(payload),
            tool_name=producer.component,
            tool_version=producer.version,
        )

    def run_created(
        self, case_id: str, clinical_text: str, cache: Mapping[str, Any]
    ) -> str:
        existing = self._ledger.events(self._run_id)
        if isinstance(existing, (list, tuple)):
            admitted = next(
                (event for event in existing if event["event_type"] == ev.RUN_CREATED),
                None,
            )
            if admitted is not None:
                payload = admitted["payload"]
                digest = hashlib.sha256(clinical_text.encode("utf-8")).hexdigest()
                same_input = payload.get("input_sha256") == digest and payload.get(
                    "input_chars"
                ) == len(clinical_text)
                if "input_sha256" not in payload:
                    same_input = (
                        len(clinical_text) <= 600
                        and payload.get("input_text") == clinical_text
                        and payload.get("input_chars") == len(clinical_text)
                    )
                if payload.get("case_id") != case_id or not same_input:
                    raise ValueError("RUN_ADMISSION_IDENTITY_MISMATCH")
                return str(admitted["created_at"])
        # ``input_text`` è il testo sintetico del caso, troncato come nella run:
        # senza di esso una run reidratata dal ledger non potrebbe mostrare da
        # quale domanda è partita.
        event = self._emit(
            ev.RUN_CREATED,
            {
                "case_id": case_id,
                "input_chars": len(clinical_text),
                "input_text": clinical_text[:600],
                "input_sha256": hashlib.sha256(
                    clinical_text.encode("utf-8")
                ).hexdigest(),
                "requested_execution_mode": self._mode,
                "document_cache": dict(cache),
                "research_notice": PipelineRun.research_notice(),
            },
            _deterministic("orchestrator"),
        )
        return event["created_at"] if isinstance(event, dict) else _now()

    def start(self, stage_id: str, producer: StageProducer, **preview: Any) -> None:
        self._started[stage_id] = time.monotonic()
        event = self._emit(
            ev.STAGE_STARTED,
            ev.stage_payload(
                stage_id=stage_id,
                stage_type=stage_type_for(stage_id),
                producer=producer,
                execution_mode=self._mode,
                **preview,
            ),
            producer,
        )
        self._started_at[stage_id] = (
            event["created_at"] if isinstance(event, dict) else _now()
        )

    def finish(
        self,
        stage_id: str,
        producer: StageProducer,
        *,
        status: str = "SUCCEEDED",
        artifact_origin: str = em.GENERATED_NOW,
        domain_event: str | None = None,
        output_preview: Mapping[str, Any] | None = None,
        reason_codes: tuple[str, ...] = (),
        warnings: tuple[str, ...] = (),
        errors: tuple[str, ...] = (),
        metrics: Mapping[str, Any] | None = None,
        lineage: Mapping[str, Any] | None = None,
    ) -> PipelineStage:
        started = self._started.pop(stage_id, None)
        duration_ms = (
            int((time.monotonic() - started) * 1000) if started is not None else None
        )
        preview = public_artifact(dict(output_preview or {}))
        ev.assert_payload_is_publishable(preview)
        em.assert_origin(artifact_origin)
        stage_mode = self._stage_mode(artifact_origin)
        started_at = self._started_at.pop(stage_id, None)
        completed_at = _now()

        if domain_event is not None:
            self._emit(
                domain_event,
                ev.stage_payload(
                    stage_id=stage_id,
                    stage_type=stage_type_for(stage_id),
                    producer=producer,
                    execution_mode=stage_mode,
                    artifact_origin=artifact_origin,
                    **preview,
                ),
                producer,
            )

        event_type = {
            "SUCCEEDED": ev.STAGE_COMPLETED,
            "WARNING": ev.STAGE_WARNING,
            "FAILED": ev.STAGE_FAILED,
            "SKIPPED": ev.STAGE_SKIPPED,
        }[status]
        # Warning, errori, metriche e lineage viaggiano nell'evento di chiusura:
        # è da questo che ``rehydration`` ricostruisce lo stage dopo un riavvio,
        # e ciò che non è nell'evento non sopravvive al processo.
        self._emit(
            event_type,
            ev.stage_payload(
                stage_id=stage_id,
                stage_type=stage_type_for(stage_id),
                producer=producer,
                status=status,
                execution_mode=stage_mode,
                artifact_origin=artifact_origin,
                reason_codes=list(reason_codes),
                duration_ms=duration_ms,
                warnings=list(warnings),
                errors=list(errors),
                metrics=dict(metrics or {}),
                lineage=dict(lineage or {}),
                output_preview=preview,
                started_at=started_at,
                completed_at=completed_at,
                sequence=STAGE_SEQUENCE.index(stage_id) + 1,
            ),
            producer,
        )

        stage = PipelineStage(
            stage_id=stage_id,
            stage_type=stage_type_for(stage_id),
            sequence=STAGE_SEQUENCE.index(stage_id) + 1,
            status=status,
            producer=producer,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            output_preview=preview,
            reason_codes=reason_codes,
            warnings=warnings,
            errors=errors,
            metrics=dict(metrics or {}),
            lineage=dict(lineage or {}),
            execution_mode=stage_mode,
            artifact_origin=artifact_origin,
        )
        self._stages.append(stage)
        return stage

    def emit_domain_event(
        self, event_type: str, stage_id: str, producer: StageProducer, **payload: Any
    ) -> None:
        """Evento di dominio non legato all'apertura o chiusura di uno stage.

        Passa comunque da ``stage_payload``, così ``stage_id`` e ``stage_type``
        viaggiano nel payload come in ogni altro evento: è l'invariante che rende
        ogni riga del ledger attribuibile a uno stage.
        """
        self._emit(
            event_type,
            ev.stage_payload(
                stage_id=stage_id,
                stage_type=stage_type_for(stage_id),
                producer=producer,
                execution_mode=self._mode,
                **payload,
            ),
            producer,
        )

    def skip_remaining(self, reason: str) -> None:
        """Marca SKIPPED ogni stage non ancora eseguito, con il motivo a monte.

        Uno stage saltato senza spiegazione sarebbe indistinguibile da un
        difetto dell'orchestratore.
        """
        done = {stage.stage_id for stage in self._stages}
        producer = _deterministic("orchestrator")
        for stage_id in STAGE_SEQUENCE:
            if stage_id in done:
                continue
            code = (
                "NOT_IMPLEMENTED" if stage_id in NOT_IMPLEMENTED_STAGE_IDS else reason
            )
            origin = (
                em.NOT_APPLICABLE
                if stage_id in NOT_IMPLEMENTED_STAGE_IDS
                else em.NOT_EXECUTED
            )
            self.finish(
                stage_id,
                producer,
                status="SKIPPED",
                artifact_origin=origin,
                reason_codes=(code,),
            )

    def run_completed(
        self,
        status: str,
        stopped_at: str | None,
        llm_calls: int,
        *,
        early_relation_aware_report: dict[str, Any] | None = None,
        run_snapshot: Mapping[str, Any] | None = None,
    ) -> None:
        # ``llm_calls`` viaggia nell'evento e non viene ricalcolato in lettura.
        # Ricalcolarlo sommando le metriche degli stage dava due valori diversi
        # per la stessa run — il parser non contribuisce a nessuna metrica di
        # stage, e in REPLAY le chiamate rigiocate venivano contate come reali.
        # Early stops can produce an empty canonical dossier without executing
        # stage 13. Persist that exact artifact, rather than rebuilding it later.
        artifact = (
            {"relation_aware_report": early_relation_aware_report}
            if early_relation_aware_report is not None
            else {}
        )
        self._emit(
            ev.RUN_COMPLETED,
            {
                "status": status,
                "stopped_at": stopped_at,
                "stage_count": len(self._stages),
                "llm_calls": llm_calls,
                **em.summarize(self._mode, self.origins),
                **artifact,
                "run_snapshot": dict(run_snapshot or {}),
            },
            _deterministic("orchestrator"),
        )
