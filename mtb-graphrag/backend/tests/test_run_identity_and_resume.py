"""Test dell'identita' atomica delle run e della semantica del resume.

Offline: nessun modello, nessun endpoint, nessun Neo4j.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from benchmarks.mtb_evidence.model_selection.run_identity import (
    EXECUTE,
    PRESERVE_NOT_REUSE,
    REPLACE,
    RUN_KEY_FIELDS,
    SKIP,
    DuplicateRunKeyError,
    RunIdentity,
    RunLedger,
    build_identity,
    case_hash,
    identity_manifest,
    is_complete,
    pair_is_complete,
    source_profile_hash,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (
    append_jsonl_atomic,
    read_jsonl,
    write_json,
)


def _identity(**overrides) -> RunIdentity:
    base = dict(
        requested_model_tag="gemma4:31b-cloud",
        effective_api_model="gemma4:31b",
        model_revision="ollama:gemma4:31b-cloud:221b330d11a8",
        role="planner",
        case_id="PILOT-K1-FGFR2-iCCA",
        task_id="PILOT-K1-FGFR2-iCCA::planner",
        seed=20240517,
        prompt_version="v1",
        schema_version="v1",
        case_hash="case-digest",
        source_profile_hash="profile-digest",
        temperature=0.0,
        num_ctx=16384,
    )
    base.update(overrides)
    return RunIdentity(**base)


def _completed(identity: RunIdentity, **extra) -> dict:
    return {**identity.as_dict(), "completed": True, "valid_output": True, **extra}


class RunKeyTest(TestCase):
    def test_thirteen_components(self):
        self.assertEqual(len(RUN_KEY_FIELDS), 13)

    def test_key_is_deterministic(self):
        self.assertEqual(_identity().run_key, _identity().run_key)

    def test_key_changes_with_every_component(self):
        """Se un componente non cambiasse la chiave, non farebbe parte dell'identita'."""
        baseline = _identity().run_key
        variations = {
            "requested_model_tag": "altro:1b",
            "effective_api_model": "altro",
            "model_revision": "ollama:x:y",
            "role": "verifier",
            "case_id": "PILOT-A2-ALK-G1202R",
            "task_id": "altro::task",
            "seed": 13,
            "prompt_version": "v2",
            "schema_version": "v2",
            "case_hash": "diverso",
            "source_profile_hash": "diverso",
            "temperature": 0.7,
            "num_ctx": 8192,
        }
        self.assertEqual(set(variations), set(RUN_KEY_FIELDS))
        for field, value in variations.items():
            with self.subTest(field=field):
                self.assertNotEqual(
                    baseline, _identity(**{field: value}).run_key, f"{field} ignorato"
                )

    def test_key_is_a_sha256_hex(self):
        key = _identity().run_key
        self.assertEqual(len(key), 64)
        int(key, 16)

    def test_case_hash_tracks_case_content(self):
        first = case_hash({"case_id": "A", "question": "x"})
        second = case_hash({"case_id": "A", "question": "y"})
        self.assertNotEqual(first, second)

    def test_source_profile_hash_is_order_independent(self):
        one = [{"source_id": "S1", "setting": "a"}, {"source_id": "S2", "setting": "b"}]
        other = list(reversed(one))
        self.assertEqual(source_profile_hash(one), source_profile_hash(other))

    def test_build_identity_uses_resolution_fields(self):
        identity = build_identity(
            requested_model_tag="tag",
            resolution={"effective_api_model": "eff", "model_revision": "rev"},
            role="planner",
            case_id="C",
            task_id="T",
            seed=1,
            case_digest="cd",
            profiles_digest="pd",
            temperature=0.0,
            num_ctx=16384,
        )
        self.assertEqual(identity.effective_api_model, "eff")
        self.assertEqual(identity.model_revision, "rev")


class ResumeSemanticsTest(TestCase):
    def test_missing_run_is_executed(self):
        self.assertEqual(RunLedger([]).decide(_identity()).action, EXECUTE)

    def test_complete_compatible_run_is_skipped(self):
        identity = _identity()
        ledger = RunLedger([_completed(identity)])
        decision = ledger.decide(identity)
        self.assertEqual(decision.action, SKIP)
        self.assertFalse(decision.should_execute)

    def test_incomplete_run_is_replaced(self):
        identity = _identity()
        partial = {**identity.as_dict(), "valid_output": True}  # senza `completed`
        decision = RunLedger([partial]).decide(identity)
        self.assertEqual(decision.action, REPLACE)
        self.assertTrue(decision.should_execute)

    def test_incompatible_run_is_preserved_not_reused(self):
        identity = _identity()
        # Stessa chiave dichiarata, componenti divergenti: e' il caso di un artefatto
        # manomesso o prodotto da un'altra configurazione.
        forged = {**_identity(seed=999).as_dict(), "run_key": identity.run_key,
                  "completed": True, "valid_output": True}
        decision = RunLedger([forged]).decide(identity)
        self.assertEqual(decision.action, PRESERVE_NOT_REUSE)
        self.assertTrue(decision.existing is not None)

    def test_duplicate_run_key_with_different_components_fails(self):
        identity = _identity()
        first = _completed(identity)
        second = {**_completed(_identity(seed=42)), "run_key": identity.run_key}
        with self.assertRaises(DuplicateRunKeyError):
            RunLedger([first, second])

    def test_identical_duplicate_is_tolerated(self):
        """Due scritture della stessa run non sono un conflitto di identita'."""
        row = _completed(_identity())
        ledger = RunLedger([row, dict(row)])
        self.assertEqual(len(ledger.completed_keys()), 1)

    def test_rows_without_run_key_are_incompatible(self):
        legacy = {"model": "gemma4:31b-cloud", "role": "planner", "valid_output": True}
        ledger = RunLedger([legacy])
        self.assertEqual(len(ledger.incompatible), 1)
        self.assertEqual(ledger.decide(_identity()).action, EXECUTE)

    def test_numeric_components_compare_by_value(self):
        identity = _identity()
        row = _completed(identity)
        row["temperature"] = 0  # int invece di float
        row["num_ctx"] = "16384"  # stringa invece di int
        self.assertEqual(RunLedger([row]).decide(identity).action, SKIP)


class PairCompletenessTest(TestCase):
    def test_pair_is_incomplete_until_every_key_is_present(self):
        identities = [_identity(seed=seed) for seed in (1, 2, 3)]
        ledger = RunLedger([_completed(identities[0]), _completed(identities[1])])
        complete, missing = pair_is_complete(ledger, identities)
        self.assertFalse(complete)
        self.assertEqual([item.seed for item in missing], [3])

    def test_row_count_alone_does_not_imply_completeness(self):
        """Tre righe presenti, ma non le tre attese."""
        expected = [_identity(seed=seed) for seed in (1, 2, 3)]
        unrelated = [_identity(seed=seed, case_id="ALTRO") for seed in (1, 2, 3)]
        ledger = RunLedger([_completed(item) for item in unrelated])
        complete, missing = pair_is_complete(ledger, expected)
        self.assertFalse(complete)
        self.assertEqual(len(missing), 3)

    def test_complete_pair(self):
        identities = [_identity(seed=seed) for seed in (1, 2, 3)]
        ledger = RunLedger([_completed(item) for item in identities])
        complete, missing = pair_is_complete(ledger, identities)
        self.assertTrue(complete)
        self.assertEqual(missing, [])

    def test_failed_but_completed_run_counts_as_done(self):
        """Un fallimento definitivo e' un esito: non va rieseguito all'infinito."""
        identity = _identity()
        row = {**identity.as_dict(), "completed": True, "valid_output": False,
               "error": "StructuredOutputError"}
        self.assertTrue(is_complete(row))
        self.assertEqual(RunLedger([row]).decide(identity).action, SKIP)


class AtomicWriteTest(TestCase):
    def test_append_preserves_previous_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.jsonl"
            for index in range(5):
                append_jsonl_atomic(path, {"index": index})
            rows = read_jsonl(path)
            self.assertEqual([row["index"] for row in rows], list(range(5)))

    def test_no_temporary_file_is_left_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.jsonl"
            append_jsonl_atomic(path, {"a": 1})
            leftovers = [p.name for p in Path(tmp).iterdir() if p.name.startswith(".")]
            self.assertEqual(leftovers, [])

    def test_truncated_final_line_is_discarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.jsonl"
            path.write_text('{"a": 1}\n{"b": tronc', encoding="utf-8")
            rows = read_jsonl(path)
            self.assertEqual(rows, [{"a": 1}])

    def test_write_json_is_atomic_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            write_json(path, {"b": 2, "a": 1})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 1, "b": 2})
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["manifest.json"])

    def test_missing_file_reads_as_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(read_jsonl(Path(tmp) / "assente.jsonl"), [])


class IdentityManifestTest(TestCase):
    def test_manifest_lists_expected_keys(self):
        identities = [_identity(seed=seed) for seed in (1, 2)]
        manifest = identity_manifest(identities)
        self.assertEqual(manifest["expected_run_count"], 2)
        self.assertEqual(len(manifest["run_keys"]), 2)
        self.assertEqual(manifest["run_key_fields"], list(RUN_KEY_FIELDS))

    def test_manifest_handles_empty_input(self):
        self.assertEqual(identity_manifest([])["expected_run_count"], 0)
