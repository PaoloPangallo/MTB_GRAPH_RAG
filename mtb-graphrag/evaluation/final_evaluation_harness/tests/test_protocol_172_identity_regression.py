from __future__ import annotations

import json

import pytest

from evaluation.final_evaluation_harness.common.identities import evaluation_id
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol


RUNTIME_COMMIT = "586bf27885c11173510a6bd0b93db3f3ac0f222a"
HARNESS_COMMIT = "3b0d326509d2a11fc69214b420074e4164ae354e"


def _seal(protocol):
    return json.loads((protocol.root / "seal_manifest.json").read_text(encoding="utf-8"))


def _sealed_plan(protocol):
    return json.loads((protocol.root / "sealed_plan_manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def protocol():
    return load_protocol()


def test_seal_evaluation_id_matches_start_computed_identity(protocol):
    assert _seal(protocol)["evaluation_id"] == evaluation_id(protocol, protocol.hashes["runtime_commit"])


def test_seal_evaluation_id_matches_plan_evaluation_identity(protocol):
    assert _seal(protocol)["evaluation_id"] == _sealed_plan(protocol)["evaluation_id"]


def test_provenance_harness_commit_does_not_change_runtime_bound_identity(protocol):
    original = protocol.manifest["harness_commit"]
    protocol.manifest["harness_commit"] = "0" * 40
    try:
        assert evaluation_id(protocol, protocol.hashes["runtime_commit"]) == evaluation_id(protocol, protocol.hashes["runtime_commit"])
    finally:
        protocol.manifest["harness_commit"] = original


def test_runtime_commit_changes_evaluation_id(protocol):
    assert evaluation_id(protocol, RUNTIME_COMMIT) != evaluation_id(protocol, "0" * 40)


def test_harness_commit_remains_provenance_in_manifest(protocol):
    assert protocol.manifest["harness_commit"] == HARNESS_COMMIT
    assert protocol.lineage["harness_commit"] == HARNESS_COMMIT
    assert protocol.amendment["P17"]["harness_commit"] == HARNESS_COMMIT
    assert _seal(protocol)["harness_commit"] == HARNESS_COMMIT
    assert _sealed_plan(protocol)["harness_commit"] == HARNESS_COMMIT
