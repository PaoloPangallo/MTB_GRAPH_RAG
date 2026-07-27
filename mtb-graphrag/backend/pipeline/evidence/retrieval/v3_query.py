"""Query tipizzata del retriever V3.

La query porta due forme dello stesso oggetto e le tiene entrambe. `original` e'
cio' che il chiamante ha scritto; la forma normalizzata e' cio' su cui i gate
decidono. Tenere solo la seconda renderebbe impossibile spiegare un esito a chi
ha scritto la prima — «perche' questa query non trova nulla?» si risponde
mostrando la trasformazione, non il risultato.

Il biomarcatore e' l'unico campo in cui la composizione fa una differenza
clinica. Gene e alterazione, quando entrambi presenti, formano **un solo**
vincolo congiunto: `EGFR` + `L858R` diventa `EGFR L858R`, e non due vincoli
alternativi di cui basti soddisfarne uno. E' la stessa regola che il fix
congiuntivo ha congelato, ed e' cio' che impedisce a una query su `EGFR L858R`
di raggiungere un claim su `EGFR T790M` per il solo fatto che il gene coincide.

Nessun LLM entra nel matching strutturale. La normalizzazione e' testuale e
deterministica: spazi, maiuscole, e nient'altro.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.retrieval.backends import (
    DEFAULT_POLICY_MODE,
    validate_policy_mode,
)
from benchmarks.mtb_evidence.evaluation.claim_type_retrieval_contract import normalize

QUERY_SCHEMA_VERSION = "qualified_claim_query/1.0"

# --- domini -------------------------------------------------------------------

DOMAIN_THERAPEUTIC = "therapeutic"
DOMAIN_DIAGNOSTIC = "diagnostic"
DOMAIN_PROGNOSTIC = "prognostic"
DOMAIN_UNTYPED = "untyped"

CLAIM_DOMAINS = (
    DOMAIN_THERAPEUTIC,
    DOMAIN_DIAGNOSTIC,
    DOMAIN_PROGNOSTIC,
    DOMAIN_UNTYPED,
)

# Il vocabolario del gate di dominio. La traduzione avviene qui e in nessun
# altro punto: il gate non impara un secondo nome per gli stessi domini.
GATE_QUERY_DOMAIN = {
    DOMAIN_THERAPEUTIC: "therapeutic_evidence_query",
    DOMAIN_DIAGNOSTIC: "diagnostic_evidence_query",
    DOMAIN_PROGNOSTIC: "prognostic_evidence_query",
    DOMAIN_UNTYPED: "untyped_evidence_query",
}

# --- forma del vincolo di intervento ------------------------------------------

INTERVENTION_ABSENT = "absent"
INTERVENTION_SINGLE = "single"
INTERVENTION_REGIMEN = "regimen"
INTERVENTION_CLASS = "class"
INTERVENTION_UNSPECIFIED_MULTI = "unspecified_multi"

INTERVENTION_FORMS = (
    INTERVENTION_ABSENT,
    INTERVENTION_SINGLE,
    INTERVENTION_REGIMEN,
    INTERVENTION_CLASS,
    INTERVENTION_UNSPECIFIED_MULTI,
)

DEFAULT_RESULT_LIMIT = 50
MAX_RESULT_LIMIT = 500


class QualifiedClaimQueryError(ValueError):
    """La query V3 non e' interrogabile cosi' com'e'."""


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True)
class QualifiedClaimQuery:
    """Che cosa si cerca nel corpus promosso, e quanto se ne vuole vedere."""

    query_id: str
    claim_domain: str = DOMAIN_UNTYPED
    gene: str = ""
    alteration: str = ""
    # Forma gia' composta. Serve alle query che nominano il biomarcatore come la
    # fonte lo scrive (`EML4::ALK Fusion AND ALK G1202R`), dove separare gene e
    # alterazione richiederebbe di interpretare.
    biomarker: str = ""
    disease: str = ""
    interventions: tuple[str, ...] = ()
    intervention_class: str = ""
    intervention_combination: bool = False
    direction: str = ""
    polarity: str = ""
    policy_mode: str = DEFAULT_POLICY_MODE
    include_warning: bool = True
    include_audit: bool = False
    include_rejected: bool = False
    result_limit: int = DEFAULT_RESULT_LIMIT
    original: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_mode", validate_policy_mode(self.policy_mode))
        object.__setattr__(self, "interventions", tuple(self.interventions))
        object.__setattr__(self, "original", dict(self.original))
        problems = validate(self)
        if problems:
            raise QualifiedClaimQueryError("; ".join(problems))

    # --- forme normalizzate ---------------------------------------------------

    @property
    def normalized_biomarker(self) -> str:
        """Il vincolo di biomarcatore, composto una volta sola.

        Gene e alterazione insieme sono un unico vincolo congiunto. La forma
        esplicita, quando c'e', vince: chi la scrive sta gia' nominando il
        biomarcatore come il corpus lo nomina.
        """
        explicit = _clean(self.biomarker)
        if explicit:
            return explicit
        parts = [_clean(self.gene), _clean(self.alteration)]
        return " ".join(part for part in parts if part)

    @property
    def normalized_disease(self) -> str:
        return _clean(self.disease)

    @property
    def normalized_interventions(self) -> tuple[str, ...]:
        return tuple(_clean(item) for item in self.interventions if _clean(item))

    @property
    def intervention_form(self) -> str:
        if _clean(self.intervention_class):
            return INTERVENTION_CLASS
        drugs = self.normalized_interventions
        if not drugs:
            return INTERVENTION_ABSENT
        if self.intervention_combination:
            return INTERVENTION_REGIMEN
        if len(drugs) == 1:
            return INTERVENTION_SINGLE
        return INTERVENTION_UNSPECIFIED_MULTI

    @property
    def is_untyped(self) -> bool:
        return self.claim_domain == DOMAIN_UNTYPED

    @property
    def constrains_biomarker(self) -> bool:
        return bool(self.normalized_biomarker)

    # --- traduzioni -----------------------------------------------------------

    def to_gate_query(self) -> dict[str, Any]:
        """La query nel vocabolario dei gate congelati.

        I campi vuoti non entrano. Un `direction: ""` verrebbe letto dal gate
        come un vincolo di direzione vuoto invece che come assenza di vincolo, e
        le due cose portano a esiti diversi.
        """
        payload: dict[str, Any] = {
            "query_id": self.query_id,
            "query_domain": GATE_QUERY_DOMAIN[self.claim_domain],
            "policy_mode": self.policy_mode,
        }
        if self.normalized_biomarker:
            payload["biomarker"] = self.normalized_biomarker
        if self.normalized_disease:
            payload["disease"] = self.normalized_disease
        if self.normalized_interventions:
            payload["interventions"] = list(self.normalized_interventions)
        if _clean(self.intervention_class):
            payload["intervention_class"] = _clean(self.intervention_class)
        if self.intervention_combination:
            payload["intervention_combination"] = True
        if _clean(self.direction):
            payload["direction"] = _clean(self.direction)
        if _clean(self.polarity):
            payload["polarity"] = _clean(self.polarity)
        return payload

    def normalized_form(self) -> dict[str, Any]:
        """La query come i gate la vedono, piu' cio' che decide il rendering."""
        return {
            "claim_domain": self.claim_domain,
            "gate_query": self.to_gate_query(),
            "include_audit": self.include_audit,
            "include_rejected": self.include_rejected,
            "include_warning": self.include_warning,
            "intervention_form": self.intervention_form,
            "normalized_biomarker": self.normalized_biomarker,
            "normalized_biomarker_key": normalize(self.normalized_biomarker),
            "normalized_disease": self.normalized_disease,
            "normalized_disease_key": normalize(self.normalized_disease),
            "normalized_interventions": list(self.normalized_interventions),
            "policy_mode": self.policy_mode,
            "query_id": self.query_id,
            "result_limit": self.result_limit,
            "schema_version": QUERY_SCHEMA_VERSION,
        }

    def to_dict(self) -> dict[str, Any]:
        """Query originale e forma normalizzata, entrambe conservate."""
        return {
            "normalized": self.normalized_form(),
            "original": dict(self.original) or self.declared_form(),
            "schema_version": QUERY_SCHEMA_VERSION,
        }

    def declared_form(self) -> dict[str, Any]:
        """I campi come sono stati dichiarati, prima di ogni normalizzazione."""
        return {
            "alteration": self.alteration,
            "biomarker": self.biomarker,
            "claim_domain": self.claim_domain,
            "direction": self.direction,
            "disease": self.disease,
            "gene": self.gene,
            "include_audit": self.include_audit,
            "include_rejected": self.include_rejected,
            "include_warning": self.include_warning,
            "intervention_class": self.intervention_class,
            "intervention_combination": self.intervention_combination,
            "interventions": list(self.interventions),
            "polarity": self.polarity,
            "policy_mode": self.policy_mode,
            "query_id": self.query_id,
            "result_limit": self.result_limit,
        }


def validate(query: QualifiedClaimQuery) -> list[str]:
    """Tutti i problemi della query, non solo il primo."""
    problems: list[str] = []
    if not _clean(query.query_id):
        problems.append("query_id mancante: il risultato non sarebbe tracciabile")
    if query.claim_domain not in CLAIM_DOMAINS:
        problems.append(
            f"claim_domain sconosciuto: {query.claim_domain!r}; ammessi {list(CLAIM_DOMAINS)}"
        )
    if _clean(query.intervention_class) and query.normalized_interventions:
        problems.append(
            "una query di classe non puo' portare anche interventi: la relazione "
            "farmaco-classe resta non verificata e non si compone con l'identita'"
        )
    if query.intervention_combination and len(query.normalized_interventions) < 2:
        problems.append(
            "combinazione dichiarata con meno di due componenti: due farmaci non "
            "dichiarati combinazione restano due vincoli alternativi"
        )
    if not isinstance(query.result_limit, int) or isinstance(query.result_limit, bool):
        problems.append(f"result_limit non e' un intero: {query.result_limit!r}")
    elif query.result_limit < 1 or query.result_limit > MAX_RESULT_LIMIT:
        problems.append(
            f"result_limit fuori intervallo [1, {MAX_RESULT_LIMIT}]: {query.result_limit}"
        )
    return problems


def build_query(payload: Mapping[str, Any]) -> QualifiedClaimQuery:
    """Costruisce una query dal dizionario, conservandone la forma originale."""
    interventions: Sequence[Any] = payload.get("interventions") or ()
    if isinstance(interventions, (str, bytes)):
        interventions = (interventions,)
    return QualifiedClaimQuery(
        query_id=str(payload.get("query_id") or ""),
        claim_domain=str(payload.get("claim_domain") or DOMAIN_UNTYPED),
        gene=str(payload.get("gene") or ""),
        alteration=str(payload.get("alteration") or ""),
        biomarker=str(payload.get("biomarker") or ""),
        disease=str(payload.get("disease") or ""),
        interventions=tuple(str(item) for item in interventions),
        intervention_class=str(payload.get("intervention_class") or ""),
        intervention_combination=bool(payload.get("intervention_combination") or False),
        direction=str(payload.get("direction") or ""),
        polarity=str(payload.get("polarity") or ""),
        policy_mode=payload.get("policy_mode", DEFAULT_POLICY_MODE),
        include_warning=bool(payload.get("include_warning", True)),
        include_audit=bool(payload.get("include_audit", False)),
        include_rejected=bool(payload.get("include_rejected", False)),
        result_limit=int(payload.get("result_limit", DEFAULT_RESULT_LIMIT)),
        original=dict(payload),
    )


def query_schema() -> dict[str, Any]:
    """Descrizione serializzabile dello schema, per gli artefatti della fase."""
    return {
        "claim_domains": list(CLAIM_DOMAINS),
        "default_result_limit": DEFAULT_RESULT_LIMIT,
        "fields": {
            "alteration": "alterazione; con il gene forma un unico vincolo congiunto",
            "biomarker": "forma gia' composta; quando presente ha la precedenza",
            "claim_domain": "dominio richiesto oppure untyped",
            "direction": "direzione, se specificata",
            "disease": "malattia della domanda",
            "gene": "gene; con l'alterazione forma un unico vincolo congiunto",
            "include_audit": "rendering del bucket audit; default escluso",
            "include_rejected": "rendering del bucket rejected; default escluso",
            "include_warning": "rendering del bucket warning; default incluso",
            "intervention_class": "classe di intervento; esclude gli interventi",
            "intervention_combination": "dichiara che gli interventi sono un regime",
            "interventions": "interventi richiesti; assente, singolo o regime",
            "polarity": "polarita', se specificata",
            "policy_mode": "modalita' di disease policy",
            "query_id": "identificatore della query",
            "result_limit": "limite per bucket",
        },
        "intervention_forms": list(INTERVENTION_FORMS),
        "llm_used_for_structural_matching": False,
        "max_result_limit": MAX_RESULT_LIMIT,
        "original_query_preserved": True,
        "schema_version": QUERY_SCHEMA_VERSION,
    }


__all__ = [
    "CLAIM_DOMAINS",
    "DEFAULT_RESULT_LIMIT",
    "DOMAIN_DIAGNOSTIC",
    "DOMAIN_PROGNOSTIC",
    "DOMAIN_THERAPEUTIC",
    "DOMAIN_UNTYPED",
    "GATE_QUERY_DOMAIN",
    "INTERVENTION_ABSENT",
    "INTERVENTION_CLASS",
    "INTERVENTION_FORMS",
    "INTERVENTION_REGIMEN",
    "INTERVENTION_SINGLE",
    "INTERVENTION_UNSPECIFIED_MULTI",
    "MAX_RESULT_LIMIT",
    "QUERY_SCHEMA_VERSION",
    "QualifiedClaimQuery",
    "QualifiedClaimQueryError",
    "build_query",
    "query_schema",
    "validate",
]
