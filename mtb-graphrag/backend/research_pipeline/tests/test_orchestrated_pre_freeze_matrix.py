"""Real orchestrator journeys with deterministic providers and documents.

Only Parser, Reader, document resolution/content, and the source dataset boundary
are controlled. ``run_case`` performs the production validation, retrieval,
selector, verifier, gates, accounting, aggregation, and dossier projection.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline.casecontext.parser import adapt_case_context
from backend.research_pipeline.documents.live_resolution import (
    DocumentResolution,
    ResolvedDocument,
    SourceUnitBundle,
    _preview_for,
)
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3
from backend.research_pipeline.orchestrator import run_case
from backend.research_pipeline.pipeline import CallBudget
from backend.research_pipeline.retrieval.composite_evidence import derive_composite_relations
from backend.research_pipeline.retrieval.kg_retrieval import load_candidates


def _value(value: str) -> dict[str, str]:
    return {"raw_value": value, "quote": value}


def _parser_output(
    raw: str,
    *, disease: str = "lung cancer",
    biomarkers: tuple[tuple[str, str | None], ...] = (("EGFR", "L858R"),),
    interventions: tuple[tuple[str, str], ...] = (("erlotinib", "TARGET"),),
    negated: bool = False,
    trials: tuple[str, ...] = (),
    diagnostics: tuple[str, ...] = (),
) -> dict:
    return {
        "disease": _value(disease),
        "diseases": [{"value": _value(disease), "assertion_status": "PRESENT",
                       "clinical_role": "PRIMARY"}],
        "biomarkers": [{
            "gene": _value(gene), "alteration": _value(variant) if variant is not None else None,
            "alteration_type": "MUTATION",
            "assertion_status": "NEGATED" if negated else "PRESENT",
            "clinical_role": "PRIMARY",
        } for gene, variant in biomarkers],
        "interventions": [{"name": _value(drug), "role": role,
                            "assertion_status": "PRESENT"}
                           for drug, role in interventions],
        "query_intent": "THERAPY_EVALUATION",
        "trial_mentions": [{"nct_id": _value(nct)} for nct in trials],
        "companion_diagnostic_mentions": [{"name": _value(name)} for name in diagnostics],
    }


def _paper_candidate(candidate_id: str = "GCA4-E2E-PAPER", **changes) -> dict:
    candidate = {
        "candidate_id": candidate_id,
        "semantic_key": "EVIDENCE_STATEMENT|Evidence:E2E",
        "predicate": "associated_with_sensitivity_to",
        "direction": "Supports",
        "disease": [{"label": "lung cancer", "type": "Disease"}],
        "biomarkers": [
            {"label": "EGFR", "type": "Gene"},
            {"label": "L858R", "type": "Variant", "gene": "EGFR",
             "alteration": "L858R", "linked_gene": "EGFR"},
        ],
        "interventions": [{"label": "erlotinib", "type": "Drug"}],
        "document_identifiers": [{"pmid": "12345678"}],
        "source_record_ids": ["source-row:1"],
        "source_datasets": ["clean_graph/evidence_statement.csv"],
        "edge_ids": ["edge:e2e:1"],
        "node_ids": ["Gene:EGFR", "Variant:L858R", "Evidence:E2E"],
        "graph_path": ["Gene:EGFR", "Variant:L858R", "Evidence:E2E"],
        "source_properties": {"relation_contract": {"disease_required": True}},
    }
    candidate.update(changes)
    return candidate


def _trial_candidate(*, gene: str = "KRAS", nct: str = "NCT12345678") -> dict:
    return {
        "candidate_id": f"GCA4-E2E-TRIAL-{gene}",
        "semantic_key": f"CLINICAL_TRIAL|{nct}",
        "predicate": "clinical_trial_investigates",
        "direction": "Associates",
        "document_identifiers": [{"nct": nct}],
        "trial_context": {"nct_id": nct, "genes": [gene], "conditions": ["lung cancer"],
                           "interventions_raw": ["erlotinib"], "interventions_normalized": []},
        "biomarkers": [], "interventions": [{"label": "erlotinib", "type": "Drug"}],
        "disease": [], "source_record_ids": [f"trial-row:{gene}"],
        "source_datasets": ["clean_graph/clinical_trials.csv"], "edge_ids": [f"trial-edge:{gene}"],
        "node_ids": [f"ClinicalTrial:{nct}"], "graph_path": [f"ClinicalTrial:{nct}"],
    }


class ControlledDocumentRuntime:
    """Deterministic document boundary consumed by the production orchestrator."""

    descriptor = {"document_cache_available": True, "manifest_hash": "fixture-manifest"}
    manifest_hash = "fixture-manifest"

    def __init__(self, units: list[dict], *, unavailable: bool = False,
                 trial_failed: bool = False) -> None:
        self.units = units
        self.unavailable = unavailable
        self.trial_failed = trial_failed
        self.manifest_by_document_id: dict[str, dict] = {}

    def resolve(self, associations) -> DocumentResolution:
        documents = []
        for association in associations:
            for bundle in association.get("available_bundles") or []:
                document_id = bundle["document_id"]
                is_trial = document_id.startswith("nct:")
                failed = self.unavailable or (is_trial and self.trial_failed)
                availability = "RESOLUTION_FAILED" if (is_trial and self.trial_failed) else (
                    "NOT_RESOLVED" if self.unavailable else "PMC_XML_AVAILABLE"
                )
                self.manifest_by_document_id[document_id] = {
                    "availability": availability,
                    "nct_id": document_id[4:] if is_trial else None,
                }
                documents.append(ResolvedDocument(
                    document_id=document_id,
                    bundle_id=bundle["bundle_id"],
                    candidate_id=association["candidate_id"],
                    availability=availability,
                    resolved=not failed,
                    cache_hit=not failed,
                    document_type="CLINICAL_TRIAL_RECORD" if is_trial else "FULL_TEXT_ARTICLE",
                    source="controlled-fixture",
                    metadata_only=False,
                    abstract_available=False,
                    full_text_available=not failed,
                    content_hash=f"controlled:{document_id}",
                    reason_codes=("RESOLUTION_FAILED",) if failed else ("FIXTURE_DOCUMENT_RESOLVED",),
                    lineage={"requested_document_id": document_id,
                             "retrieval_mode": "CONTROLLED_FIXTURE"},
                ))
        return DocumentResolution(tuple(documents), "<controlled>", self.manifest_hash)

    def load_units(self, resolution: DocumentResolution) -> SourceUnitBundle:
        resolved_ids = {doc.document_id for doc in resolution.documents if doc.resolved}
        units = {unit["source_unit_id"]: dict(unit) for unit in self.units
                 if unit["document_id"] in resolved_ids}
        return SourceUnitBundle(
            units_by_id=units,
            previews=tuple(_preview_for(unit) for unit in units.values()),
            documents_parsed=len(resolved_ids),
        )


def _reader_observation(candidate: dict, source_units: list[dict], *, fail=False) -> dict:
    if fail:
        return {"transport_result": "V3_TRANSPORT_VALID", "enrichment": None,
                "model": "deterministic-reader-stub", "prompt_version": "fixture/1"}
    unit = source_units[0]
    biomarkers = candidate.get("biomarkers") or []
    gene = next((x["label"] for x in biomarkers if x.get("type") == "Gene"), None)
    variant = next((x["label"] for x in biomarkers if x.get("type") in {"Variant", "Alteration"}), None)
    drug = next((x["label"] for x in candidate.get("interventions") or []), None)
    subjects = []
    if gene:
        subjects.append({"type": "GENE", "surface_value": gene})
    if variant:
        subjects.append({"type": "ALTERATION", "surface_value": variant})
    disease_values = candidate.get("disease") or []
    disease = disease_values[0].get("label") if disease_values else "lung cancer"
    return {
        "transport_result": "V3_TRANSPORT_VALID",
        "model": "deterministic-reader-stub", "prompt_version": "fixture/1",
        "enrichment": {
            "decision": "QUOTE", "source_unit_id": unit["source_unit_id"],
            "quote": unit["text"], "observed_evidence_type": "PREDICTIVE_ASSOCIATION",
            "observed_relation": {
                "subjects": subjects,
                "subject_pairings": ([{"gene": gene, "alteration": variant}]
                                     if gene and variant else []),
                "intervention": drug, "disease": disease,
                "effect_direction": "SENSITIVITY_RESPONSE",
                "observed_stance": "SUPPORTS", "relation_scope": "SINGLE",
                "relation_assertion": "RELATION_ASSERTED",
            },
        },
    }


def _run_orchestrated(
    tmp_path: Path,
    case_id: str,
    raw: str,
    parser_output: dict,
    candidates: dict[str, dict],
    units: list[dict],
    *,
    unavailable=False,
    trial_failed=False,
    reader_failure=False,
    reader_force_positive=False,
    reader_budgeted=False,
    semantic_fn=None,
    budget_max=20,
):
    case_context = adapt_case_context(case_id, parser_output, raw)

    def parser_provider(_budget, _case_id, _clinical_text):
        return {
            "transport_result": "FORCED_TOOL_VALID",
            "case_context_raw": case_context,
            "model": "deterministic-parser-stub", "prompt_version": "fixture/1",
        }

    def reader_provider(_budget, _case_id, _candidate_id, _document_id,
                        _case_context, candidate, _requested_drug, source_units):
        if reader_budgeted:
            from backend.research_pipeline.live_providers import LiveStageFailed
            from backend.research_pipeline.pipeline import CallBudgetExceeded
            try:
                _budget.spend("paper_context_enricher_v3", _case_id)
            except CallBudgetExceeded as error:
                raise LiveStageFailed("stage_9_paper_context_enricher",
                                      "CALL_BUDGET_EXCEEDED", str(error)) from error
        result = _reader_observation(candidate, source_units, fail=reader_failure)
        if reader_force_positive and result.get("enrichment"):
            result["enrichment"]["observed_relation"]["relation_assertion"] = "RELATION_ASSERTED"
            result["enrichment"]["observed_relation"]["observed_stance"] = "SUPPORTS"
        return result

    runtime = ControlledDocumentRuntime(
        units, unavailable=unavailable, trial_failed=trial_failed,
    )
    ledger_path = tmp_path / f"{case_id}.sqlite3"
    with patch("backend.research_pipeline.retrieval.kg_retrieval.load_candidates",
               return_value=candidates):
        try:
            run = run_case(
                case_id=case_id,
                clinical_text=raw,
                call_parser_fn=parser_provider,
                call_enricher_fn=reader_provider,
                source_units_by_id={},
                budget=CallBudget(budget_max),
                ledger=EventLedger(ledger_path),
                document_runtime=runtime,
                validate_fn=validate_enrichment_v3,
                call_semantic_alignment_fn=semantic_fn,
            )
        finally:
            for suffix in ("", "-wal", "-shm"):
                Path(f"{ledger_path}{suffix}").unlink(missing_ok=True)
    report = run.relation_aware_report
    if report is not None:
        accounting = report["pipeline_accounting"]
        parsed_mentions = accounting["parsed_mentions"]
        assert parsed_mentions, case_id
        assert {"disease", "biomarker", "intervention", "trial", "companion_diagnostic"}.issubset(
            parsed_mentions
        ), (case_id, parsed_mentions.keys())
        for category in parsed_mentions.values():
            assert category["parsed"] == category["accepted"] + category["rejected"], (
                case_id, category
            )
        assert accounting["retrieved_candidates"]["unaccounted_count"] == 0, case_id
        assert accounting["reader_attempts"]["total"] == (
            accounting["accepted_evidence"]["count"]
            + accounting["rejected_or_failed_evidence"]["count"]
        ), case_id
        assert accounting["accepted_evidence"]["unclaimed_ids"] == [], case_id
        assert accounting["final_claims"]["unknown_evidence_ids"] == [], case_id
    return run


def _source_unit(text: str, *, document_id="pmid:12345678", unit_id="SU-1") -> dict:
    return {"source_unit_id": unit_id, "document_id": document_id,
            "unit_type": "FULLTEXT_SENTENCE", "section": "Results",
            "sentence_index": 1, "text": text,
            "content_hash": f"hash:{unit_id}"}


def test_orchestrator_exact_variant_positive_reaches_full_dossier() -> None:
    raw = "lung cancer with EGFR L858R; current target erlotinib."
    candidate = _paper_candidate()
    quote = "EGFR L858R was associated with sensitivity to erlotinib in lung cancer."
    run = _run_orchestrated(
        Path(__file__).parent, "orchestrated-exact-positive", raw,
        _parser_output(raw), {candidate["candidate_id"]: candidate},
        [_source_unit(quote)],
    )

    assert run.relation_aware_report is not None, (run.stopped_at, [
        (stage.stage_id, stage.status, stage.reason_codes, stage.output_preview)
        for stage in run.stages[:3]
    ])
    assert run.relation_aware_report["paper_evidence"][0]["claim"]["status"] == "FULL_SUPPORT"
    claim = run.relation_aware_report["paper_evidence"][0]["claim"]
    assert claim["supporting_evidence_ids"]
    assert claim["document_ids"] == ["pmid:12345678"]
    assert claim["source_unit_ids"] == ["SU-1"]
    assert run.relation_aware_report["paper_evidence"][0]["accepted_evidence_records"][0][
        "public_source_identity"
    ] == "pmid:12345678"
    assert claim["source_record_ids"] == ["source-row:1"]
    assert claim["source_datasets"] == ["clean_graph/evidence_statement.csv"]
    assert claim["edge_ids"] == ["edge:e2e:1"]
    stages = {stage.stage_id: stage for stage in run.stages}
    assert stages["stage_3b_pre_retrieval_eligibility_gate"].status == "SUCCEEDED"
    assert stages["stage_5_kg_retrieval"].status == "SUCCEEDED"
    assert stages["stage_8_paper_selection"].status == "SUCCEEDED"
    assert stages["stage_10_enrichment_validation"].output_preview["validations"][0]["outcome"] == "ENRICHMENT_V3_ACCEPTED"
    assert stages["stage_13_dossier"].output_preview["relation_aware_report"]["paper_evidence"][0]["claim"]["status"] == "FULL_SUPPORT"


def test_semantic_budget_exhaustion_is_unverifiable_and_keeps_dossier_partial(tmp_path: Path) -> None:
    raw = "lung cancer with EGFR L858R; current target erlotinib."
    candidate = _paper_candidate(
        relation_family="EVIDENCE_DRUG",
        object={"type": "Drug", "label": "erlotinib"},
    )
    quote = "EGFR L858R was associated with sensitivity to erlotinib in lung cancer."

    def semantic_budget_rejected(budget, case_id, _target, _gep):
        budget.spend("semantic_alignment_verifier", case_id)

    run = _run_orchestrated(
        tmp_path, "semantic-budget-exhausted", raw, _parser_output(raw),
        {candidate["candidate_id"]: candidate}, [_source_unit(quote)],
        semantic_fn=semantic_budget_rejected, budget_max=0,
    )

    assert run.status == "PARTIAL"
    assert run.stopped_at == "CALL_BUDGET_EXCEEDED"
    stages = {stage.stage_id: stage for stage in run.stages}
    reader_result = stages["stage_9_paper_context_enricher"].output_preview["calls"]
    assert len(reader_result) == 1
    validation = stages["stage_10_enrichment_validation"].output_preview
    assert validation["validations"][0]["outcome"] == "ENRICHMENT_V3_ACCEPTED"
    semantic = validation["semantic_verification"]
    assert semantic["attempted_calls"] == 0
    assert semantic["budget_rejected_calls"] == 1
    assert semantic["attempts"][0]["status"] == "NOT_EXECUTED_BUDGET"
    paper = run.relation_aware_report["paper_evidence"][0]
    assert paper["claim"]["status"] == "UNVERIFIABLE"
    assert not paper["claim"]["supporting_evidence_ids"]


def test_reader_budget_exhaustion_keeps_prior_quote_validation_in_partial_dossier() -> None:
    raw = "lung cancer with EGFR L858R; current target erlotinib."
    first = _paper_candidate(relation_family="EVIDENCE_DRUG")
    second = _paper_candidate(
        relation_family="EVIDENCE_DRUG",
        candidate_id="GCA4-E2E-PAPER-SECOND",
        semantic_key="EVIDENCE_DRUG|Evidence:E2E-SECOND|Drug:erlotinib",
        source_record_ids=["source-row:2"], edge_ids=["edge:e2e:2"],
    )
    quote = "EGFR L858R was associated with sensitivity to erlotinib in lung cancer."
    run = _run_orchestrated(
        Path(__file__).parent, "reader-budget-preserves-validation", raw, _parser_output(raw),
        {first["candidate_id"]: first, second["candidate_id"]: second},
        [_source_unit(quote)], reader_force_positive=True, reader_budgeted=True,
        budget_max=1,
    )

    assert run.status == "PARTIAL"
    assert run.stopped_at == "CALL_BUDGET_EXCEEDED"
    stages = {stage.stage_id: stage for stage in run.stages}
    reader = stages["stage_9_paper_context_enricher"].output_preview
    validation = stages["stage_10_enrichment_validation"].output_preview
    assert len(reader["calls"]) == 1
    assert reader["pending_requests"][0]["candidate_id"] == second["candidate_id"]
    assert len(validation["validations"]) == 1
    assert validation["validations"][0]["outcome"] == "ENRICHMENT_V3_ACCEPTED"
    assert validation["validations"][0]["document_verification"]["structural_status"] == "PASS"
    assert validation["semantic_verification"]["attempted_calls"] == 0
    assert validation["semantic_verification"]["attempts"] == []
    assert stages["stage_13_dossier"].status == "WARNING"
    assert run.relation_aware_report["publication_status"] == "INCOMPLETE"
    assert run.relation_aware_report["run_status"] == "PARTIAL"


def _run_summary(run) -> dict:
    stages = {stage.stage_id: stage for stage in run.stages}
    report = run.relation_aware_report or {}
    paper = report.get("paper_evidence") or []
    trials = report.get("clinical_trials") or []
    return {
        "run_status": run.status,
        "stopped_at": run.stopped_at,
        "retrieved": stages.get("stage_5_kg_retrieval").output_preview if stages.get("stage_5_kg_retrieval") else None,
        "selection": stages.get("stage_8_paper_selection").output_preview if stages.get("stage_8_paper_selection") else None,
        "validation": stages.get("stage_10_enrichment_validation").output_preview if stages.get("stage_10_enrichment_validation") else None,
        "paper_claims": [item["claim"] for item in paper],
        "trial_records": trials,
        "kg_claims": [item["claim"] for item in report.get("kg_only_relations") or []],
        "accounting": report.get("pipeline_accounting"),
        "report": report,
    }


def test_orchestrator_rejects_wrong_variant_and_wrong_disease(tmp_path: Path) -> None:
    candidate = _paper_candidate()
    quote = "EGFR L858R was associated with sensitivity to erlotinib in lung cancer."
    wrong_variant = _run_orchestrated(
        tmp_path, "orchestrated-wrong-variant", "lung cancer with EGFR G12C; current target erlotinib.",
        _parser_output("", biomarkers=(("EGFR", "G12C"),)),
        {candidate["candidate_id"]: candidate}, [_source_unit(quote)],
    )
    wrong_disease = _run_orchestrated(
        tmp_path, "orchestrated-wrong-disease", "breast cancer with EGFR L858R; current target erlotinib.",
        _parser_output("", disease="breast cancer"),
        {candidate["candidate_id"]: candidate}, [_source_unit(quote)],
    )
    assert wrong_variant.relation_aware_report["paper_evidence"] == []
    assert wrong_disease.relation_aware_report["paper_evidence"] == []


def test_orchestrator_multigene_pairing_and_negation_are_preserved(tmp_path: Path) -> None:
    candidate = _paper_candidate()
    quote = "EGFR L858R was associated with sensitivity to erlotinib in lung cancer."
    multi = _run_orchestrated(
        tmp_path, "orchestrated-multi-pair", "lung cancer with EGFR L858R and KRAS G12C; current target erlotinib.",
        _parser_output("", biomarkers=(("EGFR", "L858R"), ("KRAS", "G12C"))),
        {candidate["candidate_id"]: candidate}, [_source_unit(quote)],
    )
    negated = _run_orchestrated(
        tmp_path, "orchestrated-negated-biomarker", "lung cancer; no EGFR L858R detected; current target erlotinib.",
        _parser_output("", negated=True), {candidate["candidate_id"]: candidate}, [_source_unit(quote)],
    )
    assert len(multi.relation_aware_report["paper_evidence"]) == 1
    claim = multi.relation_aware_report["paper_evidence"][0]["claim"]
    assert {tuple(sorted(pair.items())) for pair in claim.get("gene_variant_pairings", [])} == {
        (("alteration", "L858R"), ("gene", "EGFR")),
    }
    assert {item["alteration"] for item in claim["gene_variant_pairings"]} == {"L858R"}
    assert negated.relation_aware_report["paper_evidence"] == []


def test_orchestrator_cooccurrence_and_rejected_proposition_cannot_support(tmp_path: Path) -> None:
    candidate = _paper_candidate()
    cases = [
        ("cooccurrence", "EGFR L858R and erlotinib were studied."),
        ("rejected-proposition", "The proposition that EGFR L858R showed sensitivity to erlotinib was rejected."),
    ]
    for case_id, quote in cases:
        run = _run_orchestrated(
            tmp_path, f"orchestrated-{case_id}", "lung cancer with EGFR L858R; current target erlotinib.",
            _parser_output(""), {candidate["candidate_id"]: candidate},
            [_source_unit(quote, unit_id=f"SU-{case_id}")], reader_force_positive=True,
        )
        assert run.relation_aware_report is not None
        assert run.relation_aware_report["paper_evidence"][0]["claim"]["status"] != "FULL_SUPPORT"


def test_orchestrator_unavailable_document_and_reader_failure_are_accounted(tmp_path: Path) -> None:
    candidate = _paper_candidate()
    quote = "EGFR L858R was associated with sensitivity to erlotinib in lung cancer."
    unavailable = _run_orchestrated(
        tmp_path, "orchestrated-document-unavailable", "lung cancer with EGFR L858R; current target erlotinib.",
        _parser_output(""), {candidate["candidate_id"]: candidate}, [_source_unit(quote)], unavailable=True,
    )
    reader_failed = _run_orchestrated(
        tmp_path, "orchestrated-reader-failed", "lung cancer with EGFR L858R; current target erlotinib.",
        _parser_output(""), {candidate["candidate_id"]: candidate}, [_source_unit(quote)], reader_failure=True,
    )
    unavailable_claim = unavailable.relation_aware_report["paper_evidence"][0]["claim"]
    failure_entry = reader_failed.relation_aware_report["paper_evidence"][0]
    assert unavailable_claim["status"] == "UNVERIFIABLE"
    attempts = failure_entry["evidence_records"]
    assert attempts
    assert attempts[0]["reader_attempt_status"] in {"READER_PARSE_FAILED", "READER_TRANSPORT_FAILED"}
    assert reader_failed.relation_aware_report["pipeline_accounting"]["reader_attempts"]["total"] == 1
    assert failure_entry["claim"]["status"] == "UNVERIFIABLE"


def test_orchestrator_positive_and_contradiction_both_reach_dossier(tmp_path: Path) -> None:
    candidate = _paper_candidate(document_identifiers=[{"pmid": "12345678"}, {"pmid": "87654321"}])
    units = [
        _source_unit("EGFR L858R was associated with sensitivity to erlotinib in lung cancer.", unit_id="SU-positive"),
        _source_unit("EGFR L858R did not predict response to erlotinib in lung cancer.",
                     document_id="pmid:87654321", unit_id="SU-negative"),
    ]
    run = _run_orchestrated(
        tmp_path, "orchestrated-positive-contradiction", "lung cancer with EGFR L858R; current target erlotinib.",
        _parser_output(""), {candidate["candidate_id"]: candidate}, units,
    )
    assert run.relation_aware_report is not None
    claim = run.relation_aware_report["paper_evidence"][0]["claim"]
    assert claim["status"] == "PARTIAL_SUPPORT"
    assert claim["contradiction_present"] is True
    assert claim["supporting_evidence_ids"] and claim["contradicting_evidence_ids"]


def test_orchestrator_uses_current_target_not_previous_intervention(tmp_path: Path) -> None:
    previous_candidate = _paper_candidate(
        candidate_id="GCA4-E2E-PREVIOUS-DRUG",
        interventions=[{"label": "gefitinib", "type": "Drug"}],
    )
    raw = "lung cancer with EGFR L858R; previous gefitinib; current target erlotinib."
    run = _run_orchestrated(
        tmp_path, "orchestrated-previous-vs-target", raw,
        _parser_output("", interventions=(("gefitinib", "PREVIOUS"), ("erlotinib", "TARGET"))),
        {previous_candidate["candidate_id"]: previous_candidate},
        [_source_unit("EGFR L858R was associated with sensitivity to gefitinib in lung cancer.")],
    )
    assert run.relation_aware_report["paper_evidence"] == []


def test_orchestrator_trial_gene_mismatch_and_failed_resolution(tmp_path: Path) -> None:
    nct = "NCT12345678"
    raw = f"lung cancer EGFR L858R; target erlotinib; trial {nct}."
    parser = _parser_output("", trials=(nct,))
    mismatched = _trial_candidate(gene="KRAS", nct=nct)
    wrong_gene = _run_orchestrated(
        tmp_path, "orchestrated-wrong-trial-gene", raw, parser,
        {mismatched["candidate_id"]: mismatched}, [],
    )
    assert wrong_gene.relation_aware_report["clinical_trials"] == []

    compatible = _trial_candidate(gene="EGFR", nct=nct)
    failed = _run_orchestrated(
        tmp_path, "orchestrated-failed-trial-resolution", raw, parser,
        {compatible["candidate_id"]: compatible},
        [_source_unit("Erlotinib trial record: EGFR cohort.", document_id=f"nct:{nct}")],
        trial_failed=True,
    )
    assert failed.relation_aware_report is not None, (failed.stopped_at, [
        (stage.stage_id, stage.status, stage.reason_codes, stage.output_preview)
        for stage in failed.stages if stage.status in {"FAILED", "WARNING"}
    ])
    assert failed.relation_aware_report["clinical_trials"], failed.stages[4].output_preview
    trial = failed.relation_aware_report["clinical_trials"][0]
    assert trial["trial_resolution_status"] == "RESOLUTION_FAILED"
    assert trial["resolved_source_identity"] is None
    assert trial["evidence_interpretation"] == "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"
    assert trial["claim"]["supporting_evidence_ids"] == []


def test_orchestrator_real_companion_diagnostic_stays_kg_only(tmp_path: Path) -> None:
    source = load_candidates()
    candidate_id = "GCA4-039ca7831aca33a1e28296dc"
    candidate = source[candidate_id]
    device_name = "FoundationOne CDx  (Foundation Medicine, Inc.)"
    raw = f"lung cancer with EGFR; target erlotinib; {device_name}."
    parsed = _parser_output(
        "", disease="lung cancer", biomarkers=(("EGFR", None),),
        interventions=(("erlotinib", "TARGET"),),
        diagnostics=(device_name,),
    )
    run = _run_orchestrated(tmp_path, "orchestrated-companion-diagnostic", raw,
                            parsed, {candidate_id: candidate}, [])
    assert run.relation_aware_report is not None, (run.stopped_at, [
        (stage.stage_id, stage.status, stage.reason_codes, stage.output_preview)
        for stage in run.stages if stage.status in {"FAILED", "WARNING"}
    ])
    entries = run.relation_aware_report["kg_only_relations"]
    assert len(entries) == 1
    diagnostic = entries[0]
    assert diagnostic["verification_status"] == "KG_ONLY"
    assert diagnostic["document_id"] is None
    assert diagnostic["diagnostic_context"] == {
        "device_id": "cdx:FOUNDATIONONECD:EGFR:ERLOTINIB",
        "device_name": "FoundationOne CDx  (Foundation Medicine, Inc.)",
        "drug": "Erlotinib", "gene": "EGFR", "platform_type": "NGS",
        "specimen_types": "FFPE",
    }
    assert "patient_indication" not in diagnostic


def test_orchestrator_kg_only_relation_is_not_document_support(tmp_path: Path) -> None:
    candidate = _paper_candidate(document_identifiers=[])
    run = _run_orchestrated(
        tmp_path, "orchestrated-kg-only", "lung cancer with EGFR L858R; current target erlotinib.",
        _parser_output(""), {candidate["candidate_id"]: candidate}, [],
    )
    assert run.relation_aware_report is not None
    claim = run.relation_aware_report["kg_only_relations"][0]["claim"]
    assert claim["status"] == "KG_ONLY"
    assert claim["supporting_evidence_ids"] == []
    assert run.relation_aware_report["paper_evidence"] == []


def test_orchestrator_real_composite_join_still_requires_document_relation(tmp_path: Path) -> None:
    all_candidates = load_candidates()
    profile = next(item for item in all_candidates.values()
                   if item.get("semantic_key") == "EVIDENCE_STATEMENT|Evidence:1005")
    drug_edge = next(item for item in all_candidates.values()
                     if item.get("semantic_key", "").startswith("EVIDENCE_DRUG|Evidence:1005|"))
    derived, _ = derive_composite_relations({
        profile["candidate_id"]: profile, drug_edge["candidate_id"]: drug_edge,
    })
    composite = next(iter(derived.values()))
    drug = composite["interventions"][0]["label"]
    raw = f"Melanoma with BRAF V600E; target {drug}."
    quote = f"The proposition that BRAF V600E showed sensitivity to {drug} was rejected."
    run = _run_orchestrated(
        tmp_path, "orchestrated-real-composite", raw,
        _parser_output("", disease="Melanoma", biomarkers=(("BRAF", "V600E"),),
                       interventions=((drug, "TARGET"),)),
        {profile["candidate_id"]: profile, drug_edge["candidate_id"]: drug_edge},
        [_source_unit(quote, document_id="pmid:26678033", unit_id="SU-composite")],
        reader_force_positive=True,
    )
    assert run.relation_aware_report is not None
    claims = [entry["claim"] for entry in run.relation_aware_report["paper_evidence"]]
    composite_claims = [claim for claim in claims if claim.get("relation_origin") == "DERIVED_COMPOSITE"]
    assert len(composite_claims) == 1
    assert composite_claims[0]["status"] != "FULL_SUPPORT"
    assert composite_claims[0]["composite_lineage"]["shared_evidence_id"] == "evidence:1005"


def test_orchestrator_multisource_semantic_group_emits_one_lineaged_claim(tmp_path: Path) -> None:
    first = _paper_candidate("GCA4-E2E-GROUP-1", semantic_key="EVIDENCE_STATEMENT|Evidence:GROUP")
    second = _paper_candidate("GCA4-E2E-GROUP-2", semantic_key="EVIDENCE_STATEMENT|Evidence:GROUP",
                              source_record_ids=["source-row:2"], source_datasets=["clean_graph/evidence_statement_alt.csv"],
                              edge_ids=["edge:e2e:2"])
    raw = "lung cancer with EGFR L858R; current target erlotinib."
    run = _run_orchestrated(
        tmp_path, "orchestrated-multisource", raw, _parser_output(""),
        {first["candidate_id"]: first, second["candidate_id"]: second},
        [_source_unit("EGFR L858R was associated with sensitivity to erlotinib in lung cancer.")],
    )
    assert run.relation_aware_report is not None
    paper = run.relation_aware_report["paper_evidence"]
    assert len(paper) == 1
    claim = paper[0]["claim"]
    assert claim["candidate_group_candidate_ids"] == sorted([first["candidate_id"], second["candidate_id"]])
    assert {"source-row:1", "source-row:2"} <= set(claim["source_record_ids"])
    assert {"edge:e2e:1", "edge:e2e:2"} <= set(claim["edge_ids"])


def test_orchestrated_deterministic_claims_repeat_for_positive_conflict_and_group(tmp_path: Path) -> None:
    positive_candidate = _paper_candidate()
    conflict_candidate = _paper_candidate(
        "GCA4-E2E-DET-CONFLICT",
        document_identifiers=[{"pmid": "12345678"}, {"pmid": "87654321"}],
    )
    group_one = _paper_candidate("GCA4-E2E-DET-GROUP-1", semantic_key="EVIDENCE_STATEMENT|Evidence:DET-GROUP")
    group_two = _paper_candidate("GCA4-E2E-DET-GROUP-2", semantic_key="EVIDENCE_STATEMENT|Evidence:DET-GROUP",
                                 source_record_ids=["source-row:2"], edge_ids=["edge:e2e:2"])
    cases = [
        ("positive", {positive_candidate["candidate_id"]: positive_candidate}, [
            _source_unit("EGFR L858R was associated with sensitivity to erlotinib in lung cancer.")]),
        ("conflict", {conflict_candidate["candidate_id"]: conflict_candidate}, [
            _source_unit("EGFR L858R was associated with sensitivity to erlotinib in lung cancer.", unit_id="SU-p"),
            _source_unit("EGFR L858R did not predict response to erlotinib in lung cancer.",
                         document_id="pmid:87654321", unit_id="SU-n"),
        ]),
        ("group", {group_one["candidate_id"]: group_one, group_two["candidate_id"]: group_two}, [
            _source_unit("EGFR L858R was associated with sensitivity to erlotinib in lung cancer.")]),
    ]
    raw = "lung cancer with EGFR L858R; current target erlotinib."
    for name, candidates, units in cases:
        first = _run_orchestrated(tmp_path, f"deterministic-{name}-1", raw,
                                  _parser_output(""), candidates, units)
        second = _run_orchestrated(tmp_path, f"deterministic-{name}-2", raw,
                                   _parser_output(""), candidates, units)
        first_report = first.relation_aware_report
        second_report = second.relation_aware_report
        assert first_report is not None and second_report is not None
        assert json.dumps(first_report["claims"], sort_keys=True, separators=(",", ":")) == json.dumps(
            second_report["claims"], sort_keys=True, separators=(",", ":")
        )
        assert [claim["claim_id"] for claim in first_report["claims"]] == [
            claim["claim_id"] for claim in second_report["claims"]
        ]
