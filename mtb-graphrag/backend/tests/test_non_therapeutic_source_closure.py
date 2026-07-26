"""Protegge la provenienza e il contegno della chiusura documentale.

Il punto di questi test non e' che una revisione sia stata fatta, ma che non sia
stata fatta piu' di quanto le fonti consentano: nessun claim dal solo disegno
predittivo, nessun intervento inventato, nessuna prevalenza aggregata attribuita
a un partner, nessuna utilita' clinica dedotta.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.scripts.build_non_therapeutic_source_closure import (
    BLINDED_FIELDS,
    build,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
OUT = V3 / "non_therapeutic_source_closure"
SHADOW_V11 = V3 / "non_therapeutic_shadow_update"
SHADOW_V10 = V3 / "typed_claim_shadow_migration"
CORPUS = V3 / "qualification_corpus_v2"

START_SHA = "771e30d0178c1aadbcc3ec5ff21dacfcd28f1238"
# La fase si chiude sull'ultimo commit di contenuto. L'estremo e' fisso e non
# `HEAD`, che cresce a ogni commit successivo e riporterebbe il controllo a
# essere aperto.
PHASE_END_SHA = "99d9dd83e8bd267e34608f3df3fedb4fb72cdd62"

FROZEN_OPERATIONAL_PATHS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/active_source_profile_units.jsonl",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class ClosureCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = build()
        cls.scope = load_json(OUT / "review_scope.json")
        cls.access = {
            r["source_id"]: r for r in load_jsonl(OUT / "source_access_inventory.jsonl")
        }
        cls.hashes = load_json(OUT / "source_file_hashes.json")
        cls.review_347 = load_json(OUT / "evidence_347_source_review.json")
        cls.proposal_347 = load_json(OUT / "evidence_347_claim_proposal.json")
        cls.unit = load_json(OUT / "pmid_24122810_source_unit_review.json")
        cls.claim_reviews = {
            r["graph_evidence_id"]: r
            for r in load_jsonl(OUT / "diagnostic_claim_reviews.jsonl")
        }
        cls.locators = load_jsonl(OUT / "locator_audit.jsonl")
        cls.limitations = load_jsonl(OUT / "source_limitations.jsonl")
        cls.simulation = load_json(OUT / "shadow_update_simulation.json")
        cls.manifest = load_json(OUT / "review_manifest.json")


# ── accesso alle fonti ────────────────────────────────────────────────────────


class TestSourceAccess(ClosureCase):
    def test_both_sources_are_declared_unavailable_in_full_text(self) -> None:
        for source_id in ("PMID:24662454", "PMID:24122810"):
            with self.subTest(source_id=source_id):
                self.assertEqual(
                    self.access[source_id]["source_access_status"], "full_text_unavailable"
                )
                self.assertEqual(self.access[source_id]["completeness"], "abstract_only")
        self.assertEqual(self.manifest["full_text_acquired"], 0)
        self.assertEqual(self.manifest["full_text_unavailable"], 2)

    def test_the_priority_order_was_walked_before_declaring_unavailable(self) -> None:
        for source_id, entry in sorted(self.access.items()):
            priorities = [a["priority"] for a in entry["access_attempts"]]
            with self.subTest(source_id=source_id):
                # Le priorita' 1-4 sono state tentate prima di ripiegare sull'abstract.
                self.assertTrue(set(priorities) >= {1, 2, 3, 4, 5})
                self.assertEqual(entry["highest_priority_succeeded"], 5)

    def test_no_secondary_source_was_used(self) -> None:
        for source_id, entry in sorted(self.access.items()):
            with self.subTest(source_id=source_id):
                self.assertFalse(entry["secondary_sources_used"])
                self.assertFalse(entry["content_reconstructed"])
        self.assertFalse(self.scope["secondary_sources_used"])
        self.assertFalse(self.scope["content_reconstructed"])

    def test_the_material_hashes_match_the_local_cache(self) -> None:
        self.assertTrue(self.hashes["all_hashes_match"])
        for source_id, entry in sorted(self.hashes["entries"].items()):
            with self.subTest(source_id=source_id):
                self.assertTrue(entry["hash_matches"])
                self.assertFalse(entry["full_text_file_present"])
                self.assertIsNone(entry["full_text_sha256"])

    def test_every_access_record_has_a_locator_beyond_the_pmid(self) -> None:
        for source_id, entry in sorted(self.access.items()):
            with self.subTest(source_id=source_id):
                self.assertTrue(entry["locator"].startswith("http"))
                self.assertTrue(entry["access_date"])
                self.assertTrue(entry["file_sha256"])


# ── parte A: evidence:347 ─────────────────────────────────────────────────────


class TestEvidence347(ClosureCase):
    def test_the_record_is_reviewed_and_the_access_declared(self) -> None:
        self.assertEqual(self.review_347["graph_evidence_id"], "evidence:347")
        self.assertEqual(self.review_347["source_access_status"], "full_text_unavailable")
        self.assertEqual(len(self.review_347["questions"]), 10)

    def test_the_graph_prognostic_direction_is_rejected_against_the_source(self) -> None:
        self.assertIn("graph_prognostic_direction_rejected", self.review_347["decisions"])
        self.assertFalse(self.review_347["prognostic_direction_supported"])
        self.assertEqual(self.review_347["graph_assertion"]["direction"], "prognostic")
        self.assertIn(
            "SOURCE_REPORTS_TREATMENT_EFFECT_NOT_PROGNOSIS",
            self.review_347["reason_codes"],
        )

    def test_no_claim_is_created_from_a_predictive_design_alone(self) -> None:
        self.assertFalse(self.review_347["claim_created"])
        self.assertFalse(self.proposal_347["proposal_made"])
        self.assertIsNone(self.proposal_347["proposed_claim"])
        self.assertIn("predictive_scope_unresolved", self.review_347["decisions"])

    def test_no_intervention_is_invented(self) -> None:
        self.assertFalse(self.review_347["intervention_invented"])
        self.assertIsNone(self.review_347["graph_assertion"]["intervention"])
        preconditions = self.proposal_347["preconditions"]
        self.assertTrue(preconditions["explicit_intervention_in_source"])
        self.assertFalse(preconditions["explicit_intervention_in_graph_record"])
        self.assertIn(
            "explicit_intervention_in_graph_record",
            self.proposal_347["unmet_preconditions"],
        )

    def test_no_new_claim_type_is_introduced(self) -> None:
        self.assertFalse(self.proposal_347["new_claim_type_introduced"])
        self.assertIsNone(self.proposal_347["proposed_claim_type"])
        self.assertEqual(self.scope["new_claim_types_introduced"], 0)

    def test_the_l858r_mention_is_a_population_frequency_not_an_outcome(self) -> None:
        questions = self.review_347["questions"]
        self.assertFalse(questions["q5_l858r_separate_result"]["answer"])
        self.assertFalse(questions["q6_exon19_separate_result"]["answer"])
        self.assertFalse(questions["q9_statistically_separable_for_l858r"]["answer"])
        self.assertIn(
            "BIOMARKER_APPEARS_ONLY_AS_POPULATION_FREQUENCY",
            self.review_347["reason_codes"],
        )
        # La frase citata e' quella della frequenza, non un risultato.
        self.assertIn(
            "The most common mutations were exon 19 deletions and L858R",
            questions["q5_l858r_separate_result"]["verbatim"],
        )

    def test_the_forbidden_transformations_are_recorded_as_avoided(self) -> None:
        avoided = self.proposal_347["forbidden_transformations_avoided"]
        for fragment in (
            "prognostic_to_predictive_automatico",
            "predictive_design_to_predictive_claim_specifico",
            "composizione_della_popolazione_to_risultato_sul_biomarcatore",
            "cetuximab_citato_to_supporto_terapeutico_per_L858R",
        ):
            with self.subTest(transformation=fragment):
                self.assertIn(fragment, avoided)

    def test_the_legacy_statement_stays_promotion_blocked(self) -> None:
        self.assertEqual(
            self.review_347["legacy_statement_status"],
            "promotion_blocked_pending_full_text",
        )
        self.assertFalse(
            self.review_347["legacy_statement_status_changed_by_this_phase"]
        )
        shadow = {
            d["graph_evidence_id"]: d
            for d in load_jsonl(SHADOW_V11 / "legacy_statement_deprecation_map_v1_1.jsonl")
        }
        self.assertEqual(
            shadow["evidence:347"]["deprecation_state"],
            "promotion_blocked_pending_full_text",
        )


# ── parte B: PMID:24122810 ────────────────────────────────────────────────────


class TestSourceUnitReview(ClosureCase):
    def test_the_source_unit_received_a_first_review(self) -> None:
        self.assertEqual(self.unit["source_unit_id"], "PU-PMID-24122810-cohort-1")
        self.assertEqual(self.unit["review_status"], "first_review_complete")
        self.assertEqual(self.unit["review_independence"], "non_independent")
        self.assertEqual(self.unit["propagation_policy"], "prototype_only")
        self.assertFalse(self.unit["hard_filterable"])
        self.assertFalse(self.unit["final_evaluable"])
        self.assertTrue(self.unit["requires_second_independent_review"])

    def test_the_operational_unit_was_not_modified(self) -> None:
        self.assertFalse(self.unit["operational_unit_modified"])
        operational = next(
            u
            for u in load_jsonl(CORPUS / "active_source_profile_units.jsonl")
            if u["profile_unit_id"] == "PU-PMID-24122810-cohort-1"
        )
        self.assertEqual(operational["review_status"], "awaiting_first_review")
        self.assertFalse(operational["is_evaluable"])

    def test_the_two_claims_are_assessed_separately(self) -> None:
        self.assertEqual(
            sorted(self.claim_reviews), ["evidence:1846", "evidence:1847"]
        )
        first = self.claim_reviews["evidence:1846"]
        second = self.claim_reviews["evidence:1847"]
        self.assertNotEqual(first["review_id"], second["review_id"])
        self.assertNotEqual(first["biomarker"], second["biomarker"])
        self.assertNotEqual(first["claim_id"], second["claim_id"])

    def test_both_claims_require_narrowing_of_the_disease_scope(self) -> None:
        for graph_evidence_id, review in sorted(self.claim_reviews.items()):
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(review["decision"], "diagnostic_claim_requires_narrowing")
                narrowing = review["required_narrowing"]
                self.assertEqual(len(narrowing), 1)
                self.assertEqual(narrowing[0]["field"], "disease_scope")
                self.assertEqual(narrowing[0]["current"], "Cholangiocarcinoma")
                self.assertEqual(
                    narrowing[0]["narrowed_to"], "Intrahepatic Cholangiocarcinoma"
                )

    def test_aggregate_prevalence_is_never_attributed_to_a_partner(self) -> None:
        for graph_evidence_id, review in sorted(self.claim_reviews.items()):
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertIn(
                    "PREVALENCE_AGGREGATE_ONLY_NOT_PARTNER_SPECIFIC",
                    review["limitation_codes"],
                )
                self.assertTrue(
                    any(
                        "prevalenza partner-specifica" in item
                        for item in review["content_not_attributable"]
                    )
                )
        codes = {row["code"] for row in self.limitations}
        self.assertIn("PREVALENCE_AGGREGATE_ONLY_NOT_PARTNER_SPECIFIC", codes)

    def test_clinical_utility_is_never_invented(self) -> None:
        for graph_evidence_id, review in sorted(self.claim_reviews.items()):
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertIn("CLINICAL_UTILITY_NOT_ASSERTED", review["limitation_codes"])
                for forbidden in (
                    "test diagnostico clinicamente validato",
                    "sensibilita' o specificita' diagnostica",
                    "utilita' clinica",
                    "scelta terapeutica",
                    "prognosi",
                ):
                    self.assertIn(forbidden, review["content_not_attributable"])

    def test_the_therapeutic_association_stays_preclinical_and_out_of_scope(self) -> None:
        codes = {item["code"] for item in self.unit["limitations"]}
        self.assertIn("THERAPEUTIC_ASSOCIATION_IS_PRECLINICAL", codes)

    def test_no_claim_can_become_final(self) -> None:
        for graph_evidence_id, review in sorted(self.claim_reviews.items()):
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertFalse(review["can_become_final"])
                self.assertIn("SECOND_REVIEW_PENDING", review["final_blocked_by"])


# ── locator ───────────────────────────────────────────────────────────────────


class TestLocators(ClosureCase):
    def test_every_locator_is_more_precise_than_the_pmid(self) -> None:
        self.assertTrue(self.locators)
        for row in self.locators:
            with self.subTest(locator_id=row["locator_id"]):
                self.assertFalse(row["pmid_only"])

    def test_every_supported_decision_carries_a_section_and_sentence(self) -> None:
        for row in self.locators:
            if row["locator_status"] != "sufficient":
                continue
            with self.subTest(locator_id=row["locator_id"]):
                self.assertIsNotNone(row["section"])
                self.assertIsNotNone(row["abstract_sentence"])

    def test_the_insufficient_locators_are_declared_not_hidden(self) -> None:
        statuses = {row["locator_status"] for row in self.locators}
        self.assertTrue(statuses <= {"sufficient", "insufficient"})
        self.assertEqual(
            self.review_347["locator_status"],
            "sufficient_for_rejection_insufficient_for_claim",
        )


# ── packet ciechi ─────────────────────────────────────────────────────────────


class TestSecondReviewPackets(ClosureCase):
    def packets(self) -> dict[str, dict]:
        directory = OUT / "second_review_packets"
        return {p.name: load_json(p) for p in sorted(directory.iterdir())}

    def test_three_packets_exist(self) -> None:
        self.assertEqual(
            sorted(self.packets()),
            ["SR-evidence-1846.json", "SR-evidence-1847.json", "SR-evidence-347.json"],
        )

    def test_the_packets_are_blind_to_the_first_reviewer_decision(self) -> None:
        for name, packet in sorted(self.packets().items()):
            with self.subTest(packet=name):
                self.assertTrue(packet["blind"])
                self.assertFalse(packet["first_reviewer_decision_included"])
                self.assertFalse(packet["recommendation_included"])
                for field in BLINDED_FIELDS:
                    self.assertNotIn(field, packet)

    def test_no_decision_leaks_outside_the_allowed_vocabulary(self) -> None:
        """La parola `requires_narrowing` puo' comparire solo come voce di vocabolario."""
        for name, packet in sorted(self.packets().items()):
            stripped = {k: v for k, v in packet.items() if k != "allowed_decisions"}
            blob = json.dumps(stripped, ensure_ascii=False)
            with self.subTest(packet=name):
                for leak in (
                    "requires_narrowing",
                    "Intrahepatic",
                    "prognostic_direction_rejected",
                    "first_review_complete",
                    "PREVALENCE_AGGREGATE_ONLY",
                ):
                    self.assertNotIn(leak, blob)

    def test_the_packets_carry_the_material_and_the_questions(self) -> None:
        for name, packet in sorted(self.packets().items()):
            with self.subTest(packet=name):
                self.assertTrue(packet["abstract_sections"])
                self.assertTrue(packet["questions_to_answer"])
                self.assertTrue(packet["allowed_decisions"])
                self.assertTrue(packet["material_sha256"])
                self.assertEqual(packet["source_access_status"], "full_text_unavailable")

    def test_the_two_diagnostic_packets_do_not_reference_each_other(self) -> None:
        packets = self.packets()
        first = json.dumps(packets["SR-evidence-1846.json"], ensure_ascii=False)
        second = json.dumps(packets["SR-evidence-1847.json"], ensure_ascii=False)
        self.assertNotIn("evidence:1847", first)
        self.assertNotIn("evidence:1846", second)


# ── simulazione ───────────────────────────────────────────────────────────────


class TestSimulation(ClosureCase):
    def test_the_simulation_is_not_applied(self) -> None:
        self.assertFalse(self.simulation["applied"])
        self.assertFalse(self.simulation["shadow_repository_modified"])
        self.assertFalse(self.simulation["link_impact"]["executed"])
        self.assertFalse(self.simulation["view_impact"]["executed"])

    def test_evidence_347_remains_a_parent_without_claim(self) -> None:
        outcome = self.simulation["evidence_347"]
        self.assertEqual(outcome["outcome"], "remains_parent_without_claim")
        self.assertIsNone(outcome["claim_proposal"])
        self.assertTrue(outcome["full_text_blocker_retained"])
        self.assertFalse(outcome["legacy_statement_status_changes"])

    def test_the_derived_counts_follow_from_the_decisions(self) -> None:
        counts = self.simulation["derived_counts"]
        diagnostic = self.simulation["diagnostic_claims"]
        self.assertEqual(counts["claims_to_modify"], diagnostic["requires_narrowing"])
        self.assertEqual(counts["claims_confirmed_as_is"], diagnostic["confirmed"])
        self.assertEqual(
            counts["claims_to_retire"],
            diagnostic["rejected"] + diagnostic["identity_affected_by_narrowing"],
        )
        # Il totale non cambia: ogni claim ristretto sostituisce se stesso.
        self.assertEqual(
            counts["evidence_claims_total_after"],
            self.simulation["current_state"]["evidence_claims_total"],
        )

    def test_narrowing_the_disease_scope_changes_the_claim_id(self) -> None:
        for detail in self.simulation["diagnostic_claims"]["details"]:
            with self.subTest(graph_evidence_id=detail["graph_evidence_id"]):
                self.assertTrue(detail["claim_id_would_change"])

    def test_corpus_promotion_stays_false_in_the_simulation(self) -> None:
        readiness = self.simulation["repository_1_1_readiness_after_review"]
        self.assertFalse(readiness["corpus_promotion_ready"])
        self.assertTrue(readiness["revision_required"])


# ── artefatti, determinismo, integrita' ───────────────────────────────────────


class TestArtifacts(ClosureCase):
    def test_all_declared_artifacts_exist(self) -> None:
        expected = {
            "review_scope.json",
            "source_access_inventory.jsonl",
            "source_file_hashes.json",
            "evidence_347_source_review.json",
            "evidence_347_claim_proposal.json",
            "pmid_24122810_source_unit_review.json",
            "diagnostic_claim_reviews.jsonl",
            "locator_audit.jsonl",
            "source_limitations.jsonl",
            "shadow_update_simulation.json",
            "review_manifest.json",
            "EVIDENCE_347_SOURCE_REVIEW.md",
            "PMID_24122810_DIAGNOSTIC_REVIEW.md",
            "NON_THERAPEUTIC_SOURCE_CLOSURE.md",
            "SOURCE_CLOSURE_READINESS.md",
        }
        for name in sorted(expected):
            with self.subTest(artifact=name):
                self.assertTrue((OUT / name).exists())
        self.assertTrue((OUT / "second_review_packets").is_dir())

    def test_two_generations_are_byte_identical(self) -> None:
        self.assertEqual(build(), self.artifacts)

    def test_reversing_the_input_order_changes_nothing(self) -> None:
        self.assertEqual(build(reverse=True), self.artifacts)

    def test_the_files_on_disk_match_the_regenerated_content(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            with self.subTest(artifact=name):
                self.assertEqual((OUT / name).read_text(encoding="utf-8"), text)

    def test_the_manifest_hashes_match(self) -> None:
        for name, expected in self.manifest["artifact_sha256"].items():
            digest = hashlib.sha256(
                (OUT / name).read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            with self.subTest(artifact=name):
                self.assertEqual(digest, expected)

    def test_no_machine_specific_path_leaks(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            lowered = text.lower()
            with self.subTest(artifact=name):
                for fragment in ("c:\\", "/users/", "/home/", "appdata"):
                    self.assertNotIn(fragment, lowered)

    def test_the_manifest_declares_nothing_was_modified(self) -> None:
        for flag, value in sorted(self.manifest["invariants"].items()):
            with self.subTest(flag=flag):
                self.assertFalse(value)


class TestUpstreamUnchanged(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scope = PhaseScope(
            REPO_ROOT.parent,
            START_SHA,
            PHASE_END_SHA,
            (
                "benchmarks/mtb_evidence/v3/non_therapeutic_source_closure/",
                "benchmarks/mtb_evidence/evaluation/scripts/build_non_therapeutic_source_closure.py",
                "benchmarks/mtb_evidence/evaluation/data/source_closure_v1.json",
                "backend/tests/test_non_therapeutic_source_closure.py",
            ),
        )
        cls.changed = cls.scope.changed_paths()

    def test_no_operational_artifact_was_modified(self) -> None:
        for path in FROZEN_OPERATIONAL_PATHS:
            with self.subTest(path=path):
                self.assertNotIn(path, self.changed)

    def test_neither_shadow_repository_was_modified(self) -> None:
        for path in sorted(self.changed):
            with self.subTest(path=path):
                self.assertNotIn("typed_claim_shadow_migration/", path)
                self.assertNotIn("non_therapeutic_shadow_update/", path)

    def test_no_frozen_scientific_artifact_was_modified(self) -> None:
        for path in sorted(self.changed):
            with self.subTest(path=path):
                for prefix in (
                    "multi_intervention_adjudication/",
                    "claim_type_retrieval_contract/",
                    "qualification_corpus_v2/",
                    "non_therapeutic_claim_contract_and_erratum/",
                    "priority_curation/",
                ):
                    self.assertNotIn(prefix, path)

    def test_the_branch_only_wrote_inside_its_own_perimeter(self) -> None:
        self.assertEqual(
            self.scope.violations(self.changed),
            [],
            "modifica fuori dal perimetro della chiusura documentale",
        )


class TestIsolation(unittest.TestCase):
    def source(self) -> Path:
        return (
            REPO_ROOT
            / "benchmarks/mtb_evidence/evaluation/scripts/build_non_therapeutic_source_closure.py"
        )

    def test_the_gold_is_never_read(self) -> None:
        blob = self.source().read_text(encoding="utf-8").lower()
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
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, blob)

    def test_the_generator_makes_no_network_call(self) -> None:
        """L'acquisizione e' avvenuta in revisione; la generazione e' offline."""
        imports = [
            line.strip()
            for line in self.source().read_text(encoding="utf-8").splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in imports:
            for fragment in ("requests", "httpx", "urllib", "socket", "subprocess"):
                with self.subTest(line=line, fragment=fragment):
                    self.assertNotIn(fragment, line)

    def test_no_operational_module_imports_this_review(self) -> None:
        evidence = REPO_ROOT / "backend/pipeline/evidence"
        for path in sorted(evidence.rglob("*.py")):
            imports = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            with self.subTest(module=str(path.relative_to(evidence))):
                for line in imports:
                    self.assertNotIn("source_closure", line)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
