"""STAGE 8 — deterministic support mask, status, gate, and warnings. Fully
rule-based: combines the already-structural CaseContext-vs-candidate match
(from retrieval.py) with only VALIDATED Gemma enrichments (ENRICHMENT_ACCEPTED
or ENRICHMENT_ACCEPTED_WITH_WARNING outcomes only -- never a rejected or raw
one). Gemma's evidence_kind is treated as reported testimony to reconcile
against the candidate's own asserted direction; Gemma itself never decides
the status. This is a new, independent decision path -- it does not call or
depend on the frozen `llm_claim_extractor` / `ClaimSupportVerifier`.
"""
from __future__ import annotations

import re
from typing import Any

POSITIVE_EVIDENCE_KINDS = {"RESPONSE", "BENEFIT"}
GATE_BUCKETS = ("PRIMARY_BUCKET", "WARNING_BUCKET", "REJECTED_BUCKET", "DISCOVERY_BUCKET")
STATUS_VALUES = ("DIRECT", "PARTIAL", "AMBIGUOUS", "CONTRADICTED", "DISCOVERED", "NO_MATCH")

# --- Due assi distinti, non uno ---------------------------------------------
#
# Il campo ``direction`` di ``graph_candidate_repository/2.0`` porta **due assi
# sovrapposti**: talvolta la *polarità della fonte* (``Supports`` / ``Does Not
# Support``), talvolta la *direzione clinica dell'asserzione*
# (``Sensitivity/Response``, ``Resistance``, …). La polarità vera vive in
# ``source_properties.evidence.evidence_direction``, che il runtime non leggeva.
#
# Il test di sottostringa precedente (``"support" in direction``) era vero anche
# per ``"does not support"``, e ``"sensitivity"`` / ``"response"`` erano veri per
# ``"reduced sensitivity"`` e ``"adverse response"``. 752 candidate su 46 864
# ricevevano così supporto positivo da una fonte negativa o avversa.
#
# La lettura è ora per **valore normalizzato esatto**, e la negazione è valutata
# **prima** dell'affermazione. Un valore non mappato non è mai positivo.

#: Polarità della fonte rispetto all'asserzione.
SOURCE_SUPPORTS = "SUPPORTS"
SOURCE_DOES_NOT_SUPPORT = "DOES_NOT_SUPPORT"
SOURCE_CONTRADICTS = "CONTRADICTS"
SOURCE_NEUTRAL = "NEUTRAL"
SOURCE_UNKNOWN = "UNKNOWN"

SOURCE_POLARITIES = (SOURCE_SUPPORTS, SOURCE_DOES_NOT_SUPPORT, SOURCE_CONTRADICTS,
                     SOURCE_NEUTRAL, SOURCE_UNKNOWN)

#: Polarità che **non possono** produrre supporto positivo, in nessuna
#: combinazione con la direzione clinica o con l'``evidence_kind`` riportato.
NON_SUPPORTING_POLARITIES = frozenset({SOURCE_DOES_NOT_SUPPORT, SOURCE_CONTRADICTS, SOURCE_NEUTRAL})

#: ``evidence_direction`` / ``direction`` -> polarità. Corrisponde al vocabolario
#: osservato nei dati: 46 864 candidate v2 producono soltanto ``Supports``,
#: ``Does Not Support``, stringa vuota o assente. ``CONTRADICTS`` e ``NEUTRAL``
#: non sono prodotti dall'export corrente ma sono mappati perché il contratto 3.0
#: li prevede e un dato futuro non deve ricadere nel ramo positivo.
_POLARITY_BY_VALUE: dict[str, str] = {
    "supports": SOURCE_SUPPORTS,
    "does not support": SOURCE_DOES_NOT_SUPPORT,
    "contradicts": SOURCE_CONTRADICTS,
    "contradicts assertion": SOURCE_CONTRADICTS,
    "neutral": SOURCE_NEUTRAL,
    "no difference": SOURCE_NEUTRAL,
    "neutral or no difference": SOURCE_NEUTRAL,
}

#: Direzione clinica dell'asserzione, quando il campo la esprime.
CLINICAL_SENSITIVITY = "SENSITIVITY"
CLINICAL_RESISTANCE = "RESISTANCE"
CLINICAL_POLARITY_ONLY = "POLARITY_ONLY"
CLINICAL_UNKNOWN = "UNKNOWN"

#: ``Reduced Sensitivity`` e ``Adverse Response`` sono direzioni **avverse**: la
#: sottostringa le faceva ricadere fra le positive.
_CLINICAL_BY_VALUE: dict[str, str] = {
    "sensitivity response": CLINICAL_SENSITIVITY,
    "sensitivity": CLINICAL_SENSITIVITY,
    "response": CLINICAL_SENSITIVITY,
    "resistance": CLINICAL_RESISTANCE,
    "reduced sensitivity": CLINICAL_RESISTANCE,
    "adverse response": CLINICAL_RESISTANCE,
    "supports": CLINICAL_POLARITY_ONLY,
    "does not support": CLINICAL_POLARITY_ONLY,
}

#: Esito dedicato: la fonte non sostiene l'asserzione. Non è ``CONFLICTING`` —
#: il conflitto è fra ciò che gli autori riportano e la direzione della
#: candidate — ed è deliberatamente **diverso** da ``CONSISTENT``, così nessun
#: ramo a valle può confonderlo con un supporto.
SOURCE_DOES_NOT_SUPPORT_OUTCOME = "SOURCE_DOES_NOT_SUPPORT"

DIRECTION_CONSISTENCY_VALUES = ("CONSISTENT", "CONFLICTING", "UNRELATED",
                                SOURCE_DOES_NOT_SUPPORT_OUTCOME)


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def source_polarity(value: Any) -> str:
    """Polarità della fonte, per valore normalizzato esatto.

    Un valore assente, vuoto o non mappato è ``UNKNOWN``: non è supporto. È la
    differenza fra «la fonte non dice» e «la fonte conferma».
    """
    return _POLARITY_BY_VALUE.get(_norm(value), SOURCE_UNKNOWN)


def clinical_direction(value: Any) -> str:
    """Direzione clinica dell'asserzione, per valore normalizzato esatto."""
    return _CLINICAL_BY_VALUE.get(_norm(value), CLINICAL_UNKNOWN)


def candidate_source_polarity(candidate: dict[str, Any]) -> str:
    """Polarità della fonte di una candidate, dai **due** punti in cui vive.

    ``source_properties.evidence.evidence_direction`` è la sede propria; il campo
    ``direction`` la duplica per una parte delle candidate. Se uno dei due dichiara
    una polarità non-supportante, quella prevale: la negazione non si perde perché
    l'altro campo tace.
    """
    evidence = (candidate.get("source_properties") or {}).get("evidence") or {}
    from_evidence = source_polarity(evidence.get("evidence_direction"))
    from_direction = source_polarity(candidate.get("direction"))
    for polarity in (from_evidence, from_direction):
        if polarity in NON_SUPPORTING_POLARITIES:
            return polarity
    if SOURCE_SUPPORTS in (from_evidence, from_direction):
        return SOURCE_SUPPORTS
    return SOURCE_UNKNOWN


def direction_consistency(
    candidate_direction: str | None,
    evidence_kind: str | None,
    source_polarity_value: str | None = None,
) -> str | None:
    """Coerenza fra la direzione della candidate e l'``evidence_kind`` riportato.

    ``source_polarity_value`` è la polarità **già risolta** della fonte. Quando è
    non-supportante l'esito è ``SOURCE_DOES_NOT_SUPPORT`` qualunque cosa riporti
    l'enrichment: una fonte che non sostiene l'asserzione non può renderla
    supportata, e nessuna inversione automatica della direzione viene applicata.
    """
    if evidence_kind is None:
        return None

    # 1 — NEGAZIONE PRIMA DELL'AFFERMAZIONE.
    polarity = source_polarity_value or source_polarity(candidate_direction)
    if polarity in NON_SUPPORTING_POLARITIES:
        return SOURCE_DOES_NOT_SUPPORT_OUTCOME

    # 2 — direzione clinica, per valore esatto.
    direction = clinical_direction(candidate_direction)
    if direction == CLINICAL_RESISTANCE:
        if evidence_kind == "RESISTANCE":
            return "CONSISTENT"
        if evidence_kind in POSITIVE_EVIDENCE_KINDS:
            return "CONFLICTING"
        return "UNRELATED"
    if direction in (CLINICAL_SENSITIVITY, CLINICAL_POLARITY_ONLY):
        if evidence_kind in POSITIVE_EVIDENCE_KINDS:
            return "CONSISTENT"
        if evidence_kind == "RESISTANCE":
            return "CONFLICTING"
        return "UNRELATED"

    # 3 — direzione non mappata: mai positiva per default.
    return "UNRELATED"


def candidate_direction_consistency(candidate: dict[str, Any], evidence_kind: str | None) -> str | None:
    """Entry point **sicuro**: la candidate intera, non il solo campo ``direction``.

    ``direction_consistency`` con due argomenti risponde a una domanda più
    ristretta — «questa direzione clinica e questo ``evidence_kind`` concordano?»
    — e non può vedere la polarità, che per 213 candidate v2 vive soltanto in
    ``source_properties.evidence.evidence_direction``. Chiamarla con il solo
    ``direction`` su una candidate è quindi corretto ma incompleto.

    Ogni consumatore che decida sul **supporto** deve usare questa funzione o
    ``evaluate_association``.
    """
    return direction_consistency(candidate.get("direction"), evidence_kind,
                                 source_polarity_value=candidate_source_polarity(candidate))


def evaluate_association(query_intent: str, candidate: dict[str, Any], validated_enrichments: list[dict[str, Any]]) -> dict[str, Any]:
    """validated_enrichments: list of {"validation_outcome", "enrichment"} where outcome is
    ENRICHMENT_ACCEPTED or ENRICHMENT_ACCEPTED_WITH_WARNING only -- callers must filter first."""
    accepted = [item for item in validated_enrichments if item["validation_outcome"] in ("ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING")]
    warnings: list[str] = []
    mask = {"disease": "SUPPORTED", "biomarker": "SUPPORTED"}

    if query_intent == "THERAPY_DISCOVERY":
        mask["intervention"] = "DISCOVERED"
        mask["direction"] = "NOT_APPLICABLE"
        return {"status": "DISCOVERED", "support_mask": mask, "gate_bucket": "DISCOVERY_BUCKET", "warnings": warnings, "direction_consistencies": []}

    mask["intervention"] = "SUPPORTED"
    if not accepted:
        mask["direction"] = "NO_DOCUMENT_SIGNAL"
        warnings.append("NO_VALIDATED_ENRICHMENT_AVAILABLE")
        return {"status": "AMBIGUOUS", "support_mask": mask, "gate_bucket": "WARNING_BUCKET", "warnings": warnings, "direction_consistencies": []}

    polarity = candidate_source_polarity(candidate)
    consistencies = [
        direction_consistency(candidate.get("direction"),
                              item["enrichment"].get("evidence_kind"),
                              source_polarity_value=polarity)
        for item in accepted
    ]
    any_warning = any(item["validation_outcome"] == "ENRICHMENT_ACCEPTED_WITH_WARNING" for item in accepted)
    if any_warning:
        warnings.append("SOME_ENRICHMENTS_ACCEPTED_WITH_WARNING")

    # La polarità non-supportante è decisa **prima** di ogni altro ramo: una fonte
    # che non sostiene l'asserzione non può finire nel bucket primario, nemmeno
    # con un enrichment accettato che riporta beneficio. La candidate resta
    # visibile con il proprio motivo invece di sparire.
    if SOURCE_DOES_NOT_SUPPORT_OUTCOME in consistencies:
        mask["direction"] = SOURCE_DOES_NOT_SUPPORT_OUTCOME
        warnings.append(f"SOURCE_POLARITY_{polarity}")
        return {"status": "AMBIGUOUS", "support_mask": mask, "gate_bucket": "WARNING_BUCKET",
                "warnings": warnings, "direction_consistencies": consistencies,
                "source_polarity": polarity}

    if "CONFLICTING" in consistencies:
        mask["direction"] = "CONTRADICTED"
        return {"status": "CONTRADICTED", "support_mask": mask, "gate_bucket": "REJECTED_BUCKET", "warnings": warnings, "direction_consistencies": consistencies}
    if "CONSISTENT" in consistencies:
        mask["direction"] = "SUPPORTED"
        gate = "WARNING_BUCKET" if any_warning else "PRIMARY_BUCKET"
        status = "PARTIAL" if any_warning else "DIRECT"
        return {"status": status, "support_mask": mask, "gate_bucket": gate, "warnings": warnings, "direction_consistencies": consistencies}
    mask["direction"] = "UNRELATED_EVIDENCE"
    warnings.append("VALIDATED_ENRICHMENT_DOES_NOT_ADDRESS_DIRECTION")
    return {"status": "PARTIAL", "support_mask": mask, "gate_bucket": "WARNING_BUCKET", "warnings": warnings, "direction_consistencies": consistencies}
