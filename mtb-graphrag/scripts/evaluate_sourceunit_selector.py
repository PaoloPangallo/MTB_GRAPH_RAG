"""Valuta il selector deterministico contro i bundle congelati usati come gold.

**Come si usa il gold senza barare.** I ``bundle["source_unit_ids"]`` sono
l'unico riferimento disponibile su quali passaggi fossero rilevanti. Vengono
letti **dopo** che il selector ha prodotto il proprio ranking, mai passati in
ingresso: il modulo del selector non importa nulla che li contenga, e un test
strutturale lo verifica.

**Cosa il gold è davvero.** Non è una verità sulla rilevanza: è la scelta che il
pilot fece una volta, con la sua granularità. Il corpus lo mostra —
``FULLTEXT_SENTENCE`` copre 1595 unità e ne fornisce 5 al gold, mentre
``ABSTRACT`` ne fornisce 13 su 13. Riprodurre il gold significa in parte
riprodurre quella preferenza, non solo trovare i passaggi giusti. Per questo la
valutazione misura anche i *near miss*: unità scelte il cui testo è contenuto in
una gold, o viceversa, cioè lo stesso contenuto con un taglio diverso.

**Metriche sul ranking, non sulla selezione.** Le baseline non hanno soglia;
confrontarle con una selezione soglia le penalizzerebbe per una scelta che non
hanno fatto. Le metriche di retrieval usano quindi i primi K del ranking, e il
comportamento della soglia è riportato a parte.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.research_pipeline import data_access as da  # noqa: E402
from backend.research_pipeline.documents import cache_runtime  # noqa: E402
from backend.research_pipeline.experimental import sourceunit_selector as sus  # noqa: E402

DEFAULT_REPORT_DIR = _REPO_ROOT / "evaluation" / "sourceunit_selector"
K_VALUES = (3, 5, 10)

#: Stima grossolana, dichiarata come tale: serve a confrontare K fra loro, non a
#: prevedere la fattura del modello.
CHARS_PER_TOKEN = 4.0


def build_dataset() -> list[dict[str, Any]]:
    """Un record per bundle valutabile. Tutti i bundle, non un campione."""
    cache = cache_runtime.open_read_only()
    manifest = {row["document_id"]: row for row in da.read_jsonl(da.document_manifest_path())}
    bundles = da.read_jsonl(da.evidence_bundles_path())
    wanted = {b["candidate_id"] for b in bundles}
    candidates = {row["candidate_id"]: row for row in da.iter_jsonl(da.candidates_path())
                  if row["candidate_id"] in wanted}

    units_cache: dict[str, list[dict[str, Any]]] = {}
    dataset: list[dict[str, Any]] = []
    for bundle in sorted(bundles, key=lambda b: b["bundle_id"]):
        document_id = bundle["document_id"]
        candidate = candidates.get(bundle["candidate_id"])
        row = manifest.get(document_id)
        if candidate is None or row is None or not row.get("local_cache_path"):
            continue
        if document_id not in units_cache:
            units_cache[document_id] = cache.source_units_for_record(dict(row))
        units = units_cache[document_id]
        selection = sus.SourceUnitSelectionInput.from_candidate(candidate, document_id, units)
        dataset.append({
            "bundle_id": bundle["bundle_id"],
            "bundle_type": bundle.get("bundle_type"),
            "candidate_id": candidate["candidate_id"],
            "document_id": document_id,
            "disease": list(selection.disease),
            "genes": list(selection.genes),
            "alterations": list(selection.alterations),
            "interventions": list(selection.interventions),
            "graph_relation": selection.graph_relation,
            "gold_source_unit_ids": list(bundle.get("source_unit_ids") or []),
            "gold_count": len(bundle.get("source_unit_ids") or []),
            "document_source_unit_count": len(units),
            "_selection": selection,
            "_units_by_id": {u["source_unit_id"]: u for u in units},
        })
    return dataset


def ranked_ids(selection: sus.SourceUnitSelectionInput) -> list[str]:
    return [u.source_unit_id for u in sus.rank(selection)]


def first_k_ids(selection: sus.SourceUnitSelectionInput) -> list[str]:
    return [str(u.get("source_unit_id")) for u in selection.source_units]


def bm25_ids(selection: sus.SourceUnitSelectionInput) -> list[str]:
    return list(sus.select_bm25(selection, top_k=len(selection.source_units)))


STRATEGIES: Mapping[str, Callable[[sus.SourceUnitSelectionInput], list[str]]] = {
    "baseline_first_k": first_k_ids,
    "baseline_bm25": bm25_ids,
    "feature_selector": ranked_ids,
}


def evaluate(dataset: Sequence[Mapping[str, Any]],
             order_fn: Callable[[sus.SourceUnitSelectionInput], list[str]]) -> dict[str, Any]:
    """Metriche di retrieval sui primi K del ranking."""
    per_case: list[dict[str, Any]] = []
    for record in dataset:
        order = order_fn(record["_selection"])
        gold = set(record["gold_source_unit_ids"])
        position = {uid: i + 1 for i, uid in enumerate(order)}
        gold_ranks = sorted(position[g] for g in gold if g in position)
        entry: dict[str, Any] = {
            "bundle_id": record["bundle_id"],
            "document_id": record["document_id"],
            "gold_count": len(gold),
            "document_source_unit_count": record["document_source_unit_count"],
            "gold_ranks": gold_ranks,
            "first_gold_rank": gold_ranks[0] if gold_ranks else None,
            "reciprocal_rank": (1.0 / gold_ranks[0]) if gold_ranks else 0.0,
        }
        for k in K_VALUES:
            top = set(order[:k])
            found = len(top & gold)
            entry[f"hit@{k}"] = found > 0
            entry[f"recall@{k}"] = found / len(gold) if gold else 0.0
            entry[f"full@{k}"] = bool(gold) and found == len(gold)
        per_case.append(entry)

    def mean(key: str) -> float:
        values = [c[key] for c in per_case]
        return round(sum(values) / len(values), 4) if values else 0.0

    ranks = [c["first_gold_rank"] for c in per_case if c["first_gold_rank"]]
    return {
        "cases": len(per_case),
        "gold_total": sum(c["gold_count"] for c in per_case),
        **{f"hit_rate@{k}": round(sum(c[f'hit@{k}'] for c in per_case) / len(per_case), 4)
           for k in K_VALUES},
        **{f"recall@{k}": mean(f"recall@{k}") for k in K_VALUES},
        **{f"full_gold_coverage@{k}": round(sum(c[f'full@{k}'] for c in per_case) / len(per_case), 4)
           for k in K_VALUES},
        "mrr": mean("reciprocal_rank"),
        "mean_first_gold_rank": round(statistics.mean(ranks), 3) if ranks else None,
        "median_first_gold_rank": statistics.median(ranks) if ranks else None,
        "cases_with_no_gold_retrieved": sum(1 for c in per_case if c["first_gold_rank"] is None),
        "per_case": per_case,
    }


def near_miss_analysis(dataset: Sequence[Mapping[str, Any]], k: int = 5) -> dict[str, Any]:
    """Quanti mancati gold sono in realtà lo stesso contenuto con un taglio diverso."""
    rows: list[dict[str, Any]] = []
    for record in dataset:
        order = ranked_ids(record["_selection"])[:k]
        gold = set(record["gold_source_unit_ids"])
        units = record["_units_by_id"]
        missed = gold - set(order)
        overlapping = 0
        for gold_id in missed:
            gold_text = (units.get(gold_id, {}).get("text") or "").strip()
            if not gold_text:
                continue
            for uid in order:
                text = (units.get(uid, {}).get("text") or "").strip()
                if text and (text in gold_text or gold_text in text):
                    overlapping += 1
                    break
        rows.append({
            "bundle_id": record["bundle_id"],
            "missed_gold": len(missed),
            "missed_but_text_overlapping": overlapping,
        })
    total_missed = sum(r["missed_gold"] for r in rows)
    return {
        "top_k": k,
        "missed_gold_total": total_missed,
        "missed_but_text_overlapping": sum(r["missed_but_text_overlapping"] for r in rows),
        "granularity_recovery_rate": round(
            sum(r["missed_but_text_overlapping"] for r in rows) / total_missed, 4)
        if total_missed else None,
        "per_case": rows,
    }


def score_distribution(dataset: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Punteggi delle unità gold contro tutte le altre (§25)."""
    gold_scores: list[float] = []
    other_scores: list[float] = []
    for record in dataset:
        gold = set(record["gold_source_unit_ids"])
        for unit in sus.rank(record["_selection"]):
            (gold_scores if unit.source_unit_id in gold else other_scores).append(unit.score_total)

    def describe(values: list[float]) -> dict[str, Any]:
        if not values:
            return {}
        ordered = sorted(values)
        return {
            "n": len(ordered), "min": round(ordered[0], 4),
            "p25": round(ordered[len(ordered) // 4], 4),
            "median": round(statistics.median(ordered), 4),
            "p75": round(ordered[3 * len(ordered) // 4], 4),
            "p95": round(ordered[int(len(ordered) * 0.95)], 4),
            "max": round(ordered[-1], 4),
            "zero_fraction": round(sum(1 for v in ordered if v == 0.0) / len(ordered), 4),
        }

    return {"gold": describe(gold_scores), "non_gold": describe(other_scores)}


def token_budget(dataset: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Quanto testo riceverebbe il modello per ciascun K (§27)."""
    out: dict[str, Any] = {"chars_per_token_estimate": CHARS_PER_TOKEN}
    for k in K_VALUES:
        chars: list[int] = []
        for record in dataset:
            order = ranked_ids(record["_selection"])[:k]
            units = record["_units_by_id"]
            chars.append(sum(len(units.get(uid, {}).get("text") or "") for uid in order))
        ordered = sorted(chars)
        out[f"k={k}"] = {
            "mean_chars": round(statistics.mean(chars), 1),
            "p95_chars": ordered[int(len(ordered) * 0.95)],
            "max_chars": ordered[-1],
            "mean_tokens_est": round(statistics.mean(chars) / CHARS_PER_TOKEN, 1),
            "p95_tokens_est": round(ordered[int(len(ordered) * 0.95)] / CHARS_PER_TOKEN, 1),
            "max_tokens_est": round(ordered[-1] / CHARS_PER_TOKEN, 1),
        }
    return out


def threshold_behaviour(dataset: Sequence[Mapping[str, Any]], k: int = 4) -> dict[str, Any]:
    """Cosa succede con la soglia attiva: quante unità restano, e quante gold."""
    selected_counts: list[int] = []
    no_relevant = 0
    gold_kept = 0
    gold_total = 0
    for record in dataset:
        result = sus.select(record["_selection"], top_k=k)
        selected_counts.append(len(result.selected_source_unit_ids))
        if result.status == sus.STATUS_NO_RELEVANT:
            no_relevant += 1
        gold = set(record["gold_source_unit_ids"])
        gold_total += len(gold)
        gold_kept += len(gold & set(result.selected_source_unit_ids))
    return {
        "top_k": k,
        "rule": "score_total > 0 (nessuna soglia tarata sul gold)",
        "mean_selected_units": round(statistics.mean(selected_counts), 3),
        "cases_no_relevant_source_unit": no_relevant,
        "gold_retained": gold_kept,
        "gold_total": gold_total,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valuta il selector contro il gold congelato.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args(argv)

    dataset = build_dataset()
    print(f"dataset: {len(dataset)} bundle valutabili")

    write_jsonl(args.report_dir / "dataset.jsonl",
                ({k: v for k, v in r.items() if not k.startswith("_")} for r in dataset))

    results: dict[str, Any] = {}
    for name, order_fn in STRATEGIES.items():
        metrics = evaluate(dataset, order_fn)
        results[name] = metrics
        write_json(args.report_dir / f"{name}.json", metrics)
        print(f"  {name:20} hit@3={metrics['hit_rate@3']:.3f} hit@5={metrics['hit_rate@5']:.3f} "
              f"hit@10={metrics['hit_rate@10']:.3f} rec@5={metrics['recall@5']:.3f} "
              f"rec@10={metrics['recall@10']:.3f} mrr={metrics['mrr']:.3f}")

    write_json(args.report_dir / "retrieval_metrics.json", {
        "k_values": list(K_VALUES),
        "strategies": {name: {k: v for k, v in m.items() if k != "per_case"}
                       for name, m in results.items()},
        "near_miss": near_miss_analysis(dataset),
        "score_distribution": score_distribution(dataset),
        "threshold_behaviour": threshold_behaviour(dataset),
    })
    write_json(args.report_dir / "topk_analysis.json", token_budget(dataset))

    write_jsonl(args.report_dir / "selector_rankings.jsonl", (
        {**sus.select(r["_selection"], top_k=10).to_dict(ranking_limit=10),
         "bundle_id": r["bundle_id"], "gold_source_unit_ids": r["gold_source_unit_ids"]}
        for r in dataset))

    failures = [
        {"bundle_id": r["bundle_id"], "document_id": r["document_id"],
         "gold_count": r["gold_count"], "document_units": r["document_source_unit_count"],
         "genes": "|".join(r["genes"]), "alterations": "|".join(r["alterations"]),
         "interventions": "|".join(r["interventions"]),
         "first_gold_rank": c["first_gold_rank"], "gold_ranks": "|".join(map(str, c["gold_ranks"]))}
        for r, c in zip(dataset, results["feature_selector"]["per_case"])
        if not c["hit@5"]
    ]
    path = args.report_dir / "failure_cases.csv"
    header = ["bundle_id", "document_id", "gold_count", "document_units", "genes",
              "alterations", "interventions", "first_gold_rank", "gold_ranks"]
    path.write_text(
        ",".join(header) + "\n"
        + "".join(",".join(str(row.get(h, "")) for h in header) + "\n" for row in failures),
        encoding="utf-8")
    print(f"  casi senza gold nei primi 5: {len(failures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
