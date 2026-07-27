"""Propagation policy obbligatoria per ogni claim tipizzato.

Nel modello 1.1 `propagation_policy` esiste su `AtomicInterventionClaim` e su
`_NonTherapeuticClaimBase`, e non esiste su `AggregateInterventionClaim` ne' su
`RegimenClaim`. `hard_filterable` e `final_evaluable` esistono soltanto sui non
terapeutici. L'asimmetria non e' visibile finche' si guardano i tipi uno per
uno, e diventa un difetto quando i record vengono serializzati insieme: sei
claim su 148 non dichiarano se possano propagare, e sono esattamente i sei la
cui propagazione va impedita.

Un aggregato non separabile e un regime sono i due oggetti che un consumatore e'
tentato di scomporre. Se il record tace, il consumatore deduce; e la deduzione
piu' naturale — "il risultato vale per ogni membro" — e' precisamente
l'inferenza che l'adjudication ha rifiutato su evidence:275.

Il modello 1.2 sposta i tre campi nella base e li rende obbligatori. Obbligatori
significa due cose insieme, e la seconda e' quella che conta:

    la serializzazione li scrive sempre
    la deserializzazione **rifiuta** un record che non li porta

Un default implicito in lettura riporterebbe il problema esattamente dov'era,
con in piu' l'illusione che sia stato risolto: il campo comparirebbe nei record
riletti, ma il suo valore sarebbe stato deciso dal parser e non dalla revisione.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MODEL_SCHEMA_VERSION_V12 = "qualified_claim_model/1.2"
PROPAGATION_CONTRACT_VERSION = "claim_propagation_contract/1.0"

# --- valori ammessi -----------------------------------------------------------

PROPAGATION_NONE = "none"
PROPAGATION_PROTOTYPE_ONLY = "prototype_only"
PROPAGATION_FINAL = "final"

PROPAGATION_POLICIES = (
    PROPAGATION_NONE,
    PROPAGATION_PROTOTYPE_ONLY,
    PROPAGATION_FINAL,
)

# I tre campi che ogni claim deve dichiarare. Sono tenuti insieme perche' la
# domanda a cui rispondono e' una sola, posta a tre livelli diversi: questo
# risultato puo' uscire dal prototipo, puo' filtrare, puo' essere valutato.
REQUIRED_PROPAGATION_FIELDS = (
    "propagation_policy",
    "hard_filterable",
    "final_evaluable",
)

# Campi obbligatori aggiuntivi per i tipi che aggregano piu' interventi. Non
# sono nella base: un claim atomico non ha membri, e dargli un campo sulla
# propagazione ai membri creerebbe una domanda senza referente.
MEMBER_PROPAGATION_FIELD = "member_propagation_allowed"

AGGREGATE_REQUIRED_FIELDS = (
    MEMBER_PROPAGATION_FIELD,
    "permits_member_specific_claims",
)

REGIMEN_REQUIRED_FIELDS = (
    MEMBER_PROPAGATION_FIELD,
    "result_applies_to_combination",
)

NON_ATOMIC_CLAIM_TYPES = ("aggregate_intervention_claim", "regimen_claim")

# --- codici -------------------------------------------------------------------

PROPAGATION_POLICY_MISSING = "PROPAGATION_POLICY_MISSING"
PROPAGATION_POLICY_UNKNOWN = "PROPAGATION_POLICY_UNKNOWN"
MEMBER_PROPAGATION_FORBIDDEN = "MEMBER_PROPAGATION_FORBIDDEN"
COMPONENT_PROPAGATION_FORBIDDEN = "COMPONENT_PROPAGATION_FORBIDDEN"
AGGREGATE_RESULT_NOT_SEPARABLE_BY_MEMBER = "AGGREGATE_RESULT_NOT_SEPARABLE_BY_MEMBER"
REGIMEN_RESULT_APPLIES_TO_COMBINATION = "REGIMEN_RESULT_APPLIES_TO_COMBINATION"


class PropagationSchemaError(ValueError):
    """Un record non dichiara la propria propagation policy, o ne dichiara una ignota."""


def validate_policy(value: Any, *, claim_id: str = "") -> str:
    """La policy dichiarata, oppure un errore. Mai un default."""
    label = claim_id or "<record senza claim_id>"
    if value is None:
        raise PropagationSchemaError(
            f"{label}: {PROPAGATION_POLICY_MISSING} — la propagation policy non "
            "ha un default: un record che non la dichiara non e' valido"
        )
    text = str(value)
    if text not in PROPAGATION_POLICIES:
        raise PropagationSchemaError(
            f"{label}: {PROPAGATION_POLICY_UNKNOWN} — {text!r} non e' fra "
            f"{list(PROPAGATION_POLICIES)}"
        )
    return text


def validate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Valida i campi di propagazione di un record serializzato.

    La funzione e' il punto di deserializzazione del modello 1.2: chi legge un
    claim passa di qui, e un record incompleto non arriva mai a essere un
    oggetto. Restituire i valori invece di limitarsi a controllarli evita che
    il chiamante li rilegga dal dizionario con un `.get` e un default.
    """
    claim_id = str(record.get("claim_id") or "")
    claim_type = str(record.get("claim_type") or "")

    missing = [
        field for field in REQUIRED_PROPAGATION_FIELDS if record.get(field) is None
    ]
    if missing:
        raise PropagationSchemaError(
            f"{claim_id or '<record senza claim_id>'}: campi di propagazione "
            f"assenti {missing}"
        )

    policy = validate_policy(record.get("propagation_policy"), claim_id=claim_id)

    required_extra: tuple[str, ...] = ()
    if claim_type == "aggregate_intervention_claim":
        required_extra = AGGREGATE_REQUIRED_FIELDS
    elif claim_type == "regimen_claim":
        required_extra = REGIMEN_REQUIRED_FIELDS

    missing_extra = [field for field in required_extra if record.get(field) is None]
    if missing_extra:
        raise PropagationSchemaError(
            f"{claim_id}: {claim_type} senza {missing_extra}"
        )

    if claim_type in NON_ATOMIC_CLAIM_TYPES and record.get(MEMBER_PROPAGATION_FIELD):
        raise PropagationSchemaError(
            f"{claim_id}: {claim_type} dichiara la propagazione ai membri "
            "consentita; nessuna fase l'ha autorizzata"
        )
    if (
        claim_type == "aggregate_intervention_claim"
        and record.get("permits_member_specific_claims")
    ):
        raise PropagationSchemaError(
            f"{claim_id}: un aggregato non autorizza claim per membro"
        )
    if (
        claim_type == "regimen_claim"
        and record.get("result_applies_to_combination") is not True
    ):
        raise PropagationSchemaError(
            f"{claim_id}: un regime deve dichiarare che il risultato e' della "
            "combinazione"
        )

    payload = {
        "final_evaluable": bool(record["final_evaluable"]),
        "hard_filterable": bool(record["hard_filterable"]),
        "propagation_policy": policy,
    }
    if claim_type in NON_ATOMIC_CLAIM_TYPES:
        payload[MEMBER_PROPAGATION_FIELD] = bool(record[MEMBER_PROPAGATION_FIELD])
    return payload


def propagation_fields_for(claim_type: str) -> dict[str, Any]:
    """I valori che la 1.4 assegna a un tipo, dichiarati e non dedotti.

    Nessun valore viene ricavato dal contenuto del claim. Sono decisioni di
    fase: la propagazione resta `prototype_only` perche' nessuna revisione
    indipendente e' avvenuta, e i due flag di valutabilita' restano falsi
    perche' nessun claim di questo repository e' stato validato per un uso
    finale.
    """
    base = {
        "final_evaluable": False,
        "hard_filterable": False,
        "propagation_policy": PROPAGATION_PROTOTYPE_ONLY,
    }
    if claim_type == "aggregate_intervention_claim":
        return base | {
            MEMBER_PROPAGATION_FIELD: False,
            "permits_member_specific_claims": False,
        }
    if claim_type == "regimen_claim":
        return base | {
            MEMBER_PROPAGATION_FIELD: False,
            "result_applies_to_combination": True,
        }
    return base


def propagation_contract() -> dict[str, Any]:
    """Descrizione serializzabile del contratto, per il manifest della fase."""
    return {
        "aggregate_required_fields": list(AGGREGATE_REQUIRED_FIELDS),
        "allowed_propagation_policies": list(PROPAGATION_POLICIES),
        "contract_version": PROPAGATION_CONTRACT_VERSION,
        "deserialization_default": None,
        "implicit_defaults_permitted": False,
        "model_schema_version": MODEL_SCHEMA_VERSION_V12,
        "reason_codes": {
            "aggregate_member": AGGREGATE_RESULT_NOT_SEPARABLE_BY_MEMBER,
            "member_propagation": MEMBER_PROPAGATION_FORBIDDEN,
            "missing": PROPAGATION_POLICY_MISSING,
            "regimen_component": COMPONENT_PROPAGATION_FORBIDDEN,
            "regimen_result": REGIMEN_RESULT_APPLIES_TO_COMBINATION,
            "unknown": PROPAGATION_POLICY_UNKNOWN,
        },
        "record_without_policy_is_rejected": True,
        "regimen_required_fields": list(REGIMEN_REQUIRED_FIELDS),
        "required_fields": list(REQUIRED_PROPAGATION_FIELDS),
        "rule": (
            "Ogni claim tipizzato dichiara propagation_policy, hard_filterable e "
            "final_evaluable. La deserializzazione rifiuta un record che non li "
            "porta invece di assegnarne uno: un default in lettura farebbe "
            "decidere al parser cio' che deve decidere la revisione."
        ),
    }


__all__ = [
    "AGGREGATE_REQUIRED_FIELDS",
    "MEMBER_PROPAGATION_FIELD",
    "MODEL_SCHEMA_VERSION_V12",
    "NON_ATOMIC_CLAIM_TYPES",
    "PROPAGATION_CONTRACT_VERSION",
    "PROPAGATION_FINAL",
    "PROPAGATION_NONE",
    "PROPAGATION_POLICIES",
    "PROPAGATION_PROTOTYPE_ONLY",
    "REGIMEN_REQUIRED_FIELDS",
    "REQUIRED_PROPAGATION_FIELDS",
    "PropagationSchemaError",
    "propagation_contract",
    "propagation_fields_for",
    "validate_policy",
    "validate_record",
]
