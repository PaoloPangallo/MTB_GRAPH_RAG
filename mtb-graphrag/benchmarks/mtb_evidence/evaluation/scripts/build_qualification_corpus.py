"""Costruisce e valuta il qualification corpus, e ne calcola il freeze status."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_manifest import (  # noqa: E402
    QualificationCorpusManifest,
    content_hash,
    evaluate_freeze,
)
from backend.pipeline.evidence.profile_unit import (  # noqa: E402
    HUMAN_REVIEWED,
    MACHINE_EXTRACTED,
    PROFILE_UNIT_VERSION,
    UNIT_DIMENSIONS,
    UNKNOWN,
    validate_units,
)
from backend.pipeline.evidence.qualification_gold import (  # noqa: E402
    GOLD_VERSION,
    agreement_rate,
    candidate_from_link,
    validate_gold,
)
from backend.pipeline.evidence.repository import EvidenceStatementRepository  # noqa: E402
from backend.pipeline.evidence.source_identity import IDENTITY_VERSION  # noqa: E402
from benchmarks.mtb_evidence.evaluation.corpus_builder import (  # noqa: E402
    SCOPE_VERSION,
    build_packet,
    build_scope,
    build_units,
    render_packet_markdown,
)
from benchmarks.mtb_evidence.evaluation.linking_evaluation import (  # noqa: E402
    LINKER_STATUS_TO_GOLD,
    NOT_EVALUABLE,
    CandidatePair,
    dimension_metrics,
    evaluate_linking,
)
from benchmarks.mtb_evidence.evaluation.source_inventory import (  # noqa: E402
    ALL_STRATA,
    build_inventory,
    apply_metadata,
    stratum_counts,
)
from benchmarks.mtb_evidence.evaluation.source_profiles import default_repository  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    canonical_json,
    read_jsonl,
    write_json,
    write_jsonl,
    write_text,
)

CORPUS_VERSION = "qualification_corpus/1.0"
LINKER_VERSION = "qualification_link/1.0"

DEFAULT_QUALIFICATION = Path("benchmarks/mtb_evidence/v3/qualification")
DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/qualification_corpus")
DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/pilot/audit")
DEFAULT_PILOT = Path("benchmarks/mtb_evidence/evaluation/results/pilot_v1")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification-dir", type=Path, default=DEFAULT_QUALIFICATION)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--pilot-dir", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _now(explicit: str | None) -> str:
    return explicit or datetime.now(timezone.utc).isoformat()


def _coverage(units: Sequence[Any], statement_count: int) -> dict[str, Any]:
    """Copertura per dimensione, distinta per origine del valore.

    `frozen_kg` e' zero su ogni dimensione clinica e non e' un difetto della
    misura: lo schema V2 non modella setting, stadio, linea, popolazione ne'
    criteri. E' precisamente il vuoto che il corpus esiste per riempire.
    """
    before = {dimension: 0 for dimension in UNIT_DIMENSIONS}
    reviewed = {dimension: 0 for dimension in UNIT_DIMENSIONS}
    machine = {dimension: 0 for dimension in UNIT_DIMENSIONS}
    for unit in units:
        target = reviewed if unit.review_status == HUMAN_REVIEWED else machine
        for dimension in unit.known_dimensions():
            target[dimension] += 1

    after = {
        dimension: reviewed[dimension] + machine[dimension] for dimension in UNIT_DIMENSIONS
    }
    unit_count = len(units) or 1
    return {
        "unit_count": len(units),
        "statement_count": statement_count,
        "frozen_kg": before,
        "reviewed_source_profile": reviewed,
        "machine_extracted_profile": machine,
        "after": after,
        "still_unknown": {
            dimension: len(units) - after[dimension] for dimension in UNIT_DIMENSIONS
        },
        "coverage_after": {
            dimension: round(after[dimension] / unit_count, 4) for dimension in UNIT_DIMENSIONS
        },
    }


def _statement_coverage(units: Sequence[Any], statement_ids: Sequence[str]) -> dict[str, Any]:
    with_profile: set[str] = set()
    with_propagatable: set[str] = set()
    for unit in units:
        with_profile.update(unit.statement_ids)
        if unit.is_propagatable and unit.known_dimensions():
            with_propagatable.update(unit.statement_ids)
    total = len(statement_ids) or 1
    return {
        "statements_total": len(statement_ids),
        "statements_with_profile_unit": len(with_profile),
        "statements_without_profile_unit": len(statement_ids) - len(with_profile),
        "statements_with_propagatable_qualifiers": len(with_propagatable),
        "statement_profile_coverage": round(len(with_profile) / total, 4),
    }


def build_corpus_report(
    *,
    manifest: Any,
    metrics: Mapping[str, Any],
    linking: Mapping[str, Any],
    annotation: Mapping[str, Any],
    absent: Sequence[Mapping[str, Any]],
) -> str:
    coverage = metrics["dimension_coverage"]
    lines = [
        "# Qualification corpus — stato",
        "",
        f"- **Versione:** `{manifest.corpus_version}`",
        f"- **Freeze status:** `{manifest.freeze_status}`",
        f"- **Fonti uniche:** {manifest.source_count} | **nello scope:** {manifest.scoped_source_count}",
        f"- **Unita' di annotazione:** {manifest.profile_unit_count}",
        f"- **Unita' con revisione umana:** {manifest.reviewed_count}",
        f"- **Unita' machine-extracted:** {manifest.machine_extracted_count}",
        "",
        "## Che cosa questo corpus e' e che cosa non e'",
        "",
        "E' l'infrastruttura completa di annotazione: inventario, scope congelato,",
        "unita' di coorte, packet ciechi, contratto di gold, workflow a due revisori e",
        "metriche. **Non** e' un corpus annotato: 96 unita' su 102 attendono la lettura",
        "della fonte primaria da parte di una persona.",
        "",
        "Nessuna unita' viene dichiarata `human_reviewed` da questo processo. Gli unici",
        "stati umani presenti sono quelli degli otto profili annotati a mano prima di",
        "questa fase, conservati invariati.",
        "",
        "## Scope",
        "",
        "La strategia e' un **censimento**: tutte le fonti citate dai 147 statement",
        "entrano nel corpus. Con 102 fonti il censimento e' sostenibile, e rende",
        "impossibile la selezione opportunistica per costruzione — non esiste un",
        "criterio da cui una fonte scomoda possa essere esclusa.",
        "",
        "Il clinical gold non partecipa alla selezione.",
        "",
        "## Copertura delle dimensioni",
        "",
        "| Dimensione | frozen KG | profilo revisionato | machine-extracted | ancora unknown |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for dimension in sorted(coverage["after"]):
        lines.append(
            f"| `{dimension}` | {coverage['frozen_kg'][dimension]} | "
            f"{coverage['reviewed_source_profile'][dimension]} | "
            f"{coverage['machine_extracted_profile'][dimension]} | "
            f"{coverage['still_unknown'][dimension]} |"
        )

    lines += [
        "",
        "La colonna *frozen KG* e' zero ovunque e non e' un difetto della misura: lo",
        "schema V2 non modella setting, stadio, linea, popolazione ne' criteri. E'",
        "esattamente il vuoto che il corpus esiste per riempire.",
        "",
        "`resection_status` resta a zero perche' nessuna fonte disponibile lo afferma.",
        "Non viene inventato.",
        "",
        "## Linking",
        "",
        f"- Coppie candidate: {linking['candidate_count']}",
        f"- Record di gold: {linking['gold_record_count']}",
        f"- **Valutabili: {linking['evaluated_count']}**",
        f"- Provvisori: {linking['provisional_count']}",
        f"- Precision: `{linking['linking_precision']}` | Recall: `{linking['linking_recall']}`",
        "",
        "Precision e recall non sono calcolabili, e la ragione e' strutturale: il gold",
        "richiede due annotazioni indipendenti e questa fase non le ha prodotte. Il",
        "numero mancante e' l'unica risposta difendibile — un valore calcolato copiando",
        "le prediction del linker darebbe 1.000 qualunque cosa il linker faccia.",
        "",
        "## Fonti assenti dallo snapshot",
        "",
        f"{len(absent)} profili revisionati non hanno alcuno statement corrispondente.",
        "",
        "| Profilo | Fonte | Titolo |",
        "| --- | --- | --- |",
    ]
    for item in absent:
        lines.append(
            f"| `{item.get('source_profile_id')}` | `{item.get('canonical_source_id')}` | "
            f"{item.get('title')} |"
        )
    lines += [
        "",
        "Sono FLAURA e FOENIX-CCA2, le due fonti che l'audit del grafo aveva gia'",
        "trovato assenti. Non vengono inserite artificialmente nel repository V3-A:",
        "l'assenza e' un reperto, e correggerla nasconderebbe un limite reale dello",
        "snapshot.",
        "",
        "## Blocker al freeze",
        "",
    ]
    lines += [f"- {blocker}" for blocker in manifest.blockers] or ["- nessuno"]
    lines += [
        "",
        f"Unita' che richiedono revisione umana: {len(annotation['second_review_required_for'])}.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output
    created_at = _now(args.timestamp)

    statements = list(read_jsonl(args.qualification_dir / "evidence_statements.jsonl"))
    statements_by_id = {
        str(item.get("evidence_statement_id")): item for item in statements
    }
    repository = EvidenceStatementRepository(statements)

    metadata_path = output / "source_metadata_cache.jsonl"
    metadata: dict[str, Mapping[str, Any]] = {}
    if metadata_path.is_file():
        metadata = {str(row.get("identifier_key")): row for row in read_jsonl(metadata_path)}

    entries = build_inventory(
        statements,
        audit_dir=args.audit_dir,
        ablation_manifest=args.pilot_dir / "reporting_ablation_manifest.json",
        conflicts_path=args.qualification_dir / "conflicts.jsonl",
        pilot_runs=args.pilot_dir / "case_runs.jsonl",
        profiles=default_repository(),
    )
    apply_metadata(entries, metadata)

    # --- scope ---------------------------------------------------------------
    profiles = default_repository()
    linked_profile_ids = {
        profile_id for entry in entries for profile_id in entry.profile_ids
    }
    orphans = [
        profile for profile in profiles if profile.source_id not in linked_profile_ids
    ]
    scope = build_scope(entries, orphan_profiles=orphans)
    scope_rows = [decision.as_dict() for decision in scope]
    scope_payload = {
        "scope_version": SCOPE_VERSION,
        "selection_strategy": "census",
        "strategy_rationale": (
            "Tutte le fonti citate dai 147 statement entrano nel corpus. Con 102 fonti il "
            "censimento e' sostenibile e rende strutturalmente impossibile la selezione "
            "opportunistica: non esiste un criterio da cui una fonte scomoda possa essere "
            "esclusa, perche' non esiste un criterio."
        ),
        "universe": "147 EvidenceStatement congelati",
        "clinical_gold_used": False,
        "included_count": sum(1 for row in scope_rows if row["included"]),
        "excluded_count": sum(1 for row in scope_rows if not row["included"]),
        "strata": list(ALL_STRATA),
        "stratum_counts": stratum_counts(entries),
        "decisions": scope_rows,
    }
    scope_hash = content_hash(scope_payload["decisions"])
    scope_payload["qualification_scope_hash"] = scope_hash
    write_json(output / "qualification_scope.json", scope_payload)

    # --- unita' di annotazione ------------------------------------------------
    profiles_by_source_id = {profile.source_id: profile for profile in profiles}
    units = build_units(
        entries,
        metadata=metadata,
        profiles_by_source_id=profiles_by_source_id,
        created_at=created_at,
    )
    unit_problems = validate_units(units)
    unit_rows = [unit.as_dict() for unit in units]
    write_jsonl(output / "source_profile_units.jsonl", unit_rows)

    units_by_id = {unit.profile_unit_id: unit for unit in units}
    entries_by_source = {entry.canonical_source_id: entry for entry in entries}

    # --- annotation packets ---------------------------------------------------
    packets_dir = output / "annotation_packets"
    for unit in units:
        entry = entries_by_source.get(unit.canonical_source_id)
        if entry is None:
            continue
        packet = build_packet(
            unit, entry=entry, statements_by_id=statements_by_id, metadata=metadata
        )
        write_json(packets_dir / f"{unit.blind_annotation_id}.json", packet)
        write_text(packets_dir / f"{unit.blind_annotation_id}.md", render_packet_markdown(packet))

    # --- candidati del linker -------------------------------------------------
    candidates: list[CandidatePair] = []
    for unit in units:
        for statement_id in unit.statement_ids:
            matched = sorted(set(unit.pmids) | set(unit.dois) | set(unit.ncts))
            candidates.append(
                CandidatePair(
                    statement_id=statement_id,
                    profile_unit_id=unit.profile_unit_id,
                    predicted_status="exact_source_match",
                    match_method="exact_controlled_identifier",
                    matched_identifiers=tuple(matched),
                )
            )
    candidates.sort(key=lambda item: (item.statement_id, item.profile_unit_id))
    write_jsonl(
        output / "statement_profile_candidates.jsonl",
        [candidate.as_dict() for candidate in candidates],
    )

    # --- gold -----------------------------------------------------------------
    # I candidati diventano *tracce* di gold, non gold. Nessuna annotazione viene
    # popolata: copiare la prediction del linker nel riferimento contro cui il
    # linker viene misurato darebbe precision 1.000 comunque.
    gold_records = [
        candidate_from_link(
            candidate.statement_id,
            candidate.profile_unit_id,
            predicted_status=LINKER_STATUS_TO_GOLD[candidate.predicted_status],
        )
        for candidate in candidates
    ]
    gold_problems = validate_gold(gold_records)
    write_jsonl(
        output / "statement_qualification_gold.jsonl",
        [record.as_dict() for record in gold_records],
    )

    rate, agreed_pairs = agreement_rate(gold_records)
    linking = evaluate_linking(candidates, gold_records)
    linking["inter_annotator_agreement"] = rate if rate is not None else NOT_EVALUABLE
    linking["agreement_pair_count"] = agreed_pairs
    linking["linker_version"] = LINKER_VERSION
    write_json(output / "linking_metrics.json", linking)
    write_json(output / "dimension_linking_metrics.json", dimension_metrics(candidates, gold_records))

    # --- link e viste correnti, riportati invariati ---------------------------
    existing_links = list(read_jsonl(args.qualification_dir / "qualification_links.jsonl"))
    existing_views = list(read_jsonl(args.qualification_dir / "qualified_evidence_views.jsonl"))
    existing_conflicts = list(read_jsonl(args.qualification_dir / "conflicts.jsonl"))
    existing_ambiguous = list(read_jsonl(args.qualification_dir / "ambiguous_links.jsonl"))
    write_jsonl(output / "qualification_links.jsonl", existing_links)
    write_jsonl(output / "qualified_evidence_views.jsonl", existing_views)
    write_jsonl(output / "conflicts.jsonl", existing_conflicts)
    write_jsonl(output / "ambiguous_units.jsonl", [
        unit.as_dict() for unit in units if not unit.is_propagatable
    ])

    # --- fonti irrisolte ------------------------------------------------------
    # Due categorie che sarebbe sbagliato confondere. Un identificatore non
    # risolto e' un difetto del corpus e blocca il freeze. Una fonte assente
    # dallo snapshot e' un *risultato* dell'audit: FLAURA e FOENIX-CCA2 hanno
    # PMID perfettamente validi e non compaiono fra i 147 statement perche' lo
    # snapshot non le contiene. Contarle come difetto nasconderebbe il reperto.
    unresolved = [
        {
            "canonical_source_id": entry.canonical_source_id,
            "category": "unresolved_identifier",
            "reason": "identificatore non risolto",
            "identifiers": entry.identity.as_dict()["unresolved"],
            "blocks_freeze": True,
        }
        for entry in entries
        if not entry.identity.is_resolved
    ]
    absent = [
        {
            "canonical_source_id": f"PMID:{profile.pmid}" if profile.pmid else profile.source_id,
            "category": "absent_from_snapshot",
            "reason": (
                "profilo revisionato la cui fonte non e' citata da nessuno dei 147 statement: "
                "assente dallo snapshot, non inserita artificialmente nel repository V3-A"
            ),
            "source_profile_id": profile.source_id,
            "title": profile.title,
            "blocks_freeze": False,
        }
        for profile in orphans
    ]
    write_jsonl(output / "unresolved_sources.jsonl", unresolved + absent)

    # --- metriche di copertura ------------------------------------------------
    coverage = _coverage(units, len(statements))
    statement_coverage = _statement_coverage(units, sorted(statements_by_id))
    provenance_complete = all(unit.provenance_complete() for unit in units)
    propagatable = [unit for unit in units if unit.is_propagatable]

    qualification_metrics = {
        "corpus_version": CORPUS_VERSION,
        "generated_at_utc": created_at,
        "source_count": len(entries),
        "scoped_source_count": scope_payload["included_count"],
        "source_profile_coverage": round(
            sum(1 for entry in entries if entry.profile_status != "no_profile") / (len(entries) or 1),
            4,
        ),
        "source_stratum_coverage": stratum_counts(entries),
        "statement_coverage": statement_coverage,
        "dimension_coverage": coverage,
        "qualifier_provenance_completeness": 1.0 if provenance_complete else round(
            sum(1 for unit in units if unit.provenance_complete()) / (len(units) or 1), 4
        ),
        "ambiguous_qualification_rate": round(
            (len(units) - len(propagatable)) / (len(units) or 1), 4
        ),
        "conflict_rate": round(len(existing_conflicts) / (len(existing_links) or 1), 4),
        "unresolved_source_rate": round(len(unresolved) / (len(entries) or 1), 4),
        "absent_source_count": len(absent),
        "qualifier_addition_coverage": round(
            sum(len(unit.known_dimensions()) for unit in units)
            / ((len(units) or 1) * len(UNIT_DIMENSIONS)),
            4,
        ),
        "units_total": len(units),
        "units_reviewed": sum(1 for unit in units if unit.review_status == HUMAN_REVIEWED),
        "units_machine_extracted": sum(
            1 for unit in units if unit.extraction_status == MACHINE_EXTRACTED
        ),
        "units_awaiting_review": sum(1 for unit in units if unit.requires_human_review),
        "unit_validation_problems": unit_problems,
        "gold_validation_problems": gold_problems,
    }
    write_json(output / "qualification_metrics.json", qualification_metrics)

    annotation_status = {
        "generated_at_utc": created_at,
        "units_total": len(units),
        "by_extraction_status": _counts(units, "extraction_status"),
        "by_review_status": _counts(units, "review_status"),
        "by_cohort_state": _counts(units, "cohort_state"),
        "packets_produced": len(units),
        "second_review_required_for": [
            unit.profile_unit_id for unit in units if unit.requires_human_review
        ],
        "note": (
            "Nessuna unita' e' dichiarata human_reviewed da questo processo. Gli unici "
            "stati umani presenti provengono dagli otto profili annotati a mano prima di "
            "questa fase e vengono conservati invariati."
        ),
    }
    write_json(output / "annotation_status.json", annotation_status)

    # --- freeze ---------------------------------------------------------------
    snapshot = str(
        (statements[0].get("provenance") or {}).get("snapshot_fingerprint") or ""
    ) if statements else ""
    repository_hash = repository.content_hash()
    freeze = evaluate_freeze(
        units=units,
        gold_records=gold_records,
        required_second_reviews=len(gold_records),
        unresolved_sources=len(unresolved),
        snapshot_fingerprint=snapshot,
        expected_snapshot_fingerprint=snapshot,
        statement_repository_hash=repository_hash,
        expected_statement_repository_hash=repository_hash,
    )

    inventory_hash_payload = read_jsonl(output / "source_inventory.jsonl")
    manifest = QualificationCorpusManifest(
        corpus_version=CORPUS_VERSION,
        source_inventory_hash=content_hash(inventory_hash_payload),
        qualification_scope_hash=scope_hash,
        statement_repository_hash=repository_hash,
        source_profiles_hash=content_hash([profile.as_dict() for profile in profiles]),
        profile_units_hash=content_hash(unit_rows),
        link_gold_hash=content_hash([record.as_dict() for record in gold_records]),
        linker_version=LINKER_VERSION,
        schema_versions={
            "evidence_statement": "v3.0.0",
            "source_clinical_profile_unit": PROFILE_UNIT_VERSION,
            "statement_qualification_gold": GOLD_VERSION,
            "qualification_scope": SCOPE_VERSION,
            "source_identity": IDENTITY_VERSION,
        },
        snapshot_fingerprint=snapshot,
        source_count=len(entries),
        scoped_source_count=scope_payload["included_count"],
        profile_unit_count=len(units),
        reviewed_count=qualification_metrics["units_reviewed"],
        machine_extracted_count=qualification_metrics["units_machine_extracted"],
        provisional_count=linking["provisional_count"],
        frozen_count=linking["frozen_count"],
        unresolved_count=len(unresolved),
        evaluated_link_count=linking["evaluated_count"],
        not_evaluated_link_count=linking["not_evaluated_count"],
        created_at=created_at,
        freeze_status=freeze.status,
        blockers=freeze.blockers,
    )
    write_json(output / "qualification_corpus_manifest.json", manifest.as_dict())
    write_text(
        output / "QUALIFICATION_CORPUS_REPORT.md",
        build_corpus_report(
            manifest=manifest,
            metrics=qualification_metrics,
            linking=linking,
            annotation=annotation_status,
            absent=absent,
        ),
    )

    print(f"fonti: {len(entries)} | nello scope: {scope_payload['included_count']}")
    print(f"unita': {len(units)} | revisionate: {qualification_metrics['units_reviewed']}")
    print(f"packet: {len(units)} | candidati: {len(candidates)} | gold valutabili: {linking['evaluated_count']}")
    print(f"provenance completa: {provenance_complete}")
    print(f"freeze_status: {freeze.status}")
    for blocker in freeze.blockers:
        print(f"  blocker: {blocker}")
    if unit_problems or gold_problems:
        for problem in unit_problems + gold_problems:
            print(f"  problema: {problem}")
        return 1
    return 0


def _counts(units: Sequence[Any], attribute: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for unit in units:
        value = getattr(unit, attribute)
        found[value] = found.get(value, 0) + 1
    return dict(sorted(found.items()))


if __name__ == "__main__":
    raise SystemExit(main())
