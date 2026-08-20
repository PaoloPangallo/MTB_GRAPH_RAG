from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.runner import build_full_plan


def test_loader_requires_frozen_protocol_16_and_exact_identities(monkeypatch):
    monkeypatch.setenv("MTB_EVALUATION_PROTOCOL_VERSION", "1.7")
    protocol = load_protocol()
    assert protocol.manifest["protocol_version"] == "1.7"
    assert protocol.manifest["frozen"] is True
    assert protocol.manifest["review_status"] == "ACCEPTED"
    assert protocol.seal["protocol_sha256"] == "165791022ee91e6a751f82b2b8465f5e1a09e45a17a072e185e1956c11f2cab6"
    assert protocol.amendment["H01"]["normative_sha256"] == "0e0a312f9b8f6be62095f47f0a0bffe40004189387835b1d4243c54165d210c2"
    assert protocol.amendment["P17"]["runtime_commit"] == "628545074280e70f8382a457a352f85d3d64c094"


def test_plan_has_exact_frozen_family_counts(monkeypatch):
    monkeypatch.setenv("MTB_EVALUATION_PROTOCOL_VERSION", "1.7")
    plans = build_full_plan(load_protocol())
    counts = {}
    for plan in plans:
        counts[plan.rq] = counts.get(plan.rq, 0) + 1
    assert counts == {
        "RQ1": 1,
        "RQ2": 80,
        "RQ3": 5,
        "RQ4_DEVELOPMENT": 35,
        "RQ4_HELDOUT": 35,
        "NARRATIVE": 25,
        "OPERATIONAL_A01": 9,
        "RELIABILITY": 30,
        "LATENCY": 2,
    }
    assert len(plans) == 222
