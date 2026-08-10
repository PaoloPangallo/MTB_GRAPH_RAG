"""Controlli di consistenza dell'emendamento A01.

Non esegue valutazioni, non chiama modelli, non tocca la rete e non scrive
nulla. Verifica due cose: che il protocollo padre sia rimasto intatto, e che
ogni scenario operativo sia vincolato a un'istanza concreta scelta senza
discrezionalita'.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
GIT_ROOT = REPO_ROOT.parent

PARENT_SHA = "83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889"
PARENT_FREEZE_COMMIT = "7b0b396b10d10794ac802325f8e7e2ff5ce33e28"
RUNTIME_COMMIT = "3d2251f82a586535f79f3d0b3725c16330c365ba"

#: File del protocollo padre che l'emendamento non puo' toccare.
PARENT_FILES = (
    "mtb-graphrag/evaluation/final_protocol/protocol_hash.json",
    "mtb-graphrag/evaluation/final_protocol/success_criteria.json",
    "mtb-graphrag/evaluation/final_protocol/result_schemas.json",
    "mtb-graphrag/evaluation/final_protocol/reliability_subset.json",
    "mtb-graphrag/evaluation/final_protocol/heldout/heldout_manifest.json",
    "mtb-graphrag/docs/final_evaluation/final_evaluation_protocol.md",
)

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


BINDINGS = _json("operational_scenario_bindings.json")
CONTRACT = _json("cache_seed_contract.json")
PARSER_FIX = _json("parser_failure_fixture.json")
SELECTOR_FIX = _json("selector_failure_fixture.json")
BY_ID = {s["scenario_id"]: s for s in BINDINGS["scenarios"]}


def check_parent_hash_exact() -> None:
    """Il protocollo padre deve essere ancora quello sigillato al freeze."""
    observed = json.loads(
        (REPO_ROOT / "evaluation/final_protocol/protocol_hash.json").read_text(encoding="utf-8")
    )["protocol_sha256"]
    check("parent_protocol_hash_exact", observed == PARENT_SHA,
          f"atteso {PARENT_SHA[:16]} osservato {observed[:16]}")


def check_parent_files_untouched() -> None:
    """Nessun file del protocollo padre puo' differire dal commit di freeze."""
    diff = subprocess.run(
        ["git", "-C", str(GIT_ROOT), "diff", "--name-only", PARENT_FREEZE_COMMIT, "--", *PARENT_FILES],
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
               check_selection_is_mechanical, check_fixtures_materialized,
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
