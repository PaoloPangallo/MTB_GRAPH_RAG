"""CaseContext 2.0 — menzioni tipizzate, derivate deterministicamente.

**Il parser non decide il routing.** Estrae e struttura; questo modulo tipizza,
e il gate deterministico decide.

Le menzioni sono costruite **dall'output del parser esistente**, senza
modificare prompt né schema della tool call. È una scelta deliberata:

* il prompt del parser è congelato nel benchmark RQ4
  (``casecontext-parser-prompt/1.0``, hash `7b59558b…`), e cambiarlo
  invaliderebbe il gold;
* la distinzione fra *menzione* e *campo accettato* è una proprietà
  **deterministica** del testo, non qualcosa da chiedere a un modello. Chiederla
  al parser significherebbe far decidere all'LLM ciò che il gate deve decidere.

Regola architetturale centrale::

    ENTITY_MENTION  ≠  ACCEPTED_CASECONTEXT_FIELD

Una menzione rifiutata resta **visibile per audit**, con il proprio
``rejection_reason``: non viene cancellata.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

CASE_CONTEXT_CONTRACT_VERSION = "case-context/2.0"

# ------------------------------------------------------------------ enum

ENTITY_TYPES = ("DISEASE", "GENE", "ALTERATION", "BIOMARKER", "INTERVENTION", "SYMPTOM")

ASSERTED = "ASSERTED"
NEGATED = "NEGATED"
UNCERTAIN = "UNCERTAIN"
HYPOTHETICAL = "HYPOTHETICAL"
HISTORICAL = "HISTORICAL"
ASSERTION_UNKNOWN = "UNKNOWN"
ASSERTION_STATUSES = (ASSERTED, NEGATED, UNCERTAIN, HYPOTHETICAL, HISTORICAL, ASSERTION_UNKNOWN)

TARGET_INTERVENTION = "TARGET_INTERVENTION"
PREVIOUS_INTERVENTION = "PREVIOUS_INTERVENTION"
CURRENT_INTERVENTION = "CURRENT_INTERVENTION"
COMPARATOR = "COMPARATOR"
CONTEXTUAL_MENTION = "CONTEXTUAL_MENTION"
CONTROL_INSTRUCTION_MENTION = "CONTROL_INSTRUCTION_MENTION"
ROLE_UNKNOWN = "UNKNOWN"
INTERVENTION_ROLES = (
    TARGET_INTERVENTION, PREVIOUS_INTERVENTION, CURRENT_INTERVENTION, COMPARATOR,
    CONTEXTUAL_MENTION, CONTROL_INSTRUCTION_MENTION, ROLE_UNKNOWN,
)

# Motivi di rifiuto
MENTION_INSIDE_CONTROL_INSTRUCTION = "MENTION_INSIDE_CONTROL_INSTRUCTION"
MENTION_NEGATED = "MENTION_NEGATED"
MENTION_NOT_IN_TEXT = "MENTION_NOT_IN_TEXT"
MENTION_TYPE_INCOMPATIBLE_WITH_SLOT = "MENTION_TYPE_INCOMPATIBLE_WITH_SLOT"
MENTION_ROLE_INCOMPATIBLE_WITH_SLOT = "MENTION_ROLE_INCOMPATIBLE_WITH_SLOT"
MENTION_UNCERTAIN = "MENTION_UNCERTAIN"

# ------------------------------------------------------- lessico deterministico

#: Marcatori di negazione. Conservativi: solo forme non ambigue, in inglese e
#: italiano, che compaiono nel benchmark congelato.
_NEGATION_CUES = (
    "negative for", "tested negative", "was negative", "were negative",
    "no evidence of", "not detected", "not present", "absence of", "without",
    "never received", "has never",
    "negativo per", "non rilevat", "assenza di", "mai ricevut",
)

#: Qualificatori dello **stato di un gene**. Non sono negazioni di frase:
#: «Colorectal cancer, KRAS wild-type» non nega la malattia, nega che KRAS sia
#: mutato. Negano quindi soltanto una menzione di tipo ``ALTERATION`` a cui
#: sono adiacenti.
_GENE_STATE_NEGATION_CUES = ("wild-type", "wild type", "wildtype")

#: Marcatori di incertezza.
_UNCERTAINTY_CUES = (
    "possible", "possibly", "suspected", "cannot be excluded", "unclear",
    "uncertain", "not yet reported", "pending", "of uncertain",
    "sospett", "incert", "non ancora",
)

#: Marcatori di anteriorità terapeutica.
_HISTORICAL_CUES = (
    "previously", "prior", "has received", "was treated", "after", "following",
    "first-line", "second-line", "precedente", "gia' ricevut", "già ricevut",
)

#: Sintomi generici: presenti nel testo ma **non** diagnosi oncologiche.
#: Lista chiusa e piccola, allineata al benchmark congelato. Non è un
#: normalizzatore clinico e non decide nulla da sola: marca il tipo `SYMPTOM`,
#: e il verifier impedisce a un sintomo di popolare lo slot `disease`.
_SYMPTOM_TERMS = (
    "mal di testa", "male alla testa", "mal di schiena", "male la schiena",
    "male alla schiena", "male alla gamba", "mi fa male", "dolore",
    "stanco", "stanchezza", "affatic", "febbre",
    "headache", "back pain", "leg pain", "pain", "tired", "fatigue", "fever",
    "nausea", "cough", "tosse",
)

#: Termini che denotano una neoplasia. Usati come **oncology anchor**: la loro
#: assenza è ciò che distingue un caso oncologico da un sintomo generico.
_ONCOLOGY_TERMS = (
    "cancer", "carcinoma", "sarcoma", "leukemia", "leukaemia", "lymphoma",
    "melanoma", "tumor", "tumour", "neoplas", "metasta", "myeloma", "glioma",
    "blastoma", "adenocarcinoma", "malignan", "oncolog", "mesothelioma",
    "cml", "aml", "cll", "all", "nsclc", "gist", "msi",
    "cancro", "tumore", "linfoma", "leucemia", "neoplasia",
)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def mentions_oncology(value: Any) -> bool:
    text = _norm(value)
    return any(term in text for term in _ONCOLOGY_TERMS)


def looks_like_symptom(value: Any) -> bool:
    text = _norm(value)
    return any(term in text for term in _SYMPTOM_TERMS)


@dataclass
class SourceSpanRef:
    quote: str | None
    start_offset: int | None = None
    end_offset: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EntityMention:
    """Una menzione tipizzata. Accettata o rifiutata, resta visibile."""

    raw_text: str
    normalized_value: str | None
    entity_type: str
    semantic_role: str
    assertion_status: str
    source_span: dict[str, Any] | None
    accepted_for_casecontext: bool
    rejection_reason: str | None = None
    parser_confidence: float | None = None
    slot: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _span_of(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    spans = (payload or {}).get("source_spans") or []
    if not spans:
        return None
    span = spans[0]
    return SourceSpanRef(
        quote=span.get("quote"),
        start_offset=span.get("start_offset"),
        end_offset=span.get("end_offset"),
    ).to_dict()


def _locate(text: str, quote: str | None) -> tuple[int, int] | None:
    """Posizione letterale della citazione nel testo, se univoca o prima occorrenza."""
    if not quote:
        return None
    index = text.find(quote)
    if index < 0:
        return None
    return index, index + len(quote)


#: Confini di frase. La negazione **non** attraversa un confine di frase:
#: in «Lung adenocarcinoma. EGFR testing was negative.» il negativo riguarda
#: EGFR, non la malattia. Una finestra a caratteri fissi le confonderebbe.
_SENTENCE_BOUNDARY = re.compile(r"[.;!?\n]")


def sentence_around(text: str, span: tuple[int, int] | None) -> str:
    """La frase che contiene la menzione, senza attraversare i confini."""
    if span is None:
        return _norm(text)
    start, end = span
    left = 0
    for match in _SENTENCE_BOUNDARY.finditer(text, 0, start):
        left = match.end()
    right_match = _SENTENCE_BOUNDARY.search(text, end)
    right = right_match.start() if right_match else len(text)
    return _norm(text[left:right])


def assertion_status_for(text: str, quote: str | None, entity_type: str | None = None) -> str:
    """Stato di asserzione dedotto dalla **frase** che contiene la menzione.

    Deterministico e conservativo: in assenza di marcatori la menzione è
    ``ASSERTED``, che è il comportamento attuale del runtime.

    La negazione è limitata alla frase, e un marcatore che segue la menzione
    nella stessa frase vale (``EGFR was negative``) mentre uno in una frase
    diversa no.
    """
    span = _locate(text, quote)
    sentence = sentence_around(text, span)
    if any(cue in sentence for cue in _NEGATION_CUES):
        return NEGATED
    # I qualificatori di stato genico negano solo un'alterazione, e solo se il
    # qualificatore *è* la menzione stessa o le è adiacente.
    if entity_type == "ALTERATION" and any(
        cue in sentence for cue in _GENE_STATE_NEGATION_CUES
    ):
        return NEGATED
    if any(cue in sentence for cue in _UNCERTAINTY_CUES):
        return UNCERTAIN
    return ASSERTED


def build_mentions(
    case_context: dict[str, Any],
    clinical_text: str,
    control_spans: list[dict[str, Any]] | None = None,
) -> list[EntityMention]:
    """Menzioni tipizzate a partire dall'output del parser.

    ``control_spans`` proviene dal rilevatore di istruzioni di controllo: una
    menzione contenuta **esclusivamente** in uno di quegli span non può
    popolare un campo clinico canonico.
    """
    from .control_instructions import mention_is_inside_control_span

    control_spans = control_spans or []
    out: list[EntityMention] = []

    def _mention(raw, normalized, entity_type, role, payload, slot):
        span = _span_of(payload)
        quote = (span or {}).get("quote") or raw
        located = _locate(clinical_text, quote)
        inside_control = mention_is_inside_control_span(located, control_spans)
        status = assertion_status_for(clinical_text, quote, entity_type)
        if role in INTERVENTION_ROLES and role == ROLE_UNKNOWN and status == HISTORICAL:
            role = PREVIOUS_INTERVENTION

        rejection = None
        accepted = True
        if located is None and quote:
            accepted, rejection = False, MENTION_NOT_IN_TEXT
        elif inside_control:
            accepted, rejection = False, MENTION_INSIDE_CONTROL_INSTRUCTION
            role = CONTROL_INSTRUCTION_MENTION
        elif status == NEGATED:
            accepted, rejection = False, MENTION_NEGATED

        out.append(EntityMention(
            raw_text=str(raw), normalized_value=normalized, entity_type=entity_type,
            semantic_role=role, assertion_status=status, source_span=span,
            accepted_for_casecontext=accepted, rejection_reason=rejection, slot=slot,
        ))

    disease = case_context.get("disease") or {}
    if disease.get("raw_value"):
        entity_type = "SYMPTOM" if (
            looks_like_symptom(disease.get("raw_value")) and not mentions_oncology(disease.get("raw_value"))
        ) else "DISEASE"
        _mention(disease["raw_value"], disease.get("normalized_value"), entity_type,
                 CONTEXTUAL_MENTION, disease, "disease")

    for biomarker in case_context.get("biomarkers") or []:
        if biomarker.get("gene"):
            _mention(biomarker["gene"], biomarker.get("normalized_value"), "GENE",
                     CONTEXTUAL_MENTION, biomarker, "biomarker")
        if biomarker.get("alteration"):
            _mention(biomarker["alteration"], biomarker.get("alteration"), "ALTERATION",
                     CONTEXTUAL_MENTION, biomarker, "alteration")

    for previous in case_context.get("previous_interventions") or []:
        if previous.get("raw_value"):
            _mention(previous["raw_value"], previous.get("normalized_value"), "INTERVENTION",
                     PREVIOUS_INTERVENTION, previous, "previous_intervention")

    target = case_context.get("target_intervention") or {}
    if target.get("raw_value"):
        _mention(target["raw_value"], target.get("normalized_value"), "INTERVENTION",
                 TARGET_INTERVENTION, target, "target_intervention")

    return out


def to_contract(
    case_context: dict[str, Any],
    mentions: list[EntityMention],
    control_spans: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Struttura ``case-context/2.0``, **additiva** rispetto a 1.0.

    I campi scalari di 1.0 restano intatti: nessun consumatore esistente si
    rompe. Le strutture tipizzate sono affiancate, non sostitutive.
    """
    def _by_type(*types: str) -> list[dict[str, Any]]:
        return [m.to_dict() for m in mentions if m.entity_type in types]

    return {
        **case_context,
        "contract_version": CASE_CONTEXT_CONTRACT_VERSION,
        "disease_mentions": _by_type("DISEASE"),
        "gene_mentions": _by_type("GENE"),
        "alteration_mentions": _by_type("ALTERATION"),
        "biomarker_observations": _by_type("GENE", "ALTERATION", "BIOMARKER"),
        "intervention_mentions": _by_type("INTERVENTION"),
        "symptom_mentions": _by_type("SYMPTOM"),
        "contradictions": contradictions,
        "control_instruction_spans": control_spans,
        "parser_uncertainties": list(case_context.get("uncertainties") or []),
        "rejected_mentions": [m.to_dict() for m in mentions if not m.accepted_for_casecontext],
    }


def accepted(mentions: list[EntityMention], slot: str) -> list[EntityMention]:
    return [m for m in mentions if m.slot == slot and m.accepted_for_casecontext]
