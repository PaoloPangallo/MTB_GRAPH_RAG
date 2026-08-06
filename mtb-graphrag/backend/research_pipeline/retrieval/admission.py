"""``CandidateRuntimeAdmission`` — come il runtime tratta una candidate v3.

Il repository v3 rende visibili 1 034 candidate che v2 nascondeva
(873 ``SOURCE_DOES_NOT_SUPPORT`` + 161 ``SOURCE_NEUTRAL``). **Renderle visibili
non è averle gestite**: questo modulo è il punto in cui il runtime decide che
farne.

Tre decisioni indipendenti, che non vanno collassate in un booleano:

* **polarità della fonte** — la candidate può entrare nel percorso positivo?
* **alterazione** — l'espressione corrisponde al caso? ``A AND B`` richiede
  entrambi;
* **intervento** — un regime irrisolto non è eleggibile al match esatto.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from gca_v3.matching import (
    EXPRESSION_UNAVAILABLE, EXPRESSION_UNSUPPORTED, FULL_MATCH,
    INSUFFICIENT_CASE_INFORMATION, NO_MATCH, PARTIAL_MATCH,
    evaluate_alteration_expression,
)

ADMISSION_POLICY_VERSION = "candidate-runtime-admission/1.0"

# ------------------------------------------------------------ admission status
ADMITTED_NORMAL_GROUNDING = "ADMITTED_NORMAL_GROUNDING"
ADMITTED_GROUNDING_WITH_SOURCE_POLARITY_UNKNOWN = "ADMITTED_GROUNDING_WITH_SOURCE_POLARITY_UNKNOWN"
ADMITTED_NEGATIVE_AUDIT_BRANCH = "ADMITTED_NEGATIVE_AUDIT_BRANCH"
ADMITTED_NEUTRAL_AUDIT_BRANCH = "ADMITTED_NEUTRAL_AUDIT_BRANCH"
ADMITTED_CONTRADICTION_AUDIT_BRANCH = "ADMITTED_CONTRADICTION_AUDIT_BRANCH"
REJECTED_SOURCE_DOES_NOT_SUPPORT_POSITIVE_USE = "REJECTED_SOURCE_DOES_NOT_SUPPORT_POSITIVE_USE"
REJECTED_ALTERATION_MISMATCH = "REJECTED_ALTERATION_MISMATCH"
REJECTED_ALTERATION_INSUFFICIENT = "REJECTED_ALTERATION_INSUFFICIENT"
REJECTED_INTERVENTION_MISMATCH = "REJECTED_INTERVENTION_MISMATCH"
REJECTED_UNRESOLVED_REGIMEN_FOR_EXACT_MATCH = "REJECTED_UNRESOLVED_REGIMEN_FOR_EXACT_MATCH"
AUDIT_ONLY_UNRESOLVED_REGIMEN = "AUDIT_ONLY_UNRESOLVED_REGIMEN"
AUDIT_ONLY_UNSUPPORTED_EXPRESSION = "AUDIT_ONLY_UNSUPPORTED_EXPRESSION"

# ---------------------------------------------------------------------- branch
BRANCH_POSITIVE = "POSITIVE_OR_NORMAL_GROUNDING"
BRANCH_NEGATIVE = "NEGATIVE_DOES_NOT_SUPPORT_AUDIT"
BRANCH_NEUTRAL = "NEUTRAL_AUDIT"
BRANCH_POLARITY_UNKNOWN = "SOURCE_POLARITY_UNKNOWN"
BRANCH_UNRESOLVED_REGIMEN = "UNRESOLVED_REGIMEN_LIMITATIONS"
BRANCH_PARTIAL_ALTERATION = "COMPOUND_ALTERATION_PARTIAL_OR_INSUFFICIENT_MATCH"

#: Stati di ammissione che **non** possono entrare nelle evidenze positive.
AUDIT_ONLY_STATUSES = frozenset({
    ADMITTED_NEGATIVE_AUDIT_BRANCH, ADMITTED_NEUTRAL_AUDIT_BRANCH,
    ADMITTED_CONTRADICTION_AUDIT_BRANCH, AUDIT_ONLY_UNRESOLVED_REGIMEN,
    AUDIT_ONLY_UNSUPPORTED_EXPRESSION,
})

REJECTED_STATUSES = frozenset({
    REJECTED_SOURCE_DOES_NOT_SUPPORT_POSITIVE_USE, REJECTED_ALTERATION_MISMATCH,
    REJECTED_ALTERATION_INSUFFICIENT, REJECTED_INTERVENTION_MISMATCH,
    REJECTED_UNRESOLVED_REGIMEN_FOR_EXACT_MATCH,
})


@dataclass
class CandidateRuntimeAdmission:
    candidate_id: str
    admission_status: str
    source_alignment_status: str
    alteration_match_status: str
    intervention_match_status: str
    direction_status: str
    reason_codes: list[str] = field(default_factory=list)
    allowed_branches: list[str] = field(default_factory=list)
    warning_codes: list[str] = field(default_factory=list)
    source_stage: str = "stage_5_kg_retrieval"
    policy_version: str = ADMISSION_POLICY_VERSION
    producer: str = "DETERMINISTIC"

    @property
    def is_positive(self) -> bool:
        return BRANCH_POSITIVE in self.allowed_branches

    @property
    def is_audit_only(self) -> bool:
        return self.admission_status in AUDIT_ONLY_STATUSES

    @property
    def is_rejected(self) -> bool:
        return self.admission_status in REJECTED_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "is_positive": self.is_positive,
                "is_audit_only": self.is_audit_only, "is_rejected": self.is_rejected}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _case_alterations(verified_fields: dict[str, Any]) -> dict[str, Any]:
    """CaseContext ridotto alla forma che ``evaluate_alteration_expression`` attende.

    Usa **solo** i campi verificati dal gate: menzioni negate, incerte-rifiutate
    o contenute in istruzioni di controllo non sono qui, quindi non possono
    contribuire a un match.
    """
    genes = verified_fields.get("genes") or []
    alterations = verified_fields.get("alterations") or []
    biomarkers = []
    for index, gene in enumerate(genes):
        alteration = alterations[index] if index < len(alterations) else None
        biomarkers.append({"gene": gene, "alteration": alteration})
    for alteration in alterations[len(genes):]:
        biomarkers.append({"gene": None, "alteration": alteration})
    return {"biomarkers": biomarkers}


def evaluate_intervention(
    candidate: dict[str, Any],
    target_intervention: str | None,
    query_intent: str | None,
) -> tuple[str, list[str]]:
    """Esito del confronto sull'intervento e motivi."""
    structure = candidate.get("intervention_structure")
    components = candidate.get("intervention_components") or []

    # La struttura è valutata **prima** dell'intento: un regime irrisolto resta
    # irrisolto anche in discovery, dove va mostrato come unità e non come una
    # lista di terapie individualmente supportate. Cortocircuitare su
    # `NOT_APPLICABLE` lo avrebbe fatto scivolare nel grounding normale.
    if structure == "MULTI_COMPONENT_UNRESOLVED":
        # La presenza di tutti i nomi non recupera una semantica assente dalla
        # sorgente: non è noto se vadano somministrati insieme o in alternativa.
        return "UNRESOLVED_REGIMEN", ["REGIMEN_SEMANTICS_UNAVAILABLE_IN_EXPORT"]

    if query_intent != "THERAPY_EVALUATION":
        # Per discovery l'intervento non è un filtro: NOT_APPLICABLE, non PASS_ALL.
        return "NOT_APPLICABLE", ["INTERVENTION_NOT_APPLICABLE_FOR_DISCOVERY"]

    if not target_intervention:
        return "NO_TARGET", ["NO_VERIFIED_TARGET_INTERVENTION"]

    target = _norm(target_intervention)
    names = [_norm(c.get("name")) for c in components if c.get("name")]
    if any(target in name or name in target for name in names if name):
        return "MATCH", ["INTERVENTION_COMPATIBLE"]
    return "MISMATCH", ["TARGET_INTERVENTION_NOT_COMPATIBLE"]


def evaluate_candidate(
    candidate: dict[str, Any],
    verified_fields: dict[str, Any],
    query_intent: str | None,
) -> CandidateRuntimeAdmission:
    """Decisione di ammissione runtime per una candidate v3."""
    candidate_id = candidate.get("candidate_id", "")
    alignment = candidate.get("source_alignment_status", "SOURCE_ALIGNMENT_NOT_AVAILABLE")
    graph_direction = candidate.get("graph_direction", "UNKNOWN")
    reasons: list[str] = []
    warnings: list[str] = []

    # --- alterazione -------------------------------------------------------
    alteration_result = evaluate_alteration_expression(
        _case_alterations(verified_fields),
        candidate.get("alteration_expression_ast"),
        candidate.get("alteration_parse_status"),
    )
    alteration_status = alteration_result["result"]

    # --- intervento --------------------------------------------------------
    intervention_status, intervention_reasons = evaluate_intervention(
        candidate, verified_fields.get("target_intervention"), query_intent)
    reasons.extend(intervention_reasons)

    def admission(status: str, branches: list[str]) -> CandidateRuntimeAdmission:
        return CandidateRuntimeAdmission(
            candidate_id=candidate_id, admission_status=status,
            source_alignment_status=alignment, alteration_match_status=alteration_status,
            intervention_match_status=intervention_status,
            direction_status=graph_direction, reason_codes=reasons,
            allowed_branches=branches, warning_codes=warnings,
        )

    # --- esclusioni sull'alterazione ---------------------------------------
    if alteration_status == NO_MATCH:
        reasons.append("ALTERATION_EXPRESSION_NOT_SATISFIED")
        return admission(REJECTED_ALTERATION_MISMATCH, [])
    if alteration_status == PARTIAL_MATCH:
        # Un match su A non equivale a "A AND B".
        reasons.append("ALTERATION_EXPRESSION_ONLY_PARTIALLY_SATISFIED")
        return admission(REJECTED_ALTERATION_INSUFFICIENT, [BRANCH_PARTIAL_ALTERATION])
    if alteration_status == INSUFFICIENT_CASE_INFORMATION:
        reasons.append("CASE_LACKS_ALTERATION_INFORMATION")
        warnings.append("ALTERATION_MATCH_NOT_DETERMINABLE")
        return admission(REJECTED_ALTERATION_INSUFFICIENT, [BRANCH_PARTIAL_ALTERATION])
    if alteration_status == EXPRESSION_UNSUPPORTED:
        reasons.append("ALTERATION_EXPRESSION_UNSUPPORTED")
        return admission(AUDIT_ONLY_UNSUPPORTED_EXPRESSION, [BRANCH_PARTIAL_ALTERATION])
    if alteration_status == EXPRESSION_UNAVAILABLE:
        warnings.append("ALTERATION_EXPRESSION_UNAVAILABLE")

    # --- esclusioni sull'intervento ----------------------------------------
    if intervention_status == "MISMATCH":
        return admission(REJECTED_INTERVENTION_MISMATCH, [])
    if intervention_status == "NO_TARGET" and query_intent == "THERAPY_EVALUATION":
        return admission(REJECTED_INTERVENTION_MISMATCH, [])
    if intervention_status == "UNRESOLVED_REGIMEN":
        warnings.append("REGIMEN_SEMANTICS_UNAVAILABLE_IN_EXPORT")
        if query_intent == "THERAPY_EVALUATION":
            # Nessun exact match possibile da un'unità irrisolta.
            return admission(REJECTED_UNRESOLVED_REGIMEN_FOR_EXACT_MATCH,
                             [BRANCH_UNRESOLVED_REGIMEN])
        # Discovery: mostrabile solo come unità irrisolta, mai come lista di
        # terapie individualmente supportate.
        return admission(AUDIT_ONLY_UNRESOLVED_REGIMEN, [BRANCH_UNRESOLVED_REGIMEN])

    # --- polarità della fonte ----------------------------------------------
    if alignment == "SOURCE_DOES_NOT_SUPPORT":
        reasons.append("SOURCE_DOES_NOT_SUPPORT_THE_ASSERTION")
        warnings.append("GRAPH_DIRECTION_PRESERVED_NOT_INVERTED")
        return admission(ADMITTED_NEGATIVE_AUDIT_BRANCH, [BRANCH_NEGATIVE])
    if alignment == "SOURCE_CONTRADICTS":
        reasons.append("SOURCE_CONTRADICTS_THE_ASSERTION")
        return admission(ADMITTED_CONTRADICTION_AUDIT_BRANCH, [BRANCH_NEGATIVE])
    if alignment == "SOURCE_NEUTRAL":
        reasons.append("SOURCE_REPORTS_NO_DIFFERENCE")
        return admission(ADMITTED_NEUTRAL_AUDIT_BRANCH, [BRANCH_NEUTRAL])
    if alignment == "SOURCE_ALIGNMENT_UNCLEAR":
        warnings.append("SOURCE_ALIGNMENT_UNCLEAR")
        return admission(ADMITTED_GROUNDING_WITH_SOURCE_POLARITY_UNKNOWN,
                         [BRANCH_POSITIVE, BRANCH_POLARITY_UNKNOWN])
    if alignment == "SOURCE_ALIGNMENT_NOT_AVAILABLE":
        # Il metadato manca: il grounding documentale resta necessario e la
        # candidate non viene promossa per la sola assenza del metadato.
        warnings.append("SOURCE_POLARITY_UNAVAILABLE")
        reasons.append("DOCUMENT_GROUNDING_STILL_REQUIRED")
        return admission(ADMITTED_GROUNDING_WITH_SOURCE_POLARITY_UNKNOWN,
                         [BRANCH_POSITIVE, BRANCH_POLARITY_UNKNOWN])

    reasons.append("SOURCE_ALIGNED_WITH_THE_ASSERTION")
    return admission(ADMITTED_NORMAL_GROUNDING, [BRANCH_POSITIVE])


def split_branches(admissions: list[CandidateRuntimeAdmission]) -> dict[str, list[str]]:
    """Ripartizione delle candidate per ramo del dossier."""
    out: dict[str, list[str]] = {
        BRANCH_POSITIVE: [], BRANCH_NEGATIVE: [], BRANCH_NEUTRAL: [],
        BRANCH_POLARITY_UNKNOWN: [], BRANCH_UNRESOLVED_REGIMEN: [],
        BRANCH_PARTIAL_ALTERATION: [], "REJECTED": [],
    }
    for admission in admissions:
        if admission.is_rejected and not admission.allowed_branches:
            out["REJECTED"].append(admission.candidate_id)
            continue
        for branch in admission.allowed_branches:
            out[branch].append(admission.candidate_id)
        if admission.is_rejected:
            out["REJECTED"].append(admission.candidate_id)
    return out
