"""Materializzazione del reliability subset.

Il protocollo 1.0 definiva il sottoinsieme con una regola. Una regola è
sufficiente a impedire la scelta post-hoc solo finché nessuno la applica dopo
aver visto i risultati. Qui la regola viene **eseguita e congelata**: dopo il
freeze l'elenco degli ID non cambia, e non serve fidarsi di chi lo rieseguirà.

Regola, dichiarata prima dell'esecuzione:

* un caso per categoria dell'held-out architetturale, il primo ``case_id`` in
  ordine lessicografico — 7 casi;
* i primi tre ``case_id`` in ordine lessicografico fra i 9 casi positivi del
  corpus indipendente — 3 casi.

Totale 10 casi × 3 run = 30 run, il cui scopo è quantificare la varianza del
provider, non migliorare le metriche primarie.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = Path(__file__).resolve().parent / "reliability_subset.json"

PROTOCOL_VERSION = "mtb-graphrag-final-evaluation/1.1"
RUNTIME_COMMIT = "3d2251f82a586535f79f3d0b3725c16330c365ba"
#: Runtime sotto cui i corpora furono costruiti. Conservato come provenance: i
#: dati non sono cambiati, e' cambiato il runtime che li valutera'.
PREVIOUS_RUNTIME_COMMIT = "f52bbf5920c14324953be849e666bc84571957e9"
RUNS_PER_CASE = 3


def _json(relative: str) -> Any:
    return json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))


def build() -> dict[str, Any]:
    heldout = _json("evaluation/final_protocol/heldout/architectural_challenge_cases.json")
    by_category: dict[str, list[str]] = {}
    for case in heldout["cases"]:
        by_category.setdefault(case["category"], []).append(case["case_id"])

    architectural = [sorted(ids)[0] for _, ids in sorted(by_category.items())]

    gold = _json("evaluation/sourceunit_selector_independent/gold_annotation_manifest.json")
    positive = sorted(
        key for key, counts in gold["per_case"].items()
        if counts.get("DIRECTLY_RELEVANT", 0) > 0
    )
    grounding = positive[:3]

    case_ids = architectural + grounding
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("il reliability subset contiene ID duplicati")

    heldout_hashes = _json("evaluation/final_protocol/heldout/heldout_hashes.json")
    dataset_hashes = _json("evaluation/final_protocol/dataset_hashes.json")

    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "runtime_commit": RUNTIME_COMMIT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection_rule": (
            "primo case_id in ordine lessicografico per ciascuna delle 7 categorie di "
            "HELDOUT_ARCHITECTURAL_35, più i primi 3 case_id in ordine lessicografico "
            "fra i 9 casi positivi di SOURCEUNIT_SELECTOR_INDEPENDENT_20"
        ),
        "selection_seed": None,
        "selection_seed_note": (
            "nessun seed: la selezione è un ordinamento totale deterministico, non un "
            "campionamento casuale. Un seed suggerirebbe una casualità che non c'è."
        ),
        "materialized_before_execution": True,
        "runs_per_case": RUNS_PER_CASE,
        "n_cases": len(case_ids),
        "n_runs": len(case_ids) * RUNS_PER_CASE,
        "case_ids": case_ids,
        "by_source": {
            "HELDOUT_ARCHITECTURAL_35": architectural,
            "SOURCEUNIT_SELECTOR_INDEPENDENT_20_positive": grounding,
        },
        "purpose": "quantificare la varianza del provider LLM, che non espone un seed",
        "excluded_from": ["metriche primarie", "criteri HARD"],
        "renames_applied": {
            "revised_in": "1.1-review-1",
            "HO-AMB-01-abbreviation-collision": "HO-AMB-01-primary-site-ambiguity",
            "HO-CON-01-two-primary-diseases": "HO-CON-01-same-primary-conflicting-diagnoses",
            "note": (
                "Due casi del sottoinsieme sono stati rinominati perché il loro contenuto è "
                "cambiato in revisione e l'ID precedente sarebbe diventato fuorviante. La "
                "regola di selezione non è cambiata e continua a scegliere la stessa "
                "posizione lessicografica nella stessa categoria: nessun caso è stato "
                "sostituito, e in particolare nessuno è stato scelto in base al "
                "comportamento atteso del sistema."
            ),
        },
        "dataset_hash": {
            "heldout_bundle_sha256": heldout_hashes["heldout_bundle_sha256"],
            "dataset_bundle_sha256": dataset_hashes["dataset_bundle_sha256"],
        },
        "frozen": False,
    }
    payload["case_ids_sha256"] = hashlib.sha256(
        "\n".join(case_ids).encode("utf-8")).hexdigest()

    with OUT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return payload


if __name__ == "__main__":
    result = build()
    print(f"reliability subset: {result['n_cases']} casi × {result['runs_per_case']} run = {result['n_runs']} run")
    for case_id in result["case_ids"]:
        print(f"  {case_id}")
    print(f"case_ids_sha256: {result['case_ids_sha256']}")
