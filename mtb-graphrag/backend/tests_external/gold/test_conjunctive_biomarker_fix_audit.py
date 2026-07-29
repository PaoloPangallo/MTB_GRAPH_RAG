from __future__ import annotations

import hashlib
import json
from pathlib import Path


from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL

from benchmarks.mtb_evidence.evaluation.scripts.candidate_coverage_audit import (
    _aggregate,
)
from benchmarks.mtb_evidence.evaluation.scripts.conjunctive_biomarker_fix import (
    EXPECTED_AFTER_COUNTS,
    EXPECTED_BEFORE_COUNTS,
    generate_audit,
)


ROOT = Path(__file__).resolve().parents[3]
# Questo modulo sta in `backend/tests_external/gold/`: il bundle e' un
# presupposto, non un'eventualita'. `require` invece di `resolve` perche'
# l'assenza qui e' un errore che deve dire dove ha cercato, non un `None` che
# si propaga fino a un TypeError trenta righe piu' sotto.
GOLD = EXTERNAL.require(EXTERNAL.GOLD_BUNDLE)


V3 = ROOT / "benchmarks" / "mtb_evidence" / "v3"


def _artifact_bytes(path: Path) -> dict[str, bytes]:
    return {
        item.name: item.read_bytes()
        for item in sorted(path.iterdir(), key=lambda item: item.name)
        if item.is_file()
    }


def test_fix_audit_counts_and_reason_codes() -> None:
    frozen = V3 / "conjunctive_biomarker_fix"
    manifest = json.loads((frozen / "fix_manifest.json").read_text("utf-8"))
    diff = json.loads((frozen / "per_query_diff.json").read_text("utf-8"))
    by_case = {row["case_id"]: row for row in diff["queries"]}
    assert manifest["candidate_counts_before"] == EXPECTED_BEFORE_COUNTS
    assert manifest["candidate_counts_after"] == EXPECTED_AFTER_COUNTS
    assert by_case["PILOT-A2-ALK-G1202R"]["removed_count"] == 23
    assert by_case["PILOT-C1-EGFR-L858R-CONTEXT"]["removed_count"] == 7
    assert by_case["PILOT-K1-FGFR2-iCCA"]["removed_count"] == 0
    assert by_case["PILOT-N1-RMI2-SNAPSHOT"]["removed_count"] == 0
    removed = [
        json.loads(line)
        for line in (frozen / "removed_gene_only_matches.jsonl")
        .read_text("utf-8")
        .splitlines()
    ]
    assert len(removed) == 30
    assert {row["reason_code"] for row in removed} == {
        "ALTERATION_MISMATCH_WITH_MATCHING_GENE"
    }
    assert all(
        row["query_gene"]
        and row["query_alteration"]
        and row["statement_gene"]
        and row["statement_alteration"]
        for row in removed
    )
    assert all(row["gold_used"] is False for row in removed)


def test_fix_audit_is_frozen_after_deterministic_generation() -> None:
    frozen = V3 / "conjunctive_biomarker_fix"
    assert _aggregate(ROOT, [frozen])["aggregate_sha256"] == (
        "cf69886100af3f25f06426ad81a3ae811f9c1e76a08c240b5e2c86f41d88638d"
    )
    manifest = json.loads((frozen / "fix_manifest.json").read_text("utf-8"))
    assert manifest["deterministic_order"] == ["query_id", "statement_id"]
    assert manifest["unexpected_changes"] == []


def test_frozen_inputs_and_previous_audit_are_unchanged() -> None:
    expected = {
        "corpus": "bf23a06ac8c122d2257487c0109eb8e0226f2b16d2d733740a6cd008ed34e827",
        "packets": "6bb4ee225e4c273a6f24378dc5c982490cdbf3482a1e780e4c173695fe131bb6",
        "previous_exploration": "f0ca36d81024170a5fe51b32763333468091a1d3b3a15f822bf57694c7f711cd",
        "previous_audit": "43396526a701ba1ec7f4e1f0bbc498a798ca02fd9600deedf7ef1ed442ca7273",
    }
    actual = {
        "corpus": _aggregate(ROOT, [V3 / "qualification_corpus_v2"])[
            "aggregate_sha256"
        ],
        "packets": _aggregate(
            ROOT,
            [V3 / "priority_curation" / "annotation_packets" / "second_review"],
        )["aggregate_sha256"],
        "previous_exploration": _aggregate(
            ROOT, [V3 / "v2_v3a_exploratory_pilot"]
        )["aggregate_sha256"],
        "previous_audit": _aggregate(
            ROOT, [V3 / "candidate_coverage_audit"]
        )["aggregate_sha256"],
    }
    assert actual == expected
    config = (
        ROOT
        / "backend"
        / "pipeline"
        / "evidence"
        / "qualified_retriever_scoring_config.json"
    )
    assert hashlib.sha256(config.read_bytes()).hexdigest() == (
        "57d76d377029ba5c92cf4785d8143e2d06d02b6dc0e0c1d7ef57ea118e553fd4"
    )
    assert json.loads(config.read_text("utf-8"))["hash"] == (
        "ddbfe3cec5d79f0f321b6a853938aa074e55f9ab77149fc73f2ce17224908c00"
    )


def test_fix_harness_has_no_external_or_tuning_surface() -> None:
    source = (
        ROOT
        / "benchmarks"
        / "mtb_evidence"
        / "evaluation"
        / "scripts"
        / "conjunctive_biomarker_fix.py"
    ).read_text("utf-8").casefold()
    assert not any(
        token in source
        for token in ("requests.", "import neo4j", "neo4j.", "openai", "def tune", "weight =")
    )
