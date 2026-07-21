"""Ispezione dello schema reale del grafo.

Serve a impedire che le query dell'audit inventino campi. Prima di interrogare i
quattro casi si raccolgono label, tipi di relazione, proprieta' osservate, indici,
constraint ed esempi di record, e si salva tutto in `schema_inventory.json`.
"""

from __future__ import annotations

import re
from typing import Any

from .graph_client import GraphClient

# I nomi di label e tipo di relazione arrivano dal database, ma vengono comunque
# validati prima di essere interpolati in una query: interpolare identificatori
# senza controllo e' il modo classico di aprire un'iniezione Cypher.
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

Q_LABELS = "CALL db.labels() YIELD label RETURN label ORDER BY label"
Q_REL_TYPES = (
    "CALL db.relationshipTypes() YIELD relationshipType "
    "RETURN relationshipType ORDER BY relationshipType"
)
Q_INDEXES = "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties"
Q_CONSTRAINTS = "SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties"
Q_COMPONENTS = (
    "CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition"
)
Q_DATABASE = "CALL db.info() YIELD name RETURN name"


def _safe(identifier: str) -> str:
    if not _SAFE_IDENTIFIER.match(identifier):
        raise ValueError(f"identificatore non sicuro dal database: {identifier!r}")
    return identifier


def node_count_query(label: str) -> str:
    return f"MATCH (n:`{_safe(label)}`) RETURN count(n) AS count"


def rel_count_query(rel_type: str) -> str:
    return f"MATCH ()-[r:`{_safe(rel_type)}`]->() RETURN count(r) AS count"


def property_keys_query(label: str) -> str:
    return (
        f"MATCH (n:`{_safe(label)}`) WITH keys(n) AS ks LIMIT 500 "
        "UNWIND ks AS k RETURN DISTINCT k AS property ORDER BY property"
    )


def sample_query(label: str, limit: int = 2) -> str:
    return f"MATCH (n:`{_safe(label)}`) RETURN n AS node LIMIT {int(limit)}"


def _scalar(client: GraphClient, cypher: str, key: str, default: Any = None) -> Any:
    rows = client.run(cypher, {})
    return rows[0][key] if rows else default


def collect_labels(client: GraphClient) -> list[str]:
    return [row["label"] for row in client.run(Q_LABELS, {})]


def collect_relationship_types(client: GraphClient) -> list[str]:
    return [row["relationshipType"] for row in client.run(Q_REL_TYPES, {})]


def collect_counts(client: GraphClient) -> dict[str, Any]:
    """Conteggi per label e per tipo di relazione, piu' i totali."""
    labels = collect_labels(client)
    rel_types = collect_relationship_types(client)
    nodes_by_label = {
        label: _scalar(client, node_count_query(label), "count", 0) for label in labels
    }
    rels_by_type = {
        rel_type: _scalar(client, rel_count_query(rel_type), "count", 0)
        for rel_type in rel_types
    }
    return {
        "nodes_by_label": dict(sorted(nodes_by_label.items())),
        "relationships_by_type": dict(sorted(rels_by_type.items())),
        "total_nodes": _scalar(client, "MATCH (n) RETURN count(n) AS count", "count", 0),
        "total_relationships": _scalar(
            client, "MATCH ()-[r]->() RETURN count(r) AS count", "count", 0
        ),
    }


def collect_server_info(client: GraphClient) -> dict[str, Any]:
    components = client.run(Q_COMPONENTS, {})
    kernel = next((c for c in components if c.get("name") == "Neo4j Kernel"), None)
    versions = (kernel or {}).get("versions") or []
    return {
        "neo4j_version": versions[0] if versions else "unknown",
        "edition": (kernel or {}).get("edition", "unknown"),
        "components": components,
        "database_reported": _scalar(client, Q_DATABASE, "name", "unknown"),
    }


def build_schema_inventory(client: GraphClient) -> dict[str, Any]:
    """Inventario completo dello schema, pronto per la serializzazione."""
    labels = collect_labels(client)
    rel_types = collect_relationship_types(client)
    properties = {
        label: [row["property"] for row in client.run(property_keys_query(label), {})]
        for label in labels
    }
    samples = {
        label: client.run(sample_query(label), {}) for label in labels
    }
    return {
        "labels": labels,
        "relationship_types": rel_types,
        "properties_by_label": properties,
        "indexes": client.run(Q_INDEXES, {}),
        "constraints": client.run(Q_CONSTRAINTS, {}),
        "server": collect_server_info(client),
        "samples_by_label": samples,
        "example_records": _example_records(client),
        "queries_used": {
            "labels": Q_LABELS,
            "relationship_types": Q_REL_TYPES,
            "indexes": Q_INDEXES,
            "constraints": Q_CONSTRAINTS,
            "components": Q_COMPONENTS,
            "database": Q_DATABASE,
            "node_count_template": "MATCH (n:`<label>`) RETURN count(n) AS count",
            "relationship_count_template": (
                "MATCH ()-[r:`<type>`]->() RETURN count(r) AS count"
            ),
            "property_keys_template": (
                "MATCH (n:`<label>`) WITH keys(n) AS ks LIMIT 500 UNWIND ks AS k "
                "RETURN DISTINCT k AS property ORDER BY property"
            ),
        },
        "schema_notes": [
            "Publication.pmid e' un INTEGER; Evidence.citation_id e' un array di stringhe.",
            "Evidence non ha proprieta' per setting, linea di terapia, stadio o "
            "esposizione precedente: quei qualificatori non sono modellati.",
            "Evidence.disease e' testo libero, non una relazione verso il nodo Disease.",
            "evidence_level mescola le scale CIViC (A, B) e OncoKB (LEVEL_1, LEVEL_2).",
        ],
    }


_EXAMPLE_QUERIES: dict[str, str] = {
    "civic_evidence": (
        "MATCH (e:Evidence) WHERE e.source_type = 'PubMed' "
        "RETURN e AS evidence LIMIT 3"
    ),
    "evidence_with_drug": (
        "MATCH (mp:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence)-[:TARGETS_DRUG]->(d:Drug) "
        "RETURN mp.name AS molecular_profile, e.evidence_id AS evidence_id, "
        "e.significance AS significance, d.drug_name AS drug LIMIT 3"
    ),
    "resistance_evidence": (
        "MATCH (e:Evidence) WHERE e.significance = 'Resistance' "
        "RETURN e.evidence_id AS evidence_id, e.disease AS disease, "
        "e.citation_id AS citation_id LIMIT 3"
    ),
    "clinical_trial": (
        "MATCH (t:ClinicalTrial) RETURN t.nct_id AS nct_id, t.title AS title, "
        "t.phase AS phase, t.status AS status LIMIT 3"
    ),
}


def _example_records(client: GraphClient) -> dict[str, Any]:
    return {
        name: {"cypher": cypher, "records": client.run(cypher, {})}
        for name, cypher in _EXAMPLE_QUERIES.items()
    }
