"""Valutazione deterministica di un'espressione di alterazione contro un CaseContext.

**Non collegata al runtime.** La funzione è definita, testata e documentata qui
per la futura integrazione nel Pre-Retrieval Eligibility Gate, ma nessun modulo
del runtime la importa: collegarla ora cambierebbe il comportamento del
retrieval, cosa esclusa dallo scopo di questo branch.

Piano di integrazione in `docs/graph_candidate_v3/09_runtime_admission_policy.md`.

Regola centrale, che è il motivo per cui la funzione esiste::

    un match su A non può produrre FULL_MATCH per "A AND B"

Nella v2 questa distinzione non era esprimibile, perché ``A AND B`` veniva
serializzato come il solo ``A``.
"""

from __future__ import annotations

from typing import Any, Iterable

from .alterations import AstNode, ast_from_dict

FULL_MATCH = "FULL_MATCH"
PARTIAL_MATCH = "PARTIAL_MATCH"
NO_MATCH = "NO_MATCH"
INSUFFICIENT_CASE_INFORMATION = "INSUFFICIENT_CASE_INFORMATION"
EXPRESSION_UNAVAILABLE = "EXPRESSION_UNAVAILABLE"
EXPRESSION_UNSUPPORTED = "EXPRESSION_UNSUPPORTED"

_UNSUPPORTED_STATUSES = {"MALFORMED_EXPRESSION", "UNSUPPORTED_EXPRESSION", "AMBIGUOUS_OPERATOR"}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _case_terms(case_context: dict[str, Any] | None) -> set[tuple[str, str]]:
    """Coppie ``(gene, alteration)`` presenti nel CaseContext."""
    out: set[tuple[str, str]] = set()
    for biomarker in (case_context or {}).get("biomarkers") or []:
        gene = _norm(biomarker.get("gene"))
        alteration = _norm(biomarker.get("alteration"))
        if gene or alteration:
            out.add((gene, alteration))
    return out


def _term_present(node: AstNode, case_terms: set[tuple[str, str]]) -> bool:
    gene = _norm(node.gene)
    alteration = _norm(node.alteration)
    for case_gene, case_alteration in case_terms:
        gene_ok = bool(gene) and (gene == case_gene)
        alteration_ok = bool(alteration) and (
            alteration == case_alteration
            or (case_alteration and alteration in case_alteration)
            or (case_alteration and case_alteration in alteration)
        )
        if gene_ok and alteration_ok:
            return True
    return False


def _evaluate(node: AstNode, case_terms: set[tuple[str, str]]) -> tuple[bool, int, int]:
    """``(soddisfatta, termini_soddisfatti, termini_totali)``."""
    if node.node_type == "TERM":
        present = _term_present(node, case_terms)
        return present, int(present), 1
    if node.node_type == "NOT":
        satisfied, matched, total = _evaluate(node.operands[0], case_terms)
        # NOT è soddisfatto quando il termine NON è presente. Il conteggio dei
        # termini resta quello dell'operando, per non gonfiare il parziale.
        return (not satisfied), matched, total
    results = [_evaluate(operand, case_terms) for operand in node.operands]
    matched = sum(r[1] for r in results)
    total = sum(r[2] for r in results)
    if node.node_type == "AND":
        return all(r[0] for r in results), matched, total
    if node.node_type == "OR":
        return any(r[0] for r in results), matched, total
    return False, matched, total


def evaluate_alteration_expression(
    case_context: dict[str, Any] | None,
    alteration_expression_ast: dict[str, Any] | None,
    parse_status: str | None = None,
) -> dict[str, Any]:
    """Esito del confronto fra CaseContext ed espressione di alterazione."""
    if parse_status in _UNSUPPORTED_STATUSES:
        return {"result": EXPRESSION_UNSUPPORTED, "matched_terms": 0, "total_terms": 0}
    if not alteration_expression_ast:
        return {"result": EXPRESSION_UNAVAILABLE, "matched_terms": 0, "total_terms": 0}

    node = ast_from_dict(alteration_expression_ast)
    case_terms = _case_terms(case_context)
    if not case_terms:
        return {"result": INSUFFICIENT_CASE_INFORMATION, "matched_terms": 0,
                "total_terms": len(node.terms())}

    satisfied, matched, total = _evaluate(node, case_terms)
    if satisfied:
        result = FULL_MATCH
    elif matched > 0:
        result = PARTIAL_MATCH
    else:
        result = NO_MATCH
    return {"result": result, "matched_terms": matched, "total_terms": total}
