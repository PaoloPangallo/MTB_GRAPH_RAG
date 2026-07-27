"""Protegge gli invarianti del repository shadow 1.3.

I test difendono sei cose, e ognuna e' un modo di sbagliare che questa fase
rende possibile per la prima volta.

Che la canonicalizzazione verificata cambi una rappresentazione e non una
proposizione: gli ID cambiano, i conteggi no, e l'aggregato non si scompone.

Che il letterale della fonte sopravviva alla canonicalizzazione, perche' una
identificazione successiva non riscrive un documento del 2013.

Che la coda terminologica non sembri vuota: AUY922 resta irrisolto e continua a
comparire nel registro con lo stesso rilievo di cio' che e' stato chiuso.

Che il gate integrato sia una congiunzione e non una somma: un solo gate
incompatibile impedisce il primario, e nessun punteggio, per quanto alto, lo
riapre.

Che i bucket non ordinabili non ereditino flag di score dal gate piu'
permissivo.

Che la fase non abbia toccato nulla di cio' che dichiara di non toccare.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from backend.pipeline.evidence.shadow import disease_gate as DISEASE
from backend.pipeline.evidence.shadow import integrated_gates as GATE
from backend.pipeline.evidence.shadow import shadow_output_v12 as OUT
from backend.pipeline.evidence.shadow.terminology_v13 import (
    CANONICALIZED_GRAPH_EVIDENCE_IDS,
    REPOSITORY_VERSION,
    UNRESOLVED_DECISION_ID,
    UNRESOLVED_SOURCE_LITERAL,
    VERIFIED_CANONICAL_LABEL,
    VERIFIED_DECISION_ID,
    VERIFIED_SOURCE_LITERAL,
    CanonicalizedAggregateClaim,
    TerminologyApplicationError,
    apply_verified_terminology,
    canonical_aggregate_label,
)
from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy import (
    CLAIM_IS_CHILD_OF_QUERY,
    CLAIM_IS_PARENT_OF_QUERY,
    CROSS_DISEASE,
    DISEASE_SIBLING,
    EXACT_DISEASE,
    EXACT_RELATIONS,
    GENERIC_CANCER_SCOPE,
    MISSING_CLAIM_DISEASE,
    MISSING_QUERY_DISEASE,
    NORMALIZED_EXACT_DISEASE,
    POLICY_MODES,
    RELATION_TYPES,
    STRICT_VERIFIED,
    UNRESOLVED_DISEASE_RELATION,
    VERIFIED_DISEASE_ALIAS,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_integrated_shadow_repository_1_3 import (
    DEFAULT_OUTPUT,
    EXPECTED_COUNTS,
    EXPECTED_NEW_CLAIM_IDS,
    EXPECTED_OLD_CLAIM_IDS,
    START_SHA,
    all_queries,
    build_data_artifacts,
    run_migration,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
OUTPUT = DEFAULT_OUTPUT

# Estremo di fase: il commit che chiude la fase, mai HEAD. Il perimetro di una
# fase e' una proprieta' storica e chiusa, e misurarlo contro l'albero di lavoro
# lo farebbe crescere con la fase successiva, fallendo per la ragione sbagliata.
PHASE_END_SHA = "6b62108e110d78235556e17bb31815a31b619609"

ALLOWED_WRITE_PREFIXES = (
    "benchmarks/mtb_evidence/v3/integrated_shadow_repository_1_3/",
    "benchmarks/mtb_evidence/evaluation/integrated_shadow_repository_reports.py",
    "benchmarks/mtb_evidence/evaluation/scripts/build_integrated_shadow_repository_1_3.py",
    "backend/pipeline/evidence/shadow/disease_gate.py",
    "backend/pipeline/evidence/shadow/integrated_gates.py",
    "backend/pipeline/evidence/shadow/shadow_output_v12.py",
    "backend/pipeline/evidence/shadow/terminology_v13.py",
    "backend/tests/test_integrated_shadow_repository_1_3.py",
)

FROZEN_OPERATIONAL_PATHS = (
    "backend/pipeline/evidence/qualification.py",
    "backend/pipeline/evidence/qualified_disease_matching.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/v2_adapter.py",
    "benchmarks/mtb_evidence/pilot/audit_lib/disease.py",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualification_links.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl",
)

FROZEN_SHADOW_DIRS = (
    "benchmarks/mtb_evidence/v3/typed_claim_shadow_migration",
    "benchmarks/mtb_evidence/v3/non_therapeutic_shadow_update",
    "benchmarks/mtb_evidence/v3/diagnostic_disease_scope_narrowing_shadow",
    "benchmarks/mtb_evidence/v3/terminology_mapping_closure",
    "benchmarks/mtb_evidence/v3/disease_hierarchy_policy",
)

THERAPEUTIC = "therapeutic_evidence_query"
DIAGNOSTIC = "diagnostic_evidence_query"
NSCLC_PAIR = "EGFR L858R OR EGFR Exon 19 Deletion"
ICCA = "Intrahepatic Cholangiocarcinoma"
CCA = "Cholangiocarcinoma"
NSCLC = "Lung Non-small Cell Carcinoma"


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RepositoryCase(unittest.TestCase):
    """Il repository viene costruito una volta sola: e' deterministico."""

    result = None
    claims = None
    gate_rows = None
    queries = None

    @classmethod
    def setUpClass(cls) -> None:
        if RepositoryCase.result is None:
            RepositoryCase.result = run_migration()
            RepositoryCase.queries = all_queries()
        cls.result = RepositoryCase.result
        cls.queries = RepositoryCase.queries
        cls.claims = {claim.claim_id: claim for claim in cls.result.evidence_claims}

    def claim_for(self, graph_evidence_id: str, claim_type: str | None = None):
        found = [
            claim
            for claim in self.result.evidence_claims
            if claim.graph_evidence_id == graph_evidence_id
            and (claim_type is None or claim.claim_type == claim_type)
        ]
        self.assertTrue(found, f"nessun claim per {graph_evidence_id}")
        return found[0]


# ---------------------------------------------------------------------------
# repository
# ---------------------------------------------------------------------------


class TestRepositoryCounts(RepositoryCase):
    def test_the_counts_are_the_ones_the_phase_declares(self) -> None:
        types = {}
        domains = {}
        for claim in self.result.evidence_claims:
            types[claim.claim_type] = types.get(claim.claim_type, 0) + 1
            domain = getattr(claim, "claim_domain", None) or "therapeutic"
            domains[domain] = domains.get(domain, 0) + 1
        observed = {
            "active_claims_total": self.result.total_claims,
            "aggregate_intervention_claim": types.get(
                "aggregate_intervention_claim", 0
            ),
            "atomic_intervention_claim": types.get("atomic_intervention_claim", 0),
            "diagnostic_claims": domains.get("diagnostic", 0),
            "parents": len(self.result.parents),
            "parents_without_claims": len(self.result.parents_without_claims),
            "prognostic_claims": domains.get("prognostic", 0),
            "regimen_claim": types.get("regimen_claim", 0),
            "therapeutic_claims": domains.get("therapeutic", 0),
            "unresolved_associations": len(self.result.unresolved),
            "unsupported_associations": len(self.result.unsupported),
        }
        self.assertEqual(observed, EXPECTED_COUNTS)

    def test_retired_claims_are_not_counted_among_the_active_ones(self) -> None:
        active = {claim.claim_id for claim in self.result.evidence_claims}
        retired = {row["claim_id"] for row in self.result.deprecated_aggregate_claims}
        retired |= {row["claim_id"] for row in self.result.deprecated_diagnostic_claims}
        self.assertEqual(len(retired), 4)
        self.assertEqual(active & retired, set())
        self.assertEqual(len(active), 148)

    def test_the_three_parents_without_claims_are_unchanged(self) -> None:
        observed = sorted(
            row["graph_evidence_id"] for row in self.result.parents_without_claims
        )
        self.assertEqual(observed, ["evidence:347", "evidence:3811", "evidence:4759"])

    def test_no_claim_id_collides(self) -> None:
        ids = [claim.claim_id for claim in self.result.evidence_claims]
        ids += [row["claim_id"] for row in self.result.deprecated_aggregate_claims]
        ids += [row["claim_id"] for row in self.result.deprecated_diagnostic_claims]
        self.assertEqual(len(ids), len(set(ids)))


# ---------------------------------------------------------------------------
# terminologia
# ---------------------------------------------------------------------------


class TestTerminology(RepositoryCase):
    def test_the_two_groups_receive_the_recomputed_identifiers(self) -> None:
        observed = {
            row["graph_evidence_id"]: row["new_claim_id"]
            for row in self.result.replacement_lineage
        }
        self.assertEqual(observed, EXPECTED_NEW_CLAIM_IDS)

    def test_the_identifiers_come_from_the_formula_and_not_from_a_constant(
        self,
    ) -> None:
        """Ricalcola l'ID dal payload reale invece di confrontarlo con se stesso."""
        from backend.pipeline.evidence.shadow.identity import claim_id

        for graph_evidence_id in CANONICALIZED_GRAPH_EVIDENCE_IDS:
            claim = self.claim_for(graph_evidence_id, "aggregate_intervention_claim")
            recomputed = claim_id(
                graph_evidence_id=claim.graph_evidence_id,
                claim_type=claim.claim_type,
                canonical_intervention_or_regimen=claim.canonical_intervention,
                biomarker=claim.biomarker,
                direction=claim.direction,
                polarity=claim.polarity,
                source_unit_id=claim.source_unit_ids[0],
            )
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(recomputed, claim.claim_id)
                self.assertEqual(recomputed, EXPECTED_NEW_CLAIM_IDS[graph_evidence_id])

    def test_the_old_claims_are_retired_with_reversible_lineage(self) -> None:
        retired = {
            row["claim_id"]: row for row in self.result.deprecated_aggregate_claims
        }
        self.assertEqual(set(retired), set(EXPECTED_OLD_CLAIM_IDS.values()))
        for row in retired.values():
            with self.subTest(claim_id=row["claim_id"]):
                self.assertTrue(row["deprecated"])
                self.assertTrue(row["reversible"])
                self.assertEqual(row["terminology_decision_id"], VERIFIED_DECISION_ID)
                self.assertEqual(row["effective_repository_version"], REPOSITORY_VERSION)

    def test_the_lineage_carries_every_required_field(self) -> None:
        required = {
            "canonical_label_after",
            "canonical_label_before",
            "effective_repository_version",
            "new_claim_id",
            "old_claim_id",
            "parent_id",
            "propagation_policy",
            "reason_code",
            "reversible",
            "review_status",
            "source_literals",
            "terminology_decision_id",
        }
        for row in self.result.replacement_lineage:
            with self.subTest(old=row["old_claim_id"]):
                self.assertTrue(required <= set(row))

    def test_the_source_literal_survives_the_canonicalization(self) -> None:
        for graph_evidence_id in CANONICALIZED_GRAPH_EVIDENCE_IDS:
            claim = self.claim_for(graph_evidence_id, "aggregate_intervention_claim")
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertIn(VERIFIED_SOURCE_LITERAL, claim.source_literal_members)
                self.assertIn("PD173074", claim.source_literal_members)
                self.assertNotIn(VERIFIED_SOURCE_LITERAL, claim.canonical_members)

    def test_the_canonical_member_is_the_verified_label(self) -> None:
        for graph_evidence_id in CANONICALIZED_GRAPH_EVIDENCE_IDS:
            claim = self.claim_for(graph_evidence_id, "aggregate_intervention_claim")
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertIn(VERIFIED_CANONICAL_LABEL, claim.canonical_members)
                self.assertIn("PD173074", claim.canonical_members)
                self.assertEqual(
                    claim.canonical_intervention, "infigratinib + pd173074"
                )

    def test_the_aggregate_is_not_atomized(self) -> None:
        for graph_evidence_id in CANONICALIZED_GRAPH_EVIDENCE_IDS:
            claim = self.claim_for(graph_evidence_id, "aggregate_intervention_claim")
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertIsInstance(claim, CanonicalizedAggregateClaim)
                self.assertEqual(claim.claim_type, "aggregate_intervention_claim")
                self.assertFalse(claim.permits_member_specific_claims)

    def test_no_atomic_claim_was_created_for_the_canonicalized_members(self) -> None:
        atomic_labels = {
            claim.canonical_intervention
            for claim in self.result.evidence_claims
            if claim.claim_type == "atomic_intervention_claim"
            and claim.graph_evidence_id in CANONICALIZED_GRAPH_EVIDENCE_IDS
        }
        self.assertEqual(atomic_labels, set())

    def test_the_aggregate_label_does_not_depend_on_member_order(self) -> None:
        forward = canonical_aggregate_label(["infigratinib", "PD173074"])
        backward = canonical_aggregate_label(["PD173074", "infigratinib"])
        self.assertEqual(forward, backward)

    def test_auy922_is_still_unresolved(self) -> None:
        registry = _load_json(OUTPUT / "terminology_registry_v1_3.json")
        unresolved = registry["unresolved_mappings"]
        self.assertEqual(len(unresolved), 1)
        entry = unresolved[0]
        self.assertEqual(entry["terminology_decision_id"], UNRESOLVED_DECISION_ID)
        self.assertEqual(entry["source_literal_term"], UNRESOLVED_SOURCE_LITERAL)
        self.assertFalse(entry["is_verified"])
        self.assertFalse(entry["exact_alias_created"])
        self.assertEqual(entry["mapping_scope"], "none")
        self.assertEqual(entry["claims_materialized"], 0)
        self.assertFalse(registry["queue_fully_resolved"])

    def test_the_registry_reports_no_collision_and_no_deduplication(self) -> None:
        registry = _load_json(OUTPUT / "terminology_registry_v1_3.json")
        self.assertEqual(registry["collisions"], 0)
        self.assertEqual(registry["deduplications"], 0)
        self.assertEqual(registry["propositions_created"], 0)
        self.assertEqual(registry["propositions_removed"], 0)

    def test_an_unverified_decision_cannot_be_applied(self) -> None:
        """Il guardrail e' un test perche' e' l'errore piu' facile da introdurre."""
        decisions = _load_jsonl(
            V3 / "terminology_mapping_closure/mapping_decisions.jsonl"
        )
        tampered = [
            dict(row) | {"is_verified": False}
            if row["pair_id"] == VERIFIED_DECISION_ID
            else row
            for row in decisions
        ]
        with self.assertRaises(TerminologyApplicationError):
            apply_verified_terminology(self.result, tampered)

    def test_promoting_auy922_is_refused(self) -> None:
        decisions = _load_jsonl(
            V3 / "terminology_mapping_closure/mapping_decisions.jsonl"
        )
        tampered = [
            dict(row) | {"is_verified": True, "mapping_scope": "global"}
            if row["pair_id"] == UNRESOLVED_DECISION_ID
            else row
            for row in decisions
        ]
        with self.assertRaises(TerminologyApplicationError):
            apply_verified_terminology(self.result, tampered)


# ---------------------------------------------------------------------------
# disease gate
# ---------------------------------------------------------------------------


class TestDiseaseGate(RepositoryCase):
    def test_every_declared_relation_is_reachable_by_the_gate(self) -> None:
        self.assertEqual(sorted(DISEASE.gate_contract()["relation_types"]), sorted(RELATION_TYPES))

    def test_strict_verified_is_the_default(self) -> None:
        self.assertEqual(DISEASE.DEFAULT_POLICY_MODE, STRICT_VERIFIED)
        self.assertEqual(DISEASE.policy_mode({"query_id": "q"}), STRICT_VERIFIED)

    def test_an_unknown_mode_is_refused_instead_of_falling_back(self) -> None:
        with self.assertRaises(DISEASE.DiseaseGateError):
            DISEASE.policy_mode({"disease_policy_mode": "broad"})

    def _relation(self, query_disease: str, claim) -> DISEASE.DiseaseGateResult:
        return DISEASE.evaluate({"query_id": "q", "disease": query_disease}, claim)

    def test_exact_normalized_and_alias_are_primary(self) -> None:
        claim = self.claim_for("evidence:11240", "atomic_intervention_claim")
        # Lo spazio in piu' non basta a produrre `normalized_exact_disease`: il
        # confronto letterale avviene gia' dopo lo strip. Serve una differenza
        # che sopravviva allo strip e sparisca nella normalizzazione, come la
        # differenza di maiuscole.
        for query_disease, expected in (
            (NSCLC, EXACT_DISEASE),
            (NSCLC.lower(), NORMALIZED_EXACT_DISEASE),
            ("NSCLC", VERIFIED_DISEASE_ALIAS),
        ):
            with self.subTest(query_disease=query_disease):
                result = self._relation(query_disease, claim)
                self.assertEqual(result.relation_type, expected)
                self.assertTrue(result.primary_candidate_eligible)
                self.assertTrue(result.is_exact_relation)

    def test_parent_and_child_are_warning_and_never_primary(self) -> None:
        diagnostic = self.claim_for("evidence:1846")
        aggregate = self.claim_for("evidence:1851", "aggregate_intervention_claim")
        child = self._relation(CCA, diagnostic)
        parent = self._relation(ICCA, aggregate)
        self.assertEqual(child.relation_type, CLAIM_IS_CHILD_OF_QUERY)
        self.assertEqual(child.relation_direction, "claim_narrower_than_query")
        self.assertEqual(parent.relation_type, CLAIM_IS_PARENT_OF_QUERY)
        self.assertEqual(parent.relation_direction, "claim_broader_than_query")
        for result in (child, parent):
            self.assertEqual(result.bucket, DISEASE.WARNING_BUCKET)
            self.assertFalse(result.primary_candidate_eligible)
            self.assertFalse(result.score_eligibility["structural_score_eligible"])

    def test_sibling_is_audit_only_in_every_mode(self) -> None:
        claim = self.claim_for("evidence:8173")
        for mode in POLICY_MODES:
            with self.subTest(mode=mode):
                result = DISEASE.evaluate(
                    {"query_id": "q", "disease": ICCA}, claim, mode=mode
                )
                self.assertEqual(result.relation_type, DISEASE_SIBLING)
                self.assertEqual(result.bucket, DISEASE.AUDIT_BUCKET)
                self.assertTrue(result.audit_only)

    def test_a_generic_scope_is_never_primary(self) -> None:
        claim = self.claim_for("evidence:11240", "atomic_intervention_claim")
        for mode in POLICY_MODES:
            with self.subTest(mode=mode):
                result = DISEASE.evaluate(
                    {"query_id": "q", "disease": "Cancer"}, claim, mode=mode
                )
                self.assertEqual(result.relation_type, GENERIC_CANCER_SCOPE)
                self.assertFalse(result.primary_candidate_eligible)

    def test_unresolved_and_missing_are_audit_only(self) -> None:
        claim = self.claim_for("evidence:11240", "atomic_intervention_claim")
        missing = self._relation("", claim)
        self.assertEqual(missing.relation_type, MISSING_QUERY_DISEASE)
        self.assertTrue(missing.audit_only)
        unresolved = DISEASE.evaluate(
            {"query_id": "q", "disease": "Zzz Unregistered Disease"},
            replace(claim, disease_scope="Yyy Unregistered Disease"),
        )
        self.assertEqual(unresolved.relation_type, UNRESOLVED_DISEASE_RELATION)
        self.assertTrue(unresolved.audit_only)

    def test_a_claim_without_disease_scope_is_named_as_such(self) -> None:
        association = self.result.unresolved[0]
        result = DISEASE.evaluate({"query_id": "q", "disease": NSCLC}, association)
        self.assertEqual(result.relation_type, MISSING_CLAIM_DISEASE)
        self.assertFalse(result.object_carries_disease_scope)

    def test_cross_disease_is_rejected_and_forbids_a_positive_score(self) -> None:
        claim = self.claim_for("evidence:11240", "atomic_intervention_claim")
        for mode in POLICY_MODES:
            with self.subTest(mode=mode):
                result = DISEASE.evaluate(
                    {"query_id": "q", "disease": "Breast Cancer"}, claim, mode=mode
                )
                self.assertEqual(result.relation_type, CROSS_DISEASE)
                self.assertEqual(result.bucket, DISEASE.REJECTED_BUCKET)
                self.assertTrue(result.score_eligibility["positive_score_forbidden"])

    def test_the_primary_bucket_is_identical_across_modes(self) -> None:
        """Su ogni claim e ogni disease di prova, il primario non cambia."""
        probes = (NSCLC, "NSCLC", ICCA, CCA, "Cancer", "Breast Cancer", "")
        for claim in self.result.evidence_claims:
            for probe in probes:
                results = DISEASE.evaluate_all_modes(
                    {"query_id": "q", "disease": probe}, claim
                )
                with self.subTest(claim=claim.claim_id, disease=probe):
                    self.assertTrue(DISEASE.primary_bucket_is_mode_invariant(results))
                    relations = {r.relation_type for r in results.values()}
                    self.assertEqual(len(relations), 1)

    def test_only_exact_relations_are_primary_anywhere(self) -> None:
        for relation, per_mode in DISEASE.gate_contract()["per_relation_per_mode"].items():
            for mode, policy in per_mode.items():
                with self.subTest(relation=relation, mode=mode):
                    if policy["primary_candidate_eligible"]:
                        self.assertIn(relation, EXACT_RELATIONS)


# ---------------------------------------------------------------------------
# gate integrato
# ---------------------------------------------------------------------------


class TestIntegratedGate(RepositoryCase):
    def test_disease_exact_with_incompatible_biomarker_is_rejected(self) -> None:
        claim = self.claim_for("evidence:11598")
        query = {
            "query_id": "q",
            "query_domain": THERAPEUTIC,
            "disease": NSCLC,
            "biomarker": "EGFR L858R",
            "interventions": ["osimertinib"],
        }
        result = GATE.evaluate(query, claim)
        self.assertEqual(result.final_bucket, GATE.REJECTED_BUCKET)
        self.assertIn("biomarker", result.blocking_gates)
        self.assertFalse(result.structural_score_eligible)
        self.assertFalse(result.qualified_score_eligible)
        self.assertFalse(result.final_ranking_eligible)

    def test_disease_child_with_exact_biomarker_is_warning(self) -> None:
        claim = self.claim_for("evidence:1846")
        query = {
            "query_id": "q",
            "query_domain": DIAGNOSTIC,
            "disease": CCA,
            "biomarker": "FGFR2::BICC1 Fusion",
        }
        result = GATE.evaluate(query, claim)
        self.assertEqual(result.final_bucket, GATE.WARNING_BUCKET)
        self.assertFalse(result.primary_candidate_eligible)
        self.assertFalse(result.structural_score_eligible)
        self.assertEqual(
            result.disease_match_result["relation_type"], CLAIM_IS_CHILD_OF_QUERY
        )

    def test_disease_exact_with_regimen_component_is_warning(self) -> None:
        claim = self.claim_for("evidence:11240", "regimen_claim")
        query = {
            "query_id": "q",
            "query_domain": THERAPEUTIC,
            "disease": NSCLC,
            "biomarker": NSCLC_PAIR,
            "interventions": ["erlotinib"],
        }
        result = GATE.evaluate(query, claim)
        self.assertEqual(result.final_bucket, GATE.WARNING_BUCKET)
        self.assertEqual(
            result.intervention_match_result["match_type"], "regimen_component_related"
        )
        self.assertFalse(result.structural_score_eligible)

    def test_an_unsupported_association_with_every_axis_exact_stays_audit(self) -> None:
        association = next(
            item
            for item in self.result.unsupported
            if item.graph_evidence_id == "evidence:4759"
            and item.intervention_literal == "erlotinib"
        )
        query = {
            "query_id": "q",
            "query_domain": THERAPEUTIC,
            "disease": NSCLC,
            "biomarker": NSCLC_PAIR,
            "interventions": ["erlotinib"],
        }
        result = GATE.evaluate(query, association)
        self.assertEqual(result.final_bucket, GATE.AUDIT_BUCKET)
        self.assertFalse(result.primary_candidate_eligible)

    def test_a_deprecated_claim_with_every_axis_exact_stays_audit(self) -> None:
        claim = replace(
            self.claim_for("evidence:11240", "atomic_intervention_claim"),
            deprecated=True,
        )
        query = {
            "query_id": "q",
            "query_domain": THERAPEUTIC,
            "disease": NSCLC,
            "biomarker": NSCLC_PAIR,
            "interventions": ["erlotinib"],
        }
        result = GATE.evaluate(query, claim)
        self.assertEqual(result.final_bucket, GATE.AUDIT_BUCKET)
        self.assertEqual(result.claim_status_result["status"], "deprecated_claim")
        self.assertFalse(result.qualified_score_eligible)

    def test_an_arbitrary_score_does_not_bypass_the_gate(self) -> None:
        """Il punteggio non entra in nessuna espressione: non ha una via."""
        query = {
            "query_id": "q",
            "query_domain": THERAPEUTIC,
            "disease": CCA,
            "biomarker": "FGFR2::BICC1 Fusion",
            "interventions": ["infigratinib"],
        }
        for claim in self.result.evidence_claims:
            result = GATE.evaluate(query, claim)
            for score in (0.0, 1.0, 10_000.0):
                with self.subTest(claim=claim.claim_id, score=score):
                    GATE.check_no_score_survives_a_blocking_gate(result, score)

    def test_no_score_flag_survives_in_a_non_rankable_bucket(self) -> None:
        checked = 0
        for query in self.queries:
            gate_query = {
                key: value
                for key, value in query.items()
                if key not in ("expectation", "query_source", "scenario")
            }
            for claim in self.result.evidence_claims:
                result = GATE.evaluate(gate_query, claim)
                if result.final_bucket in (GATE.AUDIT_BUCKET, GATE.REJECTED_BUCKET):
                    checked += 1
                    self.assertFalse(result.structural_score_eligible)
                    self.assertFalse(result.qualified_score_eligible)
                    self.assertFalse(result.final_ranking_eligible)
                    self.assertTrue(
                        result.score_eligibility["positive_score_forbidden"]
                    )
        self.assertGreater(checked, 0)

    def test_the_bucket_precedence_is_conservative(self) -> None:
        self.assertEqual(
            GATE.BUCKET_PRECEDENCE,
            (
                GATE.REJECTED_BUCKET,
                GATE.AUDIT_BUCKET,
                GATE.WARNING_BUCKET,
                GATE.PRIMARY_BUCKET,
            ),
        )
        contract = GATE.bucket_precedence_contract()
        self.assertEqual(contract["explicit_exceptions"], [])

    def test_final_eligibility_is_coherent_with_the_bucket(self) -> None:
        for query in self.queries:
            gate_query = {
                key: value
                for key, value in query.items()
                if key not in ("expectation", "query_source", "scenario")
            }
            for claim in self.result.evidence_claims:
                result = GATE.evaluate(gate_query, claim)
                with self.subTest(query=query["query_id"], claim=claim.claim_id):
                    self.assertEqual(
                        result.primary_candidate_eligible,
                        result.final_bucket == GATE.PRIMARY_BUCKET,
                    )
                    self.assertEqual(
                        result.warning_eligible,
                        result.final_bucket == GATE.WARNING_BUCKET,
                    )
                    self.assertEqual(
                        result.audit_only, result.final_bucket == GATE.AUDIT_BUCKET
                    )
                    self.assertEqual(
                        result.rejected_by_native_constraints,
                        result.final_bucket == GATE.REJECTED_BUCKET,
                    )
                    self.assertEqual(
                        result.final_ranking_eligible,
                        result.primary_candidate_eligible,
                    )

    def test_primary_contains_only_candidates_compatible_with_every_gate(self) -> None:
        for query in self.queries:
            gate_query = {
                key: value
                for key, value in query.items()
                if key not in ("expectation", "query_source", "scenario")
            }
            for claim in self.result.evidence_claims:
                result = GATE.evaluate(gate_query, claim)
                if not result.primary_candidate_eligible:
                    continue
                with self.subTest(query=query["query_id"], claim=claim.claim_id):
                    self.assertEqual(result.blocking_gates, ())
                    self.assertTrue(result.biomarker_match_result["compatible"])
                    self.assertTrue(result.direction_match_result["compatible"])
                    self.assertTrue(result.domain_match_result["domain_match"])
                    self.assertTrue(
                        result.disease_match_result["is_exact_relation"]
                        or not result.disease_match_result[
                            "object_carries_disease_scope"
                        ]
                    )
                    self.assertFalse(result.claim_status_result["deprecated"])


# ---------------------------------------------------------------------------
# output shadow
# ---------------------------------------------------------------------------


class TestShadowOutput(RepositoryCase):
    def test_the_output_declares_the_four_buckets(self) -> None:
        query = {
            "query_id": "q",
            "query_domain": THERAPEUTIC,
            "disease": CCA,
            "biomarker": "FGFR2::BICC1 Fusion",
            "interventions": ["infigratinib"],
        }
        rows = [
            OUT.build_result(claim, GATE.evaluate(query, claim))
            for claim in self.result.evidence_claims
        ]
        output = OUT.bucketed_output("q", rows, policy_mode=STRICT_VERIFIED)
        for name in (
            "primary_ranked_results",
            "retained_with_warning",
            "audit_only_results",
            "rejected_by_native_constraints",
        ):
            self.assertIn(name, output)
        self.assertEqual(output["repository_version"], REPOSITORY_VERSION)
        self.assertEqual(
            output["contract_version"], "qualified_claim_retrieval_result/1.2"
        )

    def test_the_canonicalized_aggregate_never_leaves_as_atomic(self) -> None:
        claim = self.claim_for("evidence:1851", "aggregate_intervention_claim")
        query = {
            "query_id": "q",
            "query_domain": THERAPEUTIC,
            "disease": CCA,
            "biomarker": "FGFR2::BICC1 Fusion",
            "interventions": ["infigratinib"],
        }
        row = OUT.build_result(claim, GATE.evaluate(query, claim)).to_dict()
        self.assertEqual(row["subject_representation"], "intervention_aggregate")
        self.assertEqual(row["final_bucket"], GATE.WARNING_BUCKET)
        terminology = row["terminology_provenance"]
        self.assertEqual(terminology["source_literal_term"], VERIFIED_SOURCE_LITERAL)
        self.assertEqual(terminology["canonical_label"], VERIFIED_CANONICAL_LABEL)
        self.assertIn(VERIFIED_SOURCE_LITERAL, terminology["source_literal_members"])
        self.assertIn(VERIFIED_CANONICAL_LABEL, terminology["canonical_members"])

    def test_both_the_canonical_member_and_the_source_literal_reach_it(self) -> None:
        claim = self.claim_for("evidence:1851", "aggregate_intervention_claim")
        for term in (VERIFIED_CANONICAL_LABEL, VERIFIED_SOURCE_LITERAL):
            query = {
                "query_id": "q",
                "query_domain": THERAPEUTIC,
                "disease": CCA,
                "biomarker": "FGFR2::BICC1 Fusion",
                "interventions": [term],
            }
            with self.subTest(term=term):
                result = GATE.evaluate(query, claim)
                self.assertEqual(result.final_bucket, GATE.WARNING_BUCKET)
                self.assertEqual(
                    result.intervention_match_result["match_type"],
                    "aggregate_member_related",
                )

    def test_the_output_refuses_a_score_flag_in_a_non_rankable_bucket(self) -> None:
        claim = self.claim_for("evidence:11240", "atomic_intervention_claim")
        query = {
            "query_id": "q",
            "query_domain": THERAPEUTIC,
            "disease": NSCLC,
            "biomarker": NSCLC_PAIR,
            "interventions": ["erlotinib"],
        }
        row = OUT.build_result(claim, GATE.evaluate(query, claim))
        tampered = replace(
            row,
            final_bucket=GATE.AUDIT_BUCKET,
            score_eligibility=dict(row.score_eligibility)
            | {"structural_score_eligible": True},
        )
        with self.assertRaises(OUT.OutputContractError):
            OUT.check_output_invariants(tampered)


# ---------------------------------------------------------------------------
# regressioni
# ---------------------------------------------------------------------------


class TestRegressions(RepositoryCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.rows = {
            row["graph_evidence_id"]: row
            for row in _load_jsonl(OUTPUT / "regression_case_simulation_v1_3.jsonl")
        }

    def _probe(self, evidence: str, query_id: str) -> list[dict]:
        return [
            item
            for item in self.rows[evidence]["probe_outcomes"]
            if item["query_id"] == query_id
        ]

    def test_every_protected_group_has_a_case(self) -> None:
        expected = {
            "evidence:1846",
            "evidence:1847",
            "evidence:8173",
            "evidence:11219",
            "evidence:11598",
            "evidence:11599",
            "evidence:1867",
            "evidence:1851",
            "evidence:1853",
            "evidence:841",
            "evidence:11240",
            "evidence:347",
        }
        self.assertEqual(set(self.rows), expected)

    def test_no_case_leaks_a_score_outside_a_rankable_bucket(self) -> None:
        for evidence, row in sorted(self.rows.items()):
            with self.subTest(evidence=evidence):
                self.assertEqual(row["positive_score_in_non_rankable_bucket"], 0)
                self.assertEqual(row["structural_score_ever_outside_primary"], 0)

    def test_1846_and_1847_are_primary_on_icca_and_warning_on_cca(self) -> None:
        for evidence, biomarker in (
            ("evidence:1846", "BICC1"),
            ("evidence:1847", "AHCYL1"),
        ):
            number = evidence.split(":")[1]
            exact = self._probe(evidence, f"RP-{number}-ICCA-DIAGNOSTIC")
            child = self._probe(evidence, f"RP-{number}-CCA-DIAGNOSTIC")
            with self.subTest(evidence=evidence, biomarker=biomarker):
                self.assertEqual(len(exact), 1)
                self.assertEqual(exact[0]["bucket"], GATE.PRIMARY_BUCKET)
                self.assertEqual(exact[0]["disease_relation_type"], EXACT_DISEASE)
                self.assertEqual(len(child), 1)
                self.assertEqual(child[0]["bucket"], GATE.WARNING_BUCKET)
                self.assertFalse(child[0]["primary_candidate_eligible"])
                self.assertEqual(
                    child[0]["disease_relation_type"], CLAIM_IS_CHILD_OF_QUERY
                )

    def test_8173_is_sibling_audit_only_on_an_icca_query(self) -> None:
        outcomes = self._probe("evidence:8173", "RP-8173-ICCA-SIBLING")
        self.assertEqual(len(outcomes), 1)
        outcome = outcomes[0]
        self.assertEqual(outcome["disease_relation_type"], DISEASE_SIBLING)
        self.assertEqual(outcome["bucket"], GATE.AUDIT_BUCKET)
        self.assertEqual(set(outcome["by_mode"].values()), {GATE.AUDIT_BUCKET})

    def test_11219_is_primary_only_with_a_compatible_biomarker(self) -> None:
        good = self._probe("evidence:11219", "RP-11219-ALIAS-COMPATIBLE")[0]
        bad = self._probe("evidence:11219", "RP-11219-ALIAS-INCOMPATIBLE")[0]
        self.assertEqual(good["bucket"], GATE.PRIMARY_BUCKET)
        self.assertEqual(good["disease_relation_type"], VERIFIED_DISEASE_ALIAS)
        self.assertEqual(bad["bucket"], GATE.REJECTED_BUCKET)
        self.assertEqual(bad["disease_relation_type"], VERIFIED_DISEASE_ALIAS)

    def test_the_alias_does_not_compensate_an_incompatible_biomarker(self) -> None:
        for evidence in ("evidence:11598", "evidence:11599", "evidence:1867"):
            number = evidence.split(":")[1]
            outcome = self._probe(evidence, f"RP-{number}-ALIAS-INCOMPATIBLE")[0]
            with self.subTest(evidence=evidence):
                self.assertEqual(outcome["bucket"], GATE.REJECTED_BUCKET)
                self.assertFalse(outcome["primary_candidate_eligible"])
                self.assertFalse(outcome["structural_score_eligible"])
                self.assertFalse(outcome["qualified_score_eligible"])

    def test_1851_and_1853_keep_the_new_identifier_and_stay_aggregate(self) -> None:
        for evidence in ("evidence:1851", "evidence:1853"):
            row = self.rows[evidence]
            with self.subTest(evidence=evidence):
                self.assertEqual(
                    row["claim_ids"], [EXPECTED_NEW_CLAIM_IDS[evidence]]
                )
                self.assertEqual(
                    row["claim_types_observed"], ["aggregate_intervention_claim"]
                )
                number = evidence.split(":")[1]
                for suffix in ("CANONICAL-MEMBER", "SOURCE-LITERAL"):
                    outcome = self._probe(evidence, f"RP-{number}-{suffix}")[0]
                    self.assertEqual(outcome["bucket"], GATE.WARNING_BUCKET)
                    self.assertEqual(
                        outcome["intervention_match_type"], "aggregate_member_related"
                    )

    def test_841_never_matches_auy922_or_luminespib(self) -> None:
        for query_id in ("RP-841-AUY922", "RP-841-LUMINESPIB"):
            outcomes = self._probe("evidence:841", query_id)
            with self.subTest(query_id=query_id):
                self.assertTrue(outcomes)
                for outcome in outcomes:
                    self.assertEqual(outcome["bucket"], GATE.REJECTED_BUCKET)
                    self.assertEqual(outcome["intervention_match_type"], "incompatible")

    def test_11240_keeps_regimen_and_atomic_distinct(self) -> None:
        atomic = {
            item["object_id"]: item
            for item in self._probe("evidence:11240", "RP-11240-ATOMIC")
        }
        regimen = {
            item["object_id"]: item
            for item in self._probe("evidence:11240", "RP-11240-REGIMEN")
        }
        self.assertEqual(len(atomic), 2)
        self.assertEqual(len(regimen), 2)
        primary_on_atomic = [
            item for item in atomic.values() if item["primary_candidate_eligible"]
        ]
        primary_on_regimen = [
            item for item in regimen.values() if item["primary_candidate_eligible"]
        ]
        self.assertEqual(len(primary_on_atomic), 1)
        self.assertEqual(len(primary_on_regimen), 1)
        self.assertEqual(
            primary_on_atomic[0]["intervention_match_type"],
            "exact_atomic_intervention",
        )
        self.assertEqual(
            primary_on_regimen[0]["intervention_match_type"], "exact_regimen"
        )
        self.assertNotEqual(
            primary_on_atomic[0]["object_id"], primary_on_regimen[0]["object_id"]
        )

    def test_347_has_no_claim_and_stays_blocked(self) -> None:
        row = self.rows["evidence:347"]
        self.assertFalse(row["has_claims"])
        self.assertTrue(row["is_parent_without_claim"])
        self.assertEqual(row["claim_ids"], [])
        self.assertEqual(row["primary_in_queries"], [])

    def test_no_provenance_container_ever_becomes_primary(self) -> None:
        inventory = _load_json(OUTPUT / "operational_vs_shadow_inventory_v1_3.json")
        self.assertEqual(inventory["parent_probe"]["parents_ever_primary"], 0)
        self.assertGreater(inventory["parent_probe"]["parents_evaluated"], 0)


# ---------------------------------------------------------------------------
# piani
# ---------------------------------------------------------------------------


class TestPlans(RepositoryCase):
    def test_the_qualification_plan_retires_two_links_and_creates_two(self) -> None:
        rows = _load_jsonl(OUTPUT / "qualification_link_regeneration_plan_v1_3.jsonl")
        retired = [
            row
            for row in rows
            if row.get("action") == "retire_claim_link"
            and row.get("claim_id") in set(EXPECTED_OLD_CLAIM_IDS.values())
        ]
        created = [
            row
            for row in rows
            if row.get("action") == "create_claim_link"
            and row.get("claim_id") in set(EXPECTED_NEW_CLAIM_IDS.values())
        ]
        self.assertEqual(len(retired), 2)
        self.assertEqual(len(created), 2)
        for row in retired + created:
            self.assertFalse(row["executed"])
            self.assertFalse(row["atomization_performed"])
            self.assertEqual(row["propagation_policy"], "prototype_only")
            self.assertTrue(row["source_unit_ids"])
            self.assertTrue(row["locators"])

    def test_no_plan_row_is_executed(self) -> None:
        for name in (
            "qualification_link_regeneration_plan_v1_3.jsonl",
            "qualified_view_regeneration_plan_v1_3.jsonl",
        ):
            for row in _load_jsonl(OUTPUT / name):
                with self.subTest(plan=name, plan_id=row.get("plan_id")):
                    self.assertFalse(row["executed"])

    def test_the_view_plan_measures_the_zero_instead_of_assuming_it(self) -> None:
        rows = [
            row
            for row in _load_jsonl(OUTPUT / "qualified_view_regeneration_plan_v1_3.jsonl")
            if row.get("action") == "verify_no_view_references_replaced_claim"
        ]
        self.assertEqual(len(rows), 2)
        views = V3 / "qualification_corpus_v2/qualified_evidence_views.jsonl"
        digest = hashlib.sha256(
            views.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        for row in rows:
            with self.subTest(graph_evidence_id=row["graph_evidence_id"]):
                self.assertEqual(row["old_claim_id_occurrences_in_views"], 0)
                self.assertEqual(row["new_claim_id_occurrences_in_views"], 0)
                self.assertFalse(row["regeneration_required"])
                self.assertFalse(row["operational_view_modified"])
                self.assertEqual(row["checked_artifact_sha256"], digest)


# ---------------------------------------------------------------------------
# compatibilita' e determinismo
# ---------------------------------------------------------------------------


class TestCompatibility(unittest.TestCase):
    def test_the_previous_shadow_repositories_are_untouched(self) -> None:
        lineage = _load_json(OUTPUT / "repository_version_lineage.json")
        preserved = [
            version
            for version in lineage["versions"]
            if version.get("status") == "superseded_but_preserved"
        ]
        self.assertEqual(len(preserved), 3)
        for version in preserved:
            with self.subTest(path=version["path"]):
                self.assertFalse(version["modified_by_this_phase"])
                folder = REPO_ROOT / version["path"]
                observed = {
                    item.name: hashlib.sha256(
                        item.read_text(encoding="utf-8").encode("utf-8")
                    ).hexdigest()
                    for item in sorted(folder.iterdir())
                    if item.is_file()
                }
                self.assertEqual(observed, version["artifact_sha256"])

    def test_the_operational_artifacts_are_untouched(self) -> None:
        inventory = _load_json(OUTPUT / "operational_vs_shadow_inventory_v1_3.json")
        self.assertTrue(inventory["operational_hash_parity"])
        for path, digest in inventory["operational_artifact_sha256_after"].items():
            with self.subTest(path=path):
                observed = hashlib.sha256(
                    (REPO_ROOT / path).read_text(encoding="utf-8").encode("utf-8")
                ).hexdigest()
                self.assertEqual(observed, digest)
        for path in FROZEN_OPERATIONAL_PATHS:
            self.assertIn(path, inventory["operational_artifact_sha256_after"])

    def test_the_operational_query_returns_the_same_bytes(self) -> None:
        inventory = _load_json(OUTPUT / "operational_vs_shadow_inventory_v1_3.json")
        query = inventory["operational_query"]
        self.assertTrue(query["parity"])
        self.assertEqual(query["before_sha256"], query["after_sha256"])

    def test_the_repository_is_not_promoted(self) -> None:
        lineage = _load_json(OUTPUT / "repository_version_lineage.json")
        current = lineage["versions"][-1]
        self.assertEqual(current["repository_schema"], REPOSITORY_VERSION)
        self.assertEqual(current["status"], "shadow_not_promoted")
        self.assertFalse(current["promoted"])

    def test_the_gold_is_never_read(self) -> None:
        """Nessun sorgente della fase nomina il gold, in nessuna forma."""
        sources = [
            REPO_ROOT / "backend/pipeline/evidence/shadow/terminology_v13.py",
            REPO_ROOT / "backend/pipeline/evidence/shadow/disease_gate.py",
            REPO_ROOT / "backend/pipeline/evidence/shadow/integrated_gates.py",
            REPO_ROOT / "backend/pipeline/evidence/shadow/shadow_output_v12.py",
            REPO_ROOT
            / "benchmarks/mtb_evidence/evaluation/scripts/build_integrated_shadow_repository_1_3.py",
        ]
        for source in sources:
            text = source.read_text(encoding="utf-8").lower()
            with self.subTest(source=source.name):
                self.assertNotIn("snapshot_gold", text)
                self.assertNotIn("clinical_gold", text)
                self.assertNotIn("gold_pilot", text)
        inventory = _load_json(OUTPUT / "operational_vs_shadow_inventory_v1_3.json")
        self.assertEqual(inventory["gold_artifacts_read"], 0)

    def test_no_artifact_carries_a_machine_specific_path(self) -> None:
        for item in sorted(OUTPUT.iterdir()):
            if not item.is_file():
                continue
            text = item.read_text(encoding="utf-8")
            with self.subTest(artifact=item.name):
                self.assertNotIn("C:/Users", text)
                self.assertNotIn("C:\\\\Users", text)
                self.assertNotIn(str(REPO_ROOT), text)


class TestDeterminism(unittest.TestCase):
    generated = None

    @classmethod
    def setUpClass(cls) -> None:
        if TestDeterminism.generated is None:
            TestDeterminism.generated = (
                build_data_artifacts(False),
                build_data_artifacts(False),
                build_data_artifacts(True),
            )
        cls.first, cls.second, cls.reversed_ = TestDeterminism.generated

    def test_two_generations_are_byte_identical(self) -> None:
        self.assertEqual(self.first, self.second)

    def test_reversing_the_input_order_changes_nothing(self) -> None:
        self.assertEqual(self.first, self.reversed_)

    def test_the_written_artifacts_match_the_generated_ones(self) -> None:
        for name, text in sorted(self.first.items()):
            with self.subTest(artifact=name):
                path = OUTPUT / name
                self.assertTrue(path.exists(), f"{name} non e' stato scritto")
                self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_reversing_the_query_order_changes_nothing(self) -> None:
        forward = all_queries(False)
        backward = all_queries(True)
        self.assertEqual(
            sorted(json.dumps(q, sort_keys=True) for q in forward),
            sorted(json.dumps(q, sort_keys=True) for q in backward),
        )


class TestPerimeter(unittest.TestCase):
    def test_the_recorded_start_sha_is_forty_characters(self) -> None:
        self.assertEqual(len(START_SHA), 40)

    def test_the_phase_writes_only_inside_its_perimeter(self) -> None:
        if not PHASE_END_SHA:
            raise unittest.SkipTest("estremo di fase non ancora fissato")
        self.assertNotEqual(PHASE_END_SHA, "HEAD")
        self.assertEqual(len(PHASE_END_SHA), 40)
        scope = PhaseScope(
            REPO_ROOT.parent, START_SHA, PHASE_END_SHA, ALLOWED_WRITE_PREFIXES
        )
        changed = scope.changed_paths()
        self.assertEqual(scope.violations(changed), [])
        for path in FROZEN_OPERATIONAL_PATHS:
            with self.subTest(path=path):
                self.assertNotIn(path, changed)
        for folder in FROZEN_SHADOW_DIRS:
            for path in changed:
                with self.subTest(folder=folder, path=path):
                    self.assertFalse(path.startswith(f"{folder}/"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
