"""Independent, frozen evaluation harness for the SourceUnit selector.

This module deliberately keeps acquisition, annotation, ranking, and reporting
separate.  ``acquire`` reads real v2 GCA provenance and writes only metadata;
the fetched payload and parsed text live in an ephemeral cache.  ``evaluate``
fetches the same records again, loads the frozen annotation labels, and runs
the selector only after the annotation hash has been verified.

No bundle, expected quote, Gemma output, validator outcome, or canonical status
is imported by the ranking path.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import statistics
import sys
import tempfile
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.research_pipeline import data_access as da  # noqa: E402
from backend.research_pipeline.documents import cache_runtime  # noqa: E402
from backend.research_pipeline.documents.authorized_cache import (  # noqa: E402
    AuthorizedDocumentCache,
    expand_identifier,
    file_hash,
)
from backend.research_pipeline.experimental import sourceunit_selector as sus  # noqa: E402

REPORT_DIR = _REPO_ROOT / "evaluation" / "sourceunit_selector_independent"
SELECTOR_VERSION = sus.SELECTOR_VERSION
K_VALUES = (1, 3, 5, 10)
TARGET_PAIRS = 20
POOL_SIZE = 36
CHARS_PER_TOKEN = 4.0
ANNOTATION_COLUMNS = (
    "candidate_id", "document_id", "source_unit_id", "relevance_label",
    "difficulty", "annotation_basis",
)


def _json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def candidate_pmids(candidate: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    for item in candidate.get("document_identifiers") or []:
        for expanded in expand_identifier(item):
            value = str(expanded.get("pmid") or "").strip()
            if value and value not in found:
                found.append(value)
    return found


def candidate_snapshot(candidate: Mapping[str, Any], pmid: str) -> dict[str, Any]:
    biomarkers = candidate.get("biomarkers") or []
    selection = sus.SourceUnitSelectionInput.from_candidate(candidate, f"pmid:{pmid}", ())
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "candidate_version": candidate.get("candidate_version"),
        "document_id_from_provenance": f"pmid:{pmid}",
        "provenance_pmids": candidate_pmids(candidate),
        "disease": list(selection.disease),
        "genes": list(selection.genes),
        "alterations": list(selection.alterations),
        "interventions": list(selection.interventions),
        "graph_relation": selection.graph_relation,
        "direction": candidate.get("direction"),
        "biomarker_types": [str(b.get("type") or "") for b in biomarkers],
        "candidate_input_hash": _json_hash({
            "candidate_id": selection.candidate_id,
            "disease": list(selection.disease),
            "genes": list(selection.genes),
            "alterations": list(selection.alterations),
            "interventions": list(selection.interventions),
            "graph_relation": selection.graph_relation,
            "pmid": pmid,
        }),
    }


def pilot_exclusion_sets() -> tuple[set[str], set[str], set[str]]:
    """Return candidate IDs, document IDs, and identifier values used by pilot."""
    bundles = da.read_jsonl(da.evidence_bundles_path())
    candidates = {str(row.get("candidate_id")) for row in bundles}
    documents = {str(row.get("document_id")) for row in bundles}
    identifiers: set[str] = set()
    manifest = da.read_jsonl(da.document_manifest_path())
    for document in manifest:
        if document.get("document_id") in documents:
            identifiers.add(str(document.get("document_id")))
            for key in ("pmid", "pmcid"):
                value = str((document.get("identifiers") or {}).get(key) or "")
                if value:
                    identifiers.add(f"{key}:{value.lower()}")
    for document in documents:
        identifiers.add(document.lower())
    return candidates, documents, identifiers


def select_candidate_pool(limit: int = POOL_SIZE) -> list[dict[str, Any]]:
    """Select real, unseen v2 GCA records with deterministic diversity quotas."""
    pilot_candidates, pilot_documents, pilot_identifiers = pilot_exclusion_sets()
    rows = da.read_jsonl(da.candidates_path())
    grouped: dict[str, list[tuple[dict[str, Any], str]]] = defaultdict(list)
    by_pmid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id or candidate_id in pilot_candidates:
            continue
        pmids = candidate_pmids(row)
        if len(pmids) != 1:
            continue
        pmid = pmids[0]
        document_id = f"pmid:{pmid}"
        if document_id in pilot_documents or document_id.lower() in pilot_identifiers:
            continue
        if not row.get("biomarkers"):
            continue
        by_pmid[pmid].append(row)

    for pmid, candidates_for_pmid in by_pmid.items():
        # Prefer an intervention-bearing assertion when the same paper has
        # both diagnostic and therapy materializations.
        row = sorted(
            candidates_for_pmid,
            key=lambda candidate: (not bool(candidate.get("interventions")), candidate["candidate_id"]),
        )[0]
        direction = str(row.get("direction") or "UNKNOWN")
        grouped[direction].append((row, pmid))

    # Drug-bearing pairs are preferred; the repository has no intervention
    # records for Does Not Support, so that category remains represented by
    # its real no-intervention GCA records where available.
    quotas = {
        "Resistance": 7,
        "Sensitivity/Response": 7,
        "Supports": 4,
        "Does Not Support": 3,
    }
    chosen: list[dict[str, Any]] = []
    for direction, quota in quotas.items():
        candidates = sorted(
            grouped.get(direction, []),
            key=lambda pair: (not bool(pair[0].get("interventions")), pair[0]["candidate_id"]),
        )
        for row, pmid in candidates[:quota]:
            chosen.append({"candidate": row, "pmid": pmid})
    if len(chosen) < limit:
        remaining = [
            pair for direction_rows in grouped.values() for pair in direction_rows
            if pair[1] not in {item["pmid"] for item in chosen}
        ]
        for row, pmid in sorted(remaining, key=lambda pair: pair[0]["candidate_id"]):
            if len(chosen) >= limit:
                break
            chosen.append({"candidate": row, "pmid": pmid})
    return chosen[:limit]


def _record_path(root: Path, record: Mapping[str, Any]) -> Path | None:
    relative = record.get("local_cache_path")
    if not relative:
        return None
    path = root / str(relative)
    return path if path.is_file() else None


def fetch_and_parse(root: Path, candidate: Mapping[str, Any], pmid: str,
                    *, delay_seconds: float) -> dict[str, Any]:
    """Fetch PMID, derive PMCID from that response, then prefer fresh PMC text."""
    cache = AuthorizedDocumentCache(root=root, network=True, delay_seconds=delay_seconds)
    started = time.monotonic()
    pubmed = cache.resolve_pmid(pmid)
    pubmed_path = _record_path(root, pubmed)
    derived_pmcid = str((pubmed.get("identifiers") or {}).get("pmcid") or "").upper() or None
    pmc: Mapping[str, Any] | None = None
    pmc_path: Path | None = None
    if derived_pmcid:
        pmc = cache.resolve_pmc(derived_pmcid)
        pmc_path = _record_path(root, pmc)

    selected_record: Mapping[str, Any] = pubmed
    selected_source = "PUBMED_ABSTRACT"
    if pmc_path is not None:
        selected_record = pmc or pubmed
        selected_source = "PMC_FULLTEXT"
    read_only = cache_runtime.ReadOnlyDocumentCache(root)
    units = read_only.source_units_for_record(dict(selected_record))
    with_text = [u for u in units if str(u.get("text") or "").strip()]
    parser_versions = sorted({f"{u.get('parser')}@{u.get('parser_version')}" for u in units})
    identifiers = pubmed.get("identifiers") or {}
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "pmid": pmid,
        "document_id": str(selected_record.get("document_id") or f"pmid:{pmid}"),
        "pmcid": derived_pmcid,
        "source_type": selected_source,
        "availability": selected_record.get("availability"),
        "title": str(pubmed.get("title") or ""),
        "parser_versions": parser_versions,
        "source_unit_count": len(units),
        "text_available_count": len(with_text),
        "unit_types": sorted({str(u.get("unit_type") or "") for u in units}),
        "source_unit_ids": sorted(str(u.get("source_unit_id") or "") for u in units),
        "retrieval_timestamp": pubmed.get("retrieved_at") or selected_record.get("retrieved_at"),
        "pubmed_payload_hash": file_hash(pubmed_path) if pubmed_path else None,
        "pmc_payload_hash": file_hash(pmc_path) if pmc_path else None,
        "fetch_duration_seconds": round(time.monotonic() - started, 3),
        "_units": units,
        "_pubmed": pubmed,
        "_pmc": pmc,
    }


def strip_internal(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def acquire(report_dir: Path, *, delay_seconds: float, review_path: Path | None) -> int:
    pool = select_candidate_pool()
    scratch = Path(tempfile.mkdtemp(prefix="mtb-sourceunit-independent-"))
    valid: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    try:
        for item in pool:
            if len(valid) >= TARGET_PAIRS:
                break
            candidate = item["candidate"]
            pmid = item["pmid"]
            try:
                parsed = fetch_and_parse(scratch, candidate, pmid, delay_seconds=delay_seconds)
                if not parsed["text_available_count"]:
                    failures.append({"candidate_id": candidate["candidate_id"], "pmid": pmid, "reason": "NO_TEXT_UNITS"})
                    continue
                valid.append(parsed)
                print(f"[{len(valid):02d}/{TARGET_PAIRS}] {candidate['candidate_id']} PMID {pmid} {parsed['source_type']} units={parsed['source_unit_count']}")
            except Exception as exc:  # noqa: BLE001 - acquisition failure is report data
                failures.append({"candidate_id": candidate["candidate_id"], "pmid": pmid,
                                 "reason": f"{type(exc).__name__}: {exc}"})
                print(f"[FAIL] {candidate['candidate_id']} PMID {pmid}: {type(exc).__name__}: {exc}")
        if len(valid) < 15:
            raise RuntimeError(f"independent corpus hard stop: only {len(valid)} valid pairs (<15)")

        candidate_rows = []
        document_rows = []
        review_rows = []
        for parsed in valid:
            candidate = next(item["candidate"] for item in pool if item["pmid"] == parsed["pmid"])
            candidate_rows.append(candidate_snapshot(candidate, parsed["pmid"]))
            document_rows.append(strip_internal(parsed))
            for unit in parsed["_units"]:
                review_rows.append({
                    "candidate_id": parsed["candidate_id"],
                    "document_id": parsed["document_id"],
                    "source_unit_id": str(unit.get("source_unit_id") or ""),
                    "unit_type": unit.get("unit_type"),
                    "section": unit.get("section"),
                    "text": str(unit.get("text") or ""),
                })
        write_jsonl(report_dir / "candidate_inventory.jsonl", candidate_rows)
        write_jsonl(report_dir / "document_inventory.jsonl", document_rows)
        pilot_candidates, pilot_documents, _ = pilot_exclusion_sets()
        inventory = {
            "protocol_version": "independent-sourceunit-selector/1.0",
            "selector_version": SELECTOR_VERSION,
            "source_repository": "graph_candidate_repository/2.0",
            "target_pairs": TARGET_PAIRS,
            "candidate_pool_size": len(pool),
            "valid_pair_count": len(valid),
            "document_count": len({row["document_id"] for row in document_rows}),
            "pubmed_abstract_count": sum(row["source_type"] == "PUBMED_ABSTRACT" for row in document_rows),
            "pmc_fulltext_count": sum(row["source_type"] == "PMC_FULLTEXT" for row in document_rows),
            "failed_candidates": failures,
            "pilot_candidate_count": len(pilot_candidates),
            "pilot_document_count": len(pilot_documents),
            "overlap_with_pilot_candidates": sorted(set(row["candidate_id"] for row in candidate_rows) & pilot_candidates),
            "overlap_with_pilot_documents": sorted(set(row["document_id"] for row in document_rows) & pilot_documents),
            "gold_frozen_before_selector": False,
            "full_text_persisted_in_artifacts": False,
            "acquired_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        write_json(report_dir / "corpus_inventory.json", inventory)
        if review_path:
            write_jsonl(review_path, review_rows)
            print(f"annotation review (temporary, contains text): {review_path}")
        print(f"acquired independent pairs: {len(valid)}")
        return 0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def normalize_for_annotation(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).casefold()
    return " ".join("".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text).split())


def annotation_terms(candidate: Mapping[str, Any]) -> dict[str, list[str]]:
    return {
        "gene": [normalize_for_annotation(x) for x in candidate.get("genes") or []],
        "alteration": [normalize_for_annotation(x) for x in candidate.get("alterations") or []],
        "intervention": [normalize_for_annotation(x) for x in candidate.get("interventions") or []],
        "disease": [normalize_for_annotation(x) for x in candidate.get("disease") or []],
    }


def annotation_candidates(review_path: Path, candidate_path: Path) -> int:
    """Print a non-ranked lexical review aid; it is never consumed by ranking."""
    rows = read_jsonl(review_path)
    candidates = {row["candidate_id"]: row for row in read_jsonl(candidate_path)}
    for row in rows:
        candidate = candidates[row["candidate_id"]]
        text = normalize_for_annotation(row.get("text"))
        terms = annotation_terms(candidate)
        matches = {key: sorted(term for term in values if term and term in text)
                   for key, values in terms.items()}
        if any(matches.values()):
            print(json.dumps({
                "candidate_id": row["candidate_id"], "document_id": row["document_id"],
                "source_unit_id": row["source_unit_id"], "unit_type": row.get("unit_type"),
                "section": row.get("section"), "matches": matches,
                "text": row.get("text", ""),
            }, ensure_ascii=False))
    return 0


def read_gold(path: Path) -> tuple[list[dict[str, str]], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    missing = set(ANNOTATION_COLUMNS) - set(rows[0] if rows else ())
    if missing:
        raise ValueError(f"gold annotation missing columns: {sorted(missing)}")
    allowed = {"DIRECTLY_RELEVANT", "PARTIALLY_RELEVANT", "CONTEXT_ONLY", "NOT_RELEVANT"}
    bad = sorted({row["relevance_label"] for row in rows} - allowed)
    if bad:
        raise ValueError(f"invalid relevance labels: {bad}")
    return rows, digest


def query_input(candidate: Mapping[str, Any], document_id: str,
                units: Sequence[Mapping[str, Any]]) -> sus.SourceUnitSelectionInput:
    return sus.SourceUnitSelectionInput(
        candidate_id=str(candidate["candidate_id"]), document_id=document_id,
        disease=tuple(candidate.get("disease") or ()), genes=tuple(candidate.get("genes") or ()),
        alterations=tuple(candidate.get("alterations") or ()),
        interventions=tuple(candidate.get("interventions") or ()),
        graph_relation=candidate.get("graph_relation"), source_units=tuple(units),
    )


def retrieve_units_for_inventory(root: Path, candidate: Mapping[str, Any], document: Mapping[str, Any],
                                 *, delay_seconds: float) -> dict[str, Any]:
    parsed = fetch_and_parse(root, candidate, str(document["pmid"]), delay_seconds=delay_seconds)
    if parsed["document_id"] != document["document_id"]:
        raise ValueError(f"fresh document id drift for {candidate['candidate_id']}: {parsed['document_id']} != {document['document_id']}")
    return parsed


def metric_for_order(order: Sequence[str], relevant: set[str], k: int) -> dict[str, Any]:
    top = set(order[:k])
    found = len(top & relevant)
    hit = bool(found)
    recall = found / len(relevant) if relevant else 0.0
    precision = found / k if k else 0.0
    return {"hit": hit, "recall": recall, "precision": precision,
            "full_coverage": bool(relevant) and found == len(relevant)}


def aggregate_metrics(rows: Sequence[Mapping[str, Any]], prefix: str) -> dict[str, Any]:
    output: dict[str, Any] = {"cases": len(rows), "relevant_units": sum(int(r["relevant_count"]) for r in rows)}
    for k in K_VALUES:
        for metric in ("hit", "recall", "precision", "full_coverage"):
            values = [float(r[f"{prefix}_{metric}@{k}"]) for r in rows]
            output[f"{metric}_rate@{k}"] = round(statistics.mean(values), 4) if values else 0.0
    ranks = [r["first_relevant_rank"] for r in rows if r.get("first_relevant_rank")]
    output["mrr"] = round(statistics.mean([1.0 / r if r else 0.0 for r in [row.get("first_relevant_rank") for row in rows]]), 4) if rows else 0.0
    output["mean_first_relevant_rank"] = round(statistics.mean(ranks), 3) if ranks else None
    output["median_first_relevant_rank"] = statistics.median(ranks) if ranks else None
    return output


def evaluate(report_dir: Path, *, delay_seconds: float, gemma: bool = False) -> int:
    corpus = json.loads((report_dir / "corpus_inventory.json").read_text(encoding="utf-8"))
    candidate_rows = read_jsonl(report_dir / "candidate_inventory.jsonl")
    document_rows = read_jsonl(report_dir / "document_inventory.jsonl")
    gold_rows, gold_hash = read_gold(report_dir / "gold_annotations.csv")
    if not candidate_rows or len(candidate_rows) < 15:
        raise RuntimeError("independent corpus hard stop: fewer than 15 candidate rows")
    gold_lookup = {(row["candidate_id"], row["document_id"], row["source_unit_id"]): row for row in gold_rows}
    direct_by_case: dict[tuple[str, str], set[str]] = defaultdict(set)
    partial_by_case: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in gold_rows:
        key = (row["candidate_id"], row["document_id"])
        if row["relevance_label"] == "DIRECTLY_RELEVANT":
            direct_by_case[key].add(row["source_unit_id"])
        if row["relevance_label"] in {"DIRECTLY_RELEVANT", "PARTIALLY_RELEVANT"}:
            partial_by_case[key].add(row["source_unit_id"])
    if not direct_by_case:
        raise RuntimeError("gold contains no DIRECTLY_RELEVANT units")

    candidate_by_id = {row["candidate_id"]: row for row in candidate_rows}
    scratch = Path(tempfile.mkdtemp(prefix="mtb-sourceunit-independent-eval-"))
    rankings: list[dict[str, Any]] = []
    strategy_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    try:
        for document in document_rows:
            candidate = candidate_by_id[document["candidate_id"]]
            parsed = retrieve_units_for_inventory(scratch, candidate, document, delay_seconds=delay_seconds)
            units = parsed["_units"]
            selection = query_input(candidate, document["document_id"], units)
            ranked = sus.rank(selection)
            selector_order = [unit.source_unit_id for unit in ranked]
            bm25_order = list(sus.select_bm25(selection, top_k=len(units)))
            first_order = [str(unit.get("source_unit_id") or "") for unit in units]
            key = (candidate["candidate_id"], document["document_id"])
            direct = direct_by_case.get(key, set())
            partial = partial_by_case.get(key, set())
            # Empty direct gold is a valid negative case; metrics record a
            # miss while the negative-case report preserves the denominator.
            orders = {"baseline_first_k": first_order, "baseline_bm25": bm25_order, "feature_selector": selector_order}
            case = {
                "candidate_id": candidate["candidate_id"], "document_id": document["document_id"],
                "source_type": document["source_type"], "document_source_unit_count": len(units),
                "direct_relevant_count": len(direct), "partial_plus_direct_count": len(partial),
                "input_hash": selection.input_hash(), "ranking_hash": _json_hash(selector_order),
                "selector_version": SELECTOR_VERSION,
                "ranking": [unit.to_dict() for unit in ranked],
                "orders": {name: order for name, order in orders.items()},
            }
            rankings.append(case)
            for strategy, order in orders.items():
                for label, relevant in (("direct", direct), ("direct_plus_partial", partial)):
                    first = {uid: index + 1 for index, uid in enumerate(order)}
                    relevant_ranks = [first[uid] for uid in relevant if uid in first]
                    row = {"candidate_id": candidate["candidate_id"], "document_id": document["document_id"],
                           "relevant_count": len(relevant), "first_relevant_rank": min(relevant_ranks) if relevant_ranks else None}
                    for k in K_VALUES:
                        metrics = metric_for_order(order, relevant, k)
                        for metric, value in metrics.items():
                            row[f"{label}_{metric}@{k}"] = value
                    strategy_rows[f"{strategy}:{label}"].append(row)

        metric_payload = {
            "cases": len(rankings), "gold_hash": gold_hash,
            "gold_frozen_before_selector": True, "selector_started_after_gold_frozen": True,
            "selector_version": SELECTOR_VERSION, "k_values": list(K_VALUES),
            "strategies": {name: aggregate_metrics(rows, "direct") for name, rows in strategy_rows.items()
                           if name.endswith(":direct")},
            "direct_plus_partial": {name: aggregate_metrics(rows, "direct_plus_partial") for name, rows in strategy_rows.items()
                                    if name.endswith(":direct_plus_partial")},
        }
        write_jsonl(report_dir / "selector_rankings.jsonl", rankings)
        for strategy in ("baseline_first_k", "baseline_bm25", "feature_selector"):
            write_json(report_dir / f"{strategy}.json", {
                "direct": aggregate_metrics(strategy_rows[f"{strategy}:direct"], "direct"),
                "direct_plus_partial": aggregate_metrics(strategy_rows[f"{strategy}:direct_plus_partial"], "direct_plus_partial"),
            })
        write_json(report_dir / "selector_metrics.json", metric_payload)
        by_type: dict[str, dict[str, Any]] = {}
        for source_type in sorted({row["source_type"] for row in rankings}):
            indexes = {row["candidate_id"] + "|" + row["document_id"] for row in rankings if row["source_type"] == source_type}
            by_type[source_type] = {
                "cases": len(indexes),
                "feature_selector_direct": aggregate_metrics(
                    [row for row in strategy_rows["feature_selector:direct"] if row["candidate_id"] + "|" + row["document_id"] in indexes], "direct"),
            }
        write_json(report_dir / "metrics_by_document_type.json", by_type)
        write_json(report_dir / "metrics_by_difficulty.json", {
            "annotation_difficulty_labels": sorted({row.get("difficulty", "") for row in gold_rows}),
            "note": "Difficulty labels are annotation metadata; no tuning was performed.",
        })
        write_json(report_dir / "negative_cases.json", {
            "cases": [row for row in candidate_rows if row.get("direction") in {"Resistance", "Does Not Support"}],
            "direct_gold_cases": len([key for key, units in direct_by_case.items() if units]),
            "zero_direct_relevant_cases": len([key for key in {(r['candidate_id'], r['document_id']) for r in gold_rows} if not direct_by_case.get(key)]),
        })
        # No full text is emitted; failure rows contain only feature/rank metadata.
        with (report_dir / "failure_analysis.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("candidate_id", "document_id", "source_type", "document_source_unit_count", "first_direct_rank", "failure_class"))
            writer.writeheader()
            for row in strategy_rows["feature_selector:direct"]:
                if not row["direct_hit@5"]:
                    writer.writerow({**{key: row[key] for key in ("candidate_id", "document_id")},
                                     "source_type": next(item["source_type"] for item in rankings if item["candidate_id"] == row["candidate_id"] and item["document_id"] == row["document_id"]),
                                     "document_source_unit_count": next(item["document_source_unit_count"] for item in rankings if item["candidate_id"] == row["candidate_id"] and item["document_id"] == row["document_id"]),
                                     "first_direct_rank": row["first_relevant_rank"], "failure_class": "NOT_IN_TOP_5"})
        corpus["gold_annotation_hash"] = gold_hash
        corpus["gold_frozen_before_selector"] = True
        corpus["selector_started_after_gold_frozen"] = True
        write_json(report_dir / "corpus_inventory.json", corpus)
        print(f"evaluated independent pairs: {len(rankings)}")
        return 0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Frozen selector evaluation on unseen GCA/document pairs")
    parser.add_argument("phase", choices=("acquire", "annotation-candidates", "evaluate"))
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--review-path", type=Path, default=None)
    parser.add_argument("--delay-seconds", type=float, default=0.34)
    args = parser.parse_args(argv)
    if args.phase == "acquire":
        return acquire(args.report_dir, delay_seconds=args.delay_seconds, review_path=args.review_path)
    if args.phase == "annotation-candidates":
        if args.review_path is None:
            parser.error("--review-path is required for annotation-candidates")
        return annotation_candidates(args.review_path, args.report_dir / "candidate_inventory.jsonl")
    return evaluate(args.report_dir, delay_seconds=args.delay_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
