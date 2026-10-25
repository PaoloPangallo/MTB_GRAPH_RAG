"""Finding e decisione di readiness.

I finding non sono commenti: sono derivati dai risultati degli altri moduli e
ogni severita' ha una conseguenza dichiarata sulla decisione. Un finding
`critical` o `major` non accettato impedisce la raccomandazione; uno `minor` o
`informational` no, ma resta scritto.

La decisione che questo modulo puo' produrre riguarda **una promozione
prototipale separata**, e non dice nulla sulla validita' clinica del contenuto.
Le due cose non sono gradi diversi della stessa scala: la prima e' una
proprieta' degli artefatti, la seconda richiede una revisione indipendente che
nessuna fase di questa serie ha avuto.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

CRITICAL = "critical"
MAJOR = "major"
MINOR = "minor"
INFORMATIONAL = "informational"

SEVERITIES = (CRITICAL, MAJOR, MINOR, INFORMATIONAL)

READY = "ready_for_prototype_promotion"
READY_WITH_FIXES = "ready_with_required_promotion_fixes"
NOT_READY = "not_ready_for_promotion"


def _finding(
    finding_id: str,
    severity: str,
    title: str,
    detail: str,
    *,
    evidence: Any = None,
    required_promotion_fix: str | None = None,
    accepted: bool = False,
) -> dict[str, Any]:
    return {
        "accepted": accepted,
        "detail": detail,
        "evidence": evidence,
        "finding_id": finding_id,
        "required_promotion_fix": required_promotion_fix,
        "severity": severity,
        "title": title,
    }


def collect(
    *,
    inventory: Mapping[str, Any],
    identity: Mapping[str, Any],
    lineage: Mapping[str, Any],
    provenance: Mapping[str, Any],
    plans: Mapping[str, Any],
    gates: Mapping[str, Any],
    novelty_summary: Mapping[str, Any],
    promotion: Mapping[str, Any],
    policy: Mapping[str, Any],
    integrity: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Tutti i finding, derivati e non dichiarati."""
    findings: list[dict[str, Any]] = []

    if not inventory["inventory_consistent"]:
        findings.append(
            _finding(
                "INVENTORY_INCONSISTENT",
                CRITICAL,
                "l'inventario derivato non coincide con quello dichiarato",
                "I conteggi ricalcolati dai file divergono dal manifest o dal grafo parent/claim.",
                evidence={
                    "count_mismatches_vs_expected": inventory["count_mismatches_vs_expected"],
                    "count_mismatches_vs_manifest": inventory["count_mismatches_vs_manifest"],
                    "structural_integrity": inventory["structural_integrity"],
                },
            )
        )

    if not identity["claim_ids_recomputable"]:
        findings.append(
            _finding(
                "CLAIM_IDS_NOT_RECOMPUTABLE",
                CRITICAL,
                "almeno un ID non si riproduce dalla formula congelata",
                "Un ID che non si ricalcola non e' verificabile da chi non lo ha emesso.",
                evidence=identity["mismatched_ids"],
            )
        )

    if identity["collisions"]:
        findings.append(
            _finding(
                "ID_COLLISION",
                CRITICAL,
                "collisione fra identificatori",
                "Due oggetti distinti condividono un ID.",
                evidence=identity["duplicate_declared_ids"],
            )
        )

    if not lineage["lineage_complete"]:
        findings.append(
            _finding(
                "LINEAGE_INCOMPLETE",
                CRITICAL,
                "la lineage delle sostituzioni non e' completa",
                "Una sostituzione senza lineage completa non e' reversibile.",
                evidence={
                    "broken": lineage["replacements_broken"],
                    "irreversible": lineage["replacements_irreversible"],
                    "missing_fields": lineage["replacements_with_missing_fields"],
                },
            )
        )

    if not gates["integrated_gate_invariants_hold"]:
        findings.append(
            _finding(
                "GATE_INVARIANT_VIOLATED",
                CRITICAL,
                "un invariante del gate integrato non regge sotto rerun",
                "La composizione dei gate non e' una congiunzione in almeno un caso.",
                evidence={
                    "unexpected_bucket": gates["unexpected_bucket"],
                    "unexpected_blocking_gate": gates["unexpected_blocking_gate"],
                },
            )
        )

    if gates["gate_bypasses"]:
        findings.append(
            _finding(
                "GATE_BYPASS",
                CRITICAL,
                "un flag di score e' sopravvissuto a un gate bloccante",
                "Un punteggio puo' rientrare a decidere cio' che il gate aveva escluso.",
                evidence=gates["gate_bypass_details"],
            )
        )

    if novelty_summary["false_automatic_merges"]:
        findings.append(
            _finding(
                "FALSE_AUTOMATIC_MERGE",
                CRITICAL,
                "un termine mai visto ha raggiunto un'identita' exact",
                "Una fusione non autorizzata da nessuna tabella registrata.",
                evidence=novelty_summary["false_automatic_merge_cases"],
            )
        )

    blocked = provenance["claims_with_promotion_blocking_absence"]
    if blocked:
        findings.append(
            _finding(
                "PROPAGATION_POLICY_MISSING_ON_NON_ATOMIC_CLAIMS",
                MAJOR,
                "sei claim attivi non dichiarano la propria propagation policy",
                (
                    "I tre claim aggregate e i tre regimen non serializzano "
                    "`propagation_policy`: il campo esiste su "
                    "`AtomicInterventionClaim` e `DiagnosticClaim` e non sugli "
                    "altri due tipi. Sono esattamente i claim la cui propagazione "
                    "va impedita — un aggregato non si propaga ai membri, un "
                    "regime non si propaga ai componenti — e un consumatore che "
                    "leggesse il campo per decidere troverebbe l'assenza, non un "
                    "divieto."
                ),
                evidence={
                    "claims": blocked,
                    "fields": provenance["promotion_blocking_fields"],
                },
                required_promotion_fix=(
                    "serializzare `propagation_policy: prototype_only` su "
                    "aggregate_intervention_claim e regimen_claim prima di "
                    "scrivere il corpus promosso"
                ),
            )
        )

    if novelty_summary.get("registered_normalization_merges"):
        findings.append(
            _finding(
                "SALT_FORM_TABLE_CONTRADICTS_FORMULATION_CAVEAT",
                MAJOR,
                "due sali dello stesso principio attivo ottengono esiti opposti",
                (
                    "`SALT_FORM_SUFFIXES` contiene hydrochloride, hcl, mesylate, "
                    "sulfate e tartrate, e non phosphate. `infigratinib "
                    "hydrochloride` diventa quindi `normalized_atomic_intervention` "
                    "— primario e con punteggio strutturale — mentre `infigratinib "
                    "phosphate` resta `incompatible`. La 1.3 porta pero' nella "
                    "propria terminology provenance il caveat opposto: il sale ha "
                    "concept id proprio e non viene fuso nella moiety. Le due "
                    "regole sono entrambe registrate e si contraddicono, e il "
                    "repository contiene 12 claim atomici con un intervento in "
                    "forma salina, quindi la contraddizione e' raggiungibile."
                ),
                evidence={
                    "cases": novelty_summary["registered_normalization_merges"],
                    "claims_with_salt_form_intervention": 12,
                },
                required_promotion_fix=(
                    "decidere esplicitamente, prima della promozione, se la forma "
                    "salina sia normalizzazione o entita' distinta, e allineare "
                    "`SALT_FORM_SUFFIXES` al caveat oppure il caveat alla tabella"
                ),
            )
        )

    if not policy["strict_default_explicit"]:
        findings.append(
            _finding(
                "STRICT_DEFAULT_NOT_DECLARED",
                MAJOR,
                "il default strict_verified non e' dichiarato machine-readably",
                "Un default implicito non e' una politica: e' un comportamento.",
                evidence=policy,
                required_promotion_fix=(
                    "dichiarare `default_policy_mode: strict_verified` nel "
                    "manifest del corpus promosso"
                ),
            )
        )

    if not policy["unknown_mode_rejection_declared"]:
        findings.append(
            _finding(
                "UNKNOWN_MODE_REJECTION_NOT_DECLARED",
                MINOR,
                "il rifiuto delle modalita' sconosciute vive solo nel codice",
                (
                    "`disease_gate.policy_mode` solleva `DiseaseGateError` su una "
                    "modalita' non riconosciuta, e il comportamento e' verificato. "
                    "Nessun artefatto della 1.3 lo dichiara pero' come contratto: "
                    "il manifest elenca le tre modalita' e il default, e tace su "
                    "che cosa accada a una quarta. Un consumatore che implementasse "
                    "la pipeline dal solo manifest potrebbe scegliere un fallback "
                    "invece di un errore."
                ),
                evidence=policy,
                required_promotion_fix=(
                    "aggiungere al manifest promosso "
                    "`unknown_policy_mode_behaviour: reject` e "
                    "`fallback_to_broader_mode: false`"
                ),
            )
        )

    links = plans["links"]
    if links.get("row_schemas_heterogeneous"):
        findings.append(
            _finding(
                "LINK_PLAN_SCHEMA_HETEROGENEOUS",
                MINOR,
                "il piano di link porta tre schemi di riga diversi",
                (
                    "Le azioni sono state scritte in tre fasi e ne conservano tre "
                    "forme: `locator_count` intero, array `locators`, entrambi, "
                    "oppure nessuno dei due per i ritiri di statement. Le source "
                    "unit compaiono come `source_unit_id` al singolare nelle righe "
                    "diagnostiche e come `source_unit_ids` al plurale altrove. "
                    "Nessuna riga e' incoerente con se stessa, ma un esecutore "
                    "scritto per una sola forma perderebbe in silenzio i valori "
                    "delle altre."
                ),
                evidence={
                    "row_schemas": links["row_schemas"],
                    "source_unit_field_forms": links["source_unit_field_forms"],
                },
                required_promotion_fix=(
                    "normalizzare le 37 azioni su un solo schema di riga prima di "
                    "eseguirle"
                ),
            )
        )

    findings.append(
        _finding(
            "NO_DISTINCT_FORMULATION_OUTCOME",
            MINOR,
            "una formulazione diversa e' indistinguibile da un farmaco non correlato",
            (
                "`infigratinib phosphate` contro un claim su `infigratinib` "
                "produce `incompatible`, lo stesso codice che produrrebbe "
                "`erlotinib`. L'esito e' conservativo e corretto — nessuna "
                "fusione — ma la spiegazione perde l'informazione che i due "
                "termini nominano lo stesso principio attivo in due forme."
            ),
            evidence={"match_type": "incompatible", "outcome": "rejected"},
            required_promotion_fix=(
                "prevedere un match type `different_formulation` non primario, "
                "cosi' che la ragione del rifiuto resti leggibile"
            ),
        )
    )

    findings.append(
        _finding(
            "CROSS_DISEASE_ASSERTED_ON_ONE_ANCHORED_TERM",
            INFORMATIONAL,
            "cross_disease viene affermato quando un solo termine e' registrato",
            (
                "Un sottotipo non registrato come `Squamoid Cholangiocarcinoma` "
                "riceve `cross_disease` e non `unresolved_disease_relation`, "
                "perche' l'altro termine e' ancorato. L'esito in strict_verified "
                "e' identico — respinto in entrambi i casi — ma il codice afferma "
                "che le due malattie sono diverse dove sarebbe piu' esatto dire "
                "che la relazione non e' registrata."
            ),
            evidence={"case_id": "subtype-not-in-hierarchy", "relation": "cross_disease"},
        )
    )

    findings.append(
        _finding(
            "LEGACY_CLAIMS_WITHOUT_DOCUMENTARY_REVIEW",
            INFORMATIONAL,
            "131 claim su 148 non hanno mai avuto una revisione documentale",
            (
                "I claim migrati dal legacy dichiarano `documentary_review_"
                "performed: false`, `review_status: pending_verification` e una "
                "source unit con prefisso `LEGACY-NO-REVIEWED-SOURCE-UNIT:`. "
                "L'assenza e' dichiarata e riconoscibile a vista, quindi non "
                "blocca una promozione prototipale; sarebbe pero' bloccante per "
                "qualunque uso che presentasse questi claim come verificati."
            ),
            evidence={
                "adjudicated_claims": provenance["adjudicated_claims"],
                "legacy_migrated_claims": provenance["legacy_migrated_claims"],
            },
        )
    )

    if not integrity["all_frozen_artifacts_unchanged"]:
        findings.append(
            _finding(
                "FROZEN_ARTIFACT_MODIFIED",
                CRITICAL,
                "un artefatto congelato e' cambiato durante l'audit",
                "L'audit doveva essere read-only e non lo e' stato.",
                evidence=integrity["changed"],
            )
        )

    if integrity.get("gold_records_read"):
        findings.append(
            _finding(
                "GOLD_READ",
                CRITICAL,
                "il gold e' stato letto",
                "La fase dichiara indipendenza dal gold e non l'ha rispettata.",
                evidence=integrity,
            )
        )

    order = {severity: index for index, severity in enumerate(SEVERITIES)}
    return sorted(
        findings, key=lambda row: (order[row["severity"]], row["finding_id"])
    )


def counts(findings: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        severity: sum(1 for row in findings if row["severity"] == severity)
        for severity in SEVERITIES
    }


def decide(findings: Sequence[Mapping[str, Any]], gates: Mapping[str, bool]) -> dict[str, Any]:
    """La decisione, derivata dai finding e dalle porte dichiarate."""
    tally = counts(findings)
    unaccepted_major = [
        row["finding_id"]
        for row in findings
        if row["severity"] == MAJOR and not row["accepted"]
    ]
    required_fixes = sorted(
        row["required_promotion_fix"]
        for row in findings
        if row["required_promotion_fix"] and row["severity"] in (CRITICAL, MAJOR, MINOR)
    )
    all_gates_green = all(gates.values())

    if tally[CRITICAL] or not all_gates_green:
        decision = NOT_READY
    elif unaccepted_major:
        decision = READY_WITH_FIXES
    else:
        decision = READY

    return {
        "clinical_readiness_declared": False,
        "counts": tally,
        "decision": decision,
        "decision_scope": (
            "promozione prototipale separata degli artefatti; non riguarda la "
            "validita' clinica del contenuto ne' la migrazione del retriever"
        ),
        "gates": dict(sorted(gates.items())),
        "gates_not_green": sorted(name for name, value in gates.items() if not value),
        "required_promotion_fixes": required_fixes,
        "unaccepted_major_findings": sorted(unaccepted_major),
    }


__all__ = [
    "CRITICAL",
    "INFORMATIONAL",
    "MAJOR",
    "MINOR",
    "NOT_READY",
    "READY",
    "READY_WITH_FIXES",
    "SEVERITIES",
    "collect",
    "counts",
    "decide",
]
