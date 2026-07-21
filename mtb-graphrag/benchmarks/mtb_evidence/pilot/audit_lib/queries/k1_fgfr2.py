"""K1 - FGFR2 fusion/rearrangement in colangiocarcinoma intraepatico.

Tre distinzioni che l'audit non deve appiattire, prese dalla definizione del caso:
fusione/riarrangiamento non e' mutazione generica; intraepatico non e' un
colangiocarcinoma qualunque; prima linea non e' malattia gia' trattata. Le prime due
sono verificabili sui dati e vengono separate qui; la terza non e' modellata dallo
schema e viene solo segnalata.
"""

from __future__ import annotations

from typing import Any

from ..classify import classify_setting
from ..compare import GraphClaim, graph_claim_from_record
from ..disease import DIFFERENT_SPECIFICITY, disease_relation, split_disease
from ..gold import GoldCase
from ..graph_client import GraphClient
from ..normalize import norm_drug, norm_nct_set, norm_pmid_set, norm_text
from .base import (
    DRUGS_BY_NAME,
    EVIDENCE_BY_GENE,
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

CASE_ID = "PILOT-K1-FGFR2-iCCA"
GENE = "FGFR2"

# Marcatori di fusione/riarrangiamento nel nome del profilo. `::` e' la notazione
# CIViC per le fusioni.
FUSION_MARKERS = ("FUSION", "REARRANGE", "::")

PROFILES_FUSION = (
    "MATCH (mp:MolecularProfile) WHERE toUpper(mp.name) CONTAINS $gene_upper "
    "AND (toUpper(mp.name) CONTAINS 'FUSION' OR toUpper(mp.name) CONTAINS 'REARRANGE' "
    "OR mp.name CONTAINS '::') "
    "RETURN DISTINCT mp.name AS molecular_profile, "
    "mp.molecular_profile_id AS molecular_profile_id ORDER BY molecular_profile"
)

EVIDENCE_FUSION = (
    "MATCH (mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence) "
    "WHERE toUpper(mp.name) CONTAINS $gene_upper "
    "AND (toUpper(mp.name) CONTAINS 'FUSION' OR toUpper(mp.name) CONTAINS 'REARRANGE' "
    "OR mp.name CONTAINS '::') "
    "OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug) "
    "RETURN mp.name AS molecular_profile, e.evidence_id AS evidence_id, "
    "e.significance AS significance, e.evidence_direction AS evidence_direction, "
    "e.evidence_level AS evidence_level, e.disease AS disease, "
    "e.citation_id AS citation_id, e.evidence_statement AS evidence_statement, "
    "d.drug_name AS drug ORDER BY evidence_id, drug"
)

DISEASES_FOR_GENE = (
    "MATCH (g:Gene {hugo_symbol: $gene})-[:HAS_VARIANT]->(:Variant)"
    "-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence) "
    "RETURN DISTINCT e.disease AS disease, count(*) AS evidence_count "
    "ORDER BY disease"
)

DRUG_EVIDENCE = (
    "MATCH (e:Evidence)-[:TARGETS_DRUG]->(d:Drug) "
    "WHERE toLower(d.drug_name) IN $drug_names "
    "OPTIONAL MATCH (mp:MolecularProfile)-[:HAS_EVIDENCE]->(e) "
    "RETURN d.drug_name AS drug, mp.name AS molecular_profile, "
    "e.evidence_id AS evidence_id, e.significance AS significance, "
    "e.evidence_direction AS evidence_direction, e.disease AS disease, "
    "e.citation_id AS citation_id, e.evidence_statement AS evidence_statement "
    "ORDER BY drug, evidence_id"
)


def _is_fusion_profile(name: object) -> bool:
    upper = str(name or "").upper()
    return any(marker in upper for marker in FUSION_MARKERS)


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
    profiles_fusion = outcome.add(
        run_query(
            client, "profiles_fusion_or_rearrangement", PROFILES_FUSION,
            {"gene_upper": GENE},
            warn_if_empty="nessun profilo di fusione/riarrangiamento per FGFR2",
        )
    )
    evidence_all = outcome.add(
        run_query(client, "evidence_by_gene_traversal", EVIDENCE_BY_GENE, {"gene": GENE})
    )
    evidence_fusion = outcome.add(
        run_query(client, "evidence_fusion_profiles_only", EVIDENCE_FUSION, {"gene_upper": GENE})
    )
    diseases = outcome.add(run_query(client, "diseases_for_gene", DISEASES_FOR_GENE, {"gene": GENE}))
    drugs = outcome.add(
        run_query(client, "expected_drugs_present", DRUGS_BY_NAME, {"drug_names": expected_drugs})
    )
    drug_evidence = outcome.add(
        run_query(client, "evidence_for_expected_drugs", DRUG_EVIDENCE,
                  {"drug_names": expected_drugs})
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

    # Claim del grafo: si usano i record di evidenza sui profili di fusione e quelli
    # dei farmaci attesi, tenuti distinti dai profili di mutazione generica.
    claims: list[GraphClaim] = []
    fusion_bucket: list[dict[str, Any]] = []
    non_fusion_bucket: list[dict[str, Any]] = []
    for record in list(evidence_all.records) + list(evidence_fusion.records) + list(
        drug_evidence.records
    ):
        enriched = dict(record)
        enriched.setdefault("record_id", f"evidence:{record.get('evidence_id')}")
        claim = graph_claim_from_record(enriched, alias_table=alias_table)
        if not claim.drug:
            continue
        if any(existing.record_id == claim.record_id and existing.drug == claim.drug
               for existing in claims):
            continue
        claims.append(claim)
        target = fusion_bucket if _is_fusion_profile(record.get("molecular_profile")) else (
            non_fusion_bucket
        )
        target.append(claim.as_dict())

    outcome.graph_claims = claims
    outcome.buckets = {
        "fusion_or_rearrangement_profiles": fusion_bucket,
        "non_fusion_profiles": non_fusion_bucket,
    }

    # Terapie raggiunte dal traversal sui soli profili di fusione: e' la popolazione
    # del caso. I farmaci trovati su profili di mutazione generica non contano.
    outcome.found_therapies = {
        claim.drug for claim in claims
        if claim.drug and _is_fusion_profile(claim.raw.get("molecular_profile"))
    }
    discovery = pmid_discovery(
        publications.records,
        list(evidence_all.records) + list(evidence_fusion.records)
        + list(drug_evidence.records),
        norm_pmid_set(case.expected_pmids),
    )
    outcome.found_pmids = set(discovery["found"])
    outcome.found_nct_ids = {n for record in trials.records
                             for n in norm_nct_set(record.get("nct_id"))}

    outcome.entities = {
        "pmid_discovery": {k: v for k, v in discovery.items() if k != "found"},
        "gene": [dict(r) for r in gene.records],
        "fusion_profiles": [dict(r) for r in profiles_fusion.records],
        "expected_drugs_found": [dict(r) for r in drugs.records],
        "expected_drugs_missing": sorted(
            set(expected_drugs)
            - {norm_drug(r.get("drug_name"), alias_table) for r in drugs.records}
        ),
        "diseases_observed": [dict(r) for r in diseases.records],
    }
    outcome.sources = collect_sources(outcome.results)

    if discovery["implausibly_short_pmids"]:
        outcome.warnings.append(
            f"citazioni con PMID implausibilmente corti: "
            f"{discovery['implausibly_short_pmids']}; probabile difetto di ingestione "
            "nel campo citation_id, da verificare prima di usarli come fonte"
        )

    _check_disease_specificity(outcome, case, claims)
    _check_setting_modelling(outcome, evidence_fusion.records)
    return outcome


def _check_disease_specificity(
    outcome: CaseOutcome, case: GoldCase, claims: list[GraphClaim]
) -> None:
    """Segnala i record che parlano di un colangiocarcinoma meno specifico."""
    gold_disease = norm_text(case.disease)
    mismatches: list[dict[str, str]] = []
    for claim in claims:
        if not claim.disease:
            continue
        relation = disease_relation(gold_disease, claim.disease)
        if relation == DIFFERENT_SPECIFICITY:
            mismatches.append(
                {
                    "record_id": claim.record_id,
                    "graph_disease": claim.disease,
                    "gold_disease": gold_disease,
                    "relation": relation,
                }
            )
    if mismatches:
        outcome.warnings.append(
            f"{len(mismatches)} record usano una denominazione di malattia meno specifica "
            f"di '{gold_disease}' (es. colangiocarcinoma generico): non sono equivalenti "
            "e non vengono contati come corrispondenza"
        )
        outcome.entities["disease_specificity_mismatches"] = mismatches
    core = split_disease(gold_disease)
    outcome.entities["gold_disease_parsed"] = {
        "core": core.core,
        "qualifiers": list(core.qualifiers),
    }


def _check_setting_modelling(outcome: CaseOutcome, records: tuple[Any, ...]) -> None:
    """Registra quali qualificatori di setting emergono, e con quale base."""
    classified = [
        {
            "evidence_id": record.get("evidence_id"),
            "setting": classify_setting(record.get("evidence_statement")).label,
            "spans": list(classify_setting(record.get("evidence_statement")).matched_spans),
        }
        for record in records
    ]
    outcome.entities["setting_classification"] = classified
    outcome.warnings.append(
        "linea di terapia, stadio ed esposizione precedente a FGFR-inibitori non sono "
        "modellati dallo schema: ricavabili solo per euristica testuale"
    )
