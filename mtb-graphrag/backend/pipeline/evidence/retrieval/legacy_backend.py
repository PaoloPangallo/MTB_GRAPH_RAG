"""Adattatore del retriever operativo dietro il contratto dei backend.

L'adattatore non riscrive niente e non aggiunge niente. Costruisce la query
legacy con la funzione legacy, chiama `QualifiedEvidenceRetriever.retrieve` e
restituisce l'oggetto che quella funzione produce, senza convertirlo.

E' la parte piu' importante del modulo, e vale la pena dirla in negativo: **il
retriever legacy non viene fatto restituire claim V3**. Se lo facesse, la
migrazione sarebbe gia' avvenuta — il percorso operativo produrrebbe oggetti di
un modello che nessuno ha ancora validato clinicamente — e il confronto fra i due
backend non misurerebbe piu' due implementazioni ma una sola vista da due punti.

Il modulo non importa nulla del corpus V3. E' una condizione verificabile e non
una convenzione: `test_retriever_binding` esegue una run legacy in un processo
separato e controlla che ne' il loader promosso ne' il retriever V3 compaiano in
`sys.modules`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.qualified_retrieval_query import (
    QualifiedRetrievalQuery,
    build_query,
)
from backend.pipeline.evidence.qualified_retriever import (
    SUPPORTED_CORPUS_VERSION,
    QualifiedEvidenceRetriever,
    QualifiedRetrievalOutput,
)
from backend.pipeline.evidence.retrieval.backends import BACKEND_LEGACY

REPO_ROOT = Path(__file__).resolve().parents[4]

LEGACY_CORPUS = REPO_ROOT / "benchmarks" / "mtb_evidence" / "v3" / "qualification_corpus_v2"
LEGACY_SCORING_CONFIG = (
    REPO_ROOT / "backend" / "pipeline" / "evidence" / "qualified_retriever_scoring_config.json"
)

# Il retriever legacy non conosce le modalita' di policy del corpus V3: decide
# la malattia con il proprio matcher e non ha un asse su cui una modalita'
# agirebbe. Dichiararlo e' piu' onesto che riportare `strict_verified` come se
# la modalita' fosse stata applicata anche qui.
LEGACY_POLICY_MODE = "legacy_native_matching"


class LegacyEvidenceRetrieverAdapter:
    """Il retriever operativo, esposto con la firma comune dei backend."""

    backend_name = BACKEND_LEGACY

    def __init__(
        self,
        retriever: QualifiedEvidenceRetriever,
        *,
        corpus_dir: Path = LEGACY_CORPUS,
    ) -> None:
        self._retriever = retriever
        self._corpus_dir = Path(corpus_dir)

    @classmethod
    def from_corpus(
        cls,
        corpus_dir: str | Path = LEGACY_CORPUS,
        *,
        scoring_config_path: str | Path = LEGACY_SCORING_CONFIG,
    ) -> "LegacyEvidenceRetrieverAdapter":
        root = Path(corpus_dir)
        return cls(
            QualifiedEvidenceRetriever.from_corpus(
                root, scoring_config_path=scoring_config_path
            ),
            corpus_dir=root,
        )

    # --- identita' ------------------------------------------------------------

    @property
    def repository_version(self) -> str:
        """La versione del corpus legacy, non quella del corpus promosso.

        Riportare qui `qualified_claim_repository/1.4` renderebbe il campo
        inutile proprio nel caso in cui serve: distinguere quale corpus ha
        risposto a una query.
        """
        return SUPPORTED_CORPUS_VERSION

    @property
    def policy_mode(self) -> str:
        return LEGACY_POLICY_MODE

    @property
    def retriever(self) -> QualifiedEvidenceRetriever:
        return self._retriever

    # --- retrieval ------------------------------------------------------------

    def build_native_query(self, query: Mapping[str, Any]) -> QualifiedRetrievalQuery:
        """La query legacy, costruita dalla funzione legacy e da nessun'altra."""
        return build_query(query)

    def retrieve(self, query: Mapping[str, Any]) -> QualifiedRetrievalOutput:
        """L'output legacy, non convertito."""
        return self._retriever.retrieve(self.build_native_query(query))

    # --- osservabilita' -------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        report = self._retriever.validate_corpus()
        return {
            "active_index_has_historical_units": (
                self._retriever.active_index_has_historical_units
            ),
            "backend_name": self.backend_name,
            "corpus_available": self._corpus_dir.is_dir(),
            "corpus_fingerprint": report["qualification_corpus_fingerprint"],
            "counts": {
                key: value for key, value in sorted(report.items()) if isinstance(value, int)
            },
            "healthy": True,
            "policy_mode": self.policy_mode,
            "repository_version": self.repository_version,
            "scoring_config_hash": self._retriever.get_scoring_config_hash(),
        }

    def provenance_summary(self) -> dict[str, Any]:
        manifest = self._retriever.manifest
        return {
            "backend_name": self.backend_name,
            "corpus_dir": self._corpus_dir.name,
            "corpus_version": str(manifest.get("corpus_version") or ""),
            "frozen_kg_snapshot_fingerprint": str(
                manifest.get("frozen_kg_snapshot_fingerprint") or ""
            ),
            "policy_mode": self.policy_mode,
            "qualification_corpus_fingerprint": str(
                manifest.get("qualification_corpus_fingerprint") or ""
            ),
            "reads_promoted_v3_corpus": False,
            "repository_version": self.repository_version,
            "scoring_config_hash": self._retriever.get_scoring_config_hash(),
        }


__all__ = [
    "LEGACY_CORPUS",
    "LEGACY_POLICY_MODE",
    "LEGACY_SCORING_CONFIG",
    "LegacyEvidenceRetrieverAdapter",
]
