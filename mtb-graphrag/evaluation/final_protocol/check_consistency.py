"""Controlli di consistenza pre-freeze.

Verifica che il protocollo descriva il repository reale. Non esegue valutazioni,
non chiama modelli, non tocca la rete. Ogni check stampa PASS o FAIL con il
valore osservato: un FAIL è un blocco, non un avviso.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_ROOT = REPO_ROOT.parent
RUNTIME_COMMIT = "f52bbf5920c14324953be849e666bc84571957e9"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str) -> None:
    RESULTS.append((name, passed, detail))


def _json(relative: str) -> Any:
    return json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))


def _jsonl(relative: str) -> list[dict[str, Any]]:
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(GIT_ROOT), *args],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def check_runtime_unmodified() -> None:
    """Il runtime deve essere byte-identico a f52bbf5."""
    diff = _git("diff", "--stat", RUNTIME_COMMIT, "--", "mtb-graphrag/backend")
    check("runtime_unmodified", diff == "", diff or "nessuna differenza in mtb-graphrag/backend")


#: Percorsi introdotti da questa fase. Sono aggiunte, non modifiche di storico,
#: e vanno esclusi dal confronto con il commit di runtime.
PROTOCOL_PATHS = (
    "mtb-graphrag/docs/final_evaluation/",
    "mtb-graphrag/evaluation/final_protocol/",
)


def check_historical_artifacts_untouched() -> None:
    """Nessun artefatto storico di valutazione modificato."""
    tracked = _git(
        "diff", "--name-only", RUNTIME_COMMIT, "--",
        "mtb-graphrag/evaluation", "mtb-graphrag/benchmarks", "mtb-graphrag/docs",
    )
    changed = [
        line for line in tracked.splitlines()
        if line.strip() and not line.startswith(PROTOCOL_PATHS)
    ]
    check("historical_artifacts_untouched", not changed,
          f"{len(changed)} file tracciati modificati: {changed[:5]}")


def check_new_files_are_additive() -> None:
    """I file del protocollo sono aggiunte, non sovrascritture."""
    untracked = _git("ls-files", "--others", "--exclude-standard",
                     "mtb-graphrag/evaluation/final_protocol",
                     "mtb-graphrag/docs/final_evaluation").splitlines()
    added = sorted(line for line in untracked if line.strip())
    check("protocol_files_are_new", bool(added), f"{len(added)} nuovi file: {added}")


def check_declared_benchmark_hash() -> None:
    """Lo SHA-256 dichiarato del benchmark CaseContext deve corrispondere al file."""
    manifest = _json("evaluation/rq4_casecontext_robustness/frozen_benchmark_manifest.json")
    raw = (REPO_ROOT / "evaluation/rq4_casecontext_robustness/benchmark.jsonl").read_bytes()
    declared = manifest["benchmark_sha256"]
    observed_raw = hashlib.sha256(raw).hexdigest()
    observed_lf = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    matched = declared in (observed_raw, observed_lf)
    how = "raw" if declared == observed_raw else ("normalized-LF" if declared == observed_lf else "NESSUNA")
    check("casecontext_benchmark_hash_matches", matched,
          f"dichiarato={declared[:16]}… osservato({how})")


def check_selector_gold_hash_agreement() -> None:
    """Il gold del corpus indipendente ha lo stesso hash in tutti gli artefatti."""
    values = {
        "corpus_inventory": _json(
            "evaluation/sourceunit_selector_independent/corpus_inventory.json")["gold_annotation_hash"],
        "gold_manifest": _json(
            "evaluation/sourceunit_selector_independent/gold_annotation_manifest.json")["gold_annotation_hash"],
        "selector_metrics": _json(
            "evaluation/sourceunit_selector_independent/selector_metrics.json")["gold_hash"],
        "denominator_analysis": _json(
            "evaluation/sourceunit_selector_final_validation/denominator_analysis.json")["gold_hash"],
    }
    unique = set(values.values())
    check("selector_gold_hash_agreement", len(unique) == 1,
          f"{len(unique)} valore/i distinti su {len(values)} artefatti")


def check_denominators_reproducible() -> None:
    """I 9 casi positivi e gli 11 zero-direct devono derivare dal gold, non essere asseriti."""
    gold = _json("evaluation/sourceunit_selector_independent/gold_annotation_manifest.json")
    per_case = gold["per_case"]
    positive = sum(1 for counts in per_case.values() if counts.get("DIRECTLY_RELEVANT", 0) > 0)
    zero_direct = len(per_case) - positive
    direct_units = sum(counts.get("DIRECTLY_RELEVANT", 0) for counts in per_case.values())
    partial_units = sum(counts.get("PARTIALLY_RELEVANT", 0) for counts in per_case.values())
    declared = _json("evaluation/sourceunit_selector_final_validation/denominator_analysis.json")
    ok = (
        positive == declared["positive_cases"]
        and zero_direct == declared["zero_direct_cases"]
        and len(per_case) == declared["total_cases"]
        and direct_units == 29
        and partial_units == 49
    )
    check("independent_corpus_denominators_reproducible", ok,
          f"positivi={positive} zero-direct={zero_direct} direct_units={direct_units} partial_units={partial_units}")


def check_overall_vs_conditional_hit_rate() -> None:
    """HitRate@5 complessivo e condizionale devono essere coerenti: 9/20 = 0.45."""
    metrics = _json("evaluation/sourceunit_selector_independent/selector_metrics.json")
    overall = metrics["strategies"]["feature_selector:direct"]["hit_rate@5"]
    declared = _json("evaluation/sourceunit_selector_final_validation/denominator_analysis.json")
    conditional = declared["conditional_selector_hit_rate_at_5"]
    positive = declared["positive_cases"]
    total = declared["total_cases"]
    ok = abs(overall - positive / total) < 1e-9 and abs(conditional - 1.0) < 1e-9
    check("hit_rate_denominators_consistent", ok,
          f"overall={overall} ({positive}/{total}), conditional={conditional} ({positive}/{positive})")


def check_testbed_a_composition() -> None:
    """La composizione dichiarata del testbed A deve sommare a 55 e usare casi esistenti."""
    casecontext = _json("evaluation/rq4_casecontext_robustness/frozen_benchmark_manifest.json")["categories"]
    independent_total = _json(
        "evaluation/sourceunit_selector_independent/corpus_inventory.json")["valid_pair_count"]
    total = sum(casecontext.values()) + independent_total
    check("testbed_a_totals_55", total == 55,
          f"{sum(casecontext.values())} CaseContext + {independent_total} independent = {total}")


def check_runtime_repository_version() -> None:
    """Il runtime deve leggere graph_candidate_repository/2.0 e non importare la v3."""
    data_access = (REPO_ROOT / "backend/research_pipeline/data_access.py").read_text(encoding="utf-8")
    uses_v2 = "graph_candidate_repository/2.0/candidates.jsonl" in data_access
    importers = [
        path for path in (REPO_ROOT / "backend/research_pipeline").rglob("*.py")
        if "tests" not in path.parts
        and path.name != "kg_retrieval_v3.py"
        and "kg_retrieval_v3" in path.read_text(encoding="utf-8")
    ]
    check("runtime_reads_gca_2_0", uses_v2, "data_access.py punta al repository 2.0")
    check("runtime_does_not_import_gca_v3", not importers,
          f"{len(importers)} moduli non-test importano kg_retrieval_v3")


def check_oncokb_not_integrated() -> None:
    """RQ5 va classificata FUTURE WORK solo se OncoKB non è davvero nel runtime."""
    metrics = _json("evaluation/rq3_oncokb_fallback/aggregate_metrics.json")
    ok = (
        metrics["oncokb_integrated_into_runtime"] is False
        and metrics["pilot_executed"] is False
        and metrics["queries_executed"] == 0
    )
    check("oncokb_not_in_runtime", ok, f"reason={metrics['reason']}")


def check_negative_polarity_denominator() -> None:
    """Il denominatore della polarità negativa deve derivare dal repository."""
    recheck = _json("evaluation/final_deliverability/source_polarity_recheck.json")
    scan = recheck["probe_hard_cases"]["repository_scan"]
    ok = (
        scan["total"] == 46864
        and scan["negative"] == 1936
        and scan["promoted"] == 0
        and scan["primary"] == 0
    )
    check("negative_polarity_denominator", ok,
          f"total={scan['total']} negative={scan['negative']} promoted={scan['promoted']} primary={scan['primary']}")


def check_live_replay_contract() -> None:
    """Il contratto LIVE/REPLAY dichiarato deve corrispondere allo scorecard."""
    contract = _json("evaluation/live_runtime_integration/runtime_contract.json")
    scorecard = _json("evaluation/live_runtime_integration/final_scorecard.json")
    ok = (
        contract["live"]["top_k"] == scorecard["k"] == 5
        and contract["replay"]["network_access"] is False
        and scorecard["replay_network_fetch_count"] == 0
        and scorecard["replay_selector_calls"] == 0
        and scorecard["LIVE_uses_frozen_bundle_for_selection"] is False
    )
    check("live_replay_contract_consistent", ok,
          f"K={scorecard['k']} replay_network={scorecard['replay_network_fetch_count']} "
          f"replay_selector={scorecard['replay_selector_calls']}")


def check_per_stage_latency_instrumented() -> None:
    """La latenza per stage deve essere già registrata dal runtime."""
    orchestrator = (REPO_ROOT / "backend/research_pipeline/orchestrator.py").read_text(encoding="utf-8")
    check("per_stage_duration_recorded", "duration_ms" in orchestrator,
          "orchestrator.py registra duration_ms per stage")


def check_manifest_hashes_current() -> None:
    """Gli hash congelati devono corrispondere ai file attuali."""
    hashes = _json("evaluation/final_protocol/dataset_hashes.json")
    stale: list[str] = []
    for corpus_id, entry in hashes["corpora"].items():
        for relative, declared in entry["files"].items():
            raw = (REPO_ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
            if hashlib.sha256(raw).hexdigest() != declared:
                stale.append(f"{corpus_id}:{relative}")
    check("dataset_hashes_current", not stale, f"{len(stale)} file divergenti")


def check_hashes_are_platform_independent() -> None:
    """Gli hash devono coincidere con quelli calcolabili dal blob git (LF)."""
    hashes = _json("evaluation/final_protocol/dataset_hashes.json")
    sample = next(iter(hashes["corpora"].values()))
    relative, declared = next(iter(sample["files"].items()))
    blob = subprocess.run(
        ["git", "-C", str(GIT_ROOT), "show", f"HEAD:mtb-graphrag/{relative}"],
        capture_output=True, check=True,
    ).stdout.replace(b"\r\n", b"\n")
    check("hashes_match_git_blob", hashlib.sha256(blob).hexdigest() == declared,
          f"campione {relative}")


def main() -> int:
    check_runtime_unmodified()
    check_historical_artifacts_untouched()
    check_new_files_are_additive()
    check_declared_benchmark_hash()
    check_selector_gold_hash_agreement()
    check_denominators_reproducible()
    check_overall_vs_conditional_hit_rate()
    check_testbed_a_composition()
    check_runtime_repository_version()
    check_oncokb_not_integrated()
    check_negative_polarity_denominator()
    check_live_replay_contract()
    check_per_stage_latency_instrumented()
    check_manifest_hashes_current()
    check_hashes_are_platform_independent()

    failed = [name for name, passed, _ in RESULTS if not passed]
    width = max(len(name) for name, _, _ in RESULTS)
    for name, passed, detail in RESULTS:
        print(f"[{'PASS' if passed else 'FAIL'}] {name:<{width}}  {detail}")
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
