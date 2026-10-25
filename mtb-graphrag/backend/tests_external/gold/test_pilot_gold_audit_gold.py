"""Le classi del pilot audit che aprono davvero il bundle gold.

Erano mescolate ai test unitari di `audit_lib` in `backend/tests/`, e leggevano
una copia del gold tracciata sotto `pilot/input/`. Quella copia non c'e' piu':
il bundle e' un ingresso esterno privato, e il suo path arriva da qui.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase

from benchmarks.mtb_evidence.pilot.audit_lib import report, second_review
from benchmarks.mtb_evidence.pilot.audit_lib.aliases import (
    AliasValidationError,
    alias_manifest,
    build_alias_table,
)
from benchmarks.mtb_evidence.pilot.audit_lib.classify import (
    ADJUVANT_RESECTED,
    FIRST_LINE_ADVANCED,
    INSUFFICIENT_CONTEXT,
    NOT_MODELLED_QUALIFIERS,
    POST_PROGRESSION_T790M,
    TEXT_HEURISTIC,
    alteration_types,
    classify_setting,
    classify_variant_form,
    mentions,
    qualifier_status,
)
from benchmarks.mtb_evidence.pilot.audit_lib.compare import (
    FULL,
    PARTIAL,
    UNMATCHED,
    compare_case,
    graph_claim_from_record,
    match_claim,
)
from benchmarks.mtb_evidence.pilot.audit_lib.disease import (
    DIFFERENT_SPECIFICITY,
    IDENTICAL,
    SAME_ENTITY,
    disease_relation,
    diseases_match,
    split_disease,
)
from benchmarks.mtb_evidence.pilot.audit_lib.gold import (
    GoldParseError,
    load_gold,
    parse_gold_lines,
)
from benchmarks.mtb_evidence.pilot.audit_lib.graph_client import (
    GraphUnavailable,
    Neo4jGraphClient,
    _is_connectivity_error,
)
from benchmarks.mtb_evidence.pilot.audit_lib.normalize import (
    norm_drug,
    norm_nct,
    norm_nct_set,
    norm_pmid,
    norm_pmid_set,
    norm_text,
)
from benchmarks.mtb_evidence.pilot.audit_lib.queries import n1_rmi2
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (
    REDACTED,
    canonical_json,
    fingerprint,
    sanitize_uri,
    scrub,
    secret_values,
    write_json,
    write_jsonl,
    write_text,
)


from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL

from backend.tests.pilot_gold_support import (
    PILOT_ROOT,
    PROJECT_ROOT,
    _ScriptedGraphClient,
    _gold_claim,
    _graph_record,
)


# Il bundle e' un presupposto di questo albero: `require` nomina ogni
# posizione cercata invece di lasciare un `None` che esplode piu' sotto.
GOLD_PATH = EXTERNAL.require(EXTERNAL.GOLD_BUNDLE) / "mtb_evidence_gold_pilot_v1.jsonl"


class GoldParsingTest(TestCase):
    def test_parses_the_four_pilot_cases(self):
        cases = load_gold(GOLD_PATH)
        self.assertEqual(len(cases), 4)
        self.assertEqual(
            [case.case_id for case in cases],
            [
                "PILOT-K1-FGFR2-iCCA",
                "PILOT-A2-ALK-G1202R",
                "PILOT-C1-EGFR-L858R-CONTEXT",
                "PILOT-N1-RMI2-SNAPSHOT",
            ],
        )

    def test_claims_and_sources_are_structured(self):
        cases = {case.case_id: case for case in load_gold(GOLD_PATH)}
        k1 = cases["PILOT-K1-FGFR2-iCCA"]
        self.assertEqual(len(k1.claims), 2)
        self.assertEqual(len(k1.sources), 4)
        self.assertEqual(k1.expected_therapies, ("pemigatinib", "futibatinib"))
        self.assertFalse(k1.expected_abstention)
        self.assertTrue(cases["PILOT-N1-RMI2-SNAPSHOT"].expected_abstention)

    def test_blank_lines_are_ignored(self):
        line = json.dumps({"case_id": "X", "claims": [], "sources": []})
        cases = parse_gold_lines(["", line, "   ", ""])
        self.assertEqual(len(cases), 1)

    def test_malformed_json_reports_line_number(self):
        with self.assertRaises(GoldParseError) as ctx:
            parse_gold_lines(['{"case_id": "A"}', "{not json"])
        self.assertIn("riga 2", str(ctx.exception))

    def test_duplicate_case_id_is_rejected(self):
        line = json.dumps({"case_id": "DUP"})
        with self.assertRaises(GoldParseError):
            parse_gold_lines([line, line])

    def test_the_bundle_matches_the_manifest_the_repository_keeps(self):
        """Il gold aperto e' quello che il repository dichiara di aspettarsi.

        Finche' una copia del gold era tracciata sotto `pilot/input/`, questo
        test confrontava quella copia con il bundle. Ora la copia non c'e' piu'
        e il confronto sarebbe fra il file e se stesso. Cio' che resta da
        verificare — e che prima nessuno verificava — e' che il bundle
        corrisponda al manifest tracciato: e' l'unica cosa che il repository
        sa dire del gold senza contenerlo.
        """
        manifest = json.loads(
            (PILOT_ROOT / "input" / "external_gold_input.json").read_text(
                encoding="utf-8"
            )
        )
        expected = manifest["expected_sha256"][GOLD_PATH.name]
        self.assertEqual(
            hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest(), expected
        )



class CompareCaseTest(TestCase):
    def setUp(self):
        self.table = build_alias_table()
        self.cases = {case.case_id: case for case in load_gold(GOLD_PATH)}

    def test_missing_sources_become_freeze_blockers(self):
        case = self.cases["PILOT-C1-EGFR-L858R-CONTEXT"]
        comparison = compare_case(case, [], alias_table=self.table)
        self.assertFalse(comparison["freeze_ready"])
        self.assertFalse(comparison["graph_complete"])
        self.assertTrue(comparison["missing_pmids"])
        self.assertTrue(comparison["freeze_blockers"])

    def test_abstention_case_is_ready_when_graph_is_empty(self):
        case = self.cases["PILOT-N1-RMI2-SNAPSHOT"]
        comparison = compare_case(case, [], alias_table=self.table)
        self.assertTrue(comparison["freeze_ready"])
        self.assertEqual(comparison["freeze_blockers"], [])

    def test_abstention_case_blocks_when_a_therapy_appears(self):
        case = self.cases["PILOT-N1-RMI2-SNAPSHOT"]
        comparison = compare_case(
            case,
            [graph_claim_from_record(_graph_record(drug="OSIMERTINIB"))],
            alias_table=self.table,
            found_therapies={"osimertinib"},
        )
        self.assertFalse(comparison["freeze_ready"])
        self.assertTrue(
            any("astensione" in blocker for blocker in comparison["freeze_blockers"])
        )

    def test_unmatched_claims_do_not_emit_phantom_conflicts(self):
        case = self.cases["PILOT-K1-FGFR2-iCCA"]
        comparison = compare_case(case, [], alias_table=self.table)
        self.assertEqual(comparison["conflicts"], [])

    def test_comparison_exposes_every_required_field(self):
        case = self.cases["PILOT-K1-FGFR2-iCCA"]
        comparison = compare_case(case, [], alias_table=self.table)
        for key in (
            "expected_therapies", "found_therapies", "missing_therapies", "extra_therapies",
            "expected_pmids", "found_pmids", "missing_pmids", "extra_pmids",
            "expected_nct_ids", "found_nct_ids", "missing_nct_ids", "extra_nct_ids",
            "expected_claims", "structurally_matching_claims", "partially_matching_claims",
            "unmatched_claims", "qualifiers_found", "qualifiers_missing", "conflicts",
            "graph_complete", "audit_warnings", "freeze_ready", "freeze_blockers",
        ):
            self.assertIn(key, comparison)



class NegativePathProofTest(TestCase):
    def setUp(self):
        self.table = build_alias_table()
        self.case = {c.case_id: c for c in load_gold(GOLD_PATH)}["PILOT-N1-RMI2-SNAPSHOT"]

    def test_empty_traversal_produces_a_valid_negative(self):
        client = _ScriptedGraphClient(
            responses=[("MATCH (g:Gene {hugo_symbol: $gene}) RETURN g AS gene",
                        [{"gene": {"hugo_symbol": "RMI2", "entrez_id": 116028}}])],
            default=[],
        )
        outcome = n1_rmi2.run(client, self.case, self.table)
        proof = n1_rmi2.build_negative_path_proof(
            outcome, snapshot_fingerprint="deadbeef", timestamp="2026-07-21T00:00:00+00:00"
        )
        self.assertTrue(proof["is_valid_negative"])
        self.assertEqual(proof["therapeutic_path_count"], 0)
        self.assertEqual(proof["snapshot_fingerprint"], "deadbeef")
        self.assertIn("cypher", proof["primary_query"])
        self.assertIn("params", proof["primary_query"])
        self.assertEqual(proof["primary_query"]["params"], {"gene": "RMI2"})

    def test_a_found_path_is_reported_not_hidden(self):
        client = _ScriptedGraphClient(
            responses=[
                (
                    "-[:TARGETS_DRUG]->(d:Drug) RETURN g.hugo_symbol AS gene",
                    [{"gene": "RMI2", "variant": "V1", "molecular_profile": "RMI2 Mutation",
                      "evidence_id": 1, "significance": "Sensitivity/Response",
                      "disease": "X", "citation_id": ["1"], "drug": "SOMEDRUG"}],
                )
            ],
            default=[],
        )
        outcome = n1_rmi2.run(client, self.case, self.table)
        proof = n1_rmi2.build_negative_path_proof(outcome, snapshot_fingerprint="x")
        self.assertFalse(proof["is_valid_negative"])
        self.assertEqual(proof["therapeutic_path_count"], 1)
        self.assertTrue(proof["blockers"])
        self.assertTrue(outcome.blockers)

    def test_case_is_rejected_when_the_premise_fails(self):
        client = _ScriptedGraphClient(
            responses=[
                (
                    "-[:TARGETS_DRUG]->(d:Drug) RETURN g.hugo_symbol AS gene",
                    [{"gene": "RMI2", "drug": "SOMEDRUG", "evidence_id": 1}],
                )
            ],
            default=[],
        )
        outcome = n1_rmi2.run(client, self.case, self.table)
        comparison = compare_case(
            self.case, outcome.graph_claims, alias_table=self.table,
            found_therapies=outcome.found_therapies, extra_blockers=outcome.blockers,
        )
        self.assertEqual(report.decide(self.case, comparison, outcome)["decision"], report.REJECT)



class SecondReviewPackageTest(TestCase):
    def setUp(self):
        self.table = build_alias_table()
        self.cases = load_gold(GOLD_PATH)

    def _entries(self):
        from benchmarks.mtb_evidence.pilot.audit_lib.queries.base import CaseOutcome

        entries = []
        for case in self.cases:
            outcome = CaseOutcome(case_id=case.case_id)
            comparison = compare_case(case, [], alias_table=self.table)
            entries.append(
                {
                    "case_id": case.case_id,
                    "case": case,
                    "outcome": outcome,
                    "comparison": comparison,
                    "decision": report.decide(case, comparison, outcome),
                }
            )
        return entries

    def test_package_has_all_four_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            written = second_review.write_package(Path(tmp), self._entries())
            for name in (
                "review_cases.csv", "review_claims.csv", "review_sources.csv",
                "reviewer_instructions.md",
            ):
                self.assertIn(name, written)
                self.assertTrue(written[name].is_file())

    def test_decision_column_is_present_and_empty(self):
        rows = second_review.build_claim_rows(self._entries())
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["reviewer_decision"], "")
            self.assertEqual(row["reviewer_notes"], "")

    def test_all_four_decision_options_are_documented(self):
        for option in second_review.DECISION_OPTIONS:
            self.assertIn(option, second_review.INSTRUCTIONS)

    def test_package_carries_no_suggestion_of_the_answer(self):
        """Un secondo giudizio contaminato dal primo non e' un secondo giudizio."""
        with tempfile.TemporaryDirectory() as tmp:
            written = second_review.write_package(Path(tmp), self._entries())
            for name, path in written.items():
                content = path.read_text(encoding="utf-8").casefold()
                for pattern in report.FORBIDDEN_REVIEW_PATTERNS:
                    self.assertNotIn(pattern.casefold(), content, f"{pattern} in {name}")

    def test_audit_decision_never_reaches_the_reviewer(self):
        rows = second_review.build_case_rows(self._entries())
        serialized = canonical_json(rows).casefold()
        for decision in (report.KEEP, report.AMEND, report.REPLACE, report.REJECT):
            self.assertNotIn(f'"{decision.casefold()}"', serialized)



class AmendmentsTest(TestCase):
    def setUp(self):
        self.table = build_alias_table()
        self.cases = {case.case_id: case for case in load_gold(GOLD_PATH)}

    def test_every_proposal_requires_human_review(self):
        from benchmarks.mtb_evidence.pilot.audit_lib.queries.base import CaseOutcome

        case = self.cases["PILOT-K1-FGFR2-iCCA"]
        outcome = CaseOutcome(case_id=case.case_id)
        comparison = compare_case(case, [], alias_table=self.table)
        proposals = report.build_amendments(case, comparison, outcome)
        self.assertTrue(proposals)
        for proposal in proposals:
            self.assertTrue(proposal["requires_human_review"])
            for key in (
                "case_id", "field", "current_value", "proposed_value", "reason",
                "supporting_graph_record_ids", "supporting_source_ids", "confidence",
            ):
                self.assertIn(key, proposal)

    def test_amendments_do_not_touch_the_gold_file(self):
        from benchmarks.mtb_evidence.pilot.audit_lib.queries.base import CaseOutcome

        before = GOLD_PATH.read_bytes()
        for case in self.cases.values():
            outcome = CaseOutcome(case_id=case.case_id)
            report.build_amendments(case, compare_case(case, [], alias_table=self.table), outcome)
        self.assertEqual(GOLD_PATH.read_bytes(), before)
