from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .adapter import _active_claim_ids, build_shadow_dossier, load_pilot_preview, present_assessment
from .fixtures import (
    fixture_conflicting_records,
    fixture_curated_record,
    fixture_not_applicable_record,
    fixture_ruleset,
    fixture_superseded_record,
)


OUTPUT_PATH = Path(__file__).resolve().parent / "data" / "preview_cases.json"
DOSSIER_OUTPUT_PATH = Path(__file__).resolve().parent / "data" / "shadow_dossiers.json"


def generate_preview() -> dict[str, Any]:
    pilot = load_pilot_preview()
    known_claim_ids = _active_claim_ids()
    pilot_assessments = []
    pilot_path = Path(__file__).resolve().parents[1] / "escat_curation_mvp" / "data" / "pilot_drafts.jsonl"
    for line in pilot_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            pilot_assessments.append(json.loads(line)["assessment"])

    fixture_rule_set = fixture_ruleset()
    cases = {
        "FGFR2_iCCA": {
            "claim_id": "CLM-091cf6602db85e2a2d41",
            "description": "Pilot therapeutic claim with an existing incomplete draft.",
            "clinical_actionability": present_assessment(
                "CLM-091cf6602db85e2a2d41", pilot_assessments, ruleset_status="RESEARCH_DRAFT"
            ),
        },
        "ALK_G1202R_NSCLC": {
            "claim_id": "CLM-01aba27a2fb14d531e2d",
            "description": "Qualified claim with no associated ESCAT assessment.",
            "clinical_actionability": present_assessment(
                "CLM-01aba27a2fb14d531e2d", [], known_claim_ids=known_claim_ids
            ),
        },
        "EGFR_L858R_NSCLC_osimertinib": {
            "claim_id": "CLM-d4bee44e07efb6ccca9f",
            "description": "Qualified claim with no associated ESCAT assessment.",
            "clinical_actionability": present_assessment(
                "CLM-d4bee44e07efb6ccca9f", [], known_claim_ids=known_claim_ids
            ),
        },
        "RMI2": {
            "claim_id": "PILOT-N1-RMI2-SNAPSHOT",
            "description": "Exploratory case without a qualified claim identifier.",
            "clinical_actionability": present_assessment(
                "PILOT-N1-RMI2-SNAPSHOT", [], known_claim_ids=known_claim_ids
            ),
        },
        "diagnostic_explicit_not_applicable": {
            "claim_id": "CLM-8941c177da91f66ff93a",
            "description": "Diagnostic claim is NOT_APPLICABLE only because an explicit assessment exists.",
            "clinical_actionability": present_assessment(
                "CLM-8941c177da91f66ff93a",
                [fixture_not_applicable_record()],
                known_claim_ids=known_claim_ids,
            ),
        },
        "superseded_fixture": {
            "claim_id": "CASE-FIXTURE-SUPERSEDED",
            "description": "Historical superseded assessment is not shown as current.",
            "historical_assessments": [fixture_superseded_record().to_dict()],
            "clinical_actionability": present_assessment(
                "CASE-FIXTURE-SUPERSEDED",
                [fixture_superseded_record()],
                known_claim_ids={"CASE-FIXTURE-SUPERSEDED"},
            ),
        },
        "conflicting_fixture": {
            "claim_id": "CASE-FIXTURE-CONFLICT",
            "description": "Two active technical fixture assessments produce a conflict.",
            "clinical_actionability": present_assessment(
                "CASE-FIXTURE-CONFLICT",
                fixture_conflicting_records(),
                known_claim_ids={"CASE-FIXTURE-CONFLICT"},
            ),
        },
        "curated_fixture": {
            "claim_id": "CASE-FIXTURE-CURATED",
            "description": "Technical positive validation only; not a clinical ESCAT assessment.",
            "clinical_actionability": present_assessment(
                "CASE-FIXTURE-CURATED",
                [fixture_curated_record()],
                ruleset=fixture_rule_set,
                ruleset_status="TEST_FIXTURE_ONLY",
                known_claim_ids={"CASE-FIXTURE-CURATED"},
            ),
        },
    }
    return {
        "preview_mode": "OFFLINE_READ_ONLY",
        "ruleset_status": "RESEARCH_DRAFT",
        "automatic_assignment": False,
        "pilot": pilot,
        "cases": cases,
        "fixture_disclaimer": ["TEST_FIXTURE_ONLY", "NOT_A_CLINICAL_ESCAT_ASSESSMENT"],
    }



def generate_shadow_dossiers() -> dict[str, Any]:
    """Build four illustrative dossier payloads without changing source records."""
    pilot_path = Path(__file__).resolve().parents[1] / "escat_curation_mvp" / "data" / "pilot_drafts.jsonl"
    pilot_rows = [
        json.loads(line)
        for line in pilot_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    pilot_assessments = [row["assessment"] for row in pilot_rows]
    known_claim_ids = _active_claim_ids()
    cases = {
        "FGFR2_iCCA": {
            "claim_id": "CLM-091cf6602db85e2a2d41",
            "claim_relevance": {
                "claim_id": "CLM-091cf6602db85e2a2d41",
                "domain": "therapeutic",
                "biomarker": "FGFR2::TACC3 Fusion",
                "disease": "Cholangiocarcinoma",
                "intervention": "ponatinib",
            },
            "claim_sources": [],
            "rule_sources": [],
            "document_support": {},
            "assessments": pilot_assessments,
        },
        "ALK_G1202R_NSCLC": {
            "claim_id": "CLM-01aba27a2fb14d531e2d",
            "claim_relevance": {
                "claim_id": "CLM-01aba27a2fb14d531e2d",
                "domain": "therapeutic",
                "biomarker": "ALK G1202R AND v::ALK Fusion",
                "disease": "Lung Non-small Cell Carcinoma",
                "intervention": "neladalkib",
            },
            "claim_sources": [],
            "rule_sources": [],
            "document_support": {},
            "assessments": [],
        },
        "EGFR_L858R_NSCLC_osimertinib": {
            "claim_id": "CLM-d4bee44e07efb6ccca9f",
            "claim_relevance": {
                "claim_id": "CLM-d4bee44e07efb6ccca9f",
                "domain": "therapeutic",
                "biomarker": "EGFR L858R OR EGFR Exon 19 Deletion",
                "disease": "Lung Non-small Cell Carcinoma",
                "intervention": "osimertinib",
            },
            "claim_sources": [],
            "rule_sources": [],
            "document_support": {},
            "assessments": [],
        },
        "RMI2": {
            "claim_id": "PILOT-N1-RMI2-SNAPSHOT",
            "claim_relevance": {
                "claim_id": "PILOT-N1-RMI2-SNAPSHOT",
                "domain": "exploratory",
                "biomarker": "RMI2",
            },
            "claim_sources": [],
            "rule_sources": [],
            "document_support": {},
            "assessments": [],
        },
    }
    dossiers: dict[str, Any] = {}
    for name, case in cases.items():
        dossiers[name] = build_shadow_dossier(
            case["claim_id"],
            claim_relevance=case["claim_relevance"],
            claim_sources=case["claim_sources"],
            rule_sources=case["rule_sources"],
            document_support=case["document_support"],
            assessments=case["assessments"],
            known_claim_ids=known_claim_ids,
            ruleset_status="RESEARCH_DRAFT",
        )
        dossiers[name]["preview_case"] = True
        dossiers[name]["source_records_modified"] = False
        dossiers[name]["automatic_assignment"] = False
    return {
        "preview_mode": "OFFLINE_READ_ONLY",
        "ruleset_status": "RESEARCH_DRAFT",
        "ruleset_available": False,
        "automatic_assignment": False,
        "cases": dossiers,
    }


def write_dossiers(path: Path | None = None) -> Path:
    output = path or DOSSIER_OUTPUT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(generate_shadow_dossiers(), ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    return output


def write_preview(path: Path | None = None) -> Path:
    output = path or OUTPUT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(generate_preview(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(write_preview())
    print(write_dossiers())
