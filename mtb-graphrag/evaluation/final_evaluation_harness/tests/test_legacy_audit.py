from evaluation.final_evaluation_harness.common.legacy_audit import audit_legacy_checker


def test_legacy_two_failures_are_explicitly_classified():
    report = audit_legacy_checker()
    assert report["result"] == "45/47"
    assert [failure["assertion"] for failure in report["failures"]] == [
        "runtime_unmodified", "historical_artifacts_untouched"
    ]
    assert report["failures"][0]["classification"] == "EXPECTED_HISTORICAL_RUNTIME_IDENTITY_INCOMPATIBILITY"
    assert report["failures"][0]["blocking"] is False
    assert report["failures"][1]["classification"] == "EXPECTED_HISTORICAL_PROTOCOL_IDENTITY_INCOMPATIBILITY"
    assert report["failures"][1]["blocking"] is False
