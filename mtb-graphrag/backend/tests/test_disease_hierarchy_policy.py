"""Protegge la direzionalita' del match disease e il divieto di generalizzare.

I test difendono quattro cose che sono facili da perdere. Che un sottotipo e il suo
genitore non diventino la stessa cosa in nessuna delle due direzioni. Che un sibling
non diventi mai exact. Che nessun punteggio, per quanto alto, riapra il primario a
una relazione che non e' identita'. E che la fase non abbia toccato nulla di cio'
che dichiara di non toccare.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy import (
    AUDIT,
    AUDIT_ALL,
    CLAIM_DISEASE_SCOPE_BROADER_THAN_QUERY,
    CLAIM_DISEASE_SCOPE_MISSING,
    CLAIM_DISEASE_SCOPE_NARROWER_THAN_QUERY,
    CLAIM_IS_CHILD_OF_QUERY,
    CLAIM_IS_PARENT_OF_QUERY,
    CROSS_DISEASE,
    CROSS_DISEASE_MISMATCH,
    DISEASE_GATE_PRECEDES_SCORING,
    DISEASE_SIBLING,
    DISEASE_SIBLING_NOT_APPLICABLE,
    EVIDENCE_APPLIES_ONLY_TO_QUERY_SUBTYPE,
    EXACT_DISEASE,
    EXACT_RELATIONS,
    GENERIC_CANCER_SCOPE,
    GENERIC_DISEASE_SCOPE_NOT_CASE_SPECIFIC,
    MISSING_CLAIM_DISEASE,
    MISSING_QUERY_DISEASE,
    NORMALIZED_EXACT_DISEASE,
    ONTOLOGY_AWARE_WARNING,
    POLICY_MODES,
    PRIMARY,
    REJECTED,
    RELATION_TYPES,
    RESULT_NOT_SEPARABLE_FOR_QUERY_SUBTYPE,
    STRICT_VERIFIED,
    UNRESOLVED_DISEASE_RELATION,
    VERIFIED_DISEASE_ALIAS,
    WARNING,
    match_disease_scope,
    resolve_relation,
)
from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy_simulation import (
    FROZEN_QUERIES,
    REGRESSION_EVIDENCE,
    UNTYPED_QUERY,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_disease_hierarchy_policy import (
    DEFAULT_OUTPUT,
    EXPECTED_CLAIM_COUNT,
    START_SHA,
    build,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
SHADOW_V12 = V3 / "diagnostic_disease_scope_narrowing_shadow"
TERMINOLOGY = V3 / "terminology_mapping_closure"
OUT = DEFAULT_OUTPUT

EVALUATION = REPO_ROOT / "benchmarks/mtb_evidence/evaluation"
PHASE_MODULES = (
    EVALUATION / "disease_hierarchy_policy.py",
    EVALUATION / "disease_hierarchy_policy_simulation.py",
    EVALUATION / "disease_hierarchy_policy_reports.py",
    EVALUATION / "scripts/build_disease_hierarchy_policy.py",
)

# La fase termina sull'ultimo commit di contenuto. L'estremo resta fisso anche
# quando fasi successive aggiungono nuovi commit: il perimetro di una fase e' una
# proprieta' storica e chiusa.
PHASE_END_SHA = "acc5c3016333a28ea6e107defd4ab05dca90b0d9"

# PhaseScope restituisce percorsi relativi al pacchetto: il prefisso del repo viene
# gia' rimosso una volta dal helper condiviso.
ALLOWED_WRITE_PREFIXES = (
    "benchmarks/mtb_evidence/v3/disease_hierarchy_policy/",
    "benchmarks/mtb_evidence/evaluation/disease_hierarchy_policy.py",
    "benchmarks/mtb_evidence/evaluation/disease_hierarchy_policy_simulation.py",
    "benchmarks/mtb_evidence/evaluation/disease_hierarchy_policy_reports.py",
    "benchmarks/mtb_evidence/evaluation/scripts/build_disease_hierarchy_policy.py",
    "backend/tests/test_disease_hierarchy_policy.py",
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
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl",
)

NSCLC_VERIFIED_ALIASES = (
    "NSCLC",
    "Non-small Cell Lung Cancer",
    "Lung Non-small Cell Carcinoma",
    "Non-small Cell Lung Carcinoma",
)

ICCA_DIAGNOSTIC_CLAIMS = {
    "evidence:1846": "CLM-8941c177da91f66ff93a",
    "evidence:1847": "CLM-a7e1c40b794d2c4d4ca8",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl_text(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


class PolicyCase(unittest.TestCase):
    """Genera una volta sola e condivide il risultato con le sottoclassi."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = build()
        cls.manifest = json.loads(cls.artifacts["policy_manifest.json"])
        cls.scope = json.loads(cls.artifacts["review_scope.json"])
        cls.definitions = json.loads(cls.artifacts["disease_relation_definitions.json"])
        cls.modes = json.loads(cls.artifacts["disease_policy_modes.json"])
        cls.gate = json.loads(cls.artifacts["scoring_gate_invariants.json"])
        cls.codes = json.loads(cls.artifacts["disease_reason_warning_codes.json"])
        cls.migration = json.loads(cls.artifacts["migration_impact.json"])
        cls.pairs = load_jsonl_text(
            cls.artifacts["claim_disease_relation_simulation.jsonl"]
        )
        cls.queries = load_jsonl_text(cls.artifacts["query_policy_simulation.jsonl"])
        cls.regressions = load_jsonl_text(
            cls.artifacts["regression_case_simulation.jsonl"]
        )
        cls.by_case = {row["case_id"]: row for row in cls.regressions}

    def pair(self, query_id: str, graph_evidence_id: str) -> dict:
        for row in self.pairs:
            if (
                row["query_id"] == query_id
                and row["graph_evidence_id"] == graph_evidence_id
            ):
                return row
        raise AssertionError(f"coppia assente: {query_id} / {graph_evidence_id}")


class TestIdentityRelations(PolicyCase):
    def test_exact_disease_is_primary(self) -> None:
        result = match_disease_scope(
            "Intrahepatic Cholangiocarcinoma", "Intrahepatic Cholangiocarcinoma"
        )
        self.assertEqual(result.relation_type, EXACT_DISEASE)
        self.assertTrue(result.primary_candidate_eligible)
        self.assertEqual(result.score_eligibility["bucket"], PRIMARY)

    def test_normalized_exact_disease_is_primary(self) -> None:
        """Un qualificatore di stadio non cambia l'entita'."""
        result = match_disease_scope("Metastatic Lung Adenocarcinoma", "Lung Adenocarcinoma")
        self.assertEqual(result.relation_type, NORMALIZED_EXACT_DISEASE)
        self.assertTrue(result.primary_candidate_eligible)
        self.assertEqual(
            result.normalized_query_disease, result.normalized_claim_disease
        )

    def test_the_four_nsclc_literals_stay_verified_aliases_and_primary(self) -> None:
        for left in NSCLC_VERIFIED_ALIASES:
            for right in NSCLC_VERIFIED_ALIASES:
                with self.subTest(left=left, right=right):
                    result = match_disease_scope(left, right)
                    self.assertIn(result.relation_type, EXACT_RELATIONS)
                    self.assertTrue(result.primary_candidate_eligible)
                    self.assertTrue(result.relation_verified)

    def test_lung_adenocarcinoma_is_not_an_nsclc_alias(self) -> None:
        """E' un sottotipo. Trattarlo da sinonimo cancellerebbe la distinzione."""
        for alias in NSCLC_VERIFIED_ALIASES:
            with self.subTest(alias=alias):
                self.assertNotEqual(
                    resolve_relation(alias, "Lung Adenocarcinoma").relation_type,
                    VERIFIED_DISEASE_ALIAS,
                )
        groups = json.loads(self.artifacts["verified_alias_registry_snapshot.json"])
        members = {
            member for group in groups["groups"] for member in group["members"]
        }
        self.assertIn("nsclc", members)
        nsclc_group = next(
            group for group in groups["groups"] if "nsclc" in group["members"]
        )
        self.assertNotIn("lung adenocarcinoma", nsclc_group["members"])
        self.assertEqual(groups["aliases_created_in_this_phase"], 0)


class TestDirectionality(PolicyCase):
    def test_claim_child_and_claim_parent_are_not_the_same_case(self) -> None:
        child = match_disease_scope("Cholangiocarcinoma", "Intrahepatic Cholangiocarcinoma")
        parent = match_disease_scope("Intrahepatic Cholangiocarcinoma", "Cholangiocarcinoma")
        self.assertEqual(child.relation_type, CLAIM_IS_CHILD_OF_QUERY)
        self.assertEqual(parent.relation_type, CLAIM_IS_PARENT_OF_QUERY)
        self.assertNotEqual(child.relation_direction, parent.relation_direction)
        self.assertIn(CLAIM_DISEASE_SCOPE_NARROWER_THAN_QUERY, child.warning_codes)
        self.assertIn(CLAIM_DISEASE_SCOPE_BROADER_THAN_QUERY, parent.warning_codes)
        self.assertEqual(
            child.explanation_codes, (EVIDENCE_APPLIES_ONLY_TO_QUERY_SUBTYPE,)
        )
        self.assertEqual(
            parent.explanation_codes, (RESULT_NOT_SEPARABLE_FOR_QUERY_SUBTYPE,)
        )

    def test_nsclc_and_lung_adenocarcinoma_are_directional_in_both_senses(self) -> None:
        child = match_disease_scope("NSCLC", "Lung Adenocarcinoma")
        parent = match_disease_scope("Lung Adenocarcinoma", "NSCLC")
        self.assertEqual(child.relation_type, CLAIM_IS_CHILD_OF_QUERY)
        self.assertEqual(parent.relation_type, CLAIM_IS_PARENT_OF_QUERY)
        for result in (child, parent):
            with self.subTest(relation=result.relation_type):
                self.assertFalse(result.primary_candidate_eligible)
                self.assertTrue(result.warning_eligible)
                self.assertNotIn(result.relation_type, EXACT_RELATIONS)

    def test_icca_is_a_child_of_cholangiocarcinoma_and_never_an_alias(self) -> None:
        relation = resolve_relation("Cholangiocarcinoma", "Intrahepatic Cholangiocarcinoma")
        self.assertEqual(relation.relation_type, CLAIM_IS_CHILD_OF_QUERY)
        self.assertNotEqual(relation.relation_type, VERIFIED_DISEASE_ALIAS)
        hierarchy = load_jsonl_text(self.artifacts["explicit_hierarchy_relations.jsonl"])
        row = next(
            item
            for item in hierarchy
            if item.get("child_term") == "intrahepatic cholangiocarcinoma"
        )
        self.assertEqual(row["parent_term"], "cholangiocarcinoma")
        self.assertFalse(row["is_alias"])

    def test_an_icca_claim_is_not_generalized_to_every_cholangiocarcinoma(self) -> None:
        for graph_evidence_id in ICCA_DIAGNOSTIC_CLAIMS:
            with self.subTest(evidence=graph_evidence_id):
                row = self.pair("DQ-04-FGFR2-CCA", graph_evidence_id)
                self.assertEqual(row["relation_type"], CLAIM_IS_CHILD_OF_QUERY)
                for mode in POLICY_MODES:
                    self.assertFalse(row["by_mode"][mode]["primary_candidate_eligible"])
                    self.assertEqual(row["by_mode"][mode]["bucket"], WARNING)

    def test_the_direction_is_computed_not_asserted(self) -> None:
        self.assertTrue(self.definitions["relation_direction_is_computed_not_asserted"])
        self.assertTrue(self.definitions["relation_type_is_mode_invariant"])


class TestSiblingAndGeneric(PolicyCase):
    def test_a_sibling_is_never_exact(self) -> None:
        result = match_disease_scope(
            "Intrahepatic Cholangiocarcinoma", "Cholangiolocellular Carcinoma"
        )
        self.assertEqual(result.relation_type, DISEASE_SIBLING)
        self.assertNotIn(result.relation_type, EXACT_RELATIONS)
        self.assertIn(DISEASE_SIBLING_NOT_APPLICABLE, result.reason_codes)
        for mode in POLICY_MODES:
            with self.subTest(mode=mode):
                sibling = match_disease_scope(
                    "Intrahepatic Cholangiocarcinoma",
                    "Cholangiolocellular Carcinoma",
                    mode=mode,
                )
                self.assertFalse(sibling.primary_candidate_eligible)
                self.assertTrue(sibling.audit_only)
                self.assertEqual(sibling.score_eligibility["bucket"], AUDIT)

    def test_evidence_8173_stays_audit_only_for_an_icca_query(self) -> None:
        row = self.pair("DQ-03-FGFR2-ICCA", "evidence:8173")
        self.assertEqual(row["claim_disease_scope"], "Cholangiolocellular Carcinoma")
        self.assertEqual(row["relation_type"], DISEASE_SIBLING)
        for mode in POLICY_MODES:
            with self.subTest(mode=mode):
                item = row["by_mode"][mode]
                self.assertTrue(item["audit_only"])
                self.assertFalse(item["primary_candidate_eligible"])
                self.assertFalse(item["score_eligibility"]["qualified_score_eligible"])
                self.assertTrue(item["score_eligibility"]["positive_score_forbidden"])

    def test_a_generic_scope_is_not_an_alias_of_the_query_disease(self) -> None:
        result = match_disease_scope("NSCLC", "Cancer")
        self.assertEqual(result.relation_type, GENERIC_CANCER_SCOPE)
        self.assertNotIn(result.relation_type, EXACT_RELATIONS)
        self.assertFalse(result.relation_verified)
        self.assertFalse(result.primary_candidate_eligible)
        self.assertIn(GENERIC_DISEASE_SCOPE_NOT_CASE_SPECIFIC, result.reason_codes)

    def test_generic_scope_moves_between_audit_and_warning_by_mode_only(self) -> None:
        strict = match_disease_scope("NSCLC", "Cancer", mode=STRICT_VERIFIED)
        aware = match_disease_scope("NSCLC", "Cancer", mode=ONTOLOGY_AWARE_WARNING)
        self.assertTrue(strict.audit_only)
        self.assertTrue(aware.warning_eligible)
        self.assertEqual(strict.relation_type, aware.relation_type)
        self.assertFalse(strict.primary_candidate_eligible)
        self.assertFalse(aware.primary_candidate_eligible)


class TestAbsenceRelations(PolicyCase):
    def test_cross_disease_is_rejected_by_native_constraints(self) -> None:
        result = match_disease_scope("Breast Cancer", "Lung Non-small Cell Carcinoma")
        self.assertEqual(result.relation_type, CROSS_DISEASE)
        self.assertTrue(result.rejected_by_native_constraints)
        self.assertEqual(result.score_eligibility["bucket"], REJECTED)
        self.assertTrue(result.score_eligibility["positive_score_forbidden"])
        self.assertIn(CROSS_DISEASE_MISMATCH, result.reason_codes)

    def test_missing_disease_is_distinct_from_unresolved_and_from_cross(self) -> None:
        missing_query = resolve_relation("", "NSCLC")
        missing_claim = resolve_relation("NSCLC", "")
        unresolved = resolve_relation("Neuroblastoma", "Pilocytic Astrocytoma")
        cross = resolve_relation("Breast Cancer", "Lung Non-small Cell Carcinoma")
        self.assertEqual(missing_query.relation_type, MISSING_QUERY_DISEASE)
        self.assertEqual(missing_claim.relation_type, MISSING_CLAIM_DISEASE)
        self.assertEqual(unresolved.relation_type, UNRESOLVED_DISEASE_RELATION)
        self.assertEqual(cross.relation_type, CROSS_DISEASE)
        self.assertEqual(
            len(
                {
                    missing_query.relation_type,
                    missing_claim.relation_type,
                    unresolved.relation_type,
                    cross.relation_type,
                }
            ),
            4,
        )
        self.assertEqual(
            self.codes["by_relation"][MISSING_QUERY_DISEASE]["reason_code"],
            "QUERY_DISEASE_MISSING",
        )
        self.assertEqual(
            self.codes["by_relation"][MISSING_CLAIM_DISEASE]["reason_code"],
            CLAIM_DISEASE_SCOPE_MISSING,
        )

    def test_missing_and_unresolved_never_give_positive_support(self) -> None:
        for relation, pair in (
            (MISSING_QUERY_DISEASE, ("", "NSCLC")),
            (MISSING_CLAIM_DISEASE, ("NSCLC", "")),
            (UNRESOLVED_DISEASE_RELATION, ("Neuroblastoma", "Pilocytic Astrocytoma")),
        ):
            for mode in POLICY_MODES:
                with self.subTest(relation=relation, mode=mode):
                    result = match_disease_scope(*pair, mode=mode)
                    self.assertEqual(result.relation_type, relation)
                    self.assertFalse(result.primary_candidate_eligible)
                    self.assertTrue(result.audit_only)
                    self.assertTrue(
                        result.score_eligibility["positive_score_forbidden"]
                    )


class TestScoringGate(PolicyCase):
    def test_a_high_score_does_not_bypass_the_disease_gate(self) -> None:
        probe = self.by_case["PROBE-SCORE-GATE"]
        self.assertEqual(probe["relation_type"], CLAIM_IS_CHILD_OF_QUERY)
        self.assertEqual(probe["injected_score"], 1.0)
        self.assertIn("biomarker_exact_match", probe["injected_signals"])
        self.assertIn("intervention_exact_match", probe["injected_signals"])
        self.assertFalse(probe["primary_after_injection"])
        for mode in POLICY_MODES:
            with self.subTest(mode=mode):
                item = probe["by_mode"][mode]
                self.assertFalse(item["primary_candidate_eligible"])
                self.assertEqual(item["bucket"], WARNING)
                self.assertFalse(item["score_eligibility"]["structural_score_eligible"])

    def test_the_structural_score_is_reserved_to_exact_relations(self) -> None:
        self.assertTrue(self.gate["structural_score_reserved_to_exact_relations"])
        for relation in RELATION_TYPES:
            for mode in POLICY_MODES:
                with self.subTest(relation=relation, mode=mode):
                    eligible = self.gate["per_relation_per_mode"][relation][mode][
                        "structural_score_eligible"
                    ]
                    self.assertEqual(eligible, relation in EXACT_RELATIONS)

    def test_every_non_exact_relation_carries_the_gate_reason_code(self) -> None:
        for relation in RELATION_TYPES:
            if relation in EXACT_RELATIONS:
                continue
            with self.subTest(relation=relation):
                result = match_disease_scope(
                    *_pair_for(relation)
                )
                self.assertIn(DISEASE_GATE_PRECEDES_SCORING, result.reason_codes)

    def test_the_gate_precedes_scoring_in_the_contract(self) -> None:
        self.assertTrue(self.gate["gate_precedes_scoring"])
        contract = json.loads(self.artifacts["disease_match_contract.json"])
        self.assertTrue(contract["gate_precedes_scoring"])
        self.assertEqual(
            sorted(contract["primary_relations"]), sorted(EXACT_RELATIONS)
        )


def _pair_for(relation: str) -> tuple[str, str]:
    return {
        CLAIM_IS_CHILD_OF_QUERY: ("Cholangiocarcinoma", "Intrahepatic Cholangiocarcinoma"),
        CLAIM_IS_PARENT_OF_QUERY: ("Intrahepatic Cholangiocarcinoma", "Cholangiocarcinoma"),
        DISEASE_SIBLING: (
            "Intrahepatic Cholangiocarcinoma",
            "Cholangiolocellular Carcinoma",
        ),
        GENERIC_CANCER_SCOPE: ("NSCLC", "Cancer"),
        CROSS_DISEASE: ("Breast Cancer", "Lung Non-small Cell Carcinoma"),
        UNRESOLVED_DISEASE_RELATION: ("Neuroblastoma", "Pilocytic Astrocytoma"),
        MISSING_QUERY_DISEASE: ("", "NSCLC"),
        MISSING_CLAIM_DISEASE: ("NSCLC", ""),
    }[relation]


class TestRegressions(PolicyCase):
    def test_evidence_1846_and_1847_behave_the_same_way(self) -> None:
        for graph_evidence_id in ("evidence:1846", "evidence:1847"):
            suffix = graph_evidence_id.split(":")[1]
            with self.subTest(evidence=graph_evidence_id):
                exact = self.by_case[f"REG-{suffix}-DQ-03-FGFR2-ICCA"]
                self.assertEqual(exact["relation_type"], EXACT_DISEASE)
                self.assertTrue(exact["is_exact_relation"])
                self.assertTrue(
                    exact["by_mode"][STRICT_VERIFIED]["primary_candidate_eligible"]
                )
                child = self.by_case[f"REG-{suffix}-DQ-04-FGFR2-CCA"]
                self.assertEqual(child["relation_type"], CLAIM_IS_CHILD_OF_QUERY)
                self.assertFalse(child["is_exact_relation"])
                self.assertTrue(child["by_mode"][STRICT_VERIFIED]["warning_eligible"])

    def test_evidence_11219_is_primary_only_when_the_biomarker_is_compatible(self) -> None:
        compatible = self.by_case["REG-11219-DQ-01-EGFR-L858R-NSCLC"]
        incompatible = self.by_case["REG-11219-DQ-05-ALK-G1202R-NSCLC"]
        for row in (compatible, incompatible):
            with self.subTest(case=row["case_id"]):
                self.assertEqual(row["relation_type"], VERIFIED_DISEASE_ALIAS)
        self.assertTrue(compatible["biomarker_compatibility_declared"])
        self.assertTrue(
            compatible["by_mode"][STRICT_VERIFIED]["primary_candidate_eligible"]
        )
        self.assertFalse(incompatible["biomarker_compatibility_declared"])
        self.assertFalse(
            incompatible["by_mode"][STRICT_VERIFIED]["primary_candidate_eligible"]
        )

    def test_a_compatible_disease_alias_never_rescues_a_biomarker_mismatch(self) -> None:
        for case_id in (
            "REG-11598-DQ-01-EGFR-L858R-NSCLC",
            "REG-11599-DQ-01-EGFR-L858R-NSCLC",
            "REG-1867-DQ-01-EGFR-L858R-NSCLC",
        ):
            with self.subTest(case=case_id):
                row = self.by_case[case_id]
                self.assertEqual(row["relation_type"], VERIFIED_DISEASE_ALIAS)
                self.assertFalse(row["biomarker_compatibility_declared"])
                self.assertFalse(row["disease_relation_compensated_by_biomarker"])
                for mode in POLICY_MODES:
                    item = row["by_mode"][mode]
                    self.assertEqual(item["bucket"], REJECTED)
                    self.assertFalse(item["primary_candidate_eligible"])
                    self.assertFalse(
                        item["score_eligibility"]["qualified_score_eligible"]
                    )
                    self.assertTrue(
                        item["score_eligibility"]["positive_score_forbidden"]
                    )

    def test_every_named_regression_evidence_is_simulated(self) -> None:
        simulated = {row["graph_evidence_id"] for row in self.regressions}
        for graph_evidence_id in REGRESSION_EVIDENCE:
            with self.subTest(evidence=graph_evidence_id):
                self.assertIn(graph_evidence_id, simulated)


class TestModesAndBuckets(PolicyCase):
    def test_the_primary_bucket_is_identical_across_the_three_modes(self) -> None:
        self.assertTrue(self.scope["primary_bucket_is_mode_invariant"])
        for mode_entry in self.modes["modes"]:
            with self.subTest(mode=mode_entry["mode"]):
                primary = {
                    relation
                    for relation, row in mode_entry["per_relation"].items()
                    if row["primary_candidate_eligible"]
                }
                self.assertEqual(primary, set(EXACT_RELATIONS))

    def test_parent_and_child_never_reach_the_primary_bucket(self) -> None:
        self.assertTrue(self.scope["parent_and_child_never_primary"])
        for relation in (CLAIM_IS_CHILD_OF_QUERY, CLAIM_IS_PARENT_OF_QUERY):
            for mode in POLICY_MODES:
                with self.subTest(relation=relation, mode=mode):
                    result = match_disease_scope(*_pair_for(relation), mode=mode)
                    self.assertFalse(result.primary_candidate_eligible)
                    self.assertEqual(result.score_eligibility["bucket"], WARNING)

    def test_no_broad_mode_is_defined(self) -> None:
        self.assertEqual(sorted(POLICY_MODES), sorted(m["mode"] for m in self.modes["modes"]))
        self.assertNotIn("broad", " ".join(POLICY_MODES))
        self.assertEqual(self.modes["default_mode_proposed_for_promotion"], STRICT_VERIFIED)

    def test_audit_all_exposes_without_promoting(self) -> None:
        entry = next(item for item in self.modes["modes"] if item["mode"] == AUDIT_ALL)
        for relation in RELATION_TYPES:
            with self.subTest(relation=relation):
                row = entry["per_relation"][relation]
                self.assertEqual(
                    row["primary_candidate_eligible"], relation in EXACT_RELATIONS
                )


class TestClaimDomain(PolicyCase):
    def test_the_relation_does_not_depend_on_claim_type_or_domain(self) -> None:
        by_scope: dict[tuple[str, str], set[str]] = {}
        for row in self.pairs:
            key = (row["query_id"], row["claim_disease_scope"])
            by_scope.setdefault(key, set()).add(row["relation_type"])
        for key, relations in sorted(by_scope.items()):
            with self.subTest(key=key):
                self.assertEqual(len(relations), 1)

    def test_an_untyped_query_keeps_the_domains_in_separate_sections(self) -> None:
        untyped = [
            query for query in FROZEN_QUERIES if query.query_domain == UNTYPED_QUERY
        ]
        self.assertEqual(len(untyped), 1)
        rows = [
            row
            for row in self.queries
            if row["query_id"] == untyped[0].query_id
        ]
        self.assertEqual(len(rows), len(POLICY_MODES))
        for row in rows:
            with self.subTest(mode=row["policy_mode"]):
                self.assertTrue(row["sectioned_output"])
                self.assertFalse(row["cross_domain_ranking_allowed"])
                self.assertIn("diagnostic_results", row["sections_presented"])
                self.assertIn("therapeutic_results", row["sections_presented"])

    def test_no_query_allows_cross_domain_ranking(self) -> None:
        for row in self.queries:
            with self.subTest(query=row["query_id"], mode=row["policy_mode"]):
                self.assertFalse(row["cross_domain_ranking_allowed"])


class TestUpstreamUnchanged(PolicyCase):
    def test_the_shadow_repository_1_2_is_byte_identical(self) -> None:
        manifest = load_json(SHADOW_V12 / "repository_v1_2_manifest.json")
        for name, digest in manifest["artifact_sha256"].items():
            with self.subTest(artifact=name):
                self.assertEqual(sha256_text(SHADOW_V12 / name), digest)
        recorded = self.manifest["integrity"]["shadow_repository_manifest_sha256"]
        self.assertEqual(
            sha256_text(SHADOW_V12 / "repository_v1_2_manifest.json"), recorded["1.2"]
        )
        self.assertFalse(self.manifest["integrity"]["shadow_repositories_modified"])

    def test_the_terminology_closure_is_unchanged(self) -> None:
        self.assertEqual(
            sha256_text(TERMINOLOGY / "terminology_review_manifest.json"),
            self.manifest["integrity"]["terminology_closure_manifest_sha256"],
        )
        closure = load_json(TERMINOLOGY / "terminology_review_manifest.json")
        self.assertTrue(closure["readiness"]["terminology_queue_complete"])
        self.assertFalse(closure["scope"]["disease_hierarchy_activated"])

    def test_operational_artifacts_keep_their_hashes(self) -> None:
        integrity = self.manifest["integrity"]
        self.assertTrue(integrity["operational_hash_parity"])
        self.assertEqual(
            integrity["operational_artifact_sha256_before"],
            integrity["operational_artifact_sha256_after"],
        )
        for path, expected in integrity["operational_artifact_sha256_before"].items():
            with self.subTest(path=path):
                self.assertEqual(sha256_text(REPO_ROOT / path), expected)
        self.assertFalse(integrity["operational_disease_matcher_modified"])
        self.assertFalse(integrity["operational_corpus_modified"])

    def test_frozen_scientific_artifacts_keep_their_hashes(self) -> None:
        for path, expected in self.manifest["integrity"][
            "frozen_scientific_artifact_sha256"
        ].items():
            with self.subTest(path=path):
                self.assertEqual(sha256_text(REPO_ROOT / path), expected)

    def test_the_gate_is_not_implemented_in_the_operational_retriever(self) -> None:
        self.assertFalse(self.scope["gate_implemented_in_operational_retriever"])
        self.assertFalse(
            self.scope["disease_hierarchy_activated_in_operational_retriever"]
        )
        self.assertFalse(self.migration["migration_applied"])
        self.assertFalse(self.migration["operational_matcher_modified"])
        self.assertTrue(self.migration["changes_required"] > 0)
        self.assertTrue(self.migration["already_compatible"] > 0)


class TestIsolation(PolicyCase):
    def test_the_evaluation_reference_is_never_read(self) -> None:
        forbidden = (
            "clinical_gold",
            "snapshot_gold",
            "gold_pilot",
            "mtb_evidence_gold",
            "statement_qualification_gold",
            "evaluation_gold_snapshot",
            "recall@",
            "precision@",
            "mrr",
        )
        for path in PHASE_MODULES:
            source = path.read_text(encoding="utf-8").lower()
            for fragment in forbidden:
                with self.subTest(module=path.name, fragment=fragment):
                    self.assertNotIn(fragment, source)
        self.assertFalse(self.scope["gold_used"])
        self.assertFalse(self.scope["retrieval_metrics_used"])
        self.assertFalse(self.manifest["integrity"]["evaluation_reference_used"])
        self.assertFalse(
            self.manifest["integrity"]["evaluation_reference_deserialized"]
        )

    def test_no_network_or_model_imports(self) -> None:
        for path in PHASE_MODULES:
            imports = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            for forbidden in (
                "requests",
                "httpx",
                "aiohttp",
                "neo4j",
                "openai",
                "anthropic",
                "urllib",
                "socket",
            ):
                with self.subTest(module=path.name, forbidden=forbidden):
                    self.assertFalse(any(forbidden in line for line in imports))

    def test_no_unregistered_inference_is_declared(self) -> None:
        for flag in (
            "embedding_used",
            "fuzzy_matching_used",
            "llm_used",
            "substring_matching_used",
            "unregistered_knowledge_used",
        ):
            with self.subTest(flag=flag):
                self.assertFalse(self.scope[flag])
        self.assertEqual(self.scope["aliases_created"], 0)
        self.assertEqual(self.scope["relations_created"], 0)


class TestDeterminism(PolicyCase):
    def test_two_generations_and_reversed_inputs_are_byte_identical(self) -> None:
        self.assertEqual(build(), self.artifacts)
        self.assertEqual(build(reverse=True), self.artifacts)

    def test_committed_files_match_a_fresh_generation(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            with self.subTest(artifact=name):
                self.assertEqual((OUT / name).read_text(encoding="utf-8"), text)

    def test_manifest_hashes_match_and_no_machine_path_leaks(self) -> None:
        for name, expected in self.manifest["artifact_sha256"].items():
            with self.subTest(artifact=name):
                text = self.artifacts[name]
                self.assertEqual(
                    hashlib.sha256(text.encode("utf-8")).hexdigest(), expected
                )
        produced = "".join(self.artifacts.values()).lower()
        for fragment in ("c:\\", "/users/", "/home/", "appdata", "ispezionedataset"):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, produced)

    def test_the_simulation_covers_the_declared_perimeter(self) -> None:
        simulation = self.manifest["simulation"]
        self.assertEqual(simulation["claims"], EXPECTED_CLAIM_COUNT)
        self.assertEqual(simulation["queries"], len(FROZEN_QUERIES))
        self.assertEqual(simulation["modes"], len(POLICY_MODES))
        self.assertEqual(
            simulation["combinations"], simulation["pairs"] * len(POLICY_MODES)
        )
        self.assertEqual(len(self.pairs), simulation["pairs"])
        self.assertTrue(self.scope["perimeter_matches_expectation"])

    def test_every_relation_type_is_reachable(self) -> None:
        coverage = self.scope["relation_coverage"]
        reachable = set(coverage["relation_types_observed"]) | set(
            coverage["covered_by_contract_probe"]
        )
        self.assertEqual(reachable, set(RELATION_TYPES))

    def test_readiness_keeps_promotion_closed(self) -> None:
        flags = self.manifest["readiness"]
        for opened in (
            "directional_relation_contract_frozen",
            "explicit_hierarchy_relations_frozen",
            "generic_scope_policy_frozen",
            "ontology_warning_policy_frozen",
            "current_retriever_compatibility_audited",
            "shadow_disease_gate_update_ready",
            "sibling_policy_frozen",
            "strict_policy_frozen",
            "terminology_shadow_update_ready",
            "verified_alias_policy_frozen",
        ):
            with self.subTest(flag=opened):
                self.assertTrue(flags[opened])
        for closed in (
            "corpus_promotion_ready",
            "operational_retriever_migration_ready",
            "full_exploratory_rerun_ready",
        ):
            with self.subTest(flag=closed):
                self.assertFalse(flags[closed])


class TestPerimeter(PolicyCase):
    def test_the_recorded_start_sha_is_the_real_branch_point(self) -> None:
        self.assertEqual(self.scope["start_sha"], START_SHA)
        self.assertEqual(len(START_SHA), 40)

    # La misura del perimetro — `git diff START..END` — sta in
    # `backend/tests_history/test_phase_perimeters.py`: richiede la storia del
    # repository, che un archivio estratto non ha.

if __name__ == "__main__":  # pragma: no cover
    unittest.main()
