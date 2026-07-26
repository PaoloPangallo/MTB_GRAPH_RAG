"""Protegge perimetro, allineamento ed etichette di non-indipendenza del confronto.

Tutti offline: leggono artefatti congelati, non aprono connessioni, non toccano
Neo4j e non chiamano LLM. Nessun test qui apre il gold.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from benchmarks.mtb_evidence.evaluation.multi_intervention_review_comparison import (
    AlignmentError,
    CHILD_DIFFERENCE_REASONS,
    COMPARISON_VERDICTS,
    DISAGREEMENT_CAUSES,
    GUARDED_PHRASES,
    METHOD_LABELS,
    QUALIFIER,
    align,
    check_guarded_language,
    cohen_kappa,
    first_locator_granularity,
    group_key,
    intervention_key,
    normalize_intervention,
    qualifies_for_provisional_consensus,
    verdict_for,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_review_comparison_artifacts import build

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
COMPARISON = V3 / "multi_intervention_review_comparison"
FIRST = V3 / "multi_intervention_source_review"
REPLICATE = V3 / "multi_intervention_second_review"
START_SHA = "1e9d6b0d767ad3fac02e43d0186d948251b6349c"
# La fase di confronto si chiude qui. Come per la seconda revisione, il perimetro
# va misurato su un intervallo chiuso: confrontarlo con l'albero di lavoro lo
# farebbe fallire a ogni fase successiva invece che quando questa fase ha
# scritto dove non doveva.
PHASE_END_SHA = "3ef3e99a9ec0491aab37384f336e857ea08aa8a2"

FROZEN_PATHS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/corpus_manifest.py",
    "backend/pipeline/evidence/corpus_regeneration.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
)

ALLOWED_WRITE_PREFIXES = (
    "benchmarks/mtb_evidence/v3/multi_intervention_review_comparison/",
    "benchmarks/mtb_evidence/evaluation/multi_intervention_review_comparison.py",
    "benchmarks/mtb_evidence/evaluation/scripts/build_review_comparison_artifacts.py",
    "benchmarks/mtb_evidence/evaluation/data/review_comparison_",
    "backend/tests/test_multi_intervention_review_comparison.py",
    # Il test di perimetro della seconda revisione misurava il proprio intervallo
    # contro l'albero di lavoro invece che contro la fine della propria fase, e
    # sarebbe fallito a ogni fase successiva. Corretto qui, dove il difetto e'
    # emerso; le annotazioni della seconda revisione restano intatte.
    "backend/tests/test_multi_intervention_second_review.py",
)

# I mapping che devono restare distinti: fonderli cancellerebbe l'incertezza di
# identita' che entrambe le revisioni hanno registrato.
UNMERGEABLE_PAIRS = (("bgj398", "infigratinib"), ("auy922", "luminespib"))


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class ComparisonCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scope = json.loads((COMPARISON / "comparison_scope.json").read_text(encoding="utf-8"))
        cls.alignment = load_jsonl(COMPARISON / "review_alignment.jsonl")
        cls.interventions = load_jsonl(COMPARISON / "intervention_level_comparison.jsonl")
        cls.groups = load_jsonl(COMPARISON / "group_level_comparison.jsonl")
        cls.matrix = json.loads(
            (COMPARISON / "group_confusion_matrix.json").read_text(encoding="utf-8")
        )
        cls.metrics = json.loads(
            (COMPARISON / "descriptive_agreement_metrics.json").read_text(encoding="utf-8")
        )
        cls.locators = load_jsonl(COMPARISON / "locator_comparison.jsonl")
        cls.units = load_jsonl(COMPARISON / "source_unit_comparison.jsonl")
        cls.children = load_jsonl(COMPARISON / "child_claim_comparison.jsonl")
        cls.taxonomy = json.loads(
            (COMPARISON / "disagreement_taxonomy.json").read_text(encoding="utf-8")
        )
        cls.priority = load_jsonl(COMPARISON / "priority_case_analysis.jsonl")
        cls.consensus = load_jsonl(COMPARISON / "provisional_consensus_groups.jsonl")
        cls.required = load_jsonl(COMPARISON / "adjudication_required_groups.jsonl")
        cls.guidelines = load_jsonl(COMPARISON / "guideline_refinement_proposals.jsonl")
        cls.manifest = json.loads(
            (COMPARISON / "comparison_manifest.json").read_text(encoding="utf-8")
        )
        cls.packets = sorted((COMPARISON / "adjudication_packets").glob("ADJ-*.json"))


# ── perimetro e allineamento ──────────────────────────────────────────────────


class TestScope(ComparisonCase):
    def test_exactly_thirteen_groups_are_aligned(self) -> None:
        self.assertEqual(len(self.groups), 13)
        self.assertEqual(self.scope["scope_check"]["first_review_groups"], 13)
        self.assertEqual(self.scope["scope_check"]["replicate_groups"], 13)

    def test_exactly_twenty_eight_associations_are_aligned(self) -> None:
        self.assertEqual(len(self.interventions), 28)
        self.assertEqual(len(self.alignment), 28)
        self.assertEqual(self.scope["scope_check"]["first_review_associations"], 28)
        self.assertEqual(self.scope["scope_check"]["replicate_associations"], 28)

    def test_alignment_is_by_key_not_by_position(self) -> None:
        self.assertFalse(self.scope["alignment_keys"]["positional_alignment_used"])
        for row in self.alignment:
            with self.subTest(row=row["comparison_id"]):
                self.assertEqual(row["aligned_by"], "deterministic_key")

    def test_alignment_keys_are_unique(self) -> None:
        keys = {
            (row["graph_evidence_id"], row["source_id"], row["normalized_intervention"])
            for row in self.alignment
        }
        self.assertEqual(len(keys), 28)

    def test_align_rejects_a_missing_record(self) -> None:
        first = [{"graph_evidence_id": "e:1", "source_id": "PMID:1", "intervention": "a"}]
        with self.assertRaises(AlignmentError):
            align(first, [], intervention_key, label="test")

    def test_align_rejects_an_extra_record(self) -> None:
        rows = [{"graph_evidence_id": "e:1", "source_id": "PMID:1", "intervention": "a"}]
        extra = rows + [{"graph_evidence_id": "e:2", "source_id": "PMID:1", "intervention": "b"}]
        with self.assertRaises(AlignmentError):
            align(rows, extra, intervention_key, label="test")

    def test_group_key_reads_either_source_field(self) -> None:
        self.assertEqual(
            group_key({"graph_evidence_id": "e:1", "source_ids": ["PMID:9"]}), ("e:1", "PMID:9")
        )
        self.assertEqual(
            group_key({"graph_evidence_id": "e:1", "source_id": "PMID:9"}), ("e:1", "PMID:9")
        )

    def test_every_group_appears_in_both_reviews(self) -> None:
        first_ids = {row["graph_evidence_id"] for row in load_jsonl(FIRST / "group_atomicity_decisions.jsonl")}
        replicate = load_jsonl(REPLICATE / "group_decisions_second.jsonl")
        self.assertEqual(first_ids, {row["graph_evidence_id"] for row in replicate})


# ── annotazioni originali intatte ─────────────────────────────────────────────


class TestOriginalAnnotationsUntouched(ComparisonCase):
    def test_the_recorded_hashes_match_the_reviews_on_disk(self) -> None:
        for label, directory in (
            ("first_review", FIRST),
            ("blinded_replicate", REPLICATE),
        ):
            recorded = self.scope["input_hashes"][label]["files"]
            for name, digest in recorded.items():
                with self.subTest(review=label, artifact=name):
                    payload = (directory / name).read_bytes()
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)

    def test_the_second_review_packets_are_unchanged(self) -> None:
        recorded = self.scope["input_hashes"]["second_review_packets"]["files"]
        self.assertEqual(len(recorded), 13)
        for name, digest in recorded.items():
            path = FIRST / "second_review_packets" / name
            with self.subTest(packet=name):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_the_comparison_declares_it_modified_nothing(self) -> None:
        self.assertFalse(self.scope["original_annotations_modified"])
        self.assertFalse(self.scope["new_sources_read"])

    def test_the_frozen_artifacts_are_hashed_and_present(self) -> None:
        for path, digest in self.scope["input_hashes"]["frozen_artifacts"].items():
            with self.subTest(path=path):
                self.assertIsNotNone(digest, f"artefatto congelato mancante: {path}")
                self.assertEqual(
                    hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest(), digest
                )


# ── gold ──────────────────────────────────────────────────────────────────────


class TestGoldNeverUsed(ComparisonCase):
    def test_the_gold_is_hashed_but_never_read(self) -> None:
        self.assertFalse(self.scope["gold_content_read"])
        self.assertTrue(self.scope["gold_hashed_for_integrity_only"])
        self.assertTrue(self.scope["input_hashes"]["gold_artifacts"])

    def test_the_gold_appears_only_as_a_path_with_a_digest(self) -> None:
        """`comparison_scope.json` deve nominare il gold, ma solo per pesarlo.

        Registrarne gli hash e' richiesto per provare che non e' cambiato; il
        contenuto non deve comparire da nessuna parte. Il test distingue le due
        cose invece di vietare la parola.
        """
        entries = self.scope["input_hashes"]["gold_artifacts"]
        self.assertTrue(entries)
        for path, value in entries.items():
            with self.subTest(path=path):
                self.assertRegex(value, r"^[0-9a-f]{64}$")
        blob = json.dumps(self.scope, ensure_ascii=False)
        for path in entries:
            self.assertEqual(blob.count(path), 1, "il gold compare oltre alla riga di hash")

    def test_no_other_artifact_mentions_the_gold_or_retrieval_results(self) -> None:
        for path in sorted(COMPARISON.rglob("*")):
            if not path.is_file() or path.name == "comparison_scope.json":
                continue
            blob = path.read_text(encoding="utf-8").lower()
            with self.subTest(artifact=path.name):
                for fragment in ("provisional_gold", "clinical_gold", "snapshot_gold", "recall@", "ndcg"):
                    self.assertNotIn(fragment, blob)

    def test_no_adjudication_packet_carries_metrics_or_a_prefilled_decision(self) -> None:
        self.assertTrue(self.packets)
        for path in self.packets:
            payload = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(packet=path.name):
                self.assertIsNone(payload["prefilled_decision"])
                self.assertFalse(payload["gold_metrics_included"])
                self.assertFalse(payload["retrieval_results_included"])
                self.assertFalse(payload["recall_based_suggestions_included"])


# ── etichette di non-indipendenza ─────────────────────────────────────────────


class TestNonIndependenceLabels(ComparisonCase):
    def artifacts(self) -> list[Path]:
        return [path for path in sorted(COMPARISON.rglob("*.json*")) if path.is_file()]

    def test_every_structured_artifact_carries_the_method_labels(self) -> None:
        for path in self.artifacts():
            rows = (
                load_jsonl(path)
                if path.suffix == ".jsonl"
                else [json.loads(path.read_text(encoding="utf-8"))]
            )
            for row in rows:
                with self.subTest(artifact=path.name):
                    self.assertEqual(
                        row.get("comparison_type"),
                        "first_review_vs_blinded_non_independent_replicate",
                    )
                    self.assertFalse(row.get("independent_inter_reviewer_agreement"))
                    self.assertFalse(row.get("valid_for_external_reliability_claim"))
                    self.assertTrue(row.get("valid_for_adjudication_preparation"))

    def test_metrics_are_marked_descriptive_only(self) -> None:
        self.assertTrue(self.metrics["descriptive_only_due_to_non_independence"])
        for kappa in (
            self.metrics["group_level"]["kappa"],
            self.metrics["intervention_level"]["classification_kappa"],
            self.metrics["intervention_level"]["materialization_kappa"],
        ):
            with self.subTest(kappa=kappa.get("kappa")):
                self.assertTrue(kappa["computed"])
                self.assertFalse(kappa["interpretable"])
                self.assertTrue(kappa["descriptive_only_due_to_non_independence"])

    def test_sparse_kappa_is_flagged_as_sparse(self) -> None:
        for kappa in (
            self.metrics["group_level"]["kappa"],
            self.metrics["intervention_level"]["classification_kappa"],
        ):
            with self.subTest(n=kappa["n"]):
                self.assertTrue(kappa["sparse_categories"])
                self.assertLess(kappa["min_expected_cell_count"], 5)

    def test_reports_never_use_a_strong_phrase_unqualified(self) -> None:
        for path in sorted(COMPARISON.rglob("*.md")):
            offenders = check_guarded_language(path.read_text(encoding="utf-8"))
            with self.subTest(report=path.name):
                self.assertEqual(offenders, [], f"formulazione non qualificata in {path.name}")

    def test_the_language_guard_actually_catches_an_unqualified_phrase(self) -> None:
        self.assertTrue(check_guarded_language("this shows independent agreement"))
        self.assertFalse(
            check_guarded_language(f"independent agreement is impossible: {QUALIFIER}")
        )
        for phrase in GUARDED_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertTrue(check_guarded_language(f"we claim {phrase} here"))

    def test_independent_agreement_is_never_available(self) -> None:
        self.assertFalse(self.manifest["readiness"]["independent_agreement_available"])
        self.assertFalse(METHOD_LABELS["independent_inter_reviewer_agreement"])


# ── verdetti e cause ──────────────────────────────────────────────────────────


class TestVerdicts(ComparisonCase):
    def disagreements(self) -> list[dict]:
        return [
            row
            for row in self.interventions
            if row["verdict"] not in ("exact_agreement", "compatible_agreement")
        ]

    def test_every_verdict_is_in_the_vocabulary(self) -> None:
        for row in self.interventions:
            with self.subTest(row=row["comparison_id"]):
                self.assertIn(row["verdict"], COMPARISON_VERDICTS)

    def test_every_disagreement_has_a_primary_cause(self) -> None:
        disagreements = self.disagreements()
        self.assertTrue(disagreements)
        for row in disagreements:
            with self.subTest(row=row["comparison_id"]):
                self.assertIn(row["primary_cause"], DISAGREEMENT_CAUSES)

    def test_every_compatible_agreement_also_records_its_cause(self) -> None:
        for row in self.interventions:
            if row["verdict"] == "compatible_agreement":
                with self.subTest(row=row["comparison_id"]):
                    self.assertIn(row["primary_cause"], DISAGREEMENT_CAUSES)

    def test_secondary_causes_are_in_the_vocabulary(self) -> None:
        for row in self.interventions:
            for cause in row["secondary_causes"]:
                with self.subTest(row=row["comparison_id"], cause=cause):
                    self.assertIn(cause, DISAGREEMENT_CAUSES)

    def test_exact_agreement_means_agreement_on_both_axes(self) -> None:
        for row in self.interventions:
            if row["verdict"] == "exact_agreement":
                with self.subTest(row=row["comparison_id"]):
                    self.assertTrue(row["classification_match"])
                    self.assertTrue(row["materialization_match"])

    def test_materialization_disagreement_means_same_reading_different_outcome(self) -> None:
        rows = [
            row for row in self.interventions if row["verdict"] == "materialization_disagreement"
        ]
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(row=row["comparison_id"]):
                self.assertTrue(row["classification_match"])
                self.assertFalse(row["materialization_match"])

    def test_verdict_precedence_is_stable(self) -> None:
        common = {
            "first_locator_insufficient": False,
            "replicate_locator_insufficient": False,
        }
        self.assertEqual(
            verdict_for(
                first_classification="x",
                replicate_classification="x",
                first_outcome="no_claim",
                replicate_outcome="no_claim",
                **common,
            ),
            "exact_agreement",
        )
        self.assertEqual(
            verdict_for(
                first_classification="x",
                replicate_classification="x",
                first_outcome="claim_via_new_child",
                replicate_outcome="claim_via_existing_parent",
                **common,
            ),
            "materialization_disagreement",
        )
        self.assertEqual(
            verdict_for(
                first_classification="directly_tested_with_separate_result",
                replicate_classification="insufficient_source_access",
                first_outcome="no_claim",
                replicate_outcome="no_claim",
                **common,
            ),
            "compatible_agreement",
        )
        self.assertEqual(
            verdict_for(
                first_classification="a",
                replicate_classification="b",
                first_outcome="no_claim",
                replicate_outcome="no_claim",
                **common,
            ),
            "documentary_role_disagreement",
        )

    def test_the_taxonomy_covers_every_recorded_cause(self) -> None:
        recorded = {row["primary_cause"] for row in self.taxonomy["records"]}
        self.assertTrue(recorded)
        self.assertTrue(recorded.issubset(set(DISAGREEMENT_CAUSES)))
        self.assertEqual(
            sum(self.taxonomy["primary_cause_counts"].values()), len(self.taxonomy["records"])
        )


# ── mapping pending ───────────────────────────────────────────────────────────


class TestPendingMappings(ComparisonCase):
    def test_development_codes_are_never_merged_into_generic_names(self) -> None:
        for code, generic in UNMERGEABLE_PAIRS:
            with self.subTest(pair=(code, generic)):
                self.assertNotEqual(normalize_intervention(code), normalize_intervention(generic))

    def test_normalization_only_touches_case_and_whitespace(self) -> None:
        self.assertEqual(normalize_intervention("  Alectinib   Hydrochloride "), "alectinib hydrochloride")
        self.assertNotEqual(
            normalize_intervention("alectinib hydrochloride"), normalize_intervention("alectinib")
        )

    def test_pending_mappings_stay_unmaterialized_in_both_reviews(self) -> None:
        pending = [row for row in self.interventions if row["pending_mapping"]]
        self.assertTrue(pending)
        for row in pending:
            with self.subTest(row=row["comparison_id"]):
                self.assertNotEqual(row["first_claim_outcome"], "claim_via_new_child")
                self.assertNotEqual(row["replicate_claim_outcome"], "claim_via_new_child")

    def test_a_group_with_a_pending_mapping_never_reaches_provisional_consensus(self) -> None:
        for row in self.groups:
            if row["pending_mapping_present"]:
                with self.subTest(group=row["graph_evidence_id"]):
                    self.assertFalse(row["provisional_consensus"])
                    self.assertTrue(row["adjudication_required"])


# ── child claim ───────────────────────────────────────────────────────────────


class TestChildClaims(ComparisonCase):
    def test_every_association_has_a_child_status(self) -> None:
        self.assertEqual(len(self.children), 28)
        statuses = {row["child_status"] for row in self.children}
        self.assertTrue(
            statuses.issubset(
                {
                    "proposed_by_both",
                    "proposed_by_first_only",
                    "proposed_by_replicate_only",
                    "proposed_by_neither",
                }
            )
        )

    def test_the_child_counts_match_the_two_reviews(self) -> None:
        first = sum(
            1
            for row in self.children
            if row["child_status"] in ("proposed_by_both", "proposed_by_first_only")
        )
        replicate = sum(
            1
            for row in self.children
            if row["child_status"] in ("proposed_by_both", "proposed_by_replicate_only")
        )
        simulation = json.loads(
            (FIRST / "post_review_schema_simulation.json").read_text(encoding="utf-8")
        )
        self.assertEqual(first, simulation["simulated_child_statement_count"])
        replicate_rows = load_jsonl(REPLICATE / "intervention_annotations_second.jsonl")
        self.assertEqual(
            replicate,
            sum(1 for row in replicate_rows if row["materialization"] == "child_claim_proposed"),
        )

    def test_children_only_in_the_first_review_are_all_parent_interventions(self) -> None:
        rows = [row for row in self.children if row["child_status"] == "proposed_by_first_only"]
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(row=row["comparison_id"]):
                self.assertTrue(row["is_parent_intervention"])
                self.assertEqual(
                    row["difference_reason"], "parent_intervention_already_represents_result"
                )

    def test_every_child_difference_reason_is_in_the_vocabulary(self) -> None:
        for row in self.children:
            if row["difference_reason"] is None:
                continue
            with self.subTest(row=row["comparison_id"]):
                self.assertIn(row["difference_reason"], CHILD_DIFFERENCE_REASONS)

    def test_children_agreed_by_both_share_the_documentary_reading(self) -> None:
        for row in self.children:
            if row["child_status"] == "proposed_by_both":
                with self.subTest(row=row["comparison_id"]):
                    self.assertTrue(row["documentary_result_agreement"])


# ── consenso, packet, linee guida ─────────────────────────────────────────────


class TestAdjudicationPreparation(ComparisonCase):
    def test_every_group_is_either_consensus_or_adjudication_required(self) -> None:
        for row in self.groups:
            with self.subTest(group=row["graph_evidence_id"]):
                self.assertNotEqual(row["provisional_consensus"], row["adjudication_required"])
        self.assertEqual(len(self.consensus) + len(self.required), 13)

    def test_every_disagreeing_group_has_a_packet(self) -> None:
        disagreeing = {
            row["graph_evidence_id"] for row in self.groups if not row["decision_match"]
        }
        packet_ids = {json.loads(p.read_text(encoding="utf-8"))["graph_evidence_id"] for p in self.packets}
        self.assertTrue(disagreeing.issubset(packet_ids))

    def test_every_required_group_has_a_packet(self) -> None:
        required = {row["graph_evidence_id"] for row in self.required}
        packet_ids = {json.loads(p.read_text(encoding="utf-8"))["graph_evidence_id"] for p in self.packets}
        self.assertEqual(required, packet_ids)
        self.assertEqual(len(self.packets), len(self.required))

    def test_every_packet_carries_both_decisions_and_questions(self) -> None:
        for path in self.packets:
            payload = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(packet=path.name):
                for field in (
                    "first_review_decision",
                    "first_review_rationale",
                    "replicate_decision",
                    "replicate_rationale",
                    "biomarker",
                    "disease",
                    "available_source_text",
                    "possible_schema_impact",
                ):
                    self.assertTrue(payload[field], f"{field} vuoto")
                self.assertTrue(payload["adjudicator_questions"])
                self.assertTrue(payload["intervention_level_detail"])
                for question in payload["adjudicator_questions"]:
                    self.assertIn(question["kind"], ("binary", "categorial"))
                    self.assertGreaterEqual(len(question["options"]), 2)

    def test_provisional_consensus_stays_prototype_only(self) -> None:
        for row in self.consensus:
            with self.subTest(group=row["graph_evidence_id"]):
                self.assertEqual(row["propagation_policy"], "prototype_only")
                self.assertFalse(row["final"])
                self.assertFalse(row["hard_filterable"])
                self.assertFalse(row["independently_validated"])
                self.assertFalse(row["corpus_modified"])

    def test_the_consensus_rule_rejects_any_single_defect(self) -> None:
        clean = {
            "same_group_decision": True,
            "intervention_verdicts": ["exact_agreement"],
            "locator_sufficient": True,
            "pending_mapping_present": False,
            "aggregate_to_specific_risk": False,
            "scope_issue_present": False,
        }
        self.assertTrue(qualifies_for_provisional_consensus(**clean))
        for field, value in (
            ("same_group_decision", False),
            ("locator_sufficient", False),
            ("pending_mapping_present", True),
            ("aggregate_to_specific_risk", True),
            ("scope_issue_present", True),
        ):
            with self.subTest(field=field):
                self.assertFalse(qualifies_for_provisional_consensus(**{**clean, field: value}))
        self.assertFalse(
            qualifies_for_provisional_consensus(
                **{**clean, "intervention_verdicts": ["materialization_disagreement"]}
            )
        )

    def test_the_priority_cases_cover_the_required_groups(self) -> None:
        covered = {row["graph_evidence_id"] for row in self.priority}
        for required in ("evidence:275", "evidence:4759", "evidence:3811", "evidence:841"):
            with self.subTest(group=required):
                self.assertIn(required, covered)
        regimen_or_mixed = {
            row["graph_evidence_id"]
            for row in self.groups
            if {row["first_decision"], row["replicate_decision"]}
            & {"combination_regimen_required", "mixed_parent_and_children"}
        }
        self.assertTrue(regimen_or_mixed.issubset(covered))

    def test_every_priority_case_states_a_question_for_the_adjudicator(self) -> None:
        for row in self.priority:
            with self.subTest(case=row["case_id"]):
                self.assertTrue(row["adjudicator_question"])
                self.assertIn(row["misattribution_risk"], ("low", "medium", "high"))

    def test_guideline_proposals_are_not_applied_retroactively(self) -> None:
        self.assertTrue(self.guidelines)
        for row in self.guidelines:
            with self.subTest(proposal=row["proposal_id"]):
                self.assertFalse(row["retroactive_application"])
                self.assertIn(row["root_cause"], DISAGREEMENT_CAUSES)
                self.assertTrue(row["proposed_clarification"])

    def test_no_adjudication_decision_was_recorded(self) -> None:
        names = {path.name.lower() for path in COMPARISON.rglob("*") if path.is_file()}
        for banned in ("adjudication_result", "adjudicated", "final_decision", "consensus_final"):
            with self.subTest(banned=banned):
                self.assertFalse([name for name in names if banned in name])


# ── determinismo e simmetria ──────────────────────────────────────────────────


class TestDeterminism(ComparisonCase):
    def test_rebuilding_reproduces_the_committed_artifacts(self) -> None:
        rebuilt = build(swap=False)
        for name, content in rebuilt.items():
            with self.subTest(artifact=name):
                self.assertEqual(content, (COMPARISON / name).read_text(encoding="utf-8"))

    def test_the_build_is_byte_identical_twice(self) -> None:
        self.assertEqual(build(swap=False), build(swap=False))

    def test_swapping_the_review_order_leaves_symmetric_results_unchanged(self) -> None:
        forward, swapped = build(swap=False), build(swap=True)
        self.assertEqual(
            forward["descriptive_agreement_metrics.json"],
            swapped["descriptive_agreement_metrics.json"],
        )
        self.assertEqual(
            forward["group_level_comparison.jsonl"], swapped["group_level_comparison.jsonl"]
        )
        self.assertEqual(
            {name for name in forward if name.startswith("adjudication_packets/")},
            {name for name in swapped if name.startswith("adjudication_packets/")},
        )

    def test_swapping_transposes_the_confusion_matrix(self) -> None:
        forward = json.loads(build(swap=False)["group_confusion_matrix.json"])
        swapped = json.loads(build(swap=True)["group_confusion_matrix.json"])
        self.assertEqual(forward["rows"], swapped["columns"])
        for first, cells in forward["matrix"].items():
            for second, count in cells.items():
                with self.subTest(cell=(first, second)):
                    self.assertEqual(count, swapped["matrix"][second][first])

    def test_the_matrix_totals_the_thirteen_groups(self) -> None:
        self.assertEqual(self.matrix["total"], 13)

    def test_the_manifest_hashes_match_the_files_on_disk(self) -> None:
        for name, digest in self.manifest["artifact_sha256"].items():
            with self.subTest(artifact=name):
                content = (COMPARISON / name).read_text(encoding="utf-8")
                self.assertEqual(hashlib.sha256(content.encode("utf-8")).hexdigest(), digest)

    def test_kappa_declines_when_a_single_category_is_used(self) -> None:
        result = cohen_kappa([("a", "a"), ("a", "a")])
        self.assertFalse(result["computed"])
        self.assertIn("una sola categoria", result["reason"])

    def test_locator_granularity_ignores_section_labels(self) -> None:
        self.assertEqual(
            first_locator_granularity("abstract#PATIENTS AND METHODS; abstract#RESULTS"), "section"
        )
        self.assertEqual(
            first_locator_granularity("abstract#UNLABELLED, FGFR2-TACC3 patient, pazopanib sentence"),
            "sub_document_unit",
        )
        self.assertEqual(
            first_locator_granularity("full_text#Case Report; Figure 1A and 1E"),
            "sub_document_unit",
        )


class TestUntouchedArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("git") is None:
            raise unittest.SkipTest("git non disponibile")
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", START_SHA, PHASE_END_SHA],
                cwd=REPO_ROOT.parent,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:  # pragma: no cover
            raise unittest.SkipTest(f"git non utilizzabile: {error}")
        if result.returncode != 0:
            raise unittest.SkipTest("lo SHA di partenza non e' raggiungibile in questo checkout")
        cls.changed = {
            line.strip().removeprefix("mtb-graphrag/")
            for line in result.stdout.splitlines()
            if line.strip()
        }

    def test_adapter_corpus_retriever_and_scoring_are_unchanged(self) -> None:
        for path in FROZEN_PATHS:
            with self.subTest(path=path):
                self.assertNotIn(path, self.changed)

    def test_neither_review_was_modified(self) -> None:
        for path in sorted(self.changed):
            with self.subTest(path=path):
                self.assertNotIn("multi_intervention_source_review/", path)
                self.assertNotIn("multi_intervention_second_review/", path)

    def test_the_branch_only_wrote_inside_the_comparison_perimeter(self) -> None:
        for path in sorted(self.changed):
            with self.subTest(path=path):
                self.assertTrue(
                    any(path.startswith(prefix) for prefix in ALLOWED_WRITE_PREFIXES),
                    f"modifica fuori dal perimetro del confronto: {path}",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
