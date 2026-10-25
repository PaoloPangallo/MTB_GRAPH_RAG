from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "materialize_runtime_documents.py"
SPEC = importlib.util.spec_from_file_location("materialize_runtime_documents", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeCache:
    resolver_version = "fake/1.0"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def resolve_live_identifier(self, item):
        self.calls += 1
        response = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(response, Exception):
            raise response
        return dict(response)


class ExhaustiveResolutionTest(TestCase):
    def test_transient_failure_is_retried_before_terminal_classification(self):
        cache = FakeCache([
            {"availability": "DOCUMENT_UNAVAILABLE", "resolution_attempts": [{"status": 503}]},
            {"availability": "ABSTRACT_AVAILABLE", "local_cache_path": "pubmed/abstracts/1.xml",
             "metadata_cache_path": "pubmed/metadata/1.json", "identifiers": {"pmid": "1"},
             "resolution_attempts": [{"status": 200}]},
        ])

        result = MODULE.resolve_one(cache, "1", retry_budget=2, backoff_seconds=0, sleep_fn=lambda _: None)

        self.assertEqual("ABSTRACT_ONLY", result["final_document_status"])
        self.assertEqual(2, result["attempt_count"])
        self.assertEqual(2, cache.calls)

    def test_terminal_manifest_is_resumable_without_resolver_call(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.jsonl"
            existing = {"pmid": "1", "final_document_status": "DOCUMENT_UNAVAILABLE",
                        "resolution_attempted": True}
            path.write_text(json.dumps(existing) + "\n", encoding="utf-8")
            cache = FakeCache([RuntimeError("must not be called")])

            result = MODULE.materialize_targets(cache, ["1"], path, retry_budget=0)

            self.assertEqual(existing, result["rows"][0])
            self.assertEqual(0, cache.calls)

    def test_manifest_has_one_terminal_row_per_target(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.jsonl"
            cache = FakeCache([
                {"availability": "METADATA_ONLY", "metadata_cache_path": "pubmed/metadata/1.json",
                 "identifiers": {"pmid": "1"}, "resolution_attempts": [{"status": 200}]},
                {"availability": "PMC_XML_AVAILABLE", "local_cache_path": "pmc/xml/2.xml",
                 "identifiers": {"pmid": "2", "pmcid": "PMC2"},
                 "pmc_identity_verified": True, "resolution_attempts": [{"status": 200}]},
            ])

            summary = MODULE.materialize_targets(cache, ["1", "2"], path,
                                                 retry_budget=0)

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(["1", "2"], [row["pmid"] for row in rows])
            self.assertEqual(2, summary["terminal_results"])
            self.assertEqual(0, summary["unresolved_without_reason"])
