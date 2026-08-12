from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.readiness import audit_readiness


def test_readiness_is_222_without_scientific_calls():
    report = audit_readiness(load_protocol(), harness_commit="TEST")
    assert report["units"] == 222
    assert report["registry_bound"] == 222
    assert report["static_production_callable"] == 222
    assert report["semantically_ready"] == 222
    assert report["protocol_compliant"] == 222
    assert report["ambiguous"] == 0
    assert report["unbound"] == 0
    assert report["symbolic_only"] == 0
    assert report["fail_closed_placeholders"] == 0
    assert report["units_requiring_scientific_decision"] == 0
    assert report["units_requiring_runtime_change"] == 0
    assert report["calls"] == {"runtime": 0, "selector": 0, "gemma": 0, "narrator": 0, "verifier": 0, "network": 0}


def test_rq4_heldout_rows_bind_h01_identity():
    report = audit_readiness(load_protocol(), harness_commit="TEST")
    rows = [row for row in report["rows"] if row["family"] == "RQ4_HELDOUT"]
    assert len(rows) == 35
    assert {row["h01_contract_sha256"] for row in rows} == {"0e0a312f9b8f6be62095f47f0a0bffe40004189387835b1d4243c54165d210c2"}
