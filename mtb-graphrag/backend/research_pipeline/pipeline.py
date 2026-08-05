"""Orchestrates one case end-to-end: free text -> parser -> match verify ->
retrieval -> paper selection -> Gemma enrichment -> validation -> deterministic
pipeline -> dossier preview. Tracks a shared call budget across the whole
pilot run; never calls the enricher when gated out upstream.
"""
from __future__ import annotations

from typing import Any, Callable

from .casecontext import match_verifier as verifier
from .determinism import gates as detpipe
from .dossier import builder as dossier_mod
from .enrichment import validator as enrichment_validator
from .retrieval import kg_retrieval as retrieval_mod
from .retrieval.paper_selection import select_papers_for_association

MAX_REAL_CALLS_TOTAL = 20


class CallBudget:
    def __init__(self, maximum: int = MAX_REAL_CALLS_TOTAL):
        self.maximum = maximum
        self.used = 0
        self.calls: list[dict[str, Any]] = []

    def spend(self, kind: str, case_id: str) -> None:
        if self.used >= self.maximum:
            raise RuntimeError(f"CALL_BUDGET_EXCEEDED: attempted {kind} for {case_id} at used={self.used}/{self.maximum}")
        self.used += 1
        self.calls.append({"kind": kind, "case_id": case_id, "sequence": self.used})


def run_case(case_id: str, clinical_text: str, budget: CallBudget, call_parser_fn: Callable, call_enricher_fn: Callable, source_units_by_id: dict[str, dict]) -> dict[str, Any]:
    """`call_parser_fn(budget, case_id, text)` and `call_enricher_fn(budget, ...)` are
    responsible for spending the budget themselves -- only when they actually make a new
    real network call (a replay of an already-captured call must not double-spend it)."""
    trace: dict[str, Any] = {"case_id": case_id, "stage_1_free_text": clinical_text}

    parser_result = call_parser_fn(budget, case_id, clinical_text)
    trace["stage_2_casecontext_parser"] = parser_result
    if parser_result["transport_result"] != "FORCED_TOOL_VALID":
        trace["stopped_at"] = "PARSER_TRANSPORT_FAILED"
        return trace

    case_context = parser_result["case_context_raw"]
    verification_records = verifier.verify_case_context(case_context, clinical_text)
    essential_ok, warnings = verifier.essential_fields_pass(verification_records)
    trace["stage_3_casecontext_match"] = {"records": [r.to_dict() for r in verification_records], "essential_fields_pass": essential_ok, "warnings": warnings}
    if not essential_ok:
        trace["stopped_at"] = "CASECONTEXT_MISMATCH"
        return trace

    retrieval_result = retrieval_mod.retrieve(case_context)
    trace["stage_4_retrieval"] = retrieval_result
    if retrieval_result["no_match"]:
        trace["stopped_at"] = "RETRIEVAL_NO_MATCH"
        return trace

    candidate_therapies = []
    stage5, stage6, stage7, stage8 = [], [], [], []
    for association in retrieval_result["associations"]:
        selection = select_papers_for_association(association, source_units_by_id)
        stage5.append(selection)
        candidate = association["candidate"]

        enrichment_entries, validation_entries, validated_for_pipeline = [], [], []
        for paper in selection["selected_papers"]:
            interventions = [i.get("label") for i in candidate.get("interventions") or [] if i.get("label")]
            requested_drug = (case_context.get("target_intervention") or {}).get("normalized_value") or (interventions[0] if interventions else "")
            paper_source_units = [source_units_by_id[uid] for uid in paper["resolved_source_unit_ids"] if uid in source_units_by_id]

            enrichment_call = call_enricher_fn(budget, case_id, candidate["candidate_id"], paper["bundle_id"], case_context, {"candidate_id": candidate["candidate_id"], "disease": candidate.get("disease"), "biomarkers": candidate.get("biomarkers")}, requested_drug, paper_source_units)
            stage6.append(enrichment_call)

            validation = enrichment_validator.validate_enrichment(
                enrichment_call["transport_result"], enrichment_call["enrichment"],
                candidate=candidate, paper_bundle=paper, source_units_by_id=source_units_by_id, requested_drug=requested_drug,
            )
            stage7.append(validation)
            validation_entries.append({"paper_id": paper["bundle_id"], **validation})
            if enrichment_call["enrichment"] is not None:
                enrichment_entries.append(enrichment_call["enrichment"])
            if validation["outcome"] in ("ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING"):
                validated_for_pipeline.append({"validation_outcome": validation["outcome"], "enrichment": enrichment_call["enrichment"]})

        evaluation = detpipe.evaluate_association(case_context.get("query_intent"), candidate, validated_for_pipeline)
        stage8.append({"candidate_id": candidate["candidate_id"], **evaluation})
        candidate_therapies.append(dossier_mod.build_candidate_therapy_entry(
            candidate, graph_relation=candidate.get("predicate", ""),
            document_support={"selected_papers": [p["bundle_id"] for p in selection["selected_papers"]], "excluded_papers": selection["excluded_papers"]},
            enrichments=enrichment_entries, validation_results=validation_entries, evaluation=evaluation,
        ))

    trace["stage_5_paper_selection"] = stage5
    trace["stage_6_gemma_enrichment"] = stage6
    trace["stage_7_validation"] = stage7
    trace["stage_8_deterministic_pipeline"] = stage8

    preview = dossier_mod.build_dossier_preview(
        case_id, case_context, trace["stage_3_casecontext_match"], candidate_therapies,
        limitations=["research_only_pilot", "no_new_document_fetched", "gemma_used_only_as_enricher"],
    )
    trace["stage_9_dossier"] = preview
    trace["stopped_at"] = None
    return trace
