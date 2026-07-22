"""Risolve le coorti e propone profili curati per le unita' prioritarie."""

from __future__ import annotations

import argparse
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
    COHORT_RESOLVED as UNIT_COHORT_RESOLVED,
    COHORT_SINGLE,
    COHORT_UNRESOLVED,
    HUMAN_REVIEWED,
    SOURCE_CHECKED,
    UNKNOWN,
    FieldProvenance,
    SourceClinicalProfileUnit,
    validate_units,
)
from benchmarks.mtb_evidence.evaluation.source_curation import (  # noqa: E402
    CANDIDATE_STATES,
    COHORT_NOT_SEPARABLE,
    COHORT_PARTIALLY_RESOLVED,
    COHORT_RESOLVED,
    CURATION_VERSION,
    INSUFFICIENT_SOURCE_INFORMATION,
    SOURCE_UNAVAILABLE,
    classify_statement_support,
    collapse,
    detect,
    resolve_cohorts,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_CORPUS = Path("benchmarks/mtb_evidence/v3/qualification_corpus")
DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/priority_curation")

CURATABLE_DIMENSIONS = ("setting", "therapy_line", "stage", "resection_status", "evidence_design")

# Solo `evidence_design` diventa un valore dell'unita'. I marcatori di fase,
# randomizzazione, braccio unico e preclinico descrivono lo **studio**, quindi
# rilevarli equivale ad affermarli.
#
# Le altre quattro dimensioni no, e la prova e' venuta dai dati: sul PMID
# 15329413 le regex hanno prodotto `resection_status = resected` e
# `therapy_line = relapsed or refractory` da parole che descrivevano i campioni
# tumorali, non il disegno dello studio. Entrambi i valori erano plausibili,
# entrambi sbagliati, e nessuno dei due sarebbe stato distinguibile da un valore
# giusto guardando il file.
#
# Restano quindi rilevate ma non emesse: diventano domande per il revisore, con
# lo span allegato, e il campo dell'unita' resta `unknown`. E' la scelta che il
# protocollo impone — meglio un campo vuoto di un qualificatore non dimostrato.
EMITTED_DIMENSIONS = ("evidence_design",)
REVIEW_QUESTION_DIMENSIONS = ("setting", "therapy_line", "stage", "resection_status")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _abstract_for(unit: Mapping[str, Any], cache: Mapping[str, Mapping[str, Any]]):
    for pmid in unit.get("pmids") or ():
        record = cache.get(f"pmid:{pmid}")
        if record:
            return record
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    priority = list(read_jsonl(output / "priority_units.jsonl"))
    corpus_units = {
        str(row.get("profile_unit_id")): row
        for row in read_jsonl(args.corpus_dir / "source_profile_units.jsonl")
    }
    abstracts = {
        str(row.get("identifier_key")): row
        for row in read_jsonl(output / "source_abstract_cache.jsonl")
    }
    statements = {
        str(row.get("evidence_statement_id")): row
        for row in read_jsonl(args.corpus_dir / "evidence_statements.jsonl")
    } if (args.corpus_dir / "evidence_statements.jsonl").is_file() else {
        str(row.get("evidence_statement_id")): row
        for row in read_jsonl(
            Path("benchmarks/mtb_evidence/v3/qualification/evidence_statements.jsonl")
        )
    }

    access_rows: list[dict[str, Any]] = []
    resolutions: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    resolved_units: list[dict[str, Any]] = []
    unresolved_units: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for unit in priority:
        unit_id = str(unit["profile_unit_id"])
        existing = corpus_units.get(unit_id, {})
        abstract = _abstract_for(unit, abstracts)
        # Un record del registro privo di abstract non e' la fonte consultata:
        # e' la prova che la fonte non e' stata consultata.
        has_text = bool(abstract and abstract.get("abstract_available"))

        access_rows.append(
            {
                "profile_unit_id": unit_id,
                "canonical_source_id": unit["canonical_source_id"],
                "pmids": list(unit.get("pmids") or ()),
                "system_consulted": "pubmed_efetch" if abstract else "none",
                "access_date": str(abstract.get("access_date") or "") if abstract else "",
                "locator": str(abstract.get("locator") or "") if abstract else "",
                "abstract_available": bool(abstract and abstract.get("abstract_available")),
                "abstract_sha256": str(abstract.get("abstract_sha256") or "") if abstract else "",
                "abstract_length": int(abstract.get("abstract_length") or 0) if abstract else 0,
                "mesh_terms": list(abstract.get("mesh_terms") or ()) if abstract else [],
                "publication_types": list(abstract.get("publication_types") or ()) if abstract else [],
                "availability_status": (
                    "available"
                    if abstract and abstract.get("abstract_available")
                    else "awaiting_source_access"
                ),
            }
        )

        resolution = resolve_cohorts(
            profile_unit_id=unit_id,
            canonical_source_id=str(unit["canonical_source_id"]),
            abstract=abstract,
            intervention_count=len(unit.get("interventions") or ()),
            disease_count=len(unit.get("diseases") or ()),
        )

        # Estrazione ancorata: solo dimensioni con un valore univoco e uno span.
        detections = detect(abstract) if abstract else []
        collapsed = {
            dimension: collapse(detections, dimension) for dimension in CURATABLE_DIMENSIONS
        }
        proposed = {
            dimension: item
            for dimension, item in collapsed.items()
            if item is not None and dimension in EMITTED_DIMENSIONS
        }
        review_questions = {
            dimension: item
            for dimension, item in collapsed.items()
            if item is not None and dimension in REVIEW_QUESTION_DIMENSIONS
        }
        contradicted = [
            dimension
            for dimension in CURATABLE_DIMENSIONS
            if collapsed[dimension] is None
            and any(item.dimension == dimension for item in detections)
        ]

        resolution.shared_dimensions = tuple(sorted(proposed))
        resolution.specific_dimensions = tuple(sorted(review_questions))
        resolution.unknown_dimensions = tuple(
            sorted(set(CURATABLE_DIMENSIONS) - set(proposed))
        )
        resolutions.append(resolution.as_dict())

        # I profili umani preesistenti non vengono toccati.
        is_human = existing.get("review_status") == HUMAN_REVIEWED
        if is_human:
            resolved_units.append(existing)
            proposals.append(
                {
                    "profile_unit_id": unit_id,
                    "canonical_source_id": unit["canonical_source_id"],
                    "action": "preserved_human_review",
                    "proposed_dimensions": {},
                    "note": "profilo gia' revisionato da una persona: conservato invariato",
                    "curation_version": CURATION_VERSION,
                }
            )
        else:
            provenance = tuple(
                FieldProvenance(
                    field_name=dimension,
                    value_origin="primary_source_text",
                    source_locator=f"{abstract.get('locator', '')}{item.locator}"
                    if abstract
                    else item.locator,
                    access_date=str(abstract.get("access_date") or "") if abstract else "",
                    asserted_by="deterministic_span_extraction",
                    span_hash=str(abstract.get("abstract_sha256") or "") if abstract else "",
                    note=(
                        f"pattern {item.pattern_id}, sezione {item.section_label}, "
                        f"testo «{item.matched_text}», confidenza {item.confidence}"
                    ),
                )
                for dimension, item in sorted(proposed.items())
            )
            reasons = [
                "estrazione automatica ancorata all'abstract: da confermare da una persona"
            ]
            if review_questions:
                reasons.append(
                    "rilevate ma non emesse, da confermare sulla fonte: "
                    + ", ".join(sorted(review_questions))
                )
            if contradicted:
                reasons.append(
                    "rilevazioni discordanti, valore non emesso: " + ", ".join(contradicted)
                )
            if resolution.state != COHORT_RESOLVED:
                reasons.append(f"coorte: {resolution.state}")

            cohort_state = (
                COHORT_SINGLE
                if resolution.state == COHORT_RESOLVED
                else COHORT_UNRESOLVED
            )
            curated = SourceClinicalProfileUnit(
                profile_unit_id=unit_id,
                canonical_source_id=str(unit["canonical_source_id"]),
                pmids=tuple(unit.get("pmids") or ()),
                dois=tuple(unit.get("dois") or ()),
                ncts=tuple(unit.get("ncts") or ()),
                title=str(unit.get("title") or ""),
                cohort_id="cohort-1",
                cohort_state=cohort_state,
                cohort_note=resolution.explanation,
                evidence_design=(
                    proposed["evidence_design"].value if "evidence_design" in proposed else UNKNOWN
                ),
                statement_ids=tuple(unit.get("statement_ids") or ()),
                source_spans=tuple(item.locator for item in proposed.values()),
                extraction_status=(
                    SOURCE_CHECKED
                    if has_text
                    else existing.get("extraction_status", "machine_extracted")
                ),
                review_status=AWAITING_FIRST_REVIEW,
                requires_human_review=True,
                human_review_reasons=tuple(reasons),
                provenance=provenance,
                blind_annotation_id=str(unit.get("blind_annotation_id") or ""),
                created_at=created_at,
            )
            payload = curated.as_dict()
            if resolution.state == COHORT_RESOLVED:
                resolved_units.append(payload)
            else:
                unresolved_units.append(payload)
            proposals.append(
                {
                    "profile_unit_id": unit_id,
                    "canonical_source_id": unit["canonical_source_id"],
                    "action": "source_checked_proposal" if has_text else "awaiting_source_access",
                    "proposed_dimensions": {
                        dimension: item.as_dict() for dimension, item in sorted(proposed.items())
                    },
                    "review_questions": {
                        dimension: item.as_dict()
                        for dimension, item in sorted(review_questions.items())
                    },
                    "contradicted_dimensions": contradicted,
                    "cohort_resolution_state": resolution.state,
                    "note": (
                        "proposta prodotta da estrazione deterministica ancorata a span. "
                        "Non e' una revisione umana."
                    ),
                    "curation_version": CURATION_VERSION,
                }
            )

        # Relazione statement-unita'.
        conflicting_statements = {
            str(item.get("statement_id"))
            for item in read_jsonl(args.corpus_dir / "conflicts.jsonl")
        }
        for statement_id in unit.get("statement_ids") or ():
            statement = statements.get(statement_id, {})
            intervention = str((statement.get("intervention") or {}).get("label") or "")
            state, support, explanation = classify_statement_support(
                abstract=abstract,
                intervention=intervention,
                has_conflict=statement_id in conflicting_statements,
                cohort_state=resolution.state,
            )
            candidates.append(
                {
                    "statement_id": statement_id,
                    "profile_unit_id": unit_id,
                    "canonical_source_id": unit["canonical_source_id"],
                    "candidate_state": state,
                    "support_type": support,
                    "intervention": intervention,
                    "explanation": explanation,
                    "is_gold": False,
                    "note": "classificazione automatica: non e' un verdetto e non va copiata nel gold",
                    "curation_version": CURATION_VERSION,
                }
            )

    candidates.sort(key=lambda item: (item["statement_id"], item["profile_unit_id"]))
    resolutions.sort(key=lambda item: item["profile_unit_id"])
    proposals.sort(key=lambda item: item["profile_unit_id"])
    access_rows.sort(key=lambda item: item["profile_unit_id"])
    resolved_units.sort(key=lambda item: item["profile_unit_id"])
    unresolved_units.sort(key=lambda item: item["profile_unit_id"])

    write_jsonl(output / "source_access_manifest.jsonl", access_rows)
    write_jsonl(output / "cohort_resolution_decisions.jsonl", resolutions)
    write_jsonl(output / "curated_profile_proposals.jsonl", proposals)
    write_jsonl(output / "resolved_profile_units.jsonl", resolved_units)
    write_jsonl(output / "unresolved_profile_units.jsonl", unresolved_units)
    write_jsonl(output / "statement_profile_candidates.jsonl", candidates)

    units_for_validation = [
        SourceClinicalProfileUnit(
            profile_unit_id=row["profile_unit_id"],
            canonical_source_id=row["canonical_source_id"],
            cohort_state=row["cohort_state"],
            extraction_status=row["extraction_status"],
            review_status=row["review_status"],
            requires_human_review=row["requires_human_review"],
            setting=row["setting"],
            therapy_line=row["therapy_line"],
            stage=row["stage"],
            resection_status=row["resection_status"],
            evidence_design=row["evidence_design"],
            disease=row["disease"],
            intervention=tuple(row["intervention"]),
            biomarker_requirements=tuple(row["biomarker_requirements"]),
            prior_therapies=tuple(row["prior_therapies"]),
            regimen=row["regimen"],
            comparator=row["comparator"],
            population=row["population"],
            inclusion_criteria=row["inclusion_criteria"],
            exclusion_criteria=row["exclusion_criteria"],
            provenance=tuple(
                FieldProvenance(
                    field_name=item["field_name"],
                    value_origin=item["value_origin"],
                    source_locator=item.get("source_locator", ""),
                    access_date=item.get("access_date", ""),
                    asserted_by=item.get("asserted_by", ""),
                    span_hash=item.get("span_hash", ""),
                    note=item.get("note", ""),
                )
                for item in row["provenance"]
            ),
        )
        for row in resolved_units + unresolved_units
    ]
    problems = validate_units(units_for_validation)

    counts: dict[str, int] = {}
    for row in resolutions:
        counts[row["resolution_state"]] = counts.get(row["resolution_state"], 0) + 1
    candidate_counts: dict[str, int] = {}
    for row in candidates:
        candidate_counts[row["candidate_state"]] = candidate_counts.get(row["candidate_state"], 0) + 1

    write_json(
        output / "curation_summary.json",
        {
            "created_at": created_at,
            "curation_version": CURATION_VERSION,
            "priority_units": len(priority),
            "sources_with_abstract": sum(1 for row in access_rows if row["abstract_available"]),
            "sources_awaiting_access": sum(
                1 for row in access_rows if not row["abstract_available"]
            ),
            "cohort_resolution": counts,
            "candidate_states": candidate_counts,
            "new_units_created": 0,
            "new_units_note": (
                "Nessuna unita' nuova. Le fonti multi-braccio sono riconosciute ma "
                "l'abstract non permette di assegnare gli statement alle coorti; "
                "suddividere sulla base degli statement del sistema creerebbe coorti "
                "che la fonte non afferma."
            ),
            "validation_problems": problems,
            "resolved_units_hash": content_hash(resolved_units),
            "unresolved_units_hash": content_hash(unresolved_units),
            "candidates_hash": content_hash(candidates),
        },
    )

    print(f"unita' prioritarie: {len(priority)}")
    print(f"con abstract: {sum(1 for r in access_rows if r['abstract_available'])}")
    print("coorti:", counts)
    print("candidati:", candidate_counts)
    if problems:
        for problem in problems:
            print(f"  problema: {problem}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
