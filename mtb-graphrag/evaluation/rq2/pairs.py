"""Dataset delle coppie candidate–PMID e classificazione della provenance.

L'unità di analisi è la **coppia**, non il PMID unico: lo stesso PMID può essere
associato a candidate diverse con qualità diversa, e ridurre subito a PMID unici
cancellerebbe proprio la variabile che RQ2 misura.

Sulla provenance, questo corpus ha una struttura precisa che vale la pena
esplicitare, perché determina l'interpretazione dei risultati:

* l'identificatore con ``scope = "evidence_record"`` proviene da
  ``node_evidence.citation_id``: è la citazione del **record Evidence** stesso;
* l'identificatore con ``scope = "linked_publication"`` proviene da
  ``civic_evidence_publication_links.csv``, ed è anch'esso indicizzato per
  ``evidence_id``.

I due scope non portano quindi due fonti diverse: portano la **stessa** fonte
vista da due tabelle. Ciò che distingue davvero il livello di provenance è la
regola di materializzazione:

``PMID_CANDIDATE_LEVEL``
    regola ``evidence-statement``. Il PMID cita esattamente lo statement che la
    candidate asserisce.

``PMID_PARENT_LEVEL_ONLY``
    regola ``evidence-to-drug``. La candidate afferma una relazione
    biomarcatore→farmaco *derivata* dal record Evidence, e ne eredita il PMID.
    Il paper è la fonte del record padre; che discuta quello specifico farmaco
    nei termini della candidate non è garantito dalla struttura, e in 1 294 casi
    il record padre riguarda più farmaci (cfr. ``REGIMEN_SPLIT`` in RQ1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

#: Un PMID valido è una stringa di sole cifre, senza zeri iniziali significativi.
PMID_RE = re.compile(r"^[1-9]\d*$")

# Stati sintattici / di risoluzione
PMID_INVALID_FORMAT = "PMID_INVALID_FORMAT"
PMID_NOT_FOUND = "PMID_NOT_FOUND"
PMID_RESOLVED_METADATA_ONLY = "PMID_RESOLVED_METADATA_ONLY"
PMID_DOCUMENT_AVAILABLE = "PMID_DOCUMENT_AVAILABLE"
# Stati di provenance
PMID_CANDIDATE_LEVEL = "PMID_CANDIDATE_LEVEL"
PMID_PARENT_LEVEL_ONLY = "PMID_PARENT_LEVEL_ONLY"
# Stati di pertinenza semantica
PMID_EXACT_CONTEXT = "PMID_EXACT_CONTEXT"
PMID_PARTIAL_CONTEXT = "PMID_PARTIAL_CONTEXT"
PMID_OPPOSITE_DIRECTION = "PMID_OPPOSITE_DIRECTION"
PMID_INTERVENTION_MISMATCH = "PMID_INTERVENTION_MISMATCH"
PMID_DISEASE_MISMATCH = "PMID_DISEASE_MISMATCH"
PMID_BIOMARKER_MISMATCH = "PMID_BIOMARKER_MISMATCH"
PMID_NO_EXPLICIT_SUPPORT = "PMID_NO_EXPLICIT_SUPPORT"
PMID_RELEVANCE_UNDETERMINED = "PMID_RELEVANCE_UNDETERMINED"

#: Regole che producono una citazione a livello della candidate stessa.
_CANDIDATE_LEVEL_RULES = {"gca/2.0/evidence-statement"}
#: Regole che ereditano la citazione dal record Evidence padre.
_PARENT_LEVEL_RULES = {"gca/2.0/evidence-to-drug"}


def normalize_pmid(raw: Any) -> tuple[str | None, str | None]:
    """``(pmid_normalizzato, motivo_di_invalidità)``.

    Non ripara valori corrotti: normalizza solo spazi e un eventuale prefisso
    ``PMID:``. Uno zero iniziale o un separatore restano invalidi, perché
    "correggerli" inventerebbe un identificatore che la sorgente non contiene.
    """
    if raw is None:
        return None, "MISSING"
    text = str(raw).strip()
    if not text:
        return None, "EMPTY"
    text = re.sub(r"(?i)^pmid[:\s]*", "", text).strip()
    if not text:
        return None, "EMPTY"
    if re.search(r"[;,]", text):
        return None, "COMPOUND_VALUE"
    if not text.isdigit():
        return None, "NON_NUMERIC"
    if not PMID_RE.match(text):
        return None, "LEADING_ZERO"
    return text, None


def _labels(entities: Iterable[dict] | None, kind: str | None = None) -> list[str]:
    out = []
    for entity in entities or []:
        if kind and entity.get("type") != kind:
            continue
        if entity.get("label"):
            out.append(str(entity["label"]))
    return out


@dataclass
class CandidatePmidPair:
    """Una coppia candidate–PMID, con provenance e contesto clinico."""

    candidate_id: str
    pmid_raw: str
    pmid: str | None
    invalid_reason: str | None
    scopes: list[str]
    rule_id: str
    predicate: str
    provenance_level: str
    disease: list[str] = field(default_factory=list)
    gene: list[str] = field(default_factory=list)
    alteration: list[str] = field(default_factory=list)
    intervention: list[str] = field(default_factory=list)
    direction: str | None = None
    evidence_scope: str | None = None
    evidence_record_ids: list[str] = field(default_factory=list)
    sibling_drug_count: int = 1

    @property
    def syntactically_valid(self) -> bool:
        return self.pmid is not None

    def to_row(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "pmid_raw": self.pmid_raw,
            "pmid": self.pmid or "",
            "syntactically_valid": self.syntactically_valid,
            "invalid_reason": self.invalid_reason or "",
            "scopes": "|".join(self.scopes),
            "rule_id": self.rule_id,
            "predicate": self.predicate,
            "provenance_level": self.provenance_level,
            "disease": "|".join(self.disease),
            "gene": "|".join(self.gene),
            "alteration": "|".join(self.alteration),
            "intervention": "|".join(self.intervention),
            "direction": self.direction or "",
            "evidence_scope": self.evidence_scope or "",
            "evidence_record_ids": "|".join(self.evidence_record_ids),
            "sibling_drug_count": self.sibling_drug_count,
        }


PAIR_FIELDS = [
    "candidate_id", "pmid_raw", "pmid", "syntactically_valid", "invalid_reason",
    "scopes", "rule_id", "predicate", "provenance_level", "disease", "gene",
    "alteration", "intervention", "direction", "evidence_scope",
    "evidence_record_ids", "sibling_drug_count",
]


def provenance_level(rule_id: str) -> str:
    if rule_id in _CANDIDATE_LEVEL_RULES:
        return PMID_CANDIDATE_LEVEL
    if rule_id in _PARENT_LEVEL_RULES:
        return PMID_PARENT_LEVEL_ONLY
    return PMID_RELEVANCE_UNDETERMINED


def build_pairs(
    candidates: Iterable[dict[str, Any]],
    sibling_drug_counts: dict[str, int] | None = None,
) -> list[CandidatePmidPair]:
    """Una riga per coppia (candidate, PMID distinto), con gli scope aggregati."""
    sibling_drug_counts = sibling_drug_counts or {}
    pairs: list[CandidatePmidPair] = []
    for candidate in candidates:
        identifiers = candidate.get("document_identifiers") or []
        by_value: dict[str, list[str]] = {}
        for identifier in identifiers:
            raw = identifier.get("pmid")
            if raw is None:
                continue
            by_value.setdefault(str(raw), []).append(str(identifier.get("scope") or ""))
        for raw, scopes in by_value.items():
            pmid, reason = normalize_pmid(raw)
            rule_id = candidate.get("materialization_rule_id") or ""
            pairs.append(CandidatePmidPair(
                candidate_id=candidate["candidate_id"],
                pmid_raw=raw,
                pmid=pmid,
                invalid_reason=reason,
                scopes=sorted(set(scopes)),
                rule_id=rule_id,
                predicate=candidate.get("predicate") or "",
                provenance_level=provenance_level(rule_id),
                disease=_labels(candidate.get("disease")),
                gene=_labels(candidate.get("biomarkers"), "Gene"),
                alteration=_labels(candidate.get("biomarkers"), "Variant"),
                intervention=_labels(candidate.get("interventions")),
                direction=candidate.get("direction"),
                evidence_scope=candidate.get("evidence_scope"),
                evidence_record_ids=list(candidate.get("evidence_record_ids") or []),
                sibling_drug_count=sibling_drug_counts.get(candidate["candidate_id"], 1),
            ))
    return pairs
