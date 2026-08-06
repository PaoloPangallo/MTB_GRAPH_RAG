"""Piano di query OncoKB e analisi di interrogabilità (§13, §15).

Uso::

    python -m evaluation.build_rq3_plan

**Non effettua alcuna chiamata a OncoKB.** Determina, dai soli dati locali,
quali candidate prive di PMID sarebbero interrogabili e con quale chiave, e
produce ``query_plan.json``. Se la stratificazione richiesta dal protocollo non è
satisfacibile, il piano lo dichiara esplicitamente invece di sostituirla con una
approssimazione.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from evaluation.rq1.compare import load_candidates

REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = (
    REPO_ROOT / "benchmarks" / "mtb_evidence" / "document_grounded_claims"
    / "graph_candidate_repository" / "2.0" / "candidates.jsonl"
)
OUT = REPO_ROOT / "evaluation" / "rq3_oncokb_fallback"

#: Chiavi minime degli endpoint di annotazione OncoKB, dalla documentazione
#: ufficiale (api.oncokb.org, consultata il 2026-08-06).
#: `/annotate/mutations/byProteinChange` richiede hugoSymbol|entrezGeneId e
#: accetta `alteration` e `tumorType`. Senza alteration la risposta non
#: identifica un'evidenza specifica.
REQUIRED_FOR_ANNOTATION = ("gene", "alteration")
RECOMMENDED_FOR_ANNOTATION = ("disease",)


def _labels(entities, kind=None) -> list[str]:
    out = []
    for entity in entities or []:
        if kind and entity.get("type") != kind:
            continue
        if entity.get("label"):
            out.append(str(entity["label"]))
    return out


def profile(candidate: dict) -> dict:
    biomarkers = candidate.get("biomarkers") or []
    return {
        "gene": _labels(biomarkers, "Gene"),
        "alteration": _labels(biomarkers, "Variant"),
        "disease": _labels(candidate.get("disease")),
        "intervention": _labels(candidate.get("interventions")),
        "direction": candidate.get("direction"),
    }


def queryability(p: dict) -> tuple[str, list[str]]:
    """``(stato, motivi)`` di interrogabilità verso OncoKB."""
    missing = [k for k in REQUIRED_FOR_ANNOTATION if not p[k]]
    if missing:
        return "NOT_QUERYABLE", [f"missing:{k}" for k in missing]
    weak = [k for k in RECOMMENDED_FOR_ANNOTATION if not p[k]]
    if weak:
        return "QUERYABLE_WITHOUT_TUMOR_TYPE", [f"missing:{k}" for k in weak]
    return "QUERYABLE", []


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    candidates = list(load_candidates(CANDIDATES))

    without_pmid = [
        c for c in candidates
        if not any(i.get("pmid") for i in c.get("document_identifiers") or [])
    ]

    states = Counter()
    by_rule = Counter()
    reasons = Counter()
    feature_profiles = Counter()
    queryable_ids: list[str] = []

    for candidate in without_pmid:
        p = profile(candidate)
        state, why = queryability(p)
        states[state] += 1
        by_rule[(candidate["materialization_rule_id"], state)] += 1
        for reason in why:
            reasons[reason] += 1
        feature_profiles["/".join(
            k if p[k] else "-" for k in ("gene", "alteration", "disease", "intervention")
        )] += 1
        if state != "NOT_QUERYABLE":
            queryable_ids.append(candidate["candidate_id"])

    #: Strati richiesti da §15 del protocollo, verificati sui dati reali.
    required_strata = {
        "gene_alteration_disease": lambda p: p["gene"] and p["alteration"] and p["disease"],
        "gene_disease_no_alteration": lambda p: p["gene"] and p["disease"] and not p["alteration"],
        "intervention_evaluation": lambda p: bool(p["intervention"]),
        "therapy_discovery": lambda p: bool(p["gene"]) and not p["intervention"],
        "sensitivity": lambda p: "sensitiv" in str(p["direction"]).lower() or "response" in str(p["direction"]).lower(),
        "resistance": lambda p: "resistance" in str(p["direction"]).lower(),
        "nct_without_pmid": lambda p: False,  # calcolato a parte
        "no_identifier_at_all": lambda p: False,  # calcolato a parte
    }
    stratum_counts = {name: 0 for name in required_strata}
    for candidate in without_pmid:
        p = profile(candidate)
        for name, predicate in required_strata.items():
            if predicate(p):
                stratum_counts[name] += 1
    stratum_counts["nct_without_pmid"] = sum(
        1 for c in without_pmid
        if any(i.get("nct") for i in c.get("document_identifiers") or [])
    )
    stratum_counts["no_identifier_at_all"] = sum(
        1 for c in without_pmid if not (c.get("document_identifiers") or [])
    )

    unsatisfiable = sorted(name for name, count in stratum_counts.items() if count == 0)

    plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "calls_executed": 0,
        "note": "Nessuna chiamata a OncoKB è stata effettuata da questo script.",
        "oncokb": {
            "data_version": "v7.4 (07/31/2026)",
            "api_version": "v1.6.0",
            "instance_required": "https://www.oncokb.org (production, autenticata)",
            "docs_consulted_at": "2026-08-06",
        },
        "target_population": {
            "candidates_total": len(candidates),
            "candidates_without_pmid": len(without_pmid),
            "share_without_pmid": round(len(without_pmid) / len(candidates), 4),
        },
        "queryability": {
            "states": dict(states),
            "missing_key_reasons": dict(reasons),
            "feature_profiles_gene_alteration_disease_intervention": dict(feature_profiles),
            "queryable_candidate_count": len(queryable_ids),
        },
        "queryability_by_rule": {f"{rule} :: {state}": n for (rule, state), n in by_rule.items()},
        "required_strata_from_protocol": stratum_counts,
        "unsatisfiable_strata": unsatisfiable,
        "pilot_feasible": len(queryable_ids) > 0,
        "planned_sample_size": min(20, len(queryable_ids)),
        "planned_sample_candidate_ids": sorted(queryable_ids)[:20],
        "call_budget": {"max_calls": 20, "executed": 0},
    }
    (OUT / "query_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(json.dumps({
        "candidates_without_pmid": plan["target_population"]["candidates_without_pmid"],
        "queryability": plan["queryability"]["states"],
        "queryable_candidate_count": plan["queryability"]["queryable_candidate_count"],
        "unsatisfiable_strata": unsatisfiable,
        "pilot_feasible": plan["pilot_feasible"],
    }, indent=2))
    print("[rq3] feature profiles:", json.dumps(plan["queryability"]
          ["feature_profiles_gene_alteration_disease_intervention"], indent=1))
    print("[rq3] strata:", json.dumps(stratum_counts, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
