from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.mtb_evidence.escat_curation_mvp.prefill import create_draft
from benchmarks.mtb_evidence.ontology_shadow_mvp.evaluator import OntologyShadowEvaluator
from benchmarks.mtb_evidence.ontology_shadow_mvp.normalizer import EntityNormalizer
from benchmarks.mtb_evidence.ontology_shadow_mvp.registry import OntologyRegistry

from .contract import build_dossier


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CORPUS_ROOT = REPOSITORY_ROOT / "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4"
OUTPUT_PATH = Path(__file__).resolve().parent / "data" / "unified_dossier_preview.json"
PREVIEW_TIME = "2026-08-02T00:00:00+00:00"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_claims() -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(CORPUS_ROOT / "therapeutic_claims.jsonl") + _read_jsonl(CORPUS_ROOT / "diagnostic_claims.jsonl")
    return {str(row["claim_id"]): row for row in rows if not row.get("deprecated", False)}


def _load_parents() -> dict[str, dict[str, Any]]:
    return {str(row["parent_id"]): row for row in _read_jsonl(CORPUS_ROOT / "graph_evidence_parents.jsonl")}


def _provenance_for_claim(claim: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    locators = copy.deepcopy(claim.get("locators") or [])
    source_units = [{"source_unit_id": value, "scope": "claim"} for value in claim.get("source_unit_ids") or []]
    claim_sources = []
    for locator in locators:
        source_id = locator.get("source_id")
        if source_id and not any(entry["source_id"] == source_id for entry in claim_sources):
            claim_sources.append({"source_id": source_id, "scope": "claim", "locator": copy.deepcopy(locator)})
    parent_sources = [
        {"source_id": source_id, "scope": "parent", "parent_id": parent.get("parent_id")}
        for source_id in parent.get("source_ids") or []
    ]
    if claim_sources or source_units:
        status = "CLAIM_VERIFIED_LOCATOR"
        missing = None
    elif parent_sources:
        status = "PARENT_PUBLICATION_AVAILABLE"
        missing = "claim_level_source"
    else:
        status = "MISSING"
        missing = "parent_publication"
    return {
        "claim_level_sources": claim_sources,
        "parent_level_publications": parent_sources,
        "source_unit": source_units,
        "locators": locators,
        "provenance_status": status,
        "first_missing_link": missing,
        "ambiguities": copy.deepcopy(claim.get("warnings") or []),
    }


def _document_support_for_draft(draft: Any) -> dict[str, Any] | None:
    record = draft.assessment
    passage = (record.supporting_passages or [None])[0]
    source = (record.supporting_sources or [None])[0]
    if passage is None:
        return None
    support_level = passage.get("support_status") or (source or {}).get("claim_specific_support") or "AMBIGUOUS"
    return {
        "status": "PARTIALLY_AVAILABLE",
        "document_identifier": (source or {}).get("source_id"),
        "identifier_scope": "PMID" if (source or {}).get("source_id", "").startswith("PMID:") else "LOCAL_SOURCE",
        "text_availability": "ABSTRACT_CACHE",
        "supporting_passage": passage.get("text"),
        "locator": passage.get("locator"),
        "support_level": support_level,
        "supported_fields": ["claim_statement"],
        "unsupported_fields": ["ESCAT tier", "ESCAT subtier", "clinical actionability"],
        "method": "local PMID pilot alignment",
        "limitations": ["pilot passage is not a clinical validation"],
    }


def _ontology_for_claim(claim: dict[str, Any], context: dict[str, str]) -> dict[str, Any]:
    registry = OntologyRegistry.from_local_assets(REPOSITORY_ROOT)
    evaluator = OntologyShadowEvaluator(registry, EntityNormalizer(registry))
    matches = evaluator.evaluate_claim(
        claim,
        {
            "disease_context": context.get("disease"),
            "biomarker_context": context.get("biomarker"),
            "original_intervention_associations": [context.get("intervention")],
        },
    )
    result = {entity_type: match.to_dict() for entity_type, match in zip((chr(34) + chr(100) + chr(105) + chr(115) + chr(101) + chr(97) + chr(115) + chr(101), chr(34) + chr(98) + chr(105) + chr(111) + chr(109) + chr(97) + chr(114) + chr(107) + chr(101) + chr(114), chr(34) + chr(105) + chr(110) + chr(116) + chr(101) + chr(114) + chr(118) + chr(101) + chr(110) + chr(116) + chr(105) + chr(111) + chr(110)), matches)}
    result["diagnostic_entity"] = {
        "query_value": None,
        "claim_value": None,
        "match_type": "UNKNOWN",
        "distance": None,
        "path": [],
        "confidence": "low",
        "explanation": "No CompanionDiagnostic entity was loaded for this preview case.",
    }
    return result


def _diagnostic_context() -> dict[str, Any]:
    return {
        "records": [],
        "status": "STRUCTURAL_DATA_ONLY",
        "limitations": [
            "disease context missing for CompanionDiagnostic records",
            "provenance missing for CompanionDiagnostic records",
            "regulatory status unavailable",
            "therapy association does not imply therapy requirement",
            "no CompanionDiagnostic graph records were loaded in this preview",
        ],
    }


def _core_snapshot(case_id: str, claim: dict[str, Any] | None, *, abstention: bool) -> dict[str, Any]:
    claim_id = claim.get("claim_id") if claim else None
    return {
        "bucket_summary": {"primary": 1 if claim else 0, "abstained": 1 if abstention else 0},
        "bucket": "primary" if claim else "abstain",
        "abstention": abstention,
        "claims": [{"claim_id": claim_id, "rank": 1}] if claim_id else [],
        "score": {"total": 0, "source": "OFFLINE_CORE_SNAPSHOT"},
        "gate_trace": [],
        "reason_codes": ["OFFLINE_CORE_SNAPSHOT"],
        "evidence": ([{"graph_evidence_id": claim.get("graph_evidence_id"), "rank": 1}] if claim else []),
        "technical_records": [{"record_id": f"CORE-{case_id}", "source": "OFFLINE_CORE_SNAPSHOT"}],
    }


def _case(
    case_id: str,
    claim: dict[str, Any] | None,
    *,
    disease: str,
    biomarker: str,
    intervention: str,
    escat_assessment: Any = None,
) -> dict[str, Any]:
    core = _core_snapshot(case_id, claim, abstention=claim is None)
    if claim is None:
        return build_dossier(
            core,
            run={"run_id": f"SHADOW-{case_id}", "source": "offline_contract_preview"},
            case_context={
                "case_id": case_id,
                "disease": disease,
                "biomarker": biomarker,
                "intervention": intervention,
                "escat_status": "NOT_ASSESSED",
                "claim_id_available": False,
            },
            diagnostic_context=_diagnostic_context(),
            limitations=["No qualified claim_id is available; no claim extension can be associated."],
            generated_at=PREVIEW_TIME,
        )
    parent = _load_parents().get(claim.get("parent_id"), {})
    draft = create_draft(
        str(claim["claim_id"]),
        root=REPOSITORY_ROOT,
        assessment_id=f"PREVIEW-ESCAT-{case_id}",
        created_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )
    document_support = _document_support_for_draft(draft)
    return build_dossier(
        core,
        run={"run_id": f"SHADOW-{case_id}", "source": "offline_contract_preview"},
        case_context={
            "case_id": case_id,
            "disease": disease,
            "biomarker": biomarker,
            "intervention": intervention,
            "claim_id_available": True,
        },
        provenance_by_claim={str(claim["claim_id"]): _provenance_for_claim(claim, parent)},
        document_support_by_claim={str(claim["claim_id"]): document_support},
        ontology_by_claim={str(claim["claim_id"]): _ontology_for_claim(claim, {"disease": disease, "biomarker": biomarker, "intervention": intervention})},
        escat_assessments=[escat_assessment] if escat_assessment is not None else [],
        diagnostic_context=_diagnostic_context(),
        limitations=["Four-case exploratory preview; not a new V3 runtime execution."],
        generated_at=PREVIEW_TIME,
    )


def build_preview() -> dict[str, Any]:
    claims = _load_claims()
    fgfr2_id = "CLM-1d3ba8b6ae49232969c7"
    alk_id = "CLM-0f234bc9c53847910521"
    egfr_id = "CLM-1ee5f9a16a678cebf993"
    fgfr2_draft = create_draft(fgfr2_id, root=REPOSITORY_ROOT, assessment_id="PREVIEW-ESCAT-FGFR2_iCCA_derazantinib", created_at=datetime(2026, 8, 2, tzinfo=timezone.utc)).assessment
    cases = {
        "FGFR2_iCCA_derazantinib": _case("FGFR2_iCCA_derazantinib", claims[fgfr2_id], disease="Intrahepatic Cholangiocarcinoma", biomarker=claims[fgfr2_id]["biomarker"], intervention="derazantinib", escat_assessment=fgfr2_draft),
        "ALK_G1202R_NSCLC_alectinib": _case("ALK_G1202R_NSCLC_alectinib", claims[alk_id], disease="NSCLC", biomarker="ALK G1202R", intervention="alectinib"),
        "EGFR_L858R_NSCLC_osimertinib": _case("EGFR_L858R_NSCLC_osimertinib", claims[egfr_id], disease="NSCLC", biomarker="EGFR L858R", intervention="osimertinib"),
        "RMI2_NSCLC": _case("RMI2_NSCLC", None, disease="NSCLC", biomarker="RMI2", intervention="unknown"),
    }
    return {
        "preview_mode": "OFFLINE_READ_ONLY",
        "ruleset_status": "RESEARCH_DRAFT",
        "ruleset_available": False,
        "automatic_escat_tiers_assigned": False,
        "difference_between_populations": {
            "pilot_drafts": "15 persisted ESCAT curation drafts from the approved pilot; not rewritten here.",
            "exploratory_cases": "4 canonical dossier previews; only FGFR2 uses an in-memory draft-shaped assessment for presentation.",
        },
        "cases": cases,
    }


def write_preview(path: Path | None = None) -> Path:
    output = path or OUTPUT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_preview(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(write_preview())
