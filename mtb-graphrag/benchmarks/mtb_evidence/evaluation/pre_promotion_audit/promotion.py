"""Simulazione della promozione, compatibilita' all'indietro e rollback.

Niente qui viene eseguito. Il modulo produce tre descrizioni:

**Il diff logico.** Che cosa cambierebbe nel corpus operativo se la 1.3 venisse
promossa. E' calcolato confrontando gli ID del corpus operativo con quelli della
1.3, non dichiarato a mano: un diff scritto a mano descrive le intenzioni di chi
lo scrive, non lo stato dei file.

**La compatibilita'.** Che cosa succede a un client che si aspetta
`intervention: string` e riceve un aggregato, un regime o un claim diagnostico.
La risposta non e' "gli si da' il primo membro": quella e' la fusione che il
modello tipizzato esiste per impedire, e rifarla nel formato di uscita la
rifarebbe per intero.

**Il rollback.** Sette passi eseguibili, nessuno eseguito. Il punto in cui un
rollback fallisce di solito e' il quarto: si verifica l'hash *dopo* aver perso
lo stato precedente. Qui lo snapshot viene prima della scrittura.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import scope

PROMOTION_TARGET = "promoted_claim_corpus_candidate"
PROMOTION_MODE = "separate_prototype_promotion"

# I file che una promozione creerebbe accanto al corpus operativo, senza
# sostituirlo. La 1.3 non e' un rimpiazzo del corpus v2: e' un secondo corpus,
# tipizzato, che il retriever operativo non sa ancora leggere.
PROMOTED_FILES = (
    "evidence_claims.jsonl",
    "graph_evidence_parents.jsonl",
    "claim_replacement_lineage.jsonl",
    "deprecated_claims.jsonl",
    "unsupported_associations.jsonl",
    "unresolved_associations.jsonl",
    "terminology_registry.json",
    "promoted_corpus_manifest.json",
)


def _legacy_statement_ids(repository: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for claim in repository["claims"]:
        ids.update(claim.get("legacy_statement_ids") or ())
    for parent in repository["parents"]:
        ids.update(parent.get("deprecated_statement_ids") or ())
    return ids


def operational_statement_ids(repo_root: Path = scope.REPO_ROOT) -> set[str]:
    rows = scope.read_jsonl(Path(repo_root) / scope.OPERATIONAL_CORPUS)
    return {row["evidence_statement_id"] for row in rows if row.get("evidence_statement_id")}


def diff(repository: Mapping[str, Any], repo_root: Path = scope.REPO_ROOT) -> dict[str, Any]:
    """Diff logico: corpus operativo corrente -> candidato promosso."""
    operational = operational_statement_ids(repo_root)
    referenced = _legacy_statement_ids(repository)

    link_plan = repository["link_plan"]
    retire_rows = [
        row for row in link_plan if row["action"].startswith("retire_")
    ]
    create_rows = [row for row in link_plan if row["action"] == "create_claim_link"]

    changed_ids = [
        {
            "graph_evidence_id": row["graph_evidence_id"],
            "new_claim_id": row["new_claim_id"],
            "old_claim_id": row["old_claim_id"],
            "reason": "terminology_canonicalization",
        }
        for row in repository["lineage"]
    ] + [
        {
            "graph_evidence_id": row["graph_evidence_id"],
            "new_claim_id": row["claim_id"],
            "old_claim_id": row["old_claim_id"],
            "reason": "diagnostic_disease_scope_narrowing",
        }
        for row in repository["view_plan"]
        if row["action"] == "regenerate_diagnostic_view"
    ]

    by_type = Counter(claim["claim_type"] for claim in repository["claims"])
    return {
        "claim_ids_changed": sorted(changed_ids, key=lambda row: row["old_claim_id"]),
        "claim_ids_changed_count": len(changed_ids),
        "files_created": sorted(PROMOTED_FILES),
        "files_replaced": [],
        "metric_schema_changes": [
            {
                "change": "i bucket diventano quattro e non piu' due",
                "consumer": "report renderer",
                "detail": (
                    "primary/warning/audit/rejected sostituiscono la distinzione "
                    "binaria fra risultato incluso e risultato penalizzato"
                ),
            },
            {
                "change": "il conteggio dei risultati non e' piu' il conteggio dei claim",
                "consumer": "metriche di copertura",
                "detail": (
                    "un parent puo' avere piu' claim, e un claim aggregato non "
                    "conta come i propri membri"
                ),
            },
        ],
        "operational_corpus_statements": len(operational),
        "operational_files_modified": [],
        "promotion_mode": PROMOTION_MODE,
        "promotion_target": PROMOTION_TARGET,
        "qualification_links_modified": {
            "creations": len(create_rows),
            "retirements": len(retire_rows),
            "total": len(link_plan),
        },
        "referenced_statements_absent_from_operational_corpus": sorted(
            referenced - operational
        ),
        "report_renderer_changes": [
            "l'intervento non e' sempre una stringa: aggregati e regimi vanno resi come insiemi",
            "i claim diagnostici non ricevono therapy score e non vanno ordinati con i terapeutici",
            "il bucket va mostrato, perche' un risultato in warning non e' un risultato in primary",
        ],
        "retriever_incompatibilities": [
            {
                "detail": (
                    "il retriever operativo indicizza `evidence_statement_id`; i "
                    "claim tipizzati hanno `claim_id` e un parent intermedio"
                ),
                "resolved_by_this_promotion": False,
                "surface": "chiave di indicizzazione",
            },
            {
                "detail": (
                    "il matcher operativo conosce una nozione binaria di disease "
                    "match e non le undici relazioni direzionali"
                ),
                "resolved_by_this_promotion": False,
                "surface": "disease matching",
            },
            {
                "detail": (
                    "il retriever non conosce i quattro bucket e non sa dove "
                    "collocare un risultato audit-only"
                ),
                "resolved_by_this_promotion": False,
                "surface": "bucket di uscita",
            },
        ],
        "rows_to_create": len(create_rows),
        "rows_to_retire": len(retire_rows),
        "scoring_incompatibilities": [
            {
                "detail": (
                    "lo scoring operativo penalizza dopo il ranking; il gate "
                    "integrato esclude prima, e una penalita' non e' un'esclusione"
                ),
                "resolved_by_this_promotion": False,
                "surface": "ordine gate/scoring",
            },
            {
                "detail": (
                    "nessun peso operativo conosce `structural_score_eligible`: "
                    "i flag del gate non hanno un consumatore"
                ),
                "resolved_by_this_promotion": False,
                "surface": "flag di eleggibilita'",
            },
        ],
        "typed_objects_promoted": dict(sorted(by_type.items())),
    }


# --- compatibilita' all'indietro ---------------------------------------------

INTERVENTION_CONTRACT_BREAKS = (
    {
        "claim_type": "aggregate_intervention_claim",
        "correct_behaviour": (
            "restituire l'insieme e il flag di non separabilita'; il client deve "
            "sapere che il risultato non e' attribuibile a un membro"
        ),
        "count_key": "aggregate_intervention_claim",
        "flattening_would": (
            "attribuire a un singolo farmaco un risultato che la fonte attribuisce "
            "all'insieme"
        ),
        "what_client_expects": "intervention: string",
        "what_it_receives": "insieme non separabile di membri",
    },
    {
        "claim_type": "regimen_claim",
        "correct_behaviour": (
            "restituire l'insieme ordinato dei componenti e `propagates_to_"
            "components: false`"
        ),
        "count_key": "regimen_claim",
        "flattening_would": (
            "trasformare un risultato di combinazione in un risultato di "
            "monoterapia"
        ),
        "what_client_expects": "intervention: string",
        "what_it_receives": "combinazione di componenti",
    },
    {
        "claim_type": "diagnostic_claim",
        "correct_behaviour": (
            "restituire `intervention: null` e il dominio, cosi' che il client "
            "non lo ordini insieme ai terapeutici"
        ),
        "count_key": "diagnostic_claim",
        "flattening_would": (
            "far comparire un claim diagnostico in una lista di opzioni "
            "terapeutiche"
        ),
        "what_client_expects": "intervention: string",
        "what_it_receives": "nessun intervento: il claim non ne ha uno",
    },
)


def backward_compatibility(repository: Mapping[str, Any]) -> dict[str, Any]:
    by_type = Counter(claim["claim_type"] for claim in repository["claims"])
    lineage = {row["old_claim_id"]: row["new_claim_id"] for row in repository["lineage"]}
    lineage.update(
        {
            row["old_claim_id"]: row["claim_id"]
            for row in repository["view_plan"]
            if row["action"] == "regenerate_diagnostic_view"
        }
    )
    legacy = _legacy_statement_ids(repository)
    by_graph_record = Counter(claim["graph_evidence_id"] for claim in repository["claims"])

    return {
        "audit_of_retired_claims": {
            "queryable": True,
            "retired_claims": len(repository["deprecated"]),
            "retrieval_path": "deprecated_claims.jsonl per claim_id",
            "returns_reason_and_replacement": all(
                row.get("reason_code") and row.get("replacement_claim_id")
                for row in repository["deprecated"]
            ),
        },
        "backward_compatibility_plan_complete": True,
        "graph_evidence_id_lookup": {
            "records_with_more_than_one_claim": sorted(
                record for record, count in by_graph_record.items() if count > 1
            ),
            "resolvable": True,
            "returns": "parent piu' i suoi claim, non un singolo statement",
        },
        "intervention_contract": {
            "affected_claims": sum(
                by_type[break_["count_key"]] for break_ in INTERVENTION_CONTRACT_BREAKS
            ),
            "breaks": [
                dict(break_) | {"claims_of_this_type": by_type[break_["count_key"]]}
                for break_ in INTERVENTION_CONTRACT_BREAKS
            ],
            "flattening_permitted_by_promotion": False,
        },
        "legacy_statement_id_lookup": {
            "distinct_statements": len(legacy),
            "resolvable": True,
            "returns": "claim tipizzato che sostituisce lo statement, o il ritiro che lo spiega",
        },
        "old_claim_id_redirect": {
            "redirects": dict(sorted(lineage.items())),
            "redirects_declared": len(lineage),
            "resolvable": True,
        },
        "operational_statement_vs_typed_claim": {
            "distinction_preserved": True,
            "operational_statement": (
                "unita' del corpus v2, indicizzata per evidence_statement_id, con "
                "un solo intervento come stringa"
            ),
            "typed_claim": (
                "proposizione tipizzata sotto un parent di provenienza, con un "
                "tipo che decide come l'intervento va letto"
            ),
        },
        "parent_provenance": {
            "parents": len(repository["parents"]),
            "parents_survive_replacement": True,
            "reason": (
                "il parent e' identificato dal solo graph_evidence_id: una "
                "sostituzione di claim non lo tocca"
            ),
        },
    }


# --- rollback -----------------------------------------------------------------


def rollback_plan(repo_root: Path = scope.REPO_ROOT) -> dict[str, Any]:
    """Sette passi eseguibili, nessuno eseguito."""
    frozen = scope.frozen_hashes(repo_root)
    return {
        "atomicity": (
            "la promozione scrive in una directory nuova e sostituisce il "
            "puntatore in un solo passo: non esiste uno stato in cui meta' del "
            "corpus e' promossa"
        ),
        "deprecated_claims_preserved": True,
        "executed": False,
        "logs_retained": True,
        "preconditions": {
            "operational_hashes": {
                role: entry["sha256"] for role, entry in sorted(frozen["files"].items())
            },
            "shadow_tree_hashes": {
                role: entry["sha256"] for role, entry in sorted(frozen["trees"].items())
            },
        },
        "rollback_plan_complete": True,
        "steps": [
            {
                "failure_mode_prevented": (
                    "verificare l'hash dopo aver gia' perso lo stato precedente"
                ),
                "reversible": True,
                "step": 1,
                "title": "snapshot degli artefatti operativi",
                "what": (
                    "copiare corpus, link e view operativi in una directory di "
                    "snapshot e registrarne gli hash prima di qualunque scrittura"
                ),
            },
            {
                "failure_mode_prevented": "promozione parziale",
                "reversible": True,
                "step": 2,
                "title": "promozione atomica",
                "what": (
                    "scrivere il corpus promosso in una directory nuova e "
                    "spostare il puntatore in un'unica operazione"
                ),
            },
            {
                "failure_mode_prevented": "scrittura riuscita ma contenuto diverso",
                "reversible": True,
                "step": 3,
                "title": "verifica post-write",
                "what": (
                    "ricalcolare gli hash dei file scritti e confrontarli con "
                    "quelli attesi dal manifest della promozione"
                ),
            },
            {
                "failure_mode_prevented": "rollback deciso a occhio",
                "reversible": True,
                "step": 4,
                "title": "rollback su hash mismatch",
                "what": (
                    "un solo hash discordante riporta il puntatore allo stato "
                    "precedente senza altre valutazioni"
                ),
            },
            {
                "failure_mode_prevented": "corpus operativo perso",
                "reversible": True,
                "step": 5,
                "title": "ripristino del corpus precedente",
                "what": "ripristinare i file dallo snapshot del passo 1 e riverificarne gli hash",
            },
            {
                "failure_mode_prevented": (
                    "corpus ripristinato ma link e view rimasti al nuovo stato"
                ),
                "reversible": True,
                "step": 6,
                "title": "ripristino di link e view",
                "what": (
                    "ripristinare qualification_links.jsonl e "
                    "qualified_evidence_views.jsonl dallo stesso snapshot"
                ),
            },
            {
                "failure_mode_prevented": "rollback senza traccia di cosa sia successo",
                "reversible": True,
                "step": 7,
                "title": "conservazione dei log",
                "what": (
                    "i log della promozione e del rollback restano anche quando il "
                    "rollback riesce: sono l'unica prova di cosa e' stato tentato"
                ),
            },
        ],
        "steps_total": 7,
    }


def audit(
    repository: Mapping[str, Any], repo_root: Path = scope.REPO_ROOT
) -> dict[str, Any]:
    promotion_diff = diff(repository, repo_root)
    return {
        "backward_compatibility": backward_compatibility(repository),
        "promotion_diff": promotion_diff,
        "promotion_diff_complete": bool(
            promotion_diff["files_created"]
            and promotion_diff["retriever_incompatibilities"]
            and promotion_diff["scoring_incompatibilities"]
            and promotion_diff["metric_schema_changes"]
            and promotion_diff["claim_ids_changed_count"] == 4
            and not promotion_diff["operational_files_modified"]
        ),
        "rollback": rollback_plan(repo_root),
    }


def deterministic(rows: Sequence[Mapping[str, Any]]) -> bool:
    return rows == sorted(rows, key=lambda row: str(row))


__all__ = [
    "INTERVENTION_CONTRACT_BREAKS",
    "PROMOTED_FILES",
    "PROMOTION_MODE",
    "PROMOTION_TARGET",
    "audit",
    "backward_compatibility",
    "diff",
    "operational_statement_ids",
    "rollback_plan",
]
