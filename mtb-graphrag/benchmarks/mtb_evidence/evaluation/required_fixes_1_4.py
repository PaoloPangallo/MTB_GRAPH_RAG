"""Correzioni richieste dall'audit pre-promozione, applicate al piano e ai contratti.

Tre finding, tre correzioni, nessuna delle quali cambia una decisione gia'
presa:

**Schema del link plan.** Le 37 azioni sono state scritte in tre fasi e ne
portano tre forme. Nessuna riga e' incoerente con se stessa; e' l'insieme a non
avere uno schema, e un esecutore scritto per una forma perderebbe in silenzio i
valori delle altre. La normalizzazione mappa ogni riga su un unico schema e
conserva i campi originali nella mappa di compatibilita': niente viene perso, e
niente viene reinterpretato.

**Modalita' sconosciuta.** Il gate rifiuta gia' una modalita' che non conosce.
Quello che manca e' la dichiarazione: chi implementasse la pipeline leggendo il
solo manifest non saprebbe che il rifiuto e' obbligatorio, e potrebbe scegliere
un fallback. Il contratto rende la regola leggibile senza cambiarla.

**Regressioni.** Sedici casi che devono continuare a valere dopo le correzioni,
ognuno costruito su un modo in cui la correzione stessa potrebbe rompere
qualcosa che funzionava.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.pipeline.evidence.shadow import disease_gate as DISEASE
from backend.pipeline.evidence.shadow import formulation as FORM
from backend.pipeline.evidence.shadow import integrated_gates_v11 as GATE
from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy import (
    DEFAULT_MODE,
    POLICY_MODES,
)

LINK_PLAN_SCHEMA_VERSION = "qualification_link_plan/1.1"

# Lo schema unico. Sette campi, e ognuno esiste in tutte le righe: quando la
# riga originale non ha nulla da mettere il valore e' `null`, che e' un'assenza
# dichiarata e non una chiave mancante.
LINK_PLAN_FIELDS = (
    "action_type",
    "old_target_id",
    "new_target_id",
    "source_unit_id",
    "locator",
    "reason_code",
    "executed",
)

# I campi che le tre forme precedenti usavano, mappati sul campo unico che li
# assorbe. La mappa e' esplicita perche' la compatibilita' all'indietro possa
# citarla invece di essere dedotta dal codice che l'ha applicata.
LEGACY_FIELD_MAP = {
    "claim_id": "new_target_id",
    "legacy_statement_id": "old_target_id",
    "locator_count": "locator",
    "locators": "locator",
    "replaced_claim_id": "old_target_id",
    "replacement_claim_id": "new_target_id",
    "replaces_claim_id": "old_target_id",
    "source_unit_id": "source_unit_id",
    "source_unit_ids": "source_unit_id",
}


class LinkPlanSchemaError(RuntimeError):
    """Un'azione del piano non e' rappresentabile nello schema unico."""


def _locator(action: Mapping[str, Any]) -> dict[str, Any] | None:
    """Il locator in forma unica: elenco piu' conteggio, o assenza dichiarata.

    Le due forme precedenti — un intero e un array — non vengono sommate ne'
    scelte per precedenza: quando ci sono entrambe devono coincidere, e la
    divergenza sarebbe un difetto del piano e non una cosa da appianare qui.
    """
    array = action.get("locators")
    count = action.get("locator_count")
    if array is None and count is None:
        return None
    if array is not None and count is not None and len(array) != int(count):
        raise LinkPlanSchemaError(
            f"{action.get('plan_id')}: locator_count {count} non coincide con "
            f"{len(array)} locator elencati"
        )
    entries = list(array) if array is not None else []
    return {
        "count": len(entries) if array is not None else int(count),
        "entries": entries,
        "entries_enumerated": array is not None,
    }


def _source_unit(action: Mapping[str, Any]) -> list[str]:
    """Le source unit dell'azione, sempre come lista.

    Il campo conserva il nome singolare dello schema richiesto, ma il valore e'
    sempre una lista — anche quando l'elemento e' uno solo, anche quando non ce
    n'e' nessuno. Un'azione del piano ne porta legittimamente due, la prima
    linea e il rechallenge dello stesso paziente, e sceglierne una sarebbe la
    perdita silenziosa che questa normalizzazione esiste per impedire. Un tipo
    che cambia con il numero di elementi riporterebbe l'eterogeneita' dentro il
    campo che doveva eliminarla.
    """
    plural = tuple(action.get("source_unit_ids") or ())
    singular = action.get("source_unit_id")
    return sorted(
        {str(item) for item in plural} | ({str(singular)} if singular else set())
    )


def _targets(action: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Vecchio e nuovo bersaglio, distinti per tipo di azione.

    Un ritiro ha un vecchio bersaglio e puo' avere il nuovo che lo sostituisce;
    una creazione ha il nuovo e puo' avere il vecchio che sostituisce. Le due
    cose non vanno collassate in un solo campo `claim_id`, che e' esattamente
    l'ambiguita' che rende il piano difficile da eseguire.
    """
    action_type = action["action"]
    if action_type == "retire_statement_link":
        return str(action.get("legacy_statement_id") or ""), None
    if action_type == "retire_claim_link":
        return (
            str(action.get("claim_id") or ""),
            str(action.get("replacement_claim_id") or "") or None,
        )
    if action_type == "create_claim_link":
        return (
            str(action.get("replaces_claim_id") or "") or None,
            str(action.get("claim_id") or ""),
        )
    raise LinkPlanSchemaError(f"azione sconosciuta: {action_type!r}")


def normalize_link_plan(actions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Le 37 azioni su un solo schema, senza cambiarne il significato."""
    rows: list[dict[str, Any]] = []
    for action in actions:
        old_target, new_target = _targets(action)
        rows.append(
            {
                "action_type": action["action"],
                "executed": bool(action.get("executed")),
                "legacy_fields_present": sorted(
                    key for key in LEGACY_FIELD_MAP if key in action
                ),
                "locator": _locator(action),
                "new_target_id": new_target,
                "old_target_id": old_target,
                "plan_id": action["plan_id"],
                "reason_code": action.get("reason_code"),
                "schema_version": LINK_PLAN_SCHEMA_VERSION,
                "source_unit_id": _source_unit(action),
            }
        )
    return sorted(rows, key=lambda row: row["plan_id"])


def link_plan_backward_compatibility(
    original: Sequence[Mapping[str, Any]], normalized: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Cosa e' stato mappato dove, e cosa non e' cambiato."""
    legacy_keys = sorted({key for action in original for key in action if key in LEGACY_FIELD_MAP})
    return {
        "actions_after": len(normalized),
        "actions_before": len(original),
        "actions_executed": sum(1 for row in normalized if row["executed"]),
        "field_map": {key: LEGACY_FIELD_MAP[key] for key in legacy_keys},
        "legacy_fields_retained_in_original_artifact": True,
        "meaning_changed": False,
        "plan_ids_unchanged": sorted(row["plan_id"] for row in normalized)
        == sorted(str(action["plan_id"]) for action in original),
        "schema_version": LINK_PLAN_SCHEMA_VERSION,
        "source_unit_id_is_always_a_list": True,
        "source_unit_id_note": (
            "Il campo conserva il nome singolare dello schema richiesto e ha "
            "sempre valore di lista. Un'azione ne porta legittimamente due "
            "(prima linea e rechallenge dello stesso paziente): sceglierne una "
            "sarebbe la perdita silenziosa che la normalizzazione impedisce."
        ),
        "unified_fields": list(LINK_PLAN_FIELDS),
    }


# --- contratto delle modalita' ------------------------------------------------


def policy_mode_contract() -> dict[str, Any]:
    """La regola sulle modalita', dichiarata invece che soltanto implementata."""
    try:
        DISEASE.policy_mode({"disease_policy_mode": "definitely_not_a_mode"})
        rejects = False
    except DISEASE.DiseaseGateError:
        rejects = True
    return {
        "allowed_policy_modes": list(POLICY_MODES),
        "default_policy_mode": DEFAULT_MODE,
        "error_type": "DiseaseGateError",
        "fallback_to_audit_all": False,
        "fallback_to_broader_mode": False,
        "fallback_to_ontology_aware_warning": False,
        "measured_behaviour_rejects_unknown_mode": rejects,
        "silent_fallback_permitted": False,
        "unknown_policy_mode_behavior": "reject",
        "unspecified_mode_resolves_to": DEFAULT_MODE,
    }


# --- regressioni --------------------------------------------------------------


def _query(claim: Mapping[str, Any], drug: str | None = None) -> dict[str, Any]:
    query = {
        "query_id": "regression",
        "query_domain": "therapeutic_evidence_query",
        "biomarker": claim["biomarker"],
        "disease": claim["disease_scope"],
        "direction": claim["direction"],
        "polarity": claim["polarity"],
    }
    if drug is not None:
        query["interventions"] = [drug]
    return query


ARBITRARILY_HIGH_SCORE = 10**9


def formulation_cases() -> tuple[dict[str, Any], ...]:
    """I casi di forma, con l'esito atteso derivato dal contratto e non dal codice."""
    return (
        {
            "case_id": "exact-form-stays-primary",
            "claim_literal": "infigratinib",
            "expected_relation": FORM.EXACT_INTERVENTION_FORM,
            "query_literal": "infigratinib",
        },
        {
            "case_id": "case-and-space-variation-stays-primary",
            "claim_literal": "infigratinib",
            "expected_relation": FORM.NORMALIZED_EXACT_INTERVENTION_FORM,
            "query_literal": "  INFIGRATINIB  ",
        },
        {
            "case_id": "verified-salt-is-warning-not-primary",
            "claim_literal": "infigratinib",
            "expected_relation": FORM.VERIFIED_SALT_OF_ACTIVE_MOIETY,
            "query_literal": "infigratinib phosphate",
        },
        {
            "case_id": "verified-salt-symmetric",
            "claim_literal": "infigratinib phosphate",
            "expected_relation": FORM.VERIFIED_SALT_OF_ACTIVE_MOIETY,
            "query_literal": "infigratinib",
        },
        {
            "case_id": "unregistered-salt-is-unresolved",
            "claim_literal": "infigratinib",
            "expected_relation": FORM.UNRESOLVED_FORMULATION_RELATION,
            "query_literal": "infigratinib hydrochloride",
        },
        {
            "case_id": "two-different-salts-not-fused",
            "claim_literal": "infigratinib hydrochloride",
            "expected_relation": FORM.UNRESOLVED_FORMULATION_RELATION,
            "query_literal": "infigratinib phosphate",
        },
        {
            "case_id": "moiety-against-salt-in-repository",
            "claim_literal": "alectinib hydrochloride",
            "expected_relation": FORM.UNRESOLVED_FORMULATION_RELATION,
            "query_literal": "alectinib",
        },
        {
            "case_id": "unknown-salt-is-unresolved",
            "claim_literal": "alectinib hydrochloride",
            "expected_relation": FORM.UNRESOLVED_FORMULATION_RELATION,
            "query_literal": "alectinib besylate",
        },
        {
            "case_id": "unregistered-suffix-no-longer-invisible",
            "claim_literal": "neratinib maleate",
            "expected_relation": FORM.UNRESOLVED_FORMULATION_RELATION,
            "query_literal": "neratinib",
        },
        {
            "case_id": "substring-is-not-a-form-token",
            "claim_literal": "infigratinib",
            "expected_relation": FORM.INCOMPATIBLE_ACTIVE_MOIETY,
            "query_literal": "phosphatermine",
        },
        {
            "case_id": "unrelated-drug-stays-rejected",
            "claim_literal": "infigratinib",
            "expected_relation": FORM.INCOMPATIBLE_ACTIVE_MOIETY,
            "query_literal": "erlotinib",
        },
        {
            "case_id": "salt-form-exact-query-still-primary",
            "claim_literal": "alectinib hydrochloride",
            "expected_relation": FORM.EXACT_INTERVENTION_FORM,
            "query_literal": "alectinib hydrochloride",
        },
    )


def formulation_simulation() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in formulation_cases():
        relation = FORM.resolve(case["query_literal"], case["claim_literal"])
        rows.append(
            {
                "authoritative_source": relation.authoritative_source or None,
                "bucket": relation.bucket,
                "case_id": case["case_id"],
                "claim_form": relation.claim_form,
                "claim_literal": case["claim_literal"],
                "expected_relation": case["expected_relation"],
                "is_exact_form": relation.is_exact_form,
                "primary_candidate_eligible": relation.primary_candidate_eligible,
                "query_form": relation.query_form,
                "query_literal": case["query_literal"],
                "reason_codes": list(relation.reason_codes),
                "relation_as_expected": relation.relation_type
                == case["expected_relation"],
                "relation_status": relation.relation_status,
                "relation_type": relation.relation_type,
                "structural_score_eligible": relation.structural_score_eligible,
                "warning_codes": list(relation.warning_codes),
            }
        )
    return sorted(rows, key=lambda row: row["case_id"])


def gate_regression(objects: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Regressioni sul gate integrato 1.1, con l'invariante verificato sul posto."""
    rows: list[dict[str, Any]] = []
    cases = (
        ("atomic-exact-form", "atomic_salt", "alectinib hydrochloride", True),
        ("atomic-moiety-vs-salt", "atomic_salt", "alectinib", False),
        ("infigratinib-exact", "atomic_infigratinib", "infigratinib", True),
        ("infigratinib-verified-salt", "atomic_infigratinib", "infigratinib phosphate", False),
        ("infigratinib-unregistered-salt", "atomic_infigratinib", "infigratinib hydrochloride", False),
        ("infigratinib-pending-alias", "atomic_infigratinib", "BGJ398", False),
        ("regimen-component", "regimen", None, False),
        ("aggregate-member-literal", "aggregate", "BGJ398", False),
    )
    for case_id, key, drug, expect_primary in cases:
        obj, record = objects[key]
        query_drug = drug
        if key == "regimen" and drug is None:
            query_drug = record["regimen_components"][0]
        for mode in DISEASE.MODES:
            result = GATE.evaluate(_query(record, query_drug), obj, mode=mode)
            bypass = None
            try:
                GATE.check_no_score_survives_a_blocking_gate(
                    result, ARBITRARILY_HIGH_SCORE
                )
            except GATE.IntegratedGateV11Error as error:  # pragma: no cover
                bypass = str(error)
            formulation = result.formulation_match_result
            rows.append(
                {
                    "blocking_gates": list(result.blocking_gates),
                    "case_id": case_id,
                    "claim_id": result.claim_id,
                    "claim_type": result.claim_type,
                    "expected_primary": expect_primary,
                    "final_bucket": result.final_bucket,
                    "formulation_relation": formulation.get("relation_type"),
                    "gate_bypass": bypass,
                    "gate_version": GATE.GATE_VERSION,
                    "hypothetical_score": ARBITRARILY_HIGH_SCORE,
                    "policy_mode": mode,
                    "primary_as_expected": result.primary_candidate_eligible
                    == expect_primary,
                    "primary_candidate_eligible": result.primary_candidate_eligible,
                    "qualified_score_eligible": result.qualified_score_eligible,
                    "query_intervention": query_drug,
                    "structural_score_eligible": result.structural_score_eligible,
                }
            )
    return sorted(rows, key=lambda row: (row["case_id"], row["policy_mode"]))


__all__ = [
    "ARBITRARILY_HIGH_SCORE",
    "LEGACY_FIELD_MAP",
    "LINK_PLAN_FIELDS",
    "LINK_PLAN_SCHEMA_VERSION",
    "LinkPlanSchemaError",
    "formulation_cases",
    "formulation_simulation",
    "gate_regression",
    "link_plan_backward_compatibility",
    "normalize_link_plan",
    "policy_mode_contract",
]
