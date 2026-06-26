import json
import pandas as pd
from pathlib import Path
import csv

# Import fetching functions from the existing script
from recalc_pertinence import CONDITIONS, RESULTS_DIR, check_pmids_in_ncbi, fetch_pubmed_abstracts

df_cases = pd.read_csv(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\benchmark\benchmark_papers_summary_30_v2.csv")
case_info = {}
for _, row in df_cases.iterrows():
    case_info[row["case_id"]] = {
        "gene": row["gene"],
        "variant": row["variant"],
        "tumor": row["tumor"]
    }

print("1. Caricamento risultati...")
all_pmids = set()
results = {}
for cond_name, filename in CONDITIONS.items():
    filepath = RESULTS_DIR / filename
    if not filepath.exists(): continue
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    results[cond_name] = data
    for case in data:
        pmids = {int(x) for x in case.get("cited_pmids_list", []) if str(x).strip().isdigit()}
        all_pmids.update(pmids)

print(f"2. Validazione di {len(all_pmids)} PMID su NCBI...")
valid_pmids = check_pmids_in_ncbi(all_pmids)

print(f"3. Scaricamento titoli per {len(valid_pmids)} PMID...")
pmid_metadata = fetch_pubmed_abstracts(valid_pmids)

print("4. Generazione del file CSV per la validazione manuale...")
out_csv = RESULTS_DIR / "manual_pertinence_evaluation.csv"

with open(out_csv, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "Architecture", 
        "Case_ID", 
        "Gene", 
        "Variant", 
        "Tumor", 
        "PMID", 
        "Title",
        "Pertinence_Score (0/1)"
    ])
    
    for cond_name, data in results.items():
        for case in data:
            case_id = case.get("case_id")
            info = case_info.get(case_id, {})
            gene = info.get("gene", "")
            variant = info.get("variant", "")
            tumor = info.get("tumor", "")
            
            pmids = {int(x) for x in case.get("cited_pmids_list", []) if str(x).strip().isdigit()}
            real_pmids = [p for p in pmids if p in pmid_metadata]
            
            for p in real_pmids:
                title = pmid_metadata[p]["title"]
                writer.writerow([
                    cond_name,
                    case_id,
                    gene,
                    variant,
                    tumor,
                    p,
                    title,
                    ""  # Colonna vuota per la valutazione manuale
                ])

print(f"File creato con successo in: {out_csv}")
