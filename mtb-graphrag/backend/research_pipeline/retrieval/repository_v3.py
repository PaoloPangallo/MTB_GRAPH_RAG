"""Loader tipizzato di ``graph_candidate_repository/3.0``.

Il loader v2 non può leggere record v3: v3 non ha il campo ``direction`` e le
sue candidate ``evidence-to-intervention`` rappresentano un **intervento**, non
un farmaco. Interpretarle con il parser v2 significherebbe leggere una unità di
regime come se fosse una monoterapia.

Nessun fallback silenzioso: una versione non supportata o un contratto non
valido sollevano, invece di ricadere su v2. Ricadere su v2 farebbe passare per
una run v3 una run che v3 non ha mai usato.
"""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..data_access import data_root

SUPPORTED_VERSIONS = ("2.0", "3.0")
DEFAULT_VERSION = "2.0"
EXPECTED_CONTRACT_VERSION = "graph-candidate-assertion/3.0"

_DGC = "benchmarks/mtb_evidence/document_grounded_claims"

#: Enum ammessi dal contratto v3. Un valore fuori enum è un contratto non valido.
_ALIGNMENT_STATES = {
    "SOURCE_ALIGNED", "SOURCE_DOES_NOT_SUPPORT", "SOURCE_CONTRADICTS",
    "SOURCE_NEUTRAL", "SOURCE_ALIGNMENT_UNCLEAR", "SOURCE_ALIGNMENT_NOT_AVAILABLE",
}
_POLARITIES = {
    "SUPPORTS_ASSERTION", "DOES_NOT_SUPPORT_ASSERTION", "CONTRADICTS_ASSERTION",
    "NEUTRAL_OR_NO_DIFFERENCE", "UNCLEAR", "NOT_REPORTED", "UNMAPPED_SOURCE_VALUE",
}
_STRUCTURES = {
    "SINGLE_AGENT", "COMBINATION_CONFIRMED", "ALTERNATIVE_CONFIRMED",
    "SEQUENTIAL_CONFIRMED", "MULTI_COMPONENT_UNRESOLVED", "UNKNOWN",
}
_PARSE_STATES = {
    "ATOMIC", "PARSED_EXACT", "PARSED_WITH_WARNINGS", "AMBIGUOUS_OPERATOR",
    "UNSUPPORTED_EXPRESSION", "MALFORMED_EXPRESSION", "MISSING",
}


class RepositoryVersionUnsupported(ValueError):
    """Versione non riconosciuta. Nessun fallback: la run si ferma."""


class RepositoryContractInvalid(ValueError):
    """Il repository non rispetta il contratto dichiarato."""


def configured_version() -> str:
    version = (os.getenv("GRAPH_CANDIDATE_REPOSITORY_VERSION") or DEFAULT_VERSION).strip()
    if version not in SUPPORTED_VERSIONS:
        raise RepositoryVersionUnsupported(
            f"GRAPH_CANDIDATE_REPOSITORY_VERSION={version!r} non supportata; "
            f"attese: {', '.join(SUPPORTED_VERSIONS)}. Nessun fallback automatico."
        )
    return version


def repository_dir(version: str | None = None) -> Path:
    return data_root() / _DGC / "graph_candidate_repository" / (version or configured_version())


def candidates_path_for(version: str | None = None) -> Path:
    return repository_dir(version) / "candidates.jsonl"


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(version: str = "3.0", *, verify_repository_hash: bool = True) -> dict[str, Any]:
    """Verifica manifest, versione di schema e hash del repository."""
    directory = repository_dir(version)
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        raise RepositoryContractInvalid(f"manifest assente: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    contract = manifest.get("contract_version")
    if contract != EXPECTED_CONTRACT_VERSION:
        raise RepositoryContractInvalid(
            f"contract_version {contract!r}, attesa {EXPECTED_CONTRACT_VERSION!r}")

    if verify_repository_hash:
        actual = _sha_file(directory / "candidates.jsonl")
        declared = manifest.get("repository_hash")
        if declared and actual != declared:
            raise RepositoryContractInvalid(
                f"repository_hash non corrisponde: atteso {declared}, calcolato {actual}")
    return manifest


def validate_record(record: dict[str, Any]) -> None:
    """Valida un singolo record v3 contro gli enum e le strutture del contratto."""
    def _require(field: str) -> Any:
        if field not in record:
            raise RepositoryContractInvalid(f"campo mancante: {field}")
        return record[field]

    if _require("contract_version") != EXPECTED_CONTRACT_VERSION:
        raise RepositoryContractInvalid(
            f"record con contract_version {record['contract_version']!r}")

    if _require("source_alignment_status") not in _ALIGNMENT_STATES:
        raise RepositoryContractInvalid(
            f"source_alignment_status fuori enum: {record['source_alignment_status']!r}")
    if _require("source_support_polarity") not in _POLARITIES:
        raise RepositoryContractInvalid(
            f"source_support_polarity fuori enum: {record['source_support_polarity']!r}")
    if _require("intervention_structure") not in _STRUCTURES:
        raise RepositoryContractInvalid(
            f"intervention_structure fuori enum: {record['intervention_structure']!r}")
    if _require("alteration_parse_status") not in _PARSE_STATES:
        raise RepositoryContractInvalid(
            f"alteration_parse_status fuori enum: {record['alteration_parse_status']!r}")

    if not _require("source_path_ids"):
        raise RepositoryContractInvalid(f"lineage assente per {record.get('candidate_id')}")

    ast = record.get("alteration_expression_ast")
    if ast is not None and not isinstance(ast, dict):
        raise RepositoryContractInvalid("alteration_expression_ast non è un oggetto")
    if ast is not None and "node_type" not in ast:
        raise RepositoryContractInvalid("alteration_expression_ast senza node_type")

    # Invariante di polarità: una fonte che non sostiene non può risultare allineata.
    if (record["source_support_polarity"] == "DOES_NOT_SUPPORT_ASSERTION"
            and record["source_alignment_status"] == "SOURCE_ALIGNED"):
        raise RepositoryContractInvalid(
            f"{record.get('candidate_id')}: DOES_NOT_SUPPORT marcato SOURCE_ALIGNED")


@lru_cache(maxsize=1)
def load_v3_candidates() -> dict[str, dict[str, Any]]:
    """Carica e valida il repository v3. Cache invalidabile con ``cache_clear()``."""
    validate_manifest("3.0")
    path = candidates_path_for("3.0")
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        validate_record(record)
        out[record["candidate_id"]] = record
    return out


@lru_cache(maxsize=1)
def v2_to_v3_mapping() -> dict[str, list[str]]:
    """``candidate_v2_id -> [candidate_v3_id]``, dal mapping di migrazione."""
    path = repository_dir("3.0") / "v2_mapping.jsonl"
    if not path.exists():
        raise RepositoryContractInvalid(f"mapping v2→v3 assente: {path}")
    out: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("v2_candidate_id") and row.get("v3_candidate_id"):
            out.setdefault(row["v2_candidate_id"], []).append(row["v3_candidate_id"])
    return out


def bridge_bundles_to_v3(
    bundles_by_v2_candidate: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Riporta gli EvidenceBundle dagli id v2 agli id v3.

    Gli EvidenceBundle congelati sono chiavizzati sugli id **v2**: senza questo
    ponte nessuna candidate v3 avrebbe documenti e il retrieval v3 non
    troverebbe mai nulla. Il ponte usa il mapping di migrazione, che è un
    artefatto di primo livello del repository v3 — non un'euristica.

    Un bundle di una candidate v2 confluita in un'unità di regime viene
    associato all'unità: è la stessa relazione, rappresentata diversamente.
    """
    mapping = v2_to_v3_mapping()
    out: dict[str, list[dict[str, Any]]] = {}
    for v2_id, bundles in bundles_by_v2_candidate.items():
        for v3_id in mapping.get(v2_id, []):
            for bundle in bundles:
                if bundle not in out.setdefault(v3_id, []):
                    out[v3_id].append(bundle)
    return out


def describe() -> dict[str, Any]:
    version = configured_version()
    return {
        "version": version,
        "is_default": version == DEFAULT_VERSION,
        "runtime_default_changed_to_v3": DEFAULT_VERSION == "3.0",
        "candidates_path": str(candidates_path_for(version)),
        "supported_versions": list(SUPPORTED_VERSIONS),
        "fallback_enabled": False,
    }
