import json
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import data_access as da, orchestrator, replay
from backend.research_pipeline.cases.definitions import CASES
from backend.research_pipeline.pipeline import CallBudget
from backend.research_pipeline.retrieval import kg_retrieval
from backend.research_pipeline.retrieval.relation_family import classify_relation_family


CASE_ID = "CASE-1-therapy-evaluation-strong-match"
SOURCE_UNIT_ID = "SU-6e4d5a52c9be05f545487ad0"
SOURCE_TEXT = (
    "metastatic colorectal cancer. patients with mCRC bearing KRAS mutations are "
    "clinically resistant to therapy with panitumumab or cetuximab."
)


def _case_text():
    return next(row["clinical_text"] for row in CASES if row["case_id"] == CASE_ID)


def test_case1_explicit_frozen_replay_exposes_historical_relation_aware_report():
    with TemporaryDirectory() as tmp:
        run = orchestrator.run_case(
            case_id=CASE_ID,
            clinical_text=_case_text(),
            call_parser_fn=replay.parser_fn,
            call_enricher_fn=replay.enricher_fn,
            source_units_by_id={SOURCE_UNIT_ID: {"source_unit_id": SOURCE_UNIT_ID, "text": SOURCE_TEXT}},
            budget=CallBudget(3),
            ledger=EventLedger(Path(tmp) / "case1.sqlite3"),
            research_frozen_artifacts=True,
            retrieve_fn=kg_retrieval.retrieve_frozen_bundles,
            select_papers_fn=lambda association, units, **kw: replay.selection_fn(
                association, units, case_id=kw["case_id"]),
            validate_fn=lambda transport, enrichment, **kw: replay.validation_fn(
                transport, enrichment, case_id=kw["case_id"], paper_id=kw["paper_id"]),
            call_narrator_fn=None,
        )

    output = run.to_dict()
    report = output["relation_aware_report"]
    entry = report["paper_evidence"][0]
    assert entry["document_id"] == "pmid:19223544"
    assert entry["support_level"] == "PARTIAL_SUPPORT"
    assert entry["support_fields"]["alteration"] == "NOT_CONFIRMED"
    assert json.dumps(output, sort_keys=True)


def test_runtime_wires_all_relation_families_without_writer():
    candidates = kg_retrieval.load_candidates()
    selected = [
        next(row for row in candidates.values() if classify_relation_family(row) == family)
        for family in ("PAPER_EVIDENCE", "CLINICAL_TRIAL", "KG_ONLY")
    ]
    parser_result = {
        "transport_result": "FORCED_TOOL_VALID",
        "model": "offline-test",
        "prompt_version": "offline-test",
        "case_context_raw": {
            "case_id": "CASE-MULTI-FAMILY",
            "disease": {"raw_value": "lung cancer"},
            "biomarkers": [{"gene": "KRAS", "alteration": "G12D"}],
            "target_intervention": {"raw_value": "drug"},
            "query_intent": "THERAPY_EVALUATION",
        },
    }

    with TemporaryDirectory() as tmp:
        run = orchestrator.run_case(
            case_id="CASE-MULTI-FAMILY",
            clinical_text="lung cancer with KRAS G12D; therapy evaluation",
            call_parser_fn=lambda budget, case_id, text: parser_result,
            call_enricher_fn=lambda *args, **kwargs: {"transport_result": "V2_TRANSPORT_VALID", "enrichment": None},
            source_units_by_id={},
            budget=CallBudget(3),
            ledger=EventLedger(Path(tmp) / "multi.sqlite3"),
            research_frozen_artifacts=True,
            retrieve_fn=lambda _: {
                "query_intent": "THERAPY_EVALUATION",
                "associations": [
                    {"candidate_id": c["candidate_id"], "candidate": c, "relation_family": None, "match_reason_codes": [], "available_bundles": []}
                    for c in selected
                ],
                "excluded_candidates": [],
                "no_match": False,
            },
            match_verifier_fn=lambda case_context, clinical_text: {
                "records": [], "essential_fields_pass": True, "warnings": [], "bypassed": True,
            },
            eligibility_gate_fn=lambda clinical_text, case_context: None,
            call_narrator_fn=None,
        )

    report = run.to_dict()["relation_aware_report"]
    assert len(report["paper_evidence"]) == 1
    assert len(report["clinical_trials"]) == 1
    assert len(report["kg_only_relations"]) == 1
    assert report["clinical_trials"][0]["evidence_interpretation"] == "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"
    assert report["kg_only_relations"][0]["verification_status"] == "KG_ONLY"
    assert report["kg_only_relations"][0]["document_provenance"] == "NOT_AVAILABLE"
