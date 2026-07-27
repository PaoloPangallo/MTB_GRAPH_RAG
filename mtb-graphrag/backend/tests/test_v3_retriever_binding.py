"""Protegge il binding del retriever V3 e la parita' del percorso legacy.

I test difendono sette cose, e ognuna e' un modo di sbagliare che questa fase
rende possibile per la prima volta.

Che il backend si scelga dichiarandolo. Un backend sconosciuto, una versione di
repository sconosciuta e una modalita' di policy sconosciuta vengono rifiutati,
e nessuno dei tre si risolve nella default: un fallback silenzioso su un valore
sbagliato trasformerebbe un errore di configurazione in una risposta piu'
permissiva di quella chiesta.

Che il default resti `legacy`. Non come dichiarazione ma come misura: la
configurazione vuota produce `legacy`, e una run legacy in un processo pulito
non importa nessun modulo del corpus promosso.

Che il percorso legacy sia rimasto identico. L'adattatore e il retriever
operativo chiamato direttamente producono la stessa serializzazione, digest
compreso, su tutte le query di regressione — le accettate e le rifiutate.

Che i quattro bucket ci siano sempre e che i candidati esclusi non spariscano.
Audit e rejected restano nella struttura anche quando il rendering li omette, e
la modalita' di audit li ritrova.

Che i gate congelati siano applicati tutti e nell'ordine dichiarato, e che
nessun punteggio possa spostare un candidato fuori dal bucket in cui il gate lo
ha messo — verificato con un punteggio arbitrariamente alto.

Che le decisioni congelate restino congelate: biomarcatore congiuntivo, AUY922
irrisolto, il letterale BGJ398 raggiungibile accanto al nome canonico, il sale
verificato in warning e il suffisso non registrato in audit, l'aggregato mai
atomizzato e il regime mai propagato ai componenti.

Che il corpus promosso non sia stato toccato, che il gold non sia stato letto e
che la fase abbia scritto solo dentro il proprio perimetro.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT
from backend.pipeline.evidence.qualified_retriever import (
    SUPPORTED_CORPUS_VERSION,
    QualifiedEvidenceRetriever,
)
from backend.pipeline.evidence.retrieval import diagnostics as DIAG
from backend.pipeline.evidence.retrieval import v3_backend as V3
from backend.pipeline.evidence.retrieval import v3_query as QUERY
from backend.pipeline.evidence.retrieval import v3_result as RESULT
from backend.pipeline.evidence.retrieval import v3_scoring as SCORING
from backend.pipeline.evidence.retrieval.backends import (
    ALLOWED_POLICY_MODES,
    BACKEND_LEGACY,
    BACKEND_QUALIFIED_CLAIM_V3,
    DEFAULT_POLICY_MODE,
    DEFAULT_RETRIEVAL_BACKEND,
    RETRIEVAL_BACKENDS,
    RetrievalBackendConfig,
    RetrievalBackendError,
    UnknownPolicyModeError,
    UnknownRepositoryVersionError,
    UnknownRetrievalBackendError,
)
from backend.pipeline.evidence.retrieval.legacy_backend import (
    LEGACY_CORPUS,
    LEGACY_SCORING_CONFIG,
    LegacyEvidenceRetrieverAdapter,
)
from backend.pipeline.evidence.retrieval.pipeline import EvidenceRetrievalPipeline
from backend.pipeline.evidence.shadow import integrated_gates_v11 as GATE
from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation import retriever_binding_1_4 as BINDING

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO_ROOT / "benchmarks" / "mtb_evidence" / "v3" / "retriever_binding_1_4"
PROMOTED_CORPUS = REPO_ROOT / CONTRACT.PROMOTED_CORPUS_RELPATH

START_SHA = "ee89352045e20b121e7ae0e636b3a3ba772f68c6"

# Vuoto finche' la fase e' aperta: il perimetro si misura su un intervallo
# chiuso, e senza estremo finale non c'e' nulla da misurare.
PHASE_END_SHA = ""

ALLOWED_WRITE_PREFIXES = (
    "backend/pipeline/evidence/retrieval/",
    "backend/tests/test_v3_retriever_binding.py",
    "benchmarks/mtb_evidence/evaluation/retriever_binding_1_4.py",
    "benchmarks/mtb_evidence/evaluation/retriever_binding_reports.py",
    "benchmarks/mtb_evidence/evaluation/scripts/build_retriever_binding_1_4.py",
    "benchmarks/mtb_evidence/v3/retriever_binding_1_4/",
)

# Le directory che questa fase non deve poter toccare.
FROZEN_PATHS = (
    CONTRACT.PROMOTED_CORPUS_RELPATH,
    CONTRACT.REGISTRY_RELPATH,
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/v2_adapter.py",
    "benchmarks/mtb_evidence/v3/integrated_shadow_repository_1_3/",
    "benchmarks/mtb_evidence/v3/pre_promotion_required_fixes_1_4/",
    "benchmarks/mtb_evidence/v3/prototype_corpus_promotion_1_4/",
    "benchmarks/mtb_evidence/v3/typed_claim_shadow_migration/",
)

ARBITRARILY_HIGH_SCORE = BINDING.ARBITRARILY_HIGH_SCORE


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class V3Fixture(unittest.TestCase):
    """Un solo retriever V3 per classe: il corpus e' read-only e non cambia."""

    pipeline: EvidenceRetrievalPipeline
    retriever: V3.QualifiedClaimRetrieverV3

    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline = EvidenceRetrievalPipeline()
        cls.retriever = cls.pipeline.backend(BACKEND_QUALIFIED_CLAIM_V3)

    def query(self, **overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query_id": "T-01",
            "claim_domain": "therapeutic",
            "biomarker": "FGFR2::BICC1 Fusion",
            "disease": "Cholangiocarcinoma",
        }
        payload.update(overrides)
        return payload

    def buckets_of(self, result: Any, graph_evidence_id: str) -> set[str]:
        return {
            item.bucket
            for item in result.all_results
            if item.graph_evidence_id == graph_evidence_id
        }


# --------------------------------------------------------------------------
# selezione del backend
# --------------------------------------------------------------------------


class BackendSelectionTests(unittest.TestCase):
    """La selezione e' una dichiarazione, e un valore sconosciuto e' un errore."""

    def test_the_default_backend_is_legacy(self) -> None:
        self.assertEqual(DEFAULT_RETRIEVAL_BACKEND, BACKEND_LEGACY)
        self.assertEqual(RetrievalBackendConfig().retrieval_backend, BACKEND_LEGACY)
        self.assertEqual(
            EvidenceRetrievalPipeline.from_config({}).default_backend, BACKEND_LEGACY
        )
        self.assertEqual(EvidenceRetrievalPipeline().default_backend, BACKEND_LEGACY)

    def test_both_backends_are_selectable(self) -> None:
        self.assertEqual(
            set(RETRIEVAL_BACKENDS), {BACKEND_LEGACY, BACKEND_QUALIFIED_CLAIM_V3}
        )
        for name in RETRIEVAL_BACKENDS:
            with self.subTest(backend=name):
                self.assertEqual(
                    RetrievalBackendConfig(retrieval_backend=name).retrieval_backend,
                    name,
                )

    def test_an_unknown_backend_is_rejected(self) -> None:
        with self.assertRaises(UnknownRetrievalBackendError):
            RetrievalBackendConfig(retrieval_backend="qualified_claim_v4")
        with self.assertRaises(UnknownRetrievalBackendError):
            EvidenceRetrievalPipeline().run({}, retrieval_backend="graph_native")

    def test_an_unknown_repository_version_is_rejected(self) -> None:
        with self.assertRaises(UnknownRepositoryVersionError):
            RetrievalBackendConfig(
                qualified_claim_repository_version="qualified_claim_repository/1.5"
            )

    def test_an_unknown_policy_mode_is_rejected(self) -> None:
        with self.assertRaises(UnknownPolicyModeError):
            RetrievalBackendConfig(qualified_claim_policy_mode="permissive")

    def test_an_absent_value_resolves_to_the_declared_default(self) -> None:
        config = RetrievalBackendConfig.from_mapping(None)
        self.assertEqual(config.retrieval_backend, BACKEND_LEGACY)
        self.assertEqual(config.qualified_claim_policy_mode, DEFAULT_POLICY_MODE)
        self.assertEqual(
            config.qualified_claim_repository_version, CONTRACT.REPOSITORY_VERSION
        )

    def test_an_unknown_configuration_field_is_rejected(self) -> None:
        with self.assertRaises(RetrievalBackendError):
            RetrievalBackendConfig.from_mapping({"retrieval_backends": "legacy"})

    def test_the_strict_mode_is_the_default_and_the_three_modes_are_allowed(
        self,
    ) -> None:
        self.assertEqual(DEFAULT_POLICY_MODE, "strict_verified")
        self.assertEqual(
            set(ALLOWED_POLICY_MODES),
            {"strict_verified", "ontology_aware_warning", "audit_all"},
        )


# --------------------------------------------------------------------------
# isolamento del percorso legacy
# --------------------------------------------------------------------------


LEGACY_ISOLATION_PROBE = """
import json, sys
from backend.pipeline.evidence.retrieval.pipeline import EvidenceRetrievalPipeline

pipeline = EvidenceRetrievalPipeline()
outcome = pipeline.run(
    {
        "query_id": "ISO-01",
        "biomarkers": [{"gene": "EGFR", "alteration": "L858R"}],
        "disease": "NSCLC",
        "disease_aliases": ["Lung Non-small Cell Carcinoma"],
    },
    retrieval_backend="legacy",
)
watched = (
    "backend.pipeline.evidence.corpus.loader",
    "backend.pipeline.evidence.retrieval.v3_backend",
    "backend.pipeline.evidence.retrieval.v3_objects",
)
print(json.dumps({
    "backend_name": outcome.backend_name,
    "default_backend": pipeline.default_backend,
    "imported": sorted(name for name in watched if name in sys.modules),
    "instantiated_backends": list(pipeline.instantiated_backends()),
    "repository_version": outcome.repository_version,
    "results": len(outcome.payload.all_results),
}))
"""


class LegacyIsolationTests(unittest.TestCase):
    """Una run legacy non deve nemmeno poter toccare il corpus promosso."""

    @classmethod
    def setUpClass(cls) -> None:
        import os

        completed = subprocess.run(
            [sys.executable, "-c", LEGACY_ISOLATION_PROBE],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
            check=False,
        )
        if completed.returncode != 0:  # pragma: no cover
            raise unittest.SkipTest(f"probe non eseguibile: {completed.stderr[-800:]}")
        cls.probe = json.loads(completed.stdout.strip().splitlines()[-1])

    def test_the_v3_loader_is_not_imported_during_a_legacy_run(self) -> None:
        self.assertEqual(self.probe["imported"], [])

    def test_only_the_legacy_backend_is_instantiated(self) -> None:
        self.assertEqual(self.probe["instantiated_backends"], [BACKEND_LEGACY])
        self.assertEqual(self.probe["default_backend"], BACKEND_LEGACY)

    def test_the_legacy_backend_reports_the_legacy_corpus_version(self) -> None:
        self.assertEqual(self.probe["repository_version"], SUPPORTED_CORPUS_VERSION)
        self.assertNotEqual(self.probe["repository_version"], CONTRACT.REPOSITORY_VERSION)

    def test_the_legacy_run_returned_results(self) -> None:
        self.assertGreater(self.probe["results"], 0)


# --------------------------------------------------------------------------
# parita' del percorso legacy
# --------------------------------------------------------------------------


class LegacyParityTests(unittest.TestCase):
    """L'adattatore non e' un secondo retriever: e' lo stesso, con un'altra firma."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.direct = QualifiedEvidenceRetriever.from_corpus(
            LEGACY_CORPUS, scoring_config_path=LEGACY_SCORING_CONFIG
        )
        cls.adapter = LegacyEvidenceRetrieverAdapter.from_corpus()

    def test_the_adapter_and_the_direct_retriever_serialize_identically(self) -> None:
        for query_id, payload in sorted(BINDING.LEGACY_QUERIES.items()):
            with self.subTest(query=query_id):
                try:
                    expected = self.direct.retrieve(
                        self.adapter.build_native_query(payload)
                    ).as_dict()
                except Exception as error:  # noqa: BLE001
                    with self.assertRaises(type(error)):
                        self.adapter.retrieve(payload)
                    continue
                actual = self.adapter.retrieve(payload).as_dict()
                self.assertEqual(actual, expected)
                self.assertEqual(_digest(actual), _digest(expected))

    def test_the_adapter_does_not_convert_the_legacy_output(self) -> None:
        payload = BINDING.LEGACY_QUERIES["RB-01-EGFR-L858R-NSCLC"]
        output = self.adapter.retrieve(payload)
        self.assertTrue(hasattr(output, "ranked_results"))
        self.assertFalse(hasattr(output, "primary_ranked_results"))

    def test_the_recorded_parity_artifact_agrees_with_the_measurement(self) -> None:
        parity = _read_json(ARTIFACTS / "legacy_parity.json")
        self.assertTrue(parity["serialization_identical"])
        self.assertEqual(parity["mismatched_queries"], [])
        self.assertTrue(parity["v3_loader_not_initialized_under_legacy"])
        self.assertEqual(parity["v3_corpus_modules_imported_during_legacy_run"], [])
        self.assertTrue(parity["default_backend_is_legacy"])
        self.assertFalse(parity["legacy_output_converted_to_v3"])
        for query_id, expected in sorted(parity["direct_output_digests"].items()):
            with self.subTest(query=query_id):
                self.assertEqual(parity["adapter_output_digests"][query_id], expected)


# --------------------------------------------------------------------------
# caricamento del corpus promosso
# --------------------------------------------------------------------------


class PromotedCorpusLoadingTests(V3Fixture):
    """Il retriever V3 usa il loader promosso, e non ne duplica le verifiche."""

    def test_the_promoted_corpus_is_loaded_and_healthy(self) -> None:
        health = self.retriever.health_check()
        self.assertTrue(health["healthy"])
        self.assertTrue(health["prototype_promoted"])
        self.assertEqual(health["promotion_status"], CONTRACT.PROMOTION_STATUS)
        self.assertEqual(health["repository_version"], CONTRACT.REPOSITORY_VERSION)
        self.assertEqual(health["schema_version"], CONTRACT.SCHEMA_VERSION)
        self.assertTrue(health["counts_match_contract"])

    def test_the_corpus_declares_the_retriever_not_yet_bound(self) -> None:
        # Il campo puo' essere falso durante il binding test, e lo e': dice che
        # il percorso operativo non e' stato spostato, non che il corpus non
        # possa essere letto.
        self.assertFalse(self.retriever.health_check()["operational_retriever_bound"])

    def test_all_claims_stay_prototype_only(self) -> None:
        for record in self.retriever.corpus.claims:
            with self.subTest(claim=record["claim_id"]):
                self.assertEqual(record["propagation_policy"], "prototype_only")
                self.assertFalse(record["hard_filterable"])
                self.assertFalse(record["final_evaluable"])

    def test_an_unknown_policy_mode_is_rejected_by_the_retriever(self) -> None:
        with self.assertRaises(UnknownPolicyModeError):
            V3.QualifiedClaimRetrieverV3.from_registry(policy_mode="permissive")

    def test_an_unknown_repository_version_is_rejected_by_the_retriever(self) -> None:
        with self.assertRaises(UnknownRepositoryVersionError):
            V3.QualifiedClaimRetrieverV3.from_registry(
                repository_version="qualified_claim_repository/9.9"
            )

    def test_the_retriever_reports_the_loader_it_uses(self) -> None:
        summary = self.retriever.provenance_summary()
        self.assertEqual(summary["loader"], "backend.pipeline.evidence.corpus.loader")
        self.assertTrue(summary["reads_promoted_v3_corpus"])
        self.assertEqual(summary["corpus_path"], CONTRACT.PROMOTED_CORPUS_RELPATH)


# --------------------------------------------------------------------------
# query
# --------------------------------------------------------------------------


class QueryContractTests(unittest.TestCase):
    """Forma originale e forma normalizzata, entrambe conservate."""

    def test_gene_and_alteration_form_a_single_conjunctive_constraint(self) -> None:
        query = QUERY.build_query(
            {"query_id": "Q", "gene": "EGFR", "alteration": "L858R"}
        )
        self.assertEqual(query.normalized_biomarker, "EGFR L858R")

    def test_the_explicit_biomarker_wins_over_the_composed_one(self) -> None:
        query = QUERY.build_query(
            {
                "query_id": "Q",
                "gene": "EGFR",
                "alteration": "L858R",
                "biomarker": "EGFR T790M AND EGFR Exon 19 Deletion",
            }
        )
        self.assertEqual(
            query.normalized_biomarker, "EGFR T790M AND EGFR Exon 19 Deletion"
        )

    def test_the_original_query_is_preserved(self) -> None:
        payload = {"query_id": "Q", "gene": " EGFR ", "disease": "  NSCLC  "}
        query = QUERY.build_query(payload)
        self.assertEqual(query.to_dict()["original"], payload)
        self.assertEqual(query.normalized_form()["normalized_disease"], "NSCLC")

    def test_the_intervention_form_is_read_from_the_structure(self) -> None:
        cases = {
            QUERY.INTERVENTION_ABSENT: {"query_id": "Q"},
            QUERY.INTERVENTION_SINGLE: {"query_id": "Q", "interventions": ["erlotinib"]},
            QUERY.INTERVENTION_REGIMEN: {
                "query_id": "Q",
                "interventions": ["erlotinib", "ramucirumab"],
                "intervention_combination": True,
            },
            QUERY.INTERVENTION_CLASS: {
                "query_id": "Q",
                "intervention_class": "EGFR tyrosine kinase inhibitor",
            },
            QUERY.INTERVENTION_UNSPECIFIED_MULTI: {
                "query_id": "Q",
                "interventions": ["erlotinib", "gefitinib"],
            },
        }
        for expected, payload in sorted(cases.items()):
            with self.subTest(form=expected):
                self.assertEqual(
                    QUERY.build_query(payload).intervention_form, expected
                )

    def test_a_class_query_cannot_also_carry_interventions(self) -> None:
        with self.assertRaises(QUERY.QualifiedClaimQueryError):
            QUERY.build_query(
                {
                    "query_id": "Q",
                    "intervention_class": "EGFR tyrosine kinase inhibitor",
                    "interventions": ["erlotinib"],
                }
            )

    def test_a_combination_needs_at_least_two_components(self) -> None:
        with self.assertRaises(QUERY.QualifiedClaimQueryError):
            QUERY.build_query(
                {
                    "query_id": "Q",
                    "interventions": ["erlotinib"],
                    "intervention_combination": True,
                }
            )

    def test_an_unknown_claim_domain_is_rejected(self) -> None:
        with self.assertRaises(QUERY.QualifiedClaimQueryError):
            QUERY.build_query({"query_id": "Q", "claim_domain": "predictive"})

    def test_the_schema_declares_no_llm_in_structural_matching(self) -> None:
        self.assertFalse(QUERY.query_schema()["llm_used_for_structural_matching"])


# --------------------------------------------------------------------------
# bucket
# --------------------------------------------------------------------------


class FourBucketTests(V3Fixture):
    """Quattro bucket sempre presenti, e i candidati esclusi non spariscono."""

    def test_every_query_returns_the_four_buckets(self) -> None:
        result = self.retriever.retrieve(self.query())
        self.assertEqual(set(result.bucket_counts()), set(RESULT.BUCKETS))
        self.assertEqual(
            sum(result.bucket_counts().values()), result.candidate_count
        )

    def test_the_default_rendering_hides_audit_and_rejected(self) -> None:
        result = self.retriever.retrieve(self.query())
        rendered = result.rendered()
        self.assertEqual(rendered["audit_only_results"], [])
        self.assertEqual(rendered["rejected_by_native_constraints"], [])
        self.assertEqual(
            rendered["buckets_withheld_from_rendering"],
            [RESULT.AUDIT_BUCKET, RESULT.REJECTED_BUCKET],
        )

    def test_excluded_candidates_are_recoverable_in_audit_mode(self) -> None:
        result = self.retriever.retrieve(self.query())
        hidden = result.rendered()
        shown = result.rendered(include_audit=True, include_rejected=True)
        self.assertEqual(hidden["bucket_counts"], shown["bucket_counts"])
        self.assertGreater(len(shown["audit_only_results"]), 0)
        self.assertGreater(len(shown["rejected_by_native_constraints"]), 0)

    def test_the_result_limit_is_a_rendering_limit_not_a_collection_limit(self) -> None:
        result = self.retriever.retrieve(
            self.query(query_id="T-LIMIT", disease="NSCLC", biomarker="EGFR L858R")
        )
        full = result.bucket_counts()["primary_ranked_results"]
        self.assertGreater(full, 3)
        rendered = result.rendered(result_limit=3)
        self.assertEqual(len(rendered["primary_ranked_results"]), 3)
        self.assertEqual(rendered["bucket_counts"]["primary_ranked_results"], full)

    def test_the_bucket_precedence_is_the_frozen_one(self) -> None:
        self.assertEqual(
            list(GATE.BUCKET_PRECEDENCE),
            [
                RESULT.REJECTED_BUCKET,
                RESULT.AUDIT_BUCKET,
                RESULT.WARNING_BUCKET,
                RESULT.PRIMARY_BUCKET,
            ],
        )


# --------------------------------------------------------------------------
# gate
# --------------------------------------------------------------------------


class GateApplicationTests(V3Fixture):
    """Tutti i gate, nell'ordine dichiarato, e nessuno aggirabile dal punteggio."""

    def test_the_declared_order_matches_the_frozen_gate_names(self) -> None:
        order = [row["step"] for row in V3.gate_execution_order()["order"]]
        self.assertEqual(order, list(V3.GATE_EXECUTION_ORDER))
        self.assertEqual(order[0], "active_claim_loading")
        self.assertLess(
            order.index("claim_status_gate"), order.index("domain_gate")
        )
        self.assertLess(order.index("domain_gate"), order.index("biomarker_gate"))
        self.assertLess(order.index("biomarker_gate"), order.index("disease_gate"))
        self.assertLess(
            order.index("disease_gate"), order.index("intervention_identity_gate")
        )
        self.assertLess(
            order.index("intervention_identity_gate"), order.index("formulation_gate")
        )
        self.assertLess(
            order.index("formulation_gate"),
            order.index("regimen_class_aggregate_gate"),
        )
        self.assertLess(
            order.index("regimen_class_aggregate_gate"),
            order.index("direction_polarity_gate"),
        )
        self.assertLess(
            order.index("direction_polarity_gate"), order.index("bucket_composition")
        )
        self.assertLess(
            order.index("bucket_composition"), order.index("scoring_where_permitted")
        )

    def test_a_primary_result_has_no_blocking_gate(self) -> None:
        result = self.retriever.retrieve(
            self.query(query_id="T-PRIMARY", biomarker="EGFR L858R", disease="NSCLC")
        )
        self.assertGreater(len(result.primary_ranked_results), 0)
        for item in result.primary_ranked_results:
            with self.subTest(claim=item.claim_id):
                self.assertEqual(item.gate["blocking_gates"], [])
                self.assertTrue(item.gate["primary_candidate_eligible"])
                self.assertTrue(item.gate["final_ranking_eligible"])

    def test_no_score_survives_a_blocking_gate(self) -> None:
        gate_query = QUERY.build_query(
            self.query(query_id="T-SCORE", interventions=["infigratinib"])
        ).to_gate_query()
        for obj, _record in self.retriever._objects:  # noqa: SLF001 - invariante interno
            gate_result = GATE.evaluate(gate_query, obj, mode=DEFAULT_POLICY_MODE)
            with self.subTest(claim=gate_result.claim_id):
                SCORING.check_score_cannot_change_bucket(
                    gate_result, ARBITRARILY_HIGH_SCORE
                )

    def test_all_scores_are_disabled_in_the_rejected_bucket(self) -> None:
        result = self.retriever.retrieve(self.query(query_id="T-REJ"))
        self.assertGreater(len(result.rejected_by_native_constraints), 0)
        for item in result.rejected_by_native_constraints:
            with self.subTest(claim=item.claim_id):
                self.assertTrue(item.score["all_scores_disabled"])
                self.assertEqual(item.score["total"], 0.0)
                self.assertFalse(item.score["ranking_score_allowed"])
                self.assertFalse(item.score["used_for_clinical_ranking"])

    def test_the_audit_bucket_never_feeds_clinical_ranking(self) -> None:
        result = self.retriever.retrieve(self.query(query_id="T-AUDIT"))
        for item in result.audit_only_results:
            with self.subTest(claim=item.claim_id):
                self.assertFalse(item.score["used_for_clinical_ranking"])
                self.assertFalse(item.score["ranking_score_allowed"])

    def test_every_feature_records_why_it_did_not_count(self) -> None:
        result = self.retriever.retrieve(self.query(query_id="T-FEAT"))
        for item in result.rejected_by_native_constraints[:20]:
            for feature in item.score["features"]:
                with self.subTest(claim=item.claim_id, feature=feature["name"]):
                    self.assertFalse(feature["eligible"])
                    self.assertTrue(feature["exclusion_reason"])

    def test_the_weights_were_not_retuned_in_this_phase(self) -> None:
        contract = SCORING.scoring_contract()
        self.assertFalse(contract["weights_retuned_in_this_phase"])
        self.assertFalse(contract["gold_used_for_weights"])
        self.assertTrue(contract["scoring_subordinate_to_gates"])


# --------------------------------------------------------------------------
# malattia, dominio, biomarcatore
# --------------------------------------------------------------------------


class DiseaseAndDomainTests(V3Fixture):
    """Le relazioni congelate decidono il bucket, e la modalita' non le cambia."""

    def test_an_exact_or_alias_disease_is_primary_eligible(self) -> None:
        result = self.retriever.retrieve(
            self.query(query_id="T-EXACT", biomarker="EGFR L858R", disease="NSCLC")
        )
        self.assertGreater(len(result.primary_ranked_results), 0)
        for item in result.primary_ranked_results:
            with self.subTest(claim=item.claim_id):
                self.assertEqual(
                    item.provenance["disease_relation_provenance"]["relation_type"],
                    "verified_disease_alias",
                )

    def test_a_parent_disease_claim_is_warning_never_primary(self) -> None:
        result = self.retriever.retrieve(
            self.query(
                query_id="T-PARENT",
                biomarker="EGFR L858R",
                disease="Lung Adenocarcinoma",
            )
        )
        relations = {
            item.provenance["disease_relation_provenance"]["relation_type"]
            for item in result.retained_with_warning
        }
        self.assertIn("claim_is_parent_of_query", relations)
        self.assertNotIn(
            "claim_is_parent_of_query",
            {
                item.provenance["disease_relation_provenance"]["relation_type"]
                for item in result.primary_ranked_results
            },
        )

    def test_a_cross_disease_claim_is_rejected(self) -> None:
        result = self.retriever.retrieve(
            self.query(
                query_id="T-CROSS", biomarker="EGFR L858R", disease="Breast Cancer"
            )
        )
        relations = {
            item.provenance["disease_relation_provenance"]["relation_type"]
            for item in result.rejected_by_native_constraints
        }
        self.assertIn("cross_disease", relations)
        self.assertEqual(len(result.primary_ranked_results), 0)

    def test_a_sibling_disease_claim_is_audit_only(self) -> None:
        result = self.retriever.retrieve(
            self.query(
                query_id="T-SIBLING",
                biomarker="FGFR2::BICC1 Fusion",
                disease="Cholangiolocellular Carcinoma",
            )
        )
        relations = {
            item.provenance["disease_relation_provenance"]["relation_type"]
            for item in result.audit_only_results
        }
        self.assertTrue(relations & {"disease_sibling", "unresolved_disease_relation"})
        self.assertEqual(len(result.primary_ranked_results), 0)

    def test_the_disease_gate_is_not_reconstructed_by_fuzzy_matching(self) -> None:
        result = self.retriever.retrieve(
            self.query(
                query_id="T-FUZZY", biomarker="EGFR L858R", disease="Klingon Sarcoma"
            )
        )
        self.assertEqual(len(result.primary_ranked_results), 0)
        self.assertEqual(len(result.retained_with_warning), 0)

    def test_a_diagnostic_query_does_not_return_therapeutic_claims(self) -> None:
        result = self.retriever.retrieve(
            self.query(
                query_id="T-DIAG",
                claim_domain="diagnostic",
                biomarker="FGFR2::BICC1 Fusion",
                disease="Intrahepatic Cholangiocarcinoma",
            )
        )
        for item in result.primary_ranked_results + result.retained_with_warning:
            with self.subTest(claim=item.claim_id):
                self.assertEqual(item.claim_domain, "diagnostic")

    def test_an_untyped_query_returns_separate_sections(self) -> None:
        result = self.retriever.retrieve(
            self.query(
                query_id="T-UNTYPED",
                claim_domain="untyped",
                biomarker="FGFR2::BICC1 Fusion",
                disease="Intrahepatic Cholangiocarcinoma",
            )
        )
        sections = result.sections()
        self.assertEqual(set(sections), set(RESULT.SECTIONS))
        self.assertEqual(len(sections["diagnostic_results"]), 1)
        self.assertEqual(len(sections["therapeutic_results"]), 1)
        self.assertEqual(len(sections["prognostic_results"]), 0)

    def test_the_conjunctive_biomarker_match_is_preserved(self) -> None:
        gene_only = self.retriever.retrieve(
            self.query(
                query_id="T-GENE",
                gene="EGFR",
                biomarker="",
                disease="Lung Non-small Cell Carcinoma",
            )
        )
        self.assertEqual(len(gene_only.primary_ranked_results), 0)

        t790m = self.retriever.retrieve(
            self.query(
                query_id="T-T790M",
                biomarker="EGFR T790M",
                disease="Lung Non-small Cell Carcinoma",
            )
        )
        reached = {item.graph_evidence_id for item in t790m.primary_ranked_results}
        self.assertIn("evidence:1867", reached)
        # I claim congiuntivi non sono raggiunti da un solo membro della congiunzione.
        self.assertNotIn("evidence:11598", reached)
        self.assertNotIn("evidence:11599", reached)
        self.assertNotIn("evidence:11219", reached)

    def test_a_disease_alias_does_not_compensate_an_incompatible_biomarker(
        self,
    ) -> None:
        result = self.retriever.retrieve(
            self.query(query_id="T-COMP", biomarker="EGFR L858R", disease="NSCLC")
        )
        # Solo i claim: il contenitore di provenienza dello stesso record finisce
        # in audit per il proprio stato, e non per la relazione di malattia.
        claims = [
            item
            for item in result.all_results
            if item.graph_evidence_id == "evidence:11219"
            and item.claim_id.startswith("CLM-")
        ]
        self.assertEqual(len(claims), 1)
        for item in claims:
            with self.subTest(claim=item.claim_id):
                self.assertEqual(item.bucket, RESULT.REJECTED_BUCKET)
                self.assertEqual(
                    item.provenance["disease_relation_provenance"]["relation_type"],
                    "verified_disease_alias",
                )


# --------------------------------------------------------------------------
# intervento, regime, forma
# --------------------------------------------------------------------------


class InterventionTests(V3Fixture):
    """Aggregati non atomizzati, regimi non propagati, forme non fuse."""

    def _iCCA(self, **overrides: Any) -> dict[str, Any]:
        payload = self.query(
            biomarker="FGFR2::BICC1 Fusion",
            disease="Intrahepatic Cholangiocarcinoma",
        )
        payload.update(overrides)
        return payload

    def test_the_canonical_name_reaches_the_aggregate_as_warning(self) -> None:
        result = self.retriever.retrieve(
            self._iCCA(query_id="T-INFI", interventions=["infigratinib"])
        )
        warned = {item.graph_evidence_id for item in result.retained_with_warning}
        self.assertIn("evidence:1851", warned)
        self.assertNotIn(
            "evidence:1851",
            {item.graph_evidence_id for item in result.primary_ranked_results},
        )

    def test_the_source_literal_reaches_the_same_aggregate_with_the_same_bucket(
        self,
    ) -> None:
        canonical = self.retriever.retrieve(
            self._iCCA(query_id="T-INFI", interventions=["infigratinib"])
        )
        literal = self.retriever.retrieve(
            self._iCCA(query_id="T-BGJ", interventions=["BGJ398"])
        )
        self.assertEqual(
            {item.claim_id for item in canonical.retained_with_warning},
            {item.claim_id for item in literal.retained_with_warning},
        )

    def test_both_the_source_literal_and_the_canonical_label_stay_visible(self) -> None:
        result = self.retriever.retrieve(
            self._iCCA(query_id="T-BOTH", interventions=["BGJ398"])
        )
        aggregate = next(
            item
            for item in result.retained_with_warning
            if item.graph_evidence_id == "evidence:1851"
        )
        self.assertIn("BGJ398", aggregate.source_literal_members)
        self.assertIn("infigratinib", aggregate.intervention_members)
        self.assertIn("BGJ398", aggregate.intervention_members)
        terminology = aggregate.provenance["terminology_provenance"]
        self.assertEqual(terminology["canonical_label"], "infigratinib")
        self.assertEqual(terminology["source_literal_term"], "BGJ398")
        self.assertTrue(terminology["source_literal_preserved"])

    def test_the_aggregate_is_never_atomized(self) -> None:
        result = self.retriever.retrieve(
            self._iCCA(query_id="T-AGG", interventions=["infigratinib"])
        )
        aggregate = next(
            item
            for item in result.retained_with_warning
            if item.graph_evidence_id == "evidence:1851"
        )
        self.assertEqual(aggregate.claim_type, "aggregate_intervention_claim")
        self.assertFalse(aggregate.score["used_for_clinical_ranking"])

    def test_a_verified_salt_is_warning_and_an_unregistered_suffix_is_not(self) -> None:
        phosphate = self.retriever.retrieve(
            self.query(
                query_id="T-PHOS",
                biomarker="FGFR2::BICC1 Fusion",
                disease="Cholangiocarcinoma",
                interventions=["infigratinib phosphate"],
            )
        )
        warned = {
            item.graph_evidence_id: item.provenance["formulation_provenance"][
                "relation_type"
            ]
            for item in phosphate.retained_with_warning
        }
        self.assertEqual(
            warned.get("evidence:1851"), "verified_salt_of_active_moiety"
        )

        hydrochloride = self.retriever.retrieve(
            self.query(
                query_id="T-HCL",
                biomarker="FGFR2::BICC1 Fusion",
                disease="Cholangiocarcinoma",
                interventions=["infigratinib hydrochloride"],
            )
        )
        self.assertEqual(len(hydrochloride.retained_with_warning), 0)
        relations = {
            item.provenance["formulation_provenance"]["relation_type"]
            for item in hydrochloride.audit_only_results
        }
        self.assertIn("unresolved_formulation_relation", relations)

    def test_the_suffix_is_not_stripped_automatically(self) -> None:
        result = self.retriever.retrieve(
            self.query(
                query_id="T-STRIP",
                biomarker="FGFR2::BICC1 Fusion",
                disease="Cholangiocarcinoma",
                interventions=["infigratinib hydrochloride"],
            )
        )
        self.assertEqual(len(result.primary_ranked_results), 0)

    def test_auy922_stays_unresolved(self) -> None:
        result = self.retriever.retrieve(
            self.query(
                query_id="T-AUY",
                biomarker="EML4::ALK Fusion AND ALK C1156Y",
                disease="Lung Non-small Cell Carcinoma",
                interventions=["AUY922"],
            )
        )
        self.assertEqual(len(result.primary_ranked_results), 0)
        self.assertEqual(len(result.retained_with_warning), 0)
        unresolved = {
            item.graph_evidence_id
            for item in result.audit_only_results
            if item.claim_type == "unresolved_association"
        }
        self.assertIn("evidence:841", unresolved)

    def test_an_exact_regimen_is_primary_and_a_component_query_is_not(self) -> None:
        exact = self.retriever.retrieve(
            self.query(
                query_id="T-REG",
                biomarker="EGFR L858R OR EGFR Exon 19 Deletion",
                disease="Lung Non-small Cell Carcinoma",
                interventions=["erlotinib", "ramucirumab"],
                intervention_combination=True,
            )
        )
        primary = {
            item.claim_type
            for item in exact.primary_ranked_results
            if item.graph_evidence_id == "evidence:11240"
        }
        self.assertEqual(primary, {"regimen_claim"})

        component = self.retriever.retrieve(
            self.query(
                query_id="T-COMP-REG",
                biomarker="EGFR L858R OR EGFR Exon 19 Deletion",
                disease="Lung Non-small Cell Carcinoma",
                interventions=["erlotinib"],
            )
        )
        regimen = next(
            item
            for item in component.retained_with_warning
            if item.claim_type == "regimen_claim"
        )
        self.assertEqual(regimen.graph_evidence_id, "evidence:11240")
        self.assertIn(
            "RESULT_APPLIES_TO_COMBINATION_NOT_COMPONENT", regimen.warnings
        )

    def test_an_unknown_drug_code_reaches_nothing(self) -> None:
        result = self.retriever.retrieve(
            self.query(
                query_id="T-UNKNOWN-DRUG",
                biomarker="EGFR L858R",
                disease="NSCLC",
                interventions=["ZZZ-999999"],
            )
        )
        self.assertEqual(len(result.primary_ranked_results), 0)
        self.assertEqual(len(result.retained_with_warning), 0)


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------


class ProvenanceTests(V3Fixture):
    """Ogni risultato porta la catena con cui risalire al record del grafo."""

    REQUIRED = (
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
    )

    def test_every_result_carries_the_full_provenance_keys(self) -> None:
        result = self.retriever.retrieve(
            self.query(query_id="T-PROV", biomarker="EGFR L858R", disease="NSCLC")
        )
        for item in result.all_results[:60]:
            with self.subTest(claim=item.claim_id):
                self.assertEqual(
                    sorted(item.provenance), sorted(self.REQUIRED)
                )

    def test_a_deprecated_claim_carries_its_redirect(self) -> None:
        result = self.retriever.retrieve(
            self.query(
                query_id="T-REDIRECT",
                claim_domain="diagnostic",
                biomarker="FGFR2::BICC1 Fusion",
                disease="Cholangiocarcinoma",
            )
        )
        redirects = {
            item.claim_id: item.provenance["deprecated_redirect"]
            for item in result.all_results
            if item.provenance["deprecated_redirect"]
        }
        self.assertIn("CLM-2175b95ae3113c4f5d97", redirects)
        self.assertEqual(
            redirects["CLM-2175b95ae3113c4f5d97"], "CLM-8941c177da91f66ff93a"
        )

    def test_the_propagation_policy_travels_with_the_result(self) -> None:
        result = self.retriever.retrieve(
            self.query(query_id="T-POLICY", biomarker="EGFR L858R", disease="NSCLC")
        )
        for item in result.primary_ranked_results:
            with self.subTest(claim=item.claim_id):
                self.assertEqual(item.provenance["propagation_policy"], "prototype_only")
                self.assertFalse(
                    item.provenance["qualification_status"]["final_evaluable"]
                )
                self.assertFalse(
                    item.provenance["qualification_status"]["hard_filterable"]
                )

    def test_the_result_records_backend_corpus_and_policy(self) -> None:
        result = self.retriever.retrieve(self.query(query_id="T-OBS"))
        self.assertEqual(result.backend_name, BACKEND_QUALIFIED_CLAIM_V3)
        self.assertEqual(result.repository_version, CONTRACT.REPOSITORY_VERSION)
        self.assertEqual(result.policy_mode, DEFAULT_POLICY_MODE)
        self.assertTrue(result.corpus_hash)
        self.assertTrue(result.run_id.startswith("RUN-"))
        self.assertEqual(result.timestamp, CONTRACT.PROMOTED_AT)
        self.assertEqual(
            set(result.latency_ms), {"gating", "normalization", "ranking", "total"}
        )


# --------------------------------------------------------------------------
# dual-run
# --------------------------------------------------------------------------


class DualRunTests(unittest.TestCase):
    """Il dual-run descrive la divergenza, non la giudica."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline = EvidenceRetrievalPipeline()
        cls.rows = _read_jsonl(ARTIFACTS / "dual_run_diagnostic.jsonl")

    def test_the_diagnostic_covers_every_regression_query(self) -> None:
        self.assertEqual(
            [row["query_id"] for row in self.rows],
            [query["query_id"] for query in BINDING.REGRESSION_QUERIES],
        )

    def test_no_gold_metric_is_computed(self) -> None:
        contract = DIAG.diagnostic_contract()
        self.assertFalse(contract["gold_read"])
        self.assertFalse(contract["gold_metrics_computed"])
        self.assertFalse(contract["legacy_and_v3_result_counts_compared"])
        for row in self.rows:
            with self.subTest(query=row["query_id"]):
                self.assertFalse(row["gold_metrics_computed"])

    def test_both_normalized_queries_are_recorded(self) -> None:
        for row in self.rows:
            with self.subTest(query=row["query_id"]):
                self.assertTrue(row["v3_normalized_query"])
                self.assertIn("v3_bucket_counts", row)

    def test_the_dual_run_is_deterministic(self) -> None:
        first = DIAG.diagnose(
            {
                "query_id": "RB-05-FGFR2-CCA",
                "claim_domain": "therapeutic",
                "biomarker": "FGFR2::BICC1 Fusion",
                "disease": "Cholangiocarcinoma",
            },
            pipeline=self.pipeline,
            legacy_query=BINDING.LEGACY_QUERIES["RB-05-FGFR2-CCA"],
        ).to_dict()
        second = DIAG.diagnose(
            {
                "query_id": "RB-05-FGFR2-CCA",
                "claim_domain": "therapeutic",
                "biomarker": "FGFR2::BICC1 Fusion",
                "disease": "Cholangiocarcinoma",
            },
            pipeline=self.pipeline,
            legacy_query=BINDING.LEGACY_QUERIES["RB-05-FGFR2-CCA"],
        ).to_dict()
        for payload in (first, second):
            payload.pop("latency_ms")
        self.assertEqual(first, second)

    def test_the_overlap_is_measured_on_graph_evidence_records(self) -> None:
        self.assertEqual(DIAG.diagnostic_contract()["compared_on"], "graph_evidence_record_id")

    def test_a_failing_side_is_recorded_and_not_raised(self) -> None:
        row = DIAG.diagnose(
            {
                "query_id": "T-BROKEN",
                "claim_domain": "therapeutic",
                "biomarker": "EGFR L858R",
                "disease": "NSCLC",
            },
            pipeline=self.pipeline,
            legacy_query={"query_id": "T-BROKEN"},
        )
        self.assertIn("legacy", row.errors)
        self.assertTrue(row.v3_bucket_counts)


# --------------------------------------------------------------------------
# pipeline
# --------------------------------------------------------------------------


class PipelineBindingTests(unittest.TestCase):
    """La pipeline esegue entrambi i backend senza convertirne i risultati."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline = EvidenceRetrievalPipeline()

    def test_the_two_backends_return_their_own_types(self) -> None:
        legacy = self.pipeline.run(
            BINDING.LEGACY_QUERIES["RB-01-EGFR-L858R-NSCLC"],
            retrieval_backend=BACKEND_LEGACY,
        )
        v3 = self.pipeline.run(
            {
                "query_id": "RB-01-EGFR-L858R-NSCLC",
                "claim_domain": "therapeutic",
                "gene": "EGFR",
                "alteration": "L858R",
                "disease": "NSCLC",
            },
            retrieval_backend=BACKEND_QUALIFIED_CLAIM_V3,
        )
        self.assertFalse(legacy.is_v3)
        self.assertTrue(v3.is_v3)
        self.assertEqual(legacy.repository_version, SUPPORTED_CORPUS_VERSION)
        self.assertEqual(v3.repository_version, CONTRACT.REPOSITORY_VERSION)
        self.assertIsInstance(v3.payload, RESULT.QualifiedClaimRetrievalResult)

    def test_the_observability_record_names_backend_corpus_and_policy(self) -> None:
        outcome = self.pipeline.run(
            {
                "query_id": "T-OBS",
                "claim_domain": "therapeutic",
                "biomarker": "EGFR L858R",
                "disease": "NSCLC",
            },
            retrieval_backend=BACKEND_QUALIFIED_CLAIM_V3,
        )
        record = outcome.observability
        for key in (
            "backend_name",
            "bucket_counts",
            "corpus_hash",
            "failure_reason",
            "gate_decisions",
            "latency_ms",
            "policy_mode",
            "query_id",
            "repository_version",
            "run_id",
            "timestamp",
        ):
            with self.subTest(field=key):
                self.assertIn(key, record)
        self.assertFalse(record["gold_data_recorded"])

    def test_the_configured_default_is_used_when_no_backend_is_named(self) -> None:
        outcome = self.pipeline.run(BINDING.LEGACY_QUERIES["RB-02-EGFR-L858R-LUAD"])
        self.assertEqual(outcome.backend_name, BACKEND_LEGACY)


# --------------------------------------------------------------------------
# determinismo e artefatti
# --------------------------------------------------------------------------


class DeterminismTests(V3Fixture):
    """Due esecuzioni identiche danno lo stesso risultato, latenza esclusa."""

    def test_the_same_query_gives_the_same_digest(self) -> None:
        payload = self.query(query_id="T-DET", biomarker="EGFR L858R", disease="NSCLC")
        first = self.retriever.retrieve(payload)
        second = self.retriever.retrieve(payload)
        self.assertEqual(first.canonical_digest(), second.canonical_digest())
        self.assertEqual(first.run_id, second.run_id)

    def test_a_second_retriever_on_the_same_corpus_agrees(self) -> None:
        other = V3.QualifiedClaimRetrieverV3.from_registry()
        payload = self.query(query_id="T-DET2", biomarker="EGFR T790M", disease="NSCLC")
        self.assertEqual(
            self.retriever.retrieve(payload).canonical_digest(),
            other.retrieve(payload).canonical_digest(),
        )

    def test_the_recorded_regression_digests_are_reproducible(self) -> None:
        rows = {
            row["query_id"]: row
            for row in _read_jsonl(ARTIFACTS / "v3_regression_results.jsonl")
        }
        for query in BINDING.REGRESSION_QUERIES:
            payload = {
                key: value for key, value in query.items() if key != "expectation"
            }
            with self.subTest(query=query["query_id"]):
                result = self.retriever.retrieve(payload)
                recorded = rows[query["query_id"]]
                self.assertEqual(result.canonical_digest(), recorded["result_digest"])
                self.assertEqual(result.bucket_counts(), recorded["bucket_counts"])
                self.assertTrue(recorded["deterministic"])


class ArtifactTests(unittest.TestCase):
    """Gli artefatti dicono cio' che e' stato misurato, e non piu' di quello."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = _read_json(ARTIFACTS / "retriever_binding_manifest.json")

    def test_every_declared_artifact_exists(self) -> None:
        for name in (
            "EXPLORATORY_RERUN_READINESS.md",
            "LEGACY_VS_V3_BINDING.md",
            "V3_RETRIEVER_ARCHITECTURE.md",
            "backend_selection_contract.json",
            "dual_run_diagnostic.jsonl",
            "gate_execution_order.json",
            "legacy_parity.json",
            "retriever_binding_manifest.json",
            "v3_query_schema.json",
            "v3_regression_queries.jsonl",
            "v3_regression_results.jsonl",
            "v3_retrieval_result_schema.json",
            "v3_retriever_contract.json",
        ):
            with self.subTest(artifact=name):
                self.assertTrue((ARTIFACTS / name).is_file())

    def test_the_expected_readiness_flags_hold(self) -> None:
        expected = {
            "backend_selection_explicit": True,
            "clinical_readiness": False,
            "dual_run_diagnostic_ready": True,
            "four_bucket_output_implemented": True,
            "full_exploratory_rerun_ready": True,
            "integrated_gates_applied": True,
            "legacy_default_preserved": True,
            "operational_pipeline_unchanged_for_legacy": True,
            "operational_retriever_bound_to_v3": False,
            "promoted_corpus_loadable_by_v3_retriever": True,
            "provenance_complete": True,
            "strict_default_preserved": True,
            "unknown_backend_rejected": True,
            "unknown_policy_rejected": True,
            "v3_prototype_endpoint_ready": True,
            "v3_retriever_implemented": True,
        }
        for key, value in sorted(expected.items()):
            with self.subTest(flag=key):
                self.assertEqual(self.manifest["readiness"][key], value)

    def test_the_phase_does_not_claim_clinical_readiness(self) -> None:
        self.assertFalse(self.manifest["readiness"]["clinical_readiness"])
        self.assertFalse(self.manifest["readiness"]["operational_retriever_bound_to_v3"])
        self.assertFalse(self.manifest["pipeline_binding"]["v3_is_default"])

    def test_the_regression_queries_are_the_fourteen_declared_ones(self) -> None:
        rows = _read_jsonl(ARTIFACTS / "v3_regression_queries.jsonl")
        self.assertEqual(len(rows), 14)
        self.assertEqual(
            [row["query_id"] for row in rows],
            [query["query_id"] for query in BINDING.REGRESSION_QUERIES],
        )
        for row in rows:
            with self.subTest(query=row["query_id"]):
                self.assertTrue(row["expectation"])


# --------------------------------------------------------------------------
# perimetro
# --------------------------------------------------------------------------


class CorpusUntouchedTests(unittest.TestCase):
    """Il corpus promosso non e' stato toccato, e il gold non e' stato letto."""

    def test_the_promoted_corpus_files_match_their_manifest(self) -> None:
        manifest = _read_json(PROMOTED_CORPUS / CONTRACT.MANIFEST_FILE)
        for name, expected in sorted(manifest["artifact_sha256"].items()):
            with self.subTest(artifact=name):
                actual = hashlib.sha256(
                    (PROMOTED_CORPUS / name).read_text(encoding="utf-8").encode("utf-8")
                ).hexdigest()
                self.assertEqual(actual, expected)

    def test_the_registry_still_declares_the_retriever_unbound(self) -> None:
        entry = _read_json(PROMOTED_CORPUS / "corpus_registry_entry.json")
        self.assertFalse(entry["operational_retriever_bound"])
        self.assertFalse(entry["clinical_readiness"])
        self.assertFalse(entry["final_evaluable"])
        self.assertEqual(entry["default_policy_mode"], "strict_verified")
        self.assertEqual(entry["unknown_policy_mode_behavior"], "reject")

    def test_no_phase_module_reads_the_gold(self) -> None:
        package = REPO_ROOT / "backend" / "pipeline" / "evidence" / "retrieval"
        sources = sorted(package.glob("*.py")) + [
            REPO_ROOT / "benchmarks" / "mtb_evidence" / "evaluation" / "retriever_binding_1_4.py",
            REPO_ROOT
            / "benchmarks"
            / "mtb_evidence"
            / "evaluation"
            / "retriever_binding_reports.py",
        ]
        for path in sources:
            body = path.read_text(encoding="utf-8")
            with self.subTest(module=path.name):
                self.assertNotIn("mtb_evidence_gold", body)
                self.assertNotIn("provisional_gold", body)
                self.assertNotIn("gold_pilot", body)


class PhasePerimeterTests(unittest.TestCase):
    """Il perimetro della fase, misurato su un intervallo chiuso di commit."""

    def test_the_phase_wrote_only_inside_its_own_perimeter(self) -> None:
        if not PHASE_END_SHA:
            self.skipTest("la fase non e' ancora chiusa: nessun estremo da misurare")
        scope = PhaseScope(
            REPO_ROOT.parent, START_SHA, PHASE_END_SHA, ALLOWED_WRITE_PREFIXES
        )
        self.assertEqual(scope.violations(scope.changed_paths()), [])

    def test_no_frozen_path_is_writable(self) -> None:
        for path in FROZEN_PATHS:
            with self.subTest(path=path):
                self.assertFalse(path.startswith(ALLOWED_WRITE_PREFIXES))

    def test_the_retrieval_package_is_not_inside_the_promoted_namespace(self) -> None:
        for prefix in ALLOWED_WRITE_PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertFalse(prefix.startswith(CONTRACT.PROMOTED_CORPUS_RELPATH))
                self.assertNotEqual(prefix, CONTRACT.REGISTRY_RELPATH)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
