"""Test dell'accesso ai dati congelati e della configurazione LLM."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from backend.research_pipeline import data_access as da
from backend.research_pipeline import llm_config


class PathsAreConfiguredNotDerivedTest(TestCase):
    """La promozione dei moduli cambia la profondità del file: i percorsi non
    devono dipendere da ``__file__``."""

    def test_data_root_is_overridable(self) -> None:
        with TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"RESEARCH_PIPELINE_DATA_ROOT": tmp}):
                self.assertEqual(da.data_root(), Path(tmp).resolve())

    def test_every_dataset_path_follows_the_root(self) -> None:
        with TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"RESEARCH_PIPELINE_DATA_ROOT": tmp}):
                for path in (
                    da.candidates_path(), da.evidence_bundles_path(),
                    da.document_manifest_path(), da.source_unit_index_path(),
                    da.frozen_enricher_runs_path(),
                ):
                    self.assertTrue(str(path).startswith(str(Path(tmp).resolve())))

    def test_default_root_locates_the_real_datasets(self) -> None:
        """Senza override, i percorsi devono puntare ai dataset reali del repo."""
        self.assertTrue(da.source_unit_index_path().is_file())
        self.assertTrue(da.evidence_bundles_path().is_file())


class MissingDataIsExplicitTest(TestCase):
    def test_absent_dataset_raises_instead_of_returning_empty(self) -> None:
        """Una lista vuota verrebbe letta a valle come 'nessuna candidate'."""
        with TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"RESEARCH_PIPELINE_DATA_ROOT": tmp}):
                with self.assertRaises(da.FrozenDataUnavailable):
                    da.read_jsonl(da.candidates_path())

    def test_missing_document_cache_is_reported_not_silently_empty(self) -> None:
        with TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"RESEARCH_PIPELINE_CACHE_ROOT": str(Path(tmp) / "nope")}):
                self.assertFalse(da.document_cache_available())
                with self.assertRaises(da.FrozenDataUnavailable):
                    da.load_source_units([{"document_id": "d1"}])


class SourceUnitIndexCarriesNoTextTest(TestCase):
    """Proprietà di sicurezza dello STAGE 7, verificata sul dataset reale."""

    def test_index_records_have_locators_and_hash_but_no_text(self) -> None:
        index = da.load_source_unit_index()
        self.assertGreater(len(index), 0)

        sample = next(iter(index.values()))
        for expected in ("source_unit_id", "document_id", "char_start", "char_end", "content_hash"):
            self.assertIn(expected, sample)

        forbidden = {"text", "content", "body", "full_text", "abstract"}
        self.assertEqual(forbidden & set(sample), set())

    def test_no_record_in_the_whole_index_carries_text(self) -> None:
        forbidden = {"text", "content", "body", "full_text", "abstract"}
        offending = [
            unit_id for unit_id, row in da.load_source_unit_index().items()
            if forbidden & set(row)
        ]
        self.assertEqual(offending, [])


class FrozenEnricherRunsTest(TestCase):
    def test_the_seven_real_calls_are_available_for_replay(self) -> None:
        runs = da.load_frozen_enricher_runs()

        self.assertEqual(len(runs), 7)
        self.assertTrue(all(run["transport_result"] == "V2_TRANSPORT_VALID" for run in runs))

    def test_frozen_runs_carry_provenance_and_cost(self) -> None:
        """Sono risposte reali del modello, non mock: portano modello, prompt
        version, token e latenza."""
        run = da.load_frozen_enricher_runs()[0]

        for expected in ("model", "prompt_version", "transport_version",
                         "input_tokens", "output_tokens", "latency_ms"):
            self.assertIn(expected, run)

    def test_three_quotes_were_proposed(self) -> None:
        runs = da.load_frozen_enricher_runs()
        quoted = [r for r in runs if (r.get("enrichment") or {}).get("author_claim_quote")]
        self.assertEqual(len(quoted), 3)


class AvailabilityReportTest(TestCase):
    def test_an_absent_cache_is_unavailable_and_not_a_frozen_fallback(self) -> None:
        """Senza cache la catena documentale non parte: non ripiega sul congelato."""
        with TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"RESEARCH_PIPELINE_CACHE_ROOT": str(Path(tmp) / "nope")}):
                report = da.describe_availability()
                self.assertEqual(report["stages_6_to_10_mode"], "UNAVAILABLE")
                self.assertIn("DOCUMENT_CACHE_UNAVAILABLE", report["stages_6_to_10_reason"])

    def test_mode_is_canonical_when_the_cache_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"RESEARCH_PIPELINE_CACHE_ROOT": tmp}):
                report = da.describe_availability()
                self.assertEqual(report["stages_6_to_10_mode"], "CANONICAL")
                self.assertIsNone(report["stages_6_to_10_reason"])


class LLMConfigTest(TestCase):
    def test_default_endpoint_is_cloud_not_localhost(self) -> None:
        with mock.patch.dict(os.environ, {"RESEARCH_PIPELINE_LLM_API_KEY": "k"}, clear=False):
            endpoint = llm_config.resolve_endpoint()
        self.assertNotIn("localhost", endpoint.url)
        self.assertTrue(endpoint.url.endswith("/v1/chat/completions"))

    def test_missing_credentials_fail_loudly_on_a_cloud_endpoint(self) -> None:
        # L'host è ``ollama.com`` e non ``api.ollama.com``: quest'ultimo è ora
        # rifiutato da ``LLMEndpointMisconfigured`` perché non serve il percorso
        # OpenAI-compatible, e mascherebbe ciò che questo test verifica — che a
        # mancare siano le **credenziali**, non l'endpoint.
        with mock.patch.dict(os.environ, {
            "RESEARCH_PIPELINE_LLM_BASE_URL": "https://ollama.com",
            "RESEARCH_PIPELINE_LLM_API_KEY": "",
        }):
            with mock.patch.object(llm_config, "OLLAMA_API_KEY", ""):
                with self.assertRaises(llm_config.MissingLLMCredentials):
                    llm_config.resolve_endpoint()

    def test_local_endpoint_does_not_require_credentials(self) -> None:
        with mock.patch.dict(os.environ, {
            "RESEARCH_PIPELINE_LLM_BASE_URL": "http://localhost:11434",
            "RESEARCH_PIPELINE_LLM_API_KEY": "",
        }):
            with mock.patch.object(llm_config, "OLLAMA_API_KEY", ""):
                endpoint = llm_config.resolve_endpoint()
        self.assertIn("localhost", endpoint.url)

    def test_describe_never_exposes_the_key(self) -> None:
        with mock.patch.dict(os.environ, {"RESEARCH_PIPELINE_LLM_API_KEY": "super-secret-value"}):
            described = llm_config.describe()

        self.assertNotIn("super-secret-value", repr(described))
        self.assertTrue(described["credentials_configured"])

    def test_authorization_header_carries_the_bearer_token(self) -> None:
        endpoint = llm_config.LLMEndpoint(url="https://api.ollama.com/v1/chat/completions",
                                          model="gemma4:cloud")
        self.assertEqual(endpoint.headers("abc")["Authorization"], "Bearer abc")


class ResearchLedgerPathTest(TestCase):
    """Il default non è esercitato dai test che impostano RESEARCH_LEDGER_PATH,
    ed è proprio lì che si era annidato un percorso raddoppiato."""

    def test_default_ledger_sits_under_an_existing_directory(self) -> None:
        from backend.research_pipeline.run_store import research_ledger_path

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RESEARCH_LEDGER_PATH", None)
            path = research_ledger_path()

        self.assertTrue(path.parent.is_dir(), f"cartella inesistente: {path.parent}")
        self.assertNotIn("mtb-graphrag/mtb-graphrag", path.as_posix())

    def test_explicit_path_wins(self) -> None:
        from backend.research_pipeline.run_store import research_ledger_path

        with TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"RESEARCH_LEDGER_PATH": f"{tmp}/x.sqlite3"}):
                self.assertEqual(research_ledger_path(), Path(tmp).resolve() / "x.sqlite3")
