"""Disease matching esplicito per il retriever qualificato.

Il matcher separa equivalenza lessicale verificata e relazione gerarchica. Solo
stringhe identiche, normalizzazione esatta e sinonimi presenti nella tabella
locale approvata possono soddisfare il vincolo nativo. Parent, child e sibling
restano informazioni di audit: riconoscerli non autorizza a recuperarli.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from benchmarks.mtb_evidence.pilot.audit_lib.disease import (
    _SUBTYPE_OF,
    _SYNONYM_GROUPS,
    split_disease,
)


DISEASE_MATCHER_VERSION = "qualified_disease_matcher/1.0"
VERIFIED_ALIAS_VERSION = "verified-local-disease-aliases/1.0"
VERIFIED_ALIAS_SOURCE = (
    "benchmarks/mtb_evidence/pilot/audit_lib/disease.py::_SYNONYM_GROUPS"
)
VERIFIED_RELATION_SOURCE = (
    "benchmarks/mtb_evidence/pilot/audit_lib/disease.py::_SUBTYPE_OF"
)

MATCH_EXACT_STRING = "exact_string"
MATCH_NORMALIZED_EXACT = "normalized_exact"
MATCH_VERIFIED_ALIAS = "verified_alias"
MATCH_EXPLICIT_PARENT = "explicit_parent"
MATCH_EXPLICIT_CHILD = "explicit_child"
MATCH_EXPLICIT_SIBLING = "explicit_sibling"
MATCH_PAN_CANCER_OR_UNSPECIFIED = "pan_cancer_or_unspecified"
MATCH_UNRESOLVED = "unresolved"
MATCH_INCOMPATIBLE = "incompatible"

DISEASE_MATCH_TYPES = (
    MATCH_EXACT_STRING,
    MATCH_NORMALIZED_EXACT,
    MATCH_VERIFIED_ALIAS,
    MATCH_EXPLICIT_PARENT,
    MATCH_EXPLICIT_CHILD,
    MATCH_EXPLICIT_SIBLING,
    MATCH_PAN_CANCER_OR_UNSPECIFIED,
    MATCH_UNRESOLVED,
    MATCH_INCOMPATIBLE,
)

HARD_MATCH_TYPES = frozenset(
    {
        MATCH_EXACT_STRING,
        MATCH_NORMALIZED_EXACT,
        MATCH_VERIFIED_ALIAS,
    }
)

DISEASE_EXACT_MATCH = "DISEASE_EXACT_MATCH"
DISEASE_NORMALIZED_EXACT_MATCH = "DISEASE_NORMALIZED_EXACT_MATCH"
DISEASE_VERIFIED_ALIAS_MATCH = "DISEASE_VERIFIED_ALIAS_MATCH"
DISEASE_EXPLICIT_PARENT_NOT_HARD_MATCHED = (
    "DISEASE_EXPLICIT_PARENT_NOT_HARD_MATCHED"
)
DISEASE_EXPLICIT_CHILD_NOT_HARD_MATCHED = (
    "DISEASE_EXPLICIT_CHILD_NOT_HARD_MATCHED"
)
DISEASE_EXPLICIT_SIBLING_NOT_HARD_MATCHED = (
    "DISEASE_EXPLICIT_SIBLING_NOT_HARD_MATCHED"
)
DISEASE_RELATION_UNRESOLVED = "DISEASE_RELATION_UNRESOLVED"
DISEASE_INCOMPATIBLE = "DISEASE_INCOMPATIBLE"
BIOMARKER_MISMATCH_DESPITE_DISEASE_ALIAS = (
    "BIOMARKER_MISMATCH_DESPITE_DISEASE_ALIAS"
)

_PAN_CANCER_KEYS = frozenset(
    {
        "cancer",
        "malignancy",
        "pan cancer",
        "pan-cancer",
        "unspecified cancer",
        "unspecified malignancy",
    }
)

_REASON_BY_MATCH_TYPE = {
    MATCH_EXACT_STRING: DISEASE_EXACT_MATCH,
    MATCH_NORMALIZED_EXACT: DISEASE_NORMALIZED_EXACT_MATCH,
    MATCH_VERIFIED_ALIAS: DISEASE_VERIFIED_ALIAS_MATCH,
    MATCH_EXPLICIT_PARENT: DISEASE_EXPLICIT_PARENT_NOT_HARD_MATCHED,
    MATCH_EXPLICIT_CHILD: DISEASE_EXPLICIT_CHILD_NOT_HARD_MATCHED,
    MATCH_EXPLICIT_SIBLING: DISEASE_EXPLICIT_SIBLING_NOT_HARD_MATCHED,
    MATCH_PAN_CANCER_OR_UNSPECIFIED: DISEASE_RELATION_UNRESOLVED,
    MATCH_UNRESOLVED: DISEASE_RELATION_UNRESOLVED,
    MATCH_INCOMPATIBLE: DISEASE_INCOMPATIBLE,
}


def _safe_term(value: object) -> str:
    """Rende separabili qualificatori uniti da slash, senza aggiungere sinonimi."""
    return re.sub(r"[/]+", " ", "" if value is None else str(value))


def _core(value: object) -> str:
    return split_disease(_safe_term(value)).core


def _group(core: str) -> frozenset[str] | None:
    return next((group for group in _SYNONYM_GROUPS if core in group), None)


def _canonical_key(core: str) -> str:
    group = _group(core)
    if not group:
        return core
    return min(group, key=lambda item: (len(item), item))


def _parent_key(core: str) -> str:
    direct = _SUBTYPE_OF.get(core)
    if direct:
        return _canonical_key(direct)
    group = _group(core)
    if group:
        parents = {
            _canonical_key(_SUBTYPE_OF[member])
            for member in group
            if member in _SUBTYPE_OF
        }
        if len(parents) == 1:
            return next(iter(parents))
    return ""


def _relation_type(query_core: str, statement_core: str) -> str:
    query_key = _canonical_key(query_core)
    statement_key = _canonical_key(statement_core)
    query_parent = _parent_key(query_core)
    statement_parent = _parent_key(statement_core)

    if query_parent and query_parent == statement_key:
        return MATCH_EXPLICIT_PARENT
    if statement_parent and statement_parent == query_key:
        return MATCH_EXPLICIT_CHILD
    if (
        query_parent
        and statement_parent
        and query_parent == statement_parent
        and query_key != statement_key
    ):
        return MATCH_EXPLICIT_SIBLING
    return MATCH_UNRESOLVED


@dataclass(frozen=True)
class DiseaseMatchResult:
    """Esito completo e serializzabile del confronto disease."""

    query_raw: str
    query_normalized: str
    statement_raw: str
    statement_normalized: str
    query_canonical_id: str
    statement_canonical_id: str
    canonical_disease_key: str
    match_type: str
    matched: bool
    hard_match_allowed: bool
    alias_source: str
    alias_version: str
    relation_source: str
    warning_code: str
    explanation_code: str
    matcher_version: str = DISEASE_MATCHER_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def match_disease(
    query_raw: object,
    statement_raw: object,
    *,
    query_aliases: Sequence[str] = (),
    query_canonical_id: str = "",
    statement_canonical_id: str = "",
) -> DiseaseMatchResult:
    """Classifica un match disease usando soltanto dati locali verificati.

    ``query_aliases`` viene accettato per rendere esplicito il contratto della
    query, ma non concede autorita' autonoma: un valore della query vale come
    alias soltanto se la tabella locale lo collega allo stesso gruppo verificato.
    """

    query_text = "" if query_raw is None else str(query_raw)
    statement_text = "" if statement_raw is None else str(statement_raw)
    query_core = _core(query_text)
    statement_core = _core(statement_text)
    query_id = str(query_canonical_id or "").strip()
    statement_id = str(statement_canonical_id or "").strip()

    # ID espliciti discordanti prevalgono anche su etichette uguali: fondere due
    # entita' identificate diversamente sarebbe una collisione, non un alias.
    if query_id and statement_id and query_id != statement_id:
        match_type = MATCH_INCOMPATIBLE
    elif query_text.strip() == statement_text.strip() and query_text.strip():
        match_type = MATCH_EXACT_STRING
    elif query_core and query_core == statement_core:
        match_type = MATCH_NORMALIZED_EXACT
    elif query_id and statement_id and query_id == statement_id:
        match_type = MATCH_VERIFIED_ALIAS
    elif (
        query_core
        and statement_core
        and _group(query_core) is not None
        and _group(query_core) == _group(statement_core)
    ):
        match_type = MATCH_VERIFIED_ALIAS
    elif query_core in _PAN_CANCER_KEYS or statement_core in _PAN_CANCER_KEYS:
        match_type = MATCH_PAN_CANCER_OR_UNSPECIFIED
    elif query_core and statement_core:
        match_type = _relation_type(query_core, statement_core)
    else:
        match_type = MATCH_UNRESOLVED

    # Un alias della query non presente nella tabella non viene promosso. Gli
    # alias verificati già ricadono nel confronto per gruppo sopra.
    _ = tuple(query_aliases)

    hard_match_allowed = match_type in HARD_MATCH_TYPES
    alias_source = ""
    alias_version = ""
    if match_type == MATCH_VERIFIED_ALIAS:
        if query_id and statement_id and query_id == statement_id:
            alias_source = "explicit_canonical_identifier"
            alias_version = "identifier-alignment/1.0"
        else:
            alias_source = VERIFIED_ALIAS_SOURCE
            alias_version = VERIFIED_ALIAS_VERSION

    relation_source = (
        VERIFIED_RELATION_SOURCE
        if match_type
        in {MATCH_EXPLICIT_PARENT, MATCH_EXPLICIT_CHILD, MATCH_EXPLICIT_SIBLING}
        else ""
    )
    reason = _REASON_BY_MATCH_TYPE[match_type]
    warning_code = "" if hard_match_allowed else reason
    canonical_key = (
        f"id:{query_id}"
        if query_id and statement_id and query_id == statement_id
        else _canonical_key(query_core)
        if hard_match_allowed
        else ""
    )

    return DiseaseMatchResult(
        query_raw=query_text,
        query_normalized=query_core,
        statement_raw=statement_text,
        statement_normalized=statement_core,
        query_canonical_id=query_id,
        statement_canonical_id=statement_id,
        canonical_disease_key=canonical_key,
        match_type=match_type,
        matched=hard_match_allowed,
        hard_match_allowed=hard_match_allowed,
        alias_source=alias_source,
        alias_version=alias_version,
        relation_source=relation_source,
        warning_code=warning_code,
        explanation_code=reason,
    )


__all__ = [
    "DISEASE_MATCHER_VERSION",
    "VERIFIED_ALIAS_VERSION",
    "VERIFIED_ALIAS_SOURCE",
    "VERIFIED_RELATION_SOURCE",
    "MATCH_EXACT_STRING",
    "MATCH_NORMALIZED_EXACT",
    "MATCH_VERIFIED_ALIAS",
    "MATCH_EXPLICIT_PARENT",
    "MATCH_EXPLICIT_CHILD",
    "MATCH_EXPLICIT_SIBLING",
    "MATCH_PAN_CANCER_OR_UNSPECIFIED",
    "MATCH_UNRESOLVED",
    "MATCH_INCOMPATIBLE",
    "DISEASE_MATCH_TYPES",
    "HARD_MATCH_TYPES",
    "DISEASE_EXACT_MATCH",
    "DISEASE_NORMALIZED_EXACT_MATCH",
    "DISEASE_VERIFIED_ALIAS_MATCH",
    "DISEASE_EXPLICIT_PARENT_NOT_HARD_MATCHED",
    "DISEASE_EXPLICIT_CHILD_NOT_HARD_MATCHED",
    "DISEASE_EXPLICIT_SIBLING_NOT_HARD_MATCHED",
    "DISEASE_RELATION_UNRESOLVED",
    "DISEASE_INCOMPATIBLE",
    "BIOMARKER_MISMATCH_DESPITE_DISEASE_ALIAS",
    "DiseaseMatchResult",
    "match_disease",
]
