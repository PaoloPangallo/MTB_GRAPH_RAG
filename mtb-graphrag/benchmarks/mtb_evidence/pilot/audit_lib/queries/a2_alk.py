"""A2 - ALK G1202R, mutazione singola dopo ALK-TKI di seconda generazione.

Il caso vive o muore sulla separazione fra G1202R singola e mutazioni composte:
rispetto a lorlatinib hanno significato opposto, e il gold include proprio una claim
di guardrail su G1202R/L1196M che *non* si applica al caso singolo. I record vengono
quindi raccolti in bucket separati e non vengono mai fusi, cosi' come restano
separati i record di sensibilita' da quelli di resistenza.
"""

from __future__ import annotations

from typing import Any

from ..classify import classify_variant_form
from ..compare import GraphClaim, graph_claim_from_record
from ..gold import GoldCase
from ..graph_client import GraphClient
from ..normalize import norm_drug, norm_nct_set, norm_pmid_set
from .base import (
    DRUGS_BY_NAME,
    GENE_NODE,
    PROFILES_BY_GENE,
    PUBLICATIONS_BY_PMID,
    TRIALS_BY_GENE,
    TRIALS_BY_NCT,
    CaseOutcome,
    collect_sources,
    pmid_discovery,
    run_query,
)

CASE_ID = "PILOT-A2-ALK-G1202R"
GENE = "ALK"
VARIANT = "G1202R"

PROFILES_WITH_VARIANT = (
    "MATCH (mp:MolecularProfile) WHERE toUpper(mp.name) CONTAINS $variant_upper "
    "RETURN DISTINCT mp.name AS molecular_profile, "
    "mp.molecular_profile_id AS molecular_profile_id ORDER BY molecular_profile"
)

EVIDENCE_WITH_VARIANT = (
    "MATCH (mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence) "
    "WHERE toUpper(mp.name) CONTAINS $variant_upper "
    "OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug) "
    "RETURN mp.name AS molecular_profile, mp.molecular_profile_id AS molecular_profile_id, "
    "e.evidence_id AS evidence_id, e.significance AS significance, "
    "e.evidence_direction AS evidence_direction, e.evidence_level AS evidence_level, "
    "e.evidence_type AS evidence_type, e.disease AS disease, "
    "e.citation_id AS citation_id, e.evidence_statement AS evidence_statement, "
    "e.source_type AS source_type, d.drug_name AS drug ORDER BY evidence_id, drug"
)

EVIDENCE_BY_SIGNIFICANCE = (
    "MATCH (mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence) "
    "WHERE toUpper(mp.name) CONTAINS $variant_upper AND e.significance = $significance "
    "OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug) "
    "RETURN mp.name AS molecular_profile, e.evidence_id AS evidence_id, "
    "e.significance AS significance, e.evidence_direction AS evidence_direction, "
    "e.disease AS disease, e.citation_id AS citation_id, "
    "e.evidence_statement AS evidence_statement, d.drug_name AS drug "
    "ORDER BY evidence_id, drug"
)

RESISTANCE_FOR_GENE = (
    "MATCH (g:Gene {hugo_symbol: $gene})-[:HAS_VARIANT]->(v:Variant)"
    "-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence) "
    "WHERE e.significance = 'Resistance' "
    "OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug) "
    "RETURN v.variant_name AS variant, mp.name AS molecular_profile, "
    "e.evidence_id AS evidence_id, e.significance AS significance, "
    "e.evidence_direction AS evidence_direction, e.disease AS disease, "
    "e.citation_id AS citation_id, e.evidence_statement AS evidence_statement, "
    "d.drug_name AS drug ORDER BY evidence_id, drug"
)


def run(client: GraphClient, case: GoldCase, alias_table: dict[str, str]) -> CaseOutcome:
    outcome = CaseOutcome(case_id=CASE_ID)
    expected_pmids = [int(p) for p in norm_pmid_set(case.expected_pmids)]
    expected_ncts = list(norm_nct_set(case.expected_nct_ids))
    expected_drugs = [norm_drug(d, alias_table) for d in case.expected_therapies]

    gene = outcome.add(
        run_query(client, "gene_node", GENE_NODE, {"gene": GENE},
                  warn_if_empty=f"nodo Gene {GENE} assente")
    )
    outcome.add(run_query(client, "profiles_by_gene", PROFILES_BY_GENE, {"gene": GENE}))
    profiles = outcome.add(
        run_query(
            client, "profiles_containing_g1202r", PROFILES_WITH_VARIANT,
            {"variant_upper": VARIANT},
            warn_if_empty="nessun profilo molecolare contiene G1202R",
        )
    )
    evidence_all = outcome.add(
        run_query(client, "evidence_containing_g1202r", EVIDENCE_WITH_VARIANT,
                  {"variant_upper": VARIANT})
    )
    sensitivity = outcome.add(
        run_query(
            client, "evidence_sensitivity_response", EVIDENCE_BY_SIGNIFICANCE,
            {"variant_upper": VARIANT, "significance": "Sensitivity/Response"},
        )
    )
    resistance = outcome.add(
        run_query(
            client, "evidence_resistance", EVIDENCE_BY_SIGNIFICANCE,
            {"variant_upper": VARIANT, "significance": "Resistance"},
        )
    )
    outcome.add(run_query(client, "resistance_for_gene", RESISTANCE_FOR_GENE, {"gene": GENE}))
    drugs = outcome.add(
        run_query(client, "expected_drugs_present", DRUGS_BY_NAME, {"drug_names": expected_drugs})
    )
    publications = outcome.add(
        run_query(
            client, "expected_publications", PUBLICATIONS_BY_PMID, {"pmids": expected_pmids},
            warn_if_empty="nessuno dei PMID attesi e' presente come nodo Publication",
        )
    )
    trials = outcome.add(
        run_query(
            client, "expected_trials", TRIALS_BY_NCT, {"nct_ids": expected_ncts},
            warn_if_empty="nessuno degli NCT attesi e' presente come nodo ClinicalTrial",
        )
    )
    trials_gene = outcome.add(run_query(client, "trials_by_gene", TRIALS_BY_GENE, {"gene": GENE}))

    single: list[dict[str, Any]] = []
    compound: list[dict[str, Any]] = []
    sensitivity_bucket: list[dict[str, Any]] = []
    resistance_bucket: list[dict[str, Any]] = []
    claims: list[GraphClaim] = []
    seen: set[tuple[str, str]] = set()

    for record in list(evidence_all.records) + list(sensitivity.records) + list(
        resistance.records
    ):
        enriched = dict(record)
        enriched.setdefault("record_id", f"evidence:{record.get('evidence_id')}")
        claim = graph_claim_from_record(enriched, alias_table=alias_table)
        key = (claim.record_id, claim.drug)
        if key in seen:
            continue
        seen.add(key)
        claims.append(claim)
        payload = claim.as_dict()
        (compound if claim.is_compound else single).append(payload)
        if claim.relation.startswith("resistance"):
            resistance_bucket.append(payload)
        elif claim.relation.startswith("sensitivity"):
            sensitivity_bucket.append(payload)

    outcome.graph_claims = claims
    # I bucket restano separati per costruzione: nessun passaggio successivo li unisce.
    outcome.buckets = {
        "single_mutation": single,
        "compound_mutations": compound,
        "sensitivity_records": sensitivity_bucket,
        "resistance_records": resistance_bucket,
        "trials": [dict(record) for record in trials_gene.records],
    }

    # Solo i record su mutazione singola contribuiscono alle terapie del caso.
    outcome.found_therapies = {c.drug for c in claims if c.drug and not c.is_compound}
    discovery = pmid_discovery(
        publications.records,
        list(evidence_all.records) + list(sensitivity.records) + list(resistance.records),
        norm_pmid_set(case.expected_pmids),
    )
    outcome.found_pmids = set(discovery["found"])
    outcome.found_nct_ids = {n for record in trials.records
                             for n in norm_nct_set(record.get("nct_id"))}

    profile_forms = [
        {
            "molecular_profile": record.get("molecular_profile"),
            "is_compound": classify_variant_form(record.get("molecular_profile")).is_compound,
            "variants": list(
                classify_variant_form(record.get("molecular_profile")).variants
            ),
            "classification_basis": "text_heuristic",
        }
        for record in profiles.records
    ]
    outcome.entities = {
        "pmid_discovery": {k: v for k, v in discovery.items() if k != "found"},
        "gene": [dict(r) for r in gene.records],
        "profiles_with_g1202r": profile_forms,
        "expected_drugs_found": [dict(r) for r in drugs.records],
        "expected_drugs_missing": sorted(
            set(expected_drugs)
            - {norm_drug(r.get("drug_name"), alias_table) for r in drugs.records}
        ),
        "single_mutation_count": len(single),
        "compound_mutation_count": len(compound),
    }
    outcome.sources = collect_sources(outcome.results)

    if compound:
        outcome.warnings.append(
            f"{len(compound)} record riguardano mutazioni composte: conservati in un bucket "
            "separato e non applicati al caso a mutazione singola"
        )
    if not single:
        outcome.warnings.append(
            "nessun record su G1202R singola: tutti i profili trovati sono composti"
        )
    outcome.warnings.append(
        "l'esposizione precedente a un ALK-TKI di seconda generazione non e' modellata "
        "dallo schema: ricavabile solo per euristica testuale"
    )
    return outcome
