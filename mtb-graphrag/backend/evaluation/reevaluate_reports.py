"""
Reevaluate Reports — Re-valuta i report esistenti (GraphRAG e Zero-shot) usando il nuovo giudice MiniMax-M2.5.
Questo script è standalone per evitare dipendenze da Neo4j o moduli complessi della pipeline.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

# Configure standard output to use UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Carica credenziali
_env_path = Path("c:/Users/paolo/Desktop/IspezioneDatasetTesi/mtb-graphrag/.env")
load_dotenv(_env_path)

OLLAMA_BASE_URL = "https://api.ollama.com"
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

# Inizializza il giudice
llm_judge = ChatOllama(
    model="minimax-m2.5",
    base_url=OLLAMA_BASE_URL,
    api_key=OLLAMA_API_KEY,
    temperature=0.0,
    timeout=60.0,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
GRAPHRAG_JSON = RESULTS_DIR / "benchmark_results.json"
ZEROSHOT_JSON = RESULTS_DIR / "zeroshot_results.json"

JUDGE_SYSTEM = """Sei un valutatore esperto di sistemi AI per oncologia clinica.
Valuta il report MTB (Molecular Tumor Board) fornito secondo questi quattro criteri (punteggio da 1.0 a 5.0 per ciascuno):

1. COMPLETEZZA: il report copre variante, terapia, resistenze e trial in modo esaustivo? (Ispirato alla metrica "Comprehensiveness" di Edge et al., GraphRAG Microsoft)
2. UTILITÀ CLINICA: il report è immediatamente utilizzabile e actionable per un oncologo al board? La struttura scompare come criterio separato ed è assorbita qui, poiché un report mal strutturato non è actionable. (Adattamento della metrica "Empowerment" di Edge et al.)
3. FEDELTÀ ALLE EVIDENZE: i codici PMID citati sono presenti nel report e pertinenti alle raccomandazioni? (Ispirato alla metrica "citation precision" di Wu et al.)
4. ACCURATEZZA CLINICA: le raccomandazioni terapeutiche e le informazioni scientifiche fornite nel report sono clinicamente corrette? (Criterio originale, in sostituzione di "Struttura" che è banale)

Restituisci un JSON con questa struttura esatta:
{
  "completezza": <1.0-5.0>,
  "utilita_clinica": <1.0-5.0>,
  "fedelta_evidenze": <1.0-5.0>,
  "accuratezza_clinica": <1.0-5.0>,
  "score_totale": <media dei 4 criteri>,
  "motivazione": "<spiegazione sintetica dei punteggi assegnati>"
}
"""

def evaluate_report_standalone(report: str, case_info: dict) -> dict:
    user_msg = (
        f"Caso: {case_info.get('gene')} {case_info.get('variant')} / "
        f"{case_info.get('tumor_type')}\n\n"
        f"Report da valutare:\n{report}"
    )
    
    try:
        response = llm_judge.invoke([
            SystemMessage(content=JUDGE_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        clean = re.sub(r"```json|```", "", response.content).strip()
        # Rimuove eventuale testo extra prima o dopo il JSON
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            clean = match.group(0)
        return json.loads(clean)
    except Exception as e:
        return {"error": str(e), "raw_response": response.content if 'response' in locals() else ""}


def reevaluate_file(json_path: Path, label: str):
    if not json_path.exists():
        print(f"[ERRORE] File non trovato: {json_path}")
        return

    print(f"\nCaricamento report da: {json_path.name} ({label})")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Trovati {len(data)} casi. Avvio re-valutazione con MiniMax-M2.5...")
    
    t0_all = time.perf_counter()
    for i, case in enumerate(data, 1):
        case_id = case.get("case_id", f"UNKNOWN-{i}")
        gene = case.get("gene", "")
        variant = case.get("variant", "")
        tumor = case.get("tumor", "")
        report = case.get("report", "")

        print(f"[{i}/{len(data)}] Valutando {case_id} ({gene} {variant} / {tumor})... ", end="", flush=True)

        if not report:
            print("SALTATO (nessun report)")
            continue

        case_info = {
            "gene": gene,
            "variant": variant,
            "tumor_type": tumor
        }

        t0_case = time.perf_counter()
        score_detail = evaluate_report_standalone(report, case_info)
        dt = round(time.perf_counter() - t0_case, 2)

        if "error" in score_detail:
            print(f"ERRORE: {score_detail.get('error')} | Riprovo...")
            time.sleep(1)
            score_detail = evaluate_report_standalone(report, case_info)
            if "error" in score_detail:
                print("FALLITO DI NUOVO")
                continue
            else:
                print("OK (secondo tentativo) ", end="")

        judge_score = score_detail.get("score_totale")
        case["judge_score"] = judge_score
        case["judge_detail"] = score_detail
        
        if label == "Zero-shot":
            case["t_judge_sec"] = dt
            if "t_generation_sec" in case:
                case["t_total_sec"] = round(case["t_generation_sec"] + dt, 2)

        print(f"OK | Score: {judge_score} | tempo: {dt}s")
        time.sleep(0.5)

    total_time = round(time.perf_counter() - t0_all, 2)
    print(f"Completata re-valutazione per {label} in {total_time}s.")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Salvati risultati aggiornati in {json_path.name}")


def main():
    print("=== AVVIO RE-VALUTAZIONE STANDALONE CON GIUDICE MINIMAX-M2.5 ===")
    
    # 1. Re-valuta GraphRAG
    reevaluate_file(GRAPHRAG_JSON, "GraphRAG")
    
    # 2. Re-valuta Zero-shot
    reevaluate_file(ZEROSHOT_JSON, "Zero-shot")
    
    print("\nRe-valutazione completata con successo per entrambi i dataset!")


if __name__ == "__main__":
    main()
