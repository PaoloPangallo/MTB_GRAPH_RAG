import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

from backend.pipeline.agentic.ledger import EventLedger
from backend.pipeline.agentic.runtime import run_agentic_collection
from backend.pipeline.agentic.source_verifier import _parse_results, verify_evidence_items


class _Response:
    def __init__(self, content):
        self.content = content


class _SequencedLLM:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.messages = []

    def invoke(self, messages):
        self.messages.append(messages)
        return _Response(json.dumps(next(self.payloads)))


class _FailingLLM:
    """Simula un planner sempre irraggiungibile, con un messaggio di eccezione
    che conterrebbe dettagli interni se venisse mai propagato grezzo — usato
    per verificare che il fallback non lo esponga mai."""

    def __init__(self):
        self.call_count = 0

    def invoke(self, messages):
        self.call_count += 1
        raise RuntimeError("connection refused to internal-host:11434 api_key=secret123")


class EventLedgerTest(TestCase):
    def test_ledger_is_hash_chained_and_database_blocks_mutation(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite3"
            ledger = EventLedger(path)
            first = ledger.append("run-1", "started", "controller", {"case": "synthetic"})
            second = ledger.append("run-1", "completed", "tool", {"records": 2})

            self.assertEqual(first["sequence"], 1)
            self.assertEqual(second["previous_hash"], first["event_hash"])
            self.assertTrue(ledger.verify_chain("run-1"))

            connection = sqlite3.connect(path)
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "UPDATE agent_events SET actor = 'tampered' WHERE run_id = 'run-1'"
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("DELETE FROM agent_events WHERE run_id = 'run-1'")
            finally:
                connection.close()


class AgenticRuntimeTest(TestCase):
    def _tools(self):
        def update(**values):
            return lambda state: {**state, **values}

        return {
            "assess_complexity": update(complexity="high"),
            "interpret_variant": update(variant_data={"evidence_records": [{"pmid": 1}]}),
            "identify_targets": update(drug_candidates=[{"drug_name": "Drug A"}]),
            "match_trials": update(trial_candidates=[{"nct_id": "NCT1"}]),
            "check_resistance": update(resistance_data=[]),
            "enrich_oncokb": update(oncokb_enrichment=[]),
        }

    def _initial_state(self):
        return {
            "gene": "EGFR",
            "variant": "L858R",
            "tumor_type": "Lung Adenocarcinoma",
            "alteration_type": "point_mutation",
            "therapy_line": "first-line",
            "enrich_with_oncokb": False,
            "complexity": "low",
            "variant_data": {},
            "drug_candidates": [],
            "trial_candidates": [],
            "resistance_data": [],
            "oncokb_enrichment": [],
        }

    def test_planner_selects_tools_iteratively_and_logs_each_call(self):
        decisions = [
            {"tool": "interpret_variant", "rationale": "Raccolgo l'evidenza primaria."},
            {"tool": "assess_complexity", "rationale": "Valuto l'ampiezza del caso."},
            {"tool": "check_resistance", "rationale": "Cerco meccanismi di resistenza."},
            {"tool": "identify_targets", "rationale": "Cerco farmaci collegati."},
            {"tool": "match_trials", "rationale": "Cerco studi pertinenti."},
            {"tool": "finish", "rationale": "La raccolta è sufficiente."},
        ]

        with TemporaryDirectory() as directory:
            ledger = EventLedger(Path(directory) / "events.sqlite3")
            result = run_agentic_collection(
                self._initial_state(),
                ledger=ledger,
                planner_llm=_SequencedLLM(decisions),
                tool_registry=self._tools(),
            )

        self.assertEqual(result.planning_mode, "llm_dynamic")
        self.assertIsNone(result.fallback_reason)
        self.assertEqual(result.tool_path, [
            "interpret_variant",
            "assess_complexity",
            "check_resistance",
            "identify_targets",
            "match_trials",
        ])
        self.assertTrue(result.ledger_valid)
        self.assertEqual(
            sum(event["event_type"] == "tool_completed" for event in result.events),
            5,
        )
        self.assertEqual(result.planner_attempts, 6)
        self.assertEqual(len(result.tool_call_timings), 5)
        self.assertEqual(result.tool_call_timings[0]["tool"], "interpret_variant")
        self.assertEqual(result.tool_call_timings[0]["sequence"], 1)
        self.assertEqual(result.tool_call_timings[0]["status"], "completed")

    def test_planner_failure_triggers_a_single_fallback_transition_per_run(self):
        """Il planner può fallire una sola volta per run: dopo la prima
        transizione a safe_fallback non deve più essere richiamato, anche se
        restano molti altri step da completare."""
        failing_llm = _FailingLLM()
        with TemporaryDirectory() as directory:
            ledger = EventLedger(Path(directory) / "events.sqlite3")
            result = run_agentic_collection(
                self._initial_state(),
                ledger=ledger,
                planner_llm=failing_llm,
                tool_registry=self._tools(),
            )

        self.assertEqual(result.planning_mode, "safe_fallback")
        # 1 tentativo iniziale + PLANNER_MAX_RETRIES (default 1) = 2 chiamate
        # totali, mai moltiplicate per i 6 step successivi del piano sicuro.
        self.assertEqual(failing_llm.call_count, 2)
        self.assertEqual(result.planner_attempts, 2)
        self.assertEqual(
            result.tool_path,
            ["assess_complexity", "interpret_variant", "identify_targets", "check_resistance", "match_trials"],
        )

    def test_fallback_reason_is_sanitized_and_excludes_raw_exception_text(self):
        failing_llm = _FailingLLM()
        with TemporaryDirectory() as directory:
            ledger = EventLedger(Path(directory) / "events.sqlite3")
            result = run_agentic_collection(
                self._initial_state(),
                ledger=ledger,
                planner_llm=failing_llm,
                tool_registry=self._tools(),
            )

        self.assertIn(
            result.fallback_reason,
            {"timeout", "invalid_json", "service_unavailable", "budget_exhausted", "other"},
        )
        serialized_events = json.dumps(result.events, default=str)
        self.assertNotIn("secret123", serialized_events)
        self.assertNotIn("internal-host", serialized_events)
        self.assertNotIn("secret123", result.fallback_reason)

    def test_planner_fallback_event_is_recorded_once_in_the_ledger(self):
        failing_llm = _FailingLLM()
        with TemporaryDirectory() as directory:
            ledger = EventLedger(Path(directory) / "events.sqlite3")
            result = run_agentic_collection(
                self._initial_state(),
                ledger=ledger,
                planner_llm=failing_llm,
                tool_registry=self._tools(),
            )

        fallback_events = [
            event for event in result.events if event["event_type"] == "planner_fallback_triggered"
        ]
        self.assertEqual(len(fallback_events), 1)
        self.assertEqual(fallback_events[0]["payload"]["reason_category"], result.fallback_reason)
        self.assertTrue(result.ledger_valid)


class SourceVerifierTest(TestCase):
    def _item(self, source_id="PMID:29151359", object_="EGFR L858R"):
        return SimpleNamespace(
            subject="EGFR L858R",
            relation="Sensitivity/Response",
            object=object_,
            context="Lung Adenocarcinoma",
            source_id=source_id,
            evidence_statement="Osimertinib improved progression-free survival in untreated EGFR-mutated NSCLC.",
            citation_text="Soria et al., 2018",
            evidence_level="A",
        )

    def _source_loader(self):
        return lambda _pmids: {
            29151359: {
                "title": "Osimertinib in untreated EGFR-mutated NSCLC",
                "abstract": "The trial enrolled patients with EGFR-mutated advanced NSCLC.",
            }
        }

    def test_verifier_requires_semantic_support_from_pubmed(self):
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "Variante e tumore coincidono.",
            "applicability_status": "compatible",
            "applicability_reason": "Setting e linea dichiarati coincidono.",
        }]])
        results = verify_evidence_items(
            [self._item()],
            llm_client=llm,
            source_loader=self._source_loader(),
        )
        self.assertEqual(results[0].source_support_status, "supported")
        self.assertEqual(results[0].verification_level, "pubmed_abstract")
        self.assertFalse(results[0].requires_source_review)

    def test_parser_accepts_langchain_text_content_blocks(self):
        content = [{
            "type": "text",
            "text": (
                "```json\n[{\"index\": 0, \"source_support_status\": \"supported\", "
                "\"source_support_reason\": \"ok\", \"applicability_status\": \"compatible\", "
                "\"applicability_reason\": \"ok\"}]\n```"
            ),
        }]
        parsed = _parse_results(content)
        self.assertEqual(parsed[0][0], "supported")
        self.assertEqual(parsed[0][6], "compatible")

    def test_requested_therapy_line_is_sent_to_the_semantic_verifier(self):
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "La fonte descrive il proprio contesto.",
            "applicability_status": "indeterminate",
            "applicability_reason": "Setting adiuvante non dichiarato dal paziente.",
        }]])
        results = verify_evidence_items(
            [self._item()],
            llm_client=llm,
            source_loader=self._source_loader(),
            case_context={"therapy_line": "first-line"},
        )

        sent_payload = json.loads(llm.messages[0][1][1])
        self.assertEqual(sent_payload[0]["requested_case"]["therapy_line"], "first-line")
        self.assertEqual(results[0].applicability_status, "indeterminate")

    def test_missing_original_source_fails_closed(self):
        results = verify_evidence_items(
            [self._item()],
            llm_client=_SequencedLLM([]),
            source_loader=lambda _pmids: {},
        )
        self.assertEqual(results[0].source_support_status, "uncertain")
        self.assertTrue(results[0].requires_source_review)
        self.assertEqual(results[0].applicability_status, "indeterminate")

    def test_clinical_anchor_mismatch_fails_closed_before_llm(self):
        item = self._item(object_="unrelated-drug")
        results = verify_evidence_items(
            [item],
            llm_client=_SequencedLLM([]),
            source_loader=self._source_loader(),
        )
        self.assertEqual(results[0].source_support_status, "uncertain")
        self.assertEqual(results[0].verification_level, "clinical_rules")

    def test_missing_or_invalid_pmid_is_uncertain_not_unsupported(self):
        """Un PMID assente o non valido è un dato insufficiente, non una
        contraddizione: deve produrre 'uncertain', mai 'unsupported'."""
        for source_id in (None, "not-a-pmid", "PMID:abc"):
            with self.subTest(source_id=source_id):
                item = self._item(source_id=source_id)
                results = verify_evidence_items(
                    [item],
                    llm_client=_SequencedLLM([]),
                    source_loader=lambda _pmids: {},
                )
                self.assertEqual(results[0].source_support_status, "uncertain")
                self.assertEqual(results[0].verification_level, "provenance")

    def test_supported_source_with_incompatible_setting_is_not_compatible(self):
        """Fonte documentalmente supportata (T790M post-progressione) ma con
        setting esplicitamente incompatibile con una richiesta first-line:
        il supporto resta 'supported', l'applicabilità diventa 'not_compatible' —
        non deve mai ricadere in un generico bucket di supporto incerto."""
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": (
                "La fonte documenta attività di osimertinib in NSCLC EGFR T790M "
                "dopo progressione a un precedente EGFR-TKI."
            ),
            "source_population": "NSCLC EGFR T790M",
            "source_line": "seconda linea",
            "source_setting": "post-progressione",
            "source_prerequisites": "progressione a un precedente EGFR-TKI",
            "applicability_status": "not_compatible",
            "applicability_reason": (
                "La richiesta è esplicitamente first-line; la fonte riguarda solo "
                "pazienti già progrediti a un precedente EGFR-TKI."
            ),
        }]])
        results = verify_evidence_items(
            [self._item()],
            llm_client=llm,
            source_loader=self._source_loader(),
            case_context={"therapy_line": "first-line"},
        )
        result = results[0]
        self.assertEqual(result.source_support_status, "supported")
        self.assertEqual(result.applicability_status, "not_compatible")
        self.assertEqual(result.source_setting, "post-progressione")
        self.assertFalse(result.requires_source_review)
        self.assertTrue(result.requires_clinical_review)

    def test_supported_source_with_missing_stage_is_indeterminate(self):
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "La fonte documenta il proprio record.",
            "applicability_status": "indeterminate",
            "applicability_reason": "Stadio del paziente non dichiarato: impossibile decidere.",
        }]])
        results = verify_evidence_items(
            [self._item()],
            llm_client=llm,
            source_loader=self._source_loader(),
            case_context={"therapy_line": "first-line", "disease_stage": ""},
        )
        self.assertEqual(results[0].source_support_status, "supported")
        self.assertEqual(results[0].applicability_status, "indeterminate")
        self.assertTrue(results[0].requires_clinical_review)

    def test_source_genuinely_contradicts_biomarker_is_unsupported(self):
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "unsupported",
            "source_support_reason": (
                "La fonte riguarda KRAS G12C, non EGFR L858R: contraddice il biomarker della claim."
            ),
            "applicability_status": "indeterminate",
            "applicability_reason": "Applicabilità non valutabile: il supporto documentale è stato rifiutato.",
        }]])
        results = verify_evidence_items(
            [self._item()],
            llm_client=llm,
            source_loader=self._source_loader(),
        )
        self.assertEqual(results[0].source_support_status, "unsupported")
        self.assertTrue(results[0].requires_source_review)

    def test_no_first_line_metastatic_inference_in_payload_sent_to_llm(self):
        """La richiesta non deve mai essere riscritta: stadio/setting/terapie
        pregresse dichiarati vuoti restano vuoti nel payload inviato all'LLM,
        non vengono sostituiti con valori dedotti (es. 'metastatic')."""
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "uncertain",
            "source_support_reason": "Verifica non completata nel fixture.",
            "applicability_status": "indeterminate",
            "applicability_reason": "Dati clinici del paziente non dichiarati.",
        }]])
        verify_evidence_items(
            [self._item()],
            llm_client=llm,
            source_loader=self._source_loader(),
            case_context={
                "therapy_line": "first-line",
                "disease_stage": "",
                "disease_setting": "",
                "prior_therapies": "",
                "co_alterations": "",
            },
        )
        sent_payload = json.loads(llm.messages[0][1][1])
        requested = sent_payload[0]["requested_case"]
        self.assertEqual(requested["disease_stage"], "")
        self.assertEqual(requested["disease_setting"], "")
        self.assertEqual(requested["prior_therapies"], "")
        self.assertEqual(requested["co_alterations"], "")

    def test_requires_source_review_and_requires_clinical_review_are_independent(self):
        """I due booleani non devono mai collassare in un solo OR: una fonte
        supportata ma non compatibile richiede revisione clinica senza
        richiedere revisione della fonte, e viceversa per una fonte
        realmente non supportata."""
        supported_not_compatible = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "Supportata nel proprio contesto.",
            "applicability_status": "not_compatible",
            "applicability_reason": "Setting incompatibile con la richiesta.",
        }]])
        result_a = verify_evidence_items(
            [self._item()], llm_client=supported_not_compatible, source_loader=self._source_loader(),
        )[0]
        self.assertFalse(result_a.requires_source_review)
        self.assertTrue(result_a.requires_clinical_review)

        unsupported = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "unsupported",
            "source_support_reason": "Contraddice il biomarker.",
            "applicability_status": "indeterminate",
            "applicability_reason": "Non valutabile.",
        }]])
        result_b = verify_evidence_items(
            [self._item()], llm_client=unsupported, source_loader=self._source_loader(),
        )[0]
        self.assertTrue(result_b.requires_source_review)
        self.assertTrue(result_b.requires_clinical_review)
