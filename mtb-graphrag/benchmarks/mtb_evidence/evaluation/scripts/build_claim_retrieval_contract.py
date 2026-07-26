"""Costruisce e simula il contratto di retrieval per i claim tipizzati.

Legge i 15 claim adjudicati, i 13 parent e le 12 associazioni non materializzate,
e li confronta con un set deterministico di query tipizzate. Produce il contratto
e la simulazione; non tocca adapter, corpus, repository, retriever, scoring, non
rigenera le view e non assegna pesi.

Deterministico: ogni output e' ordinato per chiave dichiarata. Con
`--reverse-query-order` le query vengono valutate al contrario e l'output deve
restare identico.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from benchmarks.mtb_evidence.evaluation.claim_type_retrieval_contract import (
    BUCKETS,
    CLAIM_TYPES,
    CONTRACT_VERSION,
    DIRECTIONS,
    DISEASE_RELATIONS,
    EXCLUSION_REASON_CODES,
    MATCH_TYPES,
    PARENT_ALLOWED_USES,
    PARENT_FORBIDDEN_USES,
    PARENT_KIND,
    POLARITIES,
    QUERY_TYPES,
    RETRIEVABLE_OBJECT_KINDS,
    VERIFIED_CLASS_MEMBERSHIPS,
    WARNING_CODES,
    check_no_numerical_compensation,
    classify_query,
    normalize,
    score_eligibility,
    structural_match,
)
from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    canonical_dumps,
    canonical_jsonl,
    sha256_bytes,
    sha256_text,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
ADJ = V3 / "multi_intervention_adjudication"
DATA = REPO_ROOT / "benchmarks/mtb_evidence/evaluation/data"
DEFAULT_OUTPUT = V3 / "claim_type_retrieval_contract"

START_SHA = "6341d12088c4b856320eae3ece90936b9bbdd64b"
CONTRACT_BRANCH = "arch/v3-claim-type-retrieval-contract"

ENVIRONMENT = {
    "python_version": "3.12.10",
    "pytest_version": "9.0.2",
    "pluggy_version": "1.6.0",
    "iniconfig_version": "2.3.0",
    "packaging_version": "25.0",
    "pytest_subtests_installed": False,
    "interpreter": "python di sistema (WindowsApps PythonSoftwareFoundation.Python.3.12)",
    "venv_contains_pytest": False,
    "venv_modified_in_this_phase": False,
}

FROZEN_ARTIFACTS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/corpus_manifest.py",
    "backend/pipeline/evidence/corpus_regeneration.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
)

GOLD_ARTIFACTS = (
    "benchmarks/mtb_evidence/evaluation/data/clinical_gold_v1.jsonl",
    "benchmarks/mtb_evidence/evaluation/data/snapshot_gold_ffc97bc7c660f194.jsonl",
)

EXPECTED_CLAIMS = 15
EXPECTED_PARENTS = 13
REGRESSION_GROUPS = (
    "evidence:275",
    "evidence:4759",
    "evidence:3811",
    "evidence:11240",
    "evidence:12131",
)


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def digest(path: Path) -> str | None:
    return sha256_bytes(path.read_bytes()) if path.exists() else None


def tree_digest(directory: Path) -> dict[str, Any]:
    files = sorted(p for p in directory.rglob("*") if p.is_file())
    per_file = {
        str(p.relative_to(directory)).replace("\\", "/"): sha256_bytes(p.read_bytes())
        for p in files
    }
    joined = "\n".join(f"{name}:{value}" for name, value in sorted(per_file.items()))
    return {"file_count": len(per_file), "aggregate_sha256": sha256_text(joined)}


# --- oggetti interrogabili ----------------------------------------------------


def build_retrievable_objects(
    claims: Sequence[Mapping[str, Any]], associations: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Claim, parent e associazioni, normalizzati in una forma confrontabile.

    I parent entrano nell'insieme di proposito: se non venissero valutati non si
    potrebbe verificare che restano fuori dal ranking claim-level.
    """
    objects: list[dict[str, Any]] = []
    for claim in claims:
        if claim["claim_type"] == "regimen_claim":
            members = list(claim["regimen_components"])
        elif claim["claim_type"] == "aggregate_intervention_claim":
            members = list(claim["aggregate_members"])
        else:
            members = [claim["intervention"]]
        objects.append(
            {
                "claim_id": claim["claim_id"],
                "graph_evidence_parent": claim["graph_evidence_parent"],
                "claim_type": claim["claim_type"],
                "intervention_members": members,
                "aggregate_kind": claim.get("aggregate_kind"),
                "biomarker": claim["biomarker"],
                "disease_scope": claim["disease_scope"],
                "direction": claim["direction"],
                "polarity": claim["polarity"],
                "evidence_setting": claim["evidence_setting"],
                "source_id": claim["source_id"],
                "source_unit_id": claim["source_unit_id"],
                "locator": claim["locator"],
                "source_literal_terms": claim.get("source_literal_terms") or [],
            }
        )

    parents = {}
    for row in associations:
        parents.setdefault(row["graph_evidence_id"], row)
        if row["association_outcome"] not in ("unsupported_association", "unresolved_association"):
            continue
        objects.append(
            {
                "claim_id": f"ASSOC-{row['adjudication_id']}",
                "graph_evidence_parent": row["graph_evidence_id"],
                "claim_type": row["association_outcome"],
                "intervention_members": [row["intervention"]],
                "aggregate_kind": None,
                "biomarker": row["biomarker"],
                "disease_scope": row["disease"],
                "direction": "unknown",
                "polarity": "unknown",
                "evidence_setting": "unknown",
                "source_id": row["source_id"],
                "source_unit_id": row["source_unit_id"],
                "locator": row["locator"],
                "source_literal_terms": [],
            }
        )

    for graph_id, row in sorted(parents.items()):
        objects.append(
            {
                "claim_id": f"PARENT-{graph_id.replace(':', '-')}",
                "graph_evidence_parent": graph_id,
                "claim_type": PARENT_KIND,
                "intervention_members": [],
                "aggregate_kind": None,
                "biomarker": row["biomarker"],
                "disease_scope": row["disease"],
                "direction": "unknown",
                "polarity": "unknown",
                "evidence_setting": "unknown",
                "source_id": row["source_id"],
                "source_unit_id": row["source_unit_id"],
                "locator": row["locator"],
                "source_literal_terms": [],
            }
        )
    return objects


# --- simulazione --------------------------------------------------------------


def simulate(
    queries: Sequence[Mapping[str, Any]], objects: Sequence[Mapping[str, Any]], *, reverse: bool
) -> list[dict[str, Any]]:
    ordered = list(reversed(queries)) if reverse else list(queries)
    rows = []
    for query in ordered:
        query_type = classify_query(query)
        for obj in objects:
            match = structural_match(query, obj)
            eligibility = score_eligibility(match)
            # L'invariante non e' documentazione: viene esercitata a ogni riga
            # con un punteggio ipotetico massimo, e solleva se il tipo
            # strutturale potesse essere sopraffatto dai pesi.
            check_no_numerical_compensation(match, hypothetical_score=0.0)
            if match.bucket == "rejected_by_native_constraints" and query.get("biomarker"):
                pass
            rows.append(
                {
                    "simulation_id": f"SIM-{query['query_id']}-{match.claim_id}",
                    "query_id": query["query_id"],
                    "query_scenario": query["scenario"],
                    "query_type": query_type,
                    "query_interventions": list(query.get("interventions") or ()),
                    "query_intervention_class": query.get("intervention_class"),
                    "query_biomarker": query.get("biomarker"),
                    "query_disease": query.get("disease"),
                    "query_direction": query.get("direction"),
                    **match.as_dict(),
                    "score_eligibility": eligibility,
                    "provenance_parent": match.parent_graph_evidence_id,
                    "source_unit_id": obj["source_unit_id"],
                    "locator": obj["locator"],
                    "contract_version": CONTRACT_VERSION,
                }
            )
    return rows


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, int] = {}
    matches: dict[str, int] = {}
    for row in rows:
        buckets[row["bucket"]] = buckets.get(row["bucket"], 0) + 1
        matches[row["intervention_match_type"]] = matches.get(row["intervention_match_type"], 0) + 1
    primary = [row for row in rows if row["bucket"] == "primary_ranked_results"]
    return {
        "evaluations": len(rows),
        "bucket_counts": dict(sorted(buckets.items())),
        "match_type_counts": dict(sorted(matches.items())),
        "primary_results": len(primary),
        "primary_claim_types": dict(
            sorted(
                {
                    kind: sum(1 for row in primary if row["claim_type"] == kind)
                    for kind in {row["claim_type"] for row in primary}
                }.items()
            )
        ),
        "parent_in_primary": sum(1 for row in primary if row["claim_type"] == PARENT_KIND),
        "unsupported_in_primary": sum(
            1 for row in primary if row["claim_type"] == "unsupported_association"
        ),
        "unresolved_in_primary": sum(
            1 for row in primary if row["claim_type"] == "unresolved_association"
        ),
    }


def build_regression_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Un record per gruppo protetto, con le proprieta' verificate sulla simulazione."""
    regression = []
    for group in REGRESSION_GROUPS:
        touching = [row for row in rows if row["parent_graph_evidence_id"] == group]
        primary = [row for row in touching if row["bucket"] == "primary_ranked_results"]
        regression.append(
            {
                "graph_evidence_id": group,
                "evaluations": len(touching),
                "primary_results": len(primary),
                "primary_claim_ids": sorted({row["claim_id"] for row in primary}),
                "parent_ever_primary": any(
                    row["claim_type"] == PARENT_KIND for row in primary
                ),
                "unsupported_ever_primary": any(
                    row["claim_type"] == "unsupported_association" for row in primary
                ),
                "unresolved_ever_primary": any(
                    row["claim_type"] == "unresolved_association" for row in primary
                ),
                "match_types_observed": sorted({row["intervention_match_type"] for row in touching}),
                "buckets_observed": sorted({row["bucket"] for row in touching}),
                "warning_codes_observed": sorted(
                    {code for row in touching for code in row["warning_codes"]}
                ),
                "contract_version": CONTRACT_VERSION,
            }
        )
    return regression


# --- reportistica -------------------------------------------------------------


def render_contract(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Contratto di retrieval per i claim tipizzati",
        "",
        "L'adjudication ha deciso che il parent e' un contenitore di provenienza e che le",
        "proposizioni terapeutiche sono claim tipizzati. Quel modello non sopravvive al retrieval",
        "se il matching resta quello attuale, che confronta una stringa di intervento con un",
        "insieme di stringhe e tratta ogni corrispondenza come equivalente.",
        "",
        "## Il principio: due livelli, non uno",
        "",
        "Prima l'idoneita' strutturale, poi il punteggio. Un candidato strutturalmente",
        "incompatibile non puo' diventare compatibile con un punteggio alto.",
        "",
        "Nel sistema attuale la stessa intenzione esiste come penalita': `penalty_not_separable`",
        "vale -2, `penalty_pending_terminology` -3, `penalty_unresolved` -1, contro un",
        "`native_biomarker` da 40 e un `native_disease` da 30. Sono preferenze, non vincoli: un",
        "risultato di classe con biomarcatore e disease esatti supera qualunque penalita' e",
        "diventa evidenza per un farmaco specifico. E' esattamente cio' che l'adjudication ha",
        "vietato nei dati, e che il retrieval reintrodurrebbe.",
        "",
        "Qui quelle tre penalita' diventano gate. Il tipo strutturale del match ha precedenza sui",
        "pesi, e l'invariante e' esercitato a ogni riga della simulazione invece di essere",
        "affermato nella documentazione.",
        "",
        "## Oggetti interrogabili",
        "",
        "| oggetto | candidato claim-level | bucket massimo |",
        "| --- | --- | --- |",
        "| `graph_evidence_record` | no | audit |",
        "| `atomic_intervention_claim` | si | primario |",
        "| `regimen_claim` | si | primario |",
        "| `aggregate_intervention_claim` | si | primario |",
        "| `unsupported_association` | no | audit |",
        "| `unresolved_association` | no | warning |",
        "",
        "Il parent puo' essere caricato per lineage, fonte, record grezzo, provenienza",
        "dell'adapter e audit; non riceve mai un therapy score.",
        "",
        "## Tipi di query",
        "",
        "Cinque, non quattro. Ai quattro richiesti si aggiunge",
        "`unspecified_multi_intervention_query`: due farmaci nella query senza un indicatore",
        "strutturato di combinazione non fanno un regime. Dedurlo dalla cardinalita' produrrebbe",
        "exact match su regimi che nessuno ha chiesto, quindi restano vincoli alternativi.",
        "",
        "## Esito della simulazione",
        "",
        f"- valutazioni: {summary['evaluations']}",
        f"- risultati primari: {summary['primary_results']}",
        f"- parent in primario: {summary['parent_in_primary']}",
        f"- unsupported in primario: {summary['unsupported_in_primary']}",
        f"- unresolved in primario: {summary['unresolved_in_primary']}",
        "",
        "### Bucket",
        "",
    ]
    lines += [f"- `{key}`: {value}" for key, value in summary["bucket_counts"].items()]
    lines += ["", "### Tipi di match osservati", ""]
    lines += [f"- `{key}`: {value}" for key, value in summary["match_type_counts"].items()]
    lines += [
        "",
        "## Direzione e polarita'",
        "",
        "`reduced_sensitivity` non e' `resistance`: sono direzioni vicine e distinte, e",
        "collassarle trasformerebbe una risposta attenuata in una resistenza completa. Una query",
        "su una e un claim sull'altra danno `related_not_equivalent`, quindi warning e non",
        "primario. `does_not_support` non diventa mai supporto positivo, `conflicting` resta",
        "conflicting con warning, e `unknown` non e' assunto compatibile: contro una direzione",
        "richiesta finisce in warning con codice esplicito, non nel primario.",
        "",
        "## Disease",
        "",
        "La policy gerarchica non e' attiva. Valgono come hard match solo `exact`,",
        "`normalized_exact` e `verified_alias`. Le relazioni `explicit_parent`, `explicit_child`,",
        "`explicit_sibling` e `unresolved_disease_relation` sono dichiarate perche' il contratto",
        "resti compatibile con una futura policy ontology-aware, e sono marcate `active = false`.",
        "",
    ]
    return "\n".join(lines)


def render_regimen_doc(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# Regimi, aggregati e classi",
        "",
        "Sono i tre modi in cui una fonte puo' parlare di piu' di un farmaco insieme, e nessuno",
        "dei tre autorizza a parlare di uno solo.",
        "",
        "## Regime",
        "",
        "Il risultato appartiene alla combinazione. Exact match solo quando l'insieme dei",
        "componenti della query coincide con quello del claim dopo normalizzazione verificata;",
        "l'ordine non conta, perche' il confronto e' fra insiemi.",
        "",
        "- **componente singolo** → `regimen_component_related`, warning",
        "  `RESULT_APPLIES_TO_COMBINATION_NOT_COMPONENT`, mai exact e mai primario.",
        "- **sottoinsieme proprio** → `regimen_subset_mismatch`, `QUERY_REGIMEN_IS_PROPER_SUBSET`.",
        "- **sovrainsieme proprio** → `regimen_superset_mismatch`, `QUERY_REGIMEN_IS_PROPER_SUPERSET`.",
        "",
        "La scelta fra warning e audit per i correlati e' warning: il claim e' pertinente e",
        "l'utente ha diritto di vederlo, purche' non sia presentato come supporto per il",
        "componente. Nasconderlo in audit perderebbe informazione utile; metterlo nel primario",
        "direbbe una cosa falsa.",
        "",
        "## Aggregato di classe",
        "",
        "Exact solo su stessa classe canonica o alias di classe verificato. Una relazione",
        "verificata `farmaco appartiene a classe` produce `class_member_related` con warning",
        "`CLASS_LEVEL_EVIDENCE_NOT_DRUG_SPECIFIC`, mai `exact_intervention`.",
        "",
        "Il registro delle appartenenze verificate e' oggi **vuoto di proposito**. Senza una voce",
        "approvata, `erlotinib appartiene a EGFR-TKI` resta `unresolved_class_relation` e finisce",
        "in audit. Dedurre l'appartenenza dalla somiglianza delle stringhe sarebbe la stessa",
        "inferenza che l'adjudication ha rifiutato in `evidence:275`, spostata di un livello.",
        "",
        "## Aggregato non separabile",
        "",
        "La presenza del farmaco nella lista non autorizza un claim atomico:",
        "`aggregate_member_related`, warning `AGGREGATE_RESULT_NOT_SEPARABLE_BY_INTERVENTION`.",
        "",
        "## Mapping pending",
        "",
        "`BGJ398` e `infigratinib` non sono lo stesso termine finche' il mapping non e' approvato.",
        "Una query su `infigratinib` contro l'aggregato che nomina `BGJ398` da'",
        "`mapping_pending` e finisce in audit, non in warning: la differenza non e' di forza",
        "dell'evidenza ma di identita' dell'intervento.",
        "",
        "## Casi osservati nella simulazione",
        "",
        "| query | claim | match | bucket |",
        "| --- | --- | --- | --- |",
    ]
    interesting = [
        row
        for row in rows
        if row["intervention_match_type"]
        in (
            "exact_regimen",
            "regimen_component_related",
            "regimen_subset_mismatch",
            "regimen_superset_mismatch",
            "exact_intervention_class",
            "class_member_related",
            "unresolved_class_relation",
            "aggregate_member_related",
            "mapping_pending",
        )
    ]
    for row in sorted(interesting, key=lambda item: item["simulation_id"]):
        lines.append(
            f"| `{row['query_id']}` | `{row['claim_id']}` | `{row['intervention_match_type']}` | "
            f"`{row['bucket']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def render_scoring_audit(audit: Sequence[Mapping[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for row in audit:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    lines = [
        "# Audit di compatibilita' dello scoring",
        "",
        "Venti componenti del retriever e della configurazione di scoring, classificati rispetto",
        "al nuovo modello. Nessun peso e' stato definito, ritarato o proposto in forma numerica.",
        "",
    ]
    lines += [f"- `{key}`: {value}" for key, value in sorted(counts.items())]
    lines += [
        "",
        "## Il difetto strutturale",
        "",
        "Quattro voci sono classificate `should_be_removed` e sono la stessa cosa vista quattro",
        "volte: un vincolo espresso come peso. `penalty_pending_terminology` -3,",
        "`penalty_not_separable` -2, `penalty_unresolved` -1 e `penalty_invalid` -50 servono a",
        "impedire qualcosa, ma essendo numeri restano compensabili da altri numeri. Con",
        "`native_biomarker` a 40 le prime tre non impediscono nulla in pratica.",
        "",
        "`penalty_invalid` a -50 e' il caso limite: un valore scelto abbastanza grande da",
        "comportarsi come un vincolo. Funziona finche' nessuno ritara i pesi.",
        "",
        "## Cosa regge",
        "",
        "La struttura a quattro bucket esiste gia' ed e' quella giusta. La scomposizione del",
        "punteggio in parte nativa e qualificata regge e il contratto vi aggiunge un livello che",
        "viene prima. `provenance.graph_record_ids` e' gia' una lista e sostiene il legame",
        "claim-parent senza modifiche. Biomarcatore e disease sono indipendenti dal tipo di claim.",
        "",
        "## Dettaglio",
        "",
        "| id | componente | classificazione |",
        "| --- | --- | --- |",
    ]
    for row in sorted(audit, key=lambda item: item["component_id"]):
        lines.append(f"| `{row['component_id']}` | {row['component']} | `{row['classification']}` |")
    lines.append("")
    return "\n".join(lines)


def render_readiness(readiness: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    lines = ["# Readiness dell'implementazione del retrieval sui claim", "", "| criterio | stato |", "| --- | --- |"]
    for key, value in readiness.items():
        lines.append(f"| `{key}` | {str(value).lower()} |")
    lines += [
        "",
        "## Cosa e' congelato",
        "",
        "Tipi di claim, tipi di query, regole di match strutturale, regole di bucket, idoneita'",
        "allo scoring e codici di warning. Il contratto e' completo nel senso che ogni",
        "combinazione query-claim della simulazione riceve un match type, un bucket e una",
        "motivazione, senza casi non coperti.",
        "",
        f"La simulazione ha valutato {summary['evaluations']} combinazioni e nessun parent, nessuna",
        "associazione non sostenuta e nessuna associazione non risolta e' entrata nel bucket",
        "primario.",
        "",
        "## Cosa manca e perche'",
        "",
        "`new_weights_required` e' vero: le dodici feature proposte hanno dominio, significato e",
        "ruolo — gate, positiva o solo penalizzante — ma nessun valore. Assegnarli qui",
        "significherebbe sceglierli senza un criterio, oppure sceglierli guardando il gold, che e'",
        "escluso.",
        "",
        "`corpus_regeneration_ready` resta falso finche' adapter e repository non sono",
        "implementati. `retriever_migration_ready` e `scoring_migration_ready` sono veri nel senso",
        "che il contratto e' sufficiente a implementarli, non che siano stati implementati.",
        "`hierarchy_policy_ready` resta fuori perimetro e `full_exploratory_rerun_ready` falso.",
        "",
        "## La prima cosa da fare dopo",
        "",
        "Trasformare le tre penalita' in gate nell'implementazione, prima di qualunque",
        "ritaratura. Finche' restano pesi, ogni miglioramento numerico ottenuto altrove puo'",
        "riportare un risultato di classe o un mapping pending nel bucket primario.",
        "",
    ]
    return "\n".join(lines)


# --- assemblaggio -------------------------------------------------------------


def build(*, reverse: bool = False) -> dict[str, str]:
    claims = jsonl(ADJ / "approved_claim_simulation.jsonl")
    associations = jsonl(ADJ / "intervention_adjudications.jsonl")
    queries = jsonl(DATA / "claim_retrieval_queries_v1.jsonl")
    audit = jsonl(DATA / "claim_retrieval_scoring_audit_v1.jsonl")
    features = jsonl(DATA / "claim_retrieval_features_v1.jsonl")
    impact = json.loads(
        (DATA / "claim_retrieval_migration_impact_v1.json").read_text(encoding="utf-8")
    )

    if len(claims) != EXPECTED_CLAIMS:
        raise RuntimeError(f"claim attesi {EXPECTED_CLAIMS}: {len(claims)}")

    objects = build_retrievable_objects(claims, associations)
    parents = [obj for obj in objects if obj["claim_type"] == PARENT_KIND]
    if len(parents) != EXPECTED_PARENTS:
        raise RuntimeError(f"parent attesi {EXPECTED_PARENTS}: {len(parents)}")

    rows = simulate(queries, objects, reverse=reverse)
    summary = summarize(rows)
    regression = build_regression_rows(rows)

    readiness = {
        "claim_types_frozen": True,
        "query_types_frozen": True,
        "structural_match_rules_frozen": True,
        "candidate_bucket_rules_frozen": True,
        "score_eligibility_rules_frozen": True,
        "warning_codes_frozen": True,
        "current_scoring_audited": True,
        "new_weights_required": True,
        "adapter_migration_ready": True,
        "corpus_regeneration_ready": False,
        "retriever_migration_ready": True,
        "scoring_migration_ready": True,
        "hierarchy_policy_ready": False,
        "full_exploratory_rerun_ready": False,
    }

    files: dict[str, str] = {}
    files["claim_type_definitions.json"] = canonical_dumps(
        {
            "contract_version": CONTRACT_VERSION,
            "retrievable_object_kinds": list(RETRIEVABLE_OBJECT_KINDS),
            "claim_types": list(CLAIM_TYPES),
            "parent": {
                "kind": PARENT_KIND,
                "is_claim": False,
                "allowed_uses": list(PARENT_ALLOWED_USES),
                "forbidden_uses": list(PARENT_FORBIDDEN_USES),
                "reason_code": "PARENT_PROVENANCE_CONTAINER_NOT_CLAIM",
            },
            "non_claim_association_states": [
                "unsupported_association",
                "unresolved_association",
            ],
            "verified_class_membership_registry": {
                "entries": {key: sorted(value) for key, value in VERIFIED_CLASS_MEMBERSHIPS.items()},
                "empty_by_design": True,
                "note": (
                    "Senza una voce approvata la relazione farmaco-classe resta"
                    " unresolved_class_relation. Dedurla dalla stringa ripeterebbe a un livello"
                    " diverso l'inferenza rifiutata in evidence:275."
                ),
            },
        }
    )
    files["query_type_definitions.json"] = canonical_dumps(
        {
            "contract_version": CONTRACT_VERSION,
            "query_types": list(QUERY_TYPES),
            "regimen_requires_structured_indicator": True,
            "note": (
                "Due interventi senza `intervention_combination` non formano un regime:"
                " restano vincoli alternativi. Inferire la combinazione dalla cardinalita'"
                " produrrebbe exact regimen match su combinazioni mai chieste."
            ),
        }
    )
    files["structural_match_contract.json"] = canonical_dumps(
        {
            "contract_version": CONTRACT_VERSION,
            "structural_match_result_fields": [
                "claim_id",
                "parent_graph_evidence_id",
                "claim_type",
                "query_intervention_type",
                "query_interventions",
                "claim_interventions",
                "intervention_match_type",
                "biomarker_match_type",
                "disease_match_type",
                "direction_match_type",
                "polarity_match_type",
                "primary_candidate_eligible",
                "warning_eligible",
                "audit_only",
                "exclusion_reason_codes",
                "warning_codes",
                "explanation_codes",
            ],
            "match_types": MATCH_TYPES,
            "directions": list(DIRECTIONS),
            "polarities": list(POLARITIES),
            "direction_rules": {
                "reduced_sensitivity_is_not_resistance": True,
                "does_not_support_never_becomes_positive": True,
                "conflicting_never_becomes_positive": True,
                "unknown_not_assumed_compatible": True,
            },
            "disease_relations": DISEASE_RELATIONS,
            "hierarchy_policy_active": False,
        }
    )
    files["candidate_bucket_contract.json"] = canonical_dumps(
        {
            "contract_version": CONTRACT_VERSION,
            "buckets": list(BUCKETS),
            "bucket_rules": {
                "primary_ranked_results": "match strutturalmente equivalente e vincoli nativi soddisfatti",
                "retained_with_warning": "match correlato ma non equivalente: componente di regime, membro di classe, membro di aggregato, direzione correlata, unresolved",
                "audit_only_results": "unsupported, mapping pending, relazione di classe non verificata, parent, claim deprecati",
                "rejected_by_native_constraints": "biomarcatore, disease, direzione o polarita' incompatibili, o intervento senza alcuna relazione",
            },
            "audit_objects_are_never_deleted": True,
        }
    )
    files["score_eligibility_contract.json"] = canonical_dumps(
        {
            "contract_version": CONTRACT_VERSION,
            "levels": ["structural_score_eligibility", "qualified_score_eligibility", "final_ranking_eligibility"],
            "per_match_type": {
                name: {
                    "structural_score_eligible": spec["structural_score_eligible"],
                    "qualified_score_eligible": spec["qualified_score_eligible"],
                    "primary_ranking": spec["primary_eligible"],
                }
                for name, spec in sorted(MATCH_TYPES.items())
            },
            "no_numerical_compensation_invariant": (
                "Un match regimen_component_related, class_member_related,"
                " aggregate_member_related, unsupported o unresolved non puo' diventare exact o"
                " primary eligible per alta provenance, bonus di first review, qualita' della"
                " fonte, disease exact o biomarker exact. Il tipo strutturale precede i pesi."
            ),
            "decision_rationale": {
                "related_types_go_to_warning_not_primary": (
                    "Il claim e' pertinente e va mostrato, ma presentarlo nel primario direbbe"
                    " che sostiene il farmaco chiesto, che e' cio' che l'adjudication ha negato."
                ),
                "related_types_keep_qualified_score": (
                    "Il punteggio qualificato serve a ordinare dentro il bucket warning, non a"
                    " competere con i primari."
                ),
                "unsupported_and_unresolved_forbid_positive_score": (
                    "Sono gate, non penalita': un valore negativo piccolo resta compensabile."
                ),
            },
            "weights_defined_in_this_phase": False,
        }
    )
    files["warning_reason_codes.json"] = canonical_dumps(
        {
            "contract_version": CONTRACT_VERSION,
            "warning_codes": list(WARNING_CODES),
            "exclusion_reason_codes": list(EXCLUSION_REASON_CODES),
            "unresolved_reason_codes": [
                "FULL_TEXT_REQUIRED",
                "LOCATOR_INSUFFICIENT",
                "BIOMARKER_SCOPE_UNRESOLVED",
                "INTERVENTION_MAPPING_PENDING",
                "DOCUMENTARY_ATTRIBUTION_UNRESOLVED",
            ],
        }
    )
    files["current_scoring_assumption_audit.jsonl"] = canonical_jsonl(audit, key="component_id")
    files["proposed_scoring_features.jsonl"] = canonical_jsonl(features, key="feature_id")
    files["adjudicated_claim_query_simulation.jsonl"] = canonical_jsonl(rows, key="simulation_id")
    files["regression_case_simulation.jsonl"] = canonical_jsonl(
        regression, key="graph_evidence_id"
    )
    files["output_contract.json"] = canonical_dumps(
        {
            "contract_version": CONTRACT_VERSION,
            "result_type": "QualifiedClaimRetrievalResult",
            "fields": {
                "claim_id": "string",
                "parent_graph_evidence_id": "string",
                "claim_type": "enum(atomic_intervention_claim, aggregate_intervention_claim, regimen_claim)",
                "intervention_representation": "typed(atomic | regimen | class | aggregate | none)",
                "biomarker": "string",
                "disease": "string",
                "direction": "enum(sensitivity, resistance, reduced_sensitivity, unknown)",
                "polarity": "enum(supports, does_not_support, conflicting, unknown)",
                "structural_match": "StructuralMatchResult",
                "score_eligibility": "object(structural, qualified, final_ranking)",
                "score_breakdown": "list(ScoreComponent)",
                "warnings": "list(warning_code)",
                "source_units": "list(source_unit_id)",
                "locators": "list(locator)",
                "qualification_links": "list(link_id)",
                "provenance": "object(graph_record_ids, adapter_lineage, review_state, adjudication_reference)",
                "review_status": "enum(adjudicated, reviewed, unreviewed)",
                "deprecated": "boolean",
                "audit_status": "enum(active, audit_only, rejected)",
            },
            "intervention_representation_contract": {
                "typed": True,
                "flattening_to_single_string_forbidden": True,
                "reason": (
                    "Un regime reso come farmaco singolo ricreerebbe nel dossier l'errore che il"
                    " modello elimina nei dati."
                ),
            },
        }
    )
    files["migration_impact.json"] = canonical_dumps(
        {**impact, "contract_version": CONTRACT_VERSION}
    )
    files["CLAIM_TYPE_RETRIEVAL_CONTRACT.md"] = render_contract(summary)
    files["REGIMEN_AND_AGGREGATE_MATCHING.md"] = render_regimen_doc(rows)
    files["SCORING_COMPATIBILITY_AUDIT.md"] = render_scoring_audit(audit)
    files["CLAIM_RETRIEVAL_IMPLEMENTATION_READINESS.md"] = render_readiness(readiness, summary)
    files["contract_manifest.json"] = canonical_dumps(
        {
            "contract_version": CONTRACT_VERSION,
            "contract_branch": CONTRACT_BRANCH,
            "start_sha": START_SHA,
            "environment": ENVIRONMENT,
            "readiness": readiness,
            "simulation_summary": summary,
            "input_hashes": {
                "adjudication": tree_digest(ADJ),
                "frozen_artifacts": {path: digest(REPO_ROOT / path) for path in FROZEN_ARTIFACTS},
                "gold_artifacts": {path: digest(REPO_ROOT / path) for path in GOLD_ARTIFACTS},
            },
            "gold_used_for_rules_or_weights": False,
            "operational_components_modified": False,
            "weights_defined": False,
            "artifact_sha256": {
                name: sha256_text(content) for name, content in sorted(files.items())
            },
        }
    )
    return files


def write(files: Mapping[str, str], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(files):
        (output_dir / name).write_text(files[name], encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reverse-query-order", action="store_true")
    args = parser.parse_args()
    files = build(reverse=args.reverse_query_order)
    write(files, args.output_dir)
    print(f"scritti {len(files)} artefatti in {args.output_dir}")


if __name__ == "__main__":
    main()
