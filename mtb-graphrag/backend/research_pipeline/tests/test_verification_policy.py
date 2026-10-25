"""Support policy must declare its scope and enforce required context."""
from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.tests.test_relation_support_contract_v5 import candidate, observation


def test_required_evidence_context_cannot_be_omitted_for_full_support():
    target = candidate()
    target["source_properties"] = {"relation_contract": {"evidence_context_required": True}}
    result = assess_relation_support(target, observation(),
                                     source_unit_text="BRAF V600E showed sensitivity to vemurafenib.")
    assert result["result"] != "FULL_SUPPORT"
    assert "evidence_context" in result["required"]
    assert result["fields"]["evidence_context"] == "NOT_CONFIRMED"


def test_source_policy_declares_semantic_and_deterministic_boundaries():
    from backend.research_pipeline.enrichment.verification_policy import policy_for

    semantic = policy_for({"relation_family": "EVIDENCE_DRUG"})
    molecular = policy_for({"relation_family": "VARIANT_GENE"})
    statement = policy_for({"relation_family": "EVIDENCE_STATEMENT"})
    assert semantic.requires_semantic_comparison
    assert not molecular.requires_semantic_comparison
    assert not statement.requires_semantic_comparison
    assert statement.policy_id == "paper-relation-verifier/5.2"
    assert semantic.to_dict()["clinical_applicability"] == "NOT_EVALUATED"
    assert semantic.policy_id != molecular.policy_id


def test_deterministic_assessment_preserves_policy_provenance():
    result = assess_relation_support(candidate(), observation(),
                                     source_unit_text="BRAF V600E showed sensitivity to vemurafenib.")
    assert result["verification_policy"]["scope"] == "SOURCE_RELATION_CORRESPONDENCE"
    assert result["verification_policy"]["clinical_applicability"] == "NOT_EVALUATED"


def test_public_trace_keeps_quote_hash_and_locators_but_not_source_context():
    from backend.research_pipeline.enrichment.verification_policy import public_verification_trace

    trace = {"final_admission": "DOCUMENT_SUPPORTED", "GEP_snapshot": {
        "quote": "literal excerpt", "required_context": "whole private SourceUnit",
        "source_unit_id": "SU-1", "document_id": "pmid:1"},
        "target_snapshot": {"candidate_id": "GCA-1", "evidence_statement": "curated prose"}}
    public = public_verification_trace(trace)
    assert "required_context" not in public["GEP_snapshot"]
    assert "evidence_statement" not in public["target_snapshot"]
    assert public["GEP_snapshot"]["quote"] == "literal excerpt"
    assert len(public["GEP_snapshot"]["context_sha256"]) == 64
    assert trace["GEP_snapshot"]["required_context"] == "whole private SourceUnit"


def test_public_recorder_never_persists_source_unit_context_at_any_depth(tmp_path):
    import json
    from backend.pipeline.agentic.ledger import EventLedger
    from backend.research_pipeline.recording import RunRecorder
    from backend.research_pipeline.contracts import StageProducer
    from backend.research_pipeline.enrichment.verification_policy import public_artifact

    private = "private-source-sentinel outside the literal quote"
    artifact = {"evidence_records": [{"quote": "literal quote", "source_unit_text": private}],
                "legacy_dossier": {"author_context": {"source_unit_text": private}}}
    ledger = EventLedger(tmp_path / "privacy.sqlite3")
    recorder = RunRecorder(ledger, "run", "LIVE")
    stage = recorder.finish("stage_13_dossier", StageProducer(kind="DETERMINISTIC", component="dossier", version="test"),
                            domain_event="DOSSIER_BUILT", output_preview=artifact)
    assert private not in json.dumps(ledger.events("run"))
    assert private not in json.dumps(stage.to_dict())
    record = public_artifact(artifact)["evidence_records"][0]
    assert record["quote"] == "literal quote"
    assert len(record["source_unit_sha256"]) == 64
    assert record["source_unit_chars"] == len(private)
    assert artifact["evidence_records"][0]["source_unit_text"] == private
