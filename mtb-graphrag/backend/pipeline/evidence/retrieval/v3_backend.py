"""Retriever V3 sul corpus promosso 1.4.

Il retriever non reimplementa niente di cio' che e' gia' congelato. Il corpus lo
apre il loader promosso — con la sua verifica degli hash, il suo schema, il suo
lineage e il suo rifiuto delle modalita' sconosciute; i gate li applica il gate
integrato, nell'ordine che quel modulo dichiara; i pesi li legge dalla
configurazione operativa senza toccarli. Cio' che questo modulo aggiunge e' il
giro: quali oggetti entrano, come i quattro bucket vengono composti, e che cosa
esce.

Quattro scelte meritano di essere lette come scelte.

**Il gate e' iniettabile, e il suo default e' il 1.2.** La fase precedente ha
misurato i propri artefatti sotto il gate 1.1, e riprodurre quella misura deve
restare possibile senza rigenerarne nemmeno uno: un retriever costruito con
`gate=integrated_gates_v11` ricalcola quei digest byte per byte. Il default e' il
1.2, che legge gli operatori booleani del biomarcatore. La differenza fra i due
si vede in un campo — `gate_trace` — che il 1.1 non produce e che, assente, resta
fuori dalla serializzazione.

**Gli oggetti che entrano non sono solo i claim attivi.** Entrano anche i claim
ritirati, le associazioni non sostenute, quelle non risolte e i contenitori di
provenienza. Nessuno dei quattro puo' raggiungere il bucket primario — lo stato
dell'oggetto lo impedisce prima di ogni match — ma tutti restano recuperabili in
audit. Un retriever che li escludesse a monte non avrebbe una modalita' di audit:
avrebbe una modalita' in cui mostra di piu' fra le cose che aveva gia' scelto.

**Il limite per bucket e' un limite di rendering, non di raccolta.** I quattro
bucket restano completi nella struttura; `rendered()` taglia. Tagliare prima
renderebbe `bucket_counts` una funzione del limite invece che del corpus.

**Il timestamp e' una costante di fase, non un orologio.** Vale qui la stessa
ragione per cui `PROMOTED_AT` lo e' nel contratto di promozione: un risultato
che timbrasse `datetime.now()` sarebbe diverso a ogni esecuzione, e il test di
determinismo — l'unico modo di dimostrare che l'esito dipende dal corpus e non
dall'ambiente — non potrebbe esistere. La latenza, che e' invece una misura
dell'ambiente, viaggia in un campo separato ed e' esclusa dal digest canonico.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import Any

from backend.pipeline.evidence.corpus import loader as LOADER
from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT
from backend.pipeline.evidence.retrieval import v3_objects as OBJ
from backend.pipeline.evidence.retrieval import v3_scoring as SCORING
from backend.pipeline.evidence.retrieval.backends import (
    BACKEND_QUALIFIED_CLAIM_V3,
    validate_policy_mode,
    validate_repository_version,
)
from backend.pipeline.evidence.retrieval.v3_query import (
    DOMAIN_UNTYPED,
    QualifiedClaimQuery,
    build_query,
)
from backend.pipeline.evidence.retrieval import v3_result as RESULT
from backend.pipeline.evidence.retrieval.v3_result import (
    AUDIT_BUCKET,
    PRIMARY_BUCKET,
    REJECTED_BUCKET,
    SECTION_FOR_DOMAIN,
    WARNING_BUCKET,
    QualifiedClaimResult,
    QualifiedClaimRetrievalResult,
    build_provenance,
)
from backend.pipeline.evidence.shadow import integrated_gates_v11 as GATE_V11
from backend.pipeline.evidence.shadow import integrated_gates_v12 as GATE

BACKEND_VERSION = "qualified_claim_retriever/1.0"

# Costante di fase, non orologio. Vedi il docstring del modulo.
RUN_TIMESTAMP = CONTRACT.PROMOTED_AT

# L'ordine in cui i gate vengono applicati. Non e' una descrizione a posteriori:
# `gate_execution_order()` la serializza negli artefatti, e i primi nove passi
# corrispondono uno a uno a quelli che `integrated_gates_v11` esegue.
GATE_EXECUTION_ORDER = (
    "active_claim_loading",
    "claim_status_gate",
    "domain_gate",
    "biomarker_gate",
    "disease_gate",
    "intervention_identity_gate",
    "formulation_gate",
    "regimen_class_aggregate_gate",
    "direction_polarity_gate",
    "bucket_composition",
    "scoring_where_permitted",
    "within_bucket_ranking",
    "result_rendering",
)

# Quante volte il loader promosso e' stato invocato in questo processo. Serve a
# rendere misurabile — e non soltanto dichiarata — l'isolamento del percorso
# legacy: una run con `retrieval_backend="legacy"` deve lasciare il contatore
# fermo.
_LOADER_INVOCATIONS = 0


def loader_invocations() -> int:
    """Quante volte il corpus promosso e' stato aperto in questo processo."""
    return _LOADER_INVOCATIONS


class PromotedCorpusNotBindableError(RuntimeError):
    """Il corpus promosso non e' in uno stato che il retriever possa usare."""


def corpus_hash(corpus: LOADER.PromotedCorpus) -> str:
    """Digest degli hash che il manifest dichiara.

    Non e' l'hash dell'albero: e' l'hash di cio' che il manifest *afferma*
    sull'albero, gia' verificato dal loader. Le due cose coincidono solo se la
    verifica e' passata, ed e' esattamente l'invariante che serve citare.
    """
    declared = dict(corpus.manifest.get("artifact_sha256") or {})
    encoded = json.dumps(declared, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sort_key(result: QualifiedClaimResult) -> tuple[Any, ...]:
    """Ordinamento deterministico dentro un bucket.

    Il punteggio entra soltanto dove il gate lo ha permesso. Dove non lo ha
    permesso il termine e' costante, e l'ordine e' quello degli identificatori:
    stabile, ricalcolabile e senza nessuna pretesa clinica.
    """
    score = result.score
    ordering = -float(score.get("total") or 0.0) if score.get("ranking_score_allowed") else 0.0
    return (ordering, result.claim_type, result.graph_evidence_id, result.claim_id)


class QualifiedClaimRetrieverV3:
    """Il retriever del corpus promosso. Legge, non scrive, non ordina fra domini."""

    backend_name = BACKEND_QUALIFIED_CLAIM_V3

    def __init__(
        self,
        corpus: LOADER.PromotedCorpus,
        *,
        policy_mode: str | None = None,
        repository_version: str | None = None,
        gate: Any = None,
    ) -> None:
        self._corpus = corpus
        self._gate = gate if gate is not None else GATE
        self._policy_mode = validate_policy_mode(
            policy_mode if policy_mode is not None else corpus.policy_mode
        )
        self._repository_version = validate_repository_version(repository_version)
        self._verify_bindable()
        self._corpus_hash = corpus_hash(corpus)
        self._weights = SCORING.load_operational_weights()
        self._objects = self._build_objects()

    # --- costruzione ----------------------------------------------------------

    @classmethod
    def from_registry(
        cls,
        registry_path: Path = CONTRACT.REGISTRY_PATH,
        *,
        policy_mode: str | None = None,
        repository_version: str | None = None,
        verify_hashes: bool = True,
        gate: Any = None,
    ) -> "QualifiedClaimRetrieverV3":
        """Carica il corpus che il registro prototipale dichiara attivo.

        Il passaggio dal registro non e' una comodita': dopo un rollback non c'e'
        nessun corpus attivo, e il loader lo dice invece di caricare comunque i
        file rimasti sul disco.
        """
        global _LOADER_INVOCATIONS
        mode = validate_policy_mode(policy_mode)
        _LOADER_INVOCATIONS += 1
        corpus = LOADER.load_from_registry(
            registry_path, policy_mode=mode, verify_hashes=verify_hashes
        )
        return cls(
            corpus,
            policy_mode=mode,
            repository_version=repository_version,
            gate=gate,
        )

    def _verify_bindable(self) -> None:
        """Le condizioni d'avvio. Nessuna di esse ha un ramo permissivo."""
        entry = dict(self._corpus.registry_entry)
        manifest = self._corpus.manifest

        if entry.get("promotion_status") != CONTRACT.PROMOTION_STATUS:
            raise PromotedCorpusNotBindableError(
                f"promotion_status {entry.get('promotion_status')!r} non e' "
                f"{CONTRACT.PROMOTION_STATUS!r}"
            )
        if not entry.get("prototype_promoted"):
            raise PromotedCorpusNotBindableError(
                "il corpus non e' dichiarato promosso per il prototipo"
            )
        if self._corpus.repository_version != self._repository_version:
            raise PromotedCorpusNotBindableError(
                f"repository_version del corpus {self._corpus.repository_version!r} "
                f"diversa da quella configurata {self._repository_version!r}"
            )
        if self._corpus.schema_version != CONTRACT.SCHEMA_VERSION:
            raise PromotedCorpusNotBindableError(
                f"schema_version {self._corpus.schema_version!r} non compatibile"
            )
        if not manifest.get("artifact_sha256"):
            raise PromotedCorpusNotBindableError(
                "il manifest non dichiara nessun hash: l'integrita' non e' verificabile"
            )
        # `operational_retriever_bound` puo' essere falso, ed e' il caso normale
        # durante il binding test: il campo dice che il percorso operativo non e'
        # stato spostato sul corpus promosso, non che il corpus sia inutilizzabile.

    def _build_objects(self) -> tuple[tuple[Any, Mapping[str, Any]], ...]:
        """Gli oggetti candidati, reidratati una volta sola e riusati per query."""
        items: list[tuple[Any, Mapping[str, Any]]] = []
        for record in self._corpus.claims:
            items.append((OBJ.claim_object(record), record))
        for record in self._corpus.deprecated:
            items.append((OBJ.claim_object(record), record))
        for record in self._corpus.unsupported:
            items.append((OBJ.unsupported_object(record), record))
        for record in self._corpus.unresolved:
            items.append((OBJ.unresolved_object(record), record))
        for record in self._corpus.parents:
            items.append((OBJ.parent_object(record), record))
        return tuple(items)

    # --- identita' ------------------------------------------------------------

    @property
    def repository_version(self) -> str:
        return self._repository_version

    @property
    def policy_mode(self) -> str:
        return self._policy_mode

    @property
    def corpus(self) -> LOADER.PromotedCorpus:
        return self._corpus

    @property
    def corpus_hash(self) -> str:
        return self._corpus_hash

    @property
    def gate(self) -> Any:
        """Il gate strutturale con cui questo retriever decide i bucket.

        E' iniettabile perche' la fase precedente ha misurato i propri artefatti
        sotto il gate 1.1, e riprodurre quella misura deve restare possibile
        senza rigenerarli. Il default e' il 1.2: il gate che legge gli operatori
        booleani del biomarcatore.
        """
        return self._gate

    @property
    def gate_version(self) -> str:
        return str(getattr(self._gate, "GATE_VERSION", GATE.GATE_VERSION))

    @property
    def result_schema_version(self) -> str:
        return RESULT.SCHEMA_FOR_GATE.get(
            self.gate_version, RESULT.RESULT_SCHEMA_VERSION
        )

    # --- retrieval ------------------------------------------------------------

    def build_native_query(self, query: Mapping[str, Any]) -> QualifiedClaimQuery:
        """La query V3 tipizzata, con la modalita' della configurazione se assente."""
        payload = dict(query)
        payload.setdefault("policy_mode", self._policy_mode)
        return build_query(payload)

    def retrieve(self, query: Mapping[str, Any]) -> QualifiedClaimRetrievalResult:
        """I quattro bucket per una query. Nessuna scrittura, nessun ranking cross-domain."""
        started = perf_counter()
        typed = (
            query
            if isinstance(query, QualifiedClaimQuery)
            else self.build_native_query(query)
        )
        gate_query = typed.to_gate_query()
        normalized_at = perf_counter()

        buckets: dict[str, list[QualifiedClaimResult]] = {
            PRIMARY_BUCKET: [],
            WARNING_BUCKET: [],
            AUDIT_BUCKET: [],
            REJECTED_BUCKET: [],
        }
        blocking_counts: dict[str, int] = {}
        warnings: set[str] = set()

        for obj, record in self._objects:
            gate_result = self._gate.evaluate(gate_query, obj, mode=typed.policy_mode)
            claim_score = SCORING.score(gate_result, weights=self._weights)
            for gate_name in gate_result.blocking_gates:
                blocking_counts[gate_name] = blocking_counts.get(gate_name, 0) + 1
            warnings.update(gate_result.warning_codes)
            buckets[gate_result.final_bucket].append(
                self._result_for(obj, record, gate_result, claim_score)
            )
        gated_at = perf_counter()

        ranked: dict[str, tuple[QualifiedClaimResult, ...]] = {}
        for name, items in buckets.items():
            items.sort(key=_sort_key)
            ranked[name] = tuple(
                replace(item, rank=rank) for rank, item in enumerate(items, 1)
            )
        ranked_at = perf_counter()

        return QualifiedClaimRetrievalResult(
            query_id=typed.query_id,
            backend_name=self.backend_name,
            repository_version=self._repository_version,
            policy_mode=typed.policy_mode,
            corpus_hash=self._corpus_hash,
            run_id=self._run_id(typed),
            timestamp=RUN_TIMESTAMP,
            query=typed.to_dict(),
            primary_ranked_results=ranked[PRIMARY_BUCKET],
            retained_with_warning=ranked[WARNING_BUCKET],
            audit_only_results=ranked[AUDIT_BUCKET],
            rejected_by_native_constraints=ranked[REJECTED_BUCKET],
            candidate_count=len(self._objects),
            gate_decisions={
                "blocking_gate_counts": dict(sorted(blocking_counts.items())),
                "gate_execution_order": list(GATE_EXECUTION_ORDER),
                "gate_version": self.gate_version,
                "policy_mode": typed.policy_mode,
            },
            gate_version=self.gate_version,
            schema_version=self.result_schema_version,
            latency_ms={
                "gating": int((gated_at - normalized_at) * 1000),
                "normalization": int((normalized_at - started) * 1000),
                "ranking": int((ranked_at - gated_at) * 1000),
                "total": int((ranked_at - started) * 1000),
            },
            warnings=tuple(sorted(warnings)),
        )

    def retrieve_rendered(self, query: Mapping[str, Any]) -> dict[str, Any]:
        """Il risultato gia' reso secondo i flag della query."""
        typed = (
            query
            if isinstance(query, QualifiedClaimQuery)
            else self.build_native_query(query)
        )
        result = self.retrieve(typed)
        return result.rendered(
            include_warning=typed.include_warning,
            include_audit=typed.include_audit,
            include_rejected=typed.include_rejected,
            sectioned=typed.claim_domain == DOMAIN_UNTYPED,
            result_limit=typed.result_limit,
        )

    def _run_id(self, query: QualifiedClaimQuery) -> str:
        """Identificatore derivato dalla run, non da un contatore o da un orologio."""
        payload = json.dumps(
            {
                "backend": self.backend_name,
                "corpus_hash": self._corpus_hash,
                "policy_mode": query.policy_mode,
                "query": query.normalized_form(),
                "repository_version": self._repository_version,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return f"RUN-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"

    def _result_for(
        self,
        obj: Any,
        record: Mapping[str, Any],
        gate_result: GATE.IntegratedStructuralMatchResultV11,
        claim_score: SCORING.ClaimScore,
    ) -> QualifiedClaimResult:
        claim_id = str(
            record.get("claim_id") or record.get("association_id") or record.get("parent_id")
        )
        domain = gate_result.claim_domain
        links = self._corpus.links_for_claim(claim_id)
        views = self._corpus.views_for_claim(claim_id)
        return QualifiedClaimResult(
            claim_id=claim_id,
            parent_id=str(record.get("parent_id") or ""),
            graph_evidence_id=str(record.get("graph_evidence_id") or ""),
            claim_domain=domain,
            claim_type=gate_result.claim_type,
            bucket=gate_result.final_bucket,
            section=SECTION_FOR_DOMAIN.get(domain, ""),
            rank=0,
            biomarker=str(record.get("biomarker") or ""),
            disease_scope=str(record.get("disease_scope") or ""),
            canonical_intervention=str(getattr(obj, "canonical_intervention", "") or ""),
            intervention_members=tuple(
                str(item) for item in (getattr(obj, "intervention_members", ()) or ())
            ),
            source_literal_members=tuple(
                str(item)
                for item in (
                    record.get("source_literal_members")
                    or record.get("aggregate_members_literal")
                    or ()
                )
            ),
            gate=gate_result.to_dict(),
            score=claim_score.to_dict(),
            provenance=build_provenance(
                record,
                gate_result=gate_result,
                links=links,
                views=views,
                deprecated_redirect=self._corpus.redirect(claim_id),
            ),
            warnings=tuple(gate_result.warning_codes),
            reason_codes=tuple(gate_result.reason_codes),
            explanation_codes=tuple(gate_result.explanation_codes),
            gate_trace=(
                trace() if callable(trace := getattr(gate_result, "gate_trace", None))
                else None
            ),
            schema_version=self.result_schema_version,
        )

    # --- osservabilita' -------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        entry = dict(self._corpus.registry_entry)
        counts = self._corpus.counts()
        return {
            "backend_name": self.backend_name,
            "backend_version": BACKEND_VERSION,
            "candidate_objects": len(self._objects),
            "corpus_hash": self._corpus_hash,
            "counts": counts,
            "counts_match_contract": all(
                counts.get(key) == value
                for key, value in CONTRACT.EXPECTED_COUNTS.items()
                if key in counts
            ),
            "healthy": True,
            "operational_retriever_bound": self._corpus.operational_retriever_bound,
            "policy_mode": self._policy_mode,
            "promotion_status": str(entry.get("promotion_status") or ""),
            "prototype_promoted": bool(entry.get("prototype_promoted")),
            "repository_version": self._repository_version,
            "schema_version": self._corpus.schema_version,
        }

    def provenance_summary(self) -> dict[str, Any]:
        entry = dict(self._corpus.registry_entry)
        return {
            "backend_name": self.backend_name,
            "backend_version": BACKEND_VERSION,
            "corpus_hash": self._corpus_hash,
            "corpus_path": CONTRACT.PROMOTED_CORPUS_RELPATH,
            "gate_version": self.gate_version,
            "loader": "backend.pipeline.evidence.corpus.loader",
            "model_version": self._corpus.model_version,
            "policy_mode": self._policy_mode,
            "promoted_at": str(entry.get("promoted_at") or ""),
            "promotion_commit": str(entry.get("promotion_commit") or ""),
            "reads_promoted_v3_corpus": True,
            "repository_version": self._repository_version,
            "result_contract": self.result_schema_version,
            "schema_version": self._corpus.schema_version,
            "scoring_version": SCORING.SCORING_VERSION,
            "source_shadow_version": str(entry.get("source_shadow_version") or ""),
        }


def gate_execution_order(gate: Any = None) -> dict[str, Any]:
    """Descrizione serializzabile dell'ordine dei gate, per gli artefatti.

    L'ordine e' lo stesso per il 1.1 e per il 1.2 — il 1.2 corregge un asse, non
    ne sposta nessuno — ma la versione dichiarata no, e un artefatto deve dire
    sotto quale gate e' stato misurato.
    """
    resolved = gate if gate is not None else GATE
    return {
        "a_single_incompatible_gate_cancels_residual_eligibility": True,
        "buckets_most_to_least_restrictive": list(GATE.BUCKET_PRECEDENCE),
        "gate_version": resolved.GATE_VERSION,
        "order": [
            {"position": index, "step": name}
            for index, name in enumerate(GATE_EXECUTION_ORDER, 1)
        ],
        "scoring_position": GATE_EXECUTION_ORDER.index("scoring_where_permitted") + 1,
        "structural_gates_precede_scoring": True,
    }


def v3_retriever_contract(gate: Any = None) -> dict[str, Any]:
    """Descrizione serializzabile del retriever, per gli artefatti della fase."""
    resolved = gate if gate is not None else GATE
    return {
        "backend_name": BACKEND_QUALIFIED_CLAIM_V3,
        "backend_version": BACKEND_VERSION,
        "candidate_object_kinds": [
            "active_claim",
            "deprecated_claim",
            "unsupported_association",
            "unresolved_association",
            "graph_evidence_record",
        ],
        "corpus_mutated_by_retriever": False,
        "cross_domain_ranking": False,
        "excluded_candidates_recoverable_in_audit_mode": True,
        "gate_module": resolved.__name__,
        "gate_version": resolved.GATE_VERSION,
        "gate_is_selectable": True,
        "loader_module": "backend.pipeline.evidence.corpus.loader",
        "loader_reused_not_duplicated": [
            "hash_verification",
            "schema_validation",
            "redirect_lineage",
            "parent_claim_lookup",
            "policy_mode_validation",
        ],
        "repository_version": CONTRACT.REPOSITORY_VERSION,
        "result_limit_is_a_rendering_limit": True,
        "run_timestamp_is_a_phase_constant": True,
        "startup_checks": [
            "active_registry_entry",
            "promotion_status_is_prototype_promoted",
            "operational_retriever_bound_may_be_false",
            "repository_and_schema_versions_compatible",
            "manifest_and_files_intact",
        ],
    }


__all__ = [
    "BACKEND_VERSION",
    "GATE_EXECUTION_ORDER",
    "RUN_TIMESTAMP",
    "PromotedCorpusNotBindableError",
    "QualifiedClaimRetrieverV3",
    "corpus_hash",
    "gate_execution_order",
    "loader_invocations",
    "v3_retriever_contract",
]
