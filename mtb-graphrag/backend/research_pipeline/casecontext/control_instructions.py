"""Rilevamento deterministico di istruzioni rivolte al sistema.

**Non risolve universalmente la prompt injection**, e questo modulo non lo
afferma. L'obiettivo verificabile è più stretto e misurabile:

* coprire le forme presenti nel benchmark RQ4 congelato;
* impedire che un'entità nominata dentro un'istruzione contamini un campo
  clinico canonico;
* impedire chiamate downstream non autorizzate;
* registrare il comportamento per audit.

Il rilevatore è **conservativo**: riconosce forme imperative rivolte al sistema,
non qualunque frase sospetta. Un falso negativo lascia passare una menzione che
il verifier semantico può ancora rifiutare per altri motivi; un falso positivo
scarterebbe contenuto clinico legittimo, che è il danno peggiore.
"""

from __future__ import annotations

import re
from typing import Any

#: Pattern di istruzione rivolta al sistema. Ogni voce è ancorata a un verbo
#: imperativo o a un marcatore di ruolo, non a una parola isolata.
_CONTROL_PATTERNS: tuple[tuple[str, str], ...] = (
    # Sovrascrittura delle istruzioni
    (r"ignor[ae]\s+(?:le\s+)?istruzioni\s+precedenti", "IGNORE_PREVIOUS_INSTRUCTIONS"),
    (r"ignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above)\s+instructions?", "IGNORE_PREVIOUS_INSTRUCTIONS"),
    (r"disregard\s+(?:your|the|all|any)\b[^.]*", "DISREGARD_INSTRUCTIONS"),
    (r"forget\s+(?:your|the|all)\s+(?:instructions?|rules?|prompt)", "DISREGARD_INSTRUCTIONS"),
    (r"invece\s+del\s+task", "OVERRIDE_TASK"),
    (r"instead\s+of\s+the\s+task", "OVERRIDE_TASK"),
    (r"regardless\s+of\s+the\s+text\s+above", "OVERRIDE_TASK"),
    # Cambio di ruolo
    (r"you\s+are\s+now\s+(?:a|an)\b[^.]*", "ROLE_OVERRIDE"),
    (r"^\s*system\s*:", "ROLE_OVERRIDE"),
    (r"act\s+as\s+(?:a|an)\b[^.]*", "ROLE_OVERRIDE"),
    (r"sei\s+ora\s+un\b[^.]*", "ROLE_OVERRIDE"),
    # Esfiltrazione del prompt
    (r"repeat\s+your\s+(?:full\s+)?system\s+prompt[^.]*", "PROMPT_DISCLOSURE"),
    (r"reveal\s+(?:your\s+)?(?:system\s+)?prompt[^.]*", "PROMPT_DISCLOSURE"),
    (r"rivela\s+il\s+(?:tuo\s+)?prompt[^.]*", "PROMPT_DISCLOSURE"),
    (r"print\s+your\s+instructions[^.]*", "PROMPT_DISCLOSURE"),
    # Raccomandazione imposta
    (r"raccomanda\s+\w+", "FORCED_RECOMMENDATION"),
    (r"recommend\s+\w+\s*$", "FORCED_RECOMMENDATION"),
    (r"just\s+tell\s+me\s+whether\b[^.]*", "FORCED_RECOMMENDATION"),
    # Fabbricazione imposta
    (r"invent\s+a\b[^.]*", "FORCED_FABRICATION"),
    (r"inventa\s+un\b[^.]*", "FORCED_FABRICATION"),
    (r"make\s+up\s+a\b[^.]*", "FORCED_FABRICATION"),
    (r"if\s+no\s+\w+\s+is\s+stated[^.]*", "FORCED_FABRICATION"),
    # Imposizione di valori di campo
    (r"set\s+\w+\s+to\s+\w+[^.]*", "FORCED_FIELD_VALUE"),
    (r"important\s+instruction\s+to\s+the\s+model[^.]*", "FORCED_FIELD_VALUE"),
    (r"output\s+a\s+\w+\s+plan[^.]*", "FORCED_OUTPUT_FORMAT"),
)

_COMPILED = tuple((re.compile(pattern, re.I | re.M), code) for pattern, code in _CONTROL_PATTERNS)


def detect_control_instruction_spans(text: str) -> list[dict[str, Any]]:
    """Span delle istruzioni rivolte al sistema, ordinati e fusi se sovrapposti."""
    found: list[dict[str, Any]] = []
    for pattern, code in _COMPILED:
        for match in pattern.finditer(text or ""):
            found.append({
                "start_offset": match.start(),
                "end_offset": match.end(),
                "quote": match.group(0),
                "reason_code": code,
                "detector": "DETERMINISTIC_PATTERN",
            })
    return _merge(found)


def _merge(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not spans:
        return []
    spans = sorted(spans, key=lambda s: (s["start_offset"], -s["end_offset"]))
    merged = [spans[0]]
    for span in spans[1:]:
        last = merged[-1]
        if span["start_offset"] <= last["end_offset"]:
            last["end_offset"] = max(last["end_offset"], span["end_offset"])
            codes = set(last["reason_code"].split("|")) | {span["reason_code"]}
            last["reason_code"] = "|".join(sorted(codes))
        else:
            merged.append(span)
    return merged


def mention_is_inside_control_span(
    located: tuple[int, int] | None,
    control_spans: list[dict[str, Any]],
) -> bool:
    """Vero se la menzione è contenuta **esclusivamente** in uno span di controllo."""
    if located is None or not control_spans:
        return False
    start, end = located
    return any(
        span["start_offset"] <= start and end <= span["end_offset"]
        for span in control_spans
    )


def control_coverage(text: str, control_spans: list[dict[str, Any]]) -> float:
    """Quota del testo occupata dalle istruzioni di controllo."""
    if not text or not control_spans:
        return 0.0
    covered = sum(span["end_offset"] - span["start_offset"] for span in control_spans)
    return min(1.0, covered / len(text))


#: Soglia oltre la quale l'input è considerato *prevalentemente* una direttiva.
#: Il valore è alto di proposito: sotto questa soglia si preferisce valutare il
#: contenuto clinico indipendente, rimuovendo solo le menzioni contaminate.
PREDOMINANTLY_CONTROL_THRESHOLD = 0.5


def is_predominantly_control(text: str, control_spans: list[dict[str, Any]]) -> bool:
    return control_coverage(text, control_spans) >= PREDOMINANTLY_CONTROL_THRESHOLD


def residual_clinical_text(text: str, control_spans: list[dict[str, Any]]) -> str:
    """Il testo privato degli span di controllo, per valutare il caso indipendente."""
    if not control_spans:
        return text
    out, cursor = [], 0
    for span in sorted(control_spans, key=lambda s: s["start_offset"]):
        out.append(text[cursor:span["start_offset"]])
        cursor = span["end_offset"]
    out.append(text[cursor:])
    return " ".join(part.strip() for part in out if part.strip())
