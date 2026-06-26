"""
compare_results.py — Analisi comparativa GraphRAG vs Zero-shot (RQ1)

Legge i risultati dei judge e le metriche oggettive calcolate da compute_metrics.py
e produce le tabelle comparative finali stratificate.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Paths ──────────────────────────────────────────────────────
RESULTS_DIR      = Path(__file__).resolve().parent / "results"
GRAPHRAG_JSON    = RESULTS_DIR / "benchmark_results.json"
ZEROSHOT_JSON    = RESULTS_DIR / "zeroshot_results.json"
METRICS_GR_JSON  = RESULTS_DIR / "metrics_graphrag.json"
METRICS_ZS_JSON  = RESULTS_DIR / "metrics_zeroshot.json"
COMPARISON_CSV   = RESULTS_DIR / "comparison_summary.csv"
BENCHMARK_CSV    = Path(__file__).resolve().parents[1] / "benchmark" / "benchmark_papers_summary_30_v2.csv"

def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_csv_meta() -> dict[str, dict]:
    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["case_id"]: row for row in reader}

def safe_float(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None

def mean(vals: list) -> float | None:
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v), 3) if v else None

def perc(vals: list) -> str:
    v = [x for x in vals if x is not None]
    if not v:
        return "N/A"
    # Se sono booleani
    if all(isinstance(x, bool) for x in v):
        val = sum(v) / len(v)
    else:
        val = sum(v) / len(v)
    return f"{val:.1%}"

# ── Elaborazione ───────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Confronto GraphRAG vs Zero-shot RQ1")
    args = parser.parse_args()

    gr_results = {r["case_id"]: r for r in load_json(GRAPHRAG_JSON)}
    zs_results = {r["case_id"]: r for r in load_json(ZEROSHOT_JSON)}
    gr_metrics = {r["case_id"]: r for r in load_json(METRICS_GR_JSON)}
    zs_metrics = {r["case_id"]: r for r in load_json(METRICS_ZS_JSON)}
    meta = load_csv_meta()
    
    if not gr_metrics or not zs_metrics:
        print("Errore: file delle metriche oggettive mancanti. Esegui compute_metrics.py prima.")
        sys.exit(1)

    all_cases = sorted(list(gr_results.keys()))
    
    # Raccogliamo i dati per caso
    combined_data = []
    for case_id in all_cases:
        gr_r = gr_results.get(case_id, {})
        zs_r = zs_results.get(case_id, {})
        gr_m = gr_metrics.get(case_id, {})
        zs_m = zs_metrics.get(case_id, {})
        m_meta = meta.get(case_id, {})
        
        # Estrai i judge scores
        gr_jd = gr_r.get("judge_detail", {})
        zs_jd = zs_r.get("judge_detail", {})
        
        row = {
            "case_id": case_id,
            "kb_coverage": m_meta.get("kb_coverage", "COVERED"),
            "alteration_type": m_meta.get("alteration_type", "unknown"),
            
            # Objective Metrics
            "gr_dac": gr_m.get("dac_drug_found"),
            "zs_dac": zs_m.get("dac_drug_found"),
            "gr_pmid_cov": gr_m.get("dac_anchor_pmid_cited"),
            "zs_pmid_cov": zs_m.get("dac_anchor_pmid_cited"),
            "gr_hallucination": gr_m.get("pmid_hallucination_rate"),
            "zs_hallucination": zs_m.get("pmid_hallucination_rate"),
            "gr_escat": gr_m.get("escat_match"),
            "zs_escat": zs_m.get("escat_match"),
            
            # Subjective Metrics
            "gr_score_tot": safe_float(gr_r.get("judge_score")),
            "zs_score_tot": safe_float(zs_r.get("judge_score")),
            "gr_compl": safe_float(gr_jd.get("completezza")),
            "zs_compl": safe_float(zs_jd.get("completezza")),
            "gr_utilita": safe_float(gr_jd.get("utilita_clinica")),
            "zs_utilita": safe_float(zs_jd.get("utilita_clinica")),
            "gr_fedelta": safe_float(gr_jd.get("fedelta_evidenze")),
            "zs_fedelta": safe_float(zs_jd.get("fedelta_evidenze")),
            "gr_accur": safe_float(gr_jd.get("accuratezza_clinica")),
            "zs_accur": safe_float(zs_jd.get("accuratezza_clinica")),
        }
        combined_data.append(row)

    def print_table(title: str, subset: list[dict]):
        if not subset:
            return
        
        def avg(key): return mean([r[key] for r in subset])
        def bool_rate(key): 
            vals = [r[key] for r in subset if r[key] is not None]
            return sum(vals)/len(vals) if vals else None
            
        gr_dac = bool_rate("gr_dac")
        zs_dac = bool_rate("zs_dac")
        gr_cov = bool_rate("gr_pmid_cov")
        zs_cov = bool_rate("zs_pmid_cov")
        gr_hal = avg("gr_hallucination")
        zs_hal = avg("zs_hallucination")
        gr_esc = bool_rate("gr_escat")
        zs_esc = bool_rate("zs_escat")
        
        gr_tot = avg("gr_score_tot")
        zs_tot = avg("zs_score_tot")
        gr_cpl = avg("gr_compl")
        zs_cpl = avg("zs_compl")
        gr_uti = avg("gr_utilita")
        zs_uti = avg("zs_utilita")
        gr_fed = avg("gr_fedelta")
        zs_fed = avg("zs_fedelta")
        gr_acc = avg("gr_accur")
        zs_acc = avg("zs_accur")
        
        def fmt_p(v): return f"{v:.1%}" if v is not None else "N/A"
        def fmt_f(v): return f"{v:.2f}" if v is not None else "N/A"
        def d_p(g, z): return f"{(g-z):+.1%}" if g is not None and z is not None else "N/A"
        def d_f(g, z): return f"{(g-z):+.2f}" if g is not None and z is not None else "N/A"

        print(f"\\n{'═' * 75}")
        print(f" {title} (n={len(subset)})")
        print(f"{'═' * 75}")
        print(f"{'Metrica':<30} | {'GraphRAG':>10} | {'Zero-shot':>10} | {'Delta':>10}")
        print("-" * 75)
        print(f"{'Drug Anchor Check':<30} | {fmt_p(gr_dac):>10} | {fmt_p(zs_dac):>10} | {d_p(gr_dac, zs_dac):>10}")
        print(f"{'PMID Coverage Rate':<30} | {fmt_p(gr_cov):>10} | {fmt_p(zs_cov):>10} | {d_p(gr_cov, zs_cov):>10}")
        print(f"{'PMID Hallucination Rate':<30} | {fmt_p(gr_hal):>10} | {fmt_p(zs_hal):>10} | {d_p(gr_hal, zs_hal):>10}")
        print(f"{'ESCAT Tier Match':<30} | {fmt_p(gr_esc):>10} | {fmt_p(zs_esc):>10} | {d_p(gr_esc, zs_esc):>10}")
        print("-" * 75)
        print(f"{'Score Totale (Judge)':<30} | {fmt_f(gr_tot):>10} | {fmt_f(zs_tot):>10} | {d_f(gr_tot, zs_tot):>10}")
        print(f"{'- Completezza':<30} | {fmt_f(gr_cpl):>10} | {fmt_f(zs_cpl):>10} | {d_f(gr_cpl, zs_cpl):>10}")
        print(f"{'- Utilità Clinica':<30} | {fmt_f(gr_uti):>10} | {fmt_f(zs_uti):>10} | {d_f(gr_uti, zs_uti):>10}")
        print(f"{'- Fedeltà Evidenze':<30} | {fmt_f(gr_fed):>10} | {fmt_f(zs_fed):>10} | {d_f(gr_fed, zs_fed):>10}")
        print(f"{'- Accuratezza Clinica':<30} | {fmt_f(gr_acc):>10} | {fmt_f(zs_acc):>10} | {d_f(gr_acc, zs_acc):>10}")

    # 1. Tabella Aggregata (Tutti i casi)
    print_table("1. CONFRONTO GLOBALE (Tutti i casi)", combined_data)
    
    # 2. Tabella Solo casi con KB > 0
    valid_kb_data = [r for r in combined_data if r["kb_coverage"] == "COVERED"]
    print_table("2. CONFRONTO KB COVERED (Esclusi casi con KB mancante)", valid_kb_data)
    
    zero_kb_cases = [r["case_id"] for r in combined_data if r["kb_coverage"] != "COVERED"]
    if zero_kb_cases:
        print(f"\\n[NOTA METODOLOGICA] I seguenti casi hanno kb_coverage=0: {zero_kb_cases}.")
        print("Su questi casi GraphRAG è penalizzato per assenza di dati nel DB, non per un difetto della pipeline.")
        
    # 3. Stratificazione per Alteration Type
    print(f"\\n{'═' * 75}")
    print(f" 3. STRATIFICAZIONE PER ALTERATION TYPE (Solo casi KB > 0)")
    print(f"{'═' * 75}")
    
    alt_types = set(r["alteration_type"] for r in valid_kb_data)
    for atype in sorted(alt_types):
        subset = [r for r in valid_kb_data if r["alteration_type"] == atype]
        print_table(f"Alteration Type: {atype}", subset)
        
    # Salva CSV combinato per eventuali grafici
    fieldnames = list(combined_data[0].keys())
    with open(COMPARISON_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(combined_data)

if __name__ == "__main__":
    main()
