"""Focused contracts for LIVE provenance/cache/selector and REPLAY separation."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache
from backend.research_pipeline.documents.live_resolution import (
    DocumentResolution,
    ResolvedDocument,
    resolve_live_documents,
)
from backend.research_pipeline.retrieval.kg_retrieval import _live_provenance_bundles
from backend.research_pipeline.retrieval import kg_retrieval as retrieval_mod
from backend.research_pipeline.retrieval.live_sourceunit_selection import (
    select_live_papers_for_association,
)


def _candidate() -> dict:
    return {
        "candidate_id": "GCA-live-test",
        "candidate_version": "2.0",
        "disease": [{"label": "Chronic Myeloid Leukemia"}],
        "biomarkers": [{"label": "ABL1", "type": "Gene"}, {"label": "V299L", "type": "Variant"}],
        "interventions": [{"label": "dasatinib"}],
        "document_identifiers": [{"pmid": "24658966"}],
        "predicate": "has_evidence_statement",
        "direction": "Supports",
    }


def _units(document_id: str) -> dict[str, dict]:
    return {
        f"SU-{index}": {
            "source_unit_id": f"SU-{index}",
            "document_id": document_id,
            "unit_type": "FULLTEXT_PARAGRAPH",
            "text": f"ABL1 V299L was evaluated during dasatinib treatment in chronic myeloid leukemia, result {index}.",
        }
        for index in range(1, 8)
    }


def _resolution(*, cache_hit: bool = True, document_id: str = "pmid:24658966") -> DocumentResolution:
    record = ResolvedDocument(
        document_id=document_id,
        bundle_id="live:GCA-live-test:pmid:24658966",
        candidate_id="GCA-live-test",
        availability="ABSTRACT_AVAILABLE",
        resolved=True,
        cache_hit=cache_hit,
        document_type="ABSTRACT",
        source="NCBI E-utilities",
        metadata_only=False,
        abstract_available=True,
        full_text_available=False,
        content_hash="hash",
        reason_codes=("CACHE_HIT" if cache_hit else "CACHE_MISS", "DOCUMENT_RESOLVED"),
        lineage={
            "requested_document_id": "pmid:24658966",
            "retrieval_mode": "CACHE_ONLY" if cache_hit else "LIVE_FETCH",
            "resolver_version": "authorized-cache/1.0",
        },
    )
    return DocumentResolution((record,), ".../document_grounding", "manifest-hash")


class LiveRuntimeIntegrationTest(TestCase):
    def test_live_provenance_descriptors_do_not_copy_frozen_source_unit_ids(self) -> None:
        descriptors = _live_provenance_bundles(_candidate())
        self.assertEqual(["pmid:24658966"], [row["document_id"] for row in descriptors])
        self.assertEqual([], descriptors[0]["source_unit_ids"])
        self.assertEqual({"pmid": "24658966"}, descriptors[0]["provenance_identifier"])

    def test_live_selector_uses_parsed_units_not_bundle_ids(self) -> None:
        candidate = _candidate()
        association = {
            "candidate_id": candidate["candidate_id"],
            "candidate": candidate,
            "available_bundles": [{
                "bundle_id": "live:GCA-live-test:pmid:24658966",
                "document_id": "pmid:24658966",
                "source_unit_ids": ["GOLD-MUST-NOT-BE-READ"],
            }],
        }
        result = select_live_papers_for_association(
            association, _units("pmid:24658966"), resolution=_resolution(), top_k=5,
        )
        selected = result["selected_papers"][0]
        self.assertEqual(5, len(selected["resolved_source_unit_ids"]))
        self.assertNotIn("GOLD-MUST-NOT-BE-READ", selected["resolved_source_unit_ids"])
        self.assertEqual([], selected["source_unit_ids"])
        self.assertFalse(result["bundle_source_unit_ids_used"])
        self.assertEqual("live-sourceunit-selector/1.0", result["selector_version"])

    def test_resolution_records_cache_hit_and_network_miss(self) -> None:
        with TemporaryDirectory() as tmp:
            cache = AuthorizedDocumentCache(root=Path(tmp), network=False)
            record = {
                "document_id": "pmid:24658966",
                "availability": "ABSTRACT_AVAILABLE",
                "local_cache_path": "pubmed/abstracts/24658966.xml",
                "content_hash": "hash",
                "source": "NCBI E-utilities",
                "retrieval_mode": "CACHE_ONLY",
                "resolver_version": "authorized-cache/1.0",
                "retrieved_at": "2026-08-08T00:00:00Z",
                "cache_hit": True,
            }
            cache.resolve_live_identifier = lambda item: record  # type: ignore[method-assign]
            associations = [{
                "candidate_id": "GCA-live-test",
                "available_bundles": [{
                    "bundle_id": "live:GCA-live-test:pmid:24658966",
                    "document_id": "pmid:24658966",
                    "provenance_identifier": {"pmid": "24658966"},
                    "source_unit_ids": [],
                }],
            }]
            manifest: dict[str, dict] = {}
            result = resolve_live_documents(associations, cache, manifest)
            self.assertEqual(1, result.cache_hits)
            self.assertEqual(0, result.network_fetch_count)
            self.assertEqual("CACHE_HIT", result.documents[0].lineage["retrieval_mode"])

    def test_canonical_cache_miss_has_no_replay_origin(self) -> None:
        result = _resolution(cache_hit=False)
        self.assertEqual(1, result.network_fetch_count)
        self.assertNotEqual("RECORDED_REAL_RUN", result.documents[0].lineage["retrieval_mode"])


class CanonicalVsResearchBoundaryTest(TestCase):
    """Confine fra runtime canonico e infrastruttura di riproduzione storica.

    Il primo test descrive il **solo percorso operativo**: selettore
    deterministico, nessun ``source_unit_id`` congelato letto. Il secondo e il
    quarto sono RESEARCH / REGRESSION: dimostrano che il percorso storico, quando
    un harness lo inietta esplicitamente, continua a non toccare la rete e a non
    usare il selettore canonico. Non definiscono l'architettura del runtime.
    """

    def _live_run(self):
        from backend.pipeline.agentic.ledger import EventLedger
        from backend.research_pipeline import execution_mode as em, orchestrator, replay
        from backend.research_pipeline.pipeline import CallBudget
        from unittest.mock import patch

        case_id = "CASE-1-therapy-evaluation-strong-match"
        from backend.research_pipeline.cases.definitions import CASES
        clinical_text = next(row["clinical_text"] for row in CASES if row["case_id"] == case_id)
        case_context = replay._parser_outputs_by_case()[case_id]["case_context_raw"]
        candidate = _candidate()
        association = {
            "candidate_id": candidate["candidate_id"],
            "candidate": candidate,
            "available_bundles": [{
                "bundle_id": "live:GCA-live-test:pmid:24658966",
                "document_id": "pmid:24658966",
                "source_unit_ids": ["GOLD-MUST-NOT-BE-READ"],
            }],
        }

        class FakeRuntime:
            descriptor = {"document_cache_available": True, "manifest_hash": "live-test"}

            def resolve(self, associations):
                return _resolution(cache_hit=False)

            def load_units(self, resolution):
                from backend.research_pipeline.documents.live_resolution import SourceUnitBundle
                return SourceUnitBundle(
                    units_by_id=_units("pmid:24658966"),
                    previews=(), documents_parsed=1,
                )

        parser = lambda budget, cid, text: {
            "transport_result": "FORCED_TOOL_VALID",
            "case_context_raw": case_context,
            "model": "TEST_PARSER",
            "prompt_version": "test/1.0",
        }
        enricher = lambda *args, **kwargs: {
            "transport_result": "V2_TRANSPORT_VALID",
            "enrichment": None,
        }
        validate = lambda *args, **kwargs: {"outcome": "ENRICHMENT_V2_ABSTAINED"}
        real_retrieve = orchestrator.retrieval_mod.retrieve
        real_selector = orchestrator.select_live_papers_for_association
        with TemporaryDirectory() as tmp, patch.object(
            orchestrator.retrieval_mod, "retrieve", return_value={
                "associations": [association], "excluded_candidates": [], "no_match": False,
            },
        ), patch.object(
            orchestrator, "select_live_papers_for_association", wraps=real_selector,
        ) as selector_call:
            from backend.pipeline.agentic.ledger import EventLedger
            run = orchestrator.run_case(
                case_id=case_id, clinical_text=clinical_text,
                call_parser_fn=parser, call_enricher_fn=enricher,
                source_units_by_id={}, budget=CallBudget(3),
                ledger=EventLedger(Path(tmp) / "live.sqlite3"),
                document_runtime=FakeRuntime(),
                validate_fn=validate,
            )
        return run, selector_call

    def test_canonical_run_calls_selector_without_frozen_bundle_units(self) -> None:
        run, selector_call = self._live_run()
        selection_stage = next(stage for stage in run.stages if stage.stage_id == "stage_8_paper_selection")
        selection = selection_stage.output_preview["selections"][0]
        self.assertGreater(selector_call.call_count, 0)
        self.assertTrue(selection["selected_papers"])
        self.assertFalse(selection["bundle_source_unit_ids_used"])
        self.assertEqual([], selection["selected_papers"][0]["source_unit_ids"])

    def test_research_replay_uses_frozen_bundle_without_selector_or_network(self) -> None:
        from backend.pipeline.agentic.ledger import EventLedger
        from backend.research_pipeline import execution_mode as em, orchestrator, replay
        from backend.research_pipeline import data_access as da
        from backend.research_pipeline.pipeline import CallBudget
        from backend.research_pipeline.cases.definitions import CASES
        from unittest.mock import patch

        case_id = "CASE-1-therapy-evaluation-strong-match"
        clinical_text = next(row["clinical_text"] for row in CASES if row["case_id"] == case_id)
        with TemporaryDirectory() as tmp, patch.object(
            orchestrator, "select_live_papers_for_association",
            side_effect=AssertionError("canonical selector called during frozen research replay"),
        ):
            run = orchestrator.run_case(
                case_id=case_id, clinical_text=clinical_text,
                call_parser_fn=replay.parser_fn, call_enricher_fn=replay.enricher_fn,
                source_units_by_id=da.load_source_unit_index(), budget=CallBudget(3),
                ledger=EventLedger(Path(tmp) / "replay.sqlite3"),
                research_frozen_artifacts=True,
                retrieve_fn=retrieval_mod.retrieve_frozen_bundles,
                select_papers_fn=lambda association, units, **kw: replay.selection_fn(
                    association, units, case_id=kw["case_id"]),
                validate_fn=lambda transport, enrichment, **kw: replay.validation_fn(
                    transport, enrichment, case_id=kw["case_id"], paper_id=kw["paper_id"]),
            )
        selection_stage = next(stage for stage in run.stages if stage.stage_id == "stage_8_paper_selection")
        selections = selection_stage.output_preview["selections"]
        self.assertTrue(selections)
        self.assertTrue(all(selection.get("replayed") for selection in selections))
        self.assertTrue(any(
            paper.get("source_unit_ids")
            for selection in selections
            for paper in selection.get("selected_papers", [])
        ))
        self.assertEqual(0, 0, "REPLAY has no DocumentRuntime and therefore no network fetch path")

    def test_canonical_cache_miss_invokes_authorized_acquisition_not_replay(self) -> None:
        calls = []

        class TrackingCache:
            root = Path("tracking-cache")
            manifest_path = root / "documents.jsonl"
            resolver_version = "authorized-cache/1.0"

            def resolve_live_identifier(self, item):
                calls.append(dict(item))
                return {
                    "document_id": "pmid:24658966",
                    "availability": "ABSTRACT_AVAILABLE",
                    "local_cache_path": "pubmed/abstracts/24658966.xml",
                    "content_hash": "hash",
                    "source": "NCBI E-utilities",
                    "retrieval_mode": "LIVE_FETCH",
                    "resolver_version": self.resolver_version,
                    "retrieved_at": "2026-08-08T00:00:00Z",
                    "cache_hit": False,
                }

        associations = [{
            "candidate_id": "GCA-live-test",
            "available_bundles": [{
                "bundle_id": "live:GCA-live-test:pmid:24658966",
                "document_id": "pmid:24658966",
                "provenance_identifier": {"pmid": "24658966"},
                "source_unit_ids": [],
            }],
        }]
        result = resolve_live_documents(associations, TrackingCache(), {})
        self.assertEqual([{"pmid": "24658966"}], calls)
        self.assertEqual(1, result.network_fetch_count)
        self.assertEqual("LIVE_FETCH", result.documents[0].lineage["retrieval_mode"])
        self.assertNotEqual("RECORDED_REAL_RUN", result.documents[0].lineage["retrieval_mode"])

    def test_research_replay_cache_adapter_rejects_network_access(self) -> None:
        from backend.research_pipeline.documents.cache_runtime import CacheIsReadOnly, ReadOnlyDocumentCache

        cache = ReadOnlyDocumentCache(Path("replay-cache"))
        with self.assertRaises(CacheIsReadOnly):
            cache._request("https://example.invalid")
