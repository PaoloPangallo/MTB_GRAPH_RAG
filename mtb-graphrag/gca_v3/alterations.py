"""Parser deterministico delle espressioni di alterazione.

Grammatica implementata **solo** per gli operatori osservati nell'export
(cfr. `01_source_semantics_audit.md`)::

    expression := or_expr
    or_expr    := and_expr ( "OR" and_expr )*
    and_expr   := unary   ( "AND" unary )*
    unary      := "NOT" unary | primary
    primary    := "(" expression ")" | TERM
    TERM       := <testo libero: gene + alterazione>

Precedenza: ``NOT`` > ``AND`` > ``OR``. Le parentesi sono esplicite.

**Le parentesi sono ambigue nella sorgente** e la disambiguazione è
deterministica: su 310 gruppi parentetici osservati, 5 sono raggruppamenti
logici e 305 fanno parte del termine (300 annotazioni HGVS come
``(c.598C>T)``, 5 suffissi descrittivi come ``(ATI)``). La regola adottata è:

    un gruppo parentetico è un raggruppamento logico **se e solo se**
    contiene un operatore booleano al proprio livello

Questa regola separa correttamente tutti e 310 i casi del corpus.

Nessuna normalizzazione clinica: i termini non sono mappati, non sono
deduplicati e non sono riordinati. L'ordine è preservato perché in
``A AND ( B OR C )`` è semanticamente rilevante.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

# Stati di parsing
ATOMIC = "ATOMIC"
PARSED_EXACT = "PARSED_EXACT"
PARSED_WITH_WARNINGS = "PARSED_WITH_WARNINGS"
AMBIGUOUS_OPERATOR = "AMBIGUOUS_OPERATOR"
UNSUPPORTED_EXPRESSION = "UNSUPPORTED_EXPRESSION"
MALFORMED_EXPRESSION = "MALFORMED_EXPRESSION"
MISSING = "MISSING"

#: Operatori booleani riconosciuti, come parole intere e in maiuscolo.
#: Il minuscolo `or`/`and` non è trattato come operatore: comparirebbe dentro
#: nomi di alterazione senza esserlo.
_OPERATOR_RE = re.compile(r"\b(AND|OR|NOT)\b")
_TOKEN_RE = re.compile(r"\(|\)|\bAND\b|\bOR\b|\bNOT\b")

#: Separatori che nell'export **non** sono operatori booleani: appartengono al
#: nome dell'alterazione o del farmaco. Non vengono interpretati.
NON_OPERATOR_SEPARATORS = ("/", "+", "&", ",", ";")


@dataclass
class AstNode:
    """Nodo dell'albero sintattico."""

    node_type: str  # AND | OR | NOT | TERM
    operands: list["AstNode"] = field(default_factory=list)
    gene: str | None = None
    alteration: str | None = None
    raw: str | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.node_type == "TERM":
            return {
                "node_type": "TERM",
                "gene": self.gene,
                "alteration": self.alteration,
                "raw": self.raw,
            }
        return {
            "node_type": self.node_type,
            "operands": [operand.to_dict() for operand in self.operands],
        }

    def terms(self) -> list["AstNode"]:
        if self.node_type == "TERM":
            return [self]
        out: list[AstNode] = []
        for operand in self.operands:
            out.extend(operand.terms())
        return out

    def canonical(self) -> str:
        """Espressione canonica, per il round-trip test.

        L'ordine degli operandi è **preservato**, non ordinato: riordinare
        cambierebbe ``A AND ( B OR C )`` in modo non verificabile.
        """
        if self.node_type == "TERM":
            return self.raw or " ".join(x for x in (self.gene, self.alteration) if x)
        if self.node_type == "NOT":
            return f"NOT {self.operands[0].canonical()}"
        joined = f" {self.node_type} ".join(o.canonical() for o in self.operands)
        return f"( {joined} )"


class ParseError(Exception):
    pass


def _split_gene_alteration(raw: str) -> tuple[str | None, str | None]:
    """Separa gene e alterazione di un termine.

    Il gene è il primo token quando è un simbolo HUGO plausibile o una fusione
    (``EML4::ALK``). Se non lo è, il termine resta senza gene: **non** viene
    indovinato.
    """
    text = raw.strip()
    if not text:
        return None, None
    parts = text.split(None, 1)
    head = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else None
    # Fusione: EML4::ALK Fusion  -> gene = EML4::ALK
    if "::" in head:
        return head, rest
    # Simbolo genico plausibile: maiuscolo/numeri, non una parola comune.
    if re.fullmatch(r"[A-Z][A-Z0-9\-]{0,14}", head) and rest:
        return head, rest
    return None, text


def _tokenize(text: str) -> list[str]:
    """Tokenizza in operatori, parentesi e testo dei termini.

    Le parentesi che **non** racchiudono un operatore sono neutralizzate prima
    della tokenizzazione: appartengono al termine.
    """
    protected = _protect_non_grouping_parentheses(text)
    tokens: list[str] = []
    position = 0
    for match in _TOKEN_RE.finditer(protected):
        chunk = protected[position:match.start()].strip()
        if chunk:
            tokens.append(chunk)
        tokens.append(match.group(0))
        position = match.end()
    tail = protected[position:].strip()
    if tail:
        tokens.append(tail)
    return tokens


_PLACEHOLDER_OPEN = "\x01"
_PLACEHOLDER_CLOSE = "\x02"


def _protect_non_grouping_parentheses(text: str) -> str:
    """Sostituisce con segnaposto le parentesi che fanno parte del termine."""
    out = text
    while True:
        replaced = False
        for match in re.finditer(r"\(([^()]*)\)", out):
            if not _OPERATOR_RE.search(match.group(1)):
                out = (out[:match.start()] + _PLACEHOLDER_OPEN + match.group(1)
                       + _PLACEHOLDER_CLOSE + out[match.end():])
                replaced = True
                break
        if not replaced:
            return out


def _restore(text: str) -> str:
    return text.replace(_PLACEHOLDER_OPEN, "(").replace(_PLACEHOLDER_CLOSE, ")")


class _Parser:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.position = 0

    def peek(self) -> str | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def next(self) -> str:
        token = self.tokens[self.position]
        self.position += 1
        return token

    def parse(self) -> AstNode:
        node = self.parse_or()
        if self.position != len(self.tokens):
            raise ParseError(f"token residuo: {self.tokens[self.position:]!r}")
        return node

    def parse_or(self) -> AstNode:
        operands = [self.parse_and()]
        while self.peek() == "OR":
            self.next()
            operands.append(self.parse_and())
        return operands[0] if len(operands) == 1 else AstNode("OR", operands)

    def parse_and(self) -> AstNode:
        operands = [self.parse_unary()]
        while self.peek() == "AND":
            self.next()
            operands.append(self.parse_unary())
        return operands[0] if len(operands) == 1 else AstNode("AND", operands)

    def parse_unary(self) -> AstNode:
        if self.peek() == "NOT":
            self.next()
            return AstNode("NOT", [self.parse_unary()])
        return self.parse_primary()

    def parse_primary(self) -> AstNode:
        token = self.peek()
        if token is None:
            raise ParseError("espressione troncata")
        if token == "(":
            self.next()
            node = self.parse_or()
            if self.peek() != ")":
                raise ParseError("parentesi non chiusa")
            self.next()
            return node
        if token in {")", "AND", "OR"}:
            raise ParseError(f"operatore inatteso: {token!r}")
        raw = _restore(self.next()).strip()
        gene, alteration = _split_gene_alteration(raw)
        return AstNode("TERM", gene=gene, alteration=alteration, raw=raw)


def expression_hash(node: AstNode | None) -> str | None:
    if node is None:
        return None
    payload = json.dumps(node.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_alteration_expression(raw: Any) -> dict[str, Any]:
    """Analizza un'espressione di alterazione.

    Non solleva mai: un'espressione non analizzabile produce uno stato esplicito
    e **preserva integralmente il raw**. In nessun caso viene restituito solo il
    primo termine.
    """
    text = str(raw or "").strip()
    if not text:
        return {
            "alteration_expression_raw": None,
            "alteration_terms": [],
            "alteration_expression_ast": None,
            "alteration_parse_status": MISSING,
            "alteration_expression_hash": None,
            "alteration_parse_warnings": [],
        }

    warnings: list[str] = []
    has_operator = bool(_OPERATOR_RE.search(text))

    if not has_operator:
        gene, alteration = _split_gene_alteration(text)
        node = AstNode("TERM", gene=gene, alteration=alteration, raw=text)
        return {
            "alteration_expression_raw": text,
            "alteration_terms": [{"gene": gene, "alteration": alteration, "raw": text}],
            "alteration_expression_ast": node.to_dict(),
            "alteration_parse_status": ATOMIC,
            "alteration_expression_hash": expression_hash(node),
            "alteration_parse_warnings": [],
            "alteration_canonical_expression": node.canonical(),
        }

    try:
        node = _Parser(_tokenize(text)).parse()
    except (ParseError, IndexError) as error:
        return {
            "alteration_expression_raw": text,
            "alteration_terms": [],
            "alteration_expression_ast": None,
            "alteration_parse_status": MALFORMED_EXPRESSION,
            "alteration_expression_hash": None,
            "alteration_parse_warnings": [f"PARSE_ERROR:{error}"],
        }

    terms = [
        {"gene": t.gene, "alteration": t.alteration, "raw": t.raw}
        for t in node.terms()
    ]
    if any(t["gene"] is None for t in terms):
        warnings.append("TERM_WITHOUT_RECOGNISED_GENE")
    for separator in NON_OPERATOR_SEPARATORS:
        if any(separator in (t["raw"] or "") for t in terms):
            warnings.append(f"TERM_CONTAINS_SEPARATOR:{separator}")
            break

    status = PARSED_WITH_WARNINGS if warnings else PARSED_EXACT
    return {
        "alteration_expression_raw": text,
        "alteration_terms": terms,
        "alteration_expression_ast": node.to_dict(),
        "alteration_parse_status": status,
        "alteration_expression_hash": expression_hash(node),
        "alteration_parse_warnings": warnings,
        "alteration_canonical_expression": node.canonical(),
    }


def ast_from_dict(value: dict[str, Any] | None) -> AstNode | None:
    """Ricostruisce un AST da un record serializzato."""
    if not value:
        return None
    if value.get("node_type") == "TERM":
        return AstNode("TERM", gene=value.get("gene"),
                       alteration=value.get("alteration"), raw=value.get("raw"))
    return AstNode(
        value["node_type"],
        [ast_from_dict(operand) for operand in value.get("operands") or []],
    )
