"""
run_zeroshot_structured.py — Baseline zero-shot per valutazione oggettiva.

Chiama Gemma 4 31B (o MiniMax) senza accesso a KB.
Richiede un output JSON parsabile per poter calcolare deterministicaemente
le metriche oggettive: Therapeutic Match, Evidence Grounding, Safety.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.pipeline.llm import llm, llm_judge
from langchain_core.messages import HumanMessage, SystemMessage

BENCHMARK_CSV  = Path(__file__).resolve().parents[1] / "benchmark" / "benchmark_papers_summary_30_v2.csv"
RESULTS_DIR    = Path(__file__).resolve().parent / "results"
OUTPUT_JSON    = RESULTS_DIR / "zeroshot_structured_results.json"

TUMOR_MAP: dict[str, str] = {
    "NSCLC":               "Lung Adenocarcinoma",
    "Melanoma":            "Melanoma",
    "Breast Cancer HER2+": "Breast Cancer",
    "Breast Cancer HR+":   "Breast Cancer",
    "Ovarian Cancer":      "Ovarian Cancer",
    "CML":                 "Chronic Myeloid Leukemia",
    "Colorectal Cancer":   "Colorectal Cancer",
    "GIST":                "Gastrointestinal Stromal Tumor",
    "AML":                 "Acute Myeloid Leukemia",
    "Solid Tumor":         "Solid Tumor",
    "Gastric Cancer":      "Gastric Cancer",
    "Prostate Cancer":     "Prostate Cancer",
    "Cholangiocarcinoma":  "Cholangiocarcinoma",
    "Thyroid Cancer":      "Thyroid Cancer",
}

SYNTHESIZER_SYSTEM = """Sei un assistente clinico esperto per Molecular Tumor Board.
Produci un report in italiano e restituisci ESCLUSIVAMENTE un oggetto JSON valido.

Il JSON deve avere esattamente la seguente struttura:
{
  "report_text": "Il testo completo del report MTB formattato con le solite sezioni: 1. Variante, 2. Terapia raccomandata, 3. Resistenze, 4. Trial. Assicurati di includere i [PMID: XXXXXX] inline.",
  "recommended_drugs": ["Farmaco1", "Farmaco2"], 
  "citations": ["XXXXXX", "YYYYYY"] 
}

NOTE IMPORTANTI:
- In `recommended_drugs`, elenca solo i principi attivi dei farmaci che raccomandi.
- In `citations`, metti solo la lista di numeri PMID (come stringhe) usati come evidenza.
- Non aggiungere backtick o markup markdown attorno al JSON, restituisci solo l'oggetto JSON parsabile.
"""

def build_zeroshot_context(gene: str, variant: str, tumor_type: str,
                           alteration_type: str, therapy_line: str) -> str:
    return (
        f"=== VARIANTE ===\n"
        f"Gene: {gene} | Variante: {variant} | "
        f"Tipo: {alteration_type} | Tumore: {tumor_type} | "
        f"Linea: {therapy_line}\n\n"
        f"NOTA: Non hai accesso a un Knowledge Graph. Usa le tue conoscenze cliniche "
        f"aggiornate. Cita i PMID reali che conosci dalla letteratura per supportare ogni affermazione."
    )

def run_single(case_id: str, row: dict, dry_run: bool = False) -> dict:
    gene           = row["gene"] if row["gene"] not in ("MMR", "TMB") else ""
    variant        = row["variant"]
    tumor_type     = TUMOR_MAP.get(row["tumor"], row["tumor"])
    alteration_type = row["alteration_type"]
    therapy_line   = "first-line"

    print(f"\n{'═' * 60}")
    print(f"  {case_id}: {row['gene']} {variant} / {row['tumor']}")
    print(f"{'═' * 60}")

    context = build_zeroshot_context(
        gene, variant, tumor_type, alteration_type, therapy_line
    )

    if dry_run:
        print("  [DRY RUN] Prompt che verrebbe inviato:")
        print(f"  SYSTEM: {SYNTHESIZER_SYSTEM[:120]}...")
        print(f"  USER:\n{context}")
        return {}

    t0_gen = time.perf_counter()
    response = llm.invoke([
        SystemMessage(content=SYNTHESIZER_SYSTEM),
        HumanMessage(content=context),
    ])
    t_generation = round(time.perf_counter() - t0_gen, 2)
    raw_output = response.content

    print(f"  t_generation: {t_generation}s")

    # Parsing del JSON
    parsed_json = {}
    try:
        clean = re.sub(r"```json|```", "", raw_output).strip()
        parsed_json = json.loads(clean)
        print("  JSON estratto con successo.")
    except Exception as e:
        print(f"  [ERRORE] Parsing JSON fallito: {e}")
        parsed_json = {"report_text": raw_output, "recommended_drugs": [], "citations": []}

    return {
        "case_id":          case_id,
        "gene":             row["gene"],
        "variant":          variant,
        "tumor":            row["tumor"],
        "expected_drug":    row.get("expected_drug", ""),
        "t_generation_sec": t_generation,
        "raw_response":     raw_output,
        "structured_data":  parsed_json
    }

def main():
    parser = argparse.ArgumentParser(description="Zero-shot MTB structured benchmark")
    parser.add_argument("--case",    type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume",  action="store_true")
    args = parser.parse_args()

    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = {row["case_id"]: row for row in reader}

    if args.case:
        if args.case not in rows:
            print(f"Caso {args.case} non trovato.")
            sys.exit(1)
        cases = {args.case: rows[args.case]}
    else:
        cases = rows

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    already_done: set[str] = set()
    if args.resume and OUTPUT_JSON.exists():
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            results = json.load(f)
        already_done = {r["case_id"] for r in results}
        print(f"  [RESUME] Trovati {len(already_done)} casi già completati: {sorted(already_done)}")

    t_start_total = time.perf_counter()

    for case_id, row in cases.items():
        if case_id in already_done:
            print(f"  [SKIP] {case_id} già completato.")
            continue

        result = run_single(case_id, row, dry_run=args.dry_run)
        if result:
            results.append(result)

            if not args.dry_run:
                with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)

    if args.dry_run:
        return

    t_elapsed = round(time.perf_counter() - t_start_total, 1)

    print(f"\n{'═' * 60}")
    print(f"  Zero-shot Strutturato completato: {len(results)} casi in {t_elapsed}s")
    print(f"  Output: {OUTPUT_JSON}")
    print(f"{'═' * 60}")

if __name__ == "__main__":
    main()
