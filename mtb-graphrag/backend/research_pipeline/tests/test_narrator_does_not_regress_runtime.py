"""§33-35 — Il Narrator non riapre nessun blocker chiuso e non sposta l'autorità.

Verifica gli invarianti dichiarati dal §33 e la matrice dei confini del §35,
inclusa la riga nuova: il Dossier Narrator.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import data_access as da
from backend.research_pipeline import events as ev
from backend.research_pipeline import execution_mode as em
from backend.research_pipeline import orchestrator, replay
from backend.research_pipeline.cases.definitions import CASES
from backend.research_pipeline.contracts import (
    LLM_STAGE_IDS, PRESENTATION_STAGE_IDS, STAGE_SEQUENCE,
)
from backend.research_pipeline.determinism.gates import (
    NON_SUPPORTING_POLARITIES, candidate_direction_consistency, evaluate_association,
)
from backend.research_pipeline.dossier.builder import PRESENTABLE_AS_AUTHOR_CLAIM
from backend.research_pipeline.narrative import verifier as vf
from backend.research_pipeline.narrative.input_projection import build_narrator_input

CASE_ID = "CASE-1-therapy-evaluation-strong-match"


def _run(case_id=CASE_ID, **overrides):
    case = next(c for c in CASES if c["case_id"] == case_id)
    with tempfile.TemporaryDirectory() as tmp:
        ledger = EventLedger(Path(tmp) / "reg.sqlite3")
        kwargs = dict(
            case_id=case_id, clinical_text=case["clinical_text"],
            call_parser_fn=replay.parser_fn, call_enricher_fn=replay.enricher_fn,
            select_papers_fn=lambda a, u, **kw: replay.selection_fn(a, u, case_id=kw["case_id"]),
            validate_fn=lambda t, e, **kw: replay.validation_fn(
                t, e, case_id=kw["case_id"], paper_id=kw["paper_id"]),
            source_units_by_id=da.load_source_unit_index(), budget=None,
            ledger=ledger, execution_mode=em.REPLAY, document_runtime=None,
        )
        kwargs.update(overrides)
        run = orchestrator.run_case(**kwargs)
        events = [dict(e) for e in ledger.events_for_run(run.run_id)] \
            if hasattr(ledger, "events_for_run") else []
    return run, events


def _stages(run):
    return {s.stage_id: s for s in run.stages}


class CanonicalDossierPrecedesNarratorTest(unittest.TestCase):
    """§33.1"""

    def test_dossier_stage_precedes_narration_stages(self) -> None:
        run, _ = _run()
        order = [s.stage_id for s in run.stages]
        self.assertLess(order.index("stage_13_dossier"), order.index("stage_14_narrator"))
        self.assertLess(order.index("stage_14_narrator"),
                        order.index("stage_15_narrative_verifier"))

    def test_dossier_exists_even_when_narration_is_unavailable(self) -> None:
        run, _ = _run(call_narrator_fn=None)
        stages = _stages(run)
        self.assertEqual(stages["stage_13_dossier"].status, "SUCCEEDED")
        self.assertTrue(stages["stage_13_dossier"].output_preview["dossier"]["candidate_therapies"])

    def test_stage_sequence_declares_the_order(self) -> None:
        seq = list(STAGE_SEQUENCE)
        self.assertLess(seq.index("stage_13_dossier"), seq.index("stage_14_narrator"))
        self.assertLess(seq.index("stage_14_narrator"), seq.index("stage_15_narrative_verifier"))


class NarratorCannotChangeCanonicalStateTest(unittest.TestCase):
    """§33.2-7 — il dossier canonico è identico con e senza narrazione."""

    def _canonical(self, run):
        return _stages(run)["stage_13_dossier"].output_preview["dossier"]

    def test_canonical_dossier_is_byte_identical_with_and_without_narration(self) -> None:
        def hostile_narrator(case_id, narrator_input, run_index=0):
            """Un narratore che tenta di riscrivere tutto ciò che può."""
            return {"transport_result": "FORCED_TOOL_VALID", "narrative": {
                "narrative_summary": "PEMBROLIZUMAB è raccomandato e fortemente supportato.",
                "candidate_narratives": [
                    {"candidate_id": c["candidate_id"],
                     "text": "Status DIRECT, bucket PRIMARY_BUCKET, si raccomanda il farmaco."}
                    for c in narrator_input["candidates"]],
                "limitations_summary": "Nessuna limitazione.",
                "closing_note": "Procedere con la terapia.",
                "narrative_hash": "ostile"}}

        without, _ = _run(call_narrator_fn=None)
        with_hostile, _ = _run(call_narrator_fn=hostile_narrator)

        self.assertEqual(json.dumps(self._canonical(without), sort_keys=True),
                         json.dumps(self._canonical(with_hostile), sort_keys=True))

    def test_hostile_narrative_is_rejected_and_not_presented(self) -> None:
        def hostile_narrator(case_id, narrator_input, run_index=0):
            return {"transport_result": "FORCED_TOOL_VALID", "narrative": {
                "narrative_summary": "Si raccomanda PEMBROLIZUMAB.",
                "candidate_narratives": [
                    {"candidate_id": c["candidate_id"], "text": "È fortemente supportato."}
                    for c in narrator_input["candidates"]],
                "limitations_summary": "", "closing_note": "",
                "narrative_hash": "ostile"}}

        run, _ = _run(call_narrator_fn=hostile_narrator)
        preview = _stages(run)["stage_15_narrative_verifier"].output_preview
        self.assertEqual(preview["presentation_mode"], "STRUCTURED_DOSSIER_FALLBACK")
        self.assertIsNone(preview["verified_narrative"])
        self.assertFalse(preview["narrative_available"])

    def test_narration_never_touches_status_mask_or_gate(self) -> None:
        run, _ = _run(call_narrator_fn=None)
        entry = self._canonical(run)["candidate_therapies"][0]
        for stage_id in ("stage_14_narrator", "stage_15_narrative_verifier"):
            payload = json.dumps(_stages(run)[stage_id].output_preview)
            self.assertNotIn('"status": "DIRECT"', payload.replace(entry["status"], "«"))


class NarrativeVerifierIsDeterministicAndLlmFreeTest(unittest.TestCase):
    """§33.9-10"""

    def test_verifier_module_never_imports_an_llm_path(self) -> None:
        source = Path(vf.__file__).read_text(encoding="utf-8")
        for forbidden in ("requests", "call_narrator", "transport", "llm_config", "ollama"):
            self.assertNotIn(forbidden, source,
                             f"il verifier non deve dipendere da {forbidden}")

    def test_verifier_is_not_an_llm_stage(self) -> None:
        self.assertNotIn("stage_15_narrative_verifier", LLM_STAGE_IDS)
        self.assertIn("stage_14_narrator", LLM_STAGE_IDS)

    def test_verifier_result_is_reproducible(self) -> None:
        run, _ = _run(call_narrator_fn=None)
        dossier = self_dossier = _stages(run)["stage_13_dossier"].output_preview["dossier"]
        narrator_input = build_narrator_input(self_dossier)
        narrative = {"narrative_summary": "x", "candidate_narratives": [],
                     "limitations_summary": "y", "closing_note": "z", "narrative_hash": "h"}
        first = vf.verify_narrative(dossier, narrator_input, narrative)
        second = vf.verify_narrative(dossier, narrator_input, narrative)
        self.assertEqual(vf.result_fingerprint(first), vf.result_fingerprint(second))


class FallbackPolicyTest(unittest.TestCase):
    """§33.8 e §17 — un fallimento produce il fallback, non un secondo LLM."""

    def test_failure_produces_structured_fallback(self) -> None:
        def bad_narrator(case_id, narrator_input, run_index=0):
            return {"transport_result": "FORCED_TOOL_VALID", "narrative": {
                "narrative_summary": "Si raccomanda la terapia.",
                "candidate_narratives": [], "limitations_summary": "", "closing_note": "",
                "narrative_hash": "h"}}

        run, _ = _run(call_narrator_fn=bad_narrator)
        preview = _stages(run)["stage_15_narrative_verifier"].output_preview
        self.assertEqual(preview["presentation_mode"], "STRUCTURED_DOSSIER_FALLBACK")
        self.assertTrue(preview["fallback_reason"])

    def test_narrator_is_called_exactly_once(self) -> None:
        """Nessun retry semantico: un fallimento non richiama il modello."""
        calls = []

        def counting_narrator(case_id, narrator_input, run_index=0):
            calls.append(case_id)
            return {"transport_result": "FORCED_TOOL_VALID", "narrative": {
                "narrative_summary": "Si raccomanda la terapia.",
                "candidate_narratives": [], "limitations_summary": "", "closing_note": "",
                "narrative_hash": "h"}}

        _run(call_narrator_fn=counting_narrator)
        self.assertEqual(len(calls), 1)

    def test_narration_stages_are_declared_as_presentation(self) -> None:
        self.assertEqual(PRESENTATION_STAGE_IDS,
                         frozenset({"stage_14_narrator", "stage_15_narrative_verifier"}))


class ClosedBlockersDoNotReopenTest(unittest.TestCase):
    """§34 — ISS-001, ISS-002, ISS-003 restano chiusi."""

    def test_iss_002_negative_polarity_still_never_promoted(self) -> None:
        candidate = {"candidate_id": "X", "direction": "Does Not Support"}
        accepted = [{"validation_outcome": "ENRICHMENT_ACCEPTED",
                     "enrichment": {"evidence_kind": "RESPONSE"}}]
        result = evaluate_association("THERAPY_EVALUATION", candidate, accepted)
        self.assertNotEqual(result["gate_bucket"], "PRIMARY_BUCKET")
        self.assertNotEqual(result["support_mask"]["direction"], "SUPPORTED")
        self.assertNotEqual(candidate_direction_consistency(candidate, "RESPONSE"), "CONSISTENT")
        self.assertIn("DOES_NOT_SUPPORT", NON_SUPPORTING_POLARITIES)

    def test_iss_001_controlled_stop_still_works(self) -> None:
        from backend.research_pipeline.contracts import is_controlled_stop

        run, _ = _run("CASE-5-casecontext-mismatch-no-match", call_narrator_fn=None)
        self.assertEqual(run.status, "STOPPED")
        self.assertTrue(is_controlled_stop(run.stopped_at))

    def test_iss_003_rejected_quotes_still_not_presentable(self) -> None:
        self.assertEqual(PRESENTABLE_AS_AUTHOR_CLAIM, frozenset({"VALIDATED_QUOTE"}))

    def test_rejected_quote_does_not_reach_the_narrator(self) -> None:
        """Il Narrator non puo' narrare cio' che non riceve."""
        run, _ = _run("CASE-2-therapy-discovery", call_narrator_fn=None)
        dossier = _stages(run)["stage_13_dossier"].output_preview["dossier"]
        rejected = [v["author_claim_quote"] for e in dossier["candidate_therapies"]
                    for v in e["author_context"]
                    if v.get("presentation_state") == "REJECTED_QUOTE"
                    and v.get("author_claim_quote")]
        self.assertTrue(rejected, "CASE-2 deve contenere una quote rigettata")
        projected = json.dumps(build_narrator_input(dossier), ensure_ascii=False)
        for quote in rejected:
            self.assertNotIn(quote, projected)


class Rq3BoundaryMatrixTest(unittest.TestCase):
    """§35 — la matrice dei confini, aggiornata con il Narrator."""

    def test_llm_stages_are_exactly_three(self) -> None:
        self.assertEqual(LLM_STAGE_IDS, frozenset({
            "stage_2_casecontext_parser", "stage_9_paper_context_enricher",
            "stage_14_narrator"}))

    def test_narrator_output_schema_is_closed(self) -> None:
        """Il Narrator non puo' creare candidate, provenance o quote validate."""
        from backend.research_pipeline.narrative.prompt import TOOL_SCHEMA

        self.assertFalse(TOOL_SCHEMA["additionalProperties"])
        self.assertEqual(set(TOOL_SCHEMA["properties"]), {
            "narrative_summary", "candidate_narratives", "limitations_summary", "closing_note"})
        item = TOOL_SCHEMA["properties"]["candidate_narratives"]["items"]
        self.assertFalse(item["additionalProperties"])
        self.assertEqual(set(item["properties"]), {"candidate_id", "text"})

    def test_narrator_transport_rejects_extra_keys(self) -> None:
        from backend.research_pipeline.narrative.narrator import _argument_errors

        base = {"narrative_summary": "a", "candidate_narratives": [],
                "limitations_summary": "b", "closing_note": "c"}
        self.assertEqual(_argument_errors(base), [])
        for extra in ("canonical_status", "support_mask", "gate_bucket", "provenance", "pmid"):
            with self.subTest(extra=extra):
                errors = _argument_errors({**base, extra: "x"})
                self.assertTrue(any("EXTRA_KEYS" in e for e in errors))

    def test_narration_events_are_emitted_as_domain_events(self) -> None:
        for event_type in (ev.NARRATION_GENERATED, ev.NARRATION_VERIFIED,
                           ev.NARRATION_REJECTED, ev.STRUCTURED_FALLBACK_USED):
            self.assertIn(event_type, ev.DOMAIN_EVENT_TYPES)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
