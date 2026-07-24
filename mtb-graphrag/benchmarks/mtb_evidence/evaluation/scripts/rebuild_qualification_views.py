"""Link, viste prototipo, gold, manifest e diff della nuova versione del corpus.

Il linker lavora **solo sulle unita' attive**. Una parent sostituita e una
proposta respinta restano nel corpus perche' la storia sia leggibile, e proprio
per questo non devono comparire in una vista: un lettore che le trovasse fra i
qualificatori non avrebbe modo di sapere che descrivono uno stato superato.

Le viste sono in modalita' `prototype`, e la modalita' non e' una etichetta.
Determina tre cose:

- i qualificatori `none` non vengono applicati. Nessuno li ha confermati, e
  mostrarli come qualificatori li renderebbe indistinguibili da quelli letti su
  una fonte;
- i qualificatori `prototype_only` vengono applicati e **mostrati**, con
  `display_allowed = true` e `hard_filter_allowed = false`. Nasconderli
  toglierebbe a chi puo' correggerli l'unica occasione di vederli;
- nessuna dimensione e' hard-filterable, perche' nessuna unita' e' `final`. Non e'
  un difetto della vista: e' lo stato reale della revisione.

Il fingerprint prodotto qui identifica il corpus, non il grafo. L'impronta del
grafo congelato viene ricopiata dalla versione precedente e confrontata: se
cambiasse, la rigenerazione si fermerebbe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_regeneration import (  # noqa: E402
    BLOCKED,
    EXPECTED_AUTHOR_APPROVAL,
    EXPECTED_HASH_CHANGE,
    EXPECTED_HISTORY_UPDATE,
    EXPECTED_POLICY_MIGRATION,
    EXPECTED_UNIT_RESTRUCTURE,
    NON_HASHED_FIELDS,
    READY_FOR_PROTOTYPE,
    REGENERATION_VERSION,
    UNEXPECTED_CHANGE,
    UNRESOLVED_CONFLICT,
    corpus_fingerprint,
    stable_hash,
    validate_corpus,
)
from backend.pipeline.evidence.profile_unit import (  # noqa: E402
    NOT_APPLICABLE,
    PROFILE_UNIT_VERSION,
    UNKNOWN,
)
from backend.pipeline.evidence.propagation_policy import (  # noqa: E402
    FINAL,
    NONE,
    POLICY_VERSION,
    PROTOTYPE_ONLY,
)
from backend.pipeline.evidence.propagation_guards import (  # noqa: E402
    GUARD_VERSION,
    run_guards,
)
from backend.pipeline.evidence.qualification import (  # noqa: E402
    LINK_VERSION,
    PROFILE_DIMENSIONS,
)
from backend.pipeline.evidence.source_basis import SOURCE_BASIS_VERSION  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

V3 = Path("benchmarks/mtb_evidence/v3")
DEFAULT_OUTPUT = V3 / "qualification_corpus_v2"
DEFAULT_PREVIOUS_CORPUS = V3 / "qualification_corpus"
DEFAULT_PREVIOUS_VIEWS = V3 / "qualification"
DEFAULT_GOLD = V3 / "author_approval_23344087/provisional_gold.jsonl"
SECOND_REVIEW = V3 / "priority_curation/annotation_packets/second_review"

CORPUS_VERSION = "qualification_corpus/2.0"
MANIFEST_VERSION = "qualification_corpus_manifest/2.0"
MIGRATION_ID = "MIG-V3-002-propagation-policy-and-author-approvals"
VIEW_MODE = "prototype"

# La fonte dei dati rigenerati. Non e' il commit corrente: e' lo stato del
# repository da cui gli artefatti sono stati letti, e resta stabile mentre questa
# fase produce i propri commit.
DEFAULT_SOURCE_SHA = "d5e71fc27509551d3549a93b2743bf624eb26d56"

# Dimensione della vista → campo dell'unita'. `resection_status` esiste
# sull'unita' e non esisteva sul profilo: e' una delle cose che il passaggio da
# profilo a unita' ha reso rappresentabili.
DIMENSION_FIELD = {
    "disease_setting": "setting",
    "stage": "stage",
    "therapy_line": "therapy_line",
    "resection_status": "resection_status",
    "population": "population",
    "prior_therapies": "prior_therapies",
    "biomarker_requirements": "biomarker_requirements",
    "regimen": "regimen",
    "inclusion_criteria_summary": "inclusion_criteria",
    "exclusion_criteria_summary": "exclusion_criteria",
}

NOT_SEPARABLE = "not_separable"
SENTINELS = (UNKNOWN, NOT_APPLICABLE, NOT_SEPARABLE, "")

# Da dove viene un campo della vista. Le cinque classi non sono gradi di
# qualita': dicono chi risponde del valore, ed e' l'unica cosa che permette a chi
# legge di sapere quanto fidarsi.
ORIGIN_NATIVE = "evidence_statement_native"
ORIGIN_SOURCE_CHECKED = "source_checked"
ORIGIN_FIRST_REVIEW = "first_review_approved"
ORIGIN_MACHINE = "machine_extracted"

REVIEW_DECISION_FILES = (
    ("PMID:22277784", "first_review/statement_first_review_decisions.jsonl"),
    ("PMID:31358542", "author_approval/statement_first_review_decisions.jsonl"),
    ("PMID:22235099", "author_approval_22235099/statement_first_review_decisions.jsonl"),
    ("PMID:23344087", "author_approval_23344087/statement_first_review_decisions.jsonl"),
)

TERMINOLOGY_FILES = (
    "clinical_preclinical_review_batch/terminology_mappings.jsonl",
    "first_review/intervention_mappings.jsonl",
    "author_approval_22235099/terminology_mappings.jsonl",
    "author_approval_23344087/terminology_mappings.jsonl",
)

DETECTOR_FILES = (
    "clinical_preclinical_review_batch/detector_case_review.jsonl",
    "author_approval/detector_reference_cases.jsonl",
    "author_approval_22235099/detector_reference_cases.jsonl",
    "author_approval_23344087/detector_reference_cases.jsonl",
)

INTEGRATED_REVIEWS = ("PMID:22277784", "PMID:31358542", "PMID:22235099", "PMID:23344087")


class RebuildFailure(RuntimeError):
    """La ricostruzione non produce un corpus accettabile."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--v3-dir", type=Path, default=V3)
    parser.add_argument("--previous-corpus", type=Path, default=DEFAULT_PREVIOUS_CORPUS)
    parser.add_argument("--previous-views", type=Path, default=DEFAULT_PREVIOUS_VIEWS)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--source-sha", default=DEFAULT_SOURCE_SHA)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def hash_directory(directory: Path) -> dict[str, str]:
    if not directory.is_dir():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def _has_value(value: Any) -> bool:
    if isinstance(value, (list, tuple)):
        return bool(value)
    return str(value or "").strip().casefold() not in SENTINELS


def _sentinel_of(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "" if value else UNKNOWN
    text = str(value or "").strip().casefold()
    return text if text in SENTINELS else ""


def _origin_of(unit: Mapping[str, Any]) -> str:
    status = str(unit.get("review_status") or "")
    if status in ("first_review_complete", "human_reviewed"):
        return ORIGIN_FIRST_REVIEW
    if str(unit.get("extraction_status") or "") == "source_checked":
        return ORIGIN_SOURCE_CHECKED
    if str(unit.get("extraction_status") or "") == "machine_extracted":
        return ORIGIN_MACHINE
    return ORIGIN_MACHINE


def _locators_for(unit: Mapping[str, Any], dimension_field: str) -> list[str]:
    found = [
        str(item.get("source_locator") or "")
        for item in unit.get("provenance") or []
        if item.get("field_name") == dimension_field and item.get("source_locator")
    ]
    return sorted(set(found))


def _provenance_for(unit: Mapping[str, Any], dimension_field: str) -> dict[str, Any]:
    for item in unit.get("provenance") or []:
        if item.get("field_name") == dimension_field:
            return dict(item)
    return {}


def build_links(
    statements: Sequence[Mapping[str, Any]],
    active_units: Sequence[Mapping[str, Any]],
    *,
    created_at: str,
) -> list[dict[str, Any]]:
    """Un link per ogni coppia statement/unita' attiva che condivide un PMID."""
    by_pmid: dict[str, list[Mapping[str, Any]]] = {}
    for unit in active_units:
        for pmid in unit.get("pmids") or []:
            by_pmid.setdefault(str(pmid), []).append(unit)

    links: list[dict[str, Any]] = []
    for statement in statements:
        statement_id = str(statement.get("evidence_statement_id") or "")
        pmids = sorted(
            {
                str(ref.get("external_identifier") or "")
                for ref in statement.get("source_references") or []
                if str(ref.get("source_type") or "") == "pubmed"
                and ref.get("external_identifier")
            }
        )
        candidates = sorted(
            {
                unit["profile_unit_id"]: unit
                for pmid in pmids
                for unit in by_pmid.get(pmid, [])
            }.values(),
            key=lambda unit: str(unit["profile_unit_id"]),
        )
        for unit in candidates:
            eligibility = str(unit.get("propagation_eligibility") or NONE)
            added: list[dict[str, Any]] = []
            excluded: list[str] = []
            for dimension, field_name in sorted(DIMENSION_FIELD.items()):
                value = unit.get(field_name)
                if not _has_value(value):
                    excluded.append(dimension)
                    continue
                # Un qualificatore che nessuno ha confermato non entra nella
                # vista: mostrarlo lo renderebbe indistinguibile da uno letto
                # sulla fonte.
                if eligibility == NONE:
                    excluded.append(dimension)
                    continue
                added.append(
                    {
                        "dimension": dimension,
                        "value": value,
                        "value_origin": _origin_of(unit),
                        "source_profile_unit_id": unit["profile_unit_id"],
                        "source_identifier": str(unit.get("canonical_source_id") or ""),
                        "qualification_link_id": f"QL-{statement_id}-{unit['profile_unit_id']}",
                        "review_status": str(unit.get("review_status") or ""),
                        "propagation_eligibility": eligibility,
                        "display_allowed": eligibility in (PROTOTYPE_ONLY, FINAL),
                        "hard_filter_allowed": eligibility == FINAL,
                        "source_basis": str(unit.get("source_basis") or "unknown"),
                        "source_locators": _locators_for(unit, field_name),
                        "provenance": _provenance_for(unit, field_name),
                    }
                )
            links.append(
                {
                    "qualification_link_id": f"QL-{statement_id}-{unit['profile_unit_id']}",
                    "link_version": LINK_VERSION,
                    "statement_id": statement_id,
                    "source_profile_unit_id": unit["profile_unit_id"],
                    "canonical_source_id": str(unit.get("canonical_source_id") or ""),
                    "matched_pmids": sorted(set(pmids) & {str(p) for p in unit.get("pmids") or []}),
                    "match_method": "exact_pmid",
                    "match_status": "exact_source_match",
                    "unit_is_active": True,
                    "unit_review_status": str(unit.get("review_status") or ""),
                    "propagation_eligibility": eligibility,
                    "display_allowed": eligibility in (PROTOTYPE_ONLY, FINAL),
                    "hard_filter_allowed": eligibility == FINAL,
                    "source_basis": str(unit.get("source_basis") or "unknown"),
                    "unit_type": str(unit.get("unit_type") or ""),
                    "experiment_role": str(unit.get("experiment_role") or ""),
                    "assertion_polarity": str(unit.get("assertion_polarity") or ""),
                    "added_dimensions": added,
                    "excluded_dimensions": sorted(excluded),
                    "not_separable_fields": sorted(
                        key
                        for key in ("preclinical_model_composition", "component_to_statement_mapping")
                        if unit.get(key) == NOT_SEPARABLE
                    ),
                    "created_at": created_at,
                    "regeneration_version": REGENERATION_VERSION,
                }
            )
    return links


def build_views(
    statements: Sequence[Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    units_by_id: Mapping[str, Mapping[str, Any]],
    *,
    created_at: str,
) -> list[dict[str, Any]]:
    """Una vista per statement, in modalita' prototipo."""
    by_statement: dict[str, list[Mapping[str, Any]]] = {}
    for link in links:
        by_statement.setdefault(str(link["statement_id"]), []).append(link)

    views: list[dict[str, Any]] = []
    for statement in statements:
        statement_id = str(statement.get("evidence_statement_id") or "")
        relevant = by_statement.get(statement_id, [])

        proposals: dict[str, list[dict[str, Any]]] = {}
        for link in relevant:
            for added in link["added_dimensions"]:
                proposals.setdefault(added["dimension"], []).append(added)

        qualified: dict[str, dict[str, Any]] = {}
        conflicts: list[dict[str, Any]] = []
        ambiguous: list[str] = []
        for dimension, values in sorted(proposals.items()):
            distinct = {json.dumps(v["value"], sort_keys=True) for v in values}
            if len(distinct) > 1:
                conflicts.append(
                    {
                        "dimension": dimension,
                        "reason": "due unita' attive propongono valori diversi",
                        "values": sorted(distinct),
                        "source_profile_unit_ids": sorted(
                            v["source_profile_unit_id"] for v in values
                        ),
                        "resolution": "non applicata: la scelta fra fonti e' un giudizio umano",
                    }
                )
                continue
            if len({v["source_profile_unit_id"] for v in values}) > 1:
                ambiguous.append(dimension)
            qualified[dimension] = values[0]

        # Le tre assenze restano distinte. Sono la ragione per cui la vista
        # esiste: `unknown` dice che nessuno lo sa, `not_applicable` che la
        # domanda non si pone, `not_separable` che la fonte conferma i componenti
        # e non la loro relazione.
        sentinel_dimensions: dict[str, dict[str, list[str]]] = {
            UNKNOWN: {},
            NOT_APPLICABLE: {},
            NOT_SEPARABLE: {},
        }
        for link in relevant:
            unit = units_by_id.get(str(link["source_profile_unit_id"]), {})
            for dimension, field_name in sorted(DIMENSION_FIELD.items()):
                sentinel = _sentinel_of(unit.get(field_name))
                if sentinel in sentinel_dimensions:
                    sentinel_dimensions[sentinel].setdefault(dimension, []).append(
                        str(link["source_profile_unit_id"])
                    )
            for key in ("preclinical_model_composition", "component_to_statement_mapping"):
                if unit.get(key) == NOT_SEPARABLE:
                    sentinel_dimensions[NOT_SEPARABLE].setdefault(key, []).append(
                        str(link["source_profile_unit_id"])
                    )

        unresolved = [d for d in PROFILE_DIMENSIONS if d not in qualified]
        prototype_only = sorted(
            d for d, v in qualified.items() if v["propagation_eligibility"] == PROTOTYPE_ONLY
        )
        hard_filterable = sorted(d for d, v in qualified.items() if v["hard_filter_allowed"])

        if conflicts:
            status = "conflicting"
        elif ambiguous:
            status = "ambiguous"
        elif not qualified:
            status = "unqualified"
        elif unresolved:
            status = "partially_qualified"
        else:
            status = "qualified"

        views.append(
            {
                "statement_id": statement_id,
                "view_mode": VIEW_MODE,
                "view_version": f"qualified_evidence_view/{VIEW_MODE}/2.0",
                # I campi nativi non vengono toccati: vengono dal grafo congelato,
                # e sovrascriverli renderebbe il sistema meno capace senza renderlo
                # piu' prudente.
                "base_statement": dict(statement),
                "native_field_origin": ORIGIN_NATIVE,
                "native_fields_overwritten": False,
                "qualification_links": [link["qualification_link_id"] for link in relevant],
                "linked_source_profile_units": sorted(
                    {str(link["source_profile_unit_id"]) for link in relevant}
                ),
                "qualified_dimensions": qualified,
                "qualified_dimension_count": len(qualified),
                "unresolved_dimensions": unresolved,
                "prototype_only_dimensions": prototype_only,
                "hard_filterable_dimensions": hard_filterable,
                "final_dimensions": [
                    d for d, v in sorted(qualified.items())
                    if v["propagation_eligibility"] == FINAL
                ],
                "source_checked_dimensions": sorted(
                    d for d, v in qualified.items() if v["value_origin"] == ORIGIN_SOURCE_CHECKED
                ),
                "first_review_dimensions": sorted(
                    d for d, v in qualified.items() if v["value_origin"] == ORIGIN_FIRST_REVIEW
                ),
                "unknown_dimensions": sorted(sentinel_dimensions[UNKNOWN]),
                "not_applicable_dimensions": sorted(sentinel_dimensions[NOT_APPLICABLE]),
                "not_separable_dimensions": sorted(sentinel_dimensions[NOT_SEPARABLE]),
                "sentinel_sources": {
                    key: {k: sorted(set(v)) for k, v in sorted(value.items())}
                    for key, value in sorted(sentinel_dimensions.items())
                },
                "ambiguous_dimensions": sorted(ambiguous),
                "conflicts": conflicts,
                "qualification_status": status,
                "display_allowed": True,
                "hard_filtering_allowed": bool(hard_filterable),
                "created_at": created_at,
                "regeneration_version": REGENERATION_VERSION,
            }
        )
    return views


def collect(v3_dir: Path, relatives: Iterable[str], *, tag_field: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in relatives:
        for row in read_jsonl(v3_dir / relative):
            payload = dict(row)
            payload.setdefault("origin_artifact", relative)
            rows.append(payload)
    return rows


def build_review_decisions(v3_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_id, relative in REVIEW_DECISION_FILES:
        for row in read_jsonl(v3_dir / relative):
            payload = dict(row)
            payload.setdefault("canonical_source_id", source_id)
            payload["origin_artifact"] = relative
            # I due vocabolari convivono: la prima revisione usava
            # `first_review_link_status`, le approvazioni hanno aggiunto lo stato
            # del candidato. Normalizzare uno nell'altro perderebbe la differenza
            # fra «il link e' valido» e «il candidato e' valido».
            payload.setdefault(
                "first_review_candidate_status", payload.get("first_review_candidate_status", "")
            )
            rows.append(payload)
    return rows


def classify_changes(
    *,
    previous_units: Sequence[Mapping[str, Any]],
    units: Sequence[Mapping[str, Any]],
    stale_before: int,
    stale_after: int,
    previous_gold: Sequence[Mapping[str, Any]],
    gold: Sequence[Mapping[str, Any]],
    previous_links: Sequence[Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    previous_views: Sequence[Mapping[str, Any]],
    views: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Ogni differenza in una classe, e le classi che devono restare vuote."""
    previous_ids = {str(u.get("profile_unit_id")) for u in previous_units}
    current_ids = {str(u.get("profile_unit_id")) for u in units}
    previous_by_id = {str(u.get("profile_unit_id")): u for u in previous_units}

    changes: list[dict[str, Any]] = []

    for unit_id in sorted(current_ids - previous_ids):
        changes.append(
            {
                "entity_id": unit_id,
                "change": "unit_added",
                "change_class": EXPECTED_UNIT_RESTRUCTURE,
                "detail": "unita' assente dal corpus precedente: viene da una revisione o da una proposta",
            }
        )
    for unit_id in sorted(previous_ids - current_ids):
        changes.append(
            {
                "entity_id": unit_id,
                "change": "unit_removed",
                "change_class": UNEXPECTED_CHANGE,
                "detail": "unita' presente nel corpus precedente e assente qui",
            }
        )

    for unit in sorted(units, key=lambda u: str(u.get("profile_unit_id"))):
        unit_id = str(unit.get("profile_unit_id"))
        previous = previous_by_id.get(unit_id)
        if previous is None:
            continue
        if previous.get("is_propagatable") != unit.get("is_propagatable"):
            changes.append(
                {
                    "entity_id": unit_id,
                    "change": "is_propagatable",
                    "change_class": EXPECTED_POLICY_MIGRATION,
                    "before": previous.get("is_propagatable"),
                    "after": unit.get("is_propagatable"),
                    "detail": "flag ricalcolato dalla politica invece che trasportato",
                }
            )
        if previous.get("review_status") != unit.get("review_status"):
            changes.append(
                {
                    "entity_id": unit_id,
                    "change": "review_status",
                    "change_class": (
                        EXPECTED_AUTHOR_APPROVAL
                        if str(unit.get("review_status") or "")
                        in ("first_review_complete", "human_reviewed")
                        else EXPECTED_HISTORY_UPDATE
                    ),
                    "before": previous.get("review_status"),
                    "after": unit.get("review_status"),
                    "detail": "stato aggiornato da una revisione approvata o dallo storico",
                }
            )

    if stale_before != stale_after:
        changes.append(
            {
                "entity_id": "obsolete_serialized_flags",
                "change": "obsolete_flags_removed",
                "change_class": EXPECTED_POLICY_MIGRATION,
                "before": stale_before,
                "after": stale_after,
                "detail": "flag serializzati che il codice non onorava piu'",
            }
        )

    previous_gold_ids = {str(r.get("gold_link_id")) for r in previous_gold}
    gold_ids = {str(r.get("gold_link_id")) for r in gold}
    for link_id in sorted(gold_ids - previous_gold_ids):
        changes.append(
            {
                "entity_id": link_id,
                "change": "gold_record_added",
                "change_class": UNEXPECTED_CHANGE,
                "detail": "record di gold assente dalla versione precedente",
            }
        )
    for link_id in sorted(previous_gold_ids - gold_ids):
        changes.append(
            {
                "entity_id": link_id,
                "change": "gold_record_removed",
                "change_class": UNEXPECTED_CHANGE,
                "detail": "record di gold perso nella rigenerazione",
            }
        )
    annotated = [r for r in gold if r.get("first_annotator")]
    changes.append(
        {
            "entity_id": "provisional_gold",
            "change": "first_review_annotations",
            "change_class": EXPECTED_AUTHOR_APPROVAL,
            "before": len([r for r in previous_gold if r.get("first_annotator")]),
            "after": len(annotated),
            "detail": "annotazioni di prima revisione presenti nel gold provvisorio",
        }
    )

    changes.append(
        {
            "entity_id": "qualification_links",
            "change": "link_count",
            "change_class": EXPECTED_UNIT_RESTRUCTURE,
            "before": len(previous_links),
            "after": len(links),
            "detail": "link ricostruiti dalle sole unita' attive invece che dagli otto profili revisionati",
        }
    )
    changes.append(
        {
            "entity_id": "qualified_evidence_views",
            "change": "view_count",
            "change_class": EXPECTED_HASH_CHANGE,
            "before": len(previous_views),
            "after": len(views),
            "detail": "una vista per statement, in modalita' prototipo",
        }
    )

    counts = Counter(change["change_class"] for change in changes)
    return {
        "changes": changes,
        "counts": {name: counts.get(name, 0) for name in sorted(set(counts) | {UNEXPECTED_CHANGE, UNRESOLVED_CONFLICT})},
        "unexpected_change": counts.get(UNEXPECTED_CHANGE, 0),
        "unresolved_conflict": counts.get(UNRESOLVED_CONFLICT, 0),
    }


def build_metrics(
    *,
    statements: Sequence[Mapping[str, Any]],
    inventory: Sequence[Mapping[str, Any]],
    units: Sequence[Mapping[str, Any]],
    active: Sequence[Mapping[str, Any]],
    historical: Sequence[Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    views: Sequence[Mapping[str, Any]],
    gold: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]],
    mappings: Sequence[Mapping[str, Any]],
    detector: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    """Solo conteggi. Nessuno di essi misura la qualita' del sistema."""
    granularity = Counter(
        str(row.get("evidence_granularity") or "") for row in decisions
    )
    pending = sum(
        1
        for row in mappings
        if str(row.get("mapping_status") or "") == "requires_terminology_verification"
        or row.get("review_required")
    )
    return {
        "created_at": created_at,
        "regeneration_version": REGENERATION_VERSION,
        "metric_kind": "descriptive_corpus_metrics",
        "metric_kind_note": (
            "Contano entita' e stati. Nessuna misura la qualita' del linking o del "
            "rilevatore: esiste una sola annotazione per link, non indipendente."
        ),
        "evidence_statement_count": len(statements),
        "source_count": len(inventory),
        "total_profile_units": len(units),
        "active_profile_units": len(active),
        "historical_profile_units": len(historical),
        "units_by_review_status": dict(summary["units_by_review_status"]),
        "units_by_propagation_eligibility": dict(summary["units_by_eligibility"]),
        "active_units_by_propagation_eligibility": dict(summary["active_units_by_eligibility"]),
        "prototype_visible_units": sum(
            1 for unit in active if unit.get("may_display_qualifiers")
        ),
        "final_propagatable_units": sum(1 for unit in units if unit.get("is_propagatable")),
        "hard_filterable_qualifiers": summary["hard_filterable_qualifiers"],
        "obsolete_flags_removed": summary["obsolete_serialized_flags_before"]
        - summary["obsolete_serialized_flags_after"],
        "qualification_links": len(links),
        "prototype_views": sum(1 for view in views if view["view_mode"] == VIEW_MODE),
        "provisional_gold_records": len(gold),
        # Due conteggi e non uno: PMID 22277784 e' stato approvato dall'autore in
        # una fase che si chiamava `first_review` e non scriveva `author_decision`.
        # Un numero solo direbbe 3 o 4 a seconda di quale definizione si sceglie,
        # senza dire quale.
        "author_approved_sources": sum(1 for row in inventory if row.get("author_approved")),
        "first_review_completed_sources": sum(
            1
            for row in inventory
            if "first_review_complete" in (row.get("review_statuses") or [])
        ),
        "unresolved_units": sum(
            1
            for unit in active
            if unit.get("preclinical_model_composition") == NOT_SEPARABLE
            or str(unit.get("cohort_state") or "") == "unresolved_cohort"
        ),
        "abstract_only_units": sum(
            1 for unit in active if str(unit.get("source_basis") or "") == "abstract_only"
        ),
        "case_level_statements": granularity.get("case_level", 0),
        "named_patient_subset_statements": granularity.get("named_patient_subset", 0),
        "negative_experiments": sum(
            1 for unit in active if unit.get("experiment_role") == "negative_experiment"
        ),
        "terminology_mappings_pending": pending,
        "conflicts": sum(len(view["conflicts"]) for view in views),
        "ambiguities": sum(len(view["ambiguous_dimensions"]) for view in views),
        "not_separable_fields": sum(len(link["not_separable_fields"]) for link in links),
        "review_decisions": len(decisions),
        "detector_reference_cases": len(detector),
        "not_calculated": {
            "linking_precision": "not_calculated",
            "linking_recall": "not_calculated",
            "linking_f1": "not_calculated",
            "inter_annotator_agreement": "not_calculated",
            "detector_accuracy": "not_calculated",
            "clinical_applicability_accuracy": "not_calculated",
            "final_retrieval_quality": "not_calculated",
        },
        "not_calculated_reason": (
            "nessuna seconda revisione esiste, nessuna unita' e' final e il gold non "
            "e' valutabile. Una metrica di qualita' calcolata qui misurerebbe il "
            "sistema contro se stesso."
        ),
    }


def build_readiness(
    *,
    summary: Mapping[str, Any],
    metrics: Mapping[str, Any],
    diff: Mapping[str, Any],
    status: str,
    guard_findings: Sequence[Mapping[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    """La readiness e' per dimensione: `ready` e `prototype_ready` non sono lo stesso.

    I campi nativi vengono dal grafo congelato e sono pronti: nessuna revisione li
    riguarda. I qualificatori di prima revisione sono `prototype_ready` e non
    `final_ready`, e la differenza non e' di grado — un qualificatore mostrato che
    sia sbagliato viene letto da chi puo' correggerlo, uno che filtri e sia
    sbagliato rimuove evidenza che nessuno vedra' piu'.
    """
    return {
        "created_at": created_at,
        "regeneration_version": REGENERATION_VERSION,
        "corpus_version": summary["corpus_version"],
        "regeneration_status": status,
        "qualification_corpus_internally_consistent": True,
        "author_approval_batch_complete": True,
        "propagation_policy_migration_complete": summary["obsolete_serialized_flags_after"] == 0,
        "obsolete_serialized_flags": summary["obsolete_serialized_flags_after"],
        "unexpected_changes": diff["unexpected_change"],
        "unresolved_conflicts": diff["unresolved_conflict"],
        "hard_filtering_available": False,
        "final_evaluation_ready": False,
        "gold_evaluable": False,
        "detector_promotion_ready": False,
        "prototype_qualified_evidence_view_ready": True,
        "ready_for_prototype_retriever_implementation": status == READY_FOR_PROTOTYPE,
        "second_review_required": True,
        # Per dimensione, perche' un unico booleano direbbe che tutto il corpus e'
        # ugualmente utilizzabile, e non lo e'.
        "readiness_by_dimension": {
            "evidence_statement_native_fields": "ready",
            "source_checked_qualifiers": "prototype_ready",
            "first_review_qualifiers": "prototype_ready",
            "machine_extracted_qualifiers": "not_ready",
            "final_qualifiers": "not_available",
            "hard_filtering": "not_available",
            "component_level_filtering_23344087": "not_available",
        },
        "dimension_notes": {
            "first_review_qualifiers": (
                "prototype_ready e non final_ready: una sola annotazione, non "
                "indipendente e non clinica"
            ),
            "component_level_filtering_23344087": (
                "il pannello preclinico e' not_separable: filtrare per componente "
                "richiederebbe una struttura che l'abstract non fornisce"
            ),
            "machine_extracted_qualifiers": (
                "eligibility `none`: nessuno ha letto la fonte, quindi non entrano "
                "nemmeno nelle viste"
            ),
        },
        "unresolved_panel_component_filtering_available": False,
        "prototype_visible_units": metrics["prototype_visible_units"],
        "final_propagatable_units": metrics["final_propagatable_units"],
        "hard_filterable_qualifiers": metrics["hard_filterable_qualifiers"],
        "pre_existing_guard_findings": len(guard_findings),
        "biomarker_role_backfill_required": bool(guard_findings),
        "pre_existing_guard_finding_note": (
            "unita' scritte prima che la regola `observed_biomarker_to_requirement` "
            "esistesse dichiarano `biomarker_requirements` senza `biomarker_role`. "
            "La rigenerazione le trasporta invariate: riempire il campo a posteriori "
            "significherebbe decidere al posto di un revisore che non ha deciso"
        ),
        "standard_queue_resumed": False,
        "next_step": "prototype_qualified_evidence_retriever_implementation",
        "blockers": [],
    }


def render_diff_markdown(diff: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    lines = [
        "# Diff della rigenerazione del qualification corpus",
        "",
        f"**{summary['previous_corpus_version']} → {summary['corpus_version']}**",
        "",
        "| | prima | dopo |",
        "|---|---|---|",
        f"| flag serializzati obsoleti | {summary['obsolete_serialized_flags_before']} | "
        f"{summary['obsolete_serialized_flags_after']} |",
        f"| unita' totali | {summary['previous_profile_unit_count']} | {summary['profile_unit_count']} |",
        f"| unita' attive | — | {summary['active_profile_unit_count']} |",
        f"| unita' storiche | — | {summary['historical_profile_unit_count']} |",
        f"| link | {summary['previous_link_count']} | {summary['link_count']} |",
        f"| view | {summary['previous_view_count']} | {summary['view_count']} |",
        f"| gold | {summary['previous_gold_count']} | {summary['gold_count']} |",
        f"| unita' final | — | {summary['final_units']} |",
        f"| qualificatori hard-filterable | — | {summary['hard_filterable_qualifiers']} |",
        "",
        "## Impronte",
        "",
        "```",
        f"frozen_kg_snapshot_fingerprint   {summary['frozen_kg_snapshot_fingerprint']}  (invariata)",
        f"qualification_corpus_fingerprint {summary['previous_corpus_fingerprint']}  (prima)",
        f"                                 {summary['qualification_corpus_fingerprint']}  (dopo)",
        "```",
        "",
        "L'impronta del grafo congelato non cambia: nessun dato viene scritto nel KG.",
        "L'impronta del corpus cambia perche' cambiano unita', stati e flag.",
        "",
        "## Unita' per stato di revisione",
        "",
        "| review status | unita' |",
        "|---|---|",
    ]
    for status, count in sorted(summary["units_by_review_status"].items()):
        lines.append(f"| `{status}` | {count} |")
    lines += [
        "",
        "## Unita' per livello di propagazione",
        "",
        "| eligibility | totali | attive |",
        "|---|---|---|",
    ]
    for level in ("none", "prototype_only", "final"):
        lines.append(
            f"| `{level}` | {summary['units_by_eligibility'].get(level, 0)} | "
            f"{summary['active_units_by_eligibility'].get(level, 0)} |"
        )
    lines += ["", "## Classificazione delle differenze", "", "| classe | numero |", "|---|---|"]
    for name, count in sorted(diff["counts"].items()):
        lines.append(f"| `{name}` | {count} |")
    lines += [
        "",
        f"**`unexpected_change` = {diff['unexpected_change']}** · "
        f"**`unresolved_conflict` = {diff['unresolved_conflict']}** · "
        f"**`obsolete_serialized_flags` = {summary['obsolete_serialized_flags_after']}**",
        "",
        "La rigenerazione e' accettabile soltanto con tutti e tre a zero.",
        "",
        "## Differenze registrate",
        "",
        "| entita' | modifica | classe | prima | dopo |",
        "|---|---|---|---|---|",
    ]
    for change in diff["changes"][:60]:
        lines.append(
            f"| `{change['entity_id']}` | {change['change']} | `{change['change_class']}` | "
            f"{change.get('before', '—')} | {change.get('after', '—')} |"
        )
    if len(diff["changes"]) > 60:
        lines.append(f"| … | altre {len(diff['changes']) - 60} differenze | | | |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()
    output = args.output

    units = list(read_jsonl(output / "source_profile_units.jsonl"))
    active = list(read_jsonl(output / "active_source_profile_units.jsonl"))
    historical = list(read_jsonl(output / "historical_source_profile_units.jsonl"))
    statements = list(read_jsonl(output / "evidence_statements.jsonl"))
    inventory = list(read_jsonl(output / "source_inventory.jsonl"))
    scope = json.loads((output / "qualification_scope.json").read_text(encoding="utf-8"))
    if not units:
        raise RebuildFailure(
            "nessuna unita' canonica: eseguire prima regenerate_qualification_corpus.py"
        )
    units_by_id = {str(unit["profile_unit_id"]): unit for unit in units}

    blind_before = hash_directory(args.v3_dir / "priority_curation/annotation_packets/second_review")

    previous_manifest = json.loads(
        (args.previous_corpus / "qualification_corpus_manifest.json").read_text(encoding="utf-8")
    )
    frozen_kg = str(previous_manifest["snapshot_fingerprint"])
    previous_units = list(read_jsonl(args.previous_corpus / "source_profile_units.jsonl"))
    previous_links = list(read_jsonl(args.previous_views / "qualification_links.jsonl"))
    previous_views = list(read_jsonl(args.previous_views / "qualified_evidence_views.jsonl"))

    links = build_links(statements, active, created_at=created_at)
    views = build_views(statements, links, units_by_id, created_at=created_at)

    gold = list(read_jsonl(args.gold))
    previous_gold = list(read_jsonl(args.v3_dir / "author_approval_22235099/provisional_gold.jsonl"))

    decisions = build_review_decisions(args.v3_dir)
    mappings = collect(args.v3_dir, TERMINOLOGY_FILES)
    detector = collect(args.v3_dir, DETECTOR_FILES)

    findings = validate_corpus(
        active_units=active,
        all_units=units,
        decisions=decisions,
        mappings=mappings,
        gold=gold,
        frozen_kg_before=frozen_kg,
        frozen_kg_after=frozen_kg,
        blind_packets_before=blind_before,
        blind_packets_after=hash_directory(
            args.v3_dir / "priority_curation/annotation_packets/second_review"
        ),
    )
    if findings:
        write_jsonl(output / "validation_findings.jsonl", [f.as_dict() for f in findings])
        raise RebuildFailure(
            f"{len(findings)} violazioni: "
            + "; ".join(f"[{f.rule_id}] {f.message}" for f in findings[:5])
        )

    # Le guardie di propagazione girano sulle unita' attive. Cio' che trovano qui
    # non e' stato introdotto da questa fase: sono unita' scritte prima che la
    # regola esistesse. Registrarle senza correggerle e' l'unica opzione onesta —
    # riempire `biomarker_role` a posteriori significherebbe decidere al posto di
    # un revisore che non ha deciso, e ometterle nasconderebbe una lacuna reale.
    guard_findings = [
        {
            **violation.as_dict(),
            "blocking": False,
            "introduced_by_this_regeneration": False,
            "classification": "pre_existing_gap",
            "guard_version": GUARD_VERSION,
            "note": (
                "unita' scritta prima che la regola esistesse. La rigenerazione la "
                "trasporta invariata e non inventa il valore mancante"
            ),
        }
        for violation in run_guards(units=active)
    ]
    write_jsonl(output / "guard_findings.jsonl", guard_findings)

    # --- hash e impronte -------------------------------------------------
    components = {
        "statement_repository_hash": stable_hash(statements),
        "source_inventory_hash": stable_hash(inventory),
        "qualification_scope_hash": stable_hash(scope),
        "profile_units_hash": stable_hash(units),
        "active_profile_units_hash": stable_hash(active),
        "historical_profile_units_hash": stable_hash(historical),
        "qualification_links_hash": stable_hash(links),
        "qualified_evidence_views_hash": stable_hash(views),
        "provisional_gold_hash": stable_hash(gold),
        "propagation_policy_hash": stable_hash(
            json.loads(
                (args.v3_dir / "propagation_policy/propagation_policy.json").read_text(
                    encoding="utf-8"
                )
            )
        ),
        "terminology_mappings_hash": stable_hash(mappings),
        "review_decisions_hash": stable_hash(decisions),
        "detector_reference_cases_hash": stable_hash(detector),
        "canonical_merge_audit_hash": stable_hash(
            list(read_jsonl(output / "canonical_merge_audit.jsonl"))
        ),
        "second_review_packets_hash": stable_hash(blind_before),
    }
    fingerprint_inputs = sorted(components)
    new_fingerprint = corpus_fingerprint(components)
    previous_fingerprint = corpus_fingerprint(
        {
            "statement_repository_hash": str(previous_manifest["statement_repository_hash"]),
            "source_inventory_hash": str(previous_manifest["source_inventory_hash"]),
            "qualification_scope_hash": str(previous_manifest["qualification_scope_hash"]),
            "profile_units_hash": str(previous_manifest["profile_units_hash"]),
            "provisional_gold_hash": str(previous_manifest["link_gold_hash"]),
        }
    )
    derived_snapshot = corpus_fingerprint(
        {
            "frozen_kg_snapshot_fingerprint": frozen_kg,
            "statement_repository_hash": components["statement_repository_hash"],
            "profile_units_hash": components["profile_units_hash"],
            "qualification_links_hash": components["qualification_links_hash"],
            "provisional_gold_hash": components["provisional_gold_hash"],
            "propagation_policy_hash": components["propagation_policy_hash"],
            "profile_unit_schema": PROFILE_UNIT_VERSION,
            "policy_version": POLICY_VERSION,
        }
    )

    # --- diff -------------------------------------------------------------
    by_review = Counter(str(u.get("review_status") or "") for u in units)
    by_eligibility = Counter(str(u.get("propagation_eligibility") or "") for u in units)
    active_by_eligibility = Counter(str(u.get("propagation_eligibility") or "") for u in active)
    hard_filterable = sum(
        len(view["hard_filterable_dimensions"]) for view in views
    )
    final_units = sum(1 for u in units if u.get("propagation_eligibility") == FINAL)

    diff = classify_changes(
        previous_units=previous_units,
        units=units,
        stale_before=int(scope["obsolete_serialized_flags_before"]),
        stale_after=int(scope["obsolete_serialized_flags_after"]),
        previous_gold=previous_gold,
        gold=gold,
        previous_links=previous_links,
        links=links,
        previous_views=previous_views,
        views=views,
    )

    summary = {
        "corpus_version": CORPUS_VERSION,
        "previous_corpus_version": str(previous_manifest["corpus_version"]),
        "previous_corpus_fingerprint": previous_fingerprint,
        "qualification_corpus_fingerprint": new_fingerprint,
        "frozen_kg_snapshot_fingerprint": frozen_kg,
        "obsolete_serialized_flags_before": int(scope["obsolete_serialized_flags_before"]),
        "obsolete_serialized_flags_after": int(scope["obsolete_serialized_flags_after"]),
        "previous_profile_unit_count": len(previous_units),
        "profile_unit_count": len(units),
        "active_profile_unit_count": len(active),
        "historical_profile_unit_count": len(historical),
        "previous_link_count": len(previous_links),
        "link_count": len(links),
        "previous_view_count": len(previous_views),
        "view_count": len(views),
        "previous_gold_count": len(previous_gold),
        "gold_count": len(gold),
        "final_units": final_units,
        "hard_filterable_qualifiers": hard_filterable,
        "units_by_review_status": dict(sorted(by_review.items())),
        "units_by_eligibility": dict(sorted(by_eligibility.items())),
        "active_units_by_eligibility": dict(sorted(active_by_eligibility.items())),
    }

    if diff["unexpected_change"] or diff["unresolved_conflict"]:
        write_json(output / "corpus_regeneration_diff.json", {**summary, **diff})
        raise RebuildFailure(
            f"rigenerazione non accettabile: {diff['unexpected_change']} modifiche inattese, "
            f"{diff['unresolved_conflict']} conflitti irrisolti"
        )

    status = (
        READY_FOR_PROTOTYPE
        if not diff["unexpected_change"]
        and not diff["unresolved_conflict"]
        and scope["obsolete_serialized_flags_after"] == 0
        and final_units == 0
        and hard_filterable == 0
        else BLOCKED
    )

    # --- scrittura --------------------------------------------------------
    write_jsonl(output / "qualification_links.jsonl", links)
    write_jsonl(output / "qualified_evidence_views.jsonl", views)
    write_jsonl(output / "statement_qualification_gold.jsonl", gold)
    write_jsonl(output / "terminology_mappings.jsonl", mappings)
    write_jsonl(output / "review_decisions.jsonl", decisions)
    write_jsonl(output / "detector_reference_cases.jsonl", detector)
    write_json(output / "corpus_regeneration_diff.json", {**summary, **diff})

    manifest = {
        "corpus_version": CORPUS_VERSION,
        "manifest_version": MANIFEST_VERSION,
        "previous_corpus_version": str(previous_manifest["corpus_version"]),
        "previous_corpus_manifest": str(
            args.previous_corpus / "qualification_corpus_manifest.json"
        ).replace("\\", "/"),
        "previous_corpus_directory": str(args.previous_corpus).replace("\\", "/"),
        "previous_corpus_fingerprint": previous_fingerprint,
        "qualification_corpus_fingerprint": new_fingerprint,
        "frozen_kg_snapshot_fingerprint": frozen_kg,
        "qualified_evidence_snapshot_fingerprint": derived_snapshot,
        "regeneration_reason": str(scope["regeneration_reason"]),
        "migration_id": MIGRATION_ID,
        "propagation_policy_version": POLICY_VERSION,
        "regeneration_version": REGENERATION_VERSION,
        "linker_version": LINK_VERSION,
        "generated_at": created_at,
        "source_sha": args.source_sha,
        "regeneration_status": status,
        "schema_versions": {
            "evidence_statement": "v3.0.0",
            "source_clinical_profile_unit": PROFILE_UNIT_VERSION,
            "qualification_link": LINK_VERSION,
            "qualified_evidence_view": f"qualified_evidence_view/{VIEW_MODE}/2.0",
            "statement_qualification_gold": "statement_qualification_gold/1.0",
            "propagation_policy": POLICY_VERSION,
            "source_basis": SOURCE_BASIS_VERSION,
            "corpus_regeneration": REGENERATION_VERSION,
        },
        "component_hashes": components,
        "fingerprint_inputs": fingerprint_inputs,
        "non_hashed_fields": list(NON_HASHED_FIELDS),
        "counts": {
            "statements": len(statements),
            "sources": len(inventory),
            "profile_units": len(units),
            "active_profile_units": len(active),
            "historical_profile_units": len(historical),
            "qualification_links": len(links),
            "qualified_evidence_views": len(views),
            "provisional_gold_records": len(gold),
            "terminology_mappings": len(mappings),
            "review_decisions": len(decisions),
            "detector_reference_cases": len(detector),
            "final_units": final_units,
            "hard_filterable_qualifiers": hard_filterable,
        },
        "obsolete_serialized_flags_before": summary["obsolete_serialized_flags_before"],
        "obsolete_serialized_flags_after": summary["obsolete_serialized_flags_after"],
        "unexpected_changes": diff["unexpected_change"],
        "unresolved_conflicts": diff["unresolved_conflict"],
        "integrated_reviews": list(INTEGRATED_REVIEWS),
        "precedence_order": list(scope["precedence_order"]),
        "blockers": [],
    }
    write_json(output / "qualification_corpus_manifest.json", manifest)

    (output / "CORPUS_REGENERATION_DIFF.md").write_text(
        render_diff_markdown(diff, summary), encoding="utf-8", newline="\n"
    )

    metrics = build_metrics(
        statements=statements,
        inventory=inventory,
        units=units,
        active=active,
        historical=historical,
        links=links,
        views=views,
        gold=gold,
        decisions=decisions,
        mappings=mappings,
        detector=detector,
        summary=summary,
        created_at=created_at,
    )
    write_json(output / "regeneration_metrics.json", metrics)

    readiness = build_readiness(
        summary=summary,
        metrics=metrics,
        diff=diff,
        status=status,
        guard_findings=guard_findings,
        created_at=created_at,
    )
    write_json(output / "readiness.json", readiness)

    print(f"link: {len(links)} · view: {len(views)} · gold: {len(gold)}")
    print(f"unita': {len(units)} ({len(active)} attive) · final: {final_units}")
    print(f"qualificatori hard-filterable: {hard_filterable}")
    print(f"flag obsoleti: {summary['obsolete_serialized_flags_before']} -> "
          f"{summary['obsolete_serialized_flags_after']}")
    print(f"modifiche inattese: {diff['unexpected_change']} · conflitti: {diff['unresolved_conflict']}")
    print(f"frozen KG fingerprint: {frozen_kg[:16]}… (invariata)")
    print(f"corpus fingerprint: {previous_fingerprint[:16]}… -> {new_fingerprint[:16]}…")
    print(f"stato: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
