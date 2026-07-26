"""Protegge cecita', provenienza e vincoli documentali della seconda revisione.

Tutti offline: leggono artefatti congelati e i packet ciechi, non aprono
connessioni, non toccano Neo4j e non chiamano LLM. Nessun test qui apre un
artefatto della prima revisione: la cecita' e' l'oggetto della verifica, non un
suo presupposto.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    AGGREGATE_CATEGORIES,
    BlindnessViolation,
    EXPECTED_PACKET_IDS,
    GROUP_DECISIONS,
    INTERVENTION_CATEGORIES,
    LocatorInsufficient,
    MATERIALIZABLE_CATEGORIES,
    MENTION_CATEGORIES,
    PENDING_DEVELOPMENT_CODE_MAPPINGS,
    ProhibitedInference,
    REGIMEN_CATEGORIES,
    ScopeMismatch,
    check_annotation,
    check_group_decision,
    check_no_pending_mapping_promoted,
    check_packet_scope,
    is_denied,
    locator_is_sufficient,
    sha256_bytes,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_second_review_artifacts import build

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW = REPO_ROOT / "benchmarks/mtb_evidence/v3/multi_intervention_second_review"
PACKETS = (
    REPO_ROOT
    / "benchmarks/mtb_evidence/v3/multi_intervention_source_review/second_review_packets"
)
START_SHA = "018bdfa7393c773722bb61755c4c5146a9ef98f9"
# La fase di seconda revisione si chiude qui. Il perimetro va misurato su questo
# intervallo chiuso e non contro l'albero di lavoro: le fasi successive vivono
# su discendenti di questo commit, e confrontarle con lo stato attuale farebbe
# fallire il test ogni volta che il lavoro prosegue, invece che quando questa
# fase ha scritto dove non doveva.
PHASE_END_SHA = "1e9d6b0d767ad3fac02e43d0186d948251b6349c"

# Cio' che questa fase non puo' aver toccato. Adapter, corpus, retriever e
# scoring restano fuori dal perimetro: la revisione e' documentale.
FROZEN_PATHS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/corpus_manifest.py",
    "backend/pipeline/evidence/corpus_regeneration.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/evaluation/scripts/run_v2_adapter.py",
    "benchmarks/mtb_evidence/evaluation/scripts/run_qualified_retriever_prototype.py",
)

# I prefissi entro cui il branch di seconda revisione puo' aver scritto.
ALLOWED_WRITE_PREFIXES = (
    "benchmarks/mtb_evidence/v3/multi_intervention_second_review/",
    "benchmarks/mtb_evidence/evaluation/multi_intervention_second_review.py",
    "benchmarks/mtb_evidence/evaluation/scripts/build_second_review_artifacts.py",
    "benchmarks/mtb_evidence/evaluation/data/second_review_",
    "backend/tests/test_multi_intervention_second_review.py",
)


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def annotation(**overrides) -> dict:
    """Un'annotazione valida minima, da deformare nei test dei guard."""
    payload = {
        "alias_status": "literal_match",
        "biomarker": "EGFR L858R",
        "blind_annotation_id": "MI-B-test",
        "claim_direction": "sensitivity",
        "claim_polarity": "supports",
        "classification": "directly_tested_with_separate_result",
        "confidence": "high",
        "disease": "Cancer",
        "evidence_setting": "clinical",
        "graph_evidence_id": "evidence:1",
        "intervention": "erlotinib",
        "is_current_statement_intervention": True,
        "locator": {"source_id": "PMID:1", "section": "abstract", "abstract_sentence": 3},
        "locator_status": "sufficient",
        "materialization": "parent_retained",
        "observed_direction": "sensitivity",
        "observed_polarity": "supports",
        "paraphrased_result": "esito",
        "population_model": "coorte",
        "reviewer_note": "nota",
        "source_access_status": "abstract_only",
        "source_id": "PMID:1",
        "source_literal_term": "erlotinib",
        "source_unit_id": "SU-1",
    }
    payload.update(overrides)
    return payload


class ArtifactCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.annotations = load_jsonl(REVIEW / "intervention_annotations_second.jsonl")
        cls.decisions = load_jsonl(REVIEW / "group_decisions_second.jsonl")
        cls.units = load_jsonl(REVIEW / "source_unit_annotations_second.jsonl")
        cls.lineage = load_jsonl(REVIEW / "claim_lineage_second.jsonl")
        cls.unresolved = load_jsonl(REVIEW / "unresolved_second.jsonl")
        cls.access_log = load_jsonl(REVIEW / "allowed_file_access_log.jsonl")
        cls.inventory = load_jsonl(REVIEW / "source_access_inventory.jsonl")
        cls.metadata = json.loads((REVIEW / "reviewer_metadata.json").read_text(encoding="utf-8"))
        cls.blindness = json.loads((REVIEW / "blindness_audit.json").read_text(encoding="utf-8"))
        cls.locators = json.loads((REVIEW / "locator_completeness.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads(
            (REVIEW / "second_review_manifest.json").read_text(encoding="utf-8")
        )
        cls.packet_hashes = json.loads((REVIEW / "packet_hashes.json").read_text(encoding="utf-8"))


# ── perimetro ─────────────────────────────────────────────────────────────────


class TestScope(ArtifactCase):
    def test_exactly_thirteen_packets_were_reviewed(self) -> None:
        self.assertEqual(len(self.decisions), 13)
        self.assertEqual(len(EXPECTED_PACKET_IDS), 13)
        reviewed = {row["blind_annotation_id"] for row in self.decisions}
        self.assertEqual(reviewed, set(EXPECTED_PACKET_IDS))

    def test_the_packet_directory_matches_the_declared_scope(self) -> None:
        found = sorted(path.stem for path in PACKETS.glob("MI-B-*.json"))
        self.assertEqual(found, sorted(EXPECTED_PACKET_IDS))
        check_packet_scope(found)

    def test_check_scope_rejects_a_missing_packet(self) -> None:
        with self.assertRaises(ScopeMismatch):
            check_packet_scope(list(EXPECTED_PACKET_IDS)[:-1])

    def test_every_candidate_intervention_is_classified(self) -> None:
        for path in sorted(PACKETS.glob("MI-B-*.json")):
            packet = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(packet=packet["blind_annotation_id"]):
                classified = {
                    row["intervention"]
                    for row in self.annotations
                    if row["blind_annotation_id"] == packet["blind_annotation_id"]
                }
                self.assertEqual(classified, set(packet["candidate_interventions"]))

    def test_every_classification_is_in_the_vocabulary(self) -> None:
        for row in self.annotations:
            with self.subTest(row=row["blind_annotation_id"], drug=row["intervention"]):
                self.assertIn(row["classification"], INTERVENTION_CATEGORIES)

    def test_every_decision_is_in_the_vocabulary(self) -> None:
        for row in self.decisions:
            self.assertIn(row["decision"], GROUP_DECISIONS)

    def test_every_group_has_exactly_one_decision(self) -> None:
        ids = [row["blind_annotation_id"] for row in self.decisions]
        self.assertEqual(len(ids), len(set(ids)))


# ── provenienza ───────────────────────────────────────────────────────────────


class TestProvenance(ArtifactCase):
    def test_every_classification_is_bound_to_a_source_unit(self) -> None:
        known = {row["source_unit_id"] for row in self.units}
        for row in self.annotations:
            with self.subTest(drug=row["intervention"]):
                self.assertTrue(row["source_unit_id"])
                self.assertIn(row["source_unit_id"], known)

    def test_no_locator_is_the_source_identifier_alone(self) -> None:
        for row in self.annotations:
            with self.subTest(drug=row["intervention"]):
                self.assertTrue(
                    locator_is_sufficient(row["locator"]),
                    "un locator col solo PMID non identifica il punto del risultato",
                )
        self.assertEqual(self.locators["locators_using_source_id_only"], 0)

    def test_every_locator_probe_is_verbatim_in_the_packet_source(self) -> None:
        texts = {
            json.loads(path.read_text(encoding="utf-8"))["blind_annotation_id"]: json.loads(
                path.read_text(encoding="utf-8")
            )["source_text"]
            for path in sorted(PACKETS.glob("MI-B-*.json"))
        }
        for row in self.annotations:
            source_text = texts[row["blind_annotation_id"]]
            for probe in row["locator"]["verbatim_probes"]:
                with self.subTest(drug=row["intervention"], probe=probe[:40]):
                    self.assertIn(probe, source_text)

    def test_the_packet_embedded_text_matches_its_declared_hash(self) -> None:
        for row in self.inventory:
            if row["source_access_status"] != "abstract_only":
                continue
            with self.subTest(source=row["source_id"]):
                self.assertTrue(row["verification"]["abstract_hash_matches_embedded_text"])

    def test_the_full_text_source_is_verified_against_the_file(self) -> None:
        full = [row for row in self.inventory if row["source_access_status"] == "full_text"]
        self.assertEqual(len(full), 1)
        self.assertTrue(full[0]["verification"]["full_text_file_verified"])
        self.assertTrue(full[0]["verification"]["excerpt_verbatim_in_full_text"])

    def test_the_abstract_cache_was_never_opened(self) -> None:
        for row in self.inventory:
            self.assertFalse(row["abstract_cache_opened"])

    def test_lineage_covers_every_association(self) -> None:
        self.assertEqual(len(self.lineage), len(self.annotations))
        pairs = {(row["blind_annotation_id"], row["intervention"]) for row in self.lineage}
        self.assertEqual(
            pairs, {(row["blind_annotation_id"], row["intervention"]) for row in self.annotations}
        )

    def test_lineage_records_a_blocking_reason_for_everything_not_materialized(self) -> None:
        for row in self.lineage:
            with self.subTest(lineage=row["lineage_id"]):
                if row["proposed_materialization"] == "not_materialized":
                    self.assertTrue(row["blocking_reason"])
                else:
                    self.assertIsNone(row["blocking_reason"])


# ── vincoli documentali ───────────────────────────────────────────────────────


class TestDocumentaryConstraints(ArtifactCase):
    def children(self) -> list[dict]:
        return [row for row in self.annotations if row["materialization"] == "child_claim_proposed"]

    def test_every_proposed_child_has_a_sufficient_locator(self) -> None:
        children = self.children()
        self.assertTrue(children)
        for row in children:
            with self.subTest(drug=row["intervention"]):
                self.assertEqual(row["locator_status"], "sufficient")
                self.assertTrue(locator_is_sufficient(row["locator"]))
        self.assertTrue(self.locators["every_proposed_child_has_sufficient_locator"])

    def test_no_aggregate_result_became_a_specific_claim(self) -> None:
        for row in self.children():
            with self.subTest(drug=row["intervention"]):
                self.assertNotIn(row["classification"], AGGREGATE_CATEGORIES)

    def test_no_regimen_was_split_into_components(self) -> None:
        for row in self.children():
            with self.subTest(drug=row["intervention"]):
                self.assertNotIn(row["classification"], REGIMEN_CATEGORIES)

    def test_no_mention_or_prior_therapy_became_a_claim(self) -> None:
        for row in self.children():
            with self.subTest(drug=row["intervention"]):
                self.assertNotIn(row["classification"], MENTION_CATEGORIES)

    def test_every_child_comes_from_a_materializable_category(self) -> None:
        for row in self.children():
            self.assertIn(row["classification"], MATERIALIZABLE_CATEGORIES)

    def test_pending_development_code_mappings_were_not_promoted(self) -> None:
        check_no_pending_mapping_promoted(self.annotations)
        codes = {code.upper() for code, _ in PENDING_DEVELOPMENT_CODE_MAPPINGS}
        pending = [
            row
            for row in self.annotations
            if str(row["source_literal_term"] or "").upper() in codes
        ]
        self.assertTrue(pending, "i packet contengono codici di sviluppo da proteggere")
        for row in pending:
            with self.subTest(drug=row["intervention"]):
                self.assertEqual(row["classification"], "possible_alias_not_verified")
                self.assertEqual(row["alias_status"], "pending_not_verified")
                self.assertNotEqual(row["materialization"], "child_claim_proposed")

    def test_no_verified_alias_merge_was_declared(self) -> None:
        self.assertEqual(self.manifest["summary"]["verified_alias_merges"], 0)
        for row in self.decisions:
            self.assertNotEqual(row["decision"], "verified_alias_merge")

    def test_clinical_and_preclinical_stay_separated(self) -> None:
        for row in self.annotations:
            with self.subTest(drug=row["intervention"]):
                self.assertIn(row["evidence_setting"], ("clinical", "preclinical"))
        for unit in self.units:
            settings = {
                row["evidence_setting"]
                for row in self.annotations
                if row["source_unit_id"] == unit["source_unit_id"]
            }
            with self.subTest(unit=unit["source_unit_id"]):
                self.assertEqual(len(settings), 1, "un'unita' documentale non puo' essere mista")

    def test_no_preclinical_result_became_a_clinical_child(self) -> None:
        for row in self.children():
            if row["evidence_setting"] != "preclinical":
                continue
            self.assertEqual(
                row["claim_direction"],
                row["observed_direction"],
                "un figlio preclinico non puo' cambiare direzione",
            )

    def test_negative_evidence_is_preserved(self) -> None:
        resistance = [row for row in self.annotations if row["claim_direction"] == "resistance"]
        self.assertTrue(resistance)
        for row in resistance:
            with self.subTest(drug=row["intervention"]):
                self.assertEqual(row["claim_polarity"], "supports")
                if row["materialization"] == "child_claim_proposed":
                    self.assertEqual(row["observed_direction"], "resistance")
                    self.assertEqual(row["observed_polarity"], "supports")

    def test_a_child_never_flips_the_direction_of_its_claim(self) -> None:
        for row in self.children():
            with self.subTest(drug=row["intervention"]):
                self.assertEqual(row["observed_direction"], row["claim_direction"])
                self.assertEqual(row["observed_polarity"], row["claim_polarity"])

    def test_decisions_without_children_really_have_none(self) -> None:
        no_child = {
            "aggregate_parent_only",
            "combination_regimen_required",
            "should_not_materialize_missing_interventions",
            "insufficient_for_atomicity_decision",
        }
        for row in self.decisions:
            if row["decision"] in no_child:
                with self.subTest(group=row["blind_annotation_id"]):
                    self.assertEqual(row["proposed_child_claim_count"], 0)

    def test_the_group_decisions_still_pass_their_own_guard(self) -> None:
        for row in self.decisions:
            members = [
                item
                for item in self.annotations
                if item["blind_annotation_id"] == row["blind_annotation_id"]
            ]
            with self.subTest(group=row["blind_annotation_id"]):
                check_group_decision(row["decision"], members)

    def test_the_count_difference_between_results_and_children_is_explained(self) -> None:
        summary = self.manifest["summary"]
        self.assertEqual(
            summary["intervention_specific_results"],
            summary["separate_results_on_parent_intervention"]
            + summary["unique_proposed_child_claims"],
            "ogni risultato separato o raffina il parent o diventa un figlio",
        )
        report = (REVIEW / "MULTI_INTERVENTION_SECOND_REVIEW.md").read_text(encoding="utf-8")
        self.assertIn("Risultati separati contro figli proposti", report)


# ── guardie del vocabolario ───────────────────────────────────────────────────


class TestGuards(unittest.TestCase):
    def test_a_bare_source_identifier_is_not_a_locator(self) -> None:
        self.assertFalse(locator_is_sufficient({"source_id": "PMID:1"}))
        self.assertTrue(locator_is_sufficient({"source_id": "PMID:1", "patient_id": "caso 1"}))

    def test_an_aggregate_result_cannot_become_a_child(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_annotation(
                annotation(
                    classification="directly_tested_in_shared_aggregate_result",
                    materialization="child_claim_proposed",
                )
            )

    def test_a_regimen_cannot_be_split_into_a_child(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_annotation(
                annotation(
                    classification="directly_tested_in_combination_regimen",
                    materialization="child_claim_proposed",
                )
            )

    def test_a_mention_cannot_become_a_child(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_annotation(
                annotation(
                    classification="mentioned_background_only",
                    materialization="child_claim_proposed",
                )
            )

    def test_a_class_member_cannot_become_a_child(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_annotation(
                annotation(
                    classification="drug_class_member_not_individually_tested",
                    materialization="child_claim_proposed",
                )
            )

    def test_a_pending_alias_cannot_become_a_child(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_annotation(
                annotation(
                    classification="possible_alias_not_verified",
                    alias_status="pending_not_verified",
                    materialization="child_claim_proposed",
                )
            )

    def test_a_pending_alias_cannot_be_declared_verified(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_annotation(
                annotation(
                    classification="possible_alias_not_verified", alias_status="verified_in_source"
                )
            )

    def test_a_development_code_cannot_be_promoted_to_its_generic_name(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_no_pending_mapping_promoted(
                [
                    annotation(
                        intervention="infigratinib",
                        source_literal_term="BGJ398",
                        alias_status="verified_in_source",
                    )
                ]
            )

    def test_a_child_cannot_flip_polarity(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_annotation(
                annotation(
                    materialization="child_claim_proposed",
                    observed_polarity="does_not_support",
                )
            )

    def test_a_child_needs_a_sufficient_locator(self) -> None:
        with self.assertRaises(LocatorInsufficient):
            check_annotation(
                annotation(
                    materialization="child_claim_proposed",
                    locator_status="insufficient_for_claim",
                )
            )

    def test_a_classification_without_a_source_unit_is_rejected(self) -> None:
        with self.assertRaises(ScopeMismatch):
            check_annotation(annotation(source_unit_id=""))

    def test_atomic_children_needs_every_locator_sufficient(self) -> None:
        rows = [
            annotation(),
            annotation(
                intervention="gefitinib",
                is_current_statement_intervention=False,
                materialization="child_claim_proposed",
                locator_status="sufficient",
            ),
            annotation(
                intervention="afatinib",
                is_current_statement_intervention=False,
                classification="insufficient_source_access",
                materialization="not_materialized",
                locator_status="insufficient_for_claim",
            ),
        ]
        with self.assertRaises(ProhibitedInference):
            check_group_decision("atomic_children_supported", rows)

    def test_a_no_child_decision_rejects_a_child(self) -> None:
        rows = [
            annotation(),
            annotation(
                intervention="gefitinib",
                is_current_statement_intervention=False,
                materialization="child_claim_proposed",
            ),
        ]
        with self.assertRaises(ProhibitedInference):
            check_group_decision("aggregate_parent_only", rows)

    def test_a_group_needs_exactly_one_retained_parent(self) -> None:
        with self.assertRaises(ScopeMismatch):
            check_group_decision("aggregate_parent_only", [annotation(), annotation()])


# ── cecita' ───────────────────────────────────────────────────────────────────


class TestBlindness(ArtifactCase):
    def test_the_access_log_contains_no_prohibited_path(self) -> None:
        self.assertTrue(self.access_log)
        for row in self.access_log:
            with self.subTest(path=row["logical_path"]):
                self.assertFalse(
                    is_denied(row["logical_path"]),
                    f"path vietato nel log di accesso: {row['logical_path']}",
                )

    def test_the_access_log_never_names_a_first_review_artifact(self) -> None:
        forbidden = (
            "group_atomicity_decisions",
            "intervention_level_annotations",
            "architectural_recommendation",
            "post_review_schema_simulation",
            "atomicity_decision_report",
            "adapter_migration_readiness",
        )
        blob = " ".join(row["logical_path"] for row in self.access_log).lower()
        for fragment in forbidden:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, blob)

    def test_gold_was_never_opened(self) -> None:
        blob = " ".join(row["logical_path"] for row in self.access_log).lower()
        self.assertNotIn("gold", blob)
        self.assertFalse(self.blindness["gold_accessed"])

    def test_no_retrieval_or_metric_result_was_opened(self) -> None:
        self.assertFalse(self.blindness["retrieval_or_metric_results_accessed"])
        blob = " ".join(row["logical_path"] for row in self.access_log).lower()
        for fragment in ("evaluation/results", "case_runs", "ablation"):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, blob)

    def test_the_denylist_actually_denies(self) -> None:
        for path in (
            "benchmarks/mtb_evidence/v3/multi_intervention_source_review/group_atomicity_decisions.jsonl",
            "benchmarks/mtb_evidence/v3/first_review/provisional_gold.jsonl",
            "ATOMICITY_DECISION_REPORT.md",
            "backend/tests/test_multi_intervention_source_review.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_denied(path))

    def test_the_access_log_raises_on_a_denied_path(self) -> None:
        from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import AccessLog

        log = AccessLog(REPO_ROOT)
        with self.assertRaises(BlindnessViolation):
            log.note(
                logical_path="benchmarks/x/architectural_recommendation.json",
                purpose="test",
                access_kind="read",
            )

    def test_the_review_module_does_not_import_the_first_review(self) -> None:
        for name in (
            "benchmarks/mtb_evidence/evaluation/multi_intervention_second_review.py",
            "benchmarks/mtb_evidence/evaluation/scripts/build_second_review_artifacts.py",
        ):
            source = (REPO_ROOT / name).read_text(encoding="utf-8")
            with self.subTest(module=name):
                self.assertNotIn("import multi_intervention_source_review", source)
                self.assertNotIn("from benchmarks.mtb_evidence.evaluation.scripts.multi_", source)

    def test_contamination_is_declared_rather_than_hidden(self) -> None:
        self.assertTrue(self.blindness["context_contamination"])
        self.assertFalse(self.blindness["blindness_violation"])
        self.assertEqual(self.blindness["prohibited_files_opened"], [])


# ── metadati e readiness ──────────────────────────────────────────────────────


class TestReviewerMetadata(ArtifactCase):
    def test_the_review_is_not_declared_independent(self) -> None:
        self.assertEqual(self.metadata["reviewer_role"], "blinded_replicate")
        self.assertEqual(
            self.metadata["review_independence"], "blinded_non_independent_replicate"
        )
        self.assertFalse(self.metadata["independent_review_valid"])
        self.assertTrue(self.metadata["context_contamination"])

    def test_nothing_becomes_final(self) -> None:
        self.assertEqual(self.metadata["review_status"], "second_review_complete")
        self.assertEqual(self.metadata["propagation_policy"], "prototype_only")
        self.assertFalse(self.metadata["hard_filterable"])
        self.assertFalse(self.metadata["final_evaluable"])
        for row in self.decisions:
            with self.subTest(group=row["blind_annotation_id"]):
                self.assertEqual(row["propagation_policy"], "prototype_only")
                self.assertFalse(row["hard_filterable"])
                self.assertFalse(row["final_evaluable"])

    def test_metadata_agrees_with_the_blindness_audit(self) -> None:
        self.assertEqual(
            self.metadata["blindness_violation"], self.blindness["blindness_violation"]
        )
        self.assertEqual(
            self.metadata["independent_review_valid"], self.manifest["readiness"]["independent_review_valid"]
        )

    def test_readiness_leaves_adjudication_and_migration_closed(self) -> None:
        readiness = self.manifest["readiness"]
        self.assertTrue(readiness["all_packets_reviewed"])
        self.assertTrue(readiness["all_interventions_classified"])
        self.assertTrue(readiness["locator_requirements_satisfied"])
        self.assertTrue(readiness["ready_for_inter_reviewer_comparison"])
        self.assertFalse(readiness["ready_for_adjudication"])
        self.assertFalse(readiness["ready_for_adapter_migration"])
        self.assertFalse(readiness["independent_review_valid"])

    def test_the_unresolved_group_is_the_one_marked_insufficient(self) -> None:
        insufficient = {
            row["blind_annotation_id"]
            for row in self.decisions
            if row["decision"] == "insufficient_for_atomicity_decision"
        }
        self.assertEqual(
            set(self.manifest["readiness"]["unresolved_groups_remaining"]), insufficient
        )

    def test_every_unresolved_entry_points_at_a_reviewed_group(self) -> None:
        reviewed = {row["blind_annotation_id"] for row in self.decisions}
        for row in self.unresolved:
            with self.subTest(entry=row["unresolved_id"]):
                self.assertIn(row["blind_annotation_id"], reviewed)
                self.assertIn(
                    row["severity"], ("blocking_decision", "flagged_for_adjudication")
                )

    def test_no_comparison_or_adjudication_artifact_was_produced(self) -> None:
        names = {path.name.lower() for path in REVIEW.iterdir()}
        for banned in ("consensus", "adjudication", "comparison", "agreement", "first_review"):
            with self.subTest(banned=banned):
                self.assertFalse(
                    [name for name in names if banned in name],
                    f"la fase non deve produrre artefatti di {banned}",
                )


# ── integrita' e determinismo ─────────────────────────────────────────────────


class TestIntegrity(ArtifactCase):
    def test_the_packets_are_unchanged(self) -> None:
        recorded = self.packet_hashes["packets"]
        self.assertEqual(len(recorded), 13)
        for packet_id, entry in recorded.items():
            path = PACKETS / f"{packet_id}.json"
            with self.subTest(packet=packet_id):
                self.assertEqual(sha256_bytes(path.read_bytes()), entry["sha256"])

    def test_the_aggregate_packet_hash_matches_the_recorded_one(self) -> None:
        from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
            aggregate_hash,
        )

        pairs = [
            (path.stem, sha256_bytes(path.read_bytes()))
            for path in sorted(PACKETS.glob("MI-B-*.json"))
        ]
        self.assertEqual(aggregate_hash(pairs), self.packet_hashes["aggregate_sha256"])

    def test_the_manifest_hashes_match_the_files_on_disk(self) -> None:
        for name, digest in self.manifest["artifact_sha256"].items():
            with self.subTest(artifact=name):
                content = (REVIEW / name).read_text(encoding="utf-8")
                self.assertEqual(hashlib.sha256(content.encode("utf-8")).hexdigest(), digest)

    def test_the_manifest_covers_every_artifact_except_itself(self) -> None:
        on_disk = {path.name for path in REVIEW.iterdir()} - {"second_review_manifest.json"}
        self.assertEqual(set(self.manifest["artifact_sha256"]), on_disk)

    def test_rebuilding_reproduces_the_committed_artifacts(self) -> None:
        rebuilt = build(REVIEW, reverse=False).files
        for name, content in rebuilt.items():
            with self.subTest(artifact=name):
                self.assertEqual(content, (REVIEW / name).read_text(encoding="utf-8"))

    def test_reversing_the_packet_order_changes_nothing(self) -> None:
        forward = build(REVIEW, reverse=False).files
        backward = build(REVIEW, reverse=True).files
        self.assertEqual(forward, backward)

    def test_the_build_is_byte_identical_when_written_twice(self) -> None:
        first = Path(tempfile.mkdtemp(prefix="sr2-a-"))
        second = Path(tempfile.mkdtemp(prefix="sr2-b-"))
        try:
            build(first, reverse=False).write(first)
            build(second, reverse=True).write(second)
            names = sorted(path.name for path in first.iterdir())
            self.assertEqual(names, sorted(path.name for path in second.iterdir()))
            for name in names:
                with self.subTest(artifact=name):
                    self.assertEqual(
                        (first / name).read_bytes(), (second / name).read_bytes()
                    )
        finally:
            shutil.rmtree(first, ignore_errors=True)
            shutil.rmtree(second, ignore_errors=True)


class TestUntouchedArtifacts(unittest.TestCase):
    """Adapter, corpus, retriever e scoring non appartengono a questa fase."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.scope = PhaseScope(
            REPO_ROOT.parent, START_SHA, PHASE_END_SHA, ALLOWED_WRITE_PREFIXES
        )
        cls.changed = cls.scope.changed_paths()

    def test_the_frozen_modules_were_not_modified(self) -> None:
        for path in FROZEN_PATHS:
            with self.subTest(path=path):
                self.assertNotIn(path, self.changed)

    def test_the_second_review_packets_were_not_modified(self) -> None:
        for path in self.changed:
            with self.subTest(path=path):
                self.assertNotIn("second_review_packets", path)

    def test_the_branch_only_wrote_inside_its_own_perimeter(self) -> None:
        self.assertEqual(
            self.scope.violations(self.changed),
            [],
            "modifica fuori dal perimetro della seconda revisione",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
