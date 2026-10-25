"""Public contracts preserve runtime payloads while rejecting false evidence states."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.research_pipeline.public_schemas import CanonicalDossier, DossierResponse, EventPage, PublicPipelineRun

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "frontend/src/research/__fixtures__/runtime-contract.json"


def report():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["unresolved_report"]


def test_real_runtime_report_round_trips_without_losing_extension_provenance():
    payload = report()
    payload["retrieval_summary"]["snapshot_metadata"] = {"source_hash": "sha256:source"}
    validated = CanonicalDossier.model_validate(payload)
    assert validated.model_dump(exclude_unset=True) == payload


@pytest.mark.parametrize("status", ["INSUFFICIENT_CASE_CONTEXT", "NEEDS_CLARIFICATION", "NO_RELEVANT_KG_EVIDENCE"])
def test_dossier_early_stop_preserves_domain_status(status):
    from backend.research_pipeline.dossier.builder import build_relation_aware_report
    payload = build_relation_aware_report({}, [], run_status=status)
    assert CanonicalDossier.model_validate(payload).model_dump(exclude_unset=True) == payload
    with pytest.raises(ValidationError):
        PublicPipelineRun.model_validate({"run_id": "r1", "case_id": "c1", "status": status, "stages": []})


@pytest.mark.parametrize("field,value", [("support_level", "DIRECT"), ("relation_family", "KG_ONLY")])
def test_paper_branch_rejects_wrong_authoritative_state(field, value):
    payload = report()
    payload["paper_evidence"][0][field] = value
    with pytest.raises(ValidationError):
        CanonicalDossier.model_validate(payload)


def test_validated_quote_requires_document_and_source_unit_references():
    payload = report()
    entry = payload["paper_evidence"][0]
    entry.update(quote="literal source text", quote_valid=True, document_id="pmid:123", quote_source_unit_id=None)
    with pytest.raises(ValidationError, match="source_unit"):
        CanonicalDossier.model_validate(payload)
    entry["quote_source_unit_id"] = "SU-123"
    entry["accepted_evidence_records"] = [{"quote": "literal source text", "quote_valid": True}]
    with pytest.raises(ValidationError, match="document"):
        CanonicalDossier.model_validate(payload)
    entry["accepted_evidence_records"][0].update(paper_id="pmid:123", source_unit_id="SU-123")
    CanonicalDossier.model_validate(payload)


def test_run_rejects_invalid_status_but_preserves_historical_optional_payloads():
    payload = {"run_id": "r1", "case_id": "c1", "status": "STOPPED", "stages": [], "legacy_info": {"mode": "REPLAY"}}
    assert PublicPipelineRun.model_validate(payload).model_dump(exclude_unset=True) == payload
    with pytest.raises(ValidationError):
        PublicPipelineRun.model_validate({**payload, "status": "DIRECT"})


def test_event_page_retains_full_and_compact_payload_extensions():
    payload = {"run_id": "r1", "append_only": True, "hash_chain_valid": True, "events": [{
        "event_id": "e1", "sequence": 1, "event_type": "RUN_COMPLETED", "created_at": "now", "actor": "runtime",
        "stage_id": None, "stage_type": None, "producer": None, "payload_hash": "hash",
        "payload": {"status": "STOPPED", "future_audit": {"source": "ledger"}},
    }], "next_after_sequence": 1, "has_more": False}
    assert EventPage.model_validate(payload).model_dump(exclude_unset=True) == payload


def test_generated_frontend_contracts_are_current():
    from scripts.generate_research_contracts import render_contracts
    assert (ROOT / "frontend/src/research/contracts.generated.ts").read_text(encoding="utf-8") == render_contracts()


def test_dossier_envelope_accepts_actual_trace_and_archived_legacy_only():
    from backend.research_pipeline.narrative.input_projection import build_narrative_trace
    payload = {"run_id": "r1", "status": "COMPLETED", "dossier": report(), "narrative_trace": build_narrative_trace(report())}
    assert DossierResponse.model_validate(payload).model_dump(exclude_unset=True) == payload
    DossierResponse.model_validate({"run_id": "r1", "status": "COMPLETED", "dossier": {"candidate_therapies": []}})
    payload["dossier"]["run_status"] = "DIRECT"
    with pytest.raises(ValidationError):
        DossierResponse.model_validate(payload)


def test_builder_accepted_and_rejected_observations_preserve_exact_source_records():
    from backend.research_pipeline.dossier.builder import build_relation_aware_report
    from backend.research_pipeline.tests.test_dossier_aggregation_redesign import _candidate, _record
    records = [_record("FULL_SUPPORT"), _record("FULL_SUPPORT", valid=False, unit="SU-REJECTED")]
    payload = build_relation_aware_report({}, [_candidate()], {"GCA-CLAIM-1": {"evidence_records": records}})
    assert CanonicalDossier.model_validate(payload).model_dump(exclude_unset=True) == payload


def test_validated_quote_cannot_reference_an_unselected_source_unit():
    payload = report()
    payload["paper_evidence"][0].update(quote="literal", quote_valid=True, document_id="pmid:123",
        quote_source_unit_id="SU-WRONG", selected_source_unit_ids=["SU-SELECTED"])
    with pytest.raises(ValidationError, match="selected source"):
        CanonicalDossier.model_validate(payload)
