"""Rilevamento deterministico delle contraddizioni nel CaseContext.

**Nessun LLM giudica.** Il rilevatore lavora sugli span testuali e sullo stato di
asserzione delle menzioni, entrambi deterministici.

Il benchmark RQ4 ha misurato che tutte e cinque le contraddizioni venivano
estratte senza segnalazione e instradate al retrieval: un testo che dice insieme
«KRAS wild-type» e «KRAS G12D mutation» produceva una candidate che proseguiva.

Il rilevatore è **conservativo**: segnala solo incompatibilità esplicite nel
testo. Una contraddizione non rilevata lascia il comportamento attuale; una
falsa contraddizione bloccherebbe un caso valido, che è il danno peggiore.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .mentions import ASSERTED, NEGATED, EntityMention, _norm

CONTRADICTION_DETECTOR_VERSION = "casecontext-contradiction-detector/1.0"

BLOCKING = "BLOCKING"
WARNING = "WARNING"

# Tipi di contraddizione
ASSERTED_AND_NEGATED = "ASSERTED_AND_NEGATED_ENTITY"
ALTERATION_VS_NEGATION = "SPECIFIC_ALTERATION_WITH_EXPLICIT_NEGATION"
DISEASE_CONFLICT = "MUTUALLY_EXCLUSIVE_DISEASE"
TREATMENT_HISTORY_CONFLICT = "TREATMENT_HISTORY_CONFLICT"
INTENT_CONFLICT = "INTENT_CONFLICT"

#: Coppie di stati mutuamente esclusivi per lo stesso gene.
_EXCLUSIVE_STATE_TERMS = (
    ("wild-type", "mutation"), ("wild type", "mutation"), ("wildtype", "mutation"),
    ("wild-type", "mutant"), ("negative", "positive"),
)

#: Marcatori di «nessuna terapia ricevuta».
_NO_TREATMENT_CUES = (
    "never received any systemic therapy", "has never received", "no prior therapy",
    "treatment-naive", "treatment naive", "mai ricevuto",
)

#: Marcatori di terapia effettivamente somministrata.
_TREATMENT_GIVEN_CUES = (
    "after ", "following ", "cycles of", "was treated with", "has received",
    "previously received", "progressed on", "dopo ", "cicli di",
)


@dataclass
class Contradiction:
    contradiction_id: str
    type: str
    entity_type: str
    normalized_entity: str
    positive_spans: list[dict[str, Any]] = field(default_factory=list)
    negative_spans: list[dict[str, Any]] = field(default_factory=list)
    reason_code: str = ""
    severity: str = WARNING

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _identifier(*parts: str) -> str:
    return "CTR-" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _span(text: str, needle: str) -> dict[str, Any] | None:
    index = text.lower().find(needle.lower())
    if index < 0:
        return None
    return {"quote": text[index:index + len(needle)],
            "start_offset": index, "end_offset": index + len(needle)}


def detect(
    clinical_text: str,
    mentions: list[EntityMention],
    case_context: dict[str, Any] | None = None,
) -> list[Contradiction]:
    """Contraddizioni esplicite nel testo. Deterministico, nessun LLM."""
    text = clinical_text or ""
    lowered = _norm(text)
    out: list[Contradiction] = []

    # 1. Stessa entità ASSERTED e NEGATED fra le menzioni.
    by_entity: dict[tuple[str, str], list[EntityMention]] = {}
    for mention in mentions:
        by_entity.setdefault((mention.entity_type, _norm(mention.raw_text)), []).append(mention)
    for (entity_type, value), group in sorted(by_entity.items()):
        statuses = {m.assertion_status for m in group}
        if ASSERTED in statuses and NEGATED in statuses:
            out.append(Contradiction(
                contradiction_id=_identifier(entity_type, value, ASSERTED_AND_NEGATED),
                type=ASSERTED_AND_NEGATED, entity_type=entity_type, normalized_entity=value,
                positive_spans=[m.source_span for m in group
                                if m.assertion_status == ASSERTED and m.source_span],
                negative_spans=[m.source_span for m in group
                                if m.assertion_status == NEGATED and m.source_span],
                reason_code="SAME_ENTITY_ASSERTED_AND_NEGATED", severity=BLOCKING,
            ))

    # 2. Gene con stato mutuamente esclusivo nello stesso testo.
    genes = {_norm(m.raw_text) for m in mentions if m.entity_type == "GENE" and m.raw_text}
    for gene in sorted(genes):
        if not gene:
            continue
        for negative_term, positive_term in _EXCLUSIVE_STATE_TERMS:
            has_negative = re.search(rf"{re.escape(gene)}\s+{re.escape(negative_term)}", lowered)
            # L'alterazione specifica vale come «positive» se compare accanto al
            # gene **ed è diversa dal termine negativo stesso**: in «KRAS
            # wild-type» il parser estrae `wild-type` come alterazione, e
            # contarla come positiva renderebbe contraddittorio ogni wild-type.
            specific = [
                m for m in mentions
                if m.entity_type == "ALTERATION" and _norm(m.raw_text)
                and negative_term not in _norm(m.raw_text)
                and _norm(m.raw_text) not in negative_term
                and re.search(rf"{re.escape(gene)}\s+{re.escape(_norm(m.raw_text))}", lowered)
            ]
            has_positive = bool(specific) or bool(
                re.search(rf"{re.escape(gene)}\s+{re.escape(positive_term)}", lowered))
            if has_negative and has_positive:
                out.append(Contradiction(
                    contradiction_id=_identifier(gene, negative_term, ALTERATION_VS_NEGATION),
                    type=ALTERATION_VS_NEGATION, entity_type="GENE", normalized_entity=gene,
                    positive_spans=[s for s in (_span(text, m.raw_text) for m in specific) if s],
                    negative_spans=[s for s in [_span(text, f"{gene} {negative_term}")] if s],
                    reason_code=f"GENE_STATE_CONFLICT:{negative_term}_VS_SPECIFIC_ALTERATION",
                    severity=BLOCKING,
                ))
                break

    # 3. Negazione esplicita di un test e alterazione specifica dello stesso gene.
    for gene in sorted(genes):
        if not gene:
            continue
        negated_test = re.search(
            rf"{re.escape(gene)}[^.]{{0,40}}(?:testing\s+was\s+negative|tested\s+negative|was\s+negative)",
            lowered)
        specific = [m for m in mentions if m.entity_type == "ALTERATION"
                    and m.assertion_status == ASSERTED and m.raw_text]
        if negated_test and specific:
            out.append(Contradiction(
                contradiction_id=_identifier(gene, "negative-test", ALTERATION_VS_NEGATION),
                type=ALTERATION_VS_NEGATION, entity_type="GENE", normalized_entity=gene,
                positive_spans=[s for s in (_span(text, m.raw_text) for m in specific) if s],
                negative_spans=[{"quote": negated_test.group(0),
                                 "start_offset": negated_test.start(),
                                 "end_offset": negated_test.end()}],
                reason_code="NEGATIVE_TEST_WITH_SPECIFIC_ALTERATION", severity=BLOCKING,
            ))

    # 4. Due malattie primarie mutuamente esclusive.
    disease_mentions = [m for m in mentions if m.entity_type == "DISEASE"]
    disease_values = sorted({_norm(m.raw_text) for m in disease_mentions if m.raw_text})
    explicit_primaries = re.findall(r"(?:is a primary|primary)\s+([a-z ]+?(?:carcinoma|cancer|adenocarcinoma))",
                                    lowered)
    if len(disease_values) >= 1 and explicit_primaries:
        for primary in {p.strip() for p in explicit_primaries}:
            for declared in disease_values:
                if declared and primary and declared not in primary and primary not in declared:
                    out.append(Contradiction(
                        contradiction_id=_identifier(declared, primary, DISEASE_CONFLICT),
                        type=DISEASE_CONFLICT, entity_type="DISEASE",
                        normalized_entity=f"{declared} vs {primary}",
                        positive_spans=[s for s in [_span(text, declared)] if s],
                        negative_spans=[s for s in [_span(text, primary)] if s],
                        reason_code="TWO_MUTUALLY_EXCLUSIVE_PRIMARY_DISEASES",
                        severity=BLOCKING,
                    ))
                    break

    # 5. «Mai ricevuto terapia» insieme a una terapia somministrata.
    if any(cue in lowered for cue in _NO_TREATMENT_CUES) and \
            any(cue in lowered for cue in _TREATMENT_GIVEN_CUES):
        negative = next((c for c in _NO_TREATMENT_CUES if c in lowered), "")
        positive = next((c for c in _TREATMENT_GIVEN_CUES if c in lowered), "")
        out.append(Contradiction(
            contradiction_id=_identifier(negative, positive, TREATMENT_HISTORY_CONFLICT),
            type=TREATMENT_HISTORY_CONFLICT, entity_type="INTERVENTION",
            normalized_entity="treatment history",
            positive_spans=[s for s in [_span(text, positive)] if s],
            negative_spans=[s for s in [_span(text, negative)] if s],
            reason_code="NO_PRIOR_THERAPY_CLAIMED_WITH_ADMINISTERED_THERAPY",
            severity=BLOCKING,
        ))

    # 6. L'istruzione nega ciò che la domanda chiede.
    if re.search(r"do not evaluate any specific drug", lowered) and \
            re.search(r"whether\s+\w+\s+is\s+appropriate", lowered):
        out.append(Contradiction(
            contradiction_id=_identifier("intent", "conflict", INTENT_CONFLICT),
            type=INTENT_CONFLICT, entity_type="INTERVENTION", normalized_entity="query intent",
            positive_spans=[s for s in [_span(text, "whether")] if s],
            negative_spans=[s for s in [_span(text, "Do not evaluate any specific drug")] if s],
            reason_code="INSTRUCTION_NEGATES_THE_QUESTION", severity=BLOCKING,
        ))

    return _dedupe(out)


def _dedupe(items: list[Contradiction]) -> list[Contradiction]:
    seen: set[str] = set()
    out: list[Contradiction] = []
    for item in items:
        if item.contradiction_id not in seen:
            seen.add(item.contradiction_id)
            out.append(item)
    return out


def has_blocking(contradictions: list[Contradiction]) -> bool:
    return any(c.severity == BLOCKING for c in contradictions)
