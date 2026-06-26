import json
import requests
from pathlib import Path

# 1. Verifica struttura JSON
file_path = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results\ablation_graphrag_results.json")
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

print("=== Struttura JSON (primo caso) ===")
first_case = data[0]
print(f"Case ID: {first_case.get('case_id')}")
print(f"Keys presenti: {list(first_case.keys())}")
print(f"PMID estratti (cited_pmids_list): {first_case.get('cited_pmids_list')}")
print("===================================\n")

# 2. Verifica raggiungibilità NCBI
print("=== Verifica NCBI E-utilities ===")
try:
    response = requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=20537386&retmode=json",
        timeout=10
    )
    if response.status_code == 200:
        result = response.json()
        if "result" in result and "20537386" in result["result"]:
            print("[OK] NCBI E-utilities è raggiungibile e restituisce dati per il PMID di test.")
        else:
            print("[WARNING] NCBI raggiungibile, ma risposta inattesa.")
    else:
        print(f"[ERRORE] Status code: {response.status_code}")
except Exception as e:
    print(f"[ERRORE] Eccezione di rete: {e}")
print("===================================")
