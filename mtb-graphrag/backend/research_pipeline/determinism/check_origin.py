"""Origine dichiarata di ogni controllo deterministico.

``gates.evaluate_association`` produce una support mask di quattro assi, e la
mask da sola non dice **dove** ciascun asse è stato deciso. Due di essi —
``disease`` e ``biomarker`` — arrivano già risolti: ``kg_retrieval`` ammette una
candidate solo se il match strutturale su disease e biomarker è passato, quindi
allo stage 11 quei due valori sono costanti e non un calcolo. Gli altri due sono
gli unici realmente decisi lì.

Mostrarli affiancati senza distinguerli lascerebbe credere che i gate valutino
quattro assi indipendenti, e che ``disease: SUPPORTED`` sia una conferma
aggiuntiva anziché la ripetizione di un filtro già applicato a monte.

Questo modulo non calcola nulla: legge la mask e vi appone l'origine. Aggiungere
qui un giudizio significherebbe spostare una decisione fuori da ``gates``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CHECK_VERSION = "deterministic-checks/1.0"

#: Le quattro origini possibili. Il vocabolario è chiuso: un'origine ignota
#: renderebbe illeggibile la sola informazione che questi record esistono per
#: trasmettere.
CHECK_SOURCES: tuple[str, ...] = (
    "COMPUTED_HERE",
    "INHERITED_VERIFIED_RESULT",
    "NOT_IMPLEMENTED",
    "NOT_APPLICABLE",
)

#: Assi ereditati dal match strutturale, con lo stage che li ha decisi.
_INHERITED_AXES: dict[str, str] = {
    "disease": "stage_5_kg_retrieval",
    "biomarker": "stage_5_kg_retrieval",
}

#: Assi realmente calcolati dallo stage dei gate.
_COMPUTED_AXES: tuple[str, ...] = ("intervention", "direction")

_AXIS_LABELS: dict[str, str] = {
    "disease": "Malattia",
    "biomarker": "Biomarcatore",
    "intervention": "Intervento",
    "direction": "Direzione dell'evidenza",
}

#: Controlli previsti dal design e privi di implementazione. Restano elencati
#: perché la loro assenza è essa stessa un fatto che il relatore deve poter
#: leggere; ometterli farebbe sembrare la copertura completa.
NOT_IMPLEMENTED_CHECKS: tuple[str, ...] = (
    "source_gate",
    "provenance_gate",
    "completeness",
    "negation",
    "contradiction_gate",
    "score",
)

_NOT_IMPLEMENTED_LABELS: dict[str, str] = {
    "source_gate": "Source gate",
    "provenance_gate": "Provenance gate",
    "completeness": "Completezza",
    "negation": "Negazione",
    "contradiction_gate": "Contradiction gate",
    "score": "Score",
}


@dataclass(frozen=True)
class DeterministicCheck:
    """Un controllo, con l'origine del suo esito.

    ``source_stage`` è ``None`` quando nessuno stage lo ha prodotto: un controllo
    non implementato che dichiarasse uno stage si leggerebbe come eseguito.
    """

    check_id: str
    label: str
    source: str
    result: str | None
    reason_code: str
    source_stage: str | None
    evidence_ref: Any
    version: str

    def __post_init__(self) -> None:
        if self.source not in CHECK_SOURCES:
            raise ValueError(f"origine di controllo sconosciuta: {self.source!r}")
        if self.source == "NOT_IMPLEMENTED" and self.source_stage is not None:
            raise ValueError(
                f"{self.check_id} non è implementato ma dichiara "
                f"{self.source_stage!r}: si leggerebbe come eseguito"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "label": self.label,
            "source": self.source,
            "result": self.result,
            "reason_code": self.reason_code,
            "source_stage": self.source_stage,
            "evidence_ref": self.evidence_ref,
            "version": self.version,
        }


def _axis_check(axis: str, mask: dict[str, Any], source: str, source_stage: str) -> DeterministicCheck:
    present = axis in mask
    result = mask.get(axis) if present else None

    # Un asse dichiarato non applicabile dai gate non è un controllo fallito, e
    # nemmeno un controllo eseguito: `direction` sotto THERAPY_DISCOVERY non ha
    # un intervento richiesto rispetto a cui essere coerente.
    if result == "NOT_APPLICABLE":
        return DeterministicCheck(
            check_id=axis, label=_AXIS_LABELS.get(axis, axis),
            source="NOT_APPLICABLE", result="NOT_APPLICABLE",
            reason_code="AXIS_NOT_APPLICABLE_FOR_QUERY_INTENT",
            source_stage=source_stage, evidence_ref=None, version=CHECK_VERSION,
        )

    return DeterministicCheck(
        check_id=axis,
        label=_AXIS_LABELS.get(axis, axis),
        source=source,
        result=result,
        reason_code=str(result) if present else "AXIS_ABSENT_FROM_SUPPORT_MASK",
        source_stage=source_stage,
        evidence_ref=None,
        version=CHECK_VERSION,
    )


def checks_for(support_mask: dict[str, Any] | None) -> tuple[DeterministicCheck, ...]:
    """Controlli di una candidate, nell'ordine in cui vanno mostrati.

    Prima gli assi ereditati, poi quelli calcolati, infine quelli assenti: è
    l'ordine che rende leggibile quanto della mask sia davvero deciso qui.
    """
    mask = dict(support_mask or {})

    inherited = [
        _axis_check(axis, mask, "INHERITED_VERIFIED_RESULT", stage)
        for axis, stage in _INHERITED_AXES.items()
    ]
    computed = [
        _axis_check(axis, mask, "COMPUTED_HERE", "stage_11_deterministic_gates")
        for axis in _COMPUTED_AXES
    ]
    missing = [
        DeterministicCheck(
            check_id=check_id, label=_NOT_IMPLEMENTED_LABELS.get(check_id, check_id),
            source="NOT_IMPLEMENTED", result=None,
            reason_code="CHECK_DEFINED_IN_DESIGN_BUT_NOT_IMPLEMENTED",
            source_stage=None, evidence_ref=None, version=CHECK_VERSION,
        )
        for check_id in NOT_IMPLEMENTED_CHECKS
    ]
    return tuple([*inherited, *computed, *missing])


def checks_payload(support_mask: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Forma serializzabile, per l'``output_preview`` dello stage."""
    return [check.to_dict() for check in checks_for(support_mask)]
