"""Pre-Retrieval Eligibility Gate.

Stage canonico deterministico fra la verifica del CaseContext e il retrieval::

    CaseContext Parser
      → Match Verifier (testuale)
      → Semantic Verifier (tipo · ruolo · asserzione)
      → Contradiction Detector
      → **Pre-Retrieval Eligibility Gate**
      → KG Retrieval

**Il gate decide, il parser no.** Nessun LLM è coinvolto: la decisione deriva
dalle menzioni verificate, dagli span di controllo e dalle contraddizioni, tutti
prodotti da codice deterministico.

Il problema che risolve: nel benchmark RQ4 un CaseContext completamente vuoto
superava ``essential_fields_pass`` — perché ``MISSING_IN_TEXT`` non è
``MISMATCH`` — ed entrava nel retrieval. Esistevano due soli esiti di routing e
la categoria dell'input non li determinava.

Gli enum sono definiti **qui, nel backend**. Il frontend non ricostruisce e non
calcola lo stato.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..casecontext.contradictions import Contradiction, has_blocking
from ..casecontext.control_instructions import (
    is_predominantly_control, residual_clinical_text,
)
from ..casecontext.mentions import EntityMention, looks_like_symptom, mentions_oncology

GATE_POLICY_VERSION = "pre-retrieval-eligibility-gate/1.0"
GATE_STAGE_ID = "stage_3b_pre_retrieval_eligibility_gate"

# ---------------------------------------------------------------- stati

ELIGIBLE_FOR_RETRIEVAL = "ELIGIBLE_FOR_RETRIEVAL"
INVALID_INPUT = "INVALID_INPUT"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
NON_ACTIONABLE_MEDICAL_INPUT = "NON_ACTIONABLE_MEDICAL_INPUT"
INSUFFICIENT_ONCOLOGY_CONTEXT = "INSUFFICIENT_ONCOLOGY_CONTEXT"
MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
CONTRADICTORY_CASE_CONTEXT = "CONTRADICTORY_CASE_CONTEXT"
ADVERSARIAL_OR_CONTROL_INPUT = "ADVERSARIAL_OR_CONTROL_INPUT"
AMBIGUOUS_CASE_CONTEXT = "AMBIGUOUS_CASE_CONTEXT"

ELIGIBILITY_STATES = (
    ELIGIBLE_FOR_RETRIEVAL, INVALID_INPUT, OUT_OF_SCOPE, NON_ACTIONABLE_MEDICAL_INPUT,
    INSUFFICIENT_ONCOLOGY_CONTEXT, MISSING_REQUIRED_FIELDS, CONTRADICTORY_CASE_CONTEXT,
    ADVERSARIAL_OR_CONTROL_INPUT, AMBIGUOUS_CASE_CONTEXT,
)

#: Stage vietati quando il caso non è eleggibile.
DOWNSTREAM_STAGES = (
    "stage_4_retrieval_plan", "stage_5_kg_retrieval", "stage_6_document_resolution",
    "stage_7_source_units", "stage_8_paper_selection", "stage_9_enrichment",
)

#: Marcatori di una domanda clinica molecolare. Il gate non li usa da soli: sono
#: uno dei segnali di scope, insieme agli ancoraggi oncologici verificati.
_CLINICAL_QUESTION_CUES = (
    "therapy", "treatment", "therapeutic", "drug", "regimen", "appropriate",
    "indicated", "options", "evaluate", "consider", "eligible",
    "terapia", "trattamento", "farmaco", "opzioni", "indicata",
)


@dataclass
class EligibilityDecision:
    eligibility_status: str
    eligible: bool
    reason_codes: list[str] = field(default_factory=list)
    verified_fields: dict[str, Any] = field(default_factory=dict)
    missing_required_fields: list[str] = field(default_factory=list)
    rejected_mentions: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    scope_evidence: list[str] = field(default_factory=list)
    forbidden_downstream_stages: list[str] = field(default_factory=list)
    warning_codes: list[str] = field(default_factory=list)
    policy_version: str = GATE_POLICY_VERSION
    producer: str = "DETERMINISTIC"
    decided_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _accepted(mentions: list[EntityMention], slot: str) -> list[EntityMention]:
    return [m for m in mentions if m.slot == slot and m.accepted_for_casecontext]


def _has_clinical_question(text: str, case_context: dict[str, Any]) -> bool:
    haystack = f"{text} {case_context.get('clinical_question') or ''}".lower()
    return any(cue in haystack for cue in _CLINICAL_QUESTION_CUES)


def evaluate(
    clinical_text: str,
    case_context: dict[str, Any] | None,
    mentions: list[EntityMention],
    control_spans: list[dict[str, Any]],
    contradictions: list[Contradiction],
    transport_ok: bool = True,
) -> EligibilityDecision:
    """Decisione di eleggibilità. Ordine delle regole significativo."""
    text = clinical_text or ""
    case_context = case_context or {}
    rejected = [m.to_dict() for m in mentions if not m.accepted_for_casecontext]
    contradiction_dicts = [c.to_dict() for c in contradictions]
    now = datetime.now(timezone.utc).isoformat()

    def decide(status: str, reasons: list[str], *, eligible: bool = False,
               missing: list[str] | None = None, scope: list[str] | None = None,
               warnings: list[str] | None = None) -> EligibilityDecision:
        return EligibilityDecision(
            eligibility_status=status, eligible=eligible, reason_codes=reasons,
            verified_fields=_verified(mentions) if eligible else _verified(mentions),
            missing_required_fields=missing or [],
            rejected_mentions=rejected, contradictions=contradiction_dicts,
            scope_evidence=scope or [],
            forbidden_downstream_stages=[] if eligible else list(DOWNSTREAM_STAGES),
            warning_codes=warnings or [], decided_at=now,
        )

    # A — input vuoto
    if not text.strip():
        return decide(INVALID_INPUT, ["EMPTY_OR_WHITESPACE_INPUT"])

    # Trasporto fallito: nessun CaseContext da valutare.
    if not transport_ok or not case_context:
        return decide(INVALID_INPUT, ["NO_VALID_CASECONTEXT_PRODUCED"])

    # F — input prevalentemente direttivo
    if control_spans and is_predominantly_control(text, control_spans):
        residual = residual_clinical_text(text, control_spans)
        if not _has_oncology_anchor(mentions) and not mentions_oncology(residual):
            return decide(
                ADVERSARIAL_OR_CONTROL_INPUT,
                ["INPUT_IS_PREDOMINANTLY_A_CONTROL_INSTRUCTION"],
                scope=[f"control_span:{s['reason_code']}" for s in control_spans],
            )

    # E — contraddizione bloccante
    if has_blocking(contradictions):
        return decide(
            CONTRADICTORY_CASE_CONTEXT,
            ["BLOCKING_CONTRADICTION"] + sorted({c.reason_code for c in contradictions}),
        )

    disease = _accepted(mentions, "disease")
    genes = _accepted(mentions, "biomarker")
    alterations = _accepted(mentions, "alteration")
    target = _accepted(mentions, "target_intervention")
    symptoms = [m for m in mentions if m.entity_type == "SYMPTOM"]
    # L'evidenza di sintomo si cerca anche nel **testo**, non solo fra le
    # menzioni: il parser può aver messo il sintomo in uno slot sbagliato — è
    # esattamente il caso che il verifier semantico ha appena rifiutato — e in
    # quel caso non esiste una menzione di tipo SYMPTOM da contare. Senza questo
    # controllo «Mi fa male la gamba» finirebbe in OUT_OF_SCOPE invece che fra
    # gli input medici non azionabili, perdendo la distinzione che il protocollo
    # richiede.
    text_has_symptom = looks_like_symptom(text) and not mentions_oncology(text)
    anchor = _has_oncology_anchor(mentions)
    clinical_question = _has_clinical_question(text, case_context)

    warnings: list[str] = []
    if control_spans:
        warnings.append("CONTROL_INSTRUCTION_MENTIONS_REMOVED")

    # D — nessun campo clinico accettato
    if not (disease or genes or alterations or target):
        # C — sintomo presente ma nessun ancoraggio oncologico
        if symptoms or text_has_symptom:
            return decide(
                NON_ACTIONABLE_MEDICAL_INPUT,
                ["SYMPTOM_WITHOUT_ONCOLOGY_ANCHOR"],
                scope=[f"symptom:{m.raw_text}" for m in symptoms] or ["symptom:in_text"],
                warnings=warnings,
            )
        # B — nessun ancoraggio e nessuna domanda clinica molecolare
        if not anchor:
            return decide(
                OUT_OF_SCOPE,
                ["NO_ONCOLOGY_ANCHOR", "NO_ACCEPTED_CLINICAL_FIELD"],
                warnings=warnings,
            )
        return decide(
            INSUFFICIENT_ONCOLOGY_CONTEXT,
            ["NO_ACCEPTED_CLINICAL_FIELD"], warnings=warnings,
        )

    # Ancoraggio oncologico necessario anche quando qualche campo è accettato.
    if not anchor:
        reasons = ["NO_VERIFIED_ONCOLOGY_ANCHOR"]
        if symptoms or text_has_symptom:
            return decide(NON_ACTIONABLE_MEDICAL_INPUT,
                          ["SYMPTOM_WITHOUT_ONCOLOGY_ANCHOR"] + reasons,
                          scope=[f"symptom:{m.raw_text}" for m in symptoms] or ["symptom:in_text"],
                          warnings=warnings)
        if not clinical_question:
            return decide(OUT_OF_SCOPE, reasons + ["NO_CLINICAL_QUESTION"], warnings=warnings)
        return decide(INSUFFICIENT_ONCOLOGY_CONTEXT, reasons, warnings=warnings)

    # §11 — requisiti per query intent
    intent = case_context.get("query_intent")
    missing: list[str] = []
    if not disease:
        missing.append("disease")
    if not (genes or alterations):
        missing.append("biomarker_or_alteration")
    if intent == "THERAPY_EVALUATION" and not target:
        missing.append("target_intervention")

    if missing:
        return decide(MISSING_REQUIRED_FIELDS, ["MINIMUM_FIELDS_NOT_SATISFIED"],
                      missing=missing, warnings=warnings)

    if intent not in {"THERAPY_EVALUATION", "THERAPY_DISCOVERY"}:
        return decide(AMBIGUOUS_CASE_CONTEXT, ["QUERY_INTENT_NOT_DETERMINED"], warnings=warnings)

    reasons = ["ONCOLOGY_ANCHOR_VERIFIED", "MINIMUM_FIELDS_SATISFIED"]
    reasons.append("INTERVENTION_REQUIRED" if intent == "THERAPY_EVALUATION"
                   else "INTERVENTION_NOT_APPLICABLE")
    if any(m.warnings for m in mentions if m.accepted_for_casecontext):
        warnings.append("UNCERTAIN_MENTION_ACCEPTED")
    if contradictions:
        warnings.append("NON_BLOCKING_CONTRADICTION_PRESENT")

    return decide(ELIGIBLE_FOR_RETRIEVAL, reasons, eligible=True,
                  scope=[f"oncology_anchor:{m.raw_text}" for m in disease] or
                        [f"oncology_anchor:{m.raw_text}" for m in genes],
                  warnings=warnings)


def _has_oncology_anchor(mentions: list[EntityMention]) -> bool:
    """Un ancoraggio oncologico verificato: neoplasia, gene o alterazione accettati.

    Un sintomo non è un ancoraggio, e una menzione rifiutata non conta.
    """
    for mention in mentions:
        if not mention.accepted_for_casecontext:
            continue
        if mention.entity_type == "DISEASE" and mentions_oncology(mention.raw_text):
            return True
        if mention.entity_type in {"GENE", "ALTERATION", "BIOMARKER"}:
            return True
    return False


def _verified(mentions: list[EntityMention]) -> dict[str, Any]:
    from ..casecontext.semantic_verifier import verified_fields
    return verified_fields(mentions)


def intervention_check_for(intent: str | None) -> str:
    """Per discovery l'intervento è ``NOT_APPLICABLE``, non ``PASS_ALL``.

    Trattare un intervento mancante come wildcard farebbe corrispondere ogni
    candidate, che è l'opposto di «nessun filtro richiesto».
    """
    return "REQUIRED" if intent == "THERAPY_EVALUATION" else "NOT_APPLICABLE"
