"""Mappatura dei casi del clinical gold sulla richiesta della pipeline.

Il clinical gold descrive un caso in prosa clinica; la pipeline vuole campi tipizzati
(`gene`, `variant`, `alteration_type`, `therapy_line`, `disease_setting`). Tradurre
l'una nell'altra e' un atto interpretativo, non una conversione meccanica: decidere
che «progressione dopo ALK-TKI di seconda generazione» corrisponde a `later-line` e'
una lettura del caso.

Per questo la mappatura vive qui come **dato dichiarato**, non sparsa nel runner, e
viene registrata nel manifest della run. Un revisore puo' contestarla guardando una
tabella, invece di dover leggere il codice.

`alteration_type` non e' una scelta libera: determina quale percorso di traversal la
pipeline usa. Sbagliarlo cambierebbe l'esperimento, non solo l'etichetta.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import ClinicalGoldCase


@dataclass(frozen=True)
class CaseMapping:
    """I campi tipizzati che la pipeline riceve, con la loro giustificazione."""

    case_id: str
    gene: str
    variant: str
    tumor_type: str
    alteration_type: str
    therapy_line: str
    disease_setting: str | None
    disease_stage: str | None
    prior_therapies: tuple[str, ...]
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "gene": self.gene,
            "variant": self.variant,
            "tumor_type": self.tumor_type,
            "alteration_type": self.alteration_type,
            "therapy_line": self.therapy_line,
            "disease_setting": self.disease_setting,
            "disease_stage": self.disease_stage,
            "prior_therapies": list(self.prior_therapies),
            "rationale": self.rationale,
        }


# Una voce per caso development. Ogni scelta e' motivata rispetto al testo del gold.
CASE_MAPPINGS: tuple[CaseMapping, ...] = (
    CaseMapping(
        case_id="PILOT-K1-FGFR2-iCCA",
        gene="FGFR2",
        variant="Fusion",
        tumor_type="Intrahepatic Cholangiocarcinoma",
        alteration_type="fusion",
        therapy_line="second-line",
        disease_setting="metastatic",
        disease_stage="advanced",
        prior_therapies=("systemic chemotherapy",),
        rationale=(
            "Il gold specifica fusione/riarrangiamento, quindi alteration_type=fusion: "
            "il percorso per point_mutation cercherebbe una variante puntiforme che il "
            "caso non ha. `previously treated` con progressione dopo almeno una linea "
            "sistemica diventa second-line."
        ),
    ),
    CaseMapping(
        case_id="PILOT-A2-ALK-G1202R",
        gene="ALK",
        variant="G1202R",
        tumor_type="Non-Small Cell Lung Cancer",
        alteration_type="point_mutation",
        therapy_line="later-line",
        disease_setting="metastatic",
        disease_stage="advanced",
        prior_therapies=("second-generation ALK inhibitor",),
        rationale=(
            "G1202R e' una mutazione puntiforme singola: il gold lo dice esplicitamente "
            "e include una claim di guardrail sulle composte. La progressione dopo un "
            "ALK-TKI di seconda generazione colloca il caso oltre la seconda linea."
        ),
    ),
    CaseMapping(
        case_id="PILOT-C1-EGFR-L858R-CONTEXT",
        gene="EGFR",
        variant="L858R",
        tumor_type="Non-Small Cell Lung Cancer",
        alteration_type="point_mutation",
        therapy_line="first-line",
        disease_setting="metastatic",
        disease_stage="advanced",
        prior_therapies=(),
        rationale=(
            "Prima linea, treatment-naive, non resecato: prior_therapies resta vuoto e "
            "disease_setting e' metastatic, non resected. E' la distinzione su cui il "
            "caso si gioca, perche' separa FLAURA da ADAURA."
        ),
    ),
    CaseMapping(
        case_id="PILOT-N1-RMI2-SNAPSHOT",
        gene="RMI2",
        variant="Mutation",
        tumor_type="Solid Tumor",
        alteration_type="point_mutation",
        therapy_line="first-line",
        disease_setting=None,
        disease_stage=None,
        prior_therapies=(),
        rationale=(
            "Il gold lascia variante e malattia vuote: la domanda e' gene->farmaco sullo "
            "snapshot. Si usano i valori piu' generici possibili, perche' restringere "
            "renderebbe l'assenza di risultati meno informativa: un traversal vuoto su "
            "una richiesta generica e' una prova negativa piu' forte."
        ),
    ),
)

_BY_CASE = {mapping.case_id: mapping for mapping in CASE_MAPPINGS}


class MissingCaseMapping(KeyError):
    """Un caso del gold non ha una mappatura dichiarata."""


def mapping_for(case_id: str) -> CaseMapping:
    mapping = _BY_CASE.get(case_id)
    if mapping is None:
        raise MissingCaseMapping(
            f"nessuna mappatura dichiarata per {case_id!r}. Va aggiunta a "
            "CASE_MAPPINGS con la sua motivazione, non dedotta a runtime."
        )
    return mapping


def build_request(case: ClinicalGoldCase, *, execution_mode: str = "live") -> Any:
    """Costruisce la richiesta della pipeline dal caso gold."""
    from backend.api.schemas import ArchitectureComparisonRequest

    mapping = mapping_for(case.case_id)
    return ArchitectureComparisonRequest(
        gene=mapping.gene or None,
        variant=mapping.variant,
        tumor_type=mapping.tumor_type,
        alteration_type=mapping.alteration_type,  # type: ignore[arg-type]
        therapy_line=mapping.therapy_line,
        disease_stage=mapping.disease_stage,
        disease_setting=mapping.disease_setting,  # type: ignore[arg-type]
        prior_therapies=list(mapping.prior_therapies),
        execution_mode=execution_mode,  # type: ignore[arg-type]
    )


def mapping_manifest() -> dict[str, Mapping[str, Any]]:
    """La tabella completa, da allegare agli artefatti della run."""
    return {
        "note": (
            "Tradurre il caso clinico in campi tipizzati e' un atto interpretativo. "
            "La tabella e' dichiarata come dato perche' sia contestabile senza "
            "leggere il codice."
        ),
        "mappings": {m.case_id: m.as_dict() for m in CASE_MAPPINGS},
    }
