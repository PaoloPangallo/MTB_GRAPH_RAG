"""Adapter verso il source verifier semantico, comune alle due architetture.

Possiede due responsabilità che prima erano sparse o mancanti:

1. **La revisione del modello.** ``verify_evidence_items`` la accettava ma
   nessuno la passava, quindi ogni profilo veniva memorizzato sotto la stringa
   ``"default"``: cambiare modello non invalidava la cache e i profili vecchi
   venivano riutilizzati silenziosamente.
2. **La cache del profilo sorgente**, prima un singleton di processo. Iniettarla
   è ciò che rende possibile isolare le fasi cold e warm del case study: con un
   singleton, il cold della seconda architettura sarebbe già caldo per effetto
   della prima.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence


def default_model_revision() -> str:
    """Identificatore reale del modello che produce i profili sorgente.

    La temperatura **non** entra qui: non è una revisione del modello, e
    mescolarla renderebbe la chiave di cache incomparabile con l'identificatore
    che il provider espone. Parametri di decodifica andrebbero, semmai, in un
    hash di configurazione separato.
    """
    override = os.getenv("SOURCE_VERIFIER_MODEL_REVISION")
    if override:
        return override.strip()
    model = os.getenv("LLM_PIPELINE", "gemma4:31b-cloud").strip()
    return f"ollama:{model}"


@dataclass(frozen=True)
class VerifierTelemetry:
    """Metriche tecniche del verificatore, separate dai conteggi clinici."""

    cache_hits: int = 0
    cache_misses: int = 0
    verifier_batches: int = 0
    failed_batches: int = 0
    retry_items: int = 0
    recovered_items: int = 0
    permanently_failed_items: int = 0
    source_profile_elapsed_ms: int = 0
    applicability_elapsed_ms: int = 0

    @classmethod
    def from_metrics(cls, metrics: dict[str, Any]) -> "VerifierTelemetry":
        return cls(**{
            key: int(metrics.get(key, 0) or 0)
            for key in cls.__dataclass_fields__  # noqa: SLF001 - lettura dei campi dichiarati
        })

    @property
    def llm_calls(self) -> int:
        """Chiamate LLM effettive: i cache hit non ne producono."""
        return self.verifier_batches + self.retry_items


@dataclass
class SourceVerificationOutcome:
    verifications: tuple[Any, ...] = ()
    telemetry: VerifierTelemetry = field(default_factory=VerifierTelemetry)
    model_revision: str = ""
    prompt_version: str = ""


class SourceVerifierPort(Protocol):
    """Contratto che entrambe le architetture usano, senza saperne l'implementazione."""

    def verify(
        self, items: Sequence[Any], case_context: dict[str, Any]
    ) -> SourceVerificationOutcome: ...


class PubMedSourceVerifier:
    """Implementazione live: PubMed + LLM semantico + validazione deterministica."""

    def __init__(self, *, profile_cache: Any | None = None, model_revision: str | None = None) -> None:
        self._cache = profile_cache
        self._model_revision = model_revision or default_model_revision()

    @property
    def model_revision(self) -> str:
        return self._model_revision

    def verify(
        self, items: Sequence[Any], case_context: dict[str, Any]
    ) -> SourceVerificationOutcome:
        from backend.pipeline.agentic.source_verifier import (
            SOURCE_PROFILE_PROMPT_VERSION,
            verify_evidence_items,
        )

        metrics: dict[str, Any] = {}
        verifications = verify_evidence_items(
            list(items),
            metrics=metrics,
            profile_cache=self._cache,
            case_context=case_context,
            model_revision=self._model_revision,
        )
        return SourceVerificationOutcome(
            verifications=tuple(verifications),
            telemetry=VerifierTelemetry.from_metrics(metrics),
            model_revision=self._model_revision,
            prompt_version=SOURCE_PROFILE_PROMPT_VERSION,
        )


class ScriptedSourceVerifier:
    """Implementazione per la modalità demo: esiti da fixture, nessuna rete.

    Attraversa lo stesso contratto della versione live, quindi la demo esercita
    davvero lo strato comune anziché saltarlo.
    """

    def __init__(self, outcomes: Sequence[Any], *, model_revision: str = "scripted:demo") -> None:
        self._outcomes = list(outcomes)
        self._model_revision = model_revision

    @property
    def model_revision(self) -> str:
        return self._model_revision

    def verify(
        self, items: Sequence[Any], case_context: dict[str, Any]
    ) -> SourceVerificationOutcome:
        verifications = [
            self._outcomes[index] if index < len(self._outcomes) else self._outcomes[-1]
            for index in range(len(items))
        ] if self._outcomes else []
        return SourceVerificationOutcome(
            verifications=tuple(verifications),
            telemetry=VerifierTelemetry(cache_misses=len(verifications)),
            model_revision=self._model_revision,
            prompt_version="scripted",
        )


def build_case_context(case: Any) -> dict[str, Any]:
    """Contesto clinico passato al verificatore, senza inferenze.

    I campi non dichiarati restano vuoti: dedurre "metastatico" da uno stadio
    assente fabbricherebbe un'applicabilità che nessuno ha affermato.
    """
    def text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "presenti" if value else "assenti"
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value)
        return str(value)

    return {
        "gene": text(case.gene),
        "variant": text(case.variant),
        "tumor_type": text(case.tumor_type),
        "therapy_line": text(case.therapy_line),
        "disease_stage": text(case.disease_stage),
        "disease_setting": text(case.disease_setting),
        "prior_therapies": text(case.prior_therapies),
        "prior_response": text(case.prior_response),
        "ecog_status": text(case.ecog_status),
        "cns_metastases": text(case.cns_metastases),
        "co_alterations": text(case.co_alterations),
        "jurisdiction": text(case.jurisdiction),
        "mtb_goal": text(case.mtb_goal),
    }
