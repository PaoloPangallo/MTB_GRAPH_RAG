"""Risultato del retriever V3: quattro bucket, e cio' che li spiega.

I quattro bucket sono sempre presenti nella struttura, anche quando non vengono
resi. E' una differenza che conta: un candidato escluso non viene cancellato ma
collocato, e chi apre la modalita' di audit lo ritrova con la ragione per cui e'
finito li'. Un retriever che scartasse i candidati esclusi renderebbe la propria
selettivita' non verificabile — l'unica cosa osservabile sarebbe cio' che ha
deciso di mostrare.

Il rendering di default e' conservativo e asimmetrico, e lo e' per la stessa
ragione per cui i bucket esistono:

    primary   incluso
    warning   incluso
    audit     escluso salvo richiesta
    rejected  escluso salvo richiesta

Warning entra di default perche' e' un risultato con una riserva, non un
risultato scartato. Audit e rejected restano fuori perche' mostrarli insieme
agli altri significherebbe presentare come evidenze cose che il gate ha escluso.

La provenance non e' un riassunto: e' l'elenco dei riferimenti con cui ogni
campo del risultato puo' essere risalito fino al record del grafo. Quando manca
un anello — non c'e' uno statement legacy, non c'e' una decisione terminologica
— il campo resta vuoto invece di essere omesso, perche' "assente" e "non
applicabile" si distinguono soltanto se entrambi sono scritti.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow import integrated_gates_v11 as GATE
from backend.pipeline.evidence.shadow import integrated_gates_v12 as GATE_V12

RESULT_SCHEMA_VERSION = "qualified_claim_retrieval_result/1.4"

# Lo schema che il gate 1.2 pubblica. Il 1.4 resta leggibile e riproducibile: un
# risultato prodotto sotto il gate 1.1 non porta `gate_trace`, e il campo assente
# resta fuori dal payload canonico. E' cio' che permette di rieseguire una misura
# della fase precedente senza rigenerarne un solo artefatto.
RESULT_SCHEMA_VERSION_V15 = GATE_V12.OUTPUT_CONTRACT_VERSION

SCHEMA_FOR_GATE = {
    GATE.GATE_VERSION: RESULT_SCHEMA_VERSION,
    GATE_V12.GATE_VERSION: RESULT_SCHEMA_VERSION_V15,
}

# I campi della traccia dei gate, dichiarati una volta sola.
GATE_TRACE_FIELDS = (
    "biomarker_match",
    "biomarker_substitution",
    "dominant_gate",
    "gate_local_buckets",
    "gate_version",
)

PRIMARY_BUCKET = GATE.PRIMARY_BUCKET
WARNING_BUCKET = GATE.WARNING_BUCKET
AUDIT_BUCKET = GATE.AUDIT_BUCKET
REJECTED_BUCKET = GATE.REJECTED_BUCKET

BUCKETS = (PRIMARY_BUCKET, WARNING_BUCKET, AUDIT_BUCKET, REJECTED_BUCKET)

SECTION_THERAPEUTIC = "therapeutic_results"
SECTION_DIAGNOSTIC = "diagnostic_results"
SECTION_PROGNOSTIC = "prognostic_results"
SECTIONS = (SECTION_THERAPEUTIC, SECTION_DIAGNOSTIC, SECTION_PROGNOSTIC)

SECTION_FOR_DOMAIN = {
    "therapeutic": SECTION_THERAPEUTIC,
    "diagnostic": SECTION_DIAGNOSTIC,
    "prognostic": SECTION_PROGNOSTIC,
}

DEFAULT_RENDERED_BUCKETS = (PRIMARY_BUCKET, WARNING_BUCKET)


def _strings(value: Any) -> list[str]:
    return [str(item) for item in (value or ())]


def build_provenance(
    record: Mapping[str, Any],
    *,
    gate_result: GATE.IntegratedStructuralMatchResultV11,
    links: Sequence[Mapping[str, Any]] = (),
    views: Sequence[Mapping[str, Any]] = (),
    deprecated_redirect: str | None = None,
) -> dict[str, Any]:
    """Ogni riferimento con cui il risultato puo' essere risalito alla fonte."""
    provenance = dict(record.get("provenance") or {})
    disease = gate_result.disease_match_result
    formulation = gate_result.formulation_match_result
    terminology = dict(record.get("terminology_provenance") or {}) or dict(
        provenance.get("terminology_canonicalization") or {}
    )
    return {
        "adapter_lineage": {
            "adapter_version": str(provenance.get("adapter_version") or ""),
            "migration_origin": str(record.get("migration_origin") or ""),
            "operational_extraction_action_id": str(
                provenance.get("operational_extraction_action_id") or ""
            ),
            "snapshot_fingerprint": str(provenance.get("snapshot_fingerprint") or ""),
        },
        "claim_id": str(record.get("claim_id") or ""),
        "deprecated_redirect": deprecated_redirect or "",
        "disease_relation_provenance": {
            "contract_version": str(disease.get("contract_version") or ""),
            "relation_direction": str(disease.get("relation_direction") or ""),
            "relation_provenance": str(disease.get("relation_provenance") or ""),
            "relation_source": str(disease.get("relation_source") or ""),
            "relation_source_version": str(disease.get("relation_source_version") or ""),
            "relation_type": str(disease.get("relation_type") or ""),
            "relation_verified": bool(disease.get("relation_verified", False)),
        },
        "formulation_provenance": {
            "authoritative_source": str(formulation.get("authoritative_source") or ""),
            "claim_form": str(formulation.get("claim_form") or ""),
            "contract_version": str(formulation.get("contract_version") or ""),
            "query_form": str(formulation.get("query_form") or ""),
            "relation_status": str(formulation.get("relation_status") or ""),
            "relation_type": str(formulation.get("relation_type") or ""),
        },
        "graph_evidence_provenance": {
            "graph_evidence_id": str(record.get("graph_evidence_id") or ""),
            "graph_record_ids": _strings(provenance.get("graph_record_ids")),
            "parent_id": str(record.get("parent_id") or ""),
        },
        "legacy_statement_ids": _strings(record.get("legacy_statement_ids")),
        "locators": [dict(item) for item in (record.get("locators") or ())],
        "parent_id": str(record.get("parent_id") or ""),
        "propagation_policy": str(record.get("propagation_policy") or ""),
        "qualification_status": {
            "final_evaluable": bool(record.get("final_evaluable", False)),
            "hard_filterable": bool(record.get("hard_filterable", False)),
            "qualification_link_ids": _strings(record.get("qualification_link_ids")),
            "qualification_links": [
                str(link.get("qualification_link_id") or "") for link in links
            ],
            "qualified_view_ids": [str(view.get("view_id") or "") for view in views],
        },
        "reason_codes": list(gate_result.reason_codes),
        "review_status": str(record.get("review_status") or ""),
        "source_ids": _strings(
            provenance.get("source_ids")
            or ([provenance["source_id"]] if provenance.get("source_id") else [])
        ),
        "source_unit_ids": _strings(record.get("source_unit_ids")),
        "terminology_provenance": terminology,
        "warnings": sorted(
            set(_strings(record.get("warnings"))) | set(gate_result.warning_codes)
        ),
    }


@dataclass(frozen=True)
class QualifiedClaimResult:
    """Un claim, il bucket in cui e' finito, e la catena che lo giustifica."""

    claim_id: str
    parent_id: str
    graph_evidence_id: str
    claim_domain: str
    claim_type: str
    bucket: str
    section: str
    rank: int
    biomarker: str = ""
    disease_scope: str = ""
    canonical_intervention: str = ""
    # I letterali con cui il claim e' raggiungibile, e quelli che la fonte usa.
    # Restano due campi: su `evidence:1851` il primo contiene `infigratinib` e
    # il secondo `BGJ398`, e mostrarne uno solo cancellerebbe meta' della
    # canonicalizzazione — o il nome verificato, o il nome della fonte.
    intervention_members: tuple[str, ...] = ()
    source_literal_members: tuple[str, ...] = ()
    gate: dict[str, Any] = field(default_factory=dict)
    score: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    explanation_codes: tuple[str, ...] = ()
    # Il bucket di ogni asse, il gate dominante e la sostituzione booleana. Sta
    # qui e non dentro `provenance` perche' non e' un riferimento alla fonte ma
    # una decisione, e perche' la provenance dichiara un insieme chiuso di
    # chiavi. Assente sotto il gate 1.1, che non lo produce: in quel caso il
    # campo resta fuori dalla serializzazione e il risultato e' identico a
    # quello della fase precedente, byte per byte.
    gate_trace: dict[str, Any] | None = None
    schema_version: str = RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        if self.gate_trace is not None:
            payload["gate_trace"] = dict(self.gate_trace)
        return payload

    def _payload(self) -> dict[str, Any]:
        return {
            "biomarker": self.biomarker,
            "bucket": self.bucket,
            "canonical_intervention": self.canonical_intervention,
            "claim_domain": self.claim_domain,
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "disease_scope": self.disease_scope,
            "explanation_codes": list(self.explanation_codes),
            "gate": dict(self.gate),
            "graph_evidence_id": self.graph_evidence_id,
            "intervention_members": list(self.intervention_members),
            "parent_id": self.parent_id,
            "provenance": dict(self.provenance),
            "rank": self.rank,
            "reason_codes": list(self.reason_codes),
            "schema_version": self.schema_version,
            "score": dict(self.score),
            "section": self.section,
            "source_literal_members": list(self.source_literal_members),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class QualifiedClaimRetrievalResult:
    """I quattro bucket di una query, piu' cio' che serve a rieseguirla."""

    query_id: str
    backend_name: str
    repository_version: str
    policy_mode: str
    corpus_hash: str
    run_id: str
    timestamp: str
    query: dict[str, Any] = field(default_factory=dict)
    primary_ranked_results: tuple[QualifiedClaimResult, ...] = ()
    retained_with_warning: tuple[QualifiedClaimResult, ...] = ()
    audit_only_results: tuple[QualifiedClaimResult, ...] = ()
    rejected_by_native_constraints: tuple[QualifiedClaimResult, ...] = ()
    candidate_count: int = 0
    gate_decisions: dict[str, Any] = field(default_factory=dict)
    latency_ms: dict[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    failure_reason: str = ""
    schema_version: str = RESULT_SCHEMA_VERSION
    gate_version: str = GATE.GATE_VERSION

    # --- accesso --------------------------------------------------------------

    def bucket(self, name: str) -> tuple[QualifiedClaimResult, ...]:
        mapping = {
            PRIMARY_BUCKET: self.primary_ranked_results,
            WARNING_BUCKET: self.retained_with_warning,
            AUDIT_BUCKET: self.audit_only_results,
            REJECTED_BUCKET: self.rejected_by_native_constraints,
        }
        if name not in mapping:
            raise KeyError(f"bucket non riconosciuto: {name!r}")
        return mapping[name]

    @property
    def all_results(self) -> tuple[QualifiedClaimResult, ...]:
        return (
            self.primary_ranked_results
            + self.retained_with_warning
            + self.audit_only_results
            + self.rejected_by_native_constraints
        )

    def bucket_counts(self) -> dict[str, int]:
        return {name: len(self.bucket(name)) for name in BUCKETS}

    def sections(self) -> dict[str, list[dict[str, Any]]]:
        """Sezioni separate per dominio. Nessun ordinamento fra le sezioni.

        Le tre sezioni esistono sempre, anche vuote: una query senza tipo che
        omettesse la sezione prognostica perche' priva di risultati direbbe
        implicitamente che quel dominio non e' stato interrogato.
        """
        grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in SECTIONS}
        for result in self.primary_ranked_results + self.retained_with_warning:
            if result.section in grouped:
                grouped[result.section].append(result.to_dict())
        return grouped

    # --- rendering ------------------------------------------------------------

    def rendered(
        self,
        *,
        include_warning: bool = True,
        include_audit: bool = False,
        include_rejected: bool = False,
        sectioned: bool = False,
        result_limit: int | None = None,
    ) -> dict[str, Any]:
        """La vista che il chiamante ha chiesto. La struttura resta completa.

        `result_limit` taglia qui e non alla raccolta. Se tagliasse prima,
        `bucket_counts` diventerebbe una funzione del limite invece che del
        corpus, e due query identiche con limiti diversi sembrerebbero aver
        trovato quantita' di evidenza diverse.
        """

        def cut(items: Sequence[QualifiedClaimResult]) -> list[dict[str, Any]]:
            selected = items if result_limit is None else items[:result_limit]
            return [item.to_dict() for item in selected]

        payload: dict[str, Any] = {
            "backend_name": self.backend_name,
            "bucket_counts": self.bucket_counts(),
            "candidate_count": self.candidate_count,
            "corpus_hash": self.corpus_hash,
            "failure_reason": self.failure_reason,
            "gate_decisions": dict(self.gate_decisions),
            "gate_version": self.gate_version,
            "latency_ms": dict(self.latency_ms),
            "policy_mode": self.policy_mode,
            "primary_ranked_results": cut(self.primary_ranked_results),
            "query": dict(self.query),
            "query_id": self.query_id,
            "repository_version": self.repository_version,
            "result_limit": result_limit,
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "warnings": list(self.warnings),
        }
        payload["retained_with_warning"] = (
            cut(self.retained_with_warning) if include_warning else []
        )
        payload["audit_only_results"] = (
            cut(self.audit_only_results) if include_audit else []
        )
        payload["rejected_by_native_constraints"] = (
            cut(self.rejected_by_native_constraints) if include_rejected else []
        )
        payload["buckets_withheld_from_rendering"] = sorted(
            name
            for name, shown in (
                (WARNING_BUCKET, include_warning),
                (AUDIT_BUCKET, include_audit),
                (REJECTED_BUCKET, include_rejected),
            )
            if not shown
        )
        if sectioned:
            payload["sections"] = self.sections()
        return payload

    def to_dict(self) -> dict[str, Any]:
        """Tutto, senza filtri di rendering. E' la forma che va negli artefatti."""
        return self.rendered(
            include_warning=True,
            include_audit=True,
            include_rejected=True,
            sectioned=True,
        )

    def canonical_digest(self) -> str:
        """Digest stabile del risultato, senza la latenza.

        La latenza misura la macchina, non il corpus. Includerla renderebbe due
        esecuzioni identiche diverse a ogni giro, e il determinismo — che e' una
        proprieta' del retriever — non sarebbe piu' osservabile.
        """
        payload = self.to_dict()
        payload.pop("latency_ms", None)
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def result_schema(gate: Any = None) -> dict[str, Any]:
    """Descrizione serializzabile dello schema, per gli artefatti della fase.

    Lo schema dipende dal gate perche' e' il gate a decidere se il risultato
    porti una traccia. Chiamata senza argomenti risponde per il gate 1.1, che e'
    la forma con cui la fase precedente ha misurato i propri artefatti.
    """
    gate_version = getattr(gate, "GATE_VERSION", GATE.GATE_VERSION)
    schema_version = SCHEMA_FOR_GATE.get(gate_version, RESULT_SCHEMA_VERSION)
    payload = {
        "buckets": list(BUCKETS),
        "bucket_precedence_most_to_least_restrictive": list(GATE.BUCKET_PRECEDENCE),
        "cross_domain_ranking": False,
        "default_rendered_buckets": list(DEFAULT_RENDERED_BUCKETS),
        "excluded_candidates_retained_internally": True,
        "gate_version": gate_version,
        "provenance_fields": [
            "adapter_lineage",
            "claim_id",
            "deprecated_redirect",
            "disease_relation_provenance",
            "formulation_provenance",
            "graph_evidence_provenance",
            "legacy_statement_ids",
            "locators",
            "parent_id",
            "propagation_policy",
            "qualification_status",
            "reason_codes",
            "review_status",
            "source_ids",
            "source_unit_ids",
            "terminology_provenance",
            "warnings",
        ],
        "schema_version": schema_version,
        "sections": list(SECTIONS),
    }
    if schema_version != RESULT_SCHEMA_VERSION:
        payload["gate_trace_fields"] = list(GATE_TRACE_FIELDS)
        payload["supersedes"] = RESULT_SCHEMA_VERSION
    return payload


__all__ = [
    "AUDIT_BUCKET",
    "BUCKETS",
    "DEFAULT_RENDERED_BUCKETS",
    "GATE_TRACE_FIELDS",
    "PRIMARY_BUCKET",
    "REJECTED_BUCKET",
    "RESULT_SCHEMA_VERSION",
    "RESULT_SCHEMA_VERSION_V15",
    "SCHEMA_FOR_GATE",
    "SECTIONS",
    "SECTION_FOR_DOMAIN",
    "WARNING_BUCKET",
    "QualifiedClaimResult",
    "QualifiedClaimRetrievalResult",
    "build_provenance",
    "result_schema",
]
