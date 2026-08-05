"""Deterministic, serializable models for candidate and document evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Dict, List, Optional


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass
class GraphCandidateAssertion:
    candidate_id: str
    candidate_version: str
    subject: Dict[str, Any]
    predicate: str
    object: Dict[str, Any]
    disease: List[Dict[str, Any]] = field(default_factory=list)
    biomarkers: List[Dict[str, Any]] = field(default_factory=list)
    interventions: List[Dict[str, Any]] = field(default_factory=list)
    regimen: List[Dict[str, Any]] = field(default_factory=list)
    direction: Optional[str] = None
    evidence_scope: Optional[str] = None
    diagnostic_scope: Optional[str] = None
    graph_path: List[str] = field(default_factory=list)
    node_ids: List[str] = field(default_factory=list)
    edge_ids: List[str] = field(default_factory=list)
    evidence_record_ids: List[str] = field(default_factory=list)
    document_identifiers: List[Dict[str, Any]] = field(default_factory=list)
    source_properties: Dict[str, Any] = field(default_factory=dict)
    materialization_rule_id: str = ""
    materialized_at: Optional[str] = None
    payload_hash: str = ""
    group_id: Optional[str] = None

    @classmethod
    def from_parts(cls, subject, predicate, object_, disease=None, biomarkers=None,
                   interventions=None, regimen=None, direction=None,
                   evidence_scope=None, diagnostic_scope=None, graph_path=None,
                   node_ids=None, edge_ids=None, evidence_record_ids=None,
                   document_identifiers=None, source_properties=None,
                   materialization_rule_id="gca/2.0/edge-path", materialized_at=None,
                   group_id=None):
        payload = {
            "subject": subject,
            "predicate": predicate,
            "object": object_,
            "disease": disease or [],
            "biomarkers": biomarkers or [],
            "interventions": interventions or [],
            "regimen": regimen or [],
            "direction": direction,
            "evidence_scope": evidence_scope,
            "diagnostic_scope": diagnostic_scope,
            "graph_path": graph_path or [],
            "node_ids": node_ids or [],
            "edge_ids": edge_ids or [],
            "evidence_record_ids": evidence_record_ids or [],
            "document_identifiers": document_identifiers or [],
            "source_properties": source_properties or {},
            "materialization_rule_id": materialization_rule_id,
            "group_id": group_id,
        }
        digest = _hash(payload)
        return cls(
            candidate_id=f"GCA-{digest[:24]}",
            candidate_version="2.0",
            payload_hash=digest,
            materialized_at=materialized_at,
            **payload,
        )

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "GraphCandidateAssertion":
        data = dict(value)
        data.setdefault("candidate_version", "2.0")
        data.setdefault("payload_hash", "")
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_version": self.candidate_version,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "disease": self.disease,
            "biomarkers": self.biomarkers,
            "interventions": self.interventions,
            "regimen": self.regimen,
            "direction": self.direction,
            "evidence_scope": self.evidence_scope,
            "diagnostic_scope": self.diagnostic_scope,
            "graph_path": self.graph_path,
            "node_ids": self.node_ids,
            "edge_ids": self.edge_ids,
            "evidence_record_ids": self.evidence_record_ids,
            "document_identifiers": self.document_identifiers,
            "source_properties": self.source_properties,
            "materialization_rule_id": self.materialization_rule_id,
            "materialized_at": self.materialized_at,
            "payload_hash": self.payload_hash,
            "group_id": self.group_id,
        }


@dataclass
class SourceUnit:
    source_unit_id: str
    document_id: str
    unit_type: str
    text: str
    section: Optional[str] = None
    subsection: Optional[str] = None
    paragraph_index: Optional[int] = None
    sentence_index: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    page: Optional[int] = None
    table_id: Optional[str] = None
    table_label: Optional[str] = None
    row: Optional[int] = None
    column: Optional[int] = None
    figure_id: Optional[str] = None
    figure_label: Optional[str] = None
    caption: Optional[str] = None
    bbox: Optional[List[float]] = None
    parser: str = ""
    parser_version: str = ""
    locator_confidence: str = ""
    content_hash: str = ""

    @classmethod
    def from_document_text(cls, document_id, unit_type, text, char_start=None,
                           char_end=None, parser="fixture/text", parser_version="1.0", locator_confidence="STRUCTURAL", **kwargs):
        payload = {"document_id": document_id, "unit_type": unit_type,
                   "text": text, "char_start": char_start, "char_end": char_end,
                   **kwargs}
        digest = _hash(payload)
        return cls(source_unit_id=f"SU-{digest[:24]}", content_hash=digest,
                   document_id=document_id, unit_type=unit_type, text=text,
                   char_start=char_start, char_end=char_end, parser=parser,
                   parser_version=parser_version, locator_confidence=locator_confidence,
                   **kwargs)

    def to_dict(self):
        return self.__dict__.copy()


@dataclass
class ClaimSupportRecord:
    support_id: str
    claim_id: str
    candidate_id: str
    source_unit_id: str
    document_id: str
    support_status: str
    matched_entities: List[str] = field(default_factory=list)
    matched_relation_cues: List[str] = field(default_factory=list)
    negation_detected: bool = False
    contradiction_detected: bool = False
    supported_fields: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    ambiguous_fields: List[str] = field(default_factory=list)
    verification_rule_ids: List[str] = field(default_factory=list)
    retrieval_score: Optional[float] = None
    verification_confidence: str = ""
    review_required: bool = False
    created_at: Optional[str] = None

    @classmethod
    def create(cls, claim_id, candidate_id, source_unit_id, document_id,
               support_status, **kwargs):
        payload = {"claim_id": claim_id, "candidate_id": candidate_id,
                   "source_unit_id": source_unit_id, "document_id": document_id,
                   "support_status": support_status, **kwargs}
        return cls(support_id=f"SUP-{_hash(payload)[:24]}", **payload)

    def to_dict(self):
        return self.__dict__.copy()


@dataclass
class DocumentGroundedClaim:
    claim_id: str
    claim_version: str
    candidate_ids: List[str]
    subject: Dict[str, Any] = field(default_factory=dict)
    predicate: str = ""
    object: Dict[str, Any] = field(default_factory=dict)
    disease: List[Dict[str, Any]] = field(default_factory=list)
    biomarkers: List[Dict[str, Any]] = field(default_factory=list)
    interventions: List[Dict[str, Any]] = field(default_factory=list)
    regimen: List[Dict[str, Any]] = field(default_factory=list)
    direction: Optional[str] = None
    evidence_scope: Optional[str] = None
    source_unit_ids: List[str] = field(default_factory=list)
    support_ids: List[str] = field(default_factory=list)
    document_ids: List[str] = field(default_factory=list)
    claim_text: str = ""
    support_status: str = "NOT_ASSESSED"
    supported_fields: List[str] = field(default_factory=list)
    unsupported_fields: List[str] = field(default_factory=list)
    ambiguous_fields: List[str] = field(default_factory=list)
    contradicted_fields: List[str] = field(default_factory=list)
    verification_rule_ids: List[str] = field(default_factory=list)
    provenance_status: str = ""
    created_at: Optional[str] = None
    payload_hash: str = ""

    @classmethod
    def from_candidate(cls, candidate_id, source_unit_ids, support_ids,
                       supported_fields, support_status, **kwargs):
        payload = {"candidate_ids": [candidate_id], "source_unit_ids": source_unit_ids,
                   "support_ids": support_ids, "supported_fields": supported_fields,
                   "support_status": support_status, **kwargs}
        digest = _hash(payload)
        return cls(claim_id=f"DGC-{digest[:24]}", claim_version="1.0-pilot",
                   payload_hash=digest, **payload)

    def validate(self):
        if not self.candidate_ids:
            raise ValueError("document-grounded claim requires candidate_ids")
        if self.support_status == "DIRECT":
            required = {"biomarker", "disease", "intervention", "direction"}
            if not required.issubset(set(self.supported_fields)):
                missing = sorted(required - set(self.supported_fields))
                raise ValueError(f"DIRECT support missing fields: {missing}")
            if not self.source_unit_ids or not self.support_ids:
                raise ValueError("DIRECT support requires source units and supports")

    def to_dict(self):
        return self.__dict__.copy()
