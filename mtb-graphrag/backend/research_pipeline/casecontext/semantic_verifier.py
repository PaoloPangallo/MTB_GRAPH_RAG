"""CaseContextSemanticVerifier — quattro livelli di verifica distinti.

Il Match Verifier esistente (``match_verifier.py``) verifica la **presenza
testuale**: che la citazione compaia letteralmente nel testo. È necessario ma non
sufficiente, come il benchmark RQ4 ha mostrato: «febbre» *è* letteralmente nel
testo di «Ho la febbre», e finiva nello slot ``disease``.

Questo modulo aggiunge i livelli mancanti, **senza indebolire** il verifier
testuale, che resta il gate di letteralità:

===  ==========================  ==========================================
 A   TEXTUAL MATCH               il valore compare davvero nel testo
 B   TYPE COMPATIBILITY          la menzione è del tipo richiesto dallo slot
 C   SEMANTIC ROLE COMPATIBILITY la menzione svolge il ruolo richiesto
 D   ASSERTION COMPATIBILITY     la menzione è affermata, non negata o incerta
===  ==========================  ==========================================

Una stringa presente nel testo **non è automaticamente valida per qualunque
slot**.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .mentions import (
    ASSERTED, CONTROL_INSTRUCTION_MENTION, EntityMention, HYPOTHETICAL,
    MENTION_INSIDE_CONTROL_INSTRUCTION, MENTION_NEGATED,
    MENTION_ROLE_INCOMPATIBLE_WITH_SLOT, MENTION_TYPE_INCOMPATIBLE_WITH_SLOT,
    MENTION_UNCERTAIN, NEGATED, PREVIOUS_INTERVENTION, TARGET_INTERVENTION,
    UNCERTAIN, mentions_oncology,
)

SEMANTIC_VERIFIER_VERSION = "casecontext-semantic-verifier/1.0"

# Esiti
TEXT_MATCH = "TEXT_MATCH"
TEXT_MISMATCH = "TEXT_MISMATCH"
TYPE_MISMATCH = "TYPE_MISMATCH"
ROLE_MISMATCH = "ROLE_MISMATCH"
NEGATED_MENTION = "NEGATED_MENTION"
UNCERTAIN_MENTION = "UNCERTAIN_MENTION"
CONTROL_MENTION = "CONTROL_INSTRUCTION_MENTION"
MISSING_IN_TEXT = "MISSING_IN_TEXT"
ACCEPTED = "ACCEPTED"

#: Tipi ammessi per ciascuno slot canonico. `SYMPTOM` **non** è ammesso in
#: `disease`: è esattamente la contaminazione misurata nel benchmark RQ4.
SLOT_TYPES: dict[str, tuple[str, ...]] = {
    "disease": ("DISEASE",),
    "biomarker": ("GENE", "BIOMARKER"),
    "alteration": ("ALTERATION",),
    "previous_intervention": ("INTERVENTION",),
    "target_intervention": ("INTERVENTION",),
}

#: Ruoli ammessi per ciascuno slot.
SLOT_ROLES: dict[str, tuple[str, ...]] = {
    "target_intervention": (TARGET_INTERVENTION,),
    "previous_intervention": (PREVIOUS_INTERVENTION,),
}


@dataclass
class SemanticVerificationRecord:
    slot: str
    raw_text: str
    entity_type: str
    semantic_role: str
    assertion_status: str
    status: str
    reason_code: str
    accepted: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_mention(mention: EntityMention) -> SemanticVerificationRecord:
    """Verifica una singola menzione contro il proprio slot."""
    slot = mention.slot or ""

    def record(status: str, reason: str, accepted: bool) -> SemanticVerificationRecord:
        return SemanticVerificationRecord(
            slot=slot, raw_text=mention.raw_text, entity_type=mention.entity_type,
            semantic_role=mention.semantic_role, assertion_status=mention.assertion_status,
            status=status, reason_code=reason, accepted=accepted,
        )

    # A — letteralità (già decisa dalla costruzione della menzione)
    if mention.rejection_reason == "MENTION_NOT_IN_TEXT":
        return record(TEXT_MISMATCH, "QUOTE_NOT_IN_TEXT", False)

    # Contaminazione da istruzione di controllo: precede ogni altra valutazione.
    if (mention.rejection_reason == MENTION_INSIDE_CONTROL_INSTRUCTION
            or mention.semantic_role == CONTROL_INSTRUCTION_MENTION):
        return record(CONTROL_MENTION, MENTION_INSIDE_CONTROL_INSTRUCTION, False)

    # B — compatibilità di tipo
    allowed_types = SLOT_TYPES.get(slot)
    if allowed_types and mention.entity_type not in allowed_types:
        reason = MENTION_TYPE_INCOMPATIBLE_WITH_SLOT
        if slot == "disease" and mention.entity_type == "SYMPTOM":
            reason = "SYMPTOM_IS_NOT_A_DISEASE"
        return record(TYPE_MISMATCH, reason, False)

    # Uno slot `disease` deve contenere una neoplasia verificabile nel testo.
    if slot == "disease" and not mentions_oncology(mention.raw_text) \
            and not mentions_oncology(mention.normalized_value):
        return record(TYPE_MISMATCH, "DISEASE_WITHOUT_ONCOLOGY_ANCHOR", False)

    # C — compatibilità di ruolo
    allowed_roles = SLOT_ROLES.get(slot)
    if allowed_roles and mention.semantic_role not in allowed_roles:
        return record(ROLE_MISMATCH, MENTION_ROLE_INCOMPATIBLE_WITH_SLOT, False)

    # D — compatibilità di asserzione
    if mention.assertion_status == NEGATED:
        return record(NEGATED_MENTION, MENTION_NEGATED, False)
    if mention.assertion_status in {UNCERTAIN, HYPOTHETICAL}:
        # Non rifiutata: ammessa con warning. Un'alterazione incerta però non
        # produrrà FULL_MATCH nel matching composto.
        return record(UNCERTAIN_MENTION, MENTION_UNCERTAIN, True)
    if mention.assertion_status != ASSERTED:
        return record(UNCERTAIN_MENTION, "ASSERTION_STATUS_UNKNOWN", True)

    return record(ACCEPTED, "TYPE_ROLE_AND_ASSERTION_COMPATIBLE", True)


def verify(mentions: list[EntityMention]) -> tuple[list[EntityMention], list[dict[str, Any]]]:
    """Applica la verifica semantica, aggiornando l'accettazione delle menzioni.

    Restituisce ``(menzioni aggiornate, record di verifica)``. Le menzioni
    rifiutate **non** vengono rimosse: restano con il proprio motivo.
    """
    records: list[dict[str, Any]] = []
    updated: list[EntityMention] = []
    for mention in mentions:
        result = verify_mention(mention)
        records.append(result.to_dict())
        if not result.accepted and mention.accepted_for_casecontext:
            mention.accepted_for_casecontext = False
            mention.rejection_reason = mention.rejection_reason or result.reason_code
        if result.status == UNCERTAIN_MENTION and mention.accepted_for_casecontext:
            mention.warnings.append(result.reason_code)
        updated.append(mention)
    return updated, records


def verified_fields(mentions: list[EntityMention]) -> dict[str, Any]:
    """Campi canonici ricostruiti **solo** dalle menzioni accettate."""
    def _accepted(slot: str) -> list[EntityMention]:
        return [m for m in mentions if m.slot == slot and m.accepted_for_casecontext]

    disease = _accepted("disease")
    return {
        "disease": disease[0].normalized_value or disease[0].raw_text if disease else None,
        "genes": [m.raw_text for m in _accepted("biomarker")],
        "alterations": [m.raw_text for m in _accepted("alteration")],
        "previous_interventions": [m.raw_text for m in _accepted("previous_intervention")],
        "target_intervention": next(
            (m.normalized_value or m.raw_text for m in _accepted("target_intervention")), None),
    }
