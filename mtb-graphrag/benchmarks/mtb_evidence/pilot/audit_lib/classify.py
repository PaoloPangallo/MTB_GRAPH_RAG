"""Classificazione strutturale dei record di evidenza.

Distinzione che regge tutto il modulo: lo schema del grafo **non modella** setting,
linea di terapia, stadio ne' esposizione precedente. Le proprieta' di `Evidence` sono
`evidence_id, evidence_type, evidence_level, evidence_direction, significance,
evidence_statement, citation_id, source_type, rating, variant_origin, disease, doid`.

Quei qualificatori sono quindi recuperabili solo come euristica testuale su
`evidence_statement`, e ogni risultato porta `classification_basis="text_heuristic"`
piu' gli span che l'hanno determinato. Non vanno mai presentati come dati strutturali,
e questo modulo non decide alcuna raccomandazione clinica: constata solo quali
qualificatori compaiono nel testo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Qualificatori che il grafo rappresenta come proprieta' o relazioni.
SCHEMA_MODELLED_QUALIFIERS = frozenset(
    {"variant_profile", "disease", "direction", "significance", "source", "evidence_level"}
)

# Qualificatori che nessuna proprieta' dello schema rappresenta.
NOT_MODELLED_QUALIFIERS = frozenset(
    {"setting", "line", "stage", "prior_therapy", "resection_status", "ecog"}
)

TEXT_HEURISTIC = "text_heuristic"
STRUCTURAL = "structural"

FIRST_LINE_ADVANCED = "first_line_advanced"
ADJUVANT_RESECTED = "adjuvant_resected"
POST_PROGRESSION_T790M = "post_progression_t790m"
INSUFFICIENT_CONTEXT = "insufficient_context"
OTHER = "other"

_ADJUVANT_MARKERS = (
    r"adjuvant",
    r"resect(?:ed|ion|able)",
    r"stage\s+ib",
    r"stage\s+i{1,3}a?\b",
    r"completely\s+resected",
    r"postoperative",
)

_T790M_MARKERS = (
    r"t790m",
    r"acquired\s+resistance",
    r"progress(?:ed|ion|ing)\s+(?:on|after|during)",
    r"previously\s+treated\s+with\s+(?:an?\s+)?egfr",
    r"prior\s+egfr[-\s]?tki",
    r"second[-\s]line",
)

_FIRST_LINE_MARKERS = (
    r"first[-\s]line",
    r"previously\s+untreated",
    r"treatment[-\s]na(?:i|ï)ve",
    r"untreated",
    r"newly\s+diagnosed",
)

_ADVANCED_MARKERS = (
    r"advanced",
    r"metastatic",
    r"stage\s+iv",
    r"locally\s+advanced",
    r"unresectable",
)

_PROTEIN_VARIANT = re.compile(r"\b([A-Z])(\d{2,5})([A-Z])\b")
_COMPOUND_MARKERS = (
    r"compound\s+mutation",
    r"double\s+mutant",
    r"[A-Z]\d{2,5}[A-Z]\s*/\s*[A-Z]\d{2,5}[A-Z]",
    r"[A-Z]\d{2,5}[A-Z]\s*\+\s*[A-Z]\d{2,5}[A-Z]",
)


@dataclass(frozen=True)
class Classification:
    """Esito di una classificazione euristica, con le prove che l'hanno prodotta."""

    label: str
    classification_basis: str
    matched_spans: tuple[str, ...]
    markers: dict[str, tuple[str, ...]]
    note: str = ""


def _find(patterns: tuple[str, ...], text: str) -> tuple[str, ...]:
    hits: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            span = match.group(0).strip()
            if span and span not in hits:
                hits.append(span)
    return tuple(hits)


def classify_setting(text: object) -> Classification:
    """Classifica il setting di un record di evidenza a partire dal testo.

    Le categorie piu' specifiche (adiuvante, post-progressione T790M) hanno
    precedenza su first-line, perche' un testo adiuvante puo' contenere comunque
    marcatori generici. Tutti i marcatori trovati restano nel risultato, cosi' che
    un revisore possa vedere le sovrapposizioni invece di fidarsi dell'etichetta.
    """
    source = "" if text is None else str(text)
    markers = {
        "adjuvant": _find(_ADJUVANT_MARKERS, source),
        "t790m": _find(_T790M_MARKERS, source),
        "first_line": _find(_FIRST_LINE_MARKERS, source),
        "advanced": _find(_ADVANCED_MARKERS, source),
    }
    all_spans = tuple(span for group in markers.values() for span in group)

    if markers["adjuvant"]:
        label, note = ADJUVANT_RESECTED, "marcatori di setting adiuvante/resecato"
    elif markers["t790m"]:
        label, note = POST_PROGRESSION_T790M, "marcatori di progressione o T790M"
    elif markers["first_line"] and markers["advanced"]:
        label, note = FIRST_LINE_ADVANCED, "prima linea in malattia avanzata/metastatica"
    elif all_spans:
        label, note = OTHER, "marcatori presenti ma non sufficienti a una categoria"
    else:
        label, note = INSUFFICIENT_CONTEXT, "nessun marcatore di setting nel testo"

    return Classification(
        label=label,
        classification_basis=TEXT_HEURISTIC,
        matched_spans=all_spans,
        markers=markers,
        note=note,
    )


@dataclass(frozen=True)
class VariantForm:
    """Forma della variante: singola o composta. Le due non vanno mai fuse."""

    is_compound: bool
    variants: tuple[str, ...]
    matched_spans: tuple[str, ...]
    classification_basis: str = TEXT_HEURISTIC


def classify_variant_form(text: object) -> VariantForm:
    """Riconosce se un testo descrive una mutazione composta.

    Serve a tenere separati i record su G1202R singola da quelli su G1202R/L1196M:
    hanno significato clinico opposto rispetto a lorlatinib, e confonderli
    invaliderebbe il caso A2.
    """
    source = "" if text is None else str(text)
    spans = _find(_COMPOUND_MARKERS, source)
    variants = tuple(
        dict.fromkeys(match.group(0).upper() for match in _PROTEIN_VARIANT.finditer(source.upper()))
    )
    is_compound = bool(spans) or len(variants) > 1
    return VariantForm(is_compound=is_compound, variants=variants, matched_spans=spans)


# Tipo di alterazione. Le classi restano separate di proposito: una fusione non e'
# una mutazione generica, e nessuna regola qui le rende intercambiabili.
_ALTERATION_PATTERNS: dict[str, tuple[str, ...]] = {
    "fusion": (r"fusion", r"rearrange(?:d|ment)?", r"::"),
    "mutation": (r"mutation", r"mutant", r"\b[A-Z]\d{2,5}[A-Z]\b"),
    "amplification": (r"amplification", r"amplified", r"\bcopy\s+number\s+gain\b"),
    "deletion": (r"deletion", r"\bdel\b", r"loss"),
    "expression": (r"overexpression", r"expression"),
}


def alteration_types(text: object) -> frozenset[str]:
    """Classi di alterazione citate da un nome di profilo o di variante."""
    source = "" if text is None else str(text)
    found = {
        name
        for name, patterns in _ALTERATION_PATTERNS.items()
        if any(re.search(pattern, source, flags=re.IGNORECASE) for pattern in patterns)
    }
    return frozenset(found)


def mentions(term: str, text: object) -> bool:
    """Presenza di un termine come parola intera, senza distinzione di maiuscole."""
    source = "" if text is None else str(text)
    return re.search(rf"\b{re.escape(term)}\b", source, flags=re.IGNORECASE) is not None


def qualifier_status(name: str, present_in_record: bool, agrees: bool | None) -> str:
    """Stato di un qualificatore, distinguendo l'assenza dalla non-modellazione.

    `not_modelled_by_schema` e `absent_in_record` sono cose diverse: la prima e' un
    limite del grafo, la seconda un dato mancante in quel record. Confonderle
    falserebbe il giudizio di freeze.
    """
    if name in NOT_MODELLED_QUALIFIERS:
        return "not_modelled_by_schema"
    if not present_in_record:
        return "absent_in_record"
    if agrees is None:
        return "present_not_compared"
    return "present_and_agrees" if agrees else "present_and_conflicts"
