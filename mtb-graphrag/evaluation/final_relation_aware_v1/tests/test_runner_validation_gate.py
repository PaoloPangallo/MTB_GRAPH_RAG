from evaluation.final_relation_aware_v1.run_rq3 import relation_support_allowed


def test_rejected_validation_cannot_reach_relation_support():
    assert relation_support_allowed({"outcome": "QUOTE_INVALID"}) is False
    assert relation_support_allowed({"outcome": "REJECTED_TRANSPORT"}) is False


def test_only_accepted_validation_reaches_relation_support():
    assert relation_support_allowed({"outcome": "ENRICHMENT_V3_ACCEPTED"}) is True
