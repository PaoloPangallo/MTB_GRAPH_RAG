import json
import csv
import re
from pathlib import Path

# Assumiamo di essere eseguiti in backend/evaluation
import sys
sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.evaluation.objective_metrics import (
    calculate_therapeutic_match,
    calculate_evidence_grounding,
    calculate_safety
)
from backend.evaluation.compute_metrics import extract_pmids_from_report

RESULTS_DIR = Path("results")
BENCHMARK_CSV = Path("../benchmark/benchmark_papers_summary_30_v2.csv")

def extract_valid_pmids(report: str) -> list[str]:
    """Estrae la lista dei PMID verificati dal Knowledge Graph (sezione 5 del report GraphRAG)."""
    match = re.search(r'(?:Lista finale dei PMID|5\.\s+Lista).*?(?=\n\n|\Z)', report, re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    section = match.group(0)
    return re.findall(r'(\d{7,8})', section)

def main():
    # Carica metadati base
    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cases_meta = {r["case_id"]: r for r in reader}

    # Carica JSON dei risultati
    try:
        with open(RESULTS_DIR / "benchmark_results.json", "r", encoding="utf-8") as f:
            gr_base_results = json.load(f)
    except FileNotFoundError:
        print("Errore: benchmark_results.json mancante.")
        sys.exit(1)

    try:
        with open(RESULTS_DIR / "zeroshot_structured_results.json", "r", encoding="utf-8") as f:
            zs_results = json.load(f)
    except FileNotFoundError:
        print("Errore: zeroshot_structured_results.json mancante. Aspetto che finisca la generazione.")
        zs_results = []
        
    try:
        with open(RESULTS_DIR / "enricher_results.json", "r", encoding="utf-8") as f:
            enricher_results = json.load(f)
    except FileNotFoundError:
        enricher_results = []

    # Map per case_id
    gr_map = {r["case_id"]: r for r in gr_base_results}
    zs_map = {r["case_id"]: r for r in zs_results}
    en_map = {r["case_id"]: r for r in enricher_results}

    csv_rows = []

    for case_id in sorted(cases_meta.keys()):
        meta = cases_meta[case_id]
        expected_drug = meta["expected_drug"]
        
        row = {
            "case_id": case_id,
            "gene": meta["gene"],
            "variant": meta["variant"],
            "tumor": meta["tumor"],
            "expected_drug": expected_drug
        }
        
        # --- GraphRAG Base ---
        if case_id in gr_map:
            gr = gr_map[case_id]
            report = gr.get("report", "")
            valid_pmids = extract_valid_pmids(report)
            
            # Citazioni nel body
            citations = list(extract_pmids_from_report(report))
            
            row["gr_base_tm"] = calculate_therapeutic_match(report, expected_drug)
            row["gr_base_eg"] = calculate_evidence_grounding(citations, valid_pmids)
            row["gr_base_safety"] = calculate_safety(report, case_id)
            row["gr_base_valid_pmids"] = len(valid_pmids)
        else:
            row["gr_base_tm"] = row["gr_base_eg"] = row["gr_base_safety"] = row["gr_base_valid_pmids"] = None
            valid_pmids = [] # Fallback
            
        # --- Zero-Shot Structured ---
        if case_id in zs_map:
            zs = zs_map[case_id]
            struct = zs.get("structured_data", {})
            rec_drugs = struct.get("recommended_drugs", [])
            citations = struct.get("citations", [])
            
            row["zs_tm"] = calculate_therapeutic_match(rec_drugs, expected_drug)
            # Se la lista dei valid_pmids da GraphRAG è vuota (errore KB), il controllo fallback fallisce
            row["zs_eg"] = calculate_evidence_grounding(citations, valid_pmids) if valid_pmids else False
            row["zs_safety"] = calculate_safety(rec_drugs, case_id)
        else:
            row["zs_tm"] = row["zs_eg"] = row["zs_safety"] = None

        # --- GraphRAG + Enricher ---
        if case_id in en_map:
            en = en_map[case_id]
            report = en.get("report", "")
            # L'enricher dovrebbe usare gli stessi valid_pmids o li estraiamo
            en_valid_pmids = extract_valid_pmids(report)
            citations = list(extract_pmids_from_report(report))
            
            row["en_tm"] = calculate_therapeutic_match(report, expected_drug)
            row["en_eg"] = calculate_evidence_grounding(citations, en_valid_pmids)
            row["en_safety"] = calculate_safety(report, case_id)
        else:
            row["en_tm"] = row["en_eg"] = row["en_safety"] = None

        csv_rows.append(row)

    # Scrivi il CSV finale
    output_path = RESULTS_DIR / "three_way_comparison.csv"
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "case_id", "gene", "variant", "tumor", "expected_drug",
            "gr_base_tm", "gr_base_eg", "gr_base_safety", "gr_base_valid_pmids",
            "zs_tm",      "zs_eg",      "zs_safety",
            "en_tm",      "en_eg",      "en_safety"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"Salvato confronto a tre vie in {output_path}")

if __name__ == "__main__":
    main()
