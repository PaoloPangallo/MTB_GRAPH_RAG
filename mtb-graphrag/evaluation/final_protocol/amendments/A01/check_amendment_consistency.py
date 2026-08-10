"""Controlli di consistenza dell'emendamento A01.

Non esegue valutazioni, non chiama modelli, non tocca la rete e non scrive
nulla. Verifica due cose: che il protocollo padre sia rimasto intatto, e che
ogni scenario operativo sia vincolato a un'istanza concreta scelta senza
discrezionalita'.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
GIT_ROOT = REPO_ROOT.parent

PARENT_SHA = "83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889"
PARENT_FREEZE_COMMIT = "7b0b396b10d10794ac802325f8e7e2ff5ce33e28"
RUNTIME_COMMIT = "3d2251f82a586535f79f3d0b3725c16330c365ba"
BASE_AMENDMENT_COMMIT = "4cbaef06c510e5063e4962e9bc9d6d28e94fb4a9"

SOURCE_ARTIFACT_HASHES = {
    "benchmarks/mtb_evidence/document_grounded_claims/authorized_document_cache_pilot/"
    "document_manifest.jsonl":
        "ece9d25d74b3050f222343d3f31dc22d20d39d1883957f431c4280ef9326006b",
    "evaluation/document_cache_rebuild/manifest_inventory.json":
        "3b4df02f7fec680874036d715ac37392e096c0128240ca53e64636621f9de4cd",
    "evaluation/document_cache_rebuild/document_resolution_results.jsonl":
        "673c8aefc63d2dce598576f8ea85f20c92c601fd339a9822d9842f660e6ef4ea",
    "evaluation/sourceunit_selector_independent/final_scorecard.json":
        "03cf520f76e5746edbf119d86ee1ef145d96309f01decdec9d2e5add22dc1a70",
}

SCENARIOS = (
    "A_cache_hit", "B_cache_miss_success", "C_pmid_only_to_pmcid", "D_pmc_fulltext",
    "E_pmc_unavailable_abstract_degradation", "F_unseen_document",
    "G_document_unavailable", "H_parser_failure_fixture", "I_selector_failure_fixture",
)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str) -> None:
    RESULTS.append((name, passed, detail))


def _json(relative: str) -> Any:
    return json.loads((HERE / relative).read_text(encoding="utf-8"))


def _sha256_normalized(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _git_text(commit: str, relative: str) -> str:
    return subprocess.run(
        ["git", "-C", str(GIT_ROOT), "show", f"{commit}:mtb-graphrag/{relative}"],
        capture_output=True, text=True, check=True, encoding="utf-8",
    ).stdout


def _git_json(commit: str, relative: str) -> Any:
    return json.loads(_git_text(commit, relative))


BINDINGS = _json("operational_scenario_bindings.json")
CONTRACT = _json("cache_seed_contract.json")
PARSER_FIX = _json("parser_failure_fixture.json")
SELECTOR_FIX = _json("selector_failure_fixture.json")
BY_ID = {s["scenario_id"]: s for s in BINDINGS["scenarios"]}

DOCUMENT_MANIFEST = [
    json.loads(line)
    for line in (REPO_ROOT / (
        "benchmarks/mtb_evidence/document_grounded_claims/"
        "authorized_document_cache_pilot/document_manifest.jsonl"
    )).read_text(encoding="utf-8").splitlines()
    if line.strip()
]
DOCUMENT_RESOLUTION = {
    row["document_id"]: row
    for row in (
        json.loads(line)
        for line in (REPO_ROOT / "evaluation/document_cache_rebuild/document_resolution_results.jsonl")
        .read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
}
DOCUMENT_INVENTORY = {
    row["document_id"]: row
    for row in json.loads(
        (REPO_ROOT / "evaluation/document_cache_rebuild/manifest_inventory.json")
        .read_text(encoding="utf-8")
    )["documents"]
}
SELECTOR_SCORECARD = json.loads(
    (REPO_ROOT / "evaluation/sourceunit_selector_independent/final_scorecard.json")
    .read_text(encoding="utf-8")
)


def check_parent_hash_exact() -> None:
    """Ricalcola tutti i file del sigillo padre e il protocol hash aggregato."""
    frozen_seal = _git_json(PARENT_FREEZE_COMMIT, "evaluation/final_protocol/protocol_hash.json")
    current_seal = json.loads(
        (REPO_ROOT / "evaluation/final_protocol/protocol_hash.json").read_text(encoding="utf-8")
    )
    observed_files = {
        relative: _sha256_normalized(REPO_ROOT / relative)
        for relative in frozen_seal["files"]
    }
    joined = "\n".join(f"{name}:{digest}" for name, digest in sorted(observed_files.items()))
    recomputed = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    ok = (current_seal == frozen_seal
          and observed_files == frozen_seal["files"]
          and recomputed == frozen_seal["protocol_sha256"] == PARENT_SHA)
    check("parent_protocol_hash_exact", ok,
          f"atteso {PARENT_SHA[:16]} ricalcolato {recomputed[:16]} file={len(observed_files)}")


def check_parent_files_untouched() -> None:
    """Nessun file del protocollo padre puo' differire dal commit di freeze."""
    frozen_seal = _git_json(PARENT_FREEZE_COMMIT, "evaluation/final_protocol/protocol_hash.json")
    parent_files = [f"mtb-graphrag/{relative}" for relative in frozen_seal["files"]]
    parent_files.append("mtb-graphrag/evaluation/final_protocol/protocol_hash.json")
    diff = subprocess.run(
        ["git", "-C", str(GIT_ROOT), "diff", "--name-only", PARENT_FREEZE_COMMIT,
         "--", *parent_files],
        capture_output=True, text=True,
    ).stdout.split()
    check("parent_protocol_files_untouched", not diff, f"{len(diff)} file modificati: {diff}")


def check_runtime_untouched() -> None:
    diff = subprocess.run(
        ["git", "-C", str(GIT_ROOT), "diff", "--name-only", RUNTIME_COMMIT,
         "--", "mtb-graphrag/backend", "mtb-graphrag/frontend"],
        capture_output=True, text=True,
    ).stdout.split()
    check("runtime_untouched", not diff, f"{len(diff)} file modificati")


def check_nine_scenarios_unique() -> None:
    ids = [s["scenario_id"] for s in BINDINGS["scenarios"]]
    check("nine_scenarios_unique",
          len(ids) == 9 and len(set(ids)) == 9 and set(ids) == set(SCENARIOS),
          f"n={len(ids)} distinti={len(set(ids))}")


def check_ag_bound_to_identifiers() -> None:
    """Gli scenari A-G devono avere un'istanza documentale concreta."""
    missing = [s for s in SCENARIOS[:7] if not BY_ID[s].get("selected_document_id")]
    check("scenarios_a_to_g_bound", not missing, f"senza identificatore: {missing or 'nessuno'}")


def check_selection_is_mechanical() -> None:
    """Ogni selezione deve dichiarare regola, insieme eleggibile e indice 0."""
    bad = []
    for sid in SCENARIOS[:7]:
        s = BY_ID[sid]
        eligible = s.get("eligible_candidates") or []
        if not s.get("selection_rule") or not eligible or s.get("selection_index") != 0:
            bad.append(sid)
            continue
        chosen = (s.get("selected_document_id") or "")
        first = eligible[0]
        # il primo eleggibile deve essere quello scelto, in una delle sue forme
        if first not in {chosen, s.get("selected_pmid"), s.get("selected_pmcid"),
                         s.get("selected_case_id"), chosen.split(":", 1)[-1]}:
            bad.append(sid)
    check("selection_first_eligible_index_zero", not bad, f"non meccanici: {bad or 'nessuno'}")


def check_scenario_a_pubmed_abstract_mechanical() -> None:
    """A deriva dai contratti congelati, non da un identificatore hardcoded."""
    eligible = []
    for row in DOCUMENT_MANIFEST:
        resolution = DOCUMENT_RESOLUTION.get(row["document_id"], {})
        inventory = DOCUMENT_INVENTORY.get(row["document_id"], {})
        if (row["document_id"].startswith("pmid:")
                and row.get("availability") == "ABSTRACT_AVAILABLE"
                and row.get("source") == "NCBI E-utilities"
                and inventory.get("classification") == "EXPECTED_AVAILABLE"
                and bool(row.get("local_cache_path"))
                and resolution.get("payload_present") is True
                and resolution.get("parse_error") is None
                and int(resolution.get("with_text") or 0) > 0
                and "PubMedAbstractParser@1.0" in (resolution.get("parsers") or {})):
            eligible.append(row["document_id"])
    eligible.sort()

    a = BY_ID["A_cache_hit"]
    selected_row = next(
        (row for row in DOCUMENT_MANIFEST if row["document_id"] == a.get("selected_document_id")),
        {},
    )
    ok = (a.get("source_class") == "PUBMED_ABSTRACT"
          and a.get("eligible_candidates") == eligible
          and a.get("candidate_count") == len(eligible)
          and a.get("selection_index") == 0
          and bool(eligible)
          and a.get("selected_document_id") == eligible[0]
          and a.get("selected_pmid") == eligible[0].split(":", 1)[1]
          and a.get("selected_case_id") in (selected_row.get("candidate_ids") or []))
    check("scenario_a_pubmed_abstract_selected_mechanically", ok,
          f"eleggibili={len(eligible)} indice=0 selezionato={eligible[0] if eligible else None}")


def check_scenario_a_cache_contract_matches_selection() -> None:
    a = BY_ID["A_cache_hit"]
    contract = next(c for c in CONTRACT["contracts"] if c["scenario_id"] == "A_cache_hit")
    ok = (contract.get("baseline_manifest") == "AUTHORIZED_DOCUMENT_CACHE_43"
          and contract.get("ephemeral_cache") == "operational_cache_A"
          and contract.get("include_ids") == [a.get("selected_document_id")]
          and contract.get("exclude_ids") == []
          and contract.get("expected_network_fetch_count") == 0
          and "PRESENTE" in contract.get("expected_initial_state", ""))
    check("scenario_a_cache_seed_matches_mechanical_binding", ok,
          f"include_ids={contract.get('include_ids')} fetch={contract.get('expected_network_fetch_count')}")


def check_selection_sources_pinned() -> None:
    observed = {
        relative: _sha256_normalized(REPO_ROOT / relative)
        for relative in SOURCE_ARTIFACT_HASHES
    }
    ok = observed == SOURCE_ARTIFACT_HASHES
    changed = sorted(name for name, digest in observed.items()
                     if digest != SOURCE_ARTIFACT_HASHES[name])
    check("selection_source_artifacts_pinned", ok, f"drift={changed or 'nessuno'}")


def check_approved_b_to_h_unchanged() -> None:
    base_bindings = _git_json(
        BASE_AMENDMENT_COMMIT,
        "evaluation/final_protocol/amendments/A01/operational_scenario_bindings.json",
    )
    base_contract = _git_json(
        BASE_AMENDMENT_COMMIT,
        "evaluation/final_protocol/amendments/A01/cache_seed_contract.json",
    )
    approved = set(SCENARIOS[1:8])
    base_scenarios = {s["scenario_id"]: s for s in base_bindings["scenarios"]}
    base_contracts = {c["scenario_id"]: c for c in base_contract["contracts"]}
    current_contracts = {c["scenario_id"]: c for c in CONTRACT["contracts"]}
    changed = sorted(sid for sid in approved
                     if BY_ID[sid] != base_scenarios[sid]
                     or current_contracts[sid] != base_contracts[sid])
    parser_unchanged = PARSER_FIX == _git_json(
        BASE_AMENDMENT_COMMIT,
        "evaluation/final_protocol/amendments/A01/parser_failure_fixture.json",
    )
    check("approved_scenarios_b_to_h_unchanged", not changed and parser_unchanged,
          f"scenari modificati={changed or 'nessuno'} H_fixture_unchanged={parser_unchanged}")


def check_bf_shared_identity_documented() -> None:
    b = BY_ID["B_cache_miss_success"]
    f = BY_ID["F_unseen_document"]
    contracts = {c["scenario_id"]: c for c in CONTRACT["contracts"]}
    amendment = (HERE / "amendment.md").read_text(encoding="utf-8")
    required_one = ("B and F intentionally reuse the same document identity under isolated cache\n"
                    "states because they test different operational properties.")
    required_two = ("Operational scenarios are property tests and must not be interpreted as\n"
                    "statistically independent observations.")
    ok = (b["selected_document_id"] == f["selected_document_id"]
          and contracts[b["scenario_id"]]["ephemeral_cache"]
          != contracts[f["scenario_id"]]["ephemeral_cache"]
          and required_one in amendment and required_two in amendment)
    check("b_f_shared_identity_property_test_documented", ok,
          f"documento={b['selected_document_id']} cache_distinte="
          f"{contracts[b['scenario_id']]['ephemeral_cache'] != contracts[f['scenario_id']]['ephemeral_cache']}")


def check_fixtures_materialized() -> None:
    ok_h = (PARSER_FIX.get("fixture_id") == "FIX-PARSER-FAILED-01"
            and PARSER_FIX.get("expected_reason_code") == "PARSER_FAILED"
            and bool(PARSER_FIX.get("payload_sha256"))
            and PARSER_FIX.get("network_allowed") is False)
    ok_i = (SELECTOR_FIX.get("fixture_id") == "FIX-SELECTOR-FAILED-01"
            and SELECTOR_FIX.get("expected_reason_code") == "SOURCEUNIT_SELECTION_FAILED"
            and bool(SELECTOR_FIX.get("fixture_sha256"))
            and SELECTOR_FIX.get("gemma_allowed") is False)
    check("fixtures_h_and_i_materialized", ok_h and ok_i, f"H={ok_h} I={ok_i}")


def check_zero_direct_is_not_selector_failure() -> None:
    negative = SELECTOR_SCORECARD["negative_case_metrics"]
    declared = SELECTOR_FIX.get("zero_direct_distinction") or {}
    ok = (negative.get("zero_direct_relevant_cases") == 11
          and negative.get("selector_selected_units_in_zero_direct_cases") == 11
          and declared.get("zero_direct_cases") == 11
          and declared.get("selected_in_zero_direct_cases") == 11
          and declared.get("zero_direct_implies_selector_failure") is False)
    check("zero_direct_does_not_imply_selector_failure", ok,
          f"zero-direct={negative.get('zero_direct_relevant_cases')} "
          f"selezionati={negative.get('selector_selected_units_in_zero_direct_cases')}")


def check_selector_failure_reachability_fixture() -> None:
    """La fixture I deve rispecchiare i branch statici del runtime canonico."""
    selector_source = (
        REPO_ROOT / "backend/research_pipeline/experimental/sourceunit_selector.py"
    ).read_text(encoding="utf-8")
    live_source = (
        REPO_ROOT / "backend/research_pipeline/retrieval/live_sourceunit_selection.py"
    ).read_text(encoding="utf-8")
    orchestrator_source = (
        REPO_ROOT / "backend/research_pipeline/orchestrator.py"
    ).read_text(encoding="utf-8")
    analysis = SELECTOR_FIX.get("reachability_analysis") or {}
    state = SELECTOR_FIX.get("input_state") or {}
    units = SELECTOR_FIX.get("fixture_payload") or []
    candidate = state.get("candidate") or {}
    def normalize_text(value: Any) -> str:
        value = unicodedata.normalize("NFC", str(value or "")).casefold()
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s><]", " ", value)).strip()

    def tokenize(value: Any) -> list[str]:
        return re.findall(r"[a-z0-9]+(?:[><][a-z0-9]+)*", normalize_text(value), re.I)

    query_tokens = {
        token
        for field in ("disease", "biomarkers", "interventions")
        for item in (candidate.get(field) or [])
        for token in tokenize(item.get("label"))
        if token
    }
    unit_token_sets = [set(tokenize(unit.get("text"))) for unit in units]
    fixture_tokens = set().union(*unit_token_sets) if unit_token_sets else set()
    candidate_id = candidate.get("candidate_id")
    association = state.get("association") or {}
    resolution = state.get("resolution_record") or {}
    seeded_as = SELECTOR_FIX.get("seeded_as") or {}
    i_contract = next(
        c for c in CONTRACT["contracts"] if c["scenario_id"] == "I_selector_failure_fixture"
    )
    document_ids = {unit.get("document_id") for unit in units}
    feature_labels = [
        normalize_text(item.get("label"))
        for field in ("disease", "interventions")
        for item in (candidate.get(field) or [])
    ] + [
        re.sub(r"[^a-z0-9]", "", normalize_text(item.get("label")))
        for item in (candidate.get("biomarkers") or [])
    ]
    no_feature_match = all(
        not label or not all(part in tokens for part in label.split())
        for tokens in unit_token_sets for label in feature_labels
    )
    ok = (analysis.get("classification") == "NATURALLY_REACHABLE_FROM_INPUT_STATE"
          and analysis.get("final_result_used_for_fixture_selection") is False
          and "min_score: float = 0.0" in selector_source
          and "eligible = [u for u in ranked if u.score_total > min_score]" in selector_source
          and "total = (WEIGHT_LEXICAL * lexical[index] + bonus) * prior" in selector_source
          and "if not selection.selected_source_unit_ids:" in live_source
          and "if canonical and association.get(\"available_bundles\") and not selection.get(\"selected_papers\")" in orchestrator_source
          and "if canonical and selection_failed:" in orchestrator_source
          and bool(units)
          and all((unit.get("text") or "").strip() for unit in units)
          and not (query_tokens & fixture_tokens)
          and no_feature_match
          and state.get("required_sourceunits") == len(units) == 1
          and bool(state.get("required_text_state"))
          and bool(state.get("paper_selection_state"))
          and resolution.get("resolved") is True
          and association.get("available_bundles")
          and association.get("candidate_id") == resolution.get("candidate_id") == candidate_id
          and document_ids == {resolution.get("document_id")}
          and association["available_bundles"][0].get("document_id") == resolution.get("document_id")
          and association["available_bundles"][0].get("bundle_id") == resolution.get("bundle_id")
          and seeded_as.get("document_id") == resolution.get("document_id")
          and i_contract.get("include_ids") == [resolution.get("document_id")]
          and i_contract.get("exclude_ids") == []
          and i_contract.get("network_allowed") is False
          and i_contract.get("expected_network_fetch_count") == 0
          and SELECTOR_FIX.get("expected_selector_status") == "NO_RELEVANT_SOURCE_UNIT"
          and SELECTOR_FIX.get("expected_selected_ids") == []
          and SELECTOR_FIX.get("expected_selected_papers") == []
          and SELECTOR_FIX.get("expected_reason_code") == "SOURCEUNIT_SELECTION_FAILED")
    check("scenario_i_matches_static_runtime_reachability", ok,
          f"classe={analysis.get('classification')} sourceunits={len(units)}")


def check_fixture_hashes_match_payload() -> None:
    h = hashlib.sha256(PARSER_FIX["fixture_payload"].encode("utf-8")).hexdigest()
    blob = json.dumps(SELECTOR_FIX["fixture_payload"], sort_keys=True, ensure_ascii=False)
    i = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    ok = h == PARSER_FIX["payload_sha256"] and i == SELECTOR_FIX["fixture_sha256"]
    check("fixture_hashes_match_payload", ok, f"H={h[:12]} I={i[:12]}")


def check_cache_contract_complete() -> None:
    covered = {c["scenario_id"] for c in CONTRACT["contracts"]}
    check("cache_seed_contract_nine_of_nine", covered == set(SCENARIOS),
          f"{len(covered)}/9 · mancanti: {sorted(set(SCENARIOS) - covered) or 'nessuno'}")


def check_isolated_caches() -> None:
    policy = CONTRACT["isolation_policy"]
    caches = [c["ephemeral_cache"] for c in CONTRACT["contracts"]]
    ok = (policy["shared_mutable_cache"] is False
          and policy["reads_previous_scenario_output"] is False
          and policy["mutates_baseline"] is False
          and policy["reused_by_later_scenario"] is False
          and len(set(caches)) == 9)
    check("no_shared_mutable_operational_cache", ok, f"cache distinte={len(set(caches))}")


def check_ephemeral_caches_not_created() -> None:
    """Le directory effimere non devono esistere prima dell'esecuzione."""
    existing = [c["ephemeral_cache"] for c in CONTRACT["contracts"]
                if (REPO_ROOT / c["ephemeral_cache"]).exists()]
    check("ephemeral_caches_not_created_yet", not existing, f"presenti: {existing or 'nessuna'}")


def check_unseen_ids_exact() -> None:
    f = BY_ID["F_unseen_document"]
    ok = f["selected_pmid"] == "24088390" and f["selected_pmcid"] == "PMC4157820"
    check("unseen_ids_exact", ok, f"pmid={f['selected_pmid']} pmcid={f['selected_pmcid']}")


def check_g_is_not_degradation_fixture() -> None:
    g = BY_ID["G_document_unavailable"]
    e = BY_ID["E_pmc_unavailable_abstract_degradation"]
    unavailable = set(CONTRACT["baseline"]["unavailable_ids"])
    ok = (g["selected_document_id"] not in unavailable
          and g["selected_document_id"] != e["selected_document_id"])
    check("g_distinct_from_degradation", ok,
          f"G={g['selected_document_id']} E={e['selected_document_id']}")


def check_no_final_outcome_used() -> None:
    ok = (BINDINGS["current_cache_used_for_selection"] is False
          and BINDINGS["final_results_used_for_selection"] is False
          and _json("provenance.json")["final_results_observed_before_amendment"] is False)
    check("no_final_outcome_used_for_selection", ok, "selezione da sole fonti pre-finali")


def check_final_runs_absent() -> None:
    check("no_final_evaluation_executed",
          not (REPO_ROOT / "evaluation/final_evaluation").exists(),
          "evaluation/final_evaluation assente")


def check_amendment_not_frozen() -> None:
    frozen = _json("provenance.json")["frozen"]
    check("amendment_a01_not_frozen", frozen is False, f"frozen={frozen}")


def check_classification() -> None:
    ok = BINDINGS["classification"] == "OPERATIONAL CONFORMANCE / PROPERTY TESTS"
    check("operational_classification_declared", ok, BINDINGS["classification"])


def main() -> int:
    for fn in (check_parent_hash_exact, check_parent_files_untouched, check_runtime_untouched,
               check_nine_scenarios_unique, check_ag_bound_to_identifiers,
               check_selection_is_mechanical, check_scenario_a_pubmed_abstract_mechanical,
               check_scenario_a_cache_contract_matches_selection,
               check_selection_sources_pinned, check_approved_b_to_h_unchanged,
               check_bf_shared_identity_documented,
               check_fixtures_materialized, check_zero_direct_is_not_selector_failure,
               check_selector_failure_reachability_fixture,
               check_fixture_hashes_match_payload, check_cache_contract_complete,
               check_isolated_caches, check_ephemeral_caches_not_created,
               check_unseen_ids_exact, check_g_is_not_degradation_fixture,
               check_no_final_outcome_used, check_final_runs_absent,
               check_amendment_not_frozen, check_classification):
        fn()

    failed = [name for name, passed, _ in RESULTS if not passed]
    width = max(len(name) for name, _, _ in RESULTS)
    for name, passed, detail in RESULTS:
        print(f"[{'PASS' if passed else 'FAIL'}] {name:<{width}}  {detail}")
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
