"""N1 - RMI2, prova negativa sullo snapshot congelato.

Il gold e' un'astensione limitata allo snapshot: "NON DETERMINABILE nello snapshot
congelato". Non afferma che nessuna evidenza esista al mondo, quindi la prova da
archiviare e' esattamente il traversal deterministico eseguito e il suo risultato
vuoto, insieme a fingerprint e timestamp.

Se anche un solo percorso terapeutico venisse trovato, il caso non sarebbe un
no-answer valido. In quel caso lo script lo dichiara freeze blocker invece di
archiviare un negativo: nascondere il risultato renderebbe la prova inutile.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..gold import GoldCase
from ..graph_client import GraphClient
from ..normalize import norm_drug, norm_nct_set, norm_pmid_set
from .base import GENE_NODE, TRIALS_BY_GENE, CaseOutcome, collect_sources, run_query

CASE_ID = "PILOT-N1-RMI2-SNAPSHOT"
GENE = "RMI2"

# Il percorso previsto dal traversal deterministico gene -> evidenza -> terapia.
DETERMINISTIC_PATH = (
    "MATCH (g:Gene {hugo_symbol: $gene})-[:HAS_VARIANT]->(v:Variant)"
    "-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence)"
    "-[:TARGETS_DRUG]->(d:Drug) "
    "RETURN g.hugo_symbol AS gene, v.variant_name AS variant, "
    "mp.name AS molecular_profile, e.evidence_id AS evidence_id, "
    "e.significance AS significance, e.disease AS disease, "
    "e.citation_id AS citation_id, d.drug_name AS drug"
)

VARIANTS = (
    "MATCH (g:Gene {hugo_symbol: $gene})-[:HAS_VARIANT]->(v:Variant) "
    "RETURN v.variant_id AS variant_id, v.variant_name AS variant_name"
)

PROFILES = (
    "MATCH (g:Gene {hugo_symbol: $gene})-[:HAS_VARIANT]->(:Variant)"
    "-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile) "
    "RETURN DISTINCT mp.molecular_profile_id AS molecular_profile_id, mp.name AS name"
)

EVIDENCE = (
    "MATCH (g:Gene {hugo_symbol: $gene})-[:HAS_VARIANT]->(:Variant)"
    "-[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence) "
    "RETURN e.evidence_id AS evidence_id, e.significance AS significance, "
    "e.disease AS disease, e.citation_id AS citation_id"
)

INTERACTS_DRUGS = (
    "MATCH (g:Gene {hugo_symbol: $gene})-[r:INTERACTS_WITH]->(d:Drug) "
    "RETURN d.drug_name AS drug, r.interaction_type AS interaction_type, "
    "r.source_db AS source_db"
)

ANY_RELATIONSHIP = (
    "MATCH (g:Gene {hugo_symbol: $gene})-[r]-(n) "
    "RETURN type(r) AS relationship_type, labels(n) AS neighbour_labels, count(*) AS count"
)

PUBLICATIONS_VIA_EVIDENCE = (
    "MATCH (g:Gene {hugo_symbol: $gene})-[:HAS_VARIANT]->(:Variant)"
    "-[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence)"
    "-[:CITED_IN]->(p:Publication) "
    "RETURN p.pmid AS pmid, p.citation_text AS citation_text"
)

ALIAS_LOOKUP = (
    "MATCH (g:Gene) WHERE g.hugo_symbol = $gene OR $gene IN coalesce(g.aliases, []) "
    "RETURN g.hugo_symbol AS hugo_symbol, g.entrez_id AS entrez_id, "
    "g.aliases AS aliases, g.categories AS categories, "
    "g.is_oncokb_annotated AS is_oncokb_annotated"
)


def run(client: GraphClient, case: GoldCase, alias_table: dict[str, str]) -> CaseOutcome:
    outcome = CaseOutcome(case_id=CASE_ID)

    gene = outcome.add(
        run_query(client, "gene_node", GENE_NODE, {"gene": GENE},
                  warn_if_empty=f"nodo Gene {GENE} assente dallo snapshot")
    )
    aliases = outcome.add(run_query(client, "gene_and_aliases", ALIAS_LOOKUP, {"gene": GENE}))
    path = outcome.add(
        run_query(client, "deterministic_gene_to_therapy_path", DETERMINISTIC_PATH, {"gene": GENE})
    )
    variants = outcome.add(run_query(client, "variants", VARIANTS, {"gene": GENE}))
    profiles = outcome.add(run_query(client, "molecular_profiles", PROFILES, {"gene": GENE}))
    evidence = outcome.add(run_query(client, "clinical_evidence", EVIDENCE, {"gene": GENE}))
    interacts = outcome.add(
        run_query(client, "interacts_with_drugs", INTERACTS_DRUGS, {"gene": GENE})
    )
    publications = outcome.add(
        run_query(client, "publications_via_evidence", PUBLICATIONS_VIA_EVIDENCE, {"gene": GENE})
    )
    trials = outcome.add(run_query(client, "trials_by_gene", TRIALS_BY_GENE, {"gene": GENE}))
    relationships = outcome.add(
        run_query(client, "any_relationship", ANY_RELATIONSHIP, {"gene": GENE})
    )

    outcome.found_therapies = {
        norm_drug(record.get("drug"), alias_table) for record in path.records
    } | {norm_drug(record.get("drug"), alias_table) for record in interacts.records}
    outcome.found_therapies.discard("")
    outcome.found_pmids = {
        p for record in publications.records for p in norm_pmid_set(record.get("pmid"))
    }
    outcome.found_nct_ids = {
        n for record in trials.records for n in norm_nct_set(record.get("nct_id"))
    }

    gene_present = bool(gene.records)
    outcome.entities = {
        "gene_present": gene_present,
        "gene": [dict(r) for r in gene.records],
        "aliases": [dict(r) for r in aliases.records],
        "variant_count": len(variants.records),
        "molecular_profile_count": len(profiles.records),
        "evidence_count": len(evidence.records),
        "therapeutic_path_count": len(path.records),
        "interacts_with_drug_count": len(interacts.records),
        "trial_count": len(trials.records),
        "relationships": [dict(r) for r in relationships.records],
    }
    outcome.sources = collect_sources(outcome.results)
    outcome.buckets = {"therapeutic_paths": [dict(r) for r in path.records]}

    if not gene_present:
        outcome.warnings.append(
            "il nodo Gene RMI2 non esiste: l'astensione e' dovuta all'assenza del gene, "
            "non a un traversal vuoto su un gene presente"
        )
    elif not relationships.records:
        outcome.warnings.append(
            "il nodo Gene RMI2 esiste ma non ha alcuna relazione: l'astensione e' un "
            "negativo genuino del traversal"
        )

    categories = [
        category
        for record in gene.records
        for category in (record.get("gene", {}) or {}).get("categories", []) or []
    ]
    if categories:
        outcome.warnings.append(
            f"il nodo RMI2 porta le categorie {sorted(set(categories))} pur non avendo "
            "alcun percorso terapeutico: la proprieta' non implica evidenza clinica ed e' "
            "una trappola per qualunque euristica che la usasse come segnale"
        )
        outcome.entities["gene_categories"] = sorted(set(categories))

    if path.records or interacts.records:
        outcome.blockers.append(
            f"trovati {len(path.records)} percorsi gene->evidenza->terapia e "
            f"{len(interacts.records)} interazioni gene-farmaco per RMI2: il caso NON e' "
            "un no-answer valido e non puo' essere congelato come astensione"
        )

    return outcome


def build_negative_path_proof(
    outcome: CaseOutcome,
    *,
    snapshot_fingerprint: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Prova negativa archiviabile: query, parametri, risultato, conteggio, hash."""
    proofs = [
        {
            "query_name": result.name,
            "cypher": result.cypher,
            "params": dict(result.params),
            "record_count": result.count,
            "records": [dict(record) for record in result.records],
        }
        for result in outcome.results
    ]
    therapeutic = next(
        (p for p in proofs if p["query_name"] == "deterministic_gene_to_therapy_path"), None
    )
    path_count = therapeutic["record_count"] if therapeutic else -1
    return {
        "case_id": outcome.case_id,
        "gene": GENE,
        "timestamp_utc": timestamp or datetime.now(timezone.utc).isoformat(),
        "snapshot_fingerprint": snapshot_fingerprint,
        "primary_query": therapeutic,
        "supporting_queries": [p for p in proofs if p is not therapeutic],
        "therapeutic_path_count": path_count,
        "is_valid_negative": path_count == 0 and not outcome.blockers,
        "blockers": list(outcome.blockers),
        "warnings": list(outcome.warnings),
        "interpretation": (
            "Astensione limitata allo snapshot: il traversal deterministico "
            "gene -> variante -> profilo -> evidenza -> farmaco non restituisce alcun "
            "percorso. Non e' un'affermazione sull'assenza di evidenza nel mondo."
        ),
    }
