"""``ExternalCitationCandidate`` — oggetto sperimentale, separato dal repository.

Vincolo architetturale (§14 del protocollo): un risultato OncoKB **non deve mai**
modificare retroattivamente la GraphCandidateAssertion originale, e **non è**
supporto documentale. È una citazione *candidata*, che acquista valore solo dopo
aver attraversato l'intera catena esistente:

``Document Resolution → SourceUnit → Paper Selection → Paper Context Enricher → Validator``

Per questo l'oggetto è definito qui, nel pacchetto di valutazione, e non nei
modelli del runtime: introdurlo nel core equivarrebbe a dichiarare che il
fallback è parte dell'architettura, cosa che questo studio non stabilisce.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

#: Stati di corrispondenza fra la query derivata dalla candidate e la risposta.
MATCH_EXACT = "EXACT_MATCH"
MATCH_PARTIAL = "PARTIAL_MATCH"
MATCH_NONE = "NO_MATCH"
MATCH_NOT_QUERYABLE = "NOT_QUERYABLE"


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ExternalCitationCandidate:
    """Citazione candidata proveniente da una sorgente esterna controllata."""

    external_candidate_id: str
    graph_candidate_id: str
    origin: str
    oncokb_data_version: str | None
    query_gene: str | None
    query_alteration: str | None
    query_disease: str | None
    query_intervention: str | None
    match_level: str
    evidence_level: str | None = None
    citations: list[str] = field(default_factory=list)
    retrieved_at: str | None = None
    raw_response_hash: str | None = None
    provenance: str = "EXTERNAL_CANDIDATE_NOT_DOCUMENTARY_SUPPORT"
    warnings: list[str] = field(default_factory=list)

    #: Invariante: un ExternalCitationCandidate non è mai, di per sé, una prova.
    promoted_to_documentary_support: bool = False

    @classmethod
    def create(cls, graph_candidate_id: str, **kwargs: Any) -> "ExternalCitationCandidate":
        digest = _hash({"graph_candidate_id": graph_candidate_id, **{
            k: v for k, v in kwargs.items() if k.startswith("query_") or k == "origin"
        }})
        return cls(
            external_candidate_id=f"ECC-{digest[:24]}",
            graph_candidate_id=graph_candidate_id,
            **kwargs,
        )

    def validate(self) -> None:
        if self.promoted_to_documentary_support:
            raise ValueError(
                "Un ExternalCitationCandidate non può essere promosso a prova "
                "documentale: deve passare per Document Resolution, SourceUnit, "
                "Paper Selection, Paper Context Enricher e Validator."
            )
        if self.origin != "ONCOKB":
            raise ValueError(f"origin non supportata in questo studio: {self.origin!r}")

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()
