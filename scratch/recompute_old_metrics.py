import sys
import json
import shutil
from pathlib import Path

# Configura UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Path import backend
sys.path.append(str(Path(__file__).resolve().parents[1] / "mtb-graphrag"))

from backend.evaluation.compute_metrics import (
    extract_pmids_from_report,
    check_pmids_exist_in_kb
)

RESULTS_DIR = Path(__file__).resolve().parents[1] / "mtb-graphrag" / "backend" / "evaluation" / "results"
GRAPHRAG_JSON = RESULTS_DIR / "ablation_second_llm_graphrag_results.json"
VANILLA_JSON = RESULTS_DIR / "ablation_second_llm_vanilla_results.json"

# Crea backup dei vecchi risultati prima di sovrascrivere
shutil.copy2(GRAPHRAG_JSON, GRAPHRAG_JSON.with_suffix(".json.bak"))
shutil.copy2(VANILLA_JSON, VANILLA_JSON.with_suffix(".json.bak"))

print("Backup creati con successo in .bak")

def ricalcola_file(json_path: Path, label: str):
    print(f"\n--- Ricalcolo metriche per: {label} ({json_path.name}) ---")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    casi_cambiati = 0
    tot_hallucinated_vecchi = 0
    tot_hallucinated_nuovi = 0

    for r in data:
        case_id = r["case_id"]
        report = r["report"]
        
        # Vecchie metriche salvate nel file
        vecchi_pmid = set(r.get("cited_pmids_list", []))
        vecchi_hall = set(r.get("hallucinated_pmids_list", []))
        vecchio_rate = r.get("pmid_hallucination_rate", 0.0)

        # Nuova estrazione
        nuovi_pmid = extract_pmids_from_report(report)
        nuovi_validi = check_pmids_exist_in_kb(nuovi_pmid)
        nuovi_hall = nuovi_pmid - nuovi_validi
        nuovo_rate = len(nuovi_hall) / len(nuovi_pmid) if nuovi_pmid else 0.0

        # Conteggio cumulativo
        tot_hallucinated_vecchi += len(vecchi_hall)
        tot_hallucinated_nuovi += len(nuovi_hall)

        # Se ci sono differenze
        if nuovi_pmid != vecchi_pmid or nuovi_hall != vecchi_hall:
            casi_cambiati += 1
            print(f"Caso {case_id} CAMBIATO:")
            print(f"  PMID vecchi:         {sorted(list(vecchi_pmid))}")
            print(f"  PMID nuovi:          {sorted(list(nuovi_pmid))}")
            print(f"  Allucinazioni vecchie: {sorted(list(vecchi_hall))} (rate: {vecchio_rate:.1%})")
            print(f"  Allucinazioni nuove:   {sorted(list(nuovi_hall))} (rate: {nuovo_rate:.1%})")
            
            # Aggiorna il record
            r["cited_pmids_list"] = sorted(list(nuovi_pmid))
            r["hallucinated_pmids_list"] = sorted(list(nuovi_hall))
            r["n_cited_pmids"] = len(nuovi_pmid)
            r["n_hallucinated_pmids"] = len(nuovi_hall)
            r["pmid_hallucination_rate"] = nuovo_rate
            # Ri-valuta anche il dac_anchor_pmid_cited se presente
            # (Nel file json r contiene case_id e le chiavi del benchmark sono caricate per calcolare il dac)
            # Per semplicità ricalcoliamo solo la parte PMID/allucinazioni che è quella affetta dalla regex
        else:
            # Aggiorna comunque per allineare i campi nel json
            r["cited_pmids_list"] = sorted(list(nuovi_pmid))
            r["hallucinated_pmids_list"] = sorted(list(nuovi_hall))
            r["n_cited_pmids"] = len(nuovi_pmid)
            r["n_hallucinated_pmids"] = len(nuovi_hall)
            r["pmid_hallucination_rate"] = nuovo_rate

    # Salva il file aggiornato
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Ricalcolo completato per {label}. Casi modificati: {casi_cambiati}/{len(data)}")
    print(f"Totale PMID allucinati: vecchi = {tot_hallucinated_vecchi}, nuovi = {tot_hallucinated_nuovi}")

ricalcola_file(GRAPHRAG_JSON, "Qwen GraphRAG")
ricalcola_file(VANILLA_JSON, "Qwen Vanilla")
