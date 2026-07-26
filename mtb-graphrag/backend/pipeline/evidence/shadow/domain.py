"""Dominio di un claim: terapeutico, diagnostico, prognostico.

Il dominio e' la distinzione che il modello 1.0 non aveva e che gli e' costata
tre record senza rappresentazione. Un claim terapeutico afferma l'effetto di un
intervento; uno diagnostico afferma cosa un biomarcatore identifica; uno
prognostico afferma come va il paziente. Sono tre affermazioni di tipo diverso, e
confrontarle numericamente non e' una scelta di ranking discutibile: e' una
somma di cose che non si sommano.

Per i tre tipi terapeutici il dominio e' derivato dal tipo invece che
memorizzato. Non e' un'ottimizzazione: e' cio' che permette al repository 1.0 di
restare byte per byte quello che era, perche' nessun campo nuovo entra nella loro
serializzazione. I due tipi non terapeutici lo portano esplicito, perche' per
loro non e' ridondante.
"""

from __future__ import annotations

from typing import Any

DOMAIN_THERAPEUTIC = "therapeutic"
DOMAIN_DIAGNOSTIC = "diagnostic"
DOMAIN_PROGNOSTIC = "prognostic"

CLAIM_DOMAINS = (DOMAIN_THERAPEUTIC, DOMAIN_DIAGNOSTIC, DOMAIN_PROGNOSTIC)

CLAIM_TYPE_TO_DOMAIN = {
    "atomic_intervention_claim": DOMAIN_THERAPEUTIC,
    "aggregate_intervention_claim": DOMAIN_THERAPEUTIC,
    "regimen_claim": DOMAIN_THERAPEUTIC,
    "diagnostic_claim": DOMAIN_DIAGNOSTIC,
    "prognostic_claim": DOMAIN_PROGNOSTIC,
}

THERAPEUTIC_CLAIM_TYPES = tuple(
    t for t, d in CLAIM_TYPE_TO_DOMAIN.items() if d == DOMAIN_THERAPEUTIC
)
NON_THERAPEUTIC_CLAIM_TYPES = ("diagnostic_claim", "prognostic_claim")
ALL_CLAIM_TYPES = tuple(CLAIM_TYPE_TO_DOMAIN)

# Campi che ogni EvidenceClaim porta, qualunque sia il dominio. `intervention`
# non c'e': e' la ragione per cui la base esiste separata dai tipi terapeutici.
EVIDENCE_CLAIM_BASE_FIELDS = (
    "claim_id",
    "parent_id",
    "graph_evidence_id",
    "claim_domain",
    "claim_type",
    "biomarker",
    "disease_scope",
    "direction",
    "polarity",
    "source_unit_ids",
    "locators",
    "qualification_link_ids",
    "review_status",
    "propagation_policy",
    "provenance",
    "legacy_statement_ids",
    "deprecated",
    "schema_version",
)


class DomainError(ValueError):
    """Il dominio di un claim e' assente o incoerente col suo tipo."""


def domain_for_claim_type(claim_type: str) -> str:
    try:
        return CLAIM_TYPE_TO_DOMAIN[claim_type]
    except KeyError:
        raise DomainError(f"tipo di claim senza dominio dichiarato: {claim_type!r}") from None


def domain_of(obj: Any) -> str:
    """Dominio di un oggetto tipizzato, esplicito se lo porta, derivato altrimenti."""
    declared = getattr(obj, "claim_domain", None)
    claim_type = getattr(obj, "claim_type", None)
    if claim_type is None:
        raise DomainError("l'oggetto non e' un claim: non ha un claim_type")
    derived = domain_for_claim_type(claim_type)
    if declared is not None and declared != derived:
        raise DomainError(
            f"{getattr(obj, 'claim_id', '?')}: dominio dichiarato {declared!r} "
            f"incoerente col tipo {claim_type!r}"
        )
    return derived


def receives_therapy_score(claim_type: str) -> bool:
    """Solo i claim terapeutici ricevono un therapy score."""
    return domain_for_claim_type(claim_type) == DOMAIN_THERAPEUTIC


def is_therapeutic(claim_type: str) -> bool:
    return domain_for_claim_type(claim_type) == DOMAIN_THERAPEUTIC
