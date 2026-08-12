from __future__ import annotations

import copy

from check_consistency import h01_identity_checks, load


def test_checker_rejects_tampered_expected_normative_hash():
    amendment = load("amendment_contract.json")
    report = load("../final_protocol_v1_6_candidates/rq4/review_report.json")
    tampered = copy.deepcopy(amendment)
    tampered["H01"]["normative_sha256"] = "0" * 64
    assert h01_identity_checks(tampered, report)["h01_normative_recomputed"] is False


def test_checker_rejects_tampered_expected_support_hash():
    amendment = load("amendment_contract.json")
    report = load("../final_protocol_v1_6_candidates/rq4/review_report.json")
    tampered = copy.deepcopy(amendment)
    tampered["H01"]["support_sha256"] = "0" * 64
    assert h01_identity_checks(tampered, report)["h01_support_recomputed"] is False


def test_checker_does_not_trust_report_hash_only():
    amendment = load("amendment_contract.json")
    report = load("../final_protocol_v1_6_candidates/rq4/review_report.json")
    tampered = copy.deepcopy(report)
    tampered["normative_sha256"] = "0" * 64
    assert h01_identity_checks(amendment, tampered)["h01_identity_recorded"] is False

