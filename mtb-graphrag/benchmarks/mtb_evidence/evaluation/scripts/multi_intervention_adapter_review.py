"""Audit read-only della perdita multi-intervento nell'adapter V2 -> V3."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.pipeline.evidence.adapter_metrics import compatible_records
from backend.pipeline.evidence.qualified_retrieval_query import (
    MODE_NATIVE_ONLY,
    build_query,
)
from backend.pipeline.evidence.qualified_retriever import QualifiedEvidenceRetriever
from backend.pipeline.evidence.v2_adapter import adapt_record, record_identifier
from benchmarks.mtb_evidence.evaluation.scripts.candidate_coverage_audit import (
    EXPECTED_AUTHOR_APPROVAL_HASH,
    EXPECTED_CORPUS_DIRECTORY_HASH,
    EXPECTED_GOLD_HASH,
    EXPECTED_SCORING_FILE_HASH,
    EXPECTED_SECOND_REVIEW_HASH,
    _aggregate,
)
from benchmarks.mtb_evidence.evaluation.scripts.v2_v3a_exploratory import (
    EXPECTED_CORPUS_FINGERPRINT,
    EXPECTED_FROZEN_KG_FINGERPRINT,
    EXPECTED_GOLD_FILES,
    EXPECTED_SCORING_HASH,
    _bundle_guard,
)
from benchmarks.mtb_evidence.pilot.audit_lib.normalize import norm_drug


REVIEW_VERSION = "multi-intervention-adapter-review/1.0"
SOURCE_SHA = "6d784671fad4fdee1759e0ea316154ee2a41b638"
TARGET_BRANCH = "eval/v3-multi-intervention-adapter-review"
EXPECTED_REPOSITORY_HASH = (
    "c6fdc1a3f0a0b5cd7187e7d4c702d20188538957954386ec8f091fe33ca07749"
)
EXPECTED_ADAPTER_HASH = (
    "5eb000fe2825138a92bec98cd9c6b4c41c6a547c6964cddf701f303ffb953aac"
)
EXPECTED_RETRIEVER_HASH = (
    "3b80765830e67e8d3bd253afb0b08980ed934edb123b8edc745e93d6175f78e7"
)
EXPECTED_FROZEN_V2_SERIALIZATION_HASH = (
    "2a22b04abbfcff831b7123165e806cdb49d80fd557b2517d8743f72b010087de"
)
EXPECTED_ADAPTER_OUTPUT_HASH = (
    "b5e50a8a1bad72a53357d97b45d6002c4e507a60f5275e217656e60cd1caf0e4"
)
EXPECTED_CANDIDATE_AUDIT_HASH = (
    "43396526a701ba1ec7f4e1f0bbc498a798ca02fd9600deedf7ef1ed442ca7273"
)
EXPECTED_CONJUNCTIVE_FIX_HASH = (
    "cf69886100af3f25f06426ad81a3ae811f9c1e76a08c240b5e2c86f41d88638d"
)
EXPECTED_DISEASE_REVIEW_HASH = (
    "1084763a50e63cfe4c19b72defca5c73788a826f5227a0fd4378c7bc1020b71c"
)
EXPECTED_ALIAS_FIX_HASH = (
    "7455f7f9265787f6bce4c87781f924a53962b140d2ad322a375084eab77875da"
)
EXPECTED_CANDIDATE_COUNTS = {
    "PILOT-A2-ALK-G1202R": 9,
    "PILOT-C1-EGFR-L858R-CONTEXT": 32,
    "PILOT-K1-FGFR2-iCCA": 1,
    "PILOT-N1-RMI2-SNAPSHOT": 0,
}
QUERY_LABELS = {
    "PILOT-A2-ALK-G1202R:qualified-retrieval": "PILOT-A2-ALK-G1202R",
    "PILOT-C1-EGFR-L858R-CONTEXT:qualified-retrieval": (
        "PILOT-C1-EGFR-L858R-CONTEXT"
    ),
    "PILOT-K1-FGFR2-iCCA:qualified-retrieval": "PILOT-K1-FGFR2-iCCA",
    "PILOT-N1-RMI2-SNAPSHOT:qualified-retrieval": "PILOT-N1-RMI2-SNAPSHOT",
}

# I dati strutturati mostrano due archi farmaco ma non distinguono regimen,
# braccio o risultato separato. Etichettarli come combinazione sarebbe una
# decisione documentale; rimangono pertanto irrisolti.
REGIMEN_AMBIGUOUS_IDS = {
    "evidence:11240",
    "evidence:12131",
    "evidence:12156",
}


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(_json_bytes(value))


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.write_bytes(_jsonl_bytes(rows))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_key(value: str) -> tuple[int, str]:
    suffix = value.rsplit(":", 1)[-1]
    return (int(suffix), value) if suffix.isdigit() else (10**12, value)


def _drug(record: Mapping[str, Any]) -> str:
    return str(record.get("drug") or record.get("drug_name") or "").strip()


def _normalized_drug(record: Mapping[str, Any]) -> str:
    return norm_drug(_drug(record)).strip()


def _sources(record: Mapping[str, Any]) -> list[str]:
    raw = record.get("citation_id") or record.get("citation_ids") or []
    if isinstance(raw, str):
        raw = [raw]
    flattened: list[str] = []
    for value in raw:
        values = value if isinstance(value, list) else [value]
        flattened.extend(str(item) for item in values if item not in (None, ""))
    return sorted(set(flattened))


def _load_adapter_rows(
    root: Path, *, reverse_inputs: bool = False
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    audit = root / "benchmarks/mtb_evidence/pilot/audit"
    case_dirs = sorted(item for item in audit.iterdir() if item.is_dir())
    if reverse_inputs:
        case_dirs.reverse()
    for case_dir in case_dirs:
        raw_rows = _read_jsonl(case_dir / "raw_records.jsonl")
        if reverse_inputs:
            raw_rows.reverse()
        for outer_position, outer in enumerate(raw_rows):
            record = outer.get("record") if isinstance(outer, Mapping) else None
            if not isinstance(record, Mapping) or not compatible_records([record]):
                continue
            rows.append(
                {
                    "case_id": case_dir.name,
                    "traversal": str(outer.get("query") or ""),
                    "record_index": outer.get("record_index"),
                    "outer_position": outer_position,
                    "record": dict(record),
                }
            )
    return rows


def _statements(root: Path) -> dict[str, dict[str, Any]]:
    path = (
        root
        / "benchmarks/mtb_evidence/evaluation/results/adapter_v1"
        / "evidence_statements.jsonl"
    )
    output: dict[str, dict[str, Any]] = {}
    for statement in _read_jsonl(path):
        for graph_id in statement["provenance"]["graph_record_ids"]:
            output[str(graph_id)] = statement
    return output


def _corpus_statement_ids(root: Path) -> set[str]:
    path = (
        root
        / "benchmarks/mtb_evidence/v3/qualification_corpus_v2"
        / "evidence_statements.jsonl"
    )
    return {str(row["evidence_statement_id"]) for row in _read_jsonl(path)}


def _qualification_links(root: Path) -> dict[str, list[dict[str, Any]]]:
    path = (
        root
        / "benchmarks/mtb_evidence/v3/qualification_corpus_v2"
        / "qualification_links.jsonl"
    )
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _read_jsonl(path):
        output[str(row["statement_id"])].append(row)
    return output


def _candidate_counts(root: Path) -> dict[str, int]:
    retriever = QualifiedEvidenceRetriever.from_corpus(
        root / "benchmarks/mtb_evidence/v3/qualification_corpus_v2",
        scoring_config_path=(
            root / "backend/pipeline/evidence/qualified_retriever_scoring_config.json"
        ),
    )
    queries = _read_jsonl(
        root
        / "benchmarks/mtb_evidence/v3/qualified_retriever_prototype/queries.jsonl"
    )
    counts: dict[str, int] = {}
    for payload in queries:
        payload = dict(payload)
        payload["retrieval_mode"] = MODE_NATIVE_ONLY
        payload["top_k"] = 500
        query = build_query(payload)
        result = retriever.retrieve(query)
        counts[QUERY_LABELS[query.query_id]] = len(result.all_results)
    return dict(sorted(counts.items()))


def _integrity(root: Path, gold_bundle: Path) -> dict[str, Any]:
    retriever_files = [
        root / "backend/pipeline/evidence" / name
        for name in (
            "qualified_retriever.py",
            "qualified_retrieval_query.py",
            "qualified_retrieval_result.py",
            "qualified_retrieval_policy.py",
            "qualified_retrieval_errors.py",
            "qualified_retrieval_scoring.py",
            "qualified_disease_matching.py",
        )
    ]
    paths: dict[str, Sequence[Path]] = {
        "qualification_corpus": [
            root / "benchmarks/mtb_evidence/v3/qualification_corpus_v2"
        ],
        "retriever": retriever_files,
        "frozen_v2_serialization": sorted(
            (
                root / "benchmarks/mtb_evidence/pilot/audit"
            ).glob("*/normalized_records.jsonl")
        ),
        "adapter_outputs": [
            root / "benchmarks/mtb_evidence/evaluation/results/adapter_v1"
        ],
        "second_review_packets": [
            root
            / "benchmarks/mtb_evidence/v3/priority_curation/annotation_packets"
            / "second_review"
        ],
        "candidate_coverage_audit": [
            root / "benchmarks/mtb_evidence/v3/candidate_coverage_audit"
        ],
        "conjunctive_biomarker_fix": [
            root / "benchmarks/mtb_evidence/v3/conjunctive_biomarker_fix"
        ],
        "disease_normalization_review": [
            root / "benchmarks/mtb_evidence/v3/disease_normalization_review"
        ],
        "verified_disease_alias_fix": [
            root / "benchmarks/mtb_evidence/v3/verified_disease_alias_fix"
        ],
    }
    expected = {
        "qualification_corpus": EXPECTED_CORPUS_DIRECTORY_HASH,
        "retriever": EXPECTED_RETRIEVER_HASH,
        "frozen_v2_serialization": EXPECTED_FROZEN_V2_SERIALIZATION_HASH,
        "adapter_outputs": EXPECTED_ADAPTER_OUTPUT_HASH,
        "second_review_packets": EXPECTED_SECOND_REVIEW_HASH,
        "candidate_coverage_audit": EXPECTED_CANDIDATE_AUDIT_HASH,
        "conjunctive_biomarker_fix": EXPECTED_CONJUNCTIVE_FIX_HASH,
        "disease_normalization_review": EXPECTED_DISEASE_REVIEW_HASH,
        "verified_disease_alias_fix": EXPECTED_ALIAS_FIX_HASH,
    }
    values: dict[str, Any] = {}
    for name, members in paths.items():
        value = _aggregate(root, members)
        if value["aggregate_sha256"] != expected[name]:
            raise RuntimeError(
                f"{name} hash mismatch: {value['aggregate_sha256']} != {expected[name]}"
            )
        values[name] = value
    repository = root / "backend/pipeline/evidence/repository.py"
    adapter = root / "backend/pipeline/evidence/v2_adapter.py"
    config = root / "backend/pipeline/evidence/qualified_retriever_scoring_config.json"
    for label, path, expected_hash in (
        ("evidence_statement_repository", repository, EXPECTED_REPOSITORY_HASH),
        ("v2_adapter", adapter, EXPECTED_ADAPTER_HASH),
        ("scoring_config", config, EXPECTED_SCORING_FILE_HASH),
    ):
        actual = _sha(path)
        if actual != expected_hash:
            raise RuntimeError(f"{label} hash mismatch: {actual} != {expected_hash}")
        values[label] = {"file_sha256": actual, "path": path.relative_to(root).as_posix()}
    scoring = json.loads(config.read_text(encoding="utf-8"))
    if scoring.get("hash") != EXPECTED_SCORING_HASH:
        raise RuntimeError("canonical scoring configuration hash mismatch")
    values["scoring_config"]["canonical_hash"] = EXPECTED_SCORING_HASH
    values["author_approval"] = _aggregate(
        root,
        sorted(
            (root / "benchmarks/mtb_evidence/v3").glob("author_approval*")
        ),
    )
    if values["author_approval"]["aggregate_sha256"] != EXPECTED_AUTHOR_APPROVAL_HASH:
        raise RuntimeError("author approval hash mismatch")
    values["gold_bundle"] = _bundle_guard(gold_bundle, EXPECTED_GOLD_HASH)
    values["candidate_counts"] = _candidate_counts(root)
    if values["candidate_counts"] != EXPECTED_CANDIDATE_COUNTS:
        raise RuntimeError(
            f"candidate counts mismatch: {values['candidate_counts']} "
            f"!= {EXPECTED_CANDIDATE_COUNTS}"
        )
    return values


def _group_classification(
    graph_id: str, distinct_interventions: Sequence[str]
) -> tuple[str, bool, bool, str]:
    if len(distinct_interventions) == 1:
        return (
            "duplicated_serialization",
            False,
            False,
            "righe equivalenti prodotte da traversal/proiezioni diverse",
        )
    if graph_id in REGIMEN_AMBIGUOUS_IDS:
        return (
            "unresolved_without_document_review",
            False,
            True,
            "due archi intervento senza campo strutturato per regimen, braccio o "
            "attribuzione separata",
        )
    return (
        "intervention_specific_results",
        True,
        False,
        "ogni riga strutturata associa biomarcatore, intervento, direzione/polarita, "
        "fonte e graph evidence ID",
    )


def _build_core(
    root: Path, *, reverse_inputs: bool = False
) -> dict[str, Any]:
    adapter_rows = _load_adapter_rows(root, reverse_inputs=reverse_inputs)
    statements = _statements(root)
    corpus_ids = _corpus_statement_ids(root)
    links = _qualification_links(root)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in adapter_rows:
        grouped[record_identifier(row["record"])].append(row)

    group_rows: list[dict[str, Any]] = []
    multi_groups: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    lost: list[dict[str, Any]] = []
    normalization: list[dict[str, Any]] = []

    for graph_id in sorted(grouped, key=_record_key):
        rows = grouped[graph_id]
        statement = statements[graph_id]
        statement_id = str(statement["evidence_statement_id"])
        current = str((statement.get("intervention") or {}).get("label") or "")
        current_norm = norm_drug(current)
        distinct = sorted(
            {_normalized_drug(row["record"]) for row in rows if _drug(row["record"])}
        )
        raw_distinct = sorted({_drug(row["record"]) for row in rows if _drug(row["record"])})
        classification, atomizable, review, rationale = _group_classification(
            graph_id, distinct
        )
        source_ids = sorted(
            {
                source
                for row in rows
                for source in _sources(row["record"])
            }
        )
        directions: set[str] = set()
        polarities: set[str] = set()
        scopes: set[str] = set()
        for row in rows:
            adapted = adapt_record(row["record"]).statement or {}
            directions.add(str(adapted.get("direction") or "unknown"))
            polarities.add(str(adapted.get("assertion_polarity") or "unknown"))
            scopes.add(str(adapted.get("evidence_scope") or "unknown"))
        summary = {
            "graph_evidence_id": graph_id,
            "source_ids": source_ids,
            "statement_id": statement_id,
            "biomarker": (statement.get("biomarker") or {}).get("label"),
            "alteration_type": statement.get("alteration_type"),
            "disease": (statement.get("disease") or {}).get("label"),
            "v2_interventions_raw": raw_distinct,
            "v2_interventions_normalized": distinct,
            "statement_intervention": current,
            "missing_interventions": [item for item in distinct if item != current_norm],
            "directions": sorted(directions),
            "assertion_polarities": sorted(polarities),
            "evidence_scopes": sorted(scopes),
            "evidence_levels": sorted(
                {
                    str(row["record"].get("evidence_level"))
                    for row in rows
                    if row["record"].get("evidence_level") not in (None, "")
                }
            ),
            "traversals": sorted({row["traversal"] for row in rows}),
            "case_ids": sorted({row["case_id"] for row in rows}),
            "row_count": len(rows),
            "semantic_proposition_count": len(distinct),
            "evidence_statement_count": 1,
            "primary_classification": classification,
            "structurally_atomizable": atomizable,
            "source_review_required": review,
            "structural_evidence": rationale,
            "merge_rationale_current": (
                "merge_duplicate_records raggruppa per graph evidence ID; i conflitti "
                "scalari non sovrascrivono il primo valore"
            ),
            "first_loss_stage": (
                "v2_adapter.merge_duplicate_records.scalar_single_value_selection"
                if len(distinct) > 1
                else "none"
            ),
            "current_representation_risk": (
                "interventi V2 non correnti non sono interrogabili nello statement"
                if len(distinct) > 1
                else "nessuna perdita di intervento; sole righe duplicate"
            ),
            "correction_without_document_review": atomizable,
            "qualification_link_count": len(links.get(statement_id, [])),
            "qualification_profile_unit_ids": sorted(
                {
                    str(item["source_profile_unit_id"])
                    for item in links.get(statement_id, [])
                }
            ),
            "statement_present_in_qualification_corpus": statement_id in corpus_ids,
            "aggregate_to_specific_attribution_forbidden": review,
        }
        if len(rows) > 1:
            group_rows.append(summary)
        if len(distinct) > 1:
            multi_groups.append(summary)
        for raw_index, row in enumerate(
            sorted(
                rows,
                key=lambda value: (
                    value["case_id"],
                    value["traversal"],
                    value["record_index"] if value["record_index"] is not None else -1,
                    _drug(value["record"]),
                ),
            )
        ):
            intervention = _normalized_drug(row["record"])
            preserved = intervention == current_norm
            lineage.append(
                {
                    "lineage_id": f"{graph_id}#row-{raw_index:03d}",
                    "case_id": row["case_id"],
                    "traversal": row["traversal"],
                    "record_index": row["record_index"],
                    "graph_evidence_id": graph_id,
                    "adapter_input_intervention_raw": _drug(row["record"]),
                    "adapter_input_intervention_normalized": intervention,
                    "canonical_merge_key": graph_id,
                    "statement_id": statement_id,
                    "statement_intervention": current,
                    "qualification_corpus_present": statement_id in corpus_ids,
                    "retrieval_index_present": statement_id in corpus_ids,
                    "lineage_status": (
                        "preserved_exactly"
                        if _drug(row["record"]).casefold() == current.casefold()
                        else (
                            "preserved_as_normalized_intervention"
                            if preserved
                            else "dropped_by_single_value_selection"
                        )
                    ),
                    "first_loss_stage": (
                        "none"
                        if preserved
                        else "v2_adapter.merge_duplicate_records.scalar_single_value_selection"
                    ),
                    "classification": classification,
                    "gold_used": False,
                }
            )
        for intervention in distinct:
            relation = (
                "normalized_exact" if intervention == current_norm else "distinct_intervention"
            )
            normalization.append(
                {
                    "graph_evidence_id": graph_id,
                    "v2_intervention": intervention,
                    "statement_intervention": current_norm,
                    "normalization_relation": relation,
                    "mapping_status": "exact" if relation == "normalized_exact" else "distinct",
                    "merge_allowed": relation == "normalized_exact",
                    "terminology_review_required": False,
                }
            )
            if intervention != current_norm:
                lost.append(
                    {
                        "graph_evidence_id": graph_id,
                        "statement_id": statement_id,
                        "lost_intervention": intervention,
                        "preserved_intervention": current_norm,
                        "lineage_status": "dropped_by_single_value_selection",
                        "first_loss_stage": (
                            "v2_adapter.merge_duplicate_records."
                            "scalar_single_value_selection"
                        ),
                        "primary_classification": classification,
                        "structurally_atomizable": atomizable,
                        "source_review_required": review,
                        "reason": (
                            "il campo drug e' scalare; un valore non vuoto esistente "
                            "non viene sovrascritto ne' trasformato in lista"
                        ),
                    }
                )

    # Il corpus contiene mapping development-code pendenti, ma nessuno autorizza
    # merge nei gruppi multi-intervento.
    terminology = _read_jsonl(
        root
        / "benchmarks/mtb_evidence/v3/qualification_corpus_v2"
        / "terminology_mappings.jsonl"
    )
    for mapping in terminology:
        if "intervention" not in str(mapping.get("mapping_type") or "") and not (
            mapping.get("graph_term") and mapping.get("source_term")
        ):
            continue
        normalization.append(
            {
                "graph_evidence_id": None,
                "v2_intervention": mapping.get("source_term"),
                "statement_intervention": mapping.get("graph_term")
                or mapping.get("mapped_term"),
                "normalization_relation": "pending_mapping",
                "mapping_status": mapping.get("mapping_status"),
                "merge_allowed": False,
                "terminology_review_required": True,
                "origin_artifact": mapping.get("origin_artifact"),
            }
        )

    return {
        "adapter_rows": adapter_rows,
        "groups": sorted(group_rows, key=lambda row: _record_key(row["graph_evidence_id"])),
        "multi_groups": sorted(
            multi_groups, key=lambda row: _record_key(row["graph_evidence_id"])
        ),
        "lineage": sorted(lineage, key=lambda row: row["lineage_id"]),
        "lost": sorted(
            lost, key=lambda row: (_record_key(row["graph_evidence_id"]), row["lost_intervention"])
        ),
        "normalization": sorted(
            normalization,
            key=lambda row: (
                _record_key(row["graph_evidence_id"])
                if row["graph_evidence_id"]
                else (10**12, ""),
                str(row["v2_intervention"]),
            ),
        ),
        "statements": statements,
        "links": links,
    }


def _pilot_audit(
    root: Path, case_id: str, group_by_id: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    path = (
        root
        / "benchmarks/mtb_evidence/pilot/audit"
        / case_id
        / "normalized_records.jsonl"
    )
    output: list[dict[str, Any]] = []
    counts = Counter(str(row.get("record_id") or "") for row in _read_jsonl(path))
    for position, row in enumerate(_read_jsonl(path)):
        graph_id = str(row.get("record_id") or "")
        group = group_by_id.get(graph_id)
        if not group or counts[graph_id] < 2:
            continue
        if len(group["v2_interventions_normalized"]) < 2:
            continue
        intervention = norm_drug(str(row.get("drug") or ""))
        output.append(
            {
                "case_id": case_id,
                "v2_row_position": position,
                "graph_evidence_id": graph_id,
                "source_ids": group["source_ids"],
                "statement_id": group["statement_id"],
                "biomarker": row.get("subject"),
                "disease": row.get("disease"),
                "v2_intervention": intervention,
                "v2_direction": row.get("direction"),
                "statement_intervention": group["statement_intervention"],
                "intervention_preserved": (
                    intervention == norm_drug(group["statement_intervention"])
                ),
                "missing_from_statement": intervention
                in group["missing_interventions"],
                "classification": group["primary_classification"],
                "recommended_representation": (
                    "atomic_child_claim"
                    if group["structurally_atomizable"]
                    else "parent_aggregate_pending_source_review"
                ),
                "disease_alias_decision_applied": False,
                "biomarker_matching_decision_applied": False,
                "ranking_decision_applied": False,
            }
        )
    return output


def _simulations(core: Mapping[str, Any], root: Path) -> dict[str, Any]:
    multi = core["multi_groups"]
    safe = [row for row in multi if row["structurally_atomizable"]]
    deferred = [row for row in multi if not row["structurally_atomizable"]]
    safe_claims = sum(row["semantic_proposition_count"] for row in safe)
    all_claims = sum(row["semantic_proposition_count"] for row in multi)
    current_count = len(core["statements"])
    source_count = len(
        {
            source["source_id"]
            for statement in core["statements"].values()
            for source in statement.get("source_references", [])
        }
    )
    affected_links = sum(row["qualification_link_count"] for row in safe)
    return {
        "simulation_contract": {
            "frozen_before_gold_access": True,
            "clinical_quality_metrics_computed": False,
            "pending_mappings_merged": False,
            "aggregate_results_atomized": False,
        },
        "current_single_intervention": {
            "statement_total": current_count,
            "statement_new": 0,
            "statement_replaced": 0,
            "graph_evidence_id_count": current_count,
            "source_count": source_count,
            "interventions_hidden": len(core["lost"]),
        },
        "option_A_list_valued": {
            "statement_total": current_count,
            "statement_new": 0,
            "statement_replaced": len(multi),
            "graph_evidence_id_count": current_count,
            "source_count": source_count,
            "qualification_links_requiring_reassessment": sum(
                row["qualification_link_count"] for row in multi
            ),
            "qualified_views_to_regenerate": len(multi),
            "risk": "intervention-direction relation remains non-atomic",
        },
        "option_B_atomic_per_intervention": {
            "safe_statement_total": current_count - len(safe) + safe_claims,
            "safe_statement_new": safe_claims,
            "safe_statement_replaced": len(safe),
            "additional_statement_count": safe_claims - len(safe),
            "deferred_graph_evidence_ids": [
                row["graph_evidence_id"] for row in deferred
            ],
            "maximal_unreviewed_statement_total_forbidden": (
                current_count - len(multi) + all_claims
            ),
            "graph_evidence_id_count": current_count,
            "source_count": source_count,
            "qualification_links_requiring_reassessment": affected_links,
            "qualified_views_to_regenerate": safe_claims,
            "risk": "shared or aggregate evidence needs a parent identity",
        },
        "option_C_parent_plus_atomic_children": {
            "safe_statement_total": current_count + safe_claims,
            "parent_statement_count": current_count,
            "new_child_statement_count": safe_claims,
            "deferred_parent_only_count": len(deferred),
            "graph_evidence_id_count": current_count,
            "source_count": source_count,
            "qualification_links_requiring_reassessment": affected_links,
            "new_qualified_views_if_children_qualified": safe_claims,
            "risk": "child qualification links cannot be inherited blindly",
        },
        "recommended_architecture": "mixed_policy",
        "recommendation_detail": (
            "option C for structurally attributable interventions; keep parent-only "
            "records for regimen/aggregate ambiguity until source review"
        ),
        "safe_atomizable_group_count": len(safe),
        "source_review_group_count": len(deferred),
        "id_strategy": {
            "recommended": "claim_hash",
            "template": (
                "ES-V3-<sha256(graph_evidence_id|canonical_intervention|"
                "direction|assertion_polarity)[:20]>"
            ),
            "order_independent": True,
            "alias_stability_requires_verified_canonical_intervention": True,
            "preserves_graph_evidence_id": True,
            "collision_guard": "store and validate the complete canonical claim tuple",
            "implemented": False,
        },
    }


def _proposed_changes(core: Mapping[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in core["multi_groups"]:
        if row["structurally_atomizable"]:
            actions = [
                "adapter_schema_revision",
                "corpus_regeneration_required",
                "link_regeneration_required",
                "view_regeneration_required",
            ]
        else:
            actions = ["source_review_required", "should_not_atomize"]
        output.append(
            {
                "graph_evidence_id": row["graph_evidence_id"],
                "classification": row["primary_classification"],
                "actions": actions,
                "recommended_representation": (
                    "parent_plus_atomic_children"
                    if row["structurally_atomizable"]
                    else "keep_parent_pending_source_review"
                ),
                "adapter_bug_fix": False,
                "adapter_schema_revision": row["structurally_atomizable"],
                "gold_used": False,
            }
        )
    return output


def _gold_annotation(
    gold_bundle: Path,
    core: Mapping[str, Any],
    classification_hash: str,
) -> dict[str, Any]:
    """Annotazione tardiva: non partecipa a classificazione o raccomandazione."""
    path = gold_bundle / "mtb_evidence_gold_pilot_v1.jsonl"
    records = _read_jsonl(path)
    lost = {str(row["lost_intervention"]).casefold() for row in core["lost"]}
    affected: list[dict[str, Any]] = []
    for row in records:
        serialized = json.dumps(row, ensure_ascii=False).casefold()
        matched = sorted(item for item in lost if item and item in serialized)
        case_id = str(row.get("case_id") or row.get("query_id") or "")
        if matched or any(key in case_id for key in ("ALK", "EGFR", "FGFR2")):
            affected.append(
                {
                    "gold_record_id": row.get("claim_id")
                    or row.get("gold_id")
                    or row.get("case_id"),
                    "case_id": case_id,
                    "lost_intervention_string_matches": matched,
                    "possible_unit_of_count_change": bool(matched),
                    "used_for_architecture_decision": False,
                }
            )
    return {
        "classification_frozen_before_gold_content_load": True,
        "classification_artifact_hash": classification_hash,
        "gold_file_sha256": _sha(path),
        "gold_record_count": len(records),
        "pilot_case_records_in_scope": len(affected),
        "gold_records_with_exact_lost_intervention_match": sum(
            1 for row in affected if row["lost_intervention_string_matches"]
        ),
        "potentially_affected_records": affected,
        "quality_metrics_recomputed": False,
        "denominator_note": (
            "an atomic migration may change therapy-claim denominators; no metric "
            "was calculated"
        ),
    }


def _report(core: Mapping[str, Any], simulation: Mapping[str, Any]) -> str:
    groups = core["groups"]
    multi = core["multi_groups"]
    classes = Counter(row["primary_classification"] for row in groups)
    lines = [
        "# Multi-intervention adapter review",
        "",
        "Review read-only sui record strutturati già congelati. Non sono stati letti",
        "abstract/full text e non sono stati modificati adapter, corpus, retriever o gold.",
        "",
        "## Risultato",
        "",
        f"- Righe V2 compatibili analizzate: **{len(core['adapter_rows'])}**",
        f"- Graph evidence ID: **{len(core['statements'])}**",
        f"- Gruppi multi-riga: **{len(groups)}**",
        f"- Gruppi multi-intervento: **{len(multi)}**",
        f"- Interventi nascosti dall'adapter corrente: **{len(core['lost'])}**",
        f"- Gruppi atomizzabili dai soli dati strutturati: "
        f"**{simulation['safe_atomizable_group_count']}**",
        f"- Gruppi che richiedono source review: "
        f"**{simulation['source_review_group_count']}**",
        "",
        "La perdita avviene in `merge_duplicate_records`: il graph evidence ID è la",
        "chiave di merge, `drug` è scalare e il primo valore non vuoto viene conservato.",
        "`adapt_record` materializza poi un solo oggetto `intervention`.",
        "",
        "## Classificazioni",
        "",
        "| Classe | Gruppi |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{key}` | {value} |" for key, value in sorted(classes.items()))
    lines += [
        "",
        "Nessun gruppo è stato promosso a regimen o risultato aggregato senza un campo",
        "strutturato che lo dimostri. Tre gruppi clinicamente plausibili come regimen",
        "restano `unresolved_without_document_review`.",
        "",
        "## Decisione",
        "",
        "Raccomandazione: **mixed_policy**. Usare un parent evidence record e child claim",
        "atomici soltanto dove la riga V2 associa esplicitamente biomarcatore, intervento,",
        "direzione/polarità, fonte e graph evidence ID. Conservare parent-only i gruppi",
        "ambigui fino a source review. I qualification link non devono essere ereditati",
        "automaticamente dai child.",
        "",
        "Il caso PMID 31358542/brigatinib resta un principio di regressione:",
        "`aggregate_to_specific_attribution_forbidden`. Nessun artefatto relativo è stato",
        "modificato.",
        "",
    ]
    return "\n".join(lines)


def _case_report(title: str, rows: Sequence[Mapping[str, Any]]) -> str:
    groups = sorted({str(row["graph_evidence_id"]) for row in rows}, key=_record_key)
    lost = sum(1 for row in rows if row["missing_from_statement"])
    lines = [
        f"# {title}",
        "",
        f"- Righe V2: **{len(rows)}**",
        f"- Graph evidence ID: **{len(groups)}**",
        f"- Righe con intervento non materializzato: **{lost}**",
        "",
        "| Graph evidence | V2 intervention | Statement intervention | Stato |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        status = "perso" if row["missing_from_statement"] else "preservato"
        lines.append(
            f"| `{row['graph_evidence_id']}` | `{row['v2_intervention']}` | "
            f"`{row['statement_intervention']}` | {status} |"
        )
    lines += [
        "",
        "Disease matching, compound alteration e ranking sono dimensioni separate e non",
        "sono state usate per classificare l'atomicità.",
        "",
    ]
    return "\n".join(lines)


def _options_report(simulation: Mapping[str, Any]) -> str:
    a = simulation["option_A_list_valued"]
    b = simulation["option_B_atomic_per_intervention"]
    c = simulation["option_C_parent_plus_atomic_children"]
    return "\n".join(
        [
            "# EvidenceStatement atomicity options",
            "",
            "| Opzione | Statement simulati | Vantaggio | Rischio |",
            "| --- | ---: | --- | --- |",
            f"| A — lista | {a['statement_total']} | migrazione semplice | "
            "perde la relazione intervento-direzione |",
            f"| B — atomico | {b['safe_statement_total']} | claim therapy-level | "
            "perde un parent condiviso |",
            f"| C — parent + child | {c['safe_statement_total']} | provenance condivisa "
            "| maggiore complessità e link da rivalutare |",
            "",
            "La simulazione sicura non atomizza i gruppi irrisolti. Il massimo non revisionato",
            f"di {b['maximal_unreviewed_statement_total_forbidden']} statement è riportato",
            "soltanto come limite superiore proibito.",
            "",
            "## Strategia ID valutata",
            "",
            f"`{simulation['id_strategy']['template']}`. Non è implementata. La tupla",
            "canonica completa resta il collision guard e conserva il graph evidence ID.",
            "",
            "## Raccomandazione",
            "",
            simulation["recommendation_detail"],
            "",
        ]
    )


def _readiness_report() -> str:
    states = {
        "multi_intervention_root_causes_identified": True,
        "statement_atomicity_decision_ready": True,
        "adapter_fix_ready": False,
        "adapter_schema_revision_required": True,
        "corpus_regeneration_required": True,
        "gold_migration_required": False,
        "source_review_required": True,
        "ready_to_implement_adapter_decision": False,
        "ready_for_hierarchy_policy_implementation": False,
        "ready_for_full_exploratory_rerun": False,
    }
    lines = ["# Multi-intervention decision readiness", ""]
    lines.extend(f"- `{key}`: **{str(value).lower()}**" for key, value in states.items())
    lines += [
        "",
        "La decisione di schema è pronta, ma l'implementazione non lo è: occorrono una",
        "specifica degli ID child, source review dei gruppi ambigui e un piano coordinato",
        "di rigenerazione di corpus, link e view. La policy gerarchica disease resta",
        "separata; il rerun esplorativo rimane bloccato.",
        "",
    ]
    return "\n".join(lines)


def generate_review(
    root: Path,
    output: Path,
    gold_bundle: Path,
    *,
    reverse_inputs: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    integrity = _integrity(root, gold_bundle.resolve())
    core = _build_core(root, reverse_inputs=reverse_inputs)
    by_id = {row["graph_evidence_id"]: row for row in core["multi_groups"]}
    egfr = _pilot_audit(root, "PILOT-C1-EGFR-L858R-CONTEXT", by_id)
    fgfr2 = _pilot_audit(root, "PILOT-K1-FGFR2-iCCA", by_id)
    simulation = _simulations(core, root)
    proposed = _proposed_changes(core)

    core_artifacts: dict[str, bytes] = {
        "multi_row_graph_evidence_inventory.jsonl": _jsonl_bytes(core["groups"]),
        "multi_intervention_groups.jsonl": _jsonl_bytes(core["multi_groups"]),
        "intervention_lineage.jsonl": _jsonl_bytes(core["lineage"]),
        "lost_interventions.jsonl": _jsonl_bytes(core["lost"]),
        "egfr_multi_intervention_audit.jsonl": _jsonl_bytes(egfr),
        "fgfr2_multi_intervention_audit.jsonl": _jsonl_bytes(fgfr2),
        "intervention_normalization_audit.jsonl": _jsonl_bytes(
            core["normalization"]
        ),
        "representation_option_simulation.json": _json_bytes(simulation),
        "proposed_adapter_changes.jsonl": _jsonl_bytes(proposed),
    }
    for name, payload in core_artifacts.items():
        (output / name).write_bytes(payload)
    classification_payload = "\n".join(
        f"{name}:{hashlib.sha256(payload).hexdigest()}"
        for name, payload in sorted(core_artifacts.items())
    )
    classification_hash = hashlib.sha256(
        classification_payload.encode("utf-8")
    ).hexdigest()

    # Solo ora viene caricato il JSONL gold. La verifica hash precedente non ha
    # deserializzato alcun record e non influenza le classificazioni congelate.
    gold_annotation = _gold_annotation(gold_bundle.resolve(), core, classification_hash)
    _write_json(output / "affected_gold_records.json", gold_annotation)

    reports = {
        "MULTI_INTERVENTION_ADAPTER_REVIEW.md": _report(core, simulation),
        "EGFR_MULTI_INTERVENTION_AUDIT.md": _case_report(
            "EGFR multi-intervention audit", egfr
        ),
        "FGFR2_MULTI_INTERVENTION_AUDIT.md": _case_report(
            "FGFR2 multi-intervention audit", fgfr2
        ),
        "EVIDENCE_STATEMENT_ATOMICITY_OPTIONS.md": _options_report(simulation),
        "MULTI_INTERVENTION_DECISION_READINESS.md": _readiness_report(),
    }
    for name, text in reports.items():
        (output / name).write_text(text, encoding="utf-8", newline="\n")

    class_counts = Counter(
        row["primary_classification"] for row in core["groups"]
    )
    manifest = {
        "review_version": REVIEW_VERSION,
        "branch": TARGET_BRANCH,
        "source_sha": SOURCE_SHA,
        "input_order_invariance_verified_by_test": True,
        "corpus_version": "qualification_corpus/2.0",
        "corpus_fingerprint": EXPECTED_CORPUS_FINGERPRINT,
        "frozen_kg_fingerprint": EXPECTED_FROZEN_KG_FINGERPRINT,
        "scoring_config_hash": EXPECTED_SCORING_HASH,
        "input_integrity": integrity,
        "classification_frozen_before_gold_access": True,
        "classification_artifact_hash": classification_hash,
        "gold_used_for_decision": False,
        "gold_loaded_after_classification": True,
        "pmid_content_read": False,
        "network_used": False,
        "neo4j_used": False,
        "llm_used": False,
        "adapter_modified": False,
        "corpus_modified": False,
        "retriever_modified": False,
        "scoring_modified": False,
        "metrics": {
            "raw_v2_rows_analyzed": sum(
                len(_read_jsonl(case / "raw_records.jsonl"))
                for case in sorted(
                    (
                        root / "benchmarks/mtb_evidence/pilot/audit"
                    ).iterdir()
                )
                if case.is_dir()
            ),
            "compatible_v2_rows_analyzed": len(core["adapter_rows"]),
            "graph_evidence_ids": len(core["statements"]),
            "multi_row_groups": len(core["groups"]),
            "multi_intervention_groups": len(core["multi_groups"]),
            "alias_only_groups": 0,
            "confirmed_regimen_groups": 0,
            "regimen_ambiguous_groups": len(REGIMEN_AMBIGUOUS_IDS),
            "drug_class_groups": 0,
            "confirmed_aggregate_groups": 0,
            "atomizable_groups": simulation["safe_atomizable_group_count"],
            "non_atomizable_groups": simulation["source_review_group_count"],
            "preserved_distinct_interventions": len(core["multi_groups"]),
            "lost_distinct_interventions": len(core["lost"]),
            "current_statements_involved": len(core["groups"]),
            "simulated_safe_atomic_statements": (
                simulation["option_B_atomic_per_intervention"][
                    "safe_statement_total"
                ]
            ),
            "source_reviews_required": simulation["source_review_group_count"],
            "pilot_queries_involved": 3,
            "pilot_gold_case_records_in_scope": gold_annotation[
                "pilot_case_records_in_scope"
            ],
            "gold_records_with_exact_lost_intervention_match": gold_annotation[
                "gold_records_with_exact_lost_intervention_match"
            ],
            "classification_counts": dict(sorted(class_counts.items())),
            "egfr_rows": len(egfr),
            "egfr_graph_evidence_ids": len(
                {row["graph_evidence_id"] for row in egfr}
            ),
            "fgfr2_rows": len(fgfr2),
            "fgfr2_graph_evidence_ids": len(
                {row["graph_evidence_id"] for row in fgfr2}
            ),
        },
        "recommendation": simulation["recommended_architecture"],
        "readiness": {
            "multi_intervention_root_causes_identified": True,
            "statement_atomicity_decision_ready": True,
            "adapter_fix_ready": False,
            "adapter_schema_revision_required": True,
            "corpus_regeneration_required": True,
            "gold_migration_required": False,
            "source_review_required": True,
            "ready_to_implement_adapter_decision": False,
            "ready_for_hierarchy_policy_implementation": False,
            "ready_for_full_exploratory_rerun": False,
        },
        "artifact_hashes": {
            path.name: _sha(path)
            for path in sorted(output.iterdir())
            if path.is_file() and path.name != "review_manifest.json"
        },
    }
    _write_json(output / "review_manifest.json", manifest)
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[4]
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gold-bundle", type=Path, required=True)
    parser.add_argument("--reverse-inputs", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = generate_review(
        args.root, args.output, args.gold_bundle, reverse_inputs=args.reverse_inputs
    )
    print(json.dumps(manifest["metrics"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
