import sys
import csv
from pathlib import Path

# Setup sys.path for absolute imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "mtb-graphrag"))

from backend.pipeline.llm import driver

def run_cypher(query, params=None):
    with driver.session() as session:
        result = session.run(query, params or {})
        return [record.data() for record in result]

def print_section(title, query_string, data):
    print(f"\n{'='*80}")
    print(f" {title}")
    print(f"{'='*80}")
    print("--- CYPHER QUERY ---")
    print(query_string.strip())
    print("--------------------")
    if not data:
        print("nessun caso trovato")
    else:
        for i, row in enumerate(data, 1):
            print(f"\n[Caso {i}]")
            for k, v in row.items():
                print(f"  {k}: {v}")

def main():
    # ---------------------------------------------------------
    # Query A — Doppia significatività (sensibilità + resistenza)
    # ---------------------------------------------------------
    query_a = """
    MATCH (mp:MolecularProfile)-[:HAS_EVIDENCE]->(ev_sens:Evidence)-[:TARGETS_DRUG]->(d_sens:Drug)
    WHERE ev_sens.significance = 'Sensitivity/Response'
    OPTIONAL MATCH (ev_sens)-[:CITED_IN]->(p_sens:Publication)
    
    MATCH (mp)-[:HAS_EVIDENCE]->(ev_res:Evidence)-[:TARGETS_DRUG]->(d_res:Drug)
    WHERE ev_res.significance = 'Resistance' 
      AND toLower(ev_res.disease) = toLower(ev_sens.disease)
    OPTIONAL MATCH (ev_res)-[:CITED_IN]->(p_res:Publication)
    
    RETURN mp.name AS molecular_profile,
           ev_sens.disease AS tumor,
           collect(DISTINCT {drug: d_sens.drug_name, pmid: p_sens.pmid}) AS sensitivity_data,
           collect(DISTINCT {drug: d_res.drug_name, pmid: p_res.pmid}) AS resistance_data
    LIMIT 20
    """
    data_a = run_cypher(query_a)
    print_section("QUERY A - Doppia significatività (Sensibilità + Resistenza nello stesso tumore)", query_a, data_a)
    
    # ---------------------------------------------------------
    # Query B — Casi di resistenza con rischio pollution
    # ---------------------------------------------------------
    print(f"\n{'='*80}")
    print(" QUERY B - Casi di resistenza con rischio pollution")
    print(f"{'='*80}")
    
    resistance_cases = [
        {"gene": "EGFR", "variant": "T790M"},
        {"gene": "ALK", "variant": "G1202R"},
        {"gene": "ABL1", "variant": "T315I"},
        {"gene": "KIT", "variant": "exon 9"},
    ]
    
    query_gene = """
    MATCH (g:Gene {hugo_symbol: $gene})-[:HAS_VARIANT]->(:Variant)-[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence)-[:TARGETS_DRUG]->(d:Drug)
    WHERE e.significance = 'Sensitivity/Response'
    RETURN collect(DISTINCT d.drug_name) AS gene_level_drugs
    """
    
    query_variant = """
    MATCH (g:Gene {hugo_symbol: $gene})-[:HAS_VARIANT]->(v:Variant)-[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence)-[:TARGETS_DRUG]->(d:Drug)
    WHERE toLower(v.variant_name) CONTAINS toLower($variant)
      AND e.significance = 'Sensitivity/Response'
    RETURN collect(DISTINCT d.drug_name) AS variant_level_drugs
    """
    
    query_variant_resistance = """
    MATCH (g:Gene {hugo_symbol: $gene})-[:HAS_VARIANT]->(v:Variant)-[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence)-[:TARGETS_DRUG]->(d:Drug)
    WHERE toLower(v.variant_name) CONTAINS toLower($variant)
      AND e.significance = 'Resistance'
    RETURN collect(DISTINCT d.drug_name) AS resistance_drugs
    """
    
    for case in resistance_cases:
        gene_drugs = run_cypher(query_gene, {"gene": case["gene"]})
        var_drugs = run_cypher(query_variant, {"gene": case["gene"], "variant": case["variant"]})
        res_drugs = run_cypher(query_variant_resistance, {"gene": case["gene"], "variant": case["variant"]})
        
        g_list = gene_drugs[0]['gene_level_drugs'] if gene_drugs else []
        v_list = var_drugs[0]['variant_level_drugs'] if var_drugs else []
        r_list = res_drugs[0]['resistance_drugs'] if res_drugs else []
        
        print(f"\n[Caso] {case['gene']} {case['variant']}")
        print(f"  Farmaci sensibili trovati a livello di GENE (potenziale pollution):")
        print(f"    {g_list}")
        print(f"  Farmaci sensibili trovati a livello di VARIANTE (corretti per la variante):")
        print(f"    {v_list}")
        print(f"  Farmaci a cui la variante è RESISTENTE:")
        print(f"    {r_list}")
        
    # ---------------------------------------------------------
    # Query C — Mismatch istologico
    # ---------------------------------------------------------
    query_c = """
    MATCH (g:Gene)-[:HAS_VARIANT]->(v:Variant)-[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)-[:HAS_EVIDENCE]->(e:Evidence)
    WHERE e.evidence_level IN ['A', 'B', 'LEVEL_1', 'LEVEL_2', '1', '2']
    RETURN DISTINCT g.hugo_symbol AS gene, v.variant_name AS variant, e.disease AS strong_evidence_tumor
    """
    db_strong_evidences = run_cypher(query_c)
    
    benchmark_csv = PROJECT_ROOT / "mtb-graphrag" / "backend" / "benchmark" / "benchmark_papers_summary_30_v2.csv"
    bench_cases = []
    with open(benchmark_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bench_cases.append(row)
            
    mismatches = []
    for ev in db_strong_evidences:
        g = ev['gene']
        v = ev['variant']
        t = ev['strong_evidence_tumor']
        
        if not t:
            continue
            
        for b in bench_cases:
            if b['gene'] == g and b['variant'] == v:
                b_tumor = b['tumor']
                
                # Semplice controllo di mismatch
                t_low = t.lower()
                b_low = b_tumor.lower()
                
                # Check if it's truly a mismatch
                if t_low not in b_low and b_low not in t_low and "solid tumor" not in t_low and "cancer" not in t_low:
                    mismatches.append({
                        "benchmark_case_id": b['case_id'],
                        "gene": g,
                        "variant": v,
                        "benchmark_tumor": b_tumor,
                        "strong_evidence_tumor_in_db": t
                    })
                    
    # Deduplicate mismatches for clean output
    unique_mismatches = []
    seen = set()
    for m in mismatches:
        sig = (m["benchmark_case_id"], m["gene"], m["variant"], m["strong_evidence_tumor_in_db"])
        if sig not in seen:
            seen.add(sig)
            unique_mismatches.append(m)
            
    print_section("QUERY C - Mismatch istologico", query_c, unique_mismatches)

if __name__ == "__main__":
    main()
