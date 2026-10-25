"""Completezza della provenance, classificata invece che conteggiata.

Un campo assente non e' sempre un difetto. La 1.3 contiene due popolazioni con
storie diverse, e trattarle allo stesso modo produrrebbe o 131 falsi allarmi o
una tolleranza che nasconde i casi veri:

**Claim adjudicati** (17). Hanno una revisione documentale: locator, source id,
unita' di fonte revisionata. Da loro ci si aspetta tutto.

**Claim migrati dal legacy** (131). Non hanno mai avuto una revisione
documentale, e dichiararlo e' cio' che li rende leggibili: `documentary_review_
performed: false`, `identity_source_unit_token` con prefisso esplicito,
`review_status: pending_verification`. Chiedere loro un locator significherebbe
chiedere di inventarlo.

Le tre classi di esito sono quindi:

    promotion_blocking              manca cio' che serve a promuovere
    warning_only                    manca, ma il record dice perche'
    expected_for_legacy_migrated_claim  assente per costruzione, dichiarato

Nessun campo viene inventato: quando manca, l'audit lo scrive come mancante.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

LEGACY_ORIGIN = "legacy_single_statement"
LEGACY_SOURCE_UNIT_PREFIX = "LEGACY-NO-REVIEWED-SOURCE-UNIT:"

PROMOTION_BLOCKING = "promotion_blocking"
WARNING_ONLY = "warning_only"
EXPECTED_LEGACY = "expected_for_legacy_migrated_claim"

# I requisiti sono dichiarati per campo, non per claim, cosi' che la regola sia
# leggibile tutta insieme e non sparsa in una catena di `if`.
#
#   always      richiesto da ogni claim attivo
#   adjudicated richiesto dai soli claim con revisione documentale
#   applicable  richiesto solo se il claim e' toccato da quella decisione
REQUIREMENTS = {
    "adapter_lineage": "always",
    "claim_domain_provenance": "always",
    "disease_relation_provenance": "applicable",
    "graph_evidence_id": "always",
    "locator_or_explicit_limitation": "always",
    "parent_id": "always",
    "propagation_policy": "always",
    "review_status": "always",
    "source_id": "adjudicated",
    "source_unit": "always",
    "terminology_provenance": "applicable",
}


def _has_locator(claim: Mapping[str, Any]) -> bool:
    return bool(claim.get("locators"))


def _explicit_limitation(claim: Mapping[str, Any]) -> str | None:
    """Il modo, dichiarato, in cui il claim ammette di non avere un locator."""
    if claim.get("limitation_codes"):
        return "limitation_codes"
    provenance = claim.get("provenance") or {}
    if provenance.get("documentary_review_performed") is False:
        return "documentary_review_performed=false"
    if str(provenance.get("identity_source_unit_token") or "").startswith(
        LEGACY_SOURCE_UNIT_PREFIX
    ):
        return "identity_source_unit_token=legacy"
    if claim.get("documentary_revalidation_completed") is False:
        return "documentary_revalidation_completed=false"
    return None


def _field_states(claim: Mapping[str, Any]) -> dict[str, Any]:
    provenance = claim.get("provenance") or {}
    locators = claim.get("locators") or ()
    limitation = _explicit_limitation(claim)
    return {
        "adapter_lineage": provenance.get("adapter_version")
        or provenance.get("adjudication_version"),
        "claim_domain_provenance": claim.get("claim_domain"),
        "disease_relation_provenance": (provenance.get("scope_narrowing") or None)
        and "scope_narrowing",
        "graph_evidence_id": claim.get("graph_evidence_id"),
        "locator_or_explicit_limitation": (
            f"locators={len(locators)}" if locators else limitation
        ),
        "parent_id": claim.get("parent_id"),
        "propagation_policy": claim.get("propagation_policy"),
        "review_status": claim.get("review_status"),
        "source_id": provenance.get("source_id")
        or next(
            (item.get("source_id") for item in locators if item.get("source_id")), None
        ),
        "source_unit": (claim.get("source_unit_ids") or [None])[0]
        or provenance.get("identity_source_unit_token"),
        "terminology_provenance": (
            "terminology_provenance"
            if claim.get("terminology_provenance")
            else ("terminology_canonicalization" if provenance.get("terminology_canonicalization") else None)
        ),
    }


def _applicable_fields(claim: Mapping[str, Any]) -> set[str]:
    """I campi condizionali che questo claim deve davvero portare."""
    applicable: set[str] = set()
    provenance = claim.get("provenance") or {}
    if claim.get("terminology_provenance") or provenance.get(
        "terminology_canonicalization"
    ):
        applicable.add("terminology_provenance")
    if provenance.get("scope_narrowing"):
        applicable.add("disease_relation_provenance")
    return applicable


def classify_absence(claim: Mapping[str, Any], field: str) -> str:
    """Come va letta l'assenza di un campo su questo claim."""
    legacy = claim.get("migration_origin") == LEGACY_ORIGIN
    if field == "source_id" and legacy:
        return EXPECTED_LEGACY
    if field == "locator_or_explicit_limitation" and legacy:
        return EXPECTED_LEGACY
    if field == "propagation_policy":
        # La policy di propagazione decide se un risultato possa uscire dal
        # prototipo. Un claim che non la dichiara la fa decidere al lettore, e
        # per aggregati e regimi il lettore sbagliato la dedurrebbe dai membri.
        return PROMOTION_BLOCKING
    if field in ("parent_id", "graph_evidence_id", "source_unit", "adapter_lineage"):
        return PROMOTION_BLOCKING
    return WARNING_ONLY


def claim_rows(repository: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for claim in repository["claims"]:
        states = _field_states(claim)
        applicable = _applicable_fields(claim)
        legacy = claim.get("migration_origin") == LEGACY_ORIGIN
        missing: list[dict[str, str]] = []
        for field, requirement in sorted(REQUIREMENTS.items()):
            if requirement == "applicable" and field not in applicable:
                continue
            if requirement == "adjudicated" and legacy:
                if states[field]:
                    continue
                missing.append(
                    {"classification": EXPECTED_LEGACY, "field": field}
                )
                continue
            if states[field]:
                continue
            missing.append(
                {"classification": classify_absence(claim, field), "field": field}
            )
        rows.append(
            {
                "claim_domain": claim["claim_domain"],
                "claim_id": claim["claim_id"],
                "claim_type": claim["claim_type"],
                "graph_evidence_id": claim["graph_evidence_id"],
                "has_locator": _has_locator(claim),
                "is_legacy_migrated": legacy,
                "limitation_form": _explicit_limitation(claim),
                "migration_origin": claim.get("migration_origin"),
                "missing_fields": missing,
                "present_fields": {
                    field: bool(value) for field, value in sorted(states.items())
                },
                "promotion_blocking_absences": sorted(
                    item["field"]
                    for item in missing
                    if item["classification"] == PROMOTION_BLOCKING
                ),
                "review_status": claim.get("review_status"),
            }
        )
    return sorted(rows, key=lambda row: row["claim_id"])


def audit(repository: Mapping[str, Any]) -> dict[str, Any]:
    rows = claim_rows(repository)
    by_classification: Counter[str] = Counter()
    by_field: Counter[str] = Counter()
    for row in rows:
        for item in row["missing_fields"]:
            by_classification[item["classification"]] += 1
            by_field[f"{item['field']}:{item['classification']}"] += 1

    blocking = sorted(
        {
            item["field"]
            for row in rows
            for item in row["missing_fields"]
            if item["classification"] == PROMOTION_BLOCKING
        }
    )
    blocked_claims = sorted(
        row["claim_id"] for row in rows if row["promotion_blocking_absences"]
    )
    return {
        "absences_by_classification": dict(sorted(by_classification.items())),
        "absences_by_field": dict(sorted(by_field.items())),
        "adjudicated_claims": sum(1 for row in rows if not row["is_legacy_migrated"]),
        "claims_audited": len(rows),
        "claims_with_locator": sum(1 for row in rows if row["has_locator"]),
        "claims_with_promotion_blocking_absence": blocked_claims,
        "legacy_migrated_claims": sum(1 for row in rows if row["is_legacy_migrated"]),
        "limitation_forms": dict(
            sorted(Counter(row["limitation_form"] for row in rows).items(), key=str)
        ),
        "promotion_blocking_fields": blocking,
        "provenance_sufficient_for_prototype": not blocked_claims,
        "requirements": dict(sorted(REQUIREMENTS.items())),
    }


__all__ = [
    "EXPECTED_LEGACY",
    "PROMOTION_BLOCKING",
    "REQUIREMENTS",
    "WARNING_ONLY",
    "audit",
    "claim_rows",
    "classify_absence",
]
