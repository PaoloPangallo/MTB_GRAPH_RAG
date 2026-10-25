"""CaseContext 2.0 — menzioni tipizzate, derivate deterministicamente.

**Il parser non decide il routing.** Estrae e struttura; questo modulo tipizza,
e il gate deterministico decide.

Le menzioni sono costruite dall'output del parser, inclusa la rappresentazione
ricca multi-entità. La distinzione fra *menzione* e *campo accettato* resta una
proprietà **deterministica** del testo, non qualcosa da delegare al modello.

Regola architetturale centrale::

    ENTITY_MENTION  ≠  ACCEPTED_CASECONTEXT_FIELD

Una menzione rifiutata resta **visibile per audit**, con il proprio
``rejection_reason``: non viene cancellata.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .pair_grounding import ground_pair

CASE_CONTEXT_CONTRACT_VERSION = "case-context/2.0"

# ------------------------------------------------------------------ enum

ENTITY_TYPES = ("DISEASE", "GENE", "ALTERATION", "BIOMARKER", "INTERVENTION", "SYMPTOM", "TRIAL", "COMPANION_DIAGNOSTIC")

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
MENTION_FIELD_NOT_IN_TEXT = "MENTION_FIELD_NOT_IN_TEXT"

# ------------------------------------------------------- lessico deterministico

#: Marcatori di negazione. Conservativi: solo forme non ambigue, in inglese e
#: italiano, che compaiono nel benchmark congelato.
_NEGATION_CUES = (
    "negative for", "tested negative", "was negative", "were negative",
    "no evidence of", "not detected", "not present", "absence of", "without",
    "never received", "has never",
    "negativo per", "non rilevat", "assenza di", "mai ricevut",
)

_NEGATION_PATTERNS = (
    re.compile(r"\bno\s+(?:[a-z0-9-]+\s+){0,3}(?:mutation|mutations|alteration|amplification|amplified|deletion|fusion|rearrangement|expression|evidence)\b"),
    re.compile(r"\b(?:mutation|mutations|alteration|amplification|amplified|deletion|fusion|rearrangement|expression)\s+(?:was|were|is|are)\s+not\s+(?:detected|present|found|amplified)\b"),
    re.compile(r"\b(?:is|was|were|testing\s+was|assay\s+was)\s+negative\b"),
    re.compile(r"\bnot\s+amplified\b"),
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
    normalized_quote = _norm(quote)
    if entity_type in {"GENE", "ALTERATION"} and re.search(
        r"\bno\s+[a-z0-9 -]+\s+(?:detected|found|present)\b", normalized_quote,
    ):
        return NEGATED
    if entity_type in {"TRIAL", "COMPANION_DIAGNOSTIC"} and normalized_quote in sentence:
        prefix = sentence.split(normalized_quote, 1)[0]
        if re.search(r"\b(?:no|not|without)\s+(?:\S+\s+){0,3}$", prefix):
            return NEGATED
    if re.search(r"\bnegative\b|\bnot\s+amplified\b", normalized_quote):
        return NEGATED
    if entity_type == "GENE" and any(cue in normalized_quote for cue in _GENE_STATE_NEGATION_CUES):
        return NEGATED
    # In a sentence containing two assays, a positive clause must not inherit
    # the negation of a later negative clause.
    if entity_type == "ALTERATION" and re.search(r"\bpositive\b|\bdetected\b|\bamplified\b", normalized_quote):
        if not re.search(r"\bnot\b|\bnegative\b|\bno\b", normalized_quote):
            return ASSERTED
    if any(cue in sentence for cue in _NEGATION_CUES) or any(
        pattern.search(sentence) for pattern in _NEGATION_PATTERNS
    ):
        return NEGATED
    # I qualificatori di stato genico negano solo un'alterazione, e solo se il
    # qualificatore *è* la menzione stessa o le è adiacente.
    if entity_type == "ALTERATION" and quote:
        if any(cue in normalized_quote for cue in _GENE_STATE_NEGATION_CUES):
            return NEGATED
    if any(cue in sentence for cue in _HISTORICAL_CUES):
        return HISTORICAL
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
        declared_status = _norm(payload.get("assertion_status")).upper()
        if declared_status in {"NEGATED", "ABSENT"} and status == ASSERTED:
            # The model cannot create a positive fact by contradicting its own
            # negative annotation. Keep the mention auditable and fail closed.
            status = NEGATED
        elif declared_status == HISTORICAL and status == ASSERTED:
            status = HISTORICAL
        if role in INTERVENTION_ROLES and role == ROLE_UNKNOWN and status == HISTORICAL:
            role = PREVIOUS_INTERVENTION

        rejection = None
        accepted = True
        if located is None and quote:
            accepted, rejection = False, MENTION_NOT_IN_TEXT
        elif entity_type in {"TRIAL", "COMPANION_DIAGNOSTIC"} and str(raw).casefold() not in str(quote).casefold():
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

    diseases = case_context.get("diseases") or []
    if not diseases and case_context.get("disease"):
        diseases = [case_context.get("disease")]
    for disease in diseases:
        raw = disease.get("value") or disease.get("raw_value")
        if raw:
            entity_type = "SYMPTOM" if (
                looks_like_symptom(raw) and not mentions_oncology(raw)
            ) else "DISEASE"
            payload = dict(disease)
            payload.setdefault("raw_value", raw)
            payload.setdefault("normalized_value", disease.get("normalized_value") or _norm(raw))
            payload.setdefault("source_spans", disease.get("source_spans") or [])
            _mention(raw, payload.get("normalized_value"), entity_type,
                     disease.get("clinical_role") or CONTEXTUAL_MENTION, payload, "disease")

    for biomarker in case_context.get("biomarkers") or []:
        pair = None
        if biomarker.get("gene") and biomarker.get("alteration"):
            pair = ground_pair(clinical_text, biomarker["gene"], biomarker["alteration"])
            biomarker["pair_source_span"] = (
                {key: pair[key] for key in ("quote", "start_offset", "end_offset")}
                if pair else None
            )
            biomarker["pair_grounded"] = pair is not None
        first_mention = len(out)
        if biomarker.get("gene"):
            gene_payload = dict(biomarker)
            gene_payload["raw_value"] = biomarker["gene"]
            gene_payload["normalized_value"] = _norm(biomarker["gene"])
            gene_payload["source_spans"] = biomarker.get("gene_source_spans") or biomarker.get("source_spans") or []
            _mention(biomarker["gene"], gene_payload["normalized_value"], "GENE",
                     CONTEXTUAL_MENTION, gene_payload, "biomarker")
        if biomarker.get("alteration"):
            alteration_payload = dict(biomarker)
            alteration_payload["raw_value"] = biomarker["alteration"]
            alteration_payload["normalized_value"] = _norm(biomarker["alteration"])
            alteration_payload["source_spans"] = biomarker.get("alteration_source_spans") or biomarker.get("source_spans") or []
            _mention(biomarker["alteration"], alteration_payload["normalized_value"], "ALTERATION",
                     CONTEXTUAL_MENTION, alteration_payload, "alteration")
        if biomarker.get("gene") and biomarker.get("alteration"):
            for mention in out[first_mention:]:
                if pair is None and mention.entity_type == "ALTERATION":
                    mention.accepted_for_casecontext = False
                    mention.rejection_reason = "GENE_VARIANT_PAIR_NOT_GROUNDED"
                elif pair is not None and pair["negated"]:
                    mention.assertion_status = NEGATED
                    mention.accepted_for_casecontext = False
                    mention.rejection_reason = MENTION_NEGATED

    # A negated alteration also suppresses the paired gene as a positive
    # retrieval anchor (e.g. ``KRAS wild type``). The gene mention remains in
    # the audit trail with the same source quote and an explicit rejection.
    for alteration_mention in [m for m in out if m.entity_type == "ALTERATION" and m.assertion_status == NEGATED]:
        quote = (alteration_mention.source_span or {}).get("quote") if alteration_mention.source_span else None
        for gene_mention in out:
            if gene_mention.entity_type != "GENE" or not gene_mention.accepted_for_casecontext:
                continue
            gene_quote = (gene_mention.source_span or {}).get("quote") if gene_mention.source_span else None
            if quote and gene_quote == quote:
                gene_mention.assertion_status = NEGATED
                gene_mention.accepted_for_casecontext = False
                gene_mention.rejection_reason = MENTION_NEGATED

    canonical_interventions = case_context.get("interventions") or []
    if canonical_interventions:
        for intervention in canonical_interventions:
            raw = intervention.get("name") or intervention.get("raw_value")
            if not raw:
                continue
            role = intervention.get("role") or ROLE_UNKNOWN
            slot = "target_intervention" if role == "TARGET" else (
                "previous_intervention" if role == "PREVIOUS" else "intervention"
            )
            semantic_role = TARGET_INTERVENTION if role == "TARGET" else (
                PREVIOUS_INTERVENTION if role == "PREVIOUS" else role
            )
            payload = dict(intervention)
            payload["raw_value"] = raw
            payload["normalized_value"] = intervention.get("normalized_value") or _norm(raw)
            payload.setdefault("source_spans", [])
            _mention(raw, payload["normalized_value"], "INTERVENTION",
                     semantic_role, payload, slot)
    else:
        for previous in case_context.get("previous_interventions") or []:
            if previous.get("raw_value"):
                _mention(previous["raw_value"], previous.get("normalized_value"), "INTERVENTION",
                         PREVIOUS_INTERVENTION, previous, "previous_intervention")

        target = case_context.get("target_intervention") or {}
        if target.get("raw_value"):
            _mention(target["raw_value"], target.get("normalized_value"), "INTERVENTION",
                     TARGET_INTERVENTION, target, "target_intervention")

    for key, entity_type, primary_fields, fields in (
        ("trial_mentions", "TRIAL", ("nct_id", "trial_name"), ("nct_id", "trial_name", "phase", "status")),
        ("companion_diagnostic_mentions", "COMPANION_DIAGNOSTIC", ("name", "identifier"),
         ("name", "identifier", "associated_gene", "associated_drug", "platform", "specimen")),
    ):
        for item in case_context.get(key) or []:
            if not isinstance(item, dict):
                item = {"name": str(item)}
            primary = next((field for field in primary_fields if item.get(field)), None)
            if primary is None:
                primary = next((field for field in fields if item.get(field)), None)
            raw = str(item.get(primary) or "") if primary else ""
            quote = str(item.get(f"{primary}_quote") or raw) if primary else ""
            payload = {"source_spans": [{"quote": quote}],
                       "assertion_status": item.get("assertion_status")}
            _mention(raw, raw, entity_type, CONTEXTUAL_MENTION, payload,
                     "trial_mention" if entity_type == "TRIAL" else "companion_diagnostic_mention")
            mention = out[-1]
            if not primary:
                mention.accepted_for_casecontext = False
                mention.rejection_reason = MENTION_NOT_IN_TEXT
            for field in fields:
                field_value = item.get(field)
                if field_value in (None, ""):
                    continue
                field_quote = str(item.get(f"{field}_quote") or field_value)
                if (field_quote not in clinical_text
                        or str(field_value).casefold() not in field_quote.casefold()):
                    mention.accepted_for_casecontext = False
                    mention.rejection_reason = mention.rejection_reason or MENTION_FIELD_NOT_IN_TEXT

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
