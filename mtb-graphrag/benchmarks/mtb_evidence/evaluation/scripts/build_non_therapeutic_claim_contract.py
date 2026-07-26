"""Costruisce il contratto dei claim non terapeutici, l'erratum e la simulazione.

Audita i tre record che la migrazione shadow ha lasciato senza claim, definisce
i tipi diagnostico e prognostico, emette un erratum versionato per le due
incoerenze degli artefatti congelati e simula l'inventario emendato.

Non tocca il corpus operativo, l'adapter, il retriever, lo scoring o il
repository shadow gia' generato. Non legge il gold. Non calcola metriche. Non
impone un totale atteso: il conteggio esce dall'audit.

Deterministico: output ordinati per chiave dichiarata; `--reverse-input-order`
inverte gli ingressi e il risultato deve restare identico.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    canonical_dumps,
    canonical_jsonl,
    sha256_text,
)
from benchmarks.mtb_evidence.evaluation.non_therapeutic_claim_contract import (
    ALL_CLAIM_TYPES,
    AMENDED_SPEC_VERSION,
    AUDIT_VERDICTS,
    CLAIM_ID_FORMULA_VERSION,
    CONTRACT_VERSION,
    DIAGNOSTIC_CLAIM_CONTRACT,
    ERRATUM_VERSION,
    EVIDENCE_CLAIM_HIERARCHY,
    METRIC_SCOPE_CONTRACT,
    NON_CLAIM_OBJECT_KINDS,
    NON_THERAPEUTIC_CLAIM_TYPES,
    PREDICTIVE_CLAIM_ASSESSMENT,
    PROGNOSTIC_CLAIM_CONTRACT,
    QUERY_TYPES,
    QUERY_TYPE_PRIMARY_ELIGIBILITY,
    REJECTION_REASON_CODES,
    REQUIRED_FOR_ANY_APPROVED_CLAIM,
    SCORE_ELIGIBILITY_CONTRACT,
    THERAPEUTIC_CLAIM_TYPES,
    UNTYPED_QUERY_SECTIONING,
    canonical_subject,
    check_materialisation_preconditions,
    claim_id,
    claims_for_verdict,
    identity_payload,
    primary_eligible,
    rejection_reason,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
ADJ = V3 / "multi_intervention_adjudication"
SHADOW = V3 / "typed_claim_shadow_migration"
DATA = REPO_ROOT / "benchmarks/mtb_evidence/evaluation/data"
DEFAULT_OUTPUT = V3 / "non_therapeutic_claim_contract_and_erratum"

AUDITED_RECORDS = ("evidence:347", "evidence:1846", "evidence:1847")

# Artefatti congelati che l'erratum corregge senza riscriverli.
ORIGINAL_ARTIFACTS = (
    "benchmarks/mtb_evidence/v3/multi_intervention_adjudication/migration_specification.json",
    "benchmarks/mtb_evidence/v3/multi_intervention_adjudication/ADAPTER_MIGRATION_SPECIFICATION.md",
    "benchmarks/mtb_evidence/v3/multi_intervention_adjudication/post_adjudication_schema_simulation.json",
    "benchmarks/mtb_evidence/v3/multi_intervention_adjudication/adjudication_manifest.json",
)

CORRECTION_COMMIT_PLACEHOLDER = "arch/v3-non-therapeutic-claim-contract-and-erratum"
CORRECTION_DATE = "2026-07-26"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_file(path: Path) -> str:
    return sha256_text(path.read_text(encoding="utf-8"))


def build(reverse: bool = False) -> dict[str, str]:
    audit = load_jsonl(DATA / "non_therapeutic_audit_v1.jsonl")
    shadow_claims = load_jsonl(SHADOW / "typed_claims.jsonl")
    shadow_parents = load_jsonl(SHADOW / "graph_evidence_parents.jsonl")
    shadow_unsupported = load_jsonl(SHADOW / "unsupported_associations.jsonl")
    shadow_unresolved = load_jsonl(SHADOW / "unresolved_associations.jsonl")
    shadow_deprecations = load_jsonl(SHADOW / "legacy_statement_deprecation_map.jsonl")

    if reverse:
        audit = list(reversed(audit))
        shadow_claims = list(reversed(shadow_claims))
        shadow_parents = list(reversed(shadow_parents))
        shadow_unsupported = list(reversed(shadow_unsupported))
        shadow_unresolved = list(reversed(shadow_unresolved))
        shadow_deprecations = list(reversed(shadow_deprecations))

    simulated = simulate_claims(audit)

    artifacts: dict[str, str] = {}
    artifacts["audit_scope.json"] = canonical_dumps(_audit_scope(audit))
    artifacts["non_therapeutic_record_audit.jsonl"] = canonical_jsonl(
        audit, key="graph_evidence_id"
    )
    artifacts["diagnostic_claim_contract.json"] = canonical_dumps(DIAGNOSTIC_CLAIM_CONTRACT)
    artifacts["prognostic_claim_contract.json"] = canonical_dumps(PROGNOSTIC_CLAIM_CONTRACT)
    artifacts["evidence_claim_hierarchy.json"] = canonical_dumps(_hierarchy())
    artifacts["non_therapeutic_query_contract.json"] = canonical_dumps(_query_contract())
    artifacts["non_therapeutic_score_eligibility.json"] = canonical_dumps(
        SCORE_ELIGIBILITY_CONTRACT
    )
    artifacts["metric_scope_contract.json"] = canonical_dumps(METRIC_SCOPE_CONTRACT)
    artifacts["claim_id_simulation.jsonl"] = canonical_jsonl(simulated, key="claim_id")

    inventory = _amended_inventory(
        audit,
        simulated,
        shadow_claims,
        shadow_parents,
        shadow_unsupported,
        shadow_unresolved,
        shadow_deprecations,
    )
    artifacts["amended_shadow_simulation.json"] = canonical_dumps(inventory)
    artifacts["adjudication_erratum.json"] = canonical_dumps(_erratum(inventory))
    artifacts["migration_specification_amended.json"] = canonical_dumps(
        _amended_specification(inventory)
    )
    artifacts["artifact_version_lineage.json"] = canonical_dumps(_lineage())
    artifacts["review_manifest.json"] = canonical_dumps(_manifest(artifacts, inventory, audit))
    return artifacts


# ── audit ─────────────────────────────────────────────────────────────────────


def _audit_scope(audit: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "scope": (
            "I tre graph evidence ID che la migrazione shadow ha lasciato senza "
            "claim perche' la tassonomia aveva soltanto tipi di intervento."
        ),
        "records_in_scope": list(AUDITED_RECORDS),
        "records_audited": sorted(r["graph_evidence_id"] for r in audit),
        "scope_is_complete": sorted(r["graph_evidence_id"] for r in audit)
        == sorted(AUDITED_RECORDS),
        "selection_criterion": (
            "direction non terapeutica (diagnostic o prognostic) e nessun intervento "
            "ne' nello statement ne' nelle righe V2"
        ),
        "materials_used": [
            "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
            "benchmarks/mtb_evidence/v3/qualification_corpus_v2/active_source_profile_units.jsonl",
            "benchmarks/mtb_evidence/v3/multi_intervention_adapter_review/intervention_lineage.jsonl",
            "benchmarks/mtb_evidence/v3/priority_curation/source_abstract_cache.jsonl",
        ],
        "gold_used": False,
        "network_used": False,
        "full_text_used": False,
        "abstract_only": True,
        "verdict_vocabulary": list(AUDIT_VERDICTS),
        "required_for_any_approved_claim": list(REQUIRED_FOR_ANY_APPROVED_CLAIM),
        "verdicts": {
            record["graph_evidence_id"]: record["verdict"]
            for record in sorted(audit, key=lambda r: r["graph_evidence_id"])
        },
        "interventions_invented": 0,
    }


def _hierarchy() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "hierarchy": EVIDENCE_CLAIM_HIERARCHY,
        "therapeutic_claim_types": list(THERAPEUTIC_CLAIM_TYPES),
        "non_therapeutic_claim_types": list(NON_THERAPEUTIC_CLAIM_TYPES),
        "non_claim_object_kinds": list(NON_CLAIM_OBJECT_KINDS),
        "graph_evidence_record_role": "provenance_container",
        "graph_evidence_record_is_claim": False,
        "associations_are_evidence_claims": False,
        "associations_note": (
            "UnsupportedAssociation e UnresolvedAssociation restano oggetti "
            "auditabili e non entrano nella gerarchia di EvidenceClaim: non sono "
            "claim positivi meno buoni, sono cose che non affermano."
        ),
        "predictive_claim": PREDICTIVE_CLAIM_ASSESSMENT,
    }


def _query_contract() -> dict[str, Any]:
    matrix = {}
    for query_type in QUERY_TYPES:
        matrix[query_type] = {
            claim_type: {
                "primary_eligible": primary_eligible(query_type, claim_type),
                "rejection_reason_code": rejection_reason(query_type, claim_type),
            }
            for claim_type in ALL_CLAIM_TYPES
        }
    return {
        "contract_version": CONTRACT_VERSION,
        "query_types": list(QUERY_TYPES),
        "primary_eligibility_matrix": matrix,
        "untyped_query_sectioning": UNTYPED_QUERY_SECTIONING,
        "rejection_reason_codes": list(REJECTION_REASON_CODES),
        "implemented_operationally": False,
        "invariants": [
            "diagnostic_evidence_query non recupera claim terapeutici come diagnostici",
            "prognostic_evidence_query non recupera claim predittivi o terapeutici come equivalenti",
            "untyped_evidence_query mantiene i tipi in sezioni e bucket distinti",
        ],
    }


# ── simulazione dei claim ─────────────────────────────────────────────────────


def simulate_claims(audit: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """I claim non terapeutici che l'audit approva. Simulati, non materializzati."""
    rows: list[dict[str, Any]] = []
    for record in sorted(audit, key=lambda r: r["graph_evidence_id"]):
        for claim_type in claims_for_verdict(record["verdict"]):
            subject = record.get("diagnostic_subject") or record.get("prognostic_subject")
            interpretation = (
                record.get("diagnostic_interpretation")
                if claim_type == "diagnostic_claim"
                else record.get("prognostic_direction")
            )
            candidate = {
                "source_id": record["source_id"],
                "subject": subject,
                "disease_scope": record["disease"],
                "direction_or_interpretation": interpretation,
                "source_unit_id": record["profile_unit_id"],
                "locators": record["locators"],
                "polarity": record["assertion_polarity"],
                "provenance": record["audit_id"],
            }
            missing = check_materialisation_preconditions(candidate)
            if missing:
                raise RuntimeError(
                    f"{record['graph_evidence_id']}: claim approvato ma incompleto, "
                    f"mancano {missing}"
                )
            identity = {
                "graph_evidence_id": record["graph_evidence_id"],
                "claim_type": claim_type,
                "canonical_subject": canonical_subject(subject),
                "biomarker": record["biomarker"],
                "disease_scope": record["disease"],
                "direction_or_interpretation": interpretation,
                "polarity": record["assertion_polarity"],
                "source_unit_id": record["profile_unit_id"],
            }
            rows.append(
                {
                    "claim_id": claim_id(**identity),
                    "claim_identity_payload": identity_payload(**identity),
                    "claim_identity_sha256": hashlib.sha256(
                        identity_payload(**identity).encode("utf-8")
                    ).hexdigest(),
                    "formula_version": CLAIM_ID_FORMULA_VERSION,
                    "graph_evidence_id": record["graph_evidence_id"],
                    "parent_graph_evidence_id": record["graph_evidence_id"],
                    "legacy_statement_id": record["legacy_statement_id"],
                    "claim_type": claim_type,
                    "canonical_subject": canonical_subject(subject),
                    "diagnostic_subject": record.get("diagnostic_subject"),
                    "biomarker": record["biomarker"],
                    "disease_scope": record["disease"],
                    "diagnostic_interpretation": record.get("diagnostic_interpretation"),
                    "assay_or_method": record.get("assay_or_method"),
                    "population_or_sample_scope": record.get("population_or_sample_scope"),
                    "direction": record["graph_direction"],
                    "polarity": record["assertion_polarity"],
                    "source_id": record["source_id"],
                    "source_unit_ids": [record["profile_unit_id"]],
                    "locators": record["locators"],
                    "review_status": "audited_not_materialised",
                    "intervention_field_present": False,
                    "materialised_in_shadow_repository": False,
                    "prevalence_attributable_to_specific_fusion": record.get(
                        "prevalence_attributable_to_specific_fusion"
                    ),
                    "clinical_validation_asserted": record.get("clinical_validation_asserted"),
                    "gold_used": False,
                }
            )
    return rows


# ── inventario emendato ───────────────────────────────────────────────────────


def _amended_inventory(
    audit: Sequence[Mapping[str, Any]],
    simulated: Sequence[Mapping[str, Any]],
    shadow_claims: Sequence[Mapping[str, Any]],
    shadow_parents: Sequence[Mapping[str, Any]],
    shadow_unsupported: Sequence[Mapping[str, Any]],
    shadow_unresolved: Sequence[Mapping[str, Any]],
    shadow_deprecations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    therapeutic = Counter(c["claim_type"] for c in shadow_claims)
    non_therapeutic = Counter(c["claim_type"] for c in simulated)

    therapeutic_total = sum(therapeutic[t] for t in THERAPEUTIC_CLAIM_TYPES)
    non_therapeutic_total = sum(non_therapeutic[t] for t in NON_THERAPEUTIC_CLAIM_TYPES)

    gained = {c["graph_evidence_id"] for c in simulated}
    previously_without = {
        p["graph_evidence_id"] for p in shadow_parents if not p["child_claim_ids"]
    }
    still_without = sorted(previously_without - gained)

    previously_deprecated = [d for d in shadow_deprecations if d["is_deprecated"]]
    newly_replaced = sorted(gained)

    return {
        "simulation_version": AMENDED_SPEC_VERSION,
        "promoted": False,
        "materialised_in_shadow_repository": False,
        "parents": len(shadow_parents),
        "therapeutic_claims": {
            "total": therapeutic_total,
            "atomic_intervention_claim": therapeutic["atomic_intervention_claim"],
            "aggregate_intervention_claim": therapeutic["aggregate_intervention_claim"],
            "regimen_claim": therapeutic["regimen_claim"],
            "unchanged_from_shadow_repository": True,
        },
        "non_therapeutic_claims": {
            "total": non_therapeutic_total,
            "diagnostic_claim": non_therapeutic["diagnostic_claim"],
            "prognostic_claim": non_therapeutic["prognostic_claim"],
        },
        "total_claims_amended": therapeutic_total + non_therapeutic_total,
        "total_claims_derivation": (
            f"{therapeutic_total} terapeutici (invariati dal repository shadow) + "
            f"{non_therapeutic_total} non terapeutici approvati dall'audit"
        ),
        "expected_count_forced": False,
        "unsupported_associations": len(shadow_unsupported),
        "unresolved_associations": len(shadow_unresolved),
        "parents_without_claims": {
            "count": len(still_without),
            "graph_evidence_ids": still_without,
            "before_this_phase": sorted(previously_without),
            "gained_a_claim_in_this_phase": newly_replaced,
        },
        "legacy_statements": {
            "deprecated_before": len(previously_deprecated),
            "newly_replaced_by_non_therapeutic_claim": len(newly_replaced),
            "deprecated_after": len(previously_deprecated) + len(newly_replaced),
            "without_positive_replacement": sorted(
                d["graph_evidence_id"]
                for d in previously_deprecated
                if d["deprecation_state"] == "deprecated_without_replacement"
            ),
            "still_unresolved": [
                r["graph_evidence_id"]
                for r in sorted(audit, key=lambda x: x["graph_evidence_id"])
                if r["verdict"] == "non_therapeutic_claim_unresolved"
            ],
        },
        "qualification_links": {
            "to_retire_before": len(previously_deprecated),
            "to_create_before": 15,
            "additional_to_create": non_therapeutic_total,
            "additional_to_retire": len(newly_replaced),
            "executed": False,
        },
        "qualified_views": {
            "to_regenerate_before": 13,
            "additional_to_regenerate": len(newly_replaced),
            "to_regenerate_after": 13 + len(newly_replaced),
            "executed": False,
        },
    }


# ── erratum ───────────────────────────────────────────────────────────────────


def _erratum(inventory: Mapping[str, Any]) -> dict[str, Any]:
    spec_path = REPO_ROOT / ORIGINAL_ARTIFACTS[0]
    md_path = REPO_ROOT / ORIGINAL_ARTIFACTS[1]
    sim_path = REPO_ROOT / ORIGINAL_ARTIFACTS[2]
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    original_prose = spec["sections"]["16_deprecation"]["content"]
    simulation = json.loads(sim_path.read_text(encoding="utf-8"))

    total = inventory["total_claims_amended"]

    return {
        "erratum_version": ERRATUM_VERSION,
        "issued_on": CORRECTION_DATE,
        "issued_by_phase": CORRECTION_COMMIT_PLACEHOLDER,
        "originals_rewritten": False,
        "originals_preserved": True,
        "note": (
            "L'erratum non modifica gli artefatti congelati. Li cita per hash e "
            "dichiara la correzione accanto, cosi' che chi legge l'originale possa "
            "risalire alla rettifica e chi legge la rettifica possa verificare "
            "l'originale."
        ),
        "corrections": [
            {
                "correction_id": "ERR-A-claim-count",
                "original_artifact": ORIGINAL_ARTIFACTS[2],
                "original_sha256": sha256_file(sim_path),
                "field": "resulting_claim_count",
                "original_value": simulation["resulting_claim_count"],
                "corrected_value": total,
                "correction_basis": "derived_from_audit",
                "structured_source_of_correction": [
                    "benchmarks/mtb_evidence/v3/typed_claim_shadow_migration/typed_claims.jsonl",
                    "benchmarks/mtb_evidence/v3/non_therapeutic_claim_contract_and_erratum/claim_id_simulation.jsonl",
                ],
                "cause": (
                    "La proiezione 147 - 13 + 15 assumeva che ognuno dei 134 record non "
                    "adjudicati portasse un claim. Tre non ne portavano, perche' la "
                    "tassonomia aveva soltanto tipi di intervento e quei tre record non "
                    "affermano una terapia. Il numero non era sbagliato per un errore di "
                    "conto: era sbagliato perche' la tassonomia era incompleta."
                ),
                "impact_on_counts": {
                    "therapeutic_claims": inventory["therapeutic_claims"]["total"],
                    "non_therapeutic_claims": inventory["non_therapeutic_claims"]["total"],
                    "total_claims": total,
                    "parents_without_claims": inventory["parents_without_claims"]["count"],
                },
                "impact_on_migration": (
                    "Il denominatore claim-level cambia e va etichettato con la versione "
                    "del corpus. Due statement legacy passano da 'preservato' a "
                    "'sostituito da claim diagnostico'."
                ),
                "impact_on_documentary_decisions": "none",
                "documentary_decisions_unchanged": True,
            },
            {
                "correction_id": "ERR-B-groups-without-replacement",
                "original_artifact": ORIGINAL_ARTIFACTS[0],
                "original_sha256": sha256_file(spec_path),
                "also_appears_in": {
                    "artifact": ORIGINAL_ARTIFACTS[1],
                    "sha256": sha256_file(md_path),
                    "line": 68,
                },
                "field": "sections.16_deprecation.content",
                "original_value": original_prose,
                "original_claim": "evidence:275 ed evidence:4759 non hanno alcun claim sostitutivo",
                "corrected_value": (
                    "I 13 statement operativi corrispondenti ai gruppi adjudicati vanno "
                    "deprecati come claim, non cancellati: restano leggibili come record "
                    "storici con un puntatore al parent che li sostituisce. Due di essi "
                    "(evidence:3811 ed evidence:4759) non hanno alcun claim sostitutivo e "
                    "la deprecazione va motivata col reason code. evidence:275 ha invece "
                    "un claim sostitutivo, aggregato sulla classe EGFR-TKI: cio' che non "
                    "ha e' un sostituto atomico su erlotinib, ed e' esattamente il punto "
                    "dell'adjudication."
                ),
                "correction_basis": "structured_data_disagrees_with_prose",
                "structured_source_of_correction": [
                    "packet_adjudications.jsonl: evidence:275 approved_claims=['CLM-4ffe85304f3ef5533b58'], evidence:3811 approved_claims=[], evidence:4759 approved_claims=[]",
                    "post_adjudication_schema_simulation.json: groups_without_any_claim=['evidence:3811','evidence:4759']",
                    "MULTI_INTERVENTION_ADJUDICATION.md riga 23: gruppi che non producono alcun claim: 2 (evidence:3811, evidence:4759)",
                    "PARENT_SEMANTICS_DECISION.md riga 67: evidence:3811 e evidence:4759 senza alcun claim",
                ],
                "cause": (
                    "Errore di redazione nella prosa: evidence:275 e' il gruppo il cui "
                    "claim *atomico* e' stato rifiutato, e nella frase e' stato scambiato "
                    "con il gruppo che non ha alcun claim. Quattro artefatti strutturati "
                    "concordano contro quella frase, e la migrazione shadow ha seguito i "
                    "dati."
                ),
                "impact_on_counts": {
                    "statements_deprecated_without_replacement": 2,
                    "affected_groups": ["evidence:3811", "evidence:4759"],
                    "evidence_275_has_replacement": True,
                    "evidence_275_replacement_claim_id": "CLM-4ffe85304f3ef5533b58",
                    "evidence_275_replacement_claim_type": "aggregate_intervention_claim",
                },
                "impact_on_migration": (
                    "Nessuno: la migrazione shadow aveva gia' seguito i dati strutturati. "
                    "L'impatto e' su chi legge la specification e ne trarrebbe una "
                    "conclusione sbagliata su evidence:275."
                ),
                "impact_on_documentary_decisions": "none",
                "documentary_decisions_unchanged": True,
            },
        ],
        "adjudication_decisions_revisited": False,
        "gold_used": False,
    }


def _amended_specification(inventory: Mapping[str, Any]) -> dict[str, Any]:
    spec_path = REPO_ROOT / ORIGINAL_ARTIFACTS[0]
    original = json.loads(spec_path.read_text(encoding="utf-8"))
    return {
        "specification_version": AMENDED_SPEC_VERSION,
        "supersedes": original["specification_version"],
        "supersedes_sha256": sha256_file(spec_path),
        "original_preserved_at": ORIGINAL_ARTIFACTS[0],
        "erratum": ERRATUM_VERSION,
        "status": "amended_not_promoted",
        "amended_sections": {
            "16_deprecation": {
                "title": "Deprecazione degli statement esistenti",
                "content": next(
                    c["corrected_value"]
                    for c in _erratum(inventory)["corrections"]
                    if c["correction_id"] == "ERR-B-groups-without-replacement"
                ),
                "supersedes_original_content": True,
                "breaking_change": True,
            },
            "21_object_taxonomy": {
                "title": "Tassonomia degli oggetti del repository",
                "content": (
                    "Il repository contiene cinque categorie distinte e non "
                    "sovrapponibili. I *claim terapeutici* portano un intervento e "
                    "ricevono therapy score: atomici, aggregati, di regime. I *claim non "
                    "terapeutici* non portano intervento e non ricevono therapy score: "
                    "diagnostici e prognostici. Le *associazioni unsupported* sono "
                    "conclusioni negative auditabili. Le *associazioni unresolved* sono "
                    "sospensioni riapribili. I *parent senza claim* sono contenitori di "
                    "provenienza per i quali nessun claim e' sostenuto, ed e' un esito "
                    "legittimo. Le cinque categorie hanno denominatori separati: nessuna "
                    "metrica le somma."
                ),
                "new_section": True,
                "breaking_change": True,
            },
            "22_non_therapeutic_claims": {
                "title": "Claim non terapeutici",
                "content": (
                    "DiagnosticClaim e PrognosticClaim sono fratelli di TherapeuticClaim "
                    "sotto EvidenceClaim, non suoi sottotipi: non hanno intervento, e "
                    "metterli sotto un nodo che lo richiede costringerebbe a inventarlo. "
                    "Non ricevono therapy score, non entrano nelle metriche "
                    "therapy-level, non vengono appiattiti in `intervention` e non sono "
                    "confrontabili con regimi o classi di farmaci. PredictiveClaim non "
                    "viene introdotto: non esiste un caso materializzabile nel corpus e "
                    "il modello lo esprime gia' come TherapeuticClaim con direzione."
                ),
                "new_section": True,
                "breaking_change": True,
            },
        },
        "unchanged_sections": sorted(
            k for k in original["sections"] if k != "16_deprecation"
        ),
        "object_categories": {
            "therapeutic_claims": inventory["therapeutic_claims"]["total"],
            "non_therapeutic_claims": inventory["non_therapeutic_claims"]["total"],
            "unsupported_associations": inventory["unsupported_associations"],
            "unresolved_associations": inventory["unresolved_associations"],
            "parents_without_claims": inventory["parents_without_claims"]["count"],
        },
        "resulting_claim_count": inventory["total_claims_amended"],
        "resulting_claim_count_is_derived": True,
        "adjudication_decisions_unchanged": True,
        "gold_used": False,
    }


def _lineage() -> dict[str, Any]:
    entries = []
    for relative in ORIGINAL_ARTIFACTS:
        path = REPO_ROOT / relative
        entries.append(
            {
                "artifact": relative,
                "sha256": sha256_file(path),
                "role": "original_frozen",
                "modified_by_this_phase": False,
                "superseded_by": (
                    AMENDED_SPEC_VERSION
                    if relative.endswith("migration_specification.json")
                    else None
                ),
                "corrected_by": ERRATUM_VERSION,
            }
        )
    return {
        "lineage_version": "artifact_version_lineage/1.0",
        "originals": entries,
        "amendments": [
            {
                "artifact": "non_therapeutic_claim_contract_and_erratum/migration_specification_amended.json",
                "version": AMENDED_SPEC_VERSION,
                "supersedes": "migration-specification/1.0",
                "role": "amended",
                "promoted": False,
            },
            {
                "artifact": "non_therapeutic_claim_contract_and_erratum/adjudication_erratum.json",
                "version": ERRATUM_VERSION,
                "role": "erratum",
                "promoted": False,
            },
        ],
        "shadow_repository": {
            "artifact": "benchmarks/mtb_evidence/v3/typed_claim_shadow_migration",
            "modified_by_this_phase": False,
            "regenerated": False,
        },
        "rule": (
            "Un artefatto congelato non viene mai riscritto. La correzione vive "
            "accanto, con l'hash dell'originale, e il lineage tiene i due collegati."
        ),
    }


def _manifest(
    artifacts: Mapping[str, str],
    inventory: Mapping[str, Any],
    audit: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    verdicts = Counter(r["verdict"] for r in audit)
    return {
        "contract_version": CONTRACT_VERSION,
        "erratum_version": ERRATUM_VERSION,
        "amended_specification_version": AMENDED_SPEC_VERSION,
        "claim_id_formula_version": CLAIM_ID_FORMULA_VERSION,
        "records_audited": len(audit),
        "verdicts": dict(sorted(verdicts.items())),
        "diagnostic_claims_approved": inventory["non_therapeutic_claims"]["diagnostic_claim"],
        "prognostic_claims_approved": inventory["non_therapeutic_claims"]["prognostic_claim"],
        "predictive_claim_required": PREDICTIVE_CLAIM_ASSESSMENT["required"],
        "total_claims_amended": inventory["total_claims_amended"],
        "expected_count_forced_to_149": False,
        "interventions_invented": 0,
        "originals_modified": False,
        "shadow_repository_modified": False,
        "shadow_repository_promoted": False,
        "operational_corpus_modified": False,
        "operational_adapter_modified": False,
        "operational_retriever_modified": False,
        "operational_scoring_modified": False,
        "metrics_computed": False,
        "gold_used": False,
        "network_used": False,
        "neo4j_used": False,
        "llm_used": False,
        "artifact_sha256": {
            name: sha256_text(text) for name, text in sorted(artifacts.items())
        },
    }


def write(output: Path, artifacts: Mapping[str, str]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, text in sorted(artifacts.items()):
        (output / name).write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reverse-input-order", action="store_true")
    parser.add_argument("--check-determinism", action="store_true")
    args = parser.parse_args()

    artifacts = build(reverse=args.reverse_input_order)
    if args.check_determinism:
        other = build(reverse=not args.reverse_input_order)
        if artifacts != other:
            differing = sorted(k for k in artifacts if artifacts[k] != other.get(k))
            raise SystemExit(f"output non deterministico: {differing}")
        print("determinismo verificato: output identico con ordine invertito")
    write(args.output, artifacts)
    print(f"scritti {len(artifacts)} artefatti in {args.output}")


if __name__ == "__main__":
    main()
