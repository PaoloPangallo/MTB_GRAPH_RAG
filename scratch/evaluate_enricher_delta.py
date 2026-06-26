"""
Evaluate Enricher Delta — Script di valutazione sui 3 casi critici.
Esegue la pipeline base, recupera i dati OncoKB live, integra i dati (human-in-the-loop simulation)
e confronta i punteggi del Judge per calcolare il delta score.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

# Configura PYTHONPATH per trovare i moduli di backend
sys.path.append(str(Path(__file__).resolve().parents[1] / "mtb-graphrag"))

from langchain_core.messages import HumanMessage, SystemMessage
from backend.pipeline.state import MTBState
from backend.pipeline.graph import run_pipeline
from backend.pipeline.agents.judge import llm_as_judge
from backend.pipeline.llm import llm

BENCHMARK_CSV = Path(__file__).resolve().parents[1] / "mtb-graphrag" / "backend" / "benchmark" / "benchmark_papers_summary_30_v2.csv"
TUMOR_MAP = {
    "NSCLC":               "Lung Adenocarcinoma",
    "Colorectal Cancer":   "Colorectal Cancer",
}

INTEGRATOR_SYSTEM = """Sei un oncologo clinico esperto per il Molecular Tumor Board.
Ti viene fornito un report MTB di base e una lista di nuovi trattamenti/evidenze estratti in tempo reale da OncoKB.
Il tuo compito è integrare in modo scientifico ed elegante i dati OncoKB all'interno del report di base.

Regole di integrazione:
1. Nella Sezione 1 (Variante e ESCAT), se OncoKB riporta un livello di evidenza superiore o indica che la variante ha un significato terapeutico live, aggiorna la classificazione citando esplicitamente OncoKB.
2. Nella Sezione 2 (Terapia raccomandata), inserisci i nuovi farmaci raccomandati da OncoKB (con i relativi companion diagnostic CDx se indicati) specificando il livello di evidenza OncoKB (es. LEVEL_1, LEVEL_2) e inserendo inline i PMID forniti nel JSON [PMID: XXXXX].
3. Se un farmaco precedentemente raccomandato nel report base è in realtà non corretto o controindicato alla luce delle evidenze (es. Cetuximab/Panitumumab da soli per KRAS G12C in CRC senza inibitore di KRAS), rimuovilo o correggilo.
4. Nella Sezione 5 (PMID verificati), elenca anche i nuovi PMID provenienti da OncoKB.

Ritorna esclusivamente il report finale arricchito in formato Markdown, mantenendo la struttura in italiano e lo stile clinico formale.
"""

CRITICAL_CASES = ["BENCH-013", "BENCH-018", "BENCH-027"]


def get_case_row(case_id: str) -> dict | None:
    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["case_id"] == case_id:
                return row
    return None


def csv_row_to_state(row: dict, enrich: bool) -> MTBState:
    tumor = TUMOR_MAP.get(row["tumor"], row["tumor"])
    return {
        "gene":               row["gene"] if row["gene"] not in ("MMR", "TMB") else "",
        "variant":            row["variant"],
        "tumor_type":         tumor,
        "alteration_type":    row["alteration_type"],
        "therapy_line":       "first-line",
        "enrich_with_oncokb": enrich,
        "complexity":         "low",
        "variant_data":       {},
        "drug_candidates":    [],
        "trial_candidates":   [],
        "resistance_data":    [],
        "oncokb_enrichment":  [],
        "report":             "",
        "cited_pmids":        [],
        "escat_tier":         "",
    }


def main():
    print("=== INIZIO VALUTAZIONE DELTA ENRICHER ===")
    results = {}

    for case_id in CRITICAL_CASES:
        row = get_case_row(case_id)
        if not row:
            print(f"Caso {case_id} non trovato.")
            continue

        print(f"\nProcessing {case_id}: {row['gene']} {row['variant']} / {row['tumor']}")

        # 1. Esegui Pipeline Base
        state_base = csv_row_to_state(row, enrich=False)
        res_base = run_pipeline(state_base)
        report_base = res_base["report"]

        # Valuta report base
        score_base = llm_as_judge(report_base, {
            "gene": row["gene"],
            "variant": row["variant"],
            "tumor_type": state_base["tumor_type"],
        })

        # 2. Esegui Pipeline Enriched (recupera OncoKB)
        state_enriched = csv_row_to_state(row, enrich=True)
        res_enriched = run_pipeline(state_enriched)
        oncokb_data = res_enriched.get("oncokb_enrichment", [])

        print(f"  Trovati {len(oncokb_data)} elementi di enrichment in OncoKB.")

        # 3. Simula l'integrazione del Clinico (LLM)
        integration_msg = (
            f"Report Base:\n{report_base}\n\n"
            f"Dati di Arricchimento OncoKB (LEVEL_1/2):\n{json.dumps(oncokb_data, indent=2, ensure_ascii=False)}"
        )
        response = llm.invoke([
            SystemMessage(content=INTEGRATOR_SYSTEM),
            HumanMessage(content=integration_msg),
        ])
        report_enriched = response.content

        # Valuta report arricchito
        score_enriched = llm_as_judge(report_enriched, {
            "gene": row["gene"],
            "variant": row["variant"],
            "tumor_type": state_enriched["tumor_type"],
        })

        results[case_id] = {
            "gene": row["gene"],
            "variant": row["variant"],
            "tumor": row["tumor"],
            "base": {
                "report": report_base,
                "score": score_base,
            },
            "oncokb_raw": oncokb_data,
            "enriched": {
                "report": report_enriched,
                "score": score_enriched,
            },
        }

        print(f"  [Base] Score Totale: {score_base.get('score_totale')}")
        print(f"  [Enriched] Score Totale: {score_enriched.get('score_totale')}")
        delta = score_enriched.get("score_totale", 0) - score_base.get("score_totale", 0)
        print(f"  Delta Score: {delta:+.3f}")

    # Salva i risultati per l'analisi
    output_path = Path(__file__).resolve().parent / "enricher_evaluation_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nRisultati salvati in: {output_path}")


if __name__ == "__main__":
    main()
