"""Inventario, scope e artefatti del corpus, sui 147 statement reali.

Tutti i test sono offline: leggono artefatti congelati e non aprono connessioni,
non toccano Neo4j e non chiamano nessun LLM. Il test che richiede rete e'
separato e disattivato per default (`MTB_ALLOW_NETWORK_TESTS`).
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from backend.pipeline.evidence.corpus_manifest import content_hash
from backend.pipeline.evidence.repository import EvidenceStatementRepository
from benchmarks.mtb_evidence.evaluation.corpus_builder import (
    DESIGN_UNDETERMINED,
    build_scope,
    build_units,
    build_packet,
    evidence_design_from_metadata,
)
from benchmarks.mtb_evidence.evaluation.source_inventory import (
    ALL_STRATA,
    PRESENCE_CITATION_ONLY,
    PRESENCE_NODE,
    STRATUM_CITATION_ONLY,
    STRATUM_NEGATIVE_POLARITY,
    STRATUM_PRESENT_AS_NODE,
    STRATUM_RESISTANCE,
    build_inventory,
    stratum_counts,
)
from benchmarks.mtb_evidence.evaluation.source_profiles import default_repository

REPO_ROOT = Path(__file__).resolve().parents[2]
QUALIFICATION = REPO_ROOT / "benchmarks/mtb_evidence/v3/qualification"
CORPUS = REPO_ROOT / "benchmarks/mtb_evidence/v3/qualification_corpus"
AUDIT = REPO_ROOT / "benchmarks/mtb_evidence/pilot/audit"
PILOT = REPO_ROOT / "benchmarks/mtb_evidence/evaluation/results/pilot_v1"

EXPECTED_STATEMENTS = 147
EXPECTED_SOURCES = 102


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_statements() -> list[dict]:
    return load_jsonl(QUALIFICATION / "evidence_statements.jsonl")


def make_inventory(statements: list[dict]):
    return build_inventory(
        statements,
        audit_dir=AUDIT,
        ablation_manifest=PILOT / "reporting_ablation_manifest.json",
        conflicts_path=QUALIFICATION / "conflicts.jsonl",
        pilot_runs=PILOT / "case_runs.jsonl",
        profiles=default_repository(),
    )


class TestInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.statements = load_statements()
        cls.entries = make_inventory(cls.statements)

    def test_every_statement_source_is_inventoried(self) -> None:
        covered = {item for entry in self.entries for item in entry.statement_ids}
        self.assertEqual(len(self.statements), EXPECTED_STATEMENTS)
        self.assertEqual(len(covered), EXPECTED_STATEMENTS)

    def test_source_count_is_stable(self) -> None:
        self.assertEqual(len(self.entries), EXPECTED_SOURCES)

    def test_inventory_is_order_invariant(self) -> None:
        reversed_entries = make_inventory(list(reversed(self.statements)))
        self.assertEqual(
            [entry.canonical_source_id for entry in self.entries],
            [entry.canonical_source_id for entry in reversed_entries],
        )
        self.assertEqual(
            content_hash([entry.as_dict() for entry in self.entries]),
            content_hash([entry.as_dict() for entry in reversed_entries]),
        )

    def test_canonical_ids_are_unique(self) -> None:
        ids = [entry.canonical_source_id for entry in self.entries]
        self.assertEqual(len(ids), len(set(ids)))

    def test_citation_only_is_distinct_from_node(self) -> None:
        """Una fonte citation_only non e' interrogabile come entita' del grafo."""
        counts = stratum_counts(self.entries)
        self.assertGreater(counts[STRATUM_CITATION_ONLY], 0)
        self.assertGreater(counts[STRATUM_PRESENT_AS_NODE], 0)
        states = {entry.presence_in_snapshot for entry in self.entries}
        self.assertIn(PRESENCE_CITATION_ONLY, states)
        self.assertIn(PRESENCE_NODE, states)

    def test_absent_source_is_not_the_same_as_unlinked_source(self) -> None:
        """FLAURA e FOENIX-CCA2 sono assenti, non semplicemente non collegate."""
        rows = load_jsonl(CORPUS / "unresolved_sources.jsonl")
        absent = [row for row in rows if row["category"] == "absent_from_snapshot"]
        unresolved = [row for row in rows if row["category"] == "unresolved_identifier"]
        self.assertEqual({row["source_profile_id"] for row in absent}, {"S-C1-1", "S-K1-3"})
        self.assertEqual(unresolved, [])
        self.assertTrue(all(row["blocks_freeze"] is False for row in absent))

    def test_noisy_and_negative_sources_are_present(self) -> None:
        counts = stratum_counts(self.entries)
        self.assertGreater(counts[STRATUM_RESISTANCE], 0)
        self.assertGreater(counts[STRATUM_NEGATIVE_POLARITY], 0)

    def test_multi_statement_sources_are_flagged(self) -> None:
        multi = [entry for entry in self.entries if entry.statement_count > 1]
        self.assertGreater(len(multi), 0)

    def test_every_stratum_is_declared(self) -> None:
        for entry in self.entries:
            for stratum in entry.strata:
                with self.subTest(source=entry.canonical_source_id):
                    self.assertIn(stratum, ALL_STRATA)


class TestScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.statements = load_statements()
        cls.entries = make_inventory(cls.statements)
        cls.profiles = default_repository()

    def test_scope_is_a_census(self) -> None:
        """Nessuna fonte dello universo puo' essere esclusa discrezionalmente."""
        scope = build_scope(self.entries)
        included = [item for item in scope if item.included]
        self.assertEqual(len(included), len(self.entries))

    def test_scope_is_deterministic(self) -> None:
        first = [item.as_dict() for item in build_scope(self.entries)]
        second = [item.as_dict() for item in build_scope(list(reversed(self.entries)))]
        self.assertEqual(content_hash(first), content_hash(second))

    def test_scope_hash_is_stable(self) -> None:
        payload = json.loads((CORPUS / "qualification_scope.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["qualification_scope_hash"], content_hash(payload["decisions"]))

    def test_scope_does_not_use_the_clinical_gold(self) -> None:
        payload = json.loads((CORPUS / "qualification_scope.json").read_text(encoding="utf-8"))
        self.assertFalse(payload["clinical_gold_used"])
        self.assertEqual(payload["universe"], "147 EvidenceStatement congelati")

    def test_orphan_profiles_are_excluded_with_a_reason(self) -> None:
        scope = build_scope(self.entries, orphan_profiles=list(self.profiles)[:1])
        excluded = [item for item in scope if not item.included]
        self.assertEqual(len(excluded), 1)
        self.assertTrue(excluded[0].exclusion_reason)

    def test_every_scoped_source_has_a_blind_id(self) -> None:
        for decision in build_scope(self.entries):
            with self.subTest(source=decision.canonical_source_id):
                self.assertTrue(decision.blind_annotation_id.startswith("BA-"))


class TestUnitsAndPackets(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.statements = load_statements()
        cls.entries = make_inventory(cls.statements)
        cls.profiles = default_repository()
        cls.metadata = {
            str(row["identifier_key"]): row
            for row in load_jsonl(CORPUS / "source_metadata_cache.jsonl")
        }
        cls.units = build_units(
            cls.entries,
            metadata=cls.metadata,
            profiles_by_source_id={p.source_id: p for p in cls.profiles},
            created_at="2026-01-01T00:00:00+00:00",
        )

    def test_one_unit_per_source(self) -> None:
        self.assertEqual(len(self.units), len(self.entries))

    def test_units_are_deterministic(self) -> None:
        again = build_units(
            list(reversed(self.entries)),
            metadata=self.metadata,
            profiles_by_source_id={p.source_id: p for p in self.profiles},
            created_at="2026-01-01T00:00:00+00:00",
        )
        self.assertEqual(
            content_hash([unit.as_dict() for unit in self.units]),
            content_hash([unit.as_dict() for unit in again]),
        )

    def test_reviewed_profiles_keep_their_human_status(self) -> None:
        reviewed = [unit for unit in self.units if unit.review_status == "human_reviewed"]
        self.assertEqual(len(reviewed), 6)
        for unit in reviewed:
            with self.subTest(unit=unit.profile_unit_id):
                self.assertNotEqual(unit.extraction_status, "machine_extracted")

    def test_no_unit_is_declared_human_reviewed_by_this_process(self) -> None:
        """Solo i profili preesistenti portano uno stato umano."""
        existing = {p.source_id for p in self.profiles}
        for unit in self.units:
            if unit.review_status == "human_reviewed":
                with self.subTest(unit=unit.profile_unit_id):
                    self.assertIn(unit.source_profile_id, existing)

    def test_provenance_is_complete_on_every_unit(self) -> None:
        for unit in self.units:
            with self.subTest(unit=unit.profile_unit_id):
                self.assertTrue(unit.provenance_complete(), unit.missing_provenance())

    def test_resection_status_is_never_invented(self) -> None:
        for unit in self.units:
            with self.subTest(unit=unit.profile_unit_id):
                self.assertEqual(unit.resection_status, "unknown")

    def test_ambiguous_units_do_not_propagate(self) -> None:
        """Una coorte non identificata resta da chiarire, e non propaga.

        Il criterio e' `cohort_is_resolved` e non `is_propagatable`: dopo la
        politica di propagazione il secondo e' falso anche per unita' gia'
        revisionate una volta, che non hanno nulla di ambiguo. Confonderli
        farebbe passare per irrisolto cio' che e' soltanto non ancora
        confermato due volte.
        """
        ambiguous = [unit for unit in self.units if not unit.cohort_is_resolved]
        self.assertGreater(len(ambiguous), 0)
        for unit in ambiguous:
            with self.subTest(unit=unit.profile_unit_id):
                self.assertTrue(unit.requires_human_review)
                self.assertFalse(unit.is_propagatable)

    def test_packet_is_blind(self) -> None:
        entries_by_id = {entry.canonical_source_id: entry for entry in self.entries}
        statements_by_id = {
            str(item["evidence_statement_id"]): item for item in self.statements
        }
        for unit in self.units[:20]:
            entry = entries_by_id[unit.canonical_source_id]
            packet = build_packet(
                unit,
                entry=entry,
                statements_by_id=statements_by_id,
                metadata=self.metadata,
            )
            with self.subTest(unit=unit.profile_unit_id):
                self.assertFalse(packet["contains_clinical_gold"])
                self.assertFalse(packet["contains_expected_therapies"])
                self.assertFalse(packet["contains_system_metrics"])
                self.assertFalse(packet["contains_keep_amend_reject"])
                serialised = json.dumps(packet)
                self.assertNotIn("annotation_priority", serialised)
                self.assertNotIn("stratum", serialised)

    def test_packet_fields_default_to_unknown(self) -> None:
        entry = self.entries[0]
        unit = next(u for u in self.units if u.canonical_source_id == entry.canonical_source_id)
        packet = build_packet(
            unit, entry=entry, statements_by_id={}, metadata=self.metadata
        )
        self.assertTrue(all(item["value"] == "unknown" for item in packet["fields_to_fill"]))


class TestEvidenceDesign(unittest.TestCase):
    def test_registry_asserted_design_is_used(self) -> None:
        design, _ = evidence_design_from_metadata(
            {"publication_types": ["Journal Article", "Randomized Controlled Trial"]}
        )
        self.assertEqual(design, "randomized_controlled_trial")

    def test_absence_of_a_clinical_type_is_not_preclinical(self) -> None:
        """L'assenza di un tipo clinico non dimostra che lo studio sia preclinico."""
        design, reason = evidence_design_from_metadata(
            {"publication_types": ["Journal Article"]}
        )
        self.assertEqual(design, DESIGN_UNDETERMINED)
        self.assertNotIn("preclinic", design)
        self.assertIn("non prova", reason)

    def test_missing_metadata_is_undetermined(self) -> None:
        design, _ = evidence_design_from_metadata(None)
        self.assertEqual(design, DESIGN_UNDETERMINED)


class TestRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.statements = load_statements()

    def test_the_147_statements_are_still_ingestible(self) -> None:
        repository = EvidenceStatementRepository(self.statements)
        self.assertEqual(len(repository), EXPECTED_STATEMENTS)
        self.assertEqual(repository.validate_indices(), [])

    def test_repository_hash_matches_the_manifest(self) -> None:
        repository = EvidenceStatementRepository(self.statements)
        manifest = json.loads(
            (CORPUS / "qualification_corpus_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["statement_repository_hash"], repository.content_hash())

    def test_snapshot_fingerprint_is_unchanged(self) -> None:
        manifest = json.loads(
            (CORPUS / "qualification_corpus_manifest.json").read_text(encoding="utf-8")
        )
        expected = str(
            (self.statements[0].get("provenance") or {}).get("snapshot_fingerprint") or ""
        )
        self.assertEqual(manifest["snapshot_fingerprint"], expected)

    def test_freeze_status_is_honest(self) -> None:
        manifest = json.loads(
            (CORPUS / "qualification_corpus_manifest.json").read_text(encoding="utf-8")
        )
        if manifest["freeze_status"] == "frozen":
            self.assertEqual(manifest["blockers"], [])
        else:
            self.assertTrue(manifest["blockers"])

    def test_linking_metrics_are_not_fabricated(self) -> None:
        metrics = json.loads((CORPUS / "linking_metrics.json").read_text(encoding="utf-8"))
        if metrics["evaluated_count"] == 0:
            self.assertEqual(metrics["linking_precision"], "not_evaluable")
            self.assertEqual(metrics["linking_recall"], "not_evaluable")
            self.assertEqual(metrics["inter_annotator_agreement"], "not_evaluable")

    def test_no_gold_record_was_produced_from_a_prediction(self) -> None:
        for row in load_jsonl(CORPUS / "statement_qualification_gold.jsonl"):
            with self.subTest(gold=row["gold_link_id"]):
                if not row["is_evaluable"]:
                    self.assertIsNone(row["first_annotation"])
                    self.assertIsNone(row["second_annotation"])

    def test_candidates_are_marked_as_non_gold(self) -> None:
        for row in load_jsonl(CORPUS / "statement_profile_candidates.jsonl"):
            with self.subTest(statement=row["statement_id"]):
                self.assertFalse(row["is_gold"])

    def test_artifacts_contain_no_credentials(self) -> None:
        pattern = ("authorization", "api_key", "api-key", "bearer ", "password")
        for path in sorted(CORPUS.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for needle in pattern:
                with self.subTest(path=path.name, needle=needle):
                    self.assertNotIn(needle, text)


@unittest.skipUnless(
    os.environ.get("MTB_ALLOW_NETWORK_TESTS") == "1",
    "test di rete disabilitato per default: MTB_ALLOW_NETWORK_TESTS=1 per abilitarlo",
)
class TestRegistryFetchNetwork(unittest.TestCase):
    def test_registry_returns_a_title(self) -> None:
        from benchmarks.mtb_evidence.evaluation.scripts.fetch_source_metadata import (
            fetch_pubmed_summaries,
        )

        found = fetch_pubmed_summaries(["32203698"])
        self.assertIn("32203698", found)
        self.assertTrue(found["32203698"]["title"])


if __name__ == "__main__":
    unittest.main()
