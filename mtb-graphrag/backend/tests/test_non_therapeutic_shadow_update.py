"""Protegge gli invarianti della migrazione shadow 1.1.

Tutto offline: nessuna rete, nessun Neo4j, nessun LLM, gold mai letto, nessun
recupero di full text. Il repository 1.0 deve restare byte per byte quello che
era, e questo e' verificato invece che promesso.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from backend.pipeline.evidence.shadow import domain_gates as GATE
from backend.pipeline.evidence.shadow import shadow_output_v11 as OUT
from backend.pipeline.evidence.shadow.deprecation import (
    DEPRECATION_STATES,
    DEPRECATION_STATES_V11,
    PROMOTION_BLOCKING_STATES,
)
from backend.pipeline.evidence.shadow.domain import (
    ALL_CLAIM_TYPES,
    CLAIM_DOMAINS,
    DOMAIN_DIAGNOSTIC,
    DOMAIN_PROGNOSTIC,
    DOMAIN_THERAPEUTIC,
    DomainError,
    domain_of,
    receives_therapy_score,
)
from backend.pipeline.evidence.shadow.identity import non_therapeutic_claim_id
from backend.pipeline.evidence.shadow.non_therapeutic_claims import (
    DiagnosticClaim,
    NonTherapeuticClaimError,
    PrognosticClaim,
)
from backend.pipeline.evidence.shadow.schema import (
    MIGRATION_STATUS,
    MODEL_SCHEMA_VERSION,
    MODEL_SCHEMA_VERSION_V11,
    OUTPUT_CONTRACT_VERSION_V11,
    SHADOW_REPOSITORY_VERSION,
    SHADOW_REPOSITORY_VERSION_V11,
    STRUCTURAL_GATE_VERSION_V11,
)
from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.scripts.build_non_therapeutic_shadow_update import (
    build,
    run_migration,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
OUT_DIR = V3 / "non_therapeutic_shadow_update"
SHADOW_V10 = V3 / "typed_claim_shadow_migration"

START_SHA = "a692ec06e6f48cde0b82f758013b247bc83f2c64"
# La fase si chiude sull'ultimo commit di contenuto. L'estremo e' fisso e non
# `HEAD`, che cresce a ogni commit successivo e riporterebbe il controllo a
# essere aperto.
PHASE_END_SHA = "9104af2f8b6f3583fa14afc703b094d30a85ec4c"

FROZEN_OPERATIONAL_PATHS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl",
)


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def query(**overrides) -> dict:
    payload = {
        "query_id": "QT",
        "disease": "Cholangiocarcinoma",
        "biomarker": "FGFR2::BICC1 Fusion",
        "polarity": "supports",
        "interventions": [],
    }
    payload.update(overrides)
    return payload


class MigrationCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_migration()
        cls.parents = {p.graph_evidence_id: p for p in cls.result.parents}
        cls.diagnostic = {c.graph_evidence_id: c for c in cls.result.diagnostic_claims}
        cls.deprecations = {d.graph_evidence_id: d for d in cls.result.deprecations}


# ── modello ───────────────────────────────────────────────────────────────────


class TestModel(MigrationCase):
    def test_a_diagnostic_claim_has_no_intervention(self) -> None:
        for claim in self.result.diagnostic_claims:
            with self.subTest(claim=claim.claim_id):
                self.assertEqual(claim.intervention_members, ())
                self.assertFalse(hasattr(claim, "intervention"))
                self.assertNotIn("intervention", claim.to_dict())
                self.assertFalse(claim.to_dict()["intervention_present"])

    def test_a_prognostic_claim_has_no_intervention(self) -> None:
        claim = PrognosticClaim(
            claim_id="CLM-test",
            parent_id="GEP-test",
            graph_evidence_id="evidence:1",
            biomarker="B",
            disease_scope="D",
            direction="poor_outcome",
            polarity="supports",
            prognostic_subject="S",
            outcome="overall survival",
        )
        self.assertEqual(claim.intervention_members, ())
        self.assertNotIn("intervention", claim.to_dict())
        self.assertFalse(claim.receives_therapy_score)

    def test_diagnostic_is_distinct_from_therapeutic(self) -> None:
        self.assertEqual(domain_of(self.diagnostic["evidence:1846"]), DOMAIN_DIAGNOSTIC)
        therapeutic = self.result.therapeutic_claims[0]
        self.assertEqual(domain_of(therapeutic), DOMAIN_THERAPEUTIC)
        self.assertNotEqual(
            self.diagnostic["evidence:1846"].claim_type, therapeutic.claim_type
        )

    def test_prognostic_is_distinct_from_predictive(self) -> None:
        """Il tipo predittivo non esiste, e il prognostico non lo diventa."""
        self.assertNotIn("predictive_claim", ALL_CLAIM_TYPES)
        with self.assertRaises(NonTherapeuticClaimError):
            PrognosticClaim(
                claim_id="CLM-x",
                parent_id="GEP-x",
                graph_evidence_id="evidence:1",
                biomarker="B",
                disease_scope="D",
                direction="poor_outcome",
                polarity="supports",
                prognostic_subject="S",
                outcome="overall survival",
                predictive_effect_asserted=True,
            )

    def test_an_association_is_never_promoted_to_causality(self) -> None:
        with self.assertRaises(NonTherapeuticClaimError):
            PrognosticClaim(
                claim_id="CLM-x",
                parent_id="GEP-x",
                graph_evidence_id="evidence:1",
                biomarker="B",
                disease_scope="D",
                direction="poor_outcome",
                polarity="supports",
                prognostic_subject="S",
                outcome="overall survival",
                causality_asserted=True,
            )

    def test_a_biomarker_does_not_become_a_validated_test(self) -> None:
        with self.assertRaises(NonTherapeuticClaimError):
            DiagnosticClaim(
                claim_id="CLM-x",
                parent_id="GEP-x",
                graph_evidence_id="evidence:1",
                biomarker="B",
                disease_scope="D",
                direction="diagnostic",
                polarity="supports",
                diagnostic_subject="S",
                diagnostic_interpretation="subtype_defining_alteration",
                clinical_validation_asserted=True,
            )

    def test_a_prognostic_claim_requires_a_named_outcome(self) -> None:
        with self.assertRaises(NonTherapeuticClaimError):
            PrognosticClaim(
                claim_id="CLM-x",
                parent_id="GEP-x",
                graph_evidence_id="evidence:1",
                biomarker="B",
                disease_scope="D",
                direction="poor_outcome",
                polarity="supports",
                prognostic_subject="S",
                outcome="",
            )

    def test_the_claim_domain_is_mandatory_and_consistent(self) -> None:
        for claim in self.result.evidence_claims:
            with self.subTest(claim=claim.claim_id):
                self.assertIn(domain_of(claim), CLAIM_DOMAINS)
        with self.assertRaises(DomainError):
            domain_of(replace(self.diagnostic["evidence:1846"], claim_domain="therapeutic"))

    def test_only_therapeutic_claims_receive_a_therapy_score(self) -> None:
        self.assertTrue(receives_therapy_score("atomic_intervention_claim"))
        self.assertFalse(receives_therapy_score("diagnostic_claim"))
        self.assertFalse(receives_therapy_score("prognostic_claim"))

    def test_a_parent_without_claims_is_allowed(self) -> None:
        without = {r["graph_evidence_id"] for r in self.result.parents_without_claims}
        self.assertEqual(without, {"evidence:347", "evidence:3811", "evidence:4759"})
        for graph_evidence_id in without:
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(self.parents[graph_evidence_id].child_claim_ids, ())

    def test_the_versions_are_bumped_and_not_promoted(self) -> None:
        self.assertEqual(MODEL_SCHEMA_VERSION_V11, "qualified_claim_model/1.1")
        self.assertEqual(SHADOW_REPOSITORY_VERSION_V11, "qualified_claim_repository/1.1")
        self.assertEqual(STRUCTURAL_GATE_VERSION_V11, "claim_structural_gate/1.1")
        self.assertEqual(OUTPUT_CONTRACT_VERSION_V11, "qualified_claim_retrieval_result/1.1")
        self.assertEqual(MIGRATION_STATUS, "shadow_not_promoted")
        # Le costanti 1.0 restano leggibili e invariate.
        self.assertEqual(MODEL_SCHEMA_VERSION, "qualified_claim_model/1.0")
        self.assertEqual(SHADOW_REPOSITORY_VERSION, "qualified_claim_repository/1.0")


# ── conteggi ──────────────────────────────────────────────────────────────────


class TestCounts(MigrationCase):
    def test_the_counts_are_derived(self) -> None:
        self.assertEqual(len(self.result.parents), 147)
        self.assertEqual(len(self.result.therapeutic_claims), 146)
        self.assertEqual(len(self.result.diagnostic_claims), 2)
        self.assertEqual(len(self.result.prognostic_claims), 0)
        self.assertEqual(self.result.total_claims, 148)
        self.assertEqual(
            len(self.result.therapeutic_claims)
            + len(self.result.diagnostic_claims)
            + len(self.result.prognostic_claims),
            self.result.total_claims,
        )
        self.assertEqual(len(self.result.parents_without_claims), 3)

    def test_no_prognostic_claim_is_materialised_in_this_phase(self) -> None:
        self.assertEqual(self.result.prognostic_claims, ())

    def test_the_manifest_does_not_force_the_total(self) -> None:
        manifest = load_json(OUT_DIR / "shadow_update_manifest.json")
        self.assertFalse(manifest["invariants"]["expected_count_forced"])
        counts = manifest["counts"]
        self.assertEqual(
            counts["therapeutic_claims"]
            + counts["diagnostic_claims"]
            + counts["prognostic_claims"],
            counts["evidence_claims_total"],
        )


# ── record ────────────────────────────────────────────────────────────────────


class TestRecords(MigrationCase):
    def test_evidence_1846_becomes_a_diagnostic_claim(self) -> None:
        claim = self.diagnostic["evidence:1846"]
        self.assertEqual(claim.claim_type, "diagnostic_claim")
        self.assertEqual(claim.biomarker, "FGFR2::BICC1 Fusion")
        self.assertEqual(claim.disease_scope, "Cholangiocarcinoma")
        self.assertEqual(claim.diagnostic_interpretation, "subtype_defining_alteration")
        self.assertEqual(claim.source_unit_ids, ("PU-PMID-24122810-cohort-1",))
        self.assertTrue(claim.locators)
        self.assertEqual(claim.propagation_policy, "prototype_only")
        self.assertFalse(claim.hard_filterable)
        self.assertFalse(claim.final_evaluable)
        self.assertFalse(claim.clinical_validation_asserted)
        self.assertFalse(claim.prevalence_attributable_to_subject)
        self.assertIn(
            "PREVALENCE_AGGREGATE_ONLY_NOT_PARTNER_SPECIFIC", claim.limitation_codes
        )
        self.assertIn("CLINICAL_UTILITY_NOT_ASSERTED", claim.limitation_codes)

    def test_evidence_1847_is_a_distinct_claim(self) -> None:
        first = self.diagnostic["evidence:1846"]
        second = self.diagnostic["evidence:1847"]
        self.assertNotEqual(first.claim_id, second.claim_id)
        self.assertEqual(second.biomarker, "FGFR2::AHCYL1 Fusion")
        # Stessa fonte e stessa unita': a distinguerli e' il partner di fusione.
        self.assertEqual(first.source_unit_ids, second.source_unit_ids)
        self.assertNotEqual(first.diagnostic_subject, second.diagnostic_subject)

    def test_evidence_347_produces_no_claim_of_any_kind(self) -> None:
        for claim in self.result.evidence_claims:
            with self.subTest(claim=claim.claim_id):
                self.assertNotEqual(claim.graph_evidence_id, "evidence:347")
        self.assertEqual(self.parents["evidence:347"].child_claim_ids, ())

    def test_evidence_347_is_not_promotable_as_a_prognostic_claim(self) -> None:
        deprecation = self.deprecations["evidence:347"]
        self.assertEqual(
            deprecation.deprecation_state, "promotion_blocked_pending_full_text"
        )
        self.assertTrue(deprecation.blocks_promotion)
        self.assertTrue(deprecation.is_deprecated)
        self.assertEqual(deprecation.replacement_claim_ids, ())
        record = next(
            r
            for r in self.result.parents_without_claims
            if r["graph_evidence_id"] == "evidence:347"
        )
        self.assertEqual(
            record["no_claim_reason"], "SOURCE_CONTRADICTS_GRAPH_PROGNOSTIC_DIRECTION"
        )
        self.assertEqual(
            record["unresolved_reason"], "FULL_TEXT_REQUIRED_FOR_PREDICTIVE_SCOPE"
        )
        self.assertTrue(record["promotion_blocked"])
        self.assertTrue(record["requires_full_text"])

    def test_evidence_347_audit_records_the_state_change(self) -> None:
        audit = load_json(OUT_DIR / "evidence_347_promotion_audit.json")
        self.assertEqual(audit["claims_created"], 0)
        self.assertEqual(audit["claim_types_created"], [])
        self.assertTrue(audit["legacy_statement_promotable_before"])
        self.assertFalse(audit["legacy_statement_promotable_after"])
        self.assertFalse(audit["operational_statement_modified"])
        self.assertFalse(audit["full_text_retrieved"])

    def test_evidence_3811_and_4759_stay_without_positive_replacement(self) -> None:
        for graph_evidence_id in ("evidence:3811", "evidence:4759"):
            deprecation = self.deprecations[graph_evidence_id]
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(
                    deprecation.deprecation_state, "deprecated_without_replacement"
                )
                self.assertEqual(deprecation.replacement_claim_ids, ())
                self.assertTrue(deprecation.blocks_promotion)

    def test_the_retirement_counts_are_derived_not_assumed(self) -> None:
        retire = [d for d in self.result.deprecations if d.is_deprecated]
        replaced = [d for d in retire if d.replacement_claim_ids]
        without = [d for d in retire if not d.replacement_claim_ids]
        blocked = [d for d in self.result.deprecations if d.blocks_promotion]
        # 13 adjudicati + 2 diagnostici = 15 con sostituzione? No: i 13 adjudicati
        # includono i 2 senza sostituto, quindi 11 + 2 = 13 con sostituzione.
        self.assertEqual(len(retire), 16)
        self.assertEqual(len(replaced), 13)
        self.assertEqual(len(without), 3)
        self.assertEqual(len(blocked), 3)
        self.assertEqual(len(replaced) + len(without), len(retire))

    def test_the_two_diagnostic_statements_are_marked_replaced(self) -> None:
        for graph_evidence_id in ("evidence:1846", "evidence:1847"):
            deprecation = self.deprecations[graph_evidence_id]
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(
                    deprecation.deprecation_state, "replaced_by_diagnostic_claim"
                )
                self.assertEqual(len(deprecation.replacement_claim_ids), 1)
                self.assertFalse(deprecation.blocks_promotion)


# ── gate ──────────────────────────────────────────────────────────────────────


class TestDomainGate(MigrationCase):
    def test_a_diagnostic_query_retrieves_the_diagnostic_claim(self) -> None:
        claim = self.diagnostic["evidence:1846"]
        match = GATE.evaluate(
            query(query_domain="diagnostic_evidence_query"), claim
        )
        self.assertTrue(match.domain_match)
        self.assertTrue(match.primary_candidate_eligible)
        self.assertEqual(match.bucket, GATE.PRIMARY_BUCKET)
        self.assertEqual(match.section, "diagnostic_results")

    def test_a_therapeutic_query_does_not_return_a_diagnostic_claim_as_primary(self) -> None:
        claim = self.diagnostic["evidence:1846"]
        match = GATE.evaluate(
            query(query_domain="therapeutic_evidence_query", direction="sensitivity"),
            claim,
        )
        self.assertFalse(match.primary_candidate_eligible)
        self.assertFalse(match.domain_match)
        self.assertIn("DIAGNOSTIC_CLAIM_NOT_THERAPEUTIC", match.exclusion_reason_codes)

    def test_a_prognostic_query_does_not_return_a_therapeutic_claim(self) -> None:
        therapeutic = self.result.therapeutic_claims[0]
        match = GATE.evaluate(
            query(
                query_domain="prognostic_evidence_query",
                biomarker=therapeutic.biomarker,
                disease=therapeutic.disease_scope,
            ),
            therapeutic,
        )
        self.assertFalse(match.primary_candidate_eligible)
        self.assertIn("THERAPEUTIC_CLAIM_NOT_DIAGNOSTIC", match.exclusion_reason_codes)

    def test_a_diagnostic_query_does_not_return_a_therapeutic_claim(self) -> None:
        therapeutic = self.result.therapeutic_claims[0]
        match = GATE.evaluate(
            query(
                query_domain="diagnostic_evidence_query",
                biomarker=therapeutic.biomarker,
                disease=therapeutic.disease_scope,
            ),
            therapeutic,
        )
        self.assertFalse(match.primary_candidate_eligible)

    def test_no_therapy_score_for_non_therapeutic_claims(self) -> None:
        for claim in self.result.diagnostic_claims:
            match = GATE.evaluate(query(query_domain="diagnostic_evidence_query"), claim)
            with self.subTest(claim=claim.claim_id):
                self.assertFalse(match.therapy_score_allowed)
                self.assertTrue(match.score_eligibility["therapy_score_forbidden"])

    def test_cross_domain_ranking_is_impossible(self) -> None:
        diagnostic = GATE.evaluate(
            query(query_domain="untyped_evidence_query"),
            self.diagnostic["evidence:1846"],
        )
        therapeutic_claim = next(
            c
            for c in self.result.therapeutic_claims
            if c.biomarker == "FGFR2::BICC1 Fusion"
        )
        therapeutic = GATE.evaluate(
            query(query_domain="untyped_evidence_query"), therapeutic_claim
        )
        with self.assertRaises(GATE.DomainGateError):
            GATE.rank_within_domain([diagnostic, therapeutic])
        # Dentro un dominio l'ordinamento funziona.
        GATE.rank_within_domain([diagnostic])

    def test_an_untyped_query_matches_every_domain(self) -> None:
        for claim in (self.diagnostic["evidence:1846"], self.result.therapeutic_claims[0]):
            match = GATE.evaluate(
                query(
                    query_domain=None,
                    biomarker=claim.biomarker,
                    disease=claim.disease_scope,
                ),
                claim,
            )
            with self.subTest(claim=claim.claim_id):
                self.assertTrue(match.domain_match)

    def test_an_unknown_query_domain_raises(self) -> None:
        with self.assertRaises(GATE.DomainGateError):
            GATE.query_domain({"query_domain": "nonexistent"})


# ── output ────────────────────────────────────────────────────────────────────


class TestOutput(MigrationCase):
    def test_a_diagnostic_claim_is_not_flattened_into_an_intervention(self) -> None:
        claim = self.diagnostic["evidence:1846"]
        match = GATE.evaluate(query(query_domain="diagnostic_evidence_query"), claim)
        result = OUT.build_result("QT", claim, match)
        self.assertEqual(result.subject_representation, "diagnostic_subject")
        self.assertIsNone(result.intervention_representation)
        self.assertIsNotNone(result.diagnostic_representation)
        self.assertFalse(result.therapy_score_allowed)

    def test_a_therapeutic_claim_keeps_its_intervention_representation(self) -> None:
        claim = self.result.therapeutic_claims[0]
        match = GATE.evaluate(
            query(
                query_domain="therapeutic_evidence_query",
                biomarker=claim.biomarker,
                disease=claim.disease_scope,
                direction=claim.direction,
                interventions=[getattr(claim, "intervention", "")],
            ),
            claim,
        )
        result = OUT.build_result("QT", claim, match)
        self.assertIsNotNone(result.intervention_representation)
        self.assertIsNone(result.diagnostic_representation)

    def test_the_untyped_output_keeps_sections_separate(self) -> None:
        simulation = load_json(OUT_DIR / "untyped_sectioned_output_simulation.json")
        self.assertFalse(simulation["cross_domain_ranking"])
        self.assertTrue(simulation["queries"])
        for query_id, payload in simulation["queries"].items():
            with self.subTest(query_id=query_id):
                self.assertTrue(payload["sections_are_separate"])
                self.assertFalse(payload["cross_domain_score_comparison"])
                for section in (
                    "therapeutic_results",
                    "diagnostic_results",
                    "prognostic_results",
                ):
                    self.assertIn(section, payload)
                for row in payload["diagnostic_results"]:
                    self.assertEqual(row["claim_domain"], DOMAIN_DIAGNOSTIC)
                    self.assertIsNone(row["intervention_representation"])
                for row in payload["therapeutic_results"]:
                    self.assertEqual(row["claim_domain"], DOMAIN_THERAPEUTIC)

    def test_the_simulation_never_gives_therapy_score_to_a_non_therapeutic_claim(self) -> None:
        rows = load_jsonl(OUT_DIR / "claim_domain_gate_simulation.jsonl")
        self.assertTrue(rows)
        for row in rows:
            if row["claim_domain"] in (DOMAIN_DIAGNOSTIC, DOMAIN_PROGNOSTIC):
                with self.subTest(object_id=row["object_id"]):
                    self.assertFalse(row["therapy_score_allowed"])
                    self.assertIsNone(row["intervention_representation"])

    def test_the_diagnostic_claims_are_primary_only_in_the_right_queries(self) -> None:
        rows = load_jsonl(OUT_DIR / "claim_domain_gate_simulation.jsonl")
        primary = {
            (row["query_id"], row["object_id"])
            for row in rows
            if row["claim_domain"] == DOMAIN_DIAGNOSTIC
            and row["bucket"] == GATE.PRIMARY_BUCKET
        }
        allowed_queries = {"D01", "D02", "U01"}
        for query_id, _ in sorted(primary):
            with self.subTest(query_id=query_id):
                self.assertIn(query_id, allowed_queries)

    def test_evidence_347_produces_no_primary_result(self) -> None:
        rows = load_jsonl(OUT_DIR / "claim_domain_gate_simulation.jsonl")
        for row in rows:
            if row["parent_graph_evidence_id"] != "evidence:347":
                continue
            with self.subTest(object_id=row["object_id"]):
                self.assertNotEqual(row["bucket"], GATE.PRIMARY_BUCKET)


# ── identita' ─────────────────────────────────────────────────────────────────


class TestIdentity(MigrationCase):
    def test_the_ids_match_the_amended_simulation(self) -> None:
        simulated = {
            r["graph_evidence_id"]: r["claim_id"]
            for r in load_jsonl(
                V3
                / "non_therapeutic_claim_contract_and_erratum/claim_id_simulation.jsonl"
            )
        }
        for graph_evidence_id, claim in sorted(self.diagnostic.items()):
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(claim.claim_id, simulated[graph_evidence_id])

    def test_the_ids_are_stable_on_recomputation(self) -> None:
        again = run_migration()
        self.assertEqual(
            [c.claim_id for c in again.evidence_claims],
            [c.claim_id for c in self.result.evidence_claims],
        )

    def test_there_are_no_collisions(self) -> None:
        ids = [c.claim_id for c in self.result.evidence_claims]
        ids += [p.parent_id for p in self.result.parents]
        ids += [a.association_id for a in self.result.unsupported]
        ids += [a.association_id for a in self.result.unresolved]
        self.assertEqual(len(ids), len(set(ids)))

    def test_the_identity_carries_no_artificial_intervention(self) -> None:
        from backend.pipeline.evidence.shadow.identity import (
            non_therapeutic_identity_payload,
        )

        payload = non_therapeutic_identity_payload(
            graph_evidence_id="evidence:1846",
            claim_type="diagnostic_claim",
            canonical_subject="s",
            biomarker="B",
            disease_scope="D",
            direction_or_interpretation="subtype_defining_alteration",
            polarity="supports",
            source_unit_id="PU-1",
        )
        self.assertNotIn("intervention", payload.lower())
        self.assertEqual(len(payload.split("|")), 8)

    def test_the_parent_lineage_is_preserved(self) -> None:
        for claim in self.result.diagnostic_claims:
            with self.subTest(claim=claim.claim_id):
                self.assertEqual(
                    claim.parent_id, self.parents[claim.graph_evidence_id].parent_id
                )
                self.assertIn(claim.claim_id, self.parents[claim.graph_evidence_id].child_claim_ids)


# ── compatibilita' e determinismo ─────────────────────────────────────────────


class TestArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = build()
        cls.manifest = json.loads(cls.artifacts["shadow_update_manifest.json"])

    def test_all_declared_artifacts_exist(self) -> None:
        expected = {
            "graph_evidence_parents_v1_1.jsonl",
            "evidence_claims_v1_1.jsonl",
            "therapeutic_claims_v1_1.jsonl",
            "diagnostic_claims_v1_1.jsonl",
            "prognostic_claims_v1_1.jsonl",
            "parent_without_claim_v1_1.jsonl",
            "legacy_statement_deprecation_map_v1_1.jsonl",
            "qualification_link_regeneration_plan_v1_1.jsonl",
            "qualified_view_regeneration_plan_v1_1.jsonl",
            "claim_domain_gate_simulation.jsonl",
            "untyped_sectioned_output_simulation.json",
            "evidence_347_promotion_audit.json",
            "repository_version_lineage.json",
            "shadow_update_manifest.json",
            "NON_THERAPEUTIC_SHADOW_UPDATE.md",
            "CLAIM_DOMAIN_GATE_IMPLEMENTATION.md",
            "SHADOW_REPOSITORY_V1_1_READINESS.md",
        }
        for name in sorted(expected):
            with self.subTest(artifact=name):
                self.assertTrue((OUT_DIR / name).exists())

    def test_two_generations_are_byte_identical(self) -> None:
        self.assertEqual(build(), self.artifacts)

    def test_reversing_the_input_order_changes_nothing(self) -> None:
        self.assertEqual(build(reverse=True), self.artifacts)

    def test_the_files_on_disk_match_the_regenerated_content(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            with self.subTest(artifact=name):
                self.assertEqual((OUT_DIR / name).read_text(encoding="utf-8"), text)

    def test_the_manifest_hashes_match(self) -> None:
        for name, expected in self.manifest["artifact_sha256"].items():
            digest = hashlib.sha256(
                (OUT_DIR / name).read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            with self.subTest(artifact=name):
                self.assertEqual(digest, expected)

    def test_no_machine_specific_path_leaks(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            lowered = text.lower()
            with self.subTest(artifact=name):
                for fragment in ("c:\\", "/users/", "/home/", "appdata"):
                    self.assertNotIn(fragment, lowered)

    def test_the_manifest_declares_nothing_was_promoted_or_modified(self) -> None:
        for flag, value in sorted(self.manifest["invariants"].items()):
            if flag == "therapy_score_on_non_therapeutic_claims":
                self.assertEqual(value, 0)
                continue
            with self.subTest(flag=flag):
                self.assertFalse(value)

    def test_the_lineage_keeps_version_1_0_addressable(self) -> None:
        lineage = load_json(OUT_DIR / "repository_version_lineage.json")
        previous = next(
            v
            for v in lineage["versions"]
            if v["repository_schema"] == SHADOW_REPOSITORY_VERSION
        )
        self.assertFalse(previous["modified_by_this_phase"])
        self.assertEqual(previous["status"], "superseded_but_preserved")
        self.assertTrue(previous["artifact_sha256"])
        for name, digest in previous["artifact_sha256"].items():
            actual = hashlib.sha256(
                (SHADOW_V10 / name).read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            with self.subTest(artifact=name):
                self.assertEqual(actual, digest)


class TestShadowV10Unchanged(unittest.TestCase):
    def test_the_1_0_repository_regenerates_identically(self) -> None:
        from benchmarks.mtb_evidence.evaluation.scripts.build_typed_claim_shadow_migration import (
            build as build_v10,
        )

        for name, text in sorted(build_v10().items()):
            with self.subTest(artifact=name):
                self.assertEqual((SHADOW_V10 / name).read_text(encoding="utf-8"), text)

    def test_the_1_0_therapeutic_claims_are_unchanged(self) -> None:
        before = load_jsonl(SHADOW_V10 / "typed_claims.jsonl")
        after = load_jsonl(OUT_DIR / "therapeutic_claims_v1_1.jsonl")
        self.assertEqual(len(before), len(after))
        self.assertEqual(
            {c["claim_id"] for c in before}, {c["claim_id"] for c in after}
        )

    def test_the_1_0_deprecation_map_has_no_promotion_field(self) -> None:
        """Il campo 1.1 non deve essere comparso nel 1.0."""
        for row in load_jsonl(SHADOW_V10 / "legacy_statement_deprecation_map.jsonl"):
            with self.subTest(statement=row["legacy_statement_id"]):
                self.assertNotIn("blocks_promotion", row)


# La verifica «nulla di congelato e' stato toccato» sta in
# `backend/tests_history/test_untouched_artifacts.py`: confronta con una
# revisione di partenza, e senza storia git quel termine non esiste.



class TestIsolation(unittest.TestCase):
    def sources(self) -> list[Path]:
        shadow = REPO_ROOT / "backend/pipeline/evidence/shadow"
        script = (
            REPO_ROOT
            / "benchmarks/mtb_evidence/evaluation/scripts/build_non_therapeutic_shadow_update.py"
        )
        return sorted(shadow.glob("*.py")) + [script]

    def test_the_gold_is_never_read(self) -> None:
        for path in self.sources():
            blob = path.read_text(encoding="utf-8").lower()
            with self.subTest(module=path.name):
                for fragment in (
                    "clinical_gold",
                    "snapshot_gold",
                    "statement_qualification_gold",
                    "gold_pilot",
                    "evaluation_gold_snapshot",
                    "mtb_evidence_gold",
                    "recall@",
                    "precision@",
                ):
                    self.assertNotIn(fragment, blob)

    def test_no_network_neo4j_or_llm_import(self) -> None:
        forbidden = (
            "requests",
            "httpx",
            "aiohttp",
            "neo4j",
            "openai",
            "anthropic",
            "urllib",
            "socket",
            "subprocess",
        )
        for path in self.sources():
            imports = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            with self.subTest(module=path.name):
                for line in imports:
                    for fragment in forbidden:
                        self.assertNotIn(fragment, line)

    def test_no_operational_module_imports_the_shadow_package(self) -> None:
        evidence = REPO_ROOT / "backend/pipeline/evidence"
        for path in sorted(evidence.glob("*.py")):
            imports = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            with self.subTest(module=path.name):
                for line in imports:
                    self.assertNotIn("shadow", line)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
