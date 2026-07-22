"""Test del repository degli EvidenceStatement.

Offline: nessun grafo, nessuna rete, nessun modello.
"""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from unittest import TestCase

from backend.pipeline.evidence.repository import (
    DuplicateStatementConflict,
    EvidenceRepositoryError,
    EvidenceStatementRepository,
    SnapshotMismatchError,
    StatementNotFound,
    identity_payload,
    load_statements,
    sort_key,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PILOT_STATEMENTS = (
    PROJECT_ROOT / "benchmarks" / "mtb_evidence" / "evaluation" / "results"
    / "adapter_v1" / "evidence_statements.jsonl"
)
PILOT_SNAPSHOT = "ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae"


def _statement(identifier="ES-1", **overrides):
    base = {
        "schema_version": "v3.0.0",
        "evidence_statement_id": identifier,
        "statement_version": 1,
        "biomarker": {"label": "ALK G1202R", "gene": "ALK", "is_compound": False,
                      "component_biomarkers": []},
        "alteration_type": "snv",
        "disease": {"label": "Lung Non-small Cell Carcinoma", "specificity": "unknown"},
        "intervention": {"label": "crizotinib"},
        "regimen": None,
        "direction": "resistance",
        "evidence_scope": "therapeutic",
        "assertion_polarity": "supports",
        "clinical_context": {},
        "evidence_type": "unknown",
        "evidence_level": None,
        "source_references": [
            {"source_id": "PUBMED:22277784", "source_type": "pubmed",
             "external_identifier": "22277784", "presence_in_snapshot": "node"}
        ],
        "trial_references": [],
        "regulatory_context": None,
        "source_spans": [],
        "provenance": {
            "origin": "frozen_kg", "snapshot_fingerprint": PILOT_SNAPSHOT,
            "graph_record_ids": ["evidence:441"], "extraction_action_id": "adapter/1.0",
        },
        "review_status": "pending_verification",
        "validity": None,
        "conflicts": [],
        "created_at": "2026-07-22T00:00:00+00:00",
        "updated_at": None,
    }
    for key, value in overrides.items():
        base[key] = value
    return base


class IngestionTest(TestCase):
    def test_empty_repository(self):
        repo = EvidenceStatementRepository()
        self.assertEqual(repo.count(), 0)
        self.assertEqual(repo.all(), [])

    def test_add_returns_identifier(self):
        repo = EvidenceStatementRepository()
        self.assertEqual(repo.add(_statement("ES-9")), "ES-9")

    def test_statement_without_id_is_rejected(self):
        with self.assertRaises(EvidenceRepositoryError):
            EvidenceStatementRepository([_statement(evidence_statement_id="")])

    def test_input_is_not_mutated(self):
        """Il chiamante puo' continuare a usare il proprio oggetto."""
        original = _statement()
        snapshot = copy.deepcopy(original)
        EvidenceStatementRepository([original])
        self.assertEqual(original, snapshot)

    def test_returned_objects_are_defensive_copies(self):
        repo = EvidenceStatementRepository([_statement()])
        first = repo.get_by_statement_id("ES-1")
        first["direction"] = "manomesso"
        self.assertEqual(repo.get_by_statement_id("ES-1")["direction"], "resistance")

    def test_all_pilot_statements_are_ingested(self):
        if not PILOT_STATEMENTS.is_file():
            self.skipTest("statement del pilota non generati")
        repo = load_statements(PILOT_STATEMENTS)
        self.assertEqual(repo.count(), 147)


class DuplicateTest(TestCase):
    def test_identical_duplicate_is_accepted_once(self):
        repo = EvidenceStatementRepository([_statement(), _statement()])
        self.assertEqual(repo.count(), 1)

    def test_conflicting_duplicate_raises(self):
        """Scegliere fra i due renderebbe il repository dipendente dall'ordine."""
        with self.assertRaises(DuplicateStatementConflict):
            EvidenceStatementRepository([
                _statement(direction="resistance"),
                _statement(direction="sensitivity"),
            ])

    def test_timestamps_do_not_make_duplicates_conflicting(self):
        """created_at cambia a ogni run dell'adapter: non e' parte dell'identita'."""
        repo = EvidenceStatementRepository([
            _statement(created_at="2026-01-01T00:00:00+00:00"),
            _statement(created_at="2026-07-22T00:00:00+00:00"),
        ])
        self.assertEqual(repo.count(), 1)

    def test_same_pmid_different_direction_are_two_statements(self):
        """Uno studio puo' riportare sensibilita' per una coorte e resistenza per un'altra."""
        repo = EvidenceStatementRepository([
            _statement("ES-A", direction="sensitivity"),
            _statement("ES-B", direction="resistance"),
        ])
        self.assertEqual(repo.count(), 2)
        self.assertEqual(len(repo.find_by_pmid("22277784")), 2)

    def test_identity_payload_excludes_volatile_fields(self):
        payload = identity_payload(_statement())
        self.assertNotIn("created_at", payload)
        self.assertIn("direction", payload)


class SnapshotIsolationTest(TestCase):
    def test_same_snapshot_is_allowed(self):
        repo = EvidenceStatementRepository([_statement("ES-1"), _statement("ES-2")])
        self.assertEqual(repo.count(), 2)

    def test_different_snapshot_is_rejected(self):
        other = _statement("ES-2")
        other["provenance"] = dict(other["provenance"], snapshot_fingerprint="altro")
        with self.assertRaises(SnapshotMismatchError) as ctx:
            EvidenceStatementRepository([_statement("ES-1"), other])
        self.assertIn("non interpretabili", str(ctx.exception))

    def test_multi_snapshot_requires_explicit_opt_in(self):
        other = _statement("ES-2")
        other["provenance"] = dict(other["provenance"], snapshot_fingerprint="altro")
        repo = EvidenceStatementRepository(
            [_statement("ES-1"), other], allow_multiple_snapshots=True
        )
        self.assertEqual(repo.count(), 2)
        self.assertTrue(repo.manifest().multi_snapshot)
        self.assertEqual(len(repo.manifest().snapshots), 2)


class LookupTest(TestCase):
    def setUp(self):
        doi = _statement("ES-DOI")
        doi["source_references"] = [
            {"source_id": "DOI:10.1/x", "source_type": "doi",
             "external_identifier": "10.1/X", "presence_in_snapshot": "unknown"}
        ]
        trial = _statement("ES-NCT")
        trial["trial_references"] = [
            {"source_id": "NCT01970865", "source_type": "clinicaltrials_gov",
             "external_identifier": "NCT01970865", "presence_in_snapshot": "unknown"}
        ]
        self.repo = EvidenceStatementRepository([_statement(), doi, trial])

    def test_by_statement_id(self):
        self.assertIsNotNone(self.repo.get_by_statement_id("ES-1"))
        self.assertIsNone(self.repo.get_by_statement_id("assente"))

    def test_require_raises_for_missing(self):
        with self.assertRaises(StatementNotFound):
            self.repo.require("assente")

    def test_by_graph_evidence_id_accepts_both_forms(self):
        self.assertTrue(self.repo.get_by_graph_evidence_id("441"))
        self.assertTrue(self.repo.get_by_graph_evidence_id("evidence:441"))

    def test_by_pmid(self):
        # ES-DOI ha una sola fonte, un DOI: non compare fra i risultati per PMID.
        self.assertEqual(
            [s["evidence_statement_id"] for s in self.repo.find_by_pmid("22277784")],
            ["ES-1", "ES-NCT"],
        )
        self.assertEqual(self.repo.find_by_pmid("0022277784"), self.repo.find_by_pmid("22277784"))

    def test_by_doi_is_case_insensitive(self):
        self.assertEqual(len(self.repo.find_by_doi("10.1/x")), 1)
        self.assertEqual(len(self.repo.find_by_doi("10.1/X")), 1)

    def test_by_nct(self):
        self.assertEqual(len(self.repo.find_by_nct("nct01970865")), 1)

    def test_by_biomarker_gene_disease_intervention(self):
        self.assertTrue(self.repo.find_by_gene("ALK"))
        self.assertTrue(self.repo.find_by_biomarker("alk g1202r"))
        self.assertTrue(self.repo.find_by_disease("Lung Non-small Cell Carcinoma"))
        self.assertTrue(self.repo.find_by_intervention("crizotinib"))

    def test_by_direction_scope_polarity(self):
        self.assertEqual(len(self.repo.find_by_direction("resistance")), 3)
        self.assertEqual(len(self.repo.find_by_evidence_scope("therapeutic")), 3)
        self.assertEqual(len(self.repo.find_by_assertion_polarity("supports")), 3)

    def test_by_origin_review_status_snapshot(self):
        self.assertEqual(len(self.repo.find_by_origin("frozen_kg")), 3)
        self.assertEqual(len(self.repo.find_by_review_status("pending_verification")), 3)
        self.assertEqual(len(self.repo.find_by_snapshot_fingerprint(PILOT_SNAPSHOT)), 3)

    def test_unknown_key_returns_empty_not_error(self):
        self.assertEqual(self.repo.find_by_gene("GENE-INESISTENTE"), [])


class QueryTest(TestCase):
    def setUp(self):
        self.repo = EvidenceStatementRepository([
            _statement("ES-1", direction="resistance"),
            _statement("ES-2", direction="sensitivity"),
            _statement("ES-3", direction="sensitivity", assertion_polarity="does_not_support"),
        ])

    def test_single_filter(self):
        self.assertEqual(len(self.repo.query(direction="sensitivity")), 2)

    def test_composed_filters_are_and(self):
        found = self.repo.query(direction="sensitivity", assertion_polarity="supports")
        self.assertEqual([s["evidence_statement_id"] for s in found], ["ES-2"])

    def test_composed_filter_with_source(self):
        found = self.repo.query(pmid="22277784", review_status="pending_verification")
        self.assertEqual(len(found), 3)

    def test_no_filters_returns_all(self):
        self.assertEqual(len(self.repo.query()), 3)

    def test_impossible_combination_is_empty(self):
        self.assertEqual(self.repo.query(gene="ALK", disease="Melanoma"), [])

    def test_unknown_filter_raises_instead_of_being_ignored(self):
        """Una query silenziosamente piu' larga di quanto chiesto e' peggio di un errore."""
        with self.assertRaises(EvidenceRepositoryError) as ctx:
            self.repo.query(colore="rosso")
        self.assertIn("colore", str(ctx.exception))

    def test_none_filters_are_skipped(self):
        self.assertEqual(len(self.repo.query(direction="sensitivity", gene=None)), 2)


class OrderInvarianceTest(TestCase):
    def _statements(self):
        return [
            _statement("ES-C", disease={"label": "Melanoma", "specificity": "unknown"}),
            _statement("ES-A", disease={"label": "Adenocarcinoma", "specificity": "unknown"}),
            _statement("ES-B", disease={"label": "Breast Cancer", "specificity": "unknown"}),
        ]

    def test_results_are_sorted_deterministically(self):
        statements = self._statements()
        forward = EvidenceStatementRepository(statements).all()
        backward = EvidenceStatementRepository(list(reversed(statements))).all()
        self.assertEqual(
            [s["evidence_statement_id"] for s in forward],
            [s["evidence_statement_id"] for s in backward],
        )

    def test_content_hash_is_order_independent(self):
        statements = self._statements()
        first = EvidenceStatementRepository(statements).content_hash()
        second = EvidenceStatementRepository(list(reversed(statements))).content_hash()
        self.assertEqual(first, second)

    def test_sort_key_uses_declared_order(self):
        key = sort_key(_statement())
        self.assertEqual(len(key), 5)
        self.assertEqual(key[-1], "ES-1")


class IndexTest(TestCase):
    def setUp(self):
        self.repo = EvidenceStatementRepository([_statement("ES-1"), _statement("ES-2")])

    def test_indices_are_consistent(self):
        self.assertEqual(self.repo.validate_indices(), [])

    def test_rebuild_produces_the_same_indices(self):
        before = self.repo.all()
        self.repo.rebuild_indices()
        self.assertEqual(self.repo.all(), before)
        self.assertEqual(self.repo.validate_indices(), [])

    def test_corrupted_index_is_detected(self):
        """Gli indici sono derivati: se divergono, il repository deve dirlo."""
        self.repo._indices["gene"]["alk"].append("ES-INESISTENTE")
        problems = self.repo.validate_indices()
        self.assertTrue(problems)
        self.assertTrue(any("non esiste" in p for p in problems))

    def test_pilot_indices_are_consistent(self):
        if not PILOT_STATEMENTS.is_file():
            self.skipTest("statement del pilota non generati")
        self.assertEqual(load_statements(PILOT_STATEMENTS).validate_indices(), [])


class SerializationTest(TestCase):
    def test_round_trip_preserves_content_hash(self):
        repo = EvidenceStatementRepository([_statement("ES-1"), _statement("ES-2")])
        with tempfile.TemporaryDirectory() as tmp:
            ok, detail = repo.round_trip_ok(Path(tmp) / "statements.jsonl")
            self.assertTrue(ok, detail)

    def test_serialization_is_deterministic(self):
        repo = EvidenceStatementRepository([_statement("ES-2"), _statement("ES-1")])
        with tempfile.TemporaryDirectory() as tmp:
            first = repo.to_jsonl(Path(tmp) / "a.jsonl").read_bytes()
            second = repo.to_jsonl(Path(tmp) / "b.jsonl").read_bytes()
            self.assertEqual(first, second)

    def test_manifest_records_what_is_needed_to_reproduce(self):
        manifest = EvidenceStatementRepository(
            [_statement()], source_adapter_version="adapter/1.0"
        ).manifest().as_dict()
        for key in ("repository_version", "schema_version", "snapshot_fingerprint",
                    "source_adapter_version", "created_at", "statement_count",
                    "content_hash"):
            self.assertIn(key, manifest)
        self.assertEqual(manifest["statement_count"], 1)

    def test_pilot_round_trip(self):
        if not PILOT_STATEMENTS.is_file():
            self.skipTest("statement del pilota non generati")
        repo = load_statements(PILOT_STATEMENTS)
        with tempfile.TemporaryDirectory() as tmp:
            ok, detail = repo.round_trip_ok(Path(tmp) / "statements.jsonl")
            self.assertTrue(ok, detail)
