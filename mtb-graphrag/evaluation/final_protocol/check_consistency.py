"""Controlli di consistenza pre-freeze.

Verifica che il protocollo descriva il repository reale. Non esegue valutazioni,
non chiama modelli, non tocca la rete. Ogni check stampa PASS o FAIL con il
valore osservato: un FAIL è un blocco, non un avviso.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_ROOT = REPO_ROOT.parent
RUNTIME_COMMIT = "3d2251f82a586535f79f3d0b3725c16330c365ba"
#: Runtime storico, sostituito nel riallineamento pre-freeze. Serve ancora:
#: i sette artefatti held-out ne portano il timbro di costruzione.
BUILT_UNDER_RUNTIME_COMMIT = "f52bbf5920c14324953be849e666bc84571957e9"

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
    """Il runtime deve essere byte-identico al commit dichiarato."""
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
    """I file del protocollo sono aggiunte, mai sovrascritture di storico.

    Il confronto è contro il commit di runtime: nessuno dei percorsi introdotti
    da questa fase deve esistere là. Non si guardano i file non tracciati,
    perché una volta committati non lo sono più.
    """
    existing_at_runtime = _git("ls-tree", "-r", "--name-only", RUNTIME_COMMIT,
                               *PROTOCOL_PATHS).splitlines()
    overwritten = sorted(line for line in existing_at_runtime if line.strip())
    current = _git("ls-files", *PROTOCOL_PATHS).splitlines()
    tracked = sorted(line for line in current if line.strip())
    check("protocol_files_are_additive", not overwritten and bool(tracked),
          f"{len(tracked)} file tracciati, {len(overwritten)} preesistenti al runtime")


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


def check_no_aggregate_55() -> None:
    """L'aggregato 55 di 1.0 deve essere sparito da protocollo e specifiche.

    35 casi di routing e 20 coppie di grounding non sono la stessa unità
    sperimentale: un denominatore 55 non ha significato.
    """
    offenders: list[str] = []

    # Nessun corpus può dichiarare 55 casi: sarebbe l'aggregato reintrodotto.
    for entry in _json("evaluation/final_protocol/dataset_manifest.json")["corpora"]:
        if entry["counts"].get("n_cases") == 55:
            offenders.append(f"dataset_manifest:{entry['corpus_id']}")

    # Il divieto di aggregazione deve essere scritto, non solo sottinteso.
    schemas = _json("evaluation/final_protocol/result_schemas.json")
    if "no_cross_testbed_aggregation" not in schemas["rules"]:
        offenders.append("result_schemas: manca la regola di non aggregazione")
    if "aggregation_prohibition" not in schemas["RQ4_selective_execution"]:
        offenders.append("result_schemas: RQ4 senza divieto di aggregazione")

    metrics = _json("evaluation/final_protocol/metrics_registry.json")
    if "rule_no_aggregation" not in metrics:
        offenders.append("metrics_registry: manca rule_no_aggregation")

    # RQ4 deve avere due tabelle distinte ed etichettate, non una sola.
    tables = schemas["RQ4_selective_execution"]["tables"]
    if len(tables) != 2 or {t["independence_level"] for t in tables} != {
        "DEVELOPMENT_REGRESSION", "HELD_OUT"
    }:
        offenders.append("result_schemas: RQ4 non separa DEV e HELD_OUT")

    check("no_aggregate_55_denominator", not offenders,
          f"{len(offenders)} problemi: {offenders or 'nessuno'}")


def check_protocol_version() -> None:
    """Tutte le specifiche devono dichiarare la stessa versione di protocollo."""
    expected = "mtb-graphrag-final-evaluation/1.1"
    observed: dict[str, str] = {}
    for relative in (
        "evaluation/final_protocol/dataset_manifest.json",
        "evaluation/final_protocol/dataset_hashes.json",
        "evaluation/final_protocol/split_manifest.json",
        "evaluation/final_protocol/failure_taxonomy.json",
        "evaluation/final_protocol/metrics_registry.json",
        "evaluation/final_protocol/success_criteria.json",
        "evaluation/final_protocol/result_schemas.json",
        "evaluation/final_protocol/reliability_subset.json",
        "evaluation/final_protocol/protocol_hash.json",
        "evaluation/final_protocol/heldout/heldout_manifest.json",
        "evaluation/final_protocol/heldout/heldout_hashes.json",
    ):
        observed[relative] = _json(relative)["protocol_version"]
    wrong = {k: v for k, v in observed.items() if v != expected}
    check("protocol_version_is_1_1", not wrong, f"{len(wrong)} file divergenti su {len(observed)}")


def check_case_ids_unique() -> None:
    """Nessun case_id duplicato dentro o fra i corpus held-out."""
    architectural = [c["case_id"] for c in
                     _json("evaluation/final_protocol/heldout/architectural_challenge_cases.json")["cases"]]
    hostile = [c["case_id"] for c in
               _json("evaluation/final_protocol/heldout/narrative_heldout_cases.json")["cases"]]
    control = [c["case_id"] for c in
               _json("evaluation/final_protocol/heldout/narrative_heldout_valid_control.json")["cases"]]
    everything = architectural + hostile + control
    check("heldout_case_ids_unique", len(set(everything)) == len(everything),
          f"{len(everything)} ID, {len(set(everything))} distinti")


def check_gold_records_paired() -> None:
    """Ogni caso deve avere esattamente un record di gold, e viceversa."""
    pairs = [
        ("architectural", "architectural_challenge_cases.json", "cases",
         "architectural_challenge_gold.json", "gold"),
        ("narrative_hostile", "narrative_heldout_cases.json", "cases",
         "narrative_heldout_gold.json", "gold"),
    ]
    problems: list[str] = []
    for label, case_file, case_key, gold_file, gold_key in pairs:
        cases = {c["case_id"] for c in
                 _json(f"evaluation/final_protocol/heldout/{case_file}")[case_key]}
        gold = {g["case_id"] for g in
                _json(f"evaluation/final_protocol/heldout/{gold_file}")[gold_key]}
        if cases != gold:
            problems.append(f"{label}: {len(cases ^ gold)} non appaiati")
    control = _json("evaluation/final_protocol/heldout/narrative_heldout_valid_control.json")
    if {c["case_id"] for c in control["cases"]} != {g["case_id"] for g in control["gold"]}:
        problems.append("narrative_control: non appaiati")
    check("gold_records_paired", not problems, "; ".join(problems) or "tutti i casi hanno un gold")


def check_heldout_created_after_freeze() -> None:
    """L'held-out deve essere stato creato dopo il congelamento del runtime."""
    manifest = _json("evaluation/final_protocol/heldout/heldout_manifest.json")
    created = datetime.fromisoformat(manifest["creation_timestamp"])
    frozen = datetime.fromisoformat(manifest["runtime_freeze_timestamp"])
    cases = _json("evaluation/final_protocol/heldout/architectural_challenge_cases.json")["cases"]
    flags_ok = all(
        c["created_after_runtime_freeze"] and not c["system_output_observed_before_creation"]
        for c in cases
    )
    check("heldout_created_after_runtime_freeze", created > frozen and flags_ok,
          f"runtime {frozen.isoformat()} -> creazione {created.isoformat()}")


def check_heldout_overlap_documented() -> None:
    """L'overlap con lo sviluppo deve essere calcolato e senza copie sostanziali."""
    overlap = _json("evaluation/final_protocol/heldout/overlap_report.json")
    ok = (
        not overlap["exact_text_overlap"]
        and not overlap["normalized_text_overlap"]
        and not overlap["case_id_collisions"]
        and not overlap["substantive_overlap"]
        and all(not ids for ids in overlap["candidate_overlap_by_corpus"].values())
    )
    check("heldout_overlap_documented_and_clean", ok,
          f"verdict={overlap['overlap_verdict']}, boilerplate={len(overlap['boilerplate_overlap'])}")


def check_reliability_subset_explicit() -> None:
    """Il reliability subset deve essere un elenco di ID, non una regola."""
    subset = _json("evaluation/final_protocol/reliability_subset.json")
    architectural = {c["case_id"] for c in
                     _json("evaluation/final_protocol/heldout/architectural_challenge_cases.json")["cases"]}
    from_heldout = set(subset["by_source"]["HELDOUT_ARCHITECTURAL_35"])
    ok = (
        subset["materialized_before_execution"]
        and len(subset["case_ids"]) == subset["n_cases"] == 10
        and len(set(subset["case_ids"])) == 10
        and from_heldout <= architectural
    )
    check("reliability_subset_materialized", ok,
          f"{subset['n_cases']} casi × {subset['runs_per_case']} run = {subset['n_runs']}")


def check_schemas_declare_denominators() -> None:
    """Ogni tabella dei Risultati deve dichiarare un denominatore."""
    schemas = _json("evaluation/final_protocol/result_schemas.json")
    text = json.dumps(schemas, ensure_ascii=False).upper()
    missing = [
        key for key in ("RQ1_REPRESENTATION_FIDELITY", "RQ2_B_SOURCEUNIT_RETRIEVAL",
                        "RQ3_AUTHORITY_SEPARATION", "RQ4_SELECTIVE_EXECUTION")
        if key not in text
    ]
    has_denominator = "DENOMINATOR" in text and schemas["rules"]["denominator_mandatory"]
    check("result_schemas_declare_denominators", not missing and bool(has_denominator),
          f"tabelle mancanti: {missing or 'nessuna'}")


def check_no_fabricated_results() -> None:
    """Gli schemi non devono contenere valori numerici di risultato."""
    schemas = _json("evaluation/final_protocol/result_schemas.json")
    forbidden_keys = {"RATE", "ERROR_COUNT", "CI95", "OBSERVED_CORRECT_PATH",
                      "CORRECT_PATH_RATE", "DELTA", "FULL_SYSTEM", "ABLATION"}
    offenders: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in forbidden_keys and isinstance(value, (int, float)):
                    offenders.append(f"{path}.{key}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(schemas, "result_schemas")
    check("no_fabricated_result_values", not offenders, f"{len(offenders)} celle precompilate")


def check_grounded_review_approvable() -> None:
    """Tutti e dieci i casi grounded devono superare la revisione meccanica."""
    review = _json("evaluation/final_protocol/heldout/grounded_review.json")
    ok = review["verdict"] == "ALL_GROUNDED_CASES_APPROVABLE" and not review["requires_revision"]
    check("grounded_cases_mechanically_approvable", ok,
          f"{review['n_approvable']}/{review['n_cases']} — {review['verdict']}")


def check_ho_neg_01_intentional_discordance() -> None:
    """La discordanza direction/significance di HO-NEG-01 è voluta e va preservata."""
    review = _json("evaluation/final_protocol/heldout/grounded_review.json")
    row = next(r for r in review["rows"] if r["CASE_ID"].startswith("HO-NEG-01"))
    ok = (
        row["GCA_EVIDENCE_DIRECTION"] == "Does Not Support"
        and row["GCA_SIGNIFICANCE"] == "Sensitivity/Response"
        and row["EXPECTED_DIRECTION_MATCH"]
        and any(k.startswith("HO-NEG-01") for k in review["intentional_discordance"])
    )
    check("ho_neg_01_discordance_preserved", ok,
          f"direction={row['GCA_EVIDENCE_DIRECTION']}, significance={row['GCA_SIGNIFICANCE']}")


def check_narrative_single_primary_class() -> None:
    """Ogni caso ostile ha una sola classe primaria; le secondarie sono registrate."""
    cases = _json("evaluation/final_protocol/heldout/narrative_heldout_cases.json")["cases"]
    gold = {g["case_id"]: g for g in
            _json("evaluation/final_protocol/heldout/narrative_heldout_gold.json")["gold"]}
    problems = [
        case["case_id"] for case in cases
        if case.get("primary_mutation_count") != 1
        or case["primary_mutation_type"] != case["mutation_type"]
        or gold[case["case_id"]]["primary_mutation_type"] != case["mutation_type"]
        or "secondary_mutations" not in case
    ]
    with_secondary = sum(1 for case in cases if case["secondary_mutations"])
    check("narrative_single_primary_class", not problems,
          f"{len(cases)} casi, {with_secondary} con secondarie dichiarate, {len(problems)} problemi")


def check_adversarial_primary_gold() -> None:
    """I 5 adversarial devono dichiarare l'endpoint valutato, non lasciarlo implicito."""
    gold = _json("evaluation/final_protocol/heldout/architectural_challenge_gold.json")["gold"]
    adversarial = [g for g in gold if g["category"] == "ADVERSARIAL_CASECONTEXT"]
    ok = len(adversarial) == 5 and all(
        g["primary_gold"] == "HARD_ARCHITECTURAL_INVARIANT"
        and g["retrieval_path_is_scored"] is False
        and g["expected_retrieval_allowed"] is None
        and g.get("hard_property") and g.get("hard_observable")
        for g in adversarial
    )
    manifest = _json("evaluation/final_protocol/heldout/heldout_manifest.json")
    documented = "not the primary scored endpoint" in manifest.get("adversarial_scoring_note", "")
    check("adversarial_primary_gold_declared", ok and documented,
          f"{len(adversarial)} casi adversarial, nota nel manifest={documented}")


def check_revisions_documented() -> None:
    """Ogni caso revisionato deve dichiarare fase, contenuto precedente e motivo."""
    architectural = _json("evaluation/final_protocol/heldout/architectural_challenge_cases.json")["cases"]
    narrative = _json("evaluation/final_protocol/heldout/narrative_heldout_cases.json")["cases"]
    control = _json("evaluation/final_protocol/heldout/narrative_heldout_valid_control.json")["cases"]
    revised = [c for c in architectural + narrative if c.get("revision")]
    incomplete = [
        c["case_id"] for c in revised
        if not all(c["revision"].get(k) for k in ("revised_in", "previous_content", "reason"))
    ]
    controls_revised = [c["case_id"] for c in control if c.get("revision")]
    ok = (
        len(revised) == 6
        and not incomplete
        and not controls_revised
        and all(c["created_after_runtime_freeze"] for c in revised)
        and all(not c["system_output_observed_before_creation"] for c in revised)
    )
    check("revisions_documented_and_bounded", ok,
          f"{len(revised)} revisionati, {len(incomplete)} incompleti, "
          f"{len(controls_revised)} controlli toccati")


def check_reliability_subset_rename_documented() -> None:
    """Se un caso del subset è stato rinominato, il motivo deve essere registrato."""
    subset = _json("evaluation/final_protocol/reliability_subset.json")
    architectural = {c["case_id"] for c in
                     _json("evaluation/final_protocol/heldout/architectural_challenge_cases.json")["cases"]}
    renames = subset.get("renames_applied", {})
    resolvable = set(subset["by_source"]["HELDOUT_ARCHITECTURAL_35"]) <= architectural
    check("reliability_subset_renames_documented", bool(renames) and resolvable,
          f"{len([k for k in renames if k.startswith('HO-')])} rinomine documentate, "
          f"tutti gli ID risolvibili={resolvable}")


def check_protocol_seal_matches_files() -> None:
    """Il ``protocol_sha256`` registrato deve corrispondere ai file sul disco.

    I builder scrivono un ``generated_at``, quindi rieseguirli cambia il sigillo
    anche a contenuto invariato. Questo check trasforma quella deriva da
    silenziosa in visibile: se fallisce, o si ripristinano i file committati o
    si riesegue ``hash_protocol`` e si dichiara il nuovo sigillo.
    """
    recorded = _json("evaluation/final_protocol/protocol_hash.json")
    observed = {}
    for relative, declared in recorded["files"].items():
        raw = (REPO_ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
        observed[relative] = hashlib.sha256(raw).hexdigest()
    joined = "\n".join(f"{k}:{v}" for k, v in sorted(observed.items()))
    recomputed = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    drifted = [k for k, v in observed.items() if recorded["files"][k] != v]
    check("protocol_seal_matches_files", recomputed == recorded["protocol_sha256"],
          f"{len(drifted)} file derivati dal sigillo: {drifted[:3]}")


def check_no_final_run_executed() -> None:
    """Nessun risultato finale deve esistere: il freeze precede l'esecuzione.

    Prima del freeze questo controllo pretendeva anche ``frozen == false``.
    Ora quella condizione e' rovesciata: il protocollo e' congelato **e** non e'
    ancora stato eseguito, ed e' esattamente lo stato in cui deve trovarsi fra
    l'approvazione e la prima run.
    """
    results_dir = REPO_ROOT / "evaluation/final_evaluation"
    check("no_final_evaluation_executed", not results_dir.exists(),
          f"evaluation/final_evaluation esiste={results_dir.exists()}")


def check_protocol_is_frozen() -> None:
    """I tre sigilli devono dichiarare il freeze in modo coerente."""
    targets = {
        "protocol": "evaluation/final_protocol/protocol_hash.json",
        "heldout": "evaluation/final_protocol/heldout/heldout_manifest.json",
        "reliability": "evaluation/final_protocol/reliability_subset.json",
    }
    frozen, stamps, reviews = {}, set(), set()
    for label, relative in targets.items():
        payload = _json(relative)
        frozen[label] = payload.get("frozen")
        stamps.add(payload.get("freeze_timestamp"))
        reviews.add((payload.get("human_review") or {}).get("status"))
    ok = (all(frozen.values()) and len(stamps) == 1 and None not in stamps
          and reviews == {"ACCEPTED"})
    check("protocol_frozen", ok,
          f"frozen={frozen} timestamp unico={len(stamps) == 1} review={reviews}")


def check_human_review_accepted() -> None:
    """L'approvazione umana deve essere registrata e rintracciabile."""
    review = _json("evaluation/final_protocol/protocol_hash.json").get("human_review") or {}
    record = REPO_ROOT / "docs/final_evaluation/heldout_review.md"
    text = record.read_text(encoding="utf-8") if record.is_file() else ""
    ok = (
        review.get("status") == "ACCEPTED"
        and bool(review.get("reviewer"))
        and bool(review.get("date"))
        and "| review_status | **ACCEPTED** |" in text
        and "| esito finale | **ACCEPTED** |" in text
    )
    check("human_review_accepted", ok,
          f"status={review.get('status')} reviewer={review.get('reviewer')} "
          f"data={review.get('date')} record allineato={'ACCEPTED' in text}")


def check_no_result_observed_before_freeze() -> None:
    """Il refactor e il freeze devono precedere qualunque osservazione."""
    protocol = (REPO_ROOT / "docs/final_evaluation/final_evaluation_protocol.md").read_text(encoding="utf-8")
    declared = "final_results_observed_before_runtime_change = false" in protocol
    results_dir = REPO_ROOT / "evaluation/final_evaluation"
    check("final_results_observed_before_freeze_false", declared and not results_dir.exists(),
          f"dichiarazione nel protocollo={declared}, directory risultati={results_dir.exists()}")


def check_post_freeze_immutability_declared() -> None:
    """La regola che vincola il post-freeze deve essere scritta, non sottintesa."""
    protocol = (REPO_ROOT / "docs/final_evaluation/final_evaluation_protocol.md").read_text(encoding="utf-8")
    check("post_freeze_immutability_declared",
          "Regola di immutabilità post-freeze" in protocol,
          "regola presente nel protocollo")


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


def check_historical_regression_contract() -> None:
    """Lo scorecard storico resta coerente, come infrastruttura di regressione.

    Non e' piu' un contratto fra due modalita' del runtime: e' l'integrita'
    dell'harness che riproduce gli esperimenti congelati. Lo scorecard e' un
    artefatto storico e non viene riscritto, quindi conserva i nomi di allora.
    """
    contract = _json("evaluation/live_runtime_integration/runtime_contract.json")
    scorecard = _json("evaluation/live_runtime_integration/final_scorecard.json")
    ok = (
        contract["live"]["top_k"] == scorecard["k"] == 5
        and contract["replay"]["network_access"] is False
        and scorecard["replay_network_fetch_count"] == 0
        and scorecard["replay_selector_calls"] == 0
        and scorecard["LIVE_uses_frozen_bundle_for_selection"] is False
    )
    check("historical_regression_contract_consistent", ok,
          f"K={scorecard['k']} network={scorecard['replay_network_fetch_count']} "
          f"selector={scorecard['replay_selector_calls']} (artefatto storico)")


# --- Riallineamento pre-freeze al runtime canonico unico ---------------------


def check_protocol_declares_canonical_runtime() -> None:
    """Ogni specifica normativa deve puntare al runtime finale, non al precedente."""
    wrong = {}
    for relative in (
        "evaluation/final_protocol/dataset_manifest.json",
        "evaluation/final_protocol/dataset_hashes.json",
        "evaluation/final_protocol/split_manifest.json",
        "evaluation/final_protocol/failure_taxonomy.json",
        "evaluation/final_protocol/metrics_registry.json",
        "evaluation/final_protocol/success_criteria.json",
        "evaluation/final_protocol/result_schemas.json",
        "evaluation/final_protocol/reliability_subset.json",
        "evaluation/final_protocol/protocol_hash.json",
    ):
        observed = _json(relative)["runtime_commit"]
        if observed != RUNTIME_COMMIT:
            wrong[relative] = observed
    check("protocol_runtime_is_canonical", not wrong,
          f"{len(wrong)} specifiche divergenti; atteso {RUNTIME_COMMIT[:12]}")


def check_heldout_keeps_build_provenance() -> None:
    """I sette artefatti sigillati conservano il timbro del runtime di costruzione.

    Non e' un'incoerenza: e' provenance. Riscriverla falsificherebbe un gold
    gia' congelato e romperebbe la riproducibilita' byte-identica del bundle.
    """
    stamped = []
    for name in ("architectural_challenge_cases", "architectural_challenge_gold",
                 "narrative_heldout_cases", "narrative_heldout_gold",
                 "narrative_heldout_valid_control", "grounded_review"):
        payload = _json(f"evaluation/final_protocol/heldout/{name}.json")
        stamped.append(payload.get("runtime_commit") == BUILT_UNDER_RUNTIME_COMMIT)
    check("heldout_build_provenance_preserved", all(stamped),
          f"{sum(stamped)}/{len(stamped)} artefatti con il timbro di costruzione")


def check_canonical_user_mode_count() -> None:
    """Il runtime deve esporre una sola modalita' richiedibile."""
    execution_mode = (REPO_ROOT / "backend/research_pipeline/execution_mode.py").read_text(encoding="utf-8")
    routes = (REPO_ROOT / "backend/api/research_routes.py").read_text(encoding="utf-8")
    one_requestable = "REQUESTABLE_MODES: tuple[str, ...] = (CANONICAL_MODE,)" in execution_mode
    no_api_field = "execution_mode: str" not in routes
    check("canonical_user_mode_count_is_1", one_requestable and no_api_field,
          f"REQUESTABLE_MODES=1: {one_requestable}, campo API assente: {no_api_field}")


def check_no_primary_live_vs_replay_table() -> None:
    """La tabella di confronto fra modalita' non deve piu' essere un risultato."""
    schemas = _json("evaluation/final_protocol/result_schemas.json")
    absent = "LIVE_vs_REPLAY_properties" not in schemas
    documented = "LIVE_vs_REPLAY_properties" in schemas.get("removed_in_prefreeze_alignment", {})
    check("primary_live_vs_replay_table_absent", absent and documented,
          f"assente={absent}, rimozione documentata={documented}")


def check_canonical_and_historical_schemas() -> None:
    """I due schemi devono esistere e stare in classi di risultato diverse."""
    schemas = _json("evaluation/final_protocol/result_schemas.json")
    classes = schemas.get("result_classes", {})
    canonical = "CANONICAL_RUNTIME_OPERATIONAL" in schemas
    historical = "HISTORICAL_REGRESSION_REPRODUCIBILITY" in schemas
    separated = (
        "CANONICAL_RUNTIME_OPERATIONAL" in classes.get("PRIMARY", [])
        and "HISTORICAL_REGRESSION_REPRODUCIBILITY" in classes.get("SECONDARY_APPENDIX", [])
    )
    check("canonical_and_historical_schemas_separated",
          canonical and historical and separated,
          f"canonical={canonical} historical={historical} separati={separated}")


def check_hard_criteria_realigned() -> None:
    """I criteri HARD devono misurare il runtime canonico, non il replay."""
    criteria = _json("evaluation/final_protocol/success_criteria.json")
    hard = {c["claim"] for c in criteria["hard_criteria"]}
    regression = {c["claim"] for c in criteria["historical_regression_integrity"]["criteria"]}
    required = {
        "canonical_frozen_bundle_dependency",
        "canonical_research_replay_dependency",
        "implicit_historical_fallback",
    }
    no_replay_in_hard = not any(claim.startswith("replay_") for claim in hard)
    check("hard_criteria_realigned",
          required <= hard and no_replay_in_hard and len(regression) == 2,
          f"HARD={len(hard)} storici={len(regression)} nuovi_presenti={required <= hard}")


def check_criterion_ids_are_stable() -> None:
    """Un identificatore designa un criterio e uno solo, per sempre.

    E' la proprieta' che rende confrontabili due revisioni pre-freeze dello
    stesso protocollo: se lo stesso ID cambiasse significato, una revisione che
    approva "H-J = 0/N" non direbbe piu' quale proprieta' fosse stata approvata.
    """
    criteria = _json("evaluation/final_protocol/success_criteria.json")
    hard = {c["id"]: c["claim"] for c in criteria["hard_criteria"]}
    heldout = {c["id"]: c["claim"] for c in criteria["heldout_specific_criteria"]}
    retired = {c["id"]: c for c in criteria["retired_criteria"]}
    historical = {c["id"]: c for c in criteria["historical_regression_integrity"]["criteria"]}

    expected_hard = {
        "H-A": "unverified_essential_mismatch_reaches_retrieval",
        "H-B": "wrong_quote_accepted",
        "H-C": "wrong_document_accepted",
        "H-D": "wrong_sourceunit_accepted",
        "H-E": "does_not_support_promoted",
        "H-F": "negative_source_primary_bucket",
        "H-G": "failed_narrative_presented",
        "H-H": "llm_changes_canonical_dossier",
        "H-K": "canonical_frozen_bundle_dependency",
        "H-O": "canonical_research_replay_dependency",
        "H-P": "implicit_historical_fallback",
    }
    expected_heldout = {
        "H-L": "forbidden_retrieval_on_incomplete_essential",
        "H-M": "forbidden_retrieval_on_out_of_domain",
        "H-N": "authority_transfer_from_declared_field",
    }

    ids = list(hard) + list(heldout) + list(retired) + list(historical)
    duplicates = sorted({i for i in ids if ids.count(i) > 1})

    ok = (
        hard == expected_hard
        and heldout == expected_heldout
        and not duplicates
        and retired["H-I"]["status"] == "RETIRED_FROM_PRIMARY"
        and retired["H-J"]["status"] == "RETIRED_FROM_PRIMARY"
        and retired["H-I"]["historical_successor"] == "R-1"
        and retired["H-J"]["historical_successor"] == "R-2"
        and historical["R-1"]["maps_from"] == "H-I"
        and historical["R-2"]["maps_from"] == "H-J"
        and "H-I" not in hard and "H-J" not in hard
    )
    check("criterion_ids_stable", ok,
          f"HARD={' '.join(sorted(hard))} ritirati={' '.join(sorted(retired))} "
          f"duplicati={duplicates or 'nessuno'}")


def check_retired_ids_not_reused() -> None:
    """Gli ID ritirati non devono ricomparire come criteri attivi."""
    criteria = _json("evaluation/final_protocol/success_criteria.json")
    retired_ids = {c["id"] for c in criteria["retired_criteria"]}
    active_ids = ({c["id"] for c in criteria["hard_criteria"]}
                  | {c["id"] for c in criteria["heldout_specific_criteria"]})
    reused = sorted(retired_ids & active_ids)
    policy = criteria.get("criteria_identifier_policy", {})
    declared = policy.get("principle") == "SUCCESS CRITERION IDs ARE STABLE AUDIT IDENTIFIERS"
    check("retired_ids_not_reused", not reused and declared,
          f"riusati={reused or 'nessuno'}, politica dichiarata={declared}")


def check_heldout_counts_unchanged() -> None:
    """Il refactor non deve aver toccato i corpora held-out."""
    arch = _json("evaluation/final_protocol/heldout/architectural_challenge_cases.json")
    hostile = _json("evaluation/final_protocol/heldout/narrative_heldout_cases.json")
    controls = _json("evaluation/final_protocol/heldout/narrative_heldout_valid_control.json")
    ok = arch["n_cases"] == 35 and hostile["n_cases"] == 20 and controls["n_cases"] == 5
    check("heldout_counts_unchanged", ok,
          f"architetturali={arch['n_cases']} ostili={hostile['n_cases']} controlli={controls['n_cases']}")


def check_heldout_bundle_seal_unchanged() -> None:
    """Il sigillo held-out deve corrispondere ai file attuali, byte per byte."""
    hashes = _json("evaluation/final_protocol/heldout/heldout_hashes.json")
    base = REPO_ROOT / "evaluation/final_protocol/heldout"
    stale = []
    for name, declared in hashes["files"].items():
        raw = (base / name).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(raw).hexdigest() != declared:
            stale.append(name)
    check("heldout_bundle_seal_intact", not stale,
          f"{len(hashes['files']) - len(stale)}/{len(hashes['files'])} file sigillati invariati")


def check_reliability_ids_stable() -> None:
    """Gli ID del sottoinsieme di affidabilita' non devono cambiare col runtime."""
    subset = _json("evaluation/final_protocol/reliability_subset.json")
    digest = hashlib.sha256("\n".join(subset["case_ids"]).encode("utf-8")).hexdigest()
    ok = digest == subset["case_ids_sha256"] and len(subset["case_ids"]) == 10
    check("reliability_subset_ids_stable", ok,
          f"n={len(subset['case_ids'])} sha={subset['case_ids_sha256'][:12]}")


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
    check_no_aggregate_55()
    check_protocol_version()
    check_case_ids_unique()
    check_gold_records_paired()
    check_heldout_created_after_freeze()
    check_heldout_overlap_documented()
    check_reliability_subset_explicit()
    check_schemas_declare_denominators()
    check_no_fabricated_results()
    check_grounded_review_approvable()
    check_ho_neg_01_intentional_discordance()
    check_narrative_single_primary_class()
    check_adversarial_primary_gold()
    check_revisions_documented()
    check_reliability_subset_rename_documented()
    check_protocol_seal_matches_files()
    check_no_final_run_executed()
    check_protocol_is_frozen()
    check_human_review_accepted()
    check_no_result_observed_before_freeze()
    check_post_freeze_immutability_declared()
    check_runtime_repository_version()
    check_oncokb_not_integrated()
    check_negative_polarity_denominator()
    check_historical_regression_contract()
    check_protocol_declares_canonical_runtime()
    check_heldout_keeps_build_provenance()
    check_canonical_user_mode_count()
    check_no_primary_live_vs_replay_table()
    check_canonical_and_historical_schemas()
    check_hard_criteria_realigned()
    check_criterion_ids_are_stable()
    check_retired_ids_not_reused()
    check_heldout_counts_unchanged()
    check_heldout_bundle_seal_unchanged()
    check_reliability_ids_stable()
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
