"""Invarianti del runtime canonico: esiste un solo percorso operativo.

Questi test non descrivono una preferenza di progetto, descrivono ciò che
l'architettura afferma. Ogni affermazione che la tesi fa sul runtime — cache
first, acquisizione autorizzata sul miss, snapshot persistito prima del parsing,
selettore deterministico con K=5, nessuna dipendenza da bundle congelati, nessun
fallback storico — ha qui il proprio controllo, e il controllo fallisce se
l'affermazione smette di essere vera.

**Nessuna rete.** Le fixture montano una ``AuthorizedDocumentCache`` reale con il
solo ``_request`` sostituito: il resto del percorso — scrittura dello snapshot,
manifest, riletura dal disco, parsing — è quello di produzione. Un test che
sostituisse anche la cache dimostrerebbe che lo stub funziona.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from fastapi.testclient import TestClient

from backend.api import research_routes
from backend.api.main import app
from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import execution_mode as em
from backend.research_pipeline import orchestrator, run_store
from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache
from backend.research_pipeline.documents.live_resolution import DocumentRuntime
from backend.research_pipeline.pipeline import CallBudget
from backend.research_pipeline.retrieval import kg_retrieval as retrieval_mod
from backend.research_pipeline.retrieval import live_sourceunit_selection as selector_mod
from backend.research_pipeline.retrieval import paper_selection as frozen_selection_mod

BASE = "/api/v1/research/pipeline"
PMID = "24658966"
PMCID = "PMC3999999"

# --- Payload delle fonti autorizzate, in forma minima ma reale ----------------

ESUMMARY = json.dumps({"result": {PMID: {
    "title": "ABL1 V299L and dasatinib in chronic myeloid leukemia",
    "authors": [], "fulljournalname": "Journal of Test Oncology",
    "pubdate": "2014", "lang": ["eng"], "pubtype": ["Journal Article"],
}}}).encode("utf-8")

EFETCH = f"""<?xml version="1.0"?>
<PubmedArticleSet><PubmedArticle>
  <MedlineCitation><Article>
    <ArticleTitle>ABL1 V299L and dasatinib in chronic myeloid leukemia</ArticleTitle>
    <Abstract>
      <AbstractText>Patients carrying the ABL1 V299L mutation and treated with
      dasatinib showed a reduced response in chronic myeloid leukemia.</AbstractText>
      <AbstractText>The resistance pattern was observed consistently across the
      dasatinib cohort described in this chronic myeloid leukemia study.</AbstractText>
    </Abstract>
  </Article></MedlineCitation>
  <PubmedData><ArticleIdList>
    <ArticleId IdType="pubmed">{PMID}</ArticleId>
    <ArticleId IdType="pmc">{PMCID}</ArticleId>
  </ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>
""".encode("utf-8")

# JATS reale nella struttura che il parser attraversa: article-title, sec, p.
# Una fixture con soli <p> sotto <body> verrebbe parsata senza produrre unita',
# e il test fallirebbe descrivendo la fixture invece del runtime.
PMC_XML = b"""<?xml version="1.0"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><GetRecord><record><metadata>
  <article xmlns="http://jats.nlm.nih.gov">
    <front><article-meta><title-group>
      <article-title>ABL1 V299L and dasatinib in chronic myeloid leukemia</article-title>
    </title-group></article-meta></front>
    <body><sec>
      <title>Results</title>
      <p>ABL1 V299L confers reduced sensitivity to dasatinib in chronic myeloid leukemia.</p>
      <p>The full text describes the dasatinib cohort and the observed ABL1 V299L pattern.</p>
      <p>A third paragraph reports the chronic myeloid leukemia outcomes in detail.</p>
      <p>A fourth paragraph discusses dasatinib exposure across the study population.</p>
      <p>A fifth paragraph summarises the ABL1 V299L resistance findings.</p>
      <p>A sixth paragraph lists the limitations of the chronic myeloid leukemia analysis.</p>
    </sec></body>
  </article>
</metadata></record></GetRecord></OAI-PMH>
"""

PMC_CLOSED = b"""<?xml version="1.0"?>
<OAI-PMH><error code="idDoesNotExist">record not open access</error></OAI-PMH>
"""


def _responder(*, pmc: bytes | None):
    """Sostituisce solo il trasporto. Registra ogni URL effettivamente chiamato."""
    calls: list[str] = []

    def request(url: str):
        calls.append(url)
        if "esummary.fcgi" in url:
            return ESUMMARY, {"status": 200, "url": url}
        if "efetch.fcgi" in url:
            return EFETCH, {"status": 200, "url": url}
        if "pmc/oai" in url:
            return (pmc, {"status": 200, "url": url}) if pmc else (None, {"status": 404, "url": url})
        return None, {"status": 404, "url": url}

    return request, calls


def _candidate() -> dict:
    return {
        "candidate_id": "GCA-canonical-test",
        "candidate_version": "2.0",
        "disease": [{"label": "Chronic Myeloid Leukemia"}],
        "biomarkers": [{"label": "ABL1", "type": "Gene"}, {"label": "V299L", "type": "Variant"}],
        "interventions": [{"label": "dasatinib"}],
        "document_identifiers": [{"pmid": PMID}],
        "predicate": "has_evidence_statement",
        "direction": "Supports",
    }


def _association() -> dict:
    candidate = _candidate()
    return {
        "candidate_id": candidate["candidate_id"],
        "candidate": candidate,
        # Un ``source_unit_id`` congelato che il runtime canonico non deve leggere.
        "available_bundles": [{
            "bundle_id": f"live:{candidate['candidate_id']}:pmid:{PMID}",
            "document_id": f"pmid:{PMID}",
            "provenance_identifier": {"pmid": PMID},
            "source_unit_ids": ["FROZEN-MUST-NOT-BE-READ"],
        }],
    }


CLINICAL_TEXT = (
    "Paziente con chronic myeloid leukemia e mutazione ABL1 V299L. "
    "Si vuole valutare dasatinib."
)


def _span(quote: str) -> list[dict]:
    """Span verificabile nel testo clinico.

    Il verificatore del CaseContext esige una citazione letterale, non un valore
    normalizzato: un CaseContext senza span e' un MISMATCH e la run si ferma
    prima del retrieval. Calcolarli qui, invece di scriverli a mano, impedisce
    che una fixture affermi una posizione che il testo non ha.
    """
    start = CLINICAL_TEXT.index(quote)
    return [{"quote": quote, "start_offset": start, "end_offset": start + len(quote)}]


def _case_context() -> dict:
    return {
        "query_intent": "THERAPY_EVALUATION",
        "disease": {"raw_value": "chronic myeloid leukemia",
                    "normalized_value": "Chronic Myeloid Leukemia",
                    "source_spans": _span("chronic myeloid leukemia")},
        "biomarkers": [{"gene": "ABL1", "normalized_value": "ABL1 V299L",
                        "raw_value": "ABL1 V299L",
                        "source_spans": _span("ABL1 V299L")}],
        "target_intervention": {"raw_value": "dasatinib", "normalized_value": "dasatinib",
                                "source_spans": _span("dasatinib")},
    }


class CanonicalRuntimeFixture(TestCase):
    """Monta cache, runtime documentale e orchestratore su un percorso reale."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def cache(self, *, pmc: bytes | None = PMC_XML) -> tuple[AuthorizedDocumentCache, list[str]]:
        cache = AuthorizedDocumentCache(root=self.root / "cache", network=True, delay_seconds=0)
        request, calls = _responder(pmc=pmc)
        cache._request = request  # type: ignore[method-assign]
        return cache, calls

    def runtime(self, cache: AuthorizedDocumentCache) -> DocumentRuntime:
        return DocumentRuntime(
            cache=cache, manifest_by_document_id={},
            descriptor={"document_cache_available": True,
                        "retrieval_mode": "CACHE_FIRST_API_ON_MISS",
                        "manifest_hash": "test"},
            network_enabled=True,
        )

    def execute(self, runtime: DocumentRuntime | None, **overrides):
        """Una run canonica. I default sono quelli del runtime operativo.

        Si chiama ``execute`` e non ``run``: ``TestCase.run`` e' il runner, e
        sovrascriverlo fa fallire ogni test della classe con un errore che non
        parla di cio' che si stava provando.
        """
        recorded: dict[str, list] = {"enricher": [], "narrator": []}

        def parser(budget, case_id, text):
            return {"transport_result": "FORCED_TOOL_VALID",
                    "case_context_raw": _case_context(),
                    "model": "TEST_PARSER", "prompt_version": "test/1.0"}

        def enricher(*args, **kwargs):
            recorded["enricher"].append(args[3] if len(args) > 3 else None)
            return {"transport_result": "V2_TRANSPORT_VALID", "enrichment": None}

        def narrator(case_id, narrator_input, run_index=0):
            recorded["narrator"].append(case_id)
            return {"transport_result": "NO_NARRATIVE", "narrative": None}

        kwargs = {
            "case_id": "CASE-canonical", "clinical_text": CLINICAL_TEXT,
            "call_parser_fn": parser, "call_enricher_fn": enricher,
            "call_narrator_fn": narrator,
            "source_units_by_id": {}, "budget": CallBudget(5),
            "ledger": EventLedger(self.root / "ledger.sqlite3"),
            "document_runtime": runtime,
            "validate_fn": lambda *a, **k: {"outcome": "ENRICHMENT_V2_ABSTAINED"},
        }
        kwargs.update(overrides)
        with mock.patch.object(
            orchestrator.retrieval_mod, "retrieve",
            return_value={"associations": [_association()], "excluded_candidates": [],
                          "no_match": False},
        ):
            run = orchestrator.run_case(**kwargs)
        return run, recorded

    @staticmethod
    def stage(run, stage_id):
        return next(s for s in run.stages if s.stage_id == stage_id)


# =============================================================================
# A / B — nessuna modalità è richiedibile dall'API
# =============================================================================


class NoUserSelectableModeTest(TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict(os.environ, {"VERIFIABLE_PIPELINE_RESEARCH_ENABLED": "1"})
        self._env.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._env.stop()

    def test_replay_cannot_be_requested(self) -> None:
        response = self.client.post(
            f"{BASE}/runs", json={"demo_case_key": "CASE-1-therapy-evaluation-strong-match",
                                  "execution_mode": "REPLAY"})
        self.assertEqual(422, response.status_code, response.text)
        self.assertIn("execution_mode", response.text)

    def test_live_cannot_be_requested_either(self) -> None:
        """Non e' che LIVE sia il default: e' che non esiste piu' il campo."""
        response = self.client.post(
            f"{BASE}/runs", json={"demo_case_key": "CASE-1-therapy-evaluation-strong-match",
                                  "execution_mode": "LIVE"})
        self.assertEqual(422, response.status_code, response.text)

    def test_the_vocabulary_refuses_replay_as_a_requested_mode(self) -> None:
        with self.assertRaises(em.UnknownExecutionMode):
            em.normalize_requested_mode("REPLAY")
        self.assertEqual((em.CANONICAL_MODE,), em.REQUESTABLE_MODES)

    def test_config_declares_one_runtime_and_no_frozen_artifacts(self) -> None:
        payload = self.client.get(f"{BASE}/config").json()

        self.assertEqual([], payload["runtime"]["user_selectable_modes"])
        self.assertEqual("CACHE_FIRST_API_ON_MISS", payload["runtime"]["document_acquisition"])
        self.assertNotIn("frozen_replay", payload)
        self.assertNotIn("execution_modes", payload)

    def test_cases_do_not_advertise_frozen_artifacts(self) -> None:
        """E' il campo da cui la console derivava l'azione «apri la run registrata»."""
        cases = self.client.get(f"{BASE}/cases").json()["cases"]

        self.assertTrue(cases)
        for case in cases:
            self.assertNotIn("frozen_artifacts_available", case)


# =============================================================================
# C – F — acquisizione documentale
# =============================================================================


class DocumentAcquisitionTest(CanonicalRuntimeFixture):
    def test_the_canonical_runtime_opens_a_cache_first_runtime(self) -> None:
        with mock.patch.dict(os.environ, {"RESEARCH_DOCUMENT_CACHE_PATH": str(self.root)}):
            runtime = DocumentRuntime.open()

        self.assertTrue(runtime.network_enabled)
        self.assertEqual("CACHE_FIRST_API_ON_MISS", runtime.descriptor["retrieval_mode"])

    def test_a_cache_miss_acquires_from_authorized_apis(self) -> None:
        cache, calls = self.cache()
        run, _ = self.execute(self.runtime(cache))

        resolution = self.stage(run, "stage_6_document_resolution").output_preview
        self.assertEqual(1, resolution["cache_misses"])
        self.assertEqual(1, resolution["network_fetch_count"])
        self.assertTrue(any("esummary.fcgi" in url for url in calls))
        self.assertTrue(any("efetch.fcgi" in url for url in calls))

    def test_a_cache_hit_performs_no_network_fetch(self) -> None:
        cache, calls = self.cache()
        self.execute(self.runtime(cache))          # popola la cache
        before = len(calls)
        run, _ = self.execute(self.runtime(cache))  # seconda run sullo stesso documento

        resolution = self.stage(run, "stage_6_document_resolution").output_preview
        self.assertEqual(1, resolution["cache_hits"])
        self.assertEqual(0, resolution["network_fetch_count"])
        self.assertFalse(resolution["network_fetch_used"])
        self.assertEqual(before, len(calls), "un cache hit non deve toccare la rete")

    def test_pmid_is_resolved_to_pmcid_and_full_text_is_preferred(self) -> None:
        cache, calls = self.cache(pmc=PMC_XML)
        run, _ = self.execute(self.runtime(cache))

        document = self.stage(run, "stage_6_document_resolution").output_preview["documents"][0]
        self.assertEqual(f"pmcid:{PMCID}", document["document_id"])
        self.assertTrue(document["full_text_available"])
        self.assertEqual(PMCID, document["lineage"]["derived_pmcid"])
        self.assertTrue(any("pmc/oai" in url for url in calls))

    def test_an_unavailable_full_text_degrades_to_the_abstract(self) -> None:
        cache, _ = self.cache(pmc=PMC_CLOSED)
        run, _ = self.execute(self.runtime(cache))

        document = self.stage(run, "stage_6_document_resolution").output_preview["documents"][0]
        self.assertEqual(f"pmid:{PMID}", document["document_id"])
        self.assertTrue(document["abstract_available"])
        self.assertIn("PMC_RESOLUTION_FAILED", document["reason_codes"])
        self.assertTrue(document["resolved"], "una degradazione dichiarata resta un'acquisizione")

    def test_the_snapshot_is_persisted_before_the_parser_reads_it(self) -> None:
        """Il parser rilegge dal disco, non dalla risposta ancora in memoria."""
        cache, _ = self.cache()
        runtime = self.runtime(cache)
        seen: list[str] = []

        real_units = cache.source_units_for_record

        def recording_units(record):
            relative = record.get("local_cache_path")
            # Al momento del parsing lo snapshot esiste gia' su disco.
            self.assertTrue(relative, "nessuno snapshot persistito da rileggere")
            self.assertTrue((cache.root / relative).is_file())
            seen.append(relative)
            return real_units(record)

        cache.source_units_for_record = recording_units  # type: ignore[method-assign]
        run, _ = self.execute(runtime)

        self.assertEqual(1, len(seen))
        self.assertGreater(
            self.stage(run, "stage_7_source_units").metrics["with_exact_text"], 0)

    def test_the_run_snapshot_reports_how_documents_were_obtained(self) -> None:
        cache, _ = self.cache()
        run, _ = self.execute(self.runtime(cache))

        acquisition = run.to_dict()["document_acquisition"]
        self.assertTrue(acquisition["executed"])
        self.assertEqual(1, acquisition["network_fetches"])
        self.assertEqual(["NCBI PMC OAI"], acquisition["sources"])


# =============================================================================
# G – J — retrieval e selezione canonici
# =============================================================================


class CanonicalRetrievalAndSelectionTest(CanonicalRuntimeFixture):
    def test_retrieval_never_consults_the_frozen_bundles(self) -> None:
        with mock.patch.object(
            retrieval_mod, "load_bundles_by_candidate",
            side_effect=AssertionError("il retrieval canonico ha letto i bundle congelati"),
        ), mock.patch.object(
            retrieval_mod, "load_candidates", return_value={
                _candidate()["candidate_id"]: _candidate(),
                "GCA-without-provenance": {**_candidate(),
                                           "candidate_id": "GCA-without-provenance",
                                           "document_identifiers": []},
            },
        ):
            result = retrieval_mod.retrieve(_case_context())

        candidate_ids = [row["candidate_id"] for row in result["associations"]]
        self.assertEqual(["GCA-canonical-test"], candidate_ids)
        bundle = result["associations"][0]["available_bundles"][0]
        self.assertEqual({"pmid": PMID}, bundle["provenance_identifier"])
        self.assertEqual([], bundle["source_unit_ids"])

    def test_selection_uses_the_deterministic_selector_with_k_five(self) -> None:
        cache, _ = self.cache()
        run, _ = self.execute(self.runtime(cache))

        selection = self.stage(run, "stage_8_paper_selection").output_preview["selections"][0]
        paper = selection["selected_papers"][0]
        self.assertEqual(5, selector_mod.LIVE_SELECTOR_TOP_K)
        self.assertEqual(5, len(paper["resolved_source_unit_ids"]))
        self.assertFalse(selection["bundle_source_unit_ids_used"])
        self.assertIn("TOP_K_5", selection["criteria_order"])

    def test_the_selection_event_declares_the_deterministic_selector(self) -> None:
        cache, _ = self.cache()
        run, _ = self.execute(self.runtime(cache))

        events = EventLedger(self.root / "ledger.sqlite3").events(run.run_id)
        modes = {(e.get("payload") or {}).get("selection_mode")
                 for e in events if (e.get("payload") or {}).get("selection_mode")}
        self.assertEqual({"DETERMINISTIC_SELECTOR"}, modes)
        self.assertNotIn("LIVE_SELECTOR", modes)

    def test_no_frozen_source_unit_id_reaches_the_model(self) -> None:
        cache, _ = self.cache()
        run, _ = self.execute(self.runtime(cache))

        selection = self.stage(run, "stage_8_paper_selection").output_preview["selections"][0]
        selected = selection["selected_papers"][0]["resolved_source_unit_ids"]
        self.assertNotIn("FROZEN-MUST-NOT-BE-READ", selected)

    def test_the_frozen_paper_selector_is_never_called(self) -> None:
        cache, _ = self.cache()
        with mock.patch.object(
            orchestrator, "select_papers_for_association",
            side_effect=AssertionError("selezione da bundle congelato nel runtime canonico"),
        ):
            run, _ = self.execute(self.runtime(cache))

        # La run arriva al dossier canonico senza che il selettore da bundle
        # congelato sia mai stato una possibilita'. Lo stato e' PARTIAL solo
        # perche' il narratore di test non produce narrativa: il dossier c'e'.
        self.assertEqual("SUCCEEDED", self.stage(run, "stage_13_dossier").status)


# =============================================================================
# K — l'adattatore di replay è irraggiungibile
# =============================================================================


class ReplayAdapterIsUnreachableTest(CanonicalRuntimeFixture):
    def test_no_replay_adapter_is_invoked_by_a_canonical_run(self) -> None:
        from backend.research_pipeline import replay

        boom = mock.Mock(side_effect=AssertionError("adattatore di replay invocato"))
        with mock.patch.multiple(
            replay, parser_fn=boom, enricher_fn=boom, selection_fn=boom,
            validation_fn=boom, narrator_fn=boom,
        ):
            cache, _ = self.cache()
            run, _ = self.execute(self.runtime(cache))

        self.assertEqual("SUCCEEDED", self.stage(run, "stage_13_dossier").status)

    def test_the_product_surfaces_do_not_import_replay(self) -> None:
        """Un import e' gia' un percorso: qui non deve esistere nemmeno quello."""
        package = Path(run_store.__file__).parent
        for module in (package / "run_store.py",
                       package.parent / "api" / "research_routes.py"):
            source = module.read_text(encoding="utf-8")
            offending = [
                line for line in source.splitlines()
                if line.startswith(("import ", "from ")) and "replay" in line
            ]
            self.assertEqual([], offending, f"{module.name} importa replay")

    def test_the_frozen_retrieval_exists_but_is_a_separate_function(self) -> None:
        self.assertTrue(hasattr(retrieval_mod, "retrieve_frozen_bundles"))
        self.assertTrue(hasattr(frozen_selection_mod, "select_papers_for_association"))
        # Il default della firma canonica non ha alcun modo di raggiungerle.
        import inspect

        signature = inspect.signature(retrieval_mod.retrieve)
        self.assertEqual(["case_context"], list(signature.parameters))


# =============================================================================
# L – N — fallimenti controllati, senza fallback
# =============================================================================


class ControlledFailureTest(CanonicalRuntimeFixture):
    def test_without_a_document_runtime_the_run_fails_instead_of_replaying(self) -> None:
        run, recorded = self.execute(None)

        self.assertEqual("FAILED", run.status)
        self.assertEqual("DOCUMENT_CACHE_UNAVAILABLE", run.stopped_at)
        self.assertEqual([], recorded["enricher"], "il modello non va interrogato dopo un abort")

    def test_an_unobtainable_document_stops_the_run(self) -> None:
        cache, _ = self.cache()
        cache._request = lambda url: (None, {"status": 404, "url": url})  # type: ignore[method-assign]
        run, recorded = self.execute(self.runtime(cache))

        self.assertEqual("FAILED", run.status)
        self.assertEqual("NO_DOCUMENT_RESOLVED", run.stopped_at)
        self.assertEqual([], recorded["enricher"])
        self.assertEqual([], recorded["narrator"])

    def test_an_aborted_run_produces_no_canonical_dossier(self) -> None:
        run, _ = self.execute(None)

        dossier = self.stage(run, "stage_13_dossier")
        self.assertEqual("SKIPPED", dossier.status)
        self.assertIsNone(run.dossier_id)

    def test_no_stage_of_a_canonical_run_is_a_recorded_artifact(self) -> None:
        cache, _ = self.cache()
        run, _ = self.execute(self.runtime(cache))

        self.assertEqual(0, run.mode_summary()["replay_artifacts_used"])
        self.assertEqual(em.LIVE, run.execution_mode, "HYBRID non e' piu' producibile")


# =============================================================================
# §33 / §34 — perimetro e invarianti dichiarati
# =============================================================================


class CanonicalPerimeterTest(TestCase):
    def test_oncokb_is_not_part_of_the_canonical_runtime(self) -> None:
        """Resta un pilot fuori dal runtime, e la tesi non deve poterlo promuovere."""
        package = Path(run_store.__file__).parent
        offending = [
            path.relative_to(package).as_posix()
            for path in package.rglob("*.py")
            if "tests" not in path.parts
            and "oncokb" in path.read_text(encoding="utf-8", errors="replace").lower()
        ]
        self.assertEqual([], offending)

    def test_the_canonical_invariants_hold(self) -> None:
        """I dieci invarianti, enumerati dove possono essere letti insieme."""
        import inspect

        signature = inspect.signature(orchestrator.run_case)
        invariants = {
            "canonical_user_mode_count": len(em.REQUESTABLE_MODES),
            "canonical_cache_first": DocumentRuntime.open.__doc__ is not None
            and "cache-first" in DocumentRuntime.open.__doc__,
            "canonical_api_on_miss": AuthorizedDocumentCache(
                root=Path(TemporaryDirectory().name), network=True).network,
            "canonical_selector_K": selector_mod.LIVE_SELECTOR_TOP_K,
            "canonical_max_papers": selector_mod.MAX_PAPERS_PER_ASSOCIATION,
            "canonical_frozen_artifacts_default":
                signature.parameters["research_frozen_artifacts"].default,
            "canonical_execution_mode_parameter": "execution_mode" in signature.parameters,
            "canonical_retrieve_parameters": list(
                inspect.signature(retrieval_mod.retrieve).parameters),
        }

        self.assertEqual(1, invariants["canonical_user_mode_count"])
        self.assertTrue(invariants["canonical_cache_first"])
        self.assertTrue(invariants["canonical_api_on_miss"])
        self.assertEqual(5, invariants["canonical_selector_K"])
        self.assertEqual(2, invariants["canonical_max_papers"])
        self.assertIs(False, invariants["canonical_frozen_artifacts_default"])
        self.assertFalse(invariants["canonical_execution_mode_parameter"])
        self.assertEqual(["case_context"], invariants["canonical_retrieve_parameters"])
