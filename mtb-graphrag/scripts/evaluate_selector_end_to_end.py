"""Il selector regge fino a Gemma e al validatore, anche su documenti appena scaricati?

Le metriche di retrieval dicono se il selector ritrova le unità che il pilot
aveva scelto. Non dicono se le unità che sceglie **da solo** siano utilizzabili:
un ranking può centrare il gold e comunque consegnare al modello passaggi che
non permettono una citazione verificabile.

Tre confronti, con costi diversi e scopi diversi:

* **§22 — gold contro selector.** Lo stesso bundle, la stessa candidate, due
  insiemi di unità. Interessa la differenza, non il valore assoluto.
* **§26 — finestra di contesto.** Aggiungere l'unità precedente e successiva
  aiuta la validazione, o gonfia soltanto il prompt?
* **§33 — fetch live.** Documento riscaricato dall'API, parser, selector, Gemma:
  il percorso che un'architettura cache-miss percorrerebbe davvero.

Le chiamate al modello costano, quindi il campione è stratificato e dichiarato,
non esaustivo. Nessun testo di articolo finisce negli artefatti.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.research_pipeline import data_access as da  # noqa: E402
from backend.research_pipeline.documents import cache_runtime  # noqa: E402
from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache  # noqa: E402
from backend.research_pipeline.experimental import sourceunit_selector as sus  # noqa: E402

DEFAULT_REPORT_DIR = _REPO_ROOT / "evaluation" / "sourceunit_selector"
TOP_K = 4
SAMPLE_PER_BUCKET = 3


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ask_gemma(candidate: Mapping[str, Any], paper_id: str,
              units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Enricher v2 e validatore reali. Nessuna quote negli esiti registrati."""
    from backend.research_pipeline import live_providers
    from backend.research_pipeline.pipeline import CallBudget

    disease = candidate.get("disease") or []
    biomarkers = candidate.get("biomarkers") or []
    interventions = [i.get("label") for i in candidate.get("interventions") or [] if i.get("label")]
    drug = interventions[0] if interventions else ""
    case_context = {
        "query_intent": "THERAPY_EVALUATION",
        "disease": {"normalized_value": (disease[0] or {}).get("label") if disease else None},
        "biomarkers": [{"normalized_value": b.get("label")} for b in biomarkers],
        "target_intervention": {"normalized_value": drug},
    }
    summary = {"candidate_id": candidate.get("candidate_id"),
               "disease": disease, "biomarkers": biomarkers}
    offered = {u["source_unit_id"]: dict(u) for u in units}
    try:
        call = live_providers.enricher_fn(
            CallBudget(8), "SELECTOR-EVAL", str(candidate.get("candidate_id")), paper_id,
            case_context, summary, drug, [dict(u) for u in units],
        )
    except Exception as exc:  # noqa: BLE001
        return {"gemma_reached": False, "error": f"{type(exc).__name__}: {exc}"}

    enrichment = call.get("enrichment") or {}
    validation = live_providers.validate_fn(
        call.get("transport_result"), enrichment, candidate=dict(candidate),
        paper_bundle={"bundle_id": paper_id, "resolved_source_unit_ids": list(offered)},
        source_units_by_id=offered, requested_drug=drug,
    )
    decision = enrichment.get("decision")
    cited = enrichment.get("source_unit_id")
    outcome = str(validation.get("outcome") or "")
    return {
        "gemma_reached": True,
        "units_offered": len(units),
        "prompt_chars": sum(len(u.get("text") or "") for u in units),
        "decision": decision,
        "cited_source_unit_id": cited,
        "unauthorized_source_unit": bool(cited) and cited not in offered,
        "quote_length": len(str(enrichment.get("author_claim_quote") or "")),
        "validator_outcome": outcome,
        "validator_reason_codes": validation.get("reason_codes"),
        "quote_offset": validation.get("quote_offset"),
        "quote_validated": outcome.startswith("ENRICHMENT_V2_ACCEPTED"),
        "wrong_quote": decision == "QUOTE" and not outcome.startswith("ENRICHMENT_V2_ACCEPTED"),
        "input_tokens": call.get("input_tokens"),
        "output_tokens": call.get("output_tokens"),
    }


def load_context() -> tuple[dict, dict, list, dict]:
    cache = cache_runtime.open_read_only()
    manifest = {r["document_id"]: r for r in da.read_jsonl(da.document_manifest_path())}
    bundles = da.read_jsonl(da.evidence_bundles_path())
    wanted = {b["candidate_id"] for b in bundles}
    candidates = {r["candidate_id"]: r for r in da.iter_jsonl(da.candidates_path())
                  if r["candidate_id"] in wanted}
    return cache, manifest, bundles, candidates


def stratified_sample(bundles: Sequence[Mapping[str, Any]], units_of,
                      per_bucket: int = SAMPLE_PER_BUCKET) -> list[Mapping[str, Any]]:
    """Campione dichiarato: fino a N bundle per fascia di dimensione documento."""
    buckets: dict[str, list[Mapping[str, Any]]] = {"small": [], "medium": [], "large": []}
    for bundle in sorted(bundles, key=lambda b: b["bundle_id"]):
        count = len(units_of(bundle["document_id"]))
        key = "small" if count < 20 else "medium" if count < 100 else "large"
        if len(buckets[key]) < per_bucket:
            buckets[key].append(bundle)
    return [b for key in ("small", "medium", "large") for b in buckets[key]]


def rates(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    reached = [r for r in rows if r.get("gemma_reached")]
    if not reached:
        return {"n": 0}
    n = len(reached)
    return {
        "n": n,
        "quote_rate": round(sum(1 for r in reached if r["decision"] == "QUOTE") / n, 4),
        "abstain_rate": round(sum(1 for r in reached if r["decision"] == "ABSTAIN") / n, 4),
        "validated_quote_rate": round(sum(1 for r in reached if r["quote_validated"]) / n, 4),
        "wrong_quote_rate": round(sum(1 for r in reached if r["wrong_quote"]) / n, 4),
        "unauthorized_source_unit_rate": round(
            sum(1 for r in reached if r["unauthorized_source_unit"]) / n, 4),
        "mean_prompt_chars": round(statistics.mean(r["prompt_chars"] for r in reached), 1),
        "mean_input_tokens": round(statistics.mean(
            r["input_tokens"] for r in reached if r.get("input_tokens")), 1)
        if any(r.get("input_tokens") for r in reached) else None,
    }


def robustness_report() -> dict[str, Any]:
    """§35 — misure, non solo asserzioni nei test."""
    candidate = {
        "candidate_id": "GCA-robustness", "predicate": "has_evidence_statement",
        "disease": [{"label": "Chronic Myeloid Leukemia"}],
        "biomarkers": [{"label": "ABL1", "type": "Gene"}, {"label": "V299L", "type": "Variant"}],
        "interventions": [{"label": "dasatinib"}],
    }
    base = [
        {"source_unit_id": "SU-a", "unit_type": "FULLTEXT_PARAGRAPH",
         "text": "ABL1 V299L emerged during dasatinib therapy in chronic myeloid leukemia."},
        {"source_unit_id": "SU-b", "unit_type": "FULLTEXT_SENTENCE",
         "text": "Imatinib remains the standard first line option for most patients."},
        {"source_unit_id": "SU-c", "unit_type": "TABLE_CELL", "text": "V299L"},
        {"source_unit_id": "SU-d", "unit_type": "FULLTEXT_PARAGRAPH", "text": ""},
    ]

    def ranking(units, cand=candidate) -> str:
        return sus.select(sus.SourceUnitSelectionInput.from_candidate(cand, "pmid:1", units),
                          top_k=TOP_K).ranking_hash

    reference = ranking(base)
    checks: dict[str, Any] = {}

    permutations = [base[i:] + base[:i] for i in range(len(base))]
    checks["input_order_permutations"] = {
        "variants": len(permutations),
        "ranking_hashes_identical": all(ranking(p) == reference for p in permutations),
    }
    checks["repeat_runs"] = {
        "runs": 10,
        "ranking_hashes_identical": all(ranking(base) == reference for _ in range(10)),
    }
    nfd = [{**u, "text": unicodedata.normalize("NFD", u["text"])} for u in base]
    checks["unicode_nfc_vs_nfd"] = {"ranking_hashes_identical": ranking(nfd) == reference}
    upper = [{**u, "text": u["text"].upper()} for u in base]
    checks["case_folding"] = {"ranking_hashes_identical": ranking(upper) == reference}
    punct = [{**u, "text": u["text"].replace(".", " ...").replace(" ", "  ")} for u in base]
    checks["punctuation_and_whitespace"] = {"ranking_hashes_identical": ranking(punct) == reference}
    duplicated = base + [{**base[0], "source_unit_id": "SU-a2"}]
    dup_result = sus.select(
        sus.SourceUnitSelectionInput.from_candidate(candidate, "pmid:1", duplicated), top_k=TOP_K)
    checks["duplicate_units"] = {
        "both_present_and_ordered_by_id":
            list(dup_result.selected_source_unit_ids)[:2] == ["SU-a", "SU-a2"],
    }
    empty = sus.select(sus.SourceUnitSelectionInput.from_candidate(candidate, "pmid:1", []))
    checks["empty_document"] = {"status": empty.status,
                                "selected": list(empty.selected_source_unit_ids)}
    no_signal = sus.select(sus.SourceUnitSelectionInput.from_candidate(
        candidate, "pmid:1",
        [{"source_unit_id": "SU-x", "unit_type": "FULLTEXT_PARAGRAPH",
          "text": "Weather conditions were recorded by the site staff every morning."}]))
    checks["document_without_signal"] = {"status": no_signal.status}
    checks["ranking_drift"] = 0 if all(
        v.get("ranking_hashes_identical", True) for v in checks.values()
        if isinstance(v, dict)) else 1
    return {"selector_version": sus.SELECTOR_VERSION, "checks": checks}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Selector fino a Gemma, e su fetch live.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--skip-gemma", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=0.34)
    args = parser.parse_args(argv)

    write_json(args.report_dir / "robustness_tests.json", robustness_report())
    print("robustezza: scritta")

    cache, manifest, bundles, candidates = load_context()
    units_cache: dict[str, list[dict[str, Any]]] = {}

    def units_of(document_id: str) -> list[dict[str, Any]]:
        if document_id not in units_cache:
            units_cache[document_id] = cache.source_units_for_record(dict(manifest[document_id]))
        return units_cache[document_id]

    sample = stratified_sample(bundles, units_of)
    print(f"campione: {len(sample)} bundle")

    comparison: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    if not args.skip_gemma:
        for bundle in sample:
            document_id = bundle["document_id"]
            candidate = candidates[bundle["candidate_id"]]
            units = units_of(document_id)
            by_id = {u["source_unit_id"]: u for u in units}
            gold_units = [by_id[u] for u in bundle.get("source_unit_ids") or [] if u in by_id]

            selection = sus.SourceUnitSelectionInput.from_candidate(candidate, document_id, units)
            result = sus.select(selection, top_k=TOP_K)
            selector_units = [by_id[u] for u in result.selected_source_unit_ids if u in by_id]

            entry = {
                "bundle_id": bundle["bundle_id"], "document_id": document_id,
                "document_units": len(units),
                "gold_unit_ids": list(bundle.get("source_unit_ids") or []),
                "selector_unit_ids": list(result.selected_source_unit_ids),
                "overlap": len(set(result.selected_source_unit_ids)
                               & set(bundle.get("source_unit_ids") or [])),
                "gold": ask_gemma(candidate, bundle["bundle_id"], gold_units) if gold_units else {"gemma_reached": False},
                "selector": ask_gemma(candidate, bundle["bundle_id"], selector_units) if selector_units else {"gemma_reached": False},
            }
            comparison.append(entry)
            print(f"  {bundle['bundle_id']}: gold={entry['gold'].get('decision')} "
                  f"selector={entry['selector'].get('decision')} overlap={entry['overlap']}")

        # §26 — finestra di contesto, su un sottoinsieme.
        for bundle in sample[-3:]:
            document_id = bundle["document_id"]
            candidate = candidates[bundle["candidate_id"]]
            units = units_of(document_id)
            index = {u["source_unit_id"]: i for i, u in enumerate(units)}
            selection = sus.SourceUnitSelectionInput.from_candidate(candidate, document_id, units)
            selected = sus.select(selection, top_k=TOP_K).selected_source_unit_ids
            positions = sorted({index[u] for u in selected if u in index})
            widened = sorted({p for i in positions for p in (i - 1, i, i + 1)
                              if 0 <= p < len(units)})
            window_units = [units[p] for p in widened]
            window_rows.append({
                "bundle_id": bundle["bundle_id"],
                "single_unit_count": len(positions),
                "neighbor_window_count": len(window_units),
                "single_unit_chars": sum(len(units[p].get("text") or "") for p in positions),
                "neighbor_window_chars": sum(len(u.get("text") or "") for u in window_units),
                "neighbor_window": ask_gemma(candidate, bundle["bundle_id"], window_units),
            })
            print(f"  finestra {bundle['bundle_id']}: "
                  f"{len(positions)} -> {len(window_units)} unità")

    write_json(args.report_dir / "gemma_comparison.json", {
        "top_k": TOP_K,
        "sample_size": len(sample),
        "sampling": f"stratificato per dimensione documento, fino a {SAMPLE_PER_BUCKET} per fascia",
        "gold_bundles": rates([c["gold"] for c in comparison]),
        "selector": rates([c["selector"] for c in comparison]),
        "mean_overlap_with_gold": round(
            statistics.mean(c["overlap"] for c in comparison), 3) if comparison else None,
        "per_case": comparison,
        "neighbor_window": {
            "cases": window_rows,
            "single_vs_window": rates([w["neighbor_window"] for w in window_rows]),
        },
    })

    # §33 — documenti riscaricati dall'API, mai letti dalla cache.
    live_rows: list[dict[str, Any]] = []
    if not args.skip_gemma:
        live_targets = [b for b in sample if b["document_id"].startswith("pmid:")][:2] + \
                       [b for b in sample if b["document_id"].startswith("pmcid:")][:1]
        for bundle in live_targets:
            document_id = bundle["document_id"]
            kind, _, value = document_id.partition(":")
            candidate = candidates[bundle["candidate_id"]]
            scratch = Path(tempfile.mkdtemp(prefix="mtb-selector-live-"))
            try:
                fetch_cache = AuthorizedDocumentCache(root=scratch, network=True,
                                                      delay_seconds=args.delay_seconds)
                resolver = {"pmid": fetch_cache.resolve_pmid,
                            "pmcid": fetch_cache.resolve_pmc}[kind]
                record = resolver(value)
                read_only = cache_runtime.ReadOnlyDocumentCache(scratch)
                fresh = read_only.source_units_for_record(dict(record))
                selection = sus.SourceUnitSelectionInput.from_candidate(candidate, document_id, fresh)
                result = sus.select(selection, top_k=TOP_K)
                by_id = {u["source_unit_id"]: u for u in fresh}
                chosen = [by_id[u] for u in result.selected_source_unit_ids if u in by_id]
                live_rows.append({
                    "bundle_id": bundle["bundle_id"], "document_id": document_id,
                    "fetch_success": bool(record.get("local_cache_path")),
                    "fresh_source_units": len(fresh),
                    "selector_status": result.status,
                    "selected_unit_ids": list(result.selected_source_unit_ids),
                    "selected_are_from_fresh_document": all(
                        u in by_id for u in result.selected_source_unit_ids),
                    "overlap_with_gold": len(set(result.selected_source_unit_ids)
                                             & set(bundle.get("source_unit_ids") or [])),
                    "gemma": ask_gemma(candidate, bundle["bundle_id"], chosen) if chosen else {"gemma_reached": False},
                })
                print(f"  live {document_id}: {len(fresh)} unità -> "
                      f"{result.status} -> {live_rows[-1]['gemma'].get('decision')}")
            finally:
                shutil.rmtree(scratch, ignore_errors=True)

    write_json(args.report_dir / "live_fetch_cases.json", {
        "cases": len(live_rows),
        "all_selected_units_come_from_the_fetched_document": all(
            r["selected_are_from_fresh_document"] for r in live_rows) if live_rows else None,
        "rows": live_rows,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
