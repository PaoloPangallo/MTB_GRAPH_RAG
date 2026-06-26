"""
run_zeroshot.py — Baseline zero-shot per confronto con GraphRAG MTB.

Chiama direttamente Gemma 4 31B via Ollama Cloud (stesso LLM della pipeline)
senza alcun accesso a Neo4j o Knowledge Base. Il LLM riceve solo i dati
clinici grezzi (gene, variante, tumore, linea) e deve produrre un report
con le stesse sezioni obbligatorie della pipeline GraphRAG.

Poi chiama LLM-as-judge con gli stessi 4 criteri del benchmark GraphRAG.

Uso:
  .venv/Scripts/python -m backend.evaluation.run_zeroshot               # tutti 30 casi
  .venv/Scripts/python -m backend.evaluation.run_zeroshot --case BENCH-001
  .venv/Scripts/python -m backend.evaluation.run_zeroshot --dry-run     # stampa prompt, no LLM
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

# ── LLM — stesso di pipeline e judge ──────────────────────────
# Importiamo direttamente da llm.py: usa langchain_ollama (Gemma 4 31B)
from backend.pipeline.llm import llm, llm_judge
from langchain_core.messages import HumanMessage, SystemMessage

# ── Paths ──────────────────────────────────────────────────────
BENCHMARK_CSV  = Path(__file__).resolve().parents[1] / "benchmark" / "benchmark_papers_summary_30_v2.csv"
RESULTS_DIR    = Path(__file__).resolve().parent / "results"
OUTPUT_JSON    = RESULTS_DIR / "zeroshot_results.json"

# Mapping tumore CSV → nome OncoTree-compatibile (identico a run_benchmark.py)
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


# ── Prompt zero-shot ───────────────────────────────────────────
# SYNTHESIZER_SYSTEM identico alla pipeline, copiato verbatim da synthesizer.py
SYNTHESIZER_SYSTEM = """Sei un assistente clinico esperto per Molecular Tumor Board.
Produci un report strutturato e conciso in italiano.
IMPORTANTE:
- Collega ESPLICITAMENTE ogni singola raccomandazione terapeutica, ciascun livello ESCAT e ciascun meccanismo di resistenza al relativo PMID di supporto direttamente inline nel testo (es. "Osimertinib è raccomandato come prima linea [PMID: 37937763]").
- Non limitarti a elencare i PMID alla fine del paragrafo o in fondo al report: ogni singola affermazione terapeutica o clinica nel corpo del report deve essere immediatamente seguita dal suo rispettivo PMID di supporto tra parentesi quadre.
- Se un farmaco ha associata una companion diagnostic (CDx), riportala insieme al farmaco con la relativa citazione.
- Usa SOLO i PMID verificati forniti nel contesto dell'input. Non inventare citazioni esterne.

Struttura obbligatoria:
1. Variante e classificazione ESCAT (con citazioni inline [PMID: XXXXX])
2. Terapia raccomandata (per ciascun farmaco e companion diagnostic, includere la spiegazione dell'evidenza clinica e la citazione inline [PMID: XXXXX])
3. Profilo di resistenza (descrivere le mutazioni di resistenza come T790M o C797S e come impattano le terapie, indicando esplicitamente i PMID di supporto inline [PMID: XXXXX])
4. Trial clinici eleggibili (se presenti nel contesto, con NCT ID)
5. Lista finale dei PMID verificati nel Knowledge Graph
"""


def build_zeroshot_context(gene: str, variant: str, tumor_type: str,
                           alteration_type: str, therapy_line: str) -> str:
    """
    Costruisce il contesto zero-shot: solo i dati di input grezzi.
    Nessuna evidenza da KB, nessun drug candidate, nessun trial.
    """
    return (
        f"=== VARIANTE ===\n"
        f"Gene: {gene} | Variante: {variant} | "
        f"Tipo: {alteration_type} | Tumore: {tumor_type} | "
        f"Linea: {therapy_line}\n\n"
        f"NOTA: Non hai accesso a un Knowledge Graph. Usa le tue conoscenze cliniche "
        f"aggiornate per redigere il report. Cita i PMID reali che conosci dalla letteratura "
        f"scientifica per supportare ogni affermazione, rispettando la struttura obbligatoria."
    )


# ── Judge — identico a agents/judge.py ────────────────────────
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


def llm_as_judge_zeroshot(report: str, case_info: dict) -> dict:
    """Identico a agents/judge.llm_as_judge — separato per non importare langchain da llm.py."""
    user_msg = (
        f"Caso: {case_info.get('gene')} {case_info.get('variant')} / "
        f"{case_info.get('tumor_type')}\n\n"
        f"Report da valutare:\n{report}"
    )
    response = llm_judge.invoke([
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=user_msg),
    ])
    try:
        clean = re.sub(r"```json|```", "", response.content).strip()
        return json.loads(clean)
    except Exception:
        return {"raw_response": response.content, "error": "parsing fallito"}


# ── Run singolo caso ───────────────────────────────────────────
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

    # ── Generazione report ──────────────────────────────────────
    t0_gen = time.perf_counter()
    response = llm.invoke([
        SystemMessage(content=SYNTHESIZER_SYSTEM),
        HumanMessage(content=context),
    ])
    t_generation = round(time.perf_counter() - t0_gen, 2)
    report = response.content

    print(f"  t_generation: {t_generation}s")
    print(f"  Report length: {len(report)} chars")

    # ── Judge ───────────────────────────────────────────────────
    t0_judge = time.perf_counter()
    score = llm_as_judge_zeroshot(report, {
        "gene": row["gene"], "variant": variant, "tumor_type": tumor_type
    })
    t_judge = round(time.perf_counter() - t0_judge, 2)
    t_total = round(t_generation + t_judge, 2)

    judge_score = score.get("score_totale")
    print(f"  Judge score: {judge_score} | t_total: {t_total}s")

    return {
        "case_id":          case_id,
        "gene":             row["gene"],
        "variant":          variant,
        "tumor":            row["tumor"],
        "tumor_type":       tumor_type,
        "alteration_type":  alteration_type,
        "therapy_line":     therapy_line,
        "expected_drug":    row.get("expected_drug", ""),
        "escat":            row.get("escat", ""),
        "category":         row.get("category", ""),
        "t_generation_sec": t_generation,
        "t_judge_sec":      t_judge,
        "t_total_sec":      t_total,
        "report":           report,
        "judge_score":      judge_score,
        "judge_detail":     score,
    }


# ── Main ───────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Zero-shot MTB benchmark")
    parser.add_argument("--case",    type=str, default=None,
                        help="Singolo caso (es. BENCH-001)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Stampa il prompt senza chiamare il LLM")
    parser.add_argument("--resume",  action="store_true",
                        help="Riprende da un run precedentemente interrotto")
    args = parser.parse_args()

    # Carica CSV
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

    # Resume: carica risultati parziali se esistono
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

            # Salva incrementalmente dopo ogni caso (fault-tolerant)
            if not args.dry_run:
                with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)

    if args.dry_run:
        print("\n[DRY RUN] Nessun output scritto.")
        return

    t_elapsed = round(time.perf_counter() - t_start_total, 1)

    # Riepilogo
    valid = [r for r in results if r.get("judge_score") is not None]
    scores = [r["judge_score"] for r in valid]
    times_gen = [r["t_generation_sec"] for r in valid]
    times_tot = [r["t_total_sec"] for r in valid]

    print(f"\n{'═' * 60}")
    print(f"  Zero-shot completato: {len(results)} casi in {t_elapsed}s")
    if scores:
        print(f"  Judge score medio:    {sum(scores)/len(scores):.3f}")
        print(f"  t_generation medio:   {sum(times_gen)/len(times_gen):.1f}s")
        print(f"  t_total medio:        {sum(times_tot)/len(times_tot):.1f}s")
    print(f"  Output: {OUTPUT_JSON}")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    main()
