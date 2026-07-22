"""Classifica la struttura delle fonti residue e propone gli split.

L'audit propone **struttura**, non contenuto. Quando i segnali mostrano che una
fonte contiene una componente clinica e una preclinica, la proposta dice che
esistono due unita' e quali statement candidano a ciascuna; non riempie setting,
linea di terapia o popolazione. Quei campi richiedono la lettura di una persona,
e riempirli qui produrrebbe esattamente i valori plausibili e non verificati che
il corpus esiste per non contenere.

Nessuna proposta e' propagabile. Nessuna e' una revisione.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_manifest import content_hash  # noqa: E402
from backend.pipeline.evidence.profile_unit import (  # noqa: E402
    AWAITING_FIRST_REVIEW,
    COHORT_CANDIDATE,
    MACHINE_EXTRACTED,
    NOT_APPLICABLE,
    SOURCE_CHECKED,
    UNIT_DIMENSIONS,
    UNIT_TYPE_CLINICAL_COHORT,
    UNIT_TYPE_PRECLINICAL,
    UNIT_TYPE_UNSPECIFIED,
    UNKNOWN,
    FieldProvenance,
    SourceClinicalProfileUnit,
)
from benchmarks.mtb_evidence.evaluation.cohort_split_audit import (  # noqa: E402
    AUDIT_VERSION,
    CANDIDATE_STATES,
    CLINICAL_PRECLINICAL_SPLIT,
    CLINICAL_WITH_PRECLINICAL_VALIDATION,
    CONTEXT_ONLY,
    DETECTOR_VERSION,
    DIRECT_CLINICAL_SUPPORT,
    DIRECT_PRECLINICAL_SUPPORT,
    NOT_DETERMINABLE,
    SPLIT_PROPOSED_BY_AUDIT,
    UNSUPPORTED_BY_ACCESSIBLE_SOURCE,
    assess_split,
    classify_structure,
    structure_flags,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/v3/cohort_split_audit")
DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")
DEFAULT_QUALIFICATION = Path("benchmarks/mtb_evidence/v3/qualification")

EXCERPT_RADIUS = 100
MAX_EXCERPTS = 14


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--qualification-dir", type=Path, default=DEFAULT_QUALIFICATION)
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="recupera il full text da PMC; senza, si usa il solo abstract in cache",
    )
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _fetch_full_text(pmid: str) -> tuple[str, str, str]:
    """`(pmc_id, testo, hash)`; testo vuoto se non accessibile.

    Il testo non viene mai scritto su disco: serve a far girare il rilevatore e
    a estrarre estratti brevi attorno ai segnali trovati.
    """
    from benchmarks.mtb_evidence.evaluation.scripts.verify_source_locators import (
        fetch_pmc_document,
        pmc_id_for,
    )

    pmc_id = pmc_id_for(pmid)
    if not pmc_id:
        return "", "", ""
    text, digest, _ = fetch_pmc_document(pmc_id)
    return f"PMC{pmc_id}", text, digest


def _excerpt(text: str, start: int, end: int) -> str:
    left = max(0, start - EXCERPT_RADIUS)
    right = min(len(text), end + EXCERPT_RADIUS)
    return ("…" if left else "") + text[left:right].strip() + ("…" if right < len(text) else "")


def _proposed_units(
    unit: Mapping[str, Any],
    state: str,
    assessment: Any,
    created_at: str,
    document_hash: str,
    locator: str,
) -> list[dict[str, Any]]:
    """Proposte di unita' derivate, quando lo stato le sostiene.

    Solo lo split clinico/preclinico produce proposte concrete: e' l'unico caso
    in cui i segnali delimitano due insiemi disgiunti senza doverli inventare.
    Per bracci, coorti e sottogruppi i segnali dicono **che** esistono, non
    quali siano, e proporre unita' numerate creerebbe partizioni che la fonte
    non afferma.
    """
    if state != CLINICAL_PRECLINICAL_SPLIT:
        return []

    parent = str(unit["profile_unit_id"])
    source_id = str(unit["canonical_source_id"])
    base = parent.removesuffix("-cohort-1")

    def make(kind: str, unit_type: str, label: str, design: str) -> dict[str, Any]:
        decisions = {dimension: "unknown" for dimension in UNIT_DIMENSIONS}
        values: dict[str, Any] = {}
        for dimension in UNIT_DIMENSIONS:
            if dimension in ("biomarker_requirements", "intervention", "prior_therapies"):
                values[dimension] = ()
            else:
                values[dimension] = UNKNOWN
        if unit_type == UNIT_TYPE_PRECLINICAL:
            for dimension in ("therapy_line", "prior_therapies", "resection_status", "stage"):
                decisions[dimension] = "not_applicable"
                if dimension != "prior_therapies":
                    values[dimension] = NOT_APPLICABLE
        values["evidence_design"] = design
        decisions["evidence_design"] = "proposed_by_structural_audit"

        proposed = SourceClinicalProfileUnit(
            profile_unit_id=f"{base}-{kind}",
            canonical_source_id=source_id,
            pmids=tuple(unit.get("pmids") or ()),
            title=str(unit.get("title") or ""),
            cohort_id=kind,
            cohort_label=label,
            cohort_state=COHORT_CANDIDATE,
            cohort_note=(
                "proposta strutturale dell'audit: la fonte contiene evidenza clinica e "
                "preclinica. I campi clinici restano unknown perche' l'audit propone "
                "struttura, non contenuto."
            ),
            unit_type=unit_type,
            supersedes="",
            field_decisions=decisions,
            source_spans=(locator,) if locator else (),
            extraction_status=SOURCE_CHECKED if document_hash else MACHINE_EXTRACTED,
            review_status=AWAITING_FIRST_REVIEW,
            requires_human_review=True,
            human_review_reasons=(
                "proposta di split prodotta da audit strutturale automatico",
                "nessuna revisione umana: i campi clinici vanno compilati leggendo la fonte",
            ),
            provenance=(
                FieldProvenance(
                    field_name="evidence_design",
                    value_origin="primary_source_text",
                    source_locator=locator,
                    access_date=created_at[:10],
                    asserted_by=f"structural_audit ({DETECTOR_VERSION})",
                    span_hash=document_hash,
                    note=(
                        "segnali source-level: "
                        + ", ".join(sorted({s.signal_id for s in assessment.signals})[:6])
                    ),
                ),
            ),
            created_at=created_at,
            **values,
        )
        payload = proposed.as_dict()
        payload.update(
            {
                "proposed_profile_unit_id": payload["profile_unit_id"],
                "parent_profile_unit_id": parent,
                "unit_label": label,
                "audit_state": SPLIT_PROPOSED_BY_AUDIT,
                "human_reviewed": False,
                "source_checked": bool(document_hash),
                "is_propagatable": False,
                "is_evaluable": False,
                "confidence_category": "structural_signal_only",
                "audit_rationale": assessment.rationale,
                "audit_version": AUDIT_VERSION,
            }
        )
        return payload

    return [
        make(
            "clinical-component",
            UNIT_TYPE_CLINICAL_COHORT,
            "componente clinica proposta dall'audit",
            UNKNOWN,
        ),
        make(
            "preclinical-component",
            UNIT_TYPE_PRECLINICAL,
            "componente preclinica proposta dall'audit",
            "preclinical_in_vitro",
        ),
    ]


def _map_statement(
    statement: Mapping[str, Any],
    unit: Mapping[str, Any],
    proposals: Sequence[Mapping[str, Any]],
    text: str,
    assessment: Any,
    state: str,
) -> dict[str, Any]:
    intervention = str((statement.get("intervention") or {}).get("label") or "")
    haystack = text.casefold()
    present = bool(intervention) and intervention.casefold() in haystack

    proposed_ids = [str(item["proposed_profile_unit_id"]) for item in proposals]

    if not text:
        support, status, directness = (
            UNSUPPORTED_BY_ACCESSIBLE_SOURCE,
            "candidate_not_determinable",
            "not_determinable",
        )
    elif not present:
        # Non `candidate_invalid`: il testo consultato puo' essere il solo
        # abstract, e l'assenza li' non e' assenza nella fonte.
        support, status, directness = (
            NOT_DETERMINABLE,
            "candidate_not_determinable",
            "not_determinable",
        )
    elif assessment.has_clinical and assessment.has_preclinical:
        support, status, directness = (
            CLINICAL_WITH_PRECLINICAL_VALIDATION,
            "candidate_ambiguous",
            "direct_but_unassigned",
        )
    elif assessment.has_preclinical:
        support, status, directness = (
            DIRECT_PRECLINICAL_SUPPORT,
            "candidate_partial",
            "direct",
        )
    elif assessment.has_clinical:
        support, status, directness = (
            DIRECT_CLINICAL_SUPPORT,
            "candidate_valid",
            "direct",
        )
    else:
        support, status, directness = CONTEXT_ONLY, "candidate_not_determinable", "unclear"

    return {
        "statement_id": str(statement.get("evidence_statement_id") or ""),
        "parent_profile_unit_id": str(unit["profile_unit_id"]),
        "proposed_profile_unit_ids": proposed_ids,
        "support_type": support,
        "candidate_link_status": status,
        "directness": directness,
        "clinical_or_preclinical": (
            "both"
            if assessment.has_clinical and assessment.has_preclinical
            else "preclinical"
            if assessment.has_preclinical
            else "clinical"
            if assessment.has_clinical
            else "undetermined"
        ),
        "intervention": intervention,
        "normalization_required": bool(intervention) and not present,
        "conflict_dimensions": [],
        "not_separable_dimensions": (
            ["population", "setting", "therapy_line"]
            if status == "candidate_ambiguous"
            else []
        ),
        "non_propagation_rules": (
            [
                "clinical_population_to_cell_model",
                "preclinical_setting_to_patients",
                "in_vitro_sensitivity_to_clinical_benefit",
            ]
            if assessment.has_preclinical
            else []
        ),
        "rationale": (
            "l'intervento compare nel testo consultato ma la fonte contiene evidenza di "
            "natura diversa: l'assegnazione alla componente clinica o preclinica richiede "
            "lettura umana"
            if status == "candidate_ambiguous"
            else assessment.rationale
        ),
        "source_locators": [
            item.as_dict()["locator"] for item in assessment.signals[:4]
        ],
        "structure_state": state,
        "is_gold": False,
        "is_evaluable": False,
        "audit_version": AUDIT_VERSION,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    audit = args.audit_dir
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    scope = list(read_jsonl(audit / "audit_scope.jsonl"))
    abstracts = {
        str(row["identifier_key"]): row
        for row in read_jsonl(args.curation_dir / "source_abstract_cache.jsonl")
    }
    statements = {
        str(row["evidence_statement_id"]): row
        for row in read_jsonl(args.qualification_dir / "evidence_statements.jsonl")
    }

    access_rows: list[dict[str, Any]] = []
    classifications: list[dict[str, Any]] = []
    proposals_out: list[dict[str, Any]] = []
    proposed_units: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    signal_rows: list[dict[str, Any]] = []

    for unit in scope:
        pmid = (unit.get("pmids") or [""])[0]
        abstract = abstracts.get(f"pmid:{pmid}")

        pmc_id, full_text, document_hash = ("", "", "")
        if args.allow_network:
            pmc_id, full_text, document_hash = _fetch_full_text(pmid)

        if full_text:
            record: dict[str, Any] = {
                "abstract_available": True,
                "abstract_sections": [{"label": "FULL_TEXT", "text": full_text}],
            }
            consulted, locator = "pmc_efetch", f"{pmc_id}#full_text"
            match_type = "exact"
        elif abstract and abstract.get("abstract_available"):
            record = dict(abstract)
            consulted, locator = "pubmed_efetch", f"pmid:{pmid}#abstract"
            document_hash = str(abstract.get("abstract_sha256") or "")
            match_type = "normalized_label"
        else:
            record = {}
            consulted, locator, match_type = "none", "", "not_verified"

        assessment = assess_split(record or None)
        flags = structure_flags(assessment, unit)
        state, reason = classify_structure(
            assessment,
            {**unit, "abstract_available": bool(record)},
            flags,
            full_text_consulted=bool(full_text),
        )

        text = full_text or str(record.get("abstract_text") or "") or " ".join(
            str(item.get("text") or "") for item in record.get("abstract_sections") or []
        )

        access_rows.append(
            {
                "profile_unit_id": unit["profile_unit_id"],
                "source_identifier": unit["canonical_source_id"],
                "pmid": pmid,
                "pmc_id": pmc_id,
                "system_consulted": consulted,
                "access_date": created_at[:10],
                "availability": (
                    "full_text" if full_text else "abstract_only" if record else "unavailable"
                ),
                "sections_located": sorted(
                    {str(item.get("label")) for item in record.get("abstract_sections") or []}
                ),
                "exact_locator": locator,
                "locator_match_type": match_type,
                "document_hash": document_hash,
                "source_hash": unit.get("abstract_sha256", ""),
                "limitations": (
                    ""
                    if full_text
                    else "solo abstract: i segnali del full text non sono osservabili"
                    if record
                    else "nessun testo accessibile"
                ),
                "full_text_stored": False,
                "audit_version": AUDIT_VERSION,
            }
        )

        signal_rows.append(
            {
                "profile_unit_id": unit["profile_unit_id"],
                "source_identifier": unit["canonical_source_id"],
                "text_source": "full_text" if full_text else "abstract" if record else "none",
                **assessment.as_dict(),
                "excerpts": [
                    {
                        "signal_id": signal.signal_id,
                        "matched_text": signal.matched_text,
                        "excerpt": _excerpt(text, signal.start, signal.end),
                    }
                    for signal in assessment.signals[:MAX_EXCERPTS]
                ]
                if text
                else [],
            }
        )

        proposals = _proposed_units(unit, state, assessment, created_at, document_hash, locator)
        proposed_units.extend(proposals)
        if proposals:
            proposals_out.append(
                {
                    "parent_profile_unit_id": unit["profile_unit_id"],
                    "canonical_source_id": unit["canonical_source_id"],
                    "structure_state": state,
                    "proposed_profile_unit_ids": [
                        item["proposed_profile_unit_id"] for item in proposals
                    ],
                    "proposal_count": len(proposals),
                    "audit_state": SPLIT_PROPOSED_BY_AUDIT,
                    "is_propagatable": False,
                    "human_reviewed": False,
                    "rationale": reason,
                    "signals": sorted({s.signal_id for s in assessment.signals}),
                    "audit_version": AUDIT_VERSION,
                }
            )

        classifications.append(
            {
                "profile_unit_id": unit["profile_unit_id"],
                "canonical_source_id": unit["canonical_source_id"],
                "structure_state": state,
                "structure_rationale": reason,
                "split_likelihood": assessment.likelihood,
                "text_source": "full_text" if full_text else "abstract" if record else "none",
                **flags,
                "documentary_units": 1 + len(proposals),
                "clinical_cohorts_detected": 1 if flags["contains_clinical_evidence"] else 0,
                "arms_detected": sum(
                    1 for s in assessment.signals if s.category == "arm_structure"
                ),
                "interventions_in_statements": len(unit.get("interventions") or ()),
                "comparators_detected": sum(
                    1 for s in assessment.signals if s.category == "comparator"
                ),
                "preclinical_models_detected": sum(
                    1 for s in assessment.signals if s.category in ("in_vitro", "in_vivo")
                ),
                "shared_dimensions": ["disease", "biomarker_requirements"],
                "specific_dimensions": (
                    ["population", "setting", "evidence_design"] if proposals else []
                ),
                "not_separable_dimensions": (
                    ["therapy_line", "stage", "regimen"] if proposals else []
                ),
                "do_not_propagate": (
                    ["population", "setting", "therapy_line", "stage", "comparator"]
                    if flags["contains_preclinical_evidence"]
                    else []
                ),
                "statement_ids": list(unit.get("statement_ids") or ()),
                "audit_version": AUDIT_VERSION,
            }
        )

        for statement_id in unit.get("statement_ids") or ():
            statement = statements.get(statement_id)
            if statement is None:
                continue
            mappings.append(
                _map_statement(statement, unit, proposals, text, assessment, state)
            )

    for rows, name in (
        (access_rows, "source_access_audit.jsonl"),
        (classifications, "source_structure_classification.jsonl"),
        (proposals_out, "split_proposals.jsonl"),
        (proposed_units, "proposed_profile_units.jsonl"),
        (mappings, "statement_unit_mapping_proposals.jsonl"),
        (signal_rows, "detector_signals.jsonl"),
    ):
        rows.sort(key=lambda item: tuple(str(item.get(key, "")) for key in ("profile_unit_id", "parent_profile_unit_id", "statement_id", "proposed_profile_unit_id")))
        write_jsonl(audit / name, rows)

    write_json(
        audit / "classification_summary.json",
        {
            "created_at": created_at,
            "audit_version": AUDIT_VERSION,
            "detector_version": DETECTOR_VERSION,
            "units": len(scope),
            "with_full_text": sum(1 for row in access_rows if row["availability"] == "full_text"),
            "abstract_only": sum(1 for row in access_rows if row["availability"] == "abstract_only"),
            "unavailable": sum(1 for row in access_rows if row["availability"] == "unavailable"),
            "hashes": {
                "classification": content_hash(classifications),
                "proposals": content_hash(proposed_units),
                "mappings": content_hash(mappings),
            },
        },
    )

    states: dict[str, int] = {}
    for row in classifications:
        states[row["structure_state"]] = states.get(row["structure_state"], 0) + 1
    print(f"unita' classificate: {len(classifications)}")
    print("stati:", states)
    print(f"proposte di split: {len(proposals_out)} | unita' proposte: {len(proposed_units)}")
    print(f"statement mappati: {len(mappings)}")
    print(
        "fonti: full text "
        f"{sum(1 for row in access_rows if row['availability'] == 'full_text')}, "
        f"solo abstract {sum(1 for row in access_rows if row['availability'] == 'abstract_only')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
