"""Infrastruttura comune alle query per caso.

Ogni query e' nominata, parametrizzata e conservata insieme al proprio risultato:
il `query_manifest.json` di ciascun caso deve permettere di rieseguire l'audit
esattamente com'e' stato eseguito.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..compare import GraphClaim
from ..graph_client import GraphClient


@dataclass(frozen=True)
class QueryResult:
    name: str
    cypher: str
    params: Mapping[str, Any]
    records: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        return len(self.records)

    def as_manifest_entry(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cypher": self.cypher,
            "params": dict(self.params),
            "record_count": self.count,
            "completeness_warnings": list(self.warnings),
        }


def run_query(
    client: GraphClient,
    name: str,
    cypher: str,
    params: Mapping[str, Any] | None = None,
    *,
    warn_if_empty: str | None = None,
) -> QueryResult:
    """Esegue una query e ne conserva testo, parametri e risultato completo."""
    bound = dict(params or {})
    records = tuple(client.run(cypher, bound))
    warnings: list[str] = []
    if not records and warn_if_empty:
        warnings.append(warn_if_empty)
    return QueryResult(
        name=name, cypher=cypher, params=bound, records=records, warnings=tuple(warnings)
    )


@dataclass
class CaseOutcome:
    """Tutto cio' che l'audit di un caso produce prima del confronto con il gold."""

    case_id: str
    results: list[QueryResult] = field(default_factory=list)
    graph_claims: list[GraphClaim] = field(default_factory=list)
    found_therapies: set[str] = field(default_factory=set)
    found_pmids: set[str] = field(default_factory=set)
    found_nct_ids: set[str] = field(default_factory=set)
    entities: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    buckets: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def add(self, result: QueryResult) -> QueryResult:
        self.results.append(result)
        self.warnings.extend(result.warnings)
        return result

    def raw_records(self) -> list[dict[str, Any]]:
        """Tutti i record grezzi, etichettati con la query che li ha prodotti."""
        return [
            {"query": result.name, "record_index": index, "record": dict(record)}
            for result in self.results
            for index, record in enumerate(result.records)
        ]

    def query_manifest(self) -> list[dict[str, Any]]:
        return [result.as_manifest_entry() for result in self.results]


# Query riutilizzate da piu' casi.

GENE_NODE = "MATCH (g:Gene {hugo_symbol: $gene}) RETURN g AS gene"

PUBLICATIONS_BY_PMID = (
    "MATCH (p:Publication) WHERE p.pmid IN $pmids "
    "RETURN p.pmid AS pmid, p.citation_text AS citation_text, p.year AS year, "
    "p.source_type AS source_type ORDER BY pmid"
)

TRIALS_BY_NCT = (
    "MATCH (t:ClinicalTrial) WHERE t.nct_id IN $nct_ids "
    "RETURN t.nct_id AS nct_id, t.title AS title, t.phase AS phase, "
    "t.status AS status, t.conditions AS conditions ORDER BY nct_id"
)

TRIALS_BY_GENE = (
    "MATCH (t:ClinicalTrial)-[:ASSOCIATED_GENE]->(g:Gene {hugo_symbol: $gene}) "
    "OPTIONAL MATCH (t)-[:TESTS_DRUG]->(d:Drug) "
    "RETURN t.nct_id AS nct_id, t.title AS title, t.phase AS phase, t.status AS status, "
    "collect(DISTINCT d.drug_name) AS drugs ORDER BY nct_id"
)

DRUGS_BY_NAME = (
    "MATCH (d:Drug) WHERE toLower(d.drug_name) IN $drug_names "
    "RETURN d.drug_name AS drug_name, d.concept_id AS concept_id, d.approved AS approved "
    "ORDER BY drug_name"
)

# Traversal deterministico gene -> variante -> profilo -> evidenza -> farmaco.
EVIDENCE_BY_GENE = (
    "MATCH (g:Gene {hugo_symbol: $gene})-[:HAS_VARIANT]->(v:Variant)"
    "-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence) "
    "OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug) "
    "RETURN mp.name AS molecular_profile, mp.molecular_profile_id AS molecular_profile_id, "
    "v.variant_name AS variant, e.evidence_id AS evidence_id, "
    "e.significance AS significance, e.evidence_direction AS evidence_direction, "
    "e.evidence_level AS evidence_level, e.evidence_type AS evidence_type, "
    "e.disease AS disease, e.citation_id AS citation_id, "
    "e.evidence_statement AS evidence_statement, e.source_type AS source_type, "
    "e.variant_origin AS variant_origin, e.rating AS rating, "
    "d.drug_name AS drug, d.concept_id AS drug_concept_id "
    "ORDER BY evidence_id, drug"
)

EVIDENCE_BY_PROFILE_PATTERN = (
    "MATCH (mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence) "
    "WHERE toUpper(mp.name) CONTAINS $pattern "
    "OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug) "
    "RETURN mp.name AS molecular_profile, mp.molecular_profile_id AS molecular_profile_id, "
    "e.evidence_id AS evidence_id, e.significance AS significance, "
    "e.evidence_direction AS evidence_direction, e.evidence_level AS evidence_level, "
    "e.evidence_type AS evidence_type, e.disease AS disease, "
    "e.citation_id AS citation_id, e.evidence_statement AS evidence_statement, "
    "e.source_type AS source_type, d.drug_name AS drug "
    "ORDER BY evidence_id, drug"
)

PROFILES_BY_GENE = (
    "MATCH (g:Gene {hugo_symbol: $gene})-[:HAS_VARIANT]->(v:Variant)"
    "-[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile) "
    "RETURN DISTINCT mp.name AS molecular_profile, "
    "mp.molecular_profile_id AS molecular_profile_id, v.variant_name AS variant "
    "ORDER BY molecular_profile, variant"
)


def pmid_discovery(
    publication_records: Sequence[Mapping[str, Any]],
    evidence_records: Sequence[Mapping[str, Any]],
    expected: Sequence[str],
) -> dict[str, Any]:
    """Distingue i due modi in cui un PMID puo' essere presente nello snapshot.

    Un PMID puo' esistere come nodo `Publication` oppure comparire solo dentro
    `Evidence.citation_id`. Sono situazioni diverse: nel secondo caso la fonte e'
    comunque recuperabile dal grafo, e trattarla come assente sarebbe un falso
    negativo dell'audit.
    """
    from ..normalize import norm_pmid_set

    as_node = {p for record in publication_records for p in norm_pmid_set(record.get("pmid"))}
    as_citation = {
        p for record in evidence_records for p in norm_pmid_set(record.get("citation_id"))
    }
    expected_set = set(expected)
    # Un PMID di meno di sette cifre e' anteriore agli anni '80. Ne esistono di
    # legittimi, ma in un grafo di evidenza oncologica moderna sono quasi sempre un
    # difetto di ingestione, e vanno segnalati a chi rivede le fonti.
    implausible = sorted(p for p in as_citation if len(p) < 7)
    return {
        "as_publication_node": sorted(as_node),
        "as_evidence_citation": sorted(as_citation),
        "found": as_node | as_citation,
        "expected_only_via_citation": sorted((as_citation - as_node) & expected_set),
        "expected_absent_entirely": sorted(expected_set - as_node - as_citation),
        "implausibly_short_pmids": implausible,
    }


def collect_sources(results: Sequence[QueryResult]) -> dict[str, Any]:
    """Estrae PMID e NCT da tutti i record, con la query di provenienza."""
    from ..normalize import norm_nct_set, norm_pmid_set

    pmids: dict[str, list[str]] = {}
    ncts: dict[str, list[str]] = {}
    for result in results:
        for record in result.records:
            for pmid in norm_pmid_set(record.get("citation_id")) + norm_pmid_set(
                record.get("pmid")
            ):
                pmids.setdefault(pmid, [])
                if result.name not in pmids[pmid]:
                    pmids[pmid].append(result.name)
            for nct in norm_nct_set(record.get("nct_id")):
                ncts.setdefault(nct, [])
                if result.name not in ncts[nct]:
                    ncts[nct].append(result.name)
    return {
        "pmids": {key: sorted(value) for key, value in sorted(pmids.items())},
        "nct_ids": {key: sorted(value) for key, value in sorted(ncts.items())},
    }
