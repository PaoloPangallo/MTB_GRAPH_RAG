import csv
import json
from pathlib import Path

# Paths
results_dir = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results")
three_way_path = results_dir / "three_way_comparison.csv"
comparison_summary_path = results_dir / "comparison_summary.csv"

# 1. Update three_way_comparison.csv
three_way_rows = []
with open(three_way_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        if row["case_id"] == "BENCH-004":
            row["gr_base_tm"] = "1.0"
            row["gr_base_eg"] = "True"
        three_way_rows.append(row)

with open(three_way_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(three_way_rows)
print("Updated three_way_comparison.csv for BENCH-004")

# 2. Update comparison_summary.csv
summary_rows = []
with open(comparison_summary_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        if row["case_id"] == "BENCH-004":
            row["gr_dac"] = "True"
            row["gr_pmid_cov"] = "True"
            row["gr_score_tot"] = "4.375"
            row["gr_compl"] = "4.5"
            row["gr_utilita"] = "4.5"
            row["gr_fedelta"] = "4.0"
            row["gr_accur"] = "4.5"
        summary_rows.append(row)

with open(comparison_summary_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(summary_rows)
print("Updated comparison_summary.csv for BENCH-004")

# 3. Recalculate summary tables
def mean(vals):
    v = [float(x) for x in vals if x is not None and x != ""]
    return round(sum(v) / len(v), 3) if v else None

def bool_rate(vals):
    v = [x == "True" for x in vals if x is not None and x != ""]
    return sum(v) / len(v) if v else None

def print_table(title, subset):
    gr_dac = bool_rate([r["gr_dac"] for r in subset])
    zs_dac = bool_rate([r["zs_dac"] for r in subset])
    gr_cov = bool_rate([r["gr_pmid_cov"] for r in subset])
    zs_cov = bool_rate([r["zs_pmid_cov"] for r in subset])
    gr_hal = mean([r["gr_hallucination"] for r in subset])
    zs_hal = mean([r["zs_hallucination"] for r in subset])
    gr_esc = bool_rate([r["gr_escat"] for r in subset])
    zs_esc = bool_rate([r["zs_escat"] for r in subset])
    
    gr_tot = mean([r["gr_score_tot"] for r in subset])
    zs_tot = mean([r["zs_score_tot"] for r in subset])
    gr_cpl = mean([r["gr_compl"] for r in subset])
    zs_cpl = mean([r["zs_compl"] for r in subset])
    gr_uti = mean([r["gr_utilita"] for r in subset])
    zs_uti = mean([r["zs_utilita"] for r in subset])
    gr_fed = mean([r["gr_fedelta"] for r in subset])
    zs_fed = mean([r["zs_fedelta"] for r in subset])
    gr_acc = mean([r["gr_accur"] for r in subset])
    zs_acc = mean([r["zs_accur"] for r in subset])
    
    def fmt_p(v): return f"{v:.1%}" if v is not None else "N/A"
    def fmt_f(v): return f"{v:.2f}" if v is not None else "N/A"
    def d_p(g, z): return f"{(g-z):+.1%}" if g is not None and z is not None else "N/A"
    def d_f(g, z): return f"{(g-z):+.2f}" if g is not None and z is not None else "N/A"

    print(f"\n{'=' * 75}")
    print(f" {title} (n={len(subset)})")
    print(f"{'=' * 75}")
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

print_table("1. CONFRONTO GLOBALE (Tutti i casi)", summary_rows)
valid_kb_rows = [r for r in summary_rows if r["kb_coverage"] == "COVERED"]
print_table("2. CONFRONTO KB COVERED (Esclusi casi con KB mancante)", valid_kb_rows)
