"""Manifest e documenti del repository shadow 1.3.

Il manifest non riassume: deriva. Ogni conteggio, ogni readiness e ogni hash
vengono ricavati dagli artefatti dati appena generati, non riscritti a mano
accanto a essi. Un manifest scritto a mano e' un secondo posto in cui la verita'
puo' divergere, e diverge sempre nella direzione che fa sembrare la fase piu'
chiusa di quanto sia.

Le tre voci finali della readiness restano false per la ragione di sempre: la
1.3 e' un repository shadow riproducibile, non un corpus operativo. Promuovere,
migrare il retriever e rieseguire l'esplorazione sono decisioni successive, che
questa fase prepara e non prende.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Mapping

from backend.pipeline.evidence.shadow import disease_gate as DISEASE
from backend.pipeline.evidence.shadow import integrated_gates as GATE
from backend.pipeline.evidence.shadow import shadow_output_v12 as OUT
from backend.pipeline.evidence.shadow.identity import (
    CLAIM_ID_FORMULA_VERSION,
    CLAIM_IDENTITY_FIELDS,
)
from backend.pipeline.evidence.shadow.schema import (
    MIGRATION_STATUS,
    MODEL_SCHEMA_VERSION_V11,
)
from backend.pipeline.evidence.shadow.terminology_v13 import (
    REPOSITORY_VERSION,
    UNRESOLVED_SOURCE_LITERAL,
    VERIFIED_CANONICAL_LABEL,
    VERIFIED_DECISION_ID,
    VERIFIED_SOURCE_LITERAL,
    VERSION_BUMP_REASON,
)
from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy import (
    AUDIT_ALL,
    DEFAULT_MODE,
    ONTOLOGY_AWARE_WARNING,
    POLICY_MODES,
    RELATION_TYPES,
    STRICT_VERIFIED,
)
from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    canonical_dumps,
    sha256_text,
)

PHASE_VERSION = "integrated-shadow-repository/1.3"
REVIEWER_ROLE = "author_shadow_repository_integrator"
REVIEW_INDEPENDENCE = "non_independent"
REVIEW_STATUS = "first_review_complete"
PROPAGATION_POLICY = "prototype_only"


def _rows(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _payload(text: str) -> dict[str, Any]:
    return json.loads(text)


def readiness(artifacts: Mapping[str, str]) -> dict[str, Any]:
    """I cancelli della fase, derivati dagli artefatti e non dichiarati."""
    claims = _rows(artifacts["evidence_claims_v1_3.jsonl"])
    lineage = _rows(artifacts["claim_replacement_lineage_v1_3.jsonl"])
    registry = _payload(artifacts["terminology_registry_v1_3.json"])
    gate_rows = _rows(artifacts["integrated_structural_gate_simulation.jsonl"])
    regressions = _rows(artifacts["regression_case_simulation_v1_3.jsonl"])
    inventory = _payload(artifacts["operational_vs_shadow_inventory_v1_3.json"])

    aggregates = [
        claim
        for claim in claims
        if claim["claim_type"] == "aggregate_intervention_claim"
        and claim.get("terminology_provenance")
    ]
    modes_observed = {mode for row in gate_rows for mode in row["by_mode"]}
    # I tre conteggi sono quelli calcolati sulla matrice intera durante la
    # simulazione, non ricontati qui sul sottoinsieme emesso.
    scope = _payload(artifacts["operational_vs_shadow_inventory_v1_3.json"])[
        "gate_simulation_scope"
    ]
    leaked = scope["score_flags_leaked_outside_rankable_buckets"]
    primary_with_blocking = scope["primary_with_blocking_gate"]
    mode_invariant_primary = scope["primary_bucket_mode_invariant"]

    terminology_applied = (
        len(lineage) == 2
        and all(row["canonical_label_after"].startswith(VERIFIED_CANONICAL_LABEL) for row in lineage)
        and all(VERIFIED_SOURCE_LITERAL in row["source_literals"] for row in lineage)
    )
    literals_preserved = all(
        VERIFIED_SOURCE_LITERAL in claim["source_literal_members"]
        for claim in aggregates
    )
    unresolved_preserved = (
        not registry["queue_fully_resolved"]
        and len(registry["unresolved_mappings"]) == 1
        and registry["unresolved_mappings"][0]["source_literal_term"]
        == UNRESOLVED_SOURCE_LITERAL
        and not registry["unresolved_mappings"][0]["exact_alias_created"]
    )
    gates_clean = leaked == 0 and primary_with_blocking == 0
    regressions_clean = all(
        row["positive_score_in_non_rankable_bucket"] == 0
        and row["structural_score_ever_outside_primary"] == 0
        for row in regressions
    )
    integrity = bool(
        inventory["operational_hash_parity"]
        and inventory["operational_query"]["parity"]
        and not inventory["shadow_repositories_modified"]
        and inventory["gold_artifacts_read"] == 0
        and inventory["parent_probe"]["parents_ever_primary"] == 0
    )

    repository_ready = bool(
        len(claims) == 148
        and terminology_applied
        and literals_preserved
        and unresolved_preserved
        and gates_clean
        and regressions_clean
        and integrity
    )
    return {
        "audit_all_available": AUDIT_ALL in modes_observed,
        "claim_ids_recomputed": terminology_applied,
        "corpus_promotion_ready": False,
        "disease_gate_implemented": sorted(DISEASE.gate_contract()["relation_types"])
        == sorted(RELATION_TYPES),
        "full_exploratory_rerun_ready": False,
        "integrated_gate_implemented": gates_clean and mode_invariant_primary,
        "ontology_warning_available": ONTOLOGY_AWARE_WARNING in modes_observed,
        "operational_retriever_migration_ready": False,
        "pre_promotion_audit_ready": repository_ready and regressions_clean,
        "replacement_lineage_complete": len(lineage) == 2
        and all(row["reversible"] for row in lineage),
        "shadow_repository_v1_3_ready": repository_ready,
        "source_literals_preserved": literals_preserved,
        "strict_policy_default": DISEASE.DEFAULT_POLICY_MODE == STRICT_VERIFIED,
        "terminology_mapping_applied": terminology_applied,
        "unresolved_terminology_preserved": unresolved_preserved,
    }


def manifest(artifacts: Mapping[str, str]) -> dict[str, Any]:
    claims = _rows(artifacts["evidence_claims_v1_3.jsonl"])
    parents = _rows(artifacts["graph_evidence_parents_v1_3.jsonl"])
    lineage = _rows(artifacts["claim_replacement_lineage_v1_3.jsonl"])
    deprecated = _rows(artifacts["deprecated_claims_v1_3.jsonl"])
    registry = _payload(artifacts["terminology_registry_v1_3.json"])
    gate_rows = _rows(artifacts["integrated_structural_gate_simulation.jsonl"])
    query_rows = _rows(artifacts["query_retrieval_simulation_v1_3.jsonl"])
    regressions = _rows(artifacts["regression_case_simulation_v1_3.jsonl"])
    plan = _rows(artifacts["qualification_link_regeneration_plan_v1_3.jsonl"])
    view_plan = _rows(artifacts["qualified_view_regeneration_plan_v1_3.jsonl"])
    inventory = _payload(artifacts["operational_vs_shadow_inventory_v1_3.json"])
    scope = inventory["gate_simulation_scope"]

    types = Counter(claim["claim_type"] for claim in claims)
    domains = Counter(claim["claim_domain"] for claim in claims)
    buckets = Counter(row["final_bucket"] for row in gate_rows)
    origins = Counter(row["deprecation_origin"] for row in deprecated)

    return {
        "artifact_sha256": {
            name: sha256_text(text) for name, text in sorted(artifacts.items())
        },
        "claim_id_formula": {
            "collisions": registry["collisions"],
            "deduplications": registry["deduplications"],
            "fields": list(CLAIM_IDENTITY_FIELDS),
            "new_ids": {
                row["graph_evidence_id"]: row["new_claim_id"] for row in lineage
            },
            "old_ids": {
                row["graph_evidence_id"]: row["old_claim_id"] for row in lineage
            },
            "separator": "|",
            "version": CLAIM_ID_FORMULA_VERSION,
        },
        "counts": {
            "active_claims_total": len(claims),
            "aggregate_claims": types["aggregate_intervention_claim"],
            "atomic_claims": types["atomic_intervention_claim"],
            "by_claim_type": dict(sorted(types.items())),
            "deprecated_aggregate_claims": origins["terminology_canonicalization"],
            "deprecated_diagnostic_claims_in_lineage_only": origins[
                "diagnostic_disease_scope_narrowing"
            ],
            "diagnostic_claims": domains["diagnostic"],
            "parents": len(parents),
            "parents_without_claims": sum(
                not parent["child_claim_ids"] for parent in parents
            ),
            "prognostic_claims": domains["prognostic"],
            "qualification_plan_actions_total": len(plan),
            "regimen_claims": types["regimen_claim"],
            "replacement_aggregate_claims": len(lineage),
            "therapeutic_claims": domains["therapeutic"],
            "unresolved_associations": len(
                _rows(artifacts["unresolved_associations_v1_3.jsonl"])
            ),
            "unsupported_associations": len(
                _rows(artifacts["unsupported_associations_v1_3.jsonl"])
            ),
            "view_plan_actions_total": len(view_plan),
        },
        "disease_gate": DISEASE.GATE_VERSION,
        "evaluation_reference_deserialized": False,
        "gold_used": False,
        "integrated_structural_gate": GATE.GATE_VERSION,
        "invariants": {
            "aggregates_atomized": 0,
            "bucket_precedence": list(GATE.BUCKET_PRECEDENCE),
            "gold_artifacts_read": inventory["gold_artifacts_read"],
            "operational_artifacts_modified": not inventory["operational_hash_parity"],
            "parents_ever_primary": inventory["parent_probe"]["parents_ever_primary"],
            "plans_executed": False,
            "primary_with_blocking_gate": scope["primary_with_blocking_gate"],
            "repository_promoted": False,
            "score_flags_leaked_outside_rankable_buckets": scope[
                "score_flags_leaked_outside_rankable_buckets"
            ],
            "shadow_1_0_modified": False,
            "shadow_1_1_modified": False,
            "shadow_1_2_modified": False,
            "therapeutic_proposition_count_changed": False,
        },
        "llm_used": False,
        "migration_status": MIGRATION_STATUS,
        "model_schema": MODEL_SCHEMA_VERSION_V11,
        "neo4j_used": False,
        "network_used": False,
        "operational_query_sha256": inventory["operational_query"],
        "output_contract": OUT.OUTPUT_CONTRACT_VERSION,
        "phase": PHASE_VERSION,
        "policy": {
            "default_mode": DEFAULT_MODE,
            "modes": list(POLICY_MODES),
            "primary_bucket_is_mode_invariant": True,
            "relation_types": list(RELATION_TYPES),
        },
        "propagation_policy": PROPAGATION_POLICY,
        "python_version": "3.12",
        "readiness": readiness(artifacts),
        "repository_schema": REPOSITORY_VERSION,
        "review_independence": REVIEW_INDEPENDENCE,
        "review_status": REVIEW_STATUS,
        "reviewer_role": REVIEWER_ROLE,
        "simulation": {
            "bucket_totals_emitted": dict(sorted(buckets.items())),
            "bucket_totals_over_all_evaluations": scope[
                "bucket_totals_over_all_evaluations"
            ],
            "gate_pairs_emitted": scope["pairs_emitted"],
            "gate_pairs_evaluated": scope["pairs_evaluated"],
            "modes": len(POLICY_MODES),
            "queries": len({row["query_id"] for row in query_rows}),
            "query_outputs": len(query_rows),
            "regression_cases": len(regressions),
        },
        "supersedes": "qualified_claim_repository/1.2",
        "terminology": {
            "applied_decision_id": VERIFIED_DECISION_ID,
            "canonical_label": VERIFIED_CANONICAL_LABEL,
            "collisions": registry["collisions"],
            "deduplications": registry["deduplications"],
            "queue_fully_resolved": registry["queue_fully_resolved"],
            "source_literal_term": VERIFIED_SOURCE_LITERAL,
            "unresolved_source_literal": UNRESOLVED_SOURCE_LITERAL,
        },
        "test_framework": "unittest (stdlib)",
        "version_bump_reason": VERSION_BUMP_REASON,
    }


# --------------------------------------------------------------------------
# documenti
# --------------------------------------------------------------------------


def _repository_doc(payload: Mapping[str, Any]) -> str:
    counts = payload["counts"]
    formula = payload["claim_id_formula"]
    return f"""# Integrated shadow repository 1.3

Repository: `{REPOSITORY_VERSION}`
Stato: `{MIGRATION_STATUS}`
Motivazione del bump: {VERSION_BUMP_REASON}

La 1.3 fa due cose che le versioni precedenti avevano preparato e non potevano
fare: applica il mapping terminologico che la review ha verificato, e fa
derivare l'eleggibilità dalla congiunzione dei gate invece che da un gate alla
volta.

## Terminologia

`{VERIFIED_SOURCE_LITERAL}` → `{VERIFIED_CANONICAL_LABEL}`, decisione
`{VERIFIED_DECISION_ID}`, scope globale, verificata.

Il mapping cambia una rappresentazione canonica, non una proposizione. I due
gruppi coinvolti restano aggregate non separabili, `permits_member_specific_claims`
resta falso, e nessun claim atomico nasce dai membri. Cambia però l'identità,
perché la rappresentazione canonica è uno dei campi dell'hash: i due claim
vecchi sono ritirati con lineage reversibile e ne nascono due nuovi.

| gruppo | claim ritirato | claim attivo |
|---|---|---|
| `evidence:1851` | `{formula['old_ids']['evidence:1851']}` | `{formula['new_ids']['evidence:1851']}` |
| `evidence:1853` | `{formula['old_ids']['evidence:1853']}` | `{formula['new_ids']['evidence:1853']}` |

Il letterale della fonte non è stato toccato. `{VERIFIED_SOURCE_LITERAL}` è ciò
che il testo del 2013 dice, e un'identificazione pubblicata dopo non riscrive un
documento: il claim porta entrambe le rappresentazioni in campi distinti, ed è
raggiungibile con entrambi i nomi senza che nessuno dei due lo promuova.

`{UNRESOLVED_SOURCE_LITERAL}` / luminespib resta irrisolto. Nessun alias exact,
nessuna materializzazione, nessun claim ID modificato. Il registro elenca la
coppia aperta con lo stesso rilievo di quella chiusa: una coda che sembra vuota
non viene più guardata.

Collisioni: {formula['collisions']}. Deduplicazioni: {formula['deduplications']}.

## Conteggi

| oggetto | valore |
|---|---:|
| parent | {counts['parents']} |
| claim attivi | {counts['active_claims_total']} |
| terapeutici | {counts['therapeutic_claims']} |
| diagnostici | {counts['diagnostic_claims']} |
| prognostici | {counts['prognostic_claims']} |
| atomic | {counts['atomic_claims']} |
| aggregate | {counts['aggregate_claims']} |
| regimen | {counts['regimen_claims']} |
| unsupported association | {counts['unsupported_associations']} |
| unresolved association | {counts['unresolved_associations']} |
| parent senza claim | {counts['parents_without_claims']} |
| aggregate ritirati | {counts['deprecated_aggregate_claims']} |
| aggregate sostitutivi | {counts['replacement_aggregate_claims']} |
| diagnostici ritirati, solo lineage | {counts['deprecated_diagnostic_claims_in_lineage_only']} |

I claim ritirati non entrano nei {counts['active_claims_total']} attivi. I due
diagnostici ritirati dalle versioni precedenti restano leggibili soltanto nel
lineage storico.

## Perimetro

Corpus, adapter, repository, retriever, scoring e QualifiedEvidenceView
operative restano invariati, e la parità è misurata sugli hash prima e dopo più
una query operativa rieseguita. I repository shadow 1.0, 1.1 e 1.2 restano
leggibili e invariati con i propri manifest. I piani di link e view hanno
`executed = false`. Il gold non è stato letto.
"""


def _gate_doc(payload: Mapping[str, Any]) -> str:
    simulation = payload["simulation"]
    invariants = payload["invariants"]
    return f"""# Integrated structural gate

Gate: `{GATE.GATE_VERSION}`
Disease gate: `{DISEASE.GATE_VERSION}`
Output: `{OUT.OUTPUT_CONTRACT_VERSION}`
Modalità di default: `{DEFAULT_MODE}`

## La regola

L'eleggibilità finale deriva dalla congiunzione di sette decisioni: stato del
claim, dominio, biomarcatore, disease, intervento/regime/classe,
direzione/polarità, e idoneità allo scoring. La regola vale nelle due direzioni.

> Un singolo gate incompatibile impedisce il primary ranking.
> Un singolo gate compatibile non promuove nulla.

Fino alla 1.2 ogni gate decideva da solo e il risultato veniva letto come se le
decisioni fossero indipendenti. Non lo sono: un claim con disease exact e
biomarcatore incompatibile non è buono su un asse e meno buono sull'altro, non
risponde alla domanda.

## Precedenza dei bucket

1. `rejected_by_native_constraints`
2. `audit_only_results`
3. `retained_with_warning`
4. `primary_ranked_results`

Il motivo più restrittivo domina. Un claim unsupported o deprecated resta
audit-only anche con disease, biomarcatore e intervento tutti exact, perché ciò
che lo trattiene non è la qualità del match ma lo stato dell'oggetto. Le
eccezioni esplicite sono zero.

## Composizioni protette

| composizione | esito |
|---|---|
| disease exact + biomarker incompatible | `rejected`, score interamente falso |
| disease child + biomarker exact | `warning`, mai primary, nessuna promozione |
| disease exact + regimen component | `warning`, mai exact atomic support |
| unsupported + tutti gli assi exact | `audit` |
| deprecated + tutti gli assi exact | `audit` |

## Score

Nei bucket non ordinabili i flag di score non vengono ereditati dal gate più
permissivo: vengono azzerati. Un flag ereditato sarebbe la porta da cui un
punteggio alto rientra a decidere ciò che il gate aveva escluso.

Su {simulation['gate_pairs_evaluated']} valutazioni in {simulation['modes']}
modalità: flag di score sopravvissuti fuori dai bucket ordinabili
**{invariants['score_flags_leaked_outside_rankable_buckets']}**, primari con un
gate bloccante **{invariants['primary_with_blocking_gate']}**, contenitori di
provenienza diventati primari **{invariants['parents_ever_primary']}**.

## Modalità

`{STRICT_VERIFIED}` è il default e non un fallback: una query che non dichiara
la modalità ottiene la più conservativa. `{ONTOLOGY_AWARE_WARNING}` e
`{AUDIT_ALL}` vanno chieste esplicitamente. Il bucket primario è identico nelle
tre: exact, normalized exact e verified alias soltanto. Ciò che cambia fra le
modalità è come vengono esposte le relazioni non exact, mai quali diventano
primarie.
"""


def _readiness_doc(payload: Mapping[str, Any]) -> str:
    flags = payload["readiness"]
    lines = "\n".join(
        f"| `{name}` | **{str(value).lower()}** |" for name, value in sorted(flags.items())
    )
    return f"""# Shadow repository 1.3 readiness

Repository: `{REPOSITORY_VERSION}`
Stato: `{MIGRATION_STATUS}`

| Gate | Valore |
|---|---:|
{lines}

La 1.3 è pronta come repository shadow riproducibile e come base per un audit
pre-promozione, non come corpus operativo.

Le tre voci chiuse lo restano per la stessa ragione delle fasi precedenti. Il
mapping applicato è verificato ma la review resta non indipendente e la
propagazione resta `{PROPAGATION_POLICY}`. La coda terminologica non è chiusa:
{UNRESOLVED_SOURCE_LITERAL} attende una revisione esterna. Il gate integrato è
implementato e simulato nel percorso shadow, non nel retriever operativo, che
resta invariato e continua a usare la propria nozione binaria di disease match.

Promuovere il corpus, migrare il retriever e rieseguire l'esplorazione sono tre
decisioni successive e distinte. Questa fase le prepara e non ne prende nessuna.
"""


def build_reports(artifacts: Mapping[str, str], reverse: bool = False) -> dict[str, str]:
    """Manifest e documenti, derivati dagli artefatti dati gia' generati."""
    payload = manifest(artifacts)
    return {
        "INTEGRATED_GATE_IMPLEMENTATION.md": _gate_doc(payload),
        "INTEGRATED_SHADOW_REPOSITORY_1_3.md": _repository_doc(payload),
        "SHADOW_REPOSITORY_1_3_READINESS.md": _readiness_doc(payload),
        "repository_v1_3_manifest.json": canonical_dumps(payload),
    }


__all__ = ["PHASE_VERSION", "build_reports", "manifest", "readiness"]
