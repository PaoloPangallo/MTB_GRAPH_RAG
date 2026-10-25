"""Budget del contesto e controllo privacy prima dell'invio.

Due verifiche che devono avvenire **prima** della chiamata, non dopo.

**Budget.** `input_tokens + reserved_output_tokens <= effective_context_window`. Se
non ci sta, la riduzione dei record deve essere esplicita e registrata: un troncamento
silenzioso renderebbe i bracci non confrontabili, perche' due modelli riceverebbero
input diversi senza che nulla lo dica. Non e' teorico — il free report su C1 ha un
prompt da 11.466 token con `num_ctx` 16384.

**Privacy.** Sul cloud si inviano solo casi sintetici, casi benchmark, fonti pubbliche
o dati anonimizzati. Il controllo scatta prima dell'invio: se rileva un possibile
identificatore personale, il prompt **non parte**.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# Stima conservativa: 4 caratteri per token e' vicino al vero per testo latino e
# leggermente pessimista sul JSON, che e' cio' che serve per un budget.
CHARS_PER_TOKEN = 4

DEFAULT_RESERVED_OUTPUT_TOKENS = 1024

REDUCTION_NONE = "none"
REDUCTION_RECORD_DROP = "record_drop"


def estimate_tokens(text: str) -> int:
    return max(1, (len(text or "") + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def messages_tokens(messages: Sequence[Mapping[str, str]]) -> int:
    return sum(estimate_tokens(str(message.get("content", ""))) for message in messages)


@dataclass(frozen=True)
class BudgetDecision:
    """Esito della verifica di budget, con la traccia di ogni riduzione."""

    fits: bool
    effective_context_window: int
    reserved_output_tokens: int
    initial_tokens: int
    final_tokens: int
    initial_records: int
    kept_records: int
    excluded_records: tuple[str, ...] = ()
    reduction_reason: str = REDUCTION_NONE

    def as_dict(self) -> dict[str, Any]:
        return {
            "fits": self.fits,
            "effective_context_window": self.effective_context_window,
            "reserved_output_tokens": self.reserved_output_tokens,
            "initial_tokens": self.initial_tokens,
            "final_tokens": self.final_tokens,
            "initial_records": self.initial_records,
            "kept_records": self.kept_records,
            "excluded_records": list(self.excluded_records),
            "reduction_reason": self.reduction_reason,
        }


def effective_context_window(num_ctx: int, declared: int | None) -> int:
    """La finestra realmente utilizzabile.

    Se il modello dichiara una finestra minore di `num_ctx`, vince la sua: chiedere
    16384 a un modello da 8192 non li rende disponibili.
    """
    if declared and declared > 0:
        return min(int(num_ctx), int(declared))
    return int(num_ctx)


def check_budget(
    messages: Sequence[Mapping[str, str]],
    *,
    num_ctx: int,
    declared_context: int | None = None,
    reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT_TOKENS,
    record_count: int = 0,
) -> BudgetDecision:
    """Verifica se il prompt sta nel budget, senza modificarlo."""
    window = effective_context_window(num_ctx, declared_context)
    tokens = messages_tokens(messages)
    fits = tokens + reserved_output_tokens <= window
    return BudgetDecision(
        fits=fits,
        effective_context_window=window,
        reserved_output_tokens=reserved_output_tokens,
        initial_tokens=tokens,
        final_tokens=tokens,
        initial_records=record_count,
        kept_records=record_count,
        reduction_reason=REDUCTION_NONE,
    )


def reduce_records(
    records: Sequence[Mapping[str, Any]],
    *,
    overhead_tokens: int,
    num_ctx: int,
    declared_context: int | None = None,
    reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT_TOKENS,
    identifier_field: str = "record_id",
) -> tuple[list[Mapping[str, Any]], BudgetDecision]:
    """Riduce i record fino a rientrare nel budget, registrando cosa e' stato escluso.

    La politica e' **identica per tutti i modelli**: si scartano i record dalla coda,
    preservando l'ordine dei rimanenti. Deterministica, quindi due modelli con la
    stessa finestra ricevono esattamente lo stesso input; e quando le finestre
    differiscono, la differenza e' registrata invece di essere invisibile.
    """
    import json

    window = effective_context_window(num_ctx, declared_context)
    budget = window - reserved_output_tokens - overhead_tokens
    initial_tokens = overhead_tokens + estimate_tokens(
        json.dumps(list(records), ensure_ascii=False)
    )

    kept = list(records)
    excluded: list[str] = []
    while kept and estimate_tokens(json.dumps(kept, ensure_ascii=False)) > budget:
        dropped = kept.pop()
        excluded.append(str(dropped.get(identifier_field, f"index:{len(kept)}")))

    final_tokens = overhead_tokens + estimate_tokens(
        json.dumps(kept, ensure_ascii=False)
    )
    return kept, BudgetDecision(
        fits=bool(kept) or not records,
        effective_context_window=window,
        reserved_output_tokens=reserved_output_tokens,
        initial_tokens=initial_tokens,
        final_tokens=final_tokens,
        initial_records=len(records),
        kept_records=len(kept),
        excluded_records=tuple(reversed(excluded)),
        reduction_reason=REDUCTION_RECORD_DROP if excluded else REDUCTION_NONE,
    )


# ── Privacy ────────────────────────────────────────────────────────────────────

# Pattern di possibili identificatori personali. Volutamente prudenti: un falso
# positivo costa una run rifiutata, un falso negativo manda dati personali a un
# servizio terzo.
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("codice_fiscale", re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b")),
    ("telefono", re.compile(r"(?<!\d)(?:\+\d{1,3}[ .-]?)?(?:\d[ .-]?){9,13}\d(?!\d)")),
    ("data_di_nascita", re.compile(r"\b(?:nat[oa]\s+il|d\.?o\.?b\.?)\s*[:\s]", re.I)),
    ("codice_paziente", re.compile(r"\b(?:paziente|patient|MRN|cartella)\s*[:#]\s*\S+", re.I)),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
)


@dataclass(frozen=True)
class PrivacyDecision:
    allowed: bool
    detections: tuple[str, ...] = field(default_factory=tuple)

    @property
    def cloud_input_rejected(self) -> bool:
        return not self.allowed

    def as_dict(self) -> dict[str, Any]:
        return {
            "cloud_input_rejected": self.cloud_input_rejected,
            # Si registra il *tipo* rilevato, mai il valore corrispondente.
            "detected_categories": list(self.detections),
        }


def screen_for_personal_data(text: str) -> PrivacyDecision:
    """Cerca possibili identificatori personali. Registra il tipo, mai il valore."""
    found: list[str] = []
    for label, pattern in _PII_PATTERNS:
        if pattern.search(text or ""):
            found.append(label)
    return PrivacyDecision(allowed=not found, detections=tuple(found))


def screen_messages(messages: Sequence[Mapping[str, str]]) -> PrivacyDecision:
    joined = "\n".join(str(message.get("content", "")) for message in messages)
    return screen_for_personal_data(joined)
