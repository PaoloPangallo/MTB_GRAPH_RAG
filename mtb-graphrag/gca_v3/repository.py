"""Selezione esplicita della versione del repository delle candidate (§17).

La pipeline attuale usa ``graph_candidate_repository/2.0``. v3 **non** la
sostituisce silenziosamente: la versione è scelta da una variabile di ambiente
e il default resta ``2.0`` finché v3 non supera l'audit e i test di regressione.

    GRAPH_CANDIDATE_REPOSITORY_VERSION=2.0|3.0
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_VERSION = "2.0"
SUPPORTED_VERSIONS = ("2.0", "3.0")

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE = REPO_ROOT / "benchmarks" / "mtb_evidence" / "document_grounded_claims" / "graph_candidate_repository"


class UnsupportedRepositoryVersion(ValueError):
    """Sollevata per una versione non riconosciuta, invece di ricadere sul default.

    Un fallback silenzioso su 2.0 farebbe passare per una run v3 una run che
    v3 non ha mai usato.
    """


def configured_version() -> str:
    version = (os.getenv("GRAPH_CANDIDATE_REPOSITORY_VERSION") or DEFAULT_VERSION).strip()
    if version not in SUPPORTED_VERSIONS:
        raise UnsupportedRepositoryVersion(
            f"GRAPH_CANDIDATE_REPOSITORY_VERSION={version!r} non supportata; "
            f"attese: {', '.join(SUPPORTED_VERSIONS)}"
        )
    return version


def candidates_path(version: str | None = None) -> Path:
    return BASE / (version or configured_version()) / "candidates.jsonl"


def manifest_path(version: str | None = None) -> Path:
    return BASE / (version or configured_version()) / "manifest.json"


def describe() -> dict[str, object]:
    version = configured_version()
    return {
        "version": version,
        "is_default": version == DEFAULT_VERSION,
        "candidates_path": str(candidates_path(version)),
        "runtime_default_changed_to_v3": DEFAULT_VERSION == "3.0",
    }
