"""Identificazione e fingerprint dello snapshot Neo4j.

Lo snapshot del progetto non ha un hash ufficiale: e' stato costruito in modo
incrementale con `LOAD CSV` da `import.cypher`, senza dump ne' version stamp. Senza
un identificatore riproducibile non si puo' dire *contro quale grafo* il gold sia
stato annotato, e quindi non si puo' congelare nulla.

Il fingerprint calcolato qui e' derivato da statistiche stabili: conteggi per label,
conteggi per tipo di relazione, totali e min/max degli identificatori stabili. Non e'
un hash del contenuto - due grafi diversi con le stesse statistiche collidono - ma e'
riproducibile, verificabile e sufficiente a rilevare che lo snapshot e' cambiato.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .connection import describe_connection
from .graph_client import GraphClient
from .schema import collect_counts, collect_server_info
from .serialize import canonical_json, fingerprint

# Identificatori stabili per label: quelli con un constraint di unicita' o comunque
# assegnati dalla sorgente, non generati da Neo4j.
STABLE_IDENTIFIERS: tuple[tuple[str, str], ...] = (
    ("Gene", "entrez_id"),
    ("Variant", "variant_id"),
    ("MolecularProfile", "molecular_profile_id"),
    ("Evidence", "evidence_id"),
    ("Drug", "concept_id"),
    ("Publication", "pmid"),
    ("ClinicalTrial", "nct_id"),
)


def identifier_range_query(label: str, prop: str) -> str:
    return (
        f"MATCH (n:`{label}`) WHERE n.`{prop}` IS NOT NULL "
        f"RETURN min(n.`{prop}`) AS min_value, max(n.`{prop}`) AS max_value, "
        f"count(n.`{prop}`) AS present_count"
    )


def collect_identifier_ranges(client: GraphClient) -> dict[str, Any]:
    ranges: dict[str, Any] = {}
    for label, prop in STABLE_IDENTIFIERS:
        cypher = identifier_range_query(label, prop)
        rows = client.run(cypher, {})
        row = rows[0] if rows else {}
        ranges[f"{label}.{prop}"] = {
            "min": _plain(row.get("min_value")),
            "max": _plain(row.get("max_value")),
            "present_count": row.get("present_count", 0),
            "cypher": cypher,
        }
    return dict(sorted(ranges.items()))


def _plain(value: Any) -> Any:
    """Riduce un valore a una forma stabile e serializzabile."""
    if value is None or isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


def build_fingerprint_statistics(client: GraphClient) -> dict[str, Any]:
    """Statistiche che alimentano il fingerprint. Solo dati riproducibili."""
    counts = collect_counts(client)
    return {
        "nodes_by_label": counts["nodes_by_label"],
        "relationships_by_type": counts["relationships_by_type"],
        "total_nodes": counts["total_nodes"],
        "total_relationships": counts["total_relationships"],
        "identifier_ranges": {
            key: {k: v for k, v in value.items() if k != "cypher"}
            for key, value in collect_identifier_ranges(client).items()
        },
    }


def compute_fingerprint(statistics: dict[str, Any]) -> str:
    return fingerprint(statistics)


def git_commit_sha(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


# Provenienza dei dati caricati nel grafo. Non esiste un dump: il grafo nasce da
# `import.cypher` piu' un secondo loader per il livello disease/publication.
SNAPSHOT_PROVENANCE: dict[str, Any] = {
    "loading_method": "LOAD CSV via Cypher, nessun dump neo4j-admin",
    "loaders": [
        "import.cypher (root del workspace)",
        "data_expl/DatasetTESI/Dataset TESI/Clean_Graph_Data/carica_disease_publication.cypher",
        "estrai_disease_publication_neo4j.py (root del workspace)",
    ],
    "csv_directory": "data_expl/DatasetTESI/Dataset TESI/Clean_Graph_Data/",
    "archive": "DatasetTESI/Dataset TESI/Clean_Graph_Data.zip",
    "known_limitation": (
        "I CSV sorgente hanno mtime in tre ondate distinte (2025-05-27, 2025-05-31, "
        "2025-06-02): il grafo non corrisponde a un singolo istante di snapshot ma a "
        "un caricamento incrementale. Nessun manifest, checksum o release id di "
        "CIViC/DGIdb e' versionato nel repository."
    ),
    "official_hash_available": False,
}


def build_snapshot_manifest(
    client: GraphClient,
    *,
    repo_root: Path,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Manifest completo dello snapshot, privo di credenziali."""
    statistics = build_fingerprint_statistics(client)
    digest = compute_fingerprint(statistics)
    connection = describe_connection()
    server = collect_server_info(client)
    counts = statistics

    return {
        "audit_timestamp_utc": timestamp or datetime.now(timezone.utc).isoformat(),
        "commit_sha": git_commit_sha(repo_root),
        "neo4j_uri": connection["uri"],
        "neo4j_user": connection["user"],
        "database_name": connection["database"],
        "database_reported_by_server": server["database_reported"],
        "neo4j_version": server["neo4j_version"],
        "neo4j_edition": server["edition"],
        "nodes_by_label": counts["nodes_by_label"],
        "relationships_by_type": counts["relationships_by_type"],
        "total_nodes": counts["total_nodes"],
        "total_relationships": counts["total_relationships"],
        "identifier_ranges": collect_identifier_ranges(client),
        "snapshot_fingerprint": {
            "algorithm": "sha256(canonical_json(statistics))",
            "value": digest,
            "statistics": statistics,
            "canonical_json_preview": canonical_json(statistics)[:400],
            "note": (
                "Fingerprint derivato, non hash ufficiale: identifica una configurazione "
                "statistica dello snapshot, non il suo contenuto byte per byte."
            ),
        },
        "provenance": SNAPSHOT_PROVENANCE,
        "queries_used": {
            "counts": {
                "nodes_total": "MATCH (n) RETURN count(n) AS count",
                "relationships_total": "MATCH ()-[r]->() RETURN count(r) AS count",
                "nodes_by_label": "MATCH (n:`<label>`) RETURN count(n) AS count",
                "relationships_by_type": "MATCH ()-[r:`<type>`]->() RETURN count(r) AS count",
            },
            "identifier_ranges": {
                f"{label}.{prop}": identifier_range_query(label, prop)
                for label, prop in STABLE_IDENTIFIERS
            },
            "server": {
                "components": (
                    "CALL dbms.components() YIELD name, versions, edition "
                    "RETURN name, versions, edition"
                ),
                "database": "CALL db.info() YIELD name RETURN name",
            },
        },
        "credentials_policy": (
            "Nessuna password o token viene registrato. L'URI e' sanitizzato da "
            "eventuali userinfo prima della scrittura."
        ),
    }
