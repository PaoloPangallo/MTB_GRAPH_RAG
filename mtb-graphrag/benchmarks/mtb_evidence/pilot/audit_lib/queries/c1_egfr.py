"""C1 - EGFR L858R, prima linea in malattia avanzata.

L'audit stabilisce soltanto **quali qualificatori sono presenti** nei record del
grafo. Non decide la raccomandazione clinica, non elimina fonti perche' non
applicabili, e non attribuisce ad alcuna fonte un'applicabilita' che il gold assegna
per proprio conto.

I record vengono classificati strutturalmente in first_line_advanced,
adjuvant_resected, post_progression_t790m, insufficient_context, other. La
classificazione e' esplicitamente euristica: lo schema non ha campi per setting,
linea o stadio, quindi l'unica fonte e' il testo di `evidence_statement` piu' il nome
del profilo molecolare.
"""

from __future__ import annotations

from typing import Any

from ..classify import (
    ADJUVANT_RESECTED,
    FIRST_LINE_ADVANCED,
    POST_PROGRESSION_T790M,
    TEXT_HEURISTIC,
    classify_setting,
    mentions,
)
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

CASE_ID = "PILOT-C1-EGFR-L858R-CONTEXT"
GENE = "EGFR"
VARIANT = "L858R"
RESISTANCE_VARIANT = "T790M"

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

EVIDENCE_FOR_DRUG = (
    "MATCH (mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence)-[:TARGETS_DRUG]->(d:Drug) "
    "WHERE toLower(d.drug_name) IN $drug_names "
    "RETURN mp.name AS molecular_profile, e.evidence_id AS evidence_id, "
    "e.significance AS significance, e.evidence_direction AS evidence_direction, "
    "e.disease AS disease, e.citation_id AS citation_id, "
    "e.evidence_statement AS evidence_statement, d.drug_name AS drug "
    "ORDER BY evidence_id"
)

EVIDENCE_BY_PMID = (
    "MATCH (e:Evidence) WHERE any(c IN e.citation_id WHERE c IN $pmid_strings) "
    "OPTIONAL MATCH (mp:MolecularProfile)-[:HAS_EVIDENCE]->(e) "
    "OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug) "
    "RETURN mp.name AS molecular_profile, e.evidence_id AS evidence_id, "
    "e.significance AS significance, e.evidence_direction AS evidence_direction, "
    "e.disease AS disease, e.citation_id AS citation_id, "
    "e.evidence_statement AS evidence_statement, d.drug_name AS drug "
    "ORDER BY evidence_id, drug"
)


def _classify_record(record: dict[str, Any], claim: GraphClaim) -> dict[str, Any]:
    """Classifica un record, usando statement e nome del profilo.

    Il profilo va incluso perche' `EGFR L858R AND EGFR T790M` identifica il contesto
    post-progressione anche quando lo statement non lo dice a parole.
    """
    statement = str(record.get("evidence_statement") or "")
    profile = str(record.get("molecular_profile") or "")
    classification = classify_setting(statement)
    label = classification.label
    spans = list(classification.matched_spans)

    if mentions(RESISTANCE_VARIANT, profile) or mentions(RESISTANCE_VARIANT, statement):
        label = POST_PROGRESSION_T790M
        spans.append(RESISTANCE_VARIANT)

    return {
        "record_id": claim.record_id,
        "evidence_id": record.get("evidence_id"),
        "molecular_profile": profile,
        "drug": claim.drug,
        "disease": claim.disease,
        "citation_id": list(claim.pmids),
        "structural_class": label,
        "classification_basis": TEXT_HEURISTIC,
        "matched_spans": sorted(set(spans)),
        "mentions_t790m": mentions(RESISTANCE_VARIANT, f"{profile} {statement}"),
        "mentions_l858r": mentions(VARIANT, f"{profile} {statement}"),
    }


def run(client: GraphClient, case: GoldCase, alias_table: dict[str, str]) -> CaseOutcome:
    outcome = CaseOutcome(case_id=CASE_ID)
    expected_pmid_texts = list(norm_pmid_set(case.expected_pmids))
    expected_pmids = [int(p) for p in expected_pmid_texts]
    expected_ncts = list(norm_nct_set(case.expected_nct_ids))
    expected_drugs = [norm_drug(d, alias_table) for d in case.expected_therapies]

    gene = outcome.add(
        run_query(client, "gene_node", GENE_NODE, {"gene": GENE},
                  warn_if_empty=f"nodo Gene {GENE} assente")
    )
    outcome.add(run_query(client, "profiles_by_gene", PROFILES_BY_GENE, {"gene": GENE}))
    profiles = outcome.add(
        run_query(client, "profiles_containing_l858r", PROFILES_WITH_VARIANT,
                  {"variant_upper": VARIANT})
    )
    profiles_t790m = outcome.add(
        run_query(client, "profiles_containing_t790m", PROFILES_WITH_VARIANT,
                  {"variant_upper": RESISTANCE_VARIANT})
    )
    evidence_variant = outcome.add(
        run_query(client, "evidence_containing_l858r", EVIDENCE_WITH_VARIANT,
                  {"variant_upper": VARIANT})
    )
    evidence_drug = outcome.add(
        run_query(client, "evidence_for_osimertinib", EVIDENCE_FOR_DRUG,
                  {"drug_names": expected_drugs})
    )
    evidence_pmid = outcome.add(
        run_query(
            client, "evidence_citing_expected_pmids", EVIDENCE_BY_PMID,
            {"pmid_strings": expected_pmid_texts},
            warn_if_empty="nessun record di evidenza cita i PMID attesi",
        )
    )
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
    outcome.add(run_query(client, "trials_by_gene", TRIALS_BY_GENE, {"gene": GENE}))

    claims: list[GraphClaim] = []
    classified: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in (
        list(evidence_variant.records) + list(evidence_drug.records) + list(evidence_pmid.records)
    ):
        enriched = dict(record)
        enriched.setdefault("record_id", f"evidence:{record.get('evidence_id')}")
        claim = graph_claim_from_record(enriched, alias_table=alias_table)
        key = (claim.record_id, claim.drug)
        if key in seen:
            continue
        seen.add(key)
        claims.append(claim)
        classified.append(_classify_record(enriched, claim))

    outcome.graph_claims = claims

    buckets: dict[str, list[dict[str, Any]]] = {}
    for entry in classified:
        buckets.setdefault(entry["structural_class"], []).append(entry)
    outcome.buckets = dict(sorted(buckets.items()))

    outcome.found_therapies = {c.drug for c in claims if c.drug}
    discovery = pmid_discovery(
        publications.records,
        list(evidence_variant.records) + list(evidence_drug.records)
        + list(evidence_pmid.records),
        expected_pmid_texts,
    )
    outcome.found_pmids = set(discovery["found"])
    outcome.found_nct_ids = {n for record in trials.records
                             for n in norm_nct_set(record.get("nct_id"))}

    outcome.entities = {
        "pmid_discovery": {k: v for k, v in discovery.items() if k != "found"},
        "gene": [dict(r) for r in gene.records],
        "profiles_with_l858r": [dict(r) for r in profiles.records],
        "profiles_with_t790m": [dict(r) for r in profiles_t790m.records],
        "expected_drugs_found": [dict(r) for r in drugs.records],
        "structural_classification": classified,
        "class_counts": {name: len(items) for name, items in outcome.buckets.items()},
        "classification_disclaimer": (
            "Classificazione euristica su testo: lo schema non modella setting, linea "
            "di terapia, stadio ne' resezione. L'audit constata i qualificatori "
            "presenti e non formula alcuna raccomandazione clinica."
        ),
    }
    outcome.sources = collect_sources(outcome.results)

    if not outcome.buckets.get(FIRST_LINE_ADVANCED):
        outcome.warnings.append(
            "nessun record classificabile come first_line_advanced: il contesto "
            "direttamente applicabile al caso non e' rappresentato nello snapshot"
        )
    if outcome.buckets.get(ADJUVANT_RESECTED):
        outcome.warnings.append(
            f"{len(outcome.buckets[ADJUVANT_RESECTED])} record in setting adiuvante/resecato: "
            "conservati e classificati, non eliminati"
        )
    if outcome.buckets.get(POST_PROGRESSION_T790M):
        outcome.warnings.append(
            f"{len(outcome.buckets[POST_PROGRESSION_T790M])} record post-progressione T790M: "
            "conservati e classificati, non eliminati"
        )
    return outcome
