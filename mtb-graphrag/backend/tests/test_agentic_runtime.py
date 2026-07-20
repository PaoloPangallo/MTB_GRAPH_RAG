import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

from backend.pipeline.agentic.ledger import EventLedger
from backend.pipeline.agentic.runtime import mandatory_tools_for_goal, run_agentic_collection
from backend.pipeline.agentic.source_profile_cache import InMemorySourceProfileCache
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


class _PartialThenRecoveringLLM:
    """Simula un batch che risponde solo per il primo indice (l'indice
    successivo resta mancante, senza sollevare un'eccezione) e un retry a
    singolo record che lo recupera con successo."""

    def invoke(self, messages):
        payload = json.loads(messages[1][1])
        first = payload[0]
        reason = "recuperato dal retry" if len(payload) == 1 and first["index"] != 0 else "ok"
        return _Response(json.dumps([{
            "index": first["index"],
            "source_support_status": "supported",
            "source_support_reason": reason,
            "applicability_status": "indeterminate",
            "applicability_reason": "ok",
        }]))


class _AlwaysFailingLLM:
    """Simula un servizio sempre irraggiungibile: sia il batch iniziale sia
    il retry a singolo record devono fallire e degradare a 'uncertain'."""

    def invoke(self, messages):
        raise RuntimeError("errore simulato del servizio LLM")


class MandatoryToolsForGoalTest(TestCase):
    def test_general_review_requires_all_four_core_tools(self):
        self.assertEqual(
            set(mandatory_tools_for_goal("general-review")),
            {"interpret_variant", "identify_targets", "check_resistance", "match_trials"},
        )

    def test_unset_or_unknown_goal_defaults_to_general_review_policy(self):
        self.assertEqual(mandatory_tools_for_goal(None), mandatory_tools_for_goal("general-review"))
        self.assertEqual(mandatory_tools_for_goal("something-else"), mandatory_tools_for_goal("general-review"))

    def test_specific_goals_have_narrower_explicit_policies(self):
        self.assertEqual(set(mandatory_tools_for_goal("resistance")), {"interpret_variant", "check_resistance"})
        self.assertEqual(set(mandatory_tools_for_goal("clinical-trials")), {"interpret_variant", "match_trials"})
        self.assertEqual(set(mandatory_tools_for_goal("treatment-evidence")), {"interpret_variant", "identify_targets"})


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

    def test_finish_is_blocked_until_mandatory_tools_for_the_goal_are_completed(self):
        """Riproduce la regressione osservata nel run reale: il planner tenta
        di terminare dopo interpret_variant/identify_targets/match_trials,
        saltando check_resistance. Il controller deve impedirlo: 'finish' non
        è mai negli strumenti consentiti finché la policy minima per
        l'obiettivo MTB non è soddisfatta — il planner viene forzato al
        piano sicuro, che completa lo strumento mancante prima di finire."""
        decisions = [
            {"tool": "assess_complexity", "rationale": "Valuto l'ampiezza del caso."},
            {"tool": "interpret_variant", "rationale": "Raccolgo l'evidenza primaria."},
            {"tool": "identify_targets", "rationale": "Cerco farmaci collegati."},
            {"tool": "match_trials", "rationale": "Cerco studi pertinenti."},
            {"tool": "finish", "rationale": "La raccolta sembra sufficiente."},
        ]
        state = self._initial_state()
        state["mtb_goal"] = "general-review"
        with TemporaryDirectory() as directory:
            ledger = EventLedger(Path(directory) / "events.sqlite3")
            result = run_agentic_collection(
                state,
                ledger=ledger,
                planner_llm=_SequencedLLM(decisions),
                tool_registry=self._tools(),
            )
        self.assertIn("check_resistance", result.tool_path)
        self.assertEqual(result.missing_mandatory_tools, [])
        self.assertEqual(
            set(result.mandatory_tools),
            {"interpret_variant", "identify_targets", "check_resistance", "match_trials"},
        )

    def test_tool_failure_is_sanitized_and_excludes_raw_exception_text(self):
        """Un'eccezione sollevata da un tool non deve mai finire grezza nel
        ledger né in AgenticCollectionResult.errors (che alimenta le
        limitations restituite dall'API): solo una categoria sanitizzata."""
        def failing_tool(state):
            raise RuntimeError("upstream failure token=sekrit123 at postgres://user:pass@internal-host/db")

        tools = self._tools()
        tools["check_resistance"] = failing_tool
        decisions = [
            {"tool": "interpret_variant", "rationale": "Raccolgo l'evidenza primaria."},
            {"tool": "check_resistance", "rationale": "Cerco meccanismi di resistenza."},
        ]

        with TemporaryDirectory() as directory:
            ledger = EventLedger(Path(directory) / "events.sqlite3")
            result = run_agentic_collection(
                self._initial_state(),
                ledger=ledger,
                planner_llm=_SequencedLLM(decisions),
                tool_registry=tools,
            )

        serialized_events = json.dumps(result.events, default=str)
        self.assertNotIn("sekrit123", serialized_events)
        self.assertNotIn("postgres://", serialized_events)
        self.assertNotIn("internal-host", serialized_events)
        joined_errors = " ".join(result.errors)
        self.assertNotIn("sekrit123", joined_errors)
        self.assertNotIn("postgres://", joined_errors)
        self.assertTrue(any(
            category in joined_errors
            for category in (
                "timeout durante l'esecuzione",
                "risposta dello strumento non conforme",
                "servizio esterno non disponibile",
                "dati insufficienti o non validi",
                "errore non classificato",
            )
        ))
        failed_events = [event for event in result.events if event["event_type"] == "tool_failed"]
        self.assertEqual(len(failed_events), 1)
        self.assertIn(
            failed_events[0]["payload"]["error_category"],
            {"timeout", "invalid_response", "service_unavailable", "data_error", "other"},
        )

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
            "source_line_category": "post_progression",
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

    def test_aura3_supports_claim_with_derived_verified_claim_not_unsupported(self):
        """PMID 27959700 (AURA3): la fonte non contraddice EGFR L858R — riguarda
        L858R in presenza di T790M e dopo progressione a un precedente
        EGFR-TKI. Non deve diventare 'unsupported' solo perché la claim del KG
        è più generica: resta 'supported', con una derived_verified_claim
        contestualizzata. L'applicabilità resta 'not_compatible' per il
        conflitto esplicito first-line (caso) contro post-progressione
        (fonte)."""
        item = self._item(source_id="PMID:27959700", object_="osimertinib")
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "La fonte documenta attività di osimertinib in EGFR L858R con T790M dopo progressione a un precedente EGFR-TKI.",
            "source_population": "EGFR L858R con T790M",
            "source_line": "seconda linea",
            "source_setting": "post-progressione",
            "source_prerequisites": "progressione a un precedente EGFR-TKI",
            "source_line_category": "post_progression",
            "applicability_status": "not_compatible",
            "applicability_reason": "Richiesta first-line; la fonte riguarda pazienti post-progressione.",
        }]])
        results = verify_evidence_items(
            [item],
            llm_client=llm,
            source_loader=lambda _pmids: {
                27959700: {
                    "title": "Osimertinib in EGFR T790M-Positive Advanced NSCLC (AURA3)",
                    "abstract": "Patients with EGFR L858R and T790M progressed on a prior EGFR-TKI before receiving osimertinib.",
                }
            },
            case_context={"therapy_line": "first-line"},
        )
        result = results[0]
        self.assertEqual(result.source_support_status, "supported")
        self.assertNotEqual(result.source_support_status, "unsupported")
        self.assertIsNotNone(result.derived_verified_claim)
        self.assertIn("T790M", result.derived_verified_claim)
        self.assertIn("progressione", result.derived_verified_claim.lower())
        self.assertEqual(result.applicability_status, "not_compatible")

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

    def _regimen_source_loader(self):
        return lambda _pmids: {
            37879444: {
                "title": "Amivantamab plus carboplatino and pemetrexed in EGFR-mutated NSCLC",
                "abstract": "Patients with EGFR L858R NSCLC were treated with amivantamab, carboplatino and pemetrexed.",
            }
        }

    def test_partial_regimen_is_not_confirmed_as_the_full_source_regimen(self):
        """PMID 37879444: la fonte descrive un unico braccio amivantamab +
        carboplatino + pemetrexed, ma la claim riguarda solo amivantamab +
        carboplatino. Il supporto non deve restare 'supported' senza riserva:
        la claim è un sottoinsieme proprio del braccio ('partial'), quindi
        diventa 'uncertain'."""
        item = self._item(object_="amivantamab + carboplatino", source_id="PMID:37879444")
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "La fonte documenta il regime nel proprio contesto.",
            "source_arms": [{"arm_name": "braccio sperimentale", "interventions": ["amivantamab", "carboplatino", "pemetrexed"]}],
            "applicability_status": "indeterminate",
            "applicability_reason": "Dati clinici del paziente non dichiarati.",
        }]])
        results = verify_evidence_items(
            [item],
            llm_client=llm,
            source_loader=self._regimen_source_loader(),
        )
        result = results[0]
        self.assertEqual(result.claim_arm_match, "partial")
        self.assertEqual(result.source_support_status, "uncertain")
        self.assertIn("pemetrexed", result.source_support_reason.lower())
        self.assertTrue(result.requires_source_review)

    def test_multi_drug_claim_with_no_source_arms_reported_is_uncertain(self):
        """PMID 37879444: se l'LLM non riporta affatto source_arms per una
        claim a più farmaci, il regime non è verificabile ('unknown').
        Fail-closed a 'uncertain', mai 'supported' senza riserva."""
        item = self._item(object_="amivantamab + carboplatino + pemetrexed", source_id="PMID:37879444")
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "La fonte documenta il regime.",
            "applicability_status": "indeterminate",
            "applicability_reason": "Dati clinici del paziente non dichiarati.",
        }]])  # nessun source_arms nella risposta dell'LLM
        results = verify_evidence_items(
            [item],
            llm_client=llm,
            source_loader=self._regimen_source_loader(),
        )
        result = results[0]
        self.assertEqual(result.claim_arm_match, "unknown")
        self.assertEqual(result.source_support_status, "uncertain")
        self.assertTrue(result.requires_source_review)

    def test_comparator_arm_drugs_are_never_merged_into_the_claim_arm(self):
        """MARIPOSA: osimertinib è il comparatore in un braccio separato, non
        parte del regime amivantamab + lazertinib. Un'estrazione piatta
        unirebbe erroneamente i tre farmaci; qui i bracci restano separati e
        la claim del braccio sperimentale resta 'exact'."""
        item = self._item(object_="amivantamab + lazertinib", source_id="PMID:37879444")
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "La fonte documenta il braccio sperimentale.",
            "source_arms": [
                {"arm_name": "amivantamab+lazertinib", "interventions": ["amivantamab", "lazertinib"]},
                {"arm_name": "osimertinib (comparatore)", "interventions": ["osimertinib"]},
                {"arm_name": "lazertinib monoterapia", "interventions": ["lazertinib"]},
            ],
            "applicability_status": "indeterminate",
            "applicability_reason": "Dati clinici del paziente non dichiarati.",
        }]])
        results = verify_evidence_items(
            [item],
            llm_client=llm,
            source_loader=self._regimen_source_loader(),
        )
        result = results[0]
        self.assertEqual(result.claim_arm_match, "exact")
        self.assertEqual(result.source_support_status, "supported")

    def test_erlotinib_first_line_advanced_with_missing_patient_stage_and_setting_is_indeterminate(self):
        """Regressione richiesta: fonte con categorie complete (first_line /
        metastatic / treatment_naive), ma il caso dichiara solo
        therapy_line='first-line' — stadio, setting e terapie precedenti del
        paziente mancano. L'applicabilità finale deve restare 'indeterminate',
        anche se l'LLM avesse restituito 'compatible'."""
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "La fonte documenta erlotinib first-line in NSCLC avanzato EGFR-mutato.",
            "source_line_category": "first_line",
            "source_setting_category": "metastatic",
            "source_prior_therapy_requirement": "treatment_naive",
            "applicability_status": "compatible",
            "applicability_reason": "Le linee coincidono.",
        }]])
        results = verify_evidence_items(
            [self._item(object_="erlotinib")],
            llm_client=llm,
            source_loader=self._source_loader(),
            case_context={"therapy_line": "first-line", "disease_stage": "", "disease_setting": "", "prior_therapies": ""},
        )
        self.assertEqual(results[0].applicability_status, "indeterminate")

    def test_matching_full_regimen_stays_supported(self):
        item = self._item(object_="amivantamab + carboplatino + pemetrexed", source_id="PMID:37879444")
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "La fonte documenta il regime completo.",
            "source_arms": [{"arm_name": "braccio unico", "interventions": ["amivantamab", "carboplatino", "pemetrexed"]}],
            "applicability_status": "indeterminate",
            "applicability_reason": "Dati clinici del paziente non dichiarati.",
        }]])
        results = verify_evidence_items(
            [item],
            llm_client=llm,
            source_loader=self._regimen_source_loader(),
        )
        self.assertEqual(results[0].claim_arm_match, "exact")
        self.assertEqual(results[0].source_support_status, "supported")

    def test_retry_recovers_a_missing_item_from_a_partial_batch(self):
        """Un batch che risponde solo per un indice non deve far cadere
        l'altro record in un fallimento definitivo: il singolo indice
        mancante viene recuperato con un retry bounded a singolo record."""
        item_a = self._item(source_id="PMID:29151359")
        item_b = self._item(source_id="PMID:29151359")
        metrics: dict[str, int] = {}
        results = verify_evidence_items(
            [item_a, item_b],
            llm_client=_PartialThenRecoveringLLM(),
            source_loader=self._source_loader(),
            metrics=metrics,
        )
        self.assertEqual(results[0].source_support_status, "supported")
        self.assertEqual(results[1].source_support_status, "supported")
        self.assertEqual(results[1].source_support_reason, "recuperato dal retry")
        self.assertEqual(metrics["verifier_batches"], 1)
        self.assertEqual(metrics["retry_items"], 1)
        self.assertEqual(metrics["recovered_items"], 1)
        self.assertEqual(metrics["permanently_failed_items"], 0)
        self.assertEqual(metrics["cache_hits"], 0)
        self.assertEqual(metrics["cache_misses"], 2)

    def test_retry_that_fails_again_degrades_to_uncertain_not_an_exception(self):
        """Nessun retry infinito: se anche il retry a singolo record fallisce,
        il risultato degrada in modo fail-closed a 'uncertain', senza
        propagare l'eccezione grezza al chiamante."""
        metrics: dict[str, int] = {}
        results = verify_evidence_items(
            [self._item()],
            llm_client=_AlwaysFailingLLM(),
            source_loader=self._source_loader(),
            metrics=metrics,
        )
        self.assertEqual(results[0].source_support_status, "uncertain")
        self.assertTrue(results[0].requires_source_review)
        self.assertEqual(metrics["verifier_batches"], 1)
        self.assertEqual(metrics["failed_batches"], 1)
        self.assertEqual(metrics["retry_items"], 1)
        self.assertEqual(metrics["recovered_items"], 0)
        self.assertEqual(metrics["permanently_failed_items"], 1)

    def test_default_concurrency_is_a_single_worker(self):
        """Con un singolo endpoint Ollama, la concorrenza predefinita deve
        essere 1 sia per i batch iniziali sia per il retry, per non
        sovraccaricare il servizio."""
        from backend.pipeline.agentic import source_verifier

        self.assertEqual(source_verifier._max_workers(), 1)
        self.assertEqual(source_verifier._retry_max_workers(), 1)

    def test_max_workers_is_configurable_via_env_var(self):
        import os
        from backend.pipeline.agentic import source_verifier

        original = os.environ.get("SOURCE_VERIFIER_MAX_WORKERS")
        os.environ["SOURCE_VERIFIER_MAX_WORKERS"] = "3"
        try:
            self.assertEqual(source_verifier._max_workers(), 3)
        finally:
            if original is None:
                os.environ.pop("SOURCE_VERIFIER_MAX_WORKERS", None)
            else:
                os.environ["SOURCE_VERIFIER_MAX_WORKERS"] = original

    def test_second_call_with_same_pmid_is_served_from_cache_no_llm_call(self):
        """Il profilo della fonte (asse del supporto, indipendente dal
        paziente) viene letto da cache al secondo giro per lo stesso PMID:
        nessuna nuova chiamata LLM, anche cambiando il contesto paziente."""
        item = self._item()
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "La fonte documenta il proprio record.",
            "source_line_category": "first_line",
            "source_setting_category": "metastatic",
            "source_prior_therapy_requirement": "treatment_naive",
            "applicability_status": "compatible",
            "applicability_reason": "Coincidenza dichiarata.",
        }]])
        cache = InMemorySourceProfileCache()
        metrics_first: dict[str, int] = {}
        results_first = verify_evidence_items(
            [item], llm_client=llm, source_loader=self._source_loader(),
            profile_cache=cache, metrics=metrics_first,
            case_context={"therapy_line": "first-line", "disease_stage": "IV", "disease_setting": "metastatic", "prior_therapies": "Nessuno"},
        )
        self.assertEqual(metrics_first["cache_misses"], 1)
        self.assertEqual(metrics_first["cache_hits"], 0)
        self.assertEqual(results_first[0].applicability_status, "compatible")

        metrics_second: dict[str, int] = {}
        results_second = verify_evidence_items(
            [item], llm_client=llm, source_loader=self._source_loader(),
            profile_cache=cache, metrics=metrics_second,
            case_context={"therapy_line": "first-line", "disease_stage": "", "disease_setting": "", "prior_therapies": ""},
        )
        self.assertEqual(metrics_second["cache_hits"], 1)
        self.assertEqual(metrics_second["cache_misses"], 0)
        self.assertEqual(results_second[0].source_support_status, "supported")
        # Cambiando il contesto paziente (ora incompleto), l'applicabilità si
        # ricalcola comunque correttamente in modo puramente deterministico,
        # senza alcuna nuova chiamata LLM.
        self.assertEqual(results_second[0].applicability_status, "indeterminate")

    def test_deterministic_validator_downgrades_llm_verdict_when_setting_undeclared(self):
        """Anche se l'LLM restituisce 'compatible', il validatore deterministico
        deve ridurlo a 'indeterminate' quando la fonte dichiara un setting
        noto e il paziente non lo ha dichiarato."""
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "La fonte documenta il proprio record.",
            "source_setting_category": "metastatic",
            "source_line_category": "first_line",
            "applicability_status": "compatible",
            "applicability_reason": "Setting e linea coincidono secondo l'LLM.",
        }]])
        results = verify_evidence_items(
            [self._item()],
            llm_client=llm,
            source_loader=self._source_loader(),
            case_context={"therapy_line": "first-line", "disease_stage": "", "disease_setting": ""},
        )
        self.assertEqual(results[0].applicability_status, "indeterminate")

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


class EgfrL858rLiveScenarioRegressionTest(TestCase):
    """Fixture deterministica che riproduce l'output osservato nel run live
    EGFR L858R (nessuna chiamata live nei test automatici): il caso dichiara
    solo therapy_line='first-line', mentre disease_stage, disease_setting e
    prior_therapies sono vuoti. Copre i criteri di accettazione richiesti."""

    def _item(self, source_id, object_, evidence_statement, citation_text):
        return SimpleNamespace(
            subject="EGFR L858R",
            relation="Sensitivity/Response",
            object=object_,
            context="NSCLC",
            source_id=source_id,
            evidence_statement=evidence_statement,
            citation_text=citation_text,
            evidence_level="A",
        )

    def _scripted_llm(self, categories_by_index):
        sources = self._sources

        class _ScriptedLLM:
            def invoke(self, messages):
                payload = json.loads(messages[1][1])
                results = []
                for entry in payload:
                    index = entry["index"]
                    line_cat, setting_cat, prior_req = categories_by_index[index]
                    results.append({
                        "index": index,
                        "source_support_status": "supported",
                        "source_support_reason": "La fonte documenta il proprio record contestualizzato.",
                        "source_line_category": line_cat,
                        "source_setting_category": setting_cat,
                        "source_prior_therapy_requirement": prior_req,
                        "applicability_status": "compatible",
                        "applicability_reason": "Setting e linea coincidono secondo l'LLM (verdict pre-validazione).",
                    })
                return _Response(json.dumps(results))

        return _ScriptedLLM()

    def setUp(self):
        self._sources = {
            24263064: {"title": "Gefitinib first-line NSCLC", "abstract": "Patients with EGFR-mutated NSCLC treated with gefitinib first-line."},
            28958502: {"title": "Dacomitinib first-line NSCLC", "abstract": "Patients with EGFR-mutated NSCLC treated with dacomitinib first-line."},
            27032107: {"title": "Erlotinib first-line NSCLC", "abstract": "Patients with EGFR-mutated NSCLC treated with erlotinib first-line."},
            32955177: {"title": "ADAURA adjuvant osimertinib", "abstract": "Patients with resected EGFR-mutated NSCLC received adjuvant osimertinib."},
            99999901: {"title": "Osimertinib post-progression", "abstract": "Patients with EGFR T790M NSCLC progressed on a prior EGFR-TKI before osimertinib."},
            37879444: {"title": "Amivantamab plus carboplatin and pemetrexed in EGFR Exon20ins NSCLC", "abstract": "Patients with EGFR-mutated NSCLC were treated with amivantamab, carboplatin and pemetrexed."},
        }
        self._items = [
            self._item("PMID:24263064", "gefitinib", "Gefitinib first-line in EGFR-mutated advanced NSCLC.", "Mok et al."),
            self._item("PMID:28958502", "dacomitinib", "Dacomitinib first-line in EGFR-mutated advanced NSCLC.", "Wu et al."),
            self._item("PMID:27032107", "erlotinib", "Erlotinib first-line in EGFR-mutated advanced NSCLC.", "Yang et al."),
            self._item("PMID:32955177", "osimertinib", "Adjuvant osimertinib after complete tumor resection in EGFR-mutated NSCLC.", "Wu et al. ADAURA."),
            self._item("PMID:99999901", "osimertinib", "Osimertinib in EGFR T790M NSCLC after progression on a prior EGFR-TKI.", "Post-progression cohort."),
        ]
        self._categories = {
            0: ("first_line", "metastatic", "treatment_naive"),
            1: ("first_line", "metastatic", "treatment_naive"),
            2: ("first_line", "metastatic", "treatment_naive"),
            3: ("adjuvant", "adjuvant", "specific_therapy"),
            4: ("post_progression", "metastatic", "previously_treated"),
        }
        self._case_context = {
            "therapy_line": "first-line",
            "disease_stage": "",
            "disease_setting": "",
            "prior_therapies": "",
        }

    def test_zero_compatible_when_stage_setting_and_prior_therapies_are_missing(self):
        results = verify_evidence_items(
            self._items,
            llm_client=self._scripted_llm(self._categories),
            source_loader=lambda _pmids: self._sources,
            case_context=self._case_context,
        )
        compatible = [r for r in results if r.applicability_status == "compatible"]
        self.assertEqual(len(compatible), 0)

    def test_gefitinib_dacomitinib_erlotinib_first_line_are_indeterminate(self):
        results = verify_evidence_items(
            self._items,
            llm_client=self._scripted_llm(self._categories),
            source_loader=lambda _pmids: self._sources,
            case_context=self._case_context,
        )
        for index in (0, 1, 2):
            self.assertEqual(results[index].applicability_status, "indeterminate")

    def test_adaura_adjuvant_is_indeterminate_not_not_compatible(self):
        results = verify_evidence_items(
            self._items,
            llm_client=self._scripted_llm(self._categories),
            source_loader=lambda _pmids: self._sources,
            case_context=self._case_context,
        )
        self.assertEqual(results[3].applicability_status, "indeterminate")

    def test_post_progression_source_against_first_line_case_is_not_compatible(self):
        results = verify_evidence_items(
            self._items,
            llm_client=self._scripted_llm(self._categories),
            source_loader=lambda _pmids: self._sources,
            case_context=self._case_context,
        )
        self.assertEqual(results[4].applicability_status, "not_compatible")

    def test_no_reason_contradicts_its_final_verdict(self):
        """Nessuna motivazione deve affermare che i dati coincidono quando il
        verdict finale è stato declassato dal validatore deterministico."""
        results = verify_evidence_items(
            self._items,
            llm_client=self._scripted_llm(self._categories),
            source_loader=lambda _pmids: self._sources,
            case_context=self._case_context,
        )
        for result in results:
            if result.applicability_status != "compatible":
                self.assertNotIn("coincidono secondo l'llm", result.applicability_reason.lower())

    def test_pmid_37879444_partial_regimen_is_not_supported(self):
        item = self._item(
            "PMID:37879444", "AMIVANTAMAB, CARBOPLATIN",
            "Amivantamab plus carboplatin in EGFR Exon20ins NSCLC.", "Real-world claim.",
        )
        llm = _SequencedLLM([[{
            "index": 0,
            "source_support_status": "supported",
            "source_support_reason": "La fonte documenta il regime nel proprio contesto.",
            "source_arms": [{"arm_name": "braccio unico", "interventions": ["amivantamab", "carboplatin", "pemetrexed"]}],
            "applicability_status": "indeterminate",
            "applicability_reason": "Dati clinici del paziente non dichiarati.",
        }]])
        results = verify_evidence_items(
            [item],
            llm_client=llm,
            source_loader=lambda _pmids: self._sources,
            case_context=self._case_context,
        )
        self.assertEqual(results[0].claim_arm_match, "partial")
        self.assertEqual(results[0].source_support_status, "uncertain")
        self.assertIn("pemetrexed", results[0].source_support_reason.lower())
