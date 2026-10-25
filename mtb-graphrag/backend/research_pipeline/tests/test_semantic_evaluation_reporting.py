"""Evaluation accounting must not reward provider failures as correct abstentions."""


def test_reporting_keeps_failure_and_reference_denominators_separate():
    from scripts.evaluate_semantic_admission_v2 import summarize

    report = summarize([
        {"reference_admission": "DOCUMENT_SUPPORTED", "technical_success": True,
         "observed_admission": "DOCUMENT_SUPPORTED"},
        {"reference_admission": "UNVERIFIABLE", "technical_success": True,
         "observed_admission": "DOCUMENT_SUPPORTED"},
        {"reference_admission": "UNVERIFIABLE", "technical_success": False,
         "observed_admission": "UNVERIFIABLE"},
    ])
    assert report["units_attempted"] == 3
    assert report["technical_completed"] == 2
    assert report["technical_failed"] == 1
    assert report["false_document_supported"] == 1
    assert report["non_support_reference_n"] == 2
    assert report["direct_support_preserved"] == 1
    assert report["direct_support_reference_n"] == 1
    assert report["admission_correct_completed"] == 1
    assert report["independent_gold"] is False


def test_reporting_empty_sample_does_not_manufacture_perfect_accuracy():
    from scripts.evaluate_semantic_admission_v2 import summarize

    report = summarize([])
    assert report["admission_accuracy_completed"] is None
    assert report["units_attempted"] == 0


def test_malformed_provider_envelopes_are_technical_failures():
    from scripts.evaluate_semantic_admission_v2 import classify_attempt

    for body in ([1], {"choices": [1]}):
        outcome, completed = classify_attempt({"status_code": 200, "response": body, "error_type": None},
                                              {"required_context": "text"})
        assert outcome == "MALFORMED_PROVIDER_ENVELOPE"
        assert completed is False
