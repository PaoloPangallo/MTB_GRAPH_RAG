"""ISS-003 — una quote non validata non è presentabile come citazione d'autore.

Il dossier **canonico** era già corretto: status, mask, bucket e gate non erano
mai toccati da un enrichment rigettato. Il difetto stava nel dossier
**presentato**: le voci di ``author_context`` non portavano il proprio esito, e
la UI ricadeva su ``accepted = quote != null``.

Questi test coprono i due lati: la voce del dossier e la regola di presentazione.
"""

from __future__ import annotations

import unittest

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import execution_mode as em
from backend.research_pipeline import live_providers as lp
from backend.research_pipeline import orchestrator
from backend.research_pipeline.determinism.gates import evaluate_association
from backend.research_pipeline.dossier import builder
from backend.research_pipeline.dossier.builder import (
    ABSTAINED,
    PRESENTABLE_AS_AUTHOR_CLAIM,
    PROPOSED_QUOTE_NOT_VALIDATED,
    REJECTED_QUOTE,
    VALIDATED_QUOTE,
    annotate_enrichment,
    presentation_state,
)

DOC = ("In this phase III trial, patients with KRAS G12D metastatic colorectal cancer "
       "did not derive benefit from panitumumab.")
UNITS = {
    "SU-A1": {"source_unit_id": "SU-A1", "document_id": "DOC-A", "text": DOC},
    "SU-B1": {"source_unit_id": "SU-B1", "document_id": "DOC-B",
              "text": "Encorafenib plus cetuximab produced responses."},
}
PAPER = {"bundle_id": "EB-A", "document_id": "DOC-A",
         "source_unit_ids": ["SU-A1"], "resolved_source_unit_ids": ["SU-A1"]}
CAND = {"candidate_id": "GCA-T", "direction": "Supports",
        "disease": [{"label": "Colorectal Cancer"}], "biomarkers": [{"label": "KRAS G12D"}],
        "interventions": [{"label": "panitumumab"}], "source_properties": {}}
LITERAL = "did not derive benefit from panitumumab"


def _args(decision="QUOTE", su="SU-A1", quote="", summary="", ab=""):
    return {"decision": decision, "source_unit_id": su, "author_claim_quote": quote,
            "author_context_summary": summary, "abstention_reason": ab}


def _presented(entry) -> list:
    """Le voci che un consumatore può rendere come citazione d'autore."""
    return [e for e in entry["author_context"]
            if e.get("presentation_state") in PRESENTABLE_AS_AUTHOR_CLAIM]


def _entry_for(args):
    validation = lp.validate_fn("V2_TRANSPORT_VALID", dict(args), candidate=CAND,
                                paper_bundle=PAPER, source_units_by_id=UNITS,
                                requested_drug="panitumumab")
    gate = orchestrator._accepted_for_gates(validation["outcome"])
    validated = [] if gate is None else [{"validation_outcome": gate, "enrichment": dict(args)}]
    entry = builder.build_candidate_therapy_entry(
        CAND, graph_relation="has_evidence_statement",
        document_support={"selected_papers": ["EB-A"], "excluded_papers": []},
        enrichments=[annotate_enrichment(dict(args), paper_id="EB-A",
                                         validation=validation,
                                         accepted_for_gates=gate is not None)],
        validation_results=[{"paper_id": "EB-A", **validation}],
        evaluation=evaluate_association("THERAPY_EVALUATION", CAND, validated))
    return validation, entry


class PresentationStateVocabulary(unittest.TestCase):

    def test_only_validated_is_presentable(self) -> None:
        self.assertEqual(PRESENTABLE_AS_AUTHOR_CLAIM, frozenset({VALIDATED_QUOTE}))
        self.assertNotIn(REJECTED_QUOTE, PRESENTABLE_AS_AUTHOR_CLAIM)
        self.assertNotIn(ABSTAINED, PRESENTABLE_AS_AUTHOR_CLAIM)
        self.assertNotIn(PROPOSED_QUOTE_NOT_VALIDATED, PRESENTABLE_AS_AUTHOR_CLAIM)

    def test_missing_outcome_is_not_an_acceptance(self) -> None:
        """Assenza di esito != accettazione. È il default conservativo."""
        self.assertEqual(presentation_state(None, has_quote=True), PROPOSED_QUOTE_NOT_VALIDATED)
        self.assertNotIn(presentation_state(None, has_quote=True), PRESENTABLE_AS_AUTHOR_CLAIM)

    def test_unknown_outcome_is_rejected_not_accepted(self) -> None:
        self.assertEqual(presentation_state("SOME_FUTURE_OUTCOME", has_quote=True), REJECTED_QUOTE)

    def test_both_validator_vocabularies_are_recognised(self) -> None:
        for outcome in ("ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING",
                        "ENRICHMENT_V2_ACCEPTED", "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY"):
            with self.subTest(outcome=outcome):
                self.assertEqual(presentation_state(outcome, has_quote=True), VALIDATED_QUOTE)


class QuotePresentationMatchesValidation(unittest.TestCase):
    """§11 del mandato: i nove scenari."""

    def test_A_valid_quote_is_presentable(self) -> None:
        validation, entry = _entry_for(_args(quote=LITERAL,
                                             summary="Patients did not derive benefit from panitumumab."))
        self.assertEqual(validation["outcome"], "ENRICHMENT_V2_ACCEPTED")
        self.assertEqual(len(_presented(entry)), 1)

    def test_B_invented_quote_is_not_presentable(self) -> None:
        _, entry = _entry_for(_args(quote="Panitumumab significantly prolonged overall survival.",
                                    summary="Panitumumab prolonged survival."))
        self.assertEqual(_presented(entry), [])

    def test_C_altered_quote_is_not_presentable(self) -> None:
        _, entry = _entry_for(_args(quote="did derive benefit from panitumumab",
                                    summary="Patients did derive benefit."))
        self.assertEqual(_presented(entry), [])

    def test_D_quote_from_other_sourceunit_is_not_presentable(self) -> None:
        _, entry = _entry_for(_args(quote="Encorafenib plus cetuximab produced responses.",
                                    summary="Encorafenib plus cetuximab produced responses."))
        self.assertEqual(_presented(entry), [])

    def test_E_quote_from_other_document_is_not_presentable(self) -> None:
        _, entry = _entry_for(_args(su="SU-B1", quote="Encorafenib plus cetuximab produced responses.",
                                    summary="Encorafenib plus cetuximab produced responses."))
        self.assertEqual(_presented(entry), [])

    def test_F_invented_sourceunit_is_not_presentable(self) -> None:
        _, entry = _entry_for(_args(su="SU-NOPE", quote=LITERAL, summary="Patients did not benefit."))
        self.assertEqual(_presented(entry), [])

    def test_G_abstain_is_not_presentable(self) -> None:
        _, entry = _entry_for(_args(decision="ABSTAIN", su="", ab="NO_RELEVANT_PASSAGE"))
        self.assertEqual(_presented(entry), [])
        self.assertEqual(entry["author_context"][0]["presentation_state"], ABSTAINED)

    def test_H_enrichment_without_quote_is_not_presentable(self) -> None:
        _, entry = _entry_for(_args(quote="", summary="Some summary."))
        self.assertEqual(_presented(entry), [])

    def test_I_validator_failure_is_not_an_acceptance(self) -> None:
        entry = builder.build_candidate_therapy_entry(
            CAND, graph_relation="x", document_support={},
            enrichments=[annotate_enrichment({"author_claim_quote": "qualcosa"},
                                             paper_id="EB-A", validation=None,
                                             accepted_for_gates=False)],
            validation_results=[],
            evaluation=evaluate_association("THERAPY_EVALUATION", CAND, []))
        self.assertEqual(_presented(entry), [])

    def test_rejected_entries_remain_visible_for_audit(self) -> None:
        """Conservate, non cancellate: servono all'audit."""
        _, entry = _entry_for(_args(quote="Panitumumab prolonged survival.",
                                    summary="Panitumumab prolonged survival."))
        self.assertEqual(len(entry["author_context"]), 1)
        voice = entry["author_context"][0]
        self.assertEqual(voice["presentation_state"], REJECTED_QUOTE)
        self.assertEqual(voice["validation_outcome"], "REJECTED_QUOTE_NOT_FOUND")
        self.assertIn("QUOTE_NOT_LITERAL_IN_SOURCE_UNIT", voice["validation_reason_codes"])
        self.assertEqual(voice["author_claim_quote"], "Panitumumab prolonged survival.")

    def test_canonical_status_still_protected(self) -> None:
        """Il dossier canonico non era rotto e non deve regredire."""
        _, entry = _entry_for(_args(quote="Panitumumab prolonged survival.",
                                    summary="Panitumumab prolonged survival."))
        self.assertEqual(entry["status"], "AMBIGUOUS")
        self.assertEqual(entry["gate_results"]["support_mask"]["direction"], "NO_DOCUMENT_SIGNAL")
        self.assertEqual(entry["gate_results"]["bucket"], "WARNING_BUCKET")

    def test_annotate_does_not_mutate_the_original(self) -> None:
        original = _args(quote=LITERAL, summary="x")
        snapshot = dict(original)
        annotate_enrichment(original, paper_id="EB-A",
                            validation={"outcome": "ENRICHMENT_V2_ACCEPTED"},
                            accepted_for_gates=True)
        self.assertEqual(original, snapshot)


class EndToEndThroughOrchestrator(unittest.TestCase):
    """Il dossier prodotto da una run reale porta gli esiti su ogni voce."""

    def test_replay_run_annotates_every_author_context_entry(self) -> None:
        import tempfile
        from pathlib import Path

        from backend.research_pipeline import data_access as da
        from backend.research_pipeline import replay

        case_id = "CASE-1-therapy-evaluation-strong-match"
        if not replay.has_frozen_case(case_id):  # pragma: no cover
            self.skipTest("artefatti congelati non disponibili")

        with tempfile.TemporaryDirectory() as tmp:
            ledger = EventLedger(Path(tmp) / "e2e.sqlite3")
            case = next(c for c in __import__(
                "backend.research_pipeline.cases.definitions", fromlist=["CASES"]).CASES
                if c["case_id"] == case_id)
            run = orchestrator.run_case(
                case_id=case_id, clinical_text=case["clinical_text"],
                call_parser_fn=replay.parser_fn, call_enricher_fn=replay.enricher_fn,
                select_papers_fn=lambda a, u, **kw: replay.selection_fn(a, u, case_id=kw["case_id"]),
                validate_fn=lambda t, e, **kw: replay.validation_fn(
                    t, e, case_id=kw["case_id"], paper_id=kw["paper_id"]),
                source_units_by_id=da.load_source_unit_index(), budget=None,
                ledger=ledger, execution_mode=em.REPLAY, document_runtime=None)

        dossier_stage = next(s for s in run.stages if s.stage_id == "stage_13_dossier")
        therapies = dossier_stage.output_preview["dossier"]["candidate_therapies"]
        self.assertTrue(therapies, "la run deve produrre almeno una candidate")
        seen = 0
        for therapy in therapies:
            for voice in therapy["author_context"]:
                seen += 1
                self.assertIn("presentation_state", voice)
                self.assertIn(voice["presentation_state"], (
                    VALIDATED_QUOTE, REJECTED_QUOTE, ABSTAINED, PROPOSED_QUOTE_NOT_VALIDATED))
                if voice["presentation_state"] == VALIDATED_QUOTE:
                    self.assertTrue(voice["accepted_for_gates"],
                                    "presentabile ma non ammessa ai gate: incoerenza")
        self.assertGreater(seen, 0, "il dossier deve contenere author_context")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
